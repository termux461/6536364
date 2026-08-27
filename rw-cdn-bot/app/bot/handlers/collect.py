"""Data collection FSM, started once a payment is confirmed.

Every secret is encrypted before it touches the database and the bot never echoes it back.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import (
    dns_mode_keyboard,
    ssh_auth_keyboard,
    yandex_auth_keyboard,
)
from app.bot.notifications import ensure_progress_message
from app.bot.states import CollectData
from app.config import get_settings
from app.core.crypto import secret_box
from app.models import User
from app.models.enums import OrderStatus, SSHAuthType, YandexAuthType
from app.repositories import DeploymentRepository, InfraRepository, OrderRepository
from app.services.dns import verify_a_record, verify_cname_record
from app.services.queue import JobQueue
from app.services.remnawave import RemnawaveClient
from app.services.vault import purge_yandex_cookies, read_yandex_cookies, store_yandex_cookies
from app.services.yandex import CookieJar, YandexCloudClient, build_auth, parse_cookies

logger = logging.getLogger(__name__)
router = Router(name="collect")
# Commands that must work even while a collection FSM state is active are registered on
# this router, which is included *before* the collection one.
commands_router = Router(name="collect_commands")

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}$", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
MAX_SECRET_BYTES = 32 * 1024


async def start_collection(message: Message, state: FSMContext, order_id: int) -> None:
    await state.clear()
    await state.update_data(order_id=order_id)
    await state.set_state(CollectData.panel_url)
    await message.answer(texts.ASK_PANEL_URL)


async def _order_id(state: FSMContext) -> int:
    data = await state.get_data()
    return int(data["order_id"])


async def _read_payload(message: Message, limit: int = MAX_SECRET_BYTES) -> str | None:
    """Accept a secret as plain text or as an uploaded file."""
    if message.document:
        if (message.document.file_size or 0) > limit:
            await message.answer("Файл слишком большой.")
            return None
        buffer = await message.bot.download(message.document)
        return buffer.read().decode("utf-8", errors="replace") if buffer else None
    return message.text


def _uploaded_name(message: Message) -> str | None:
    return message.document.file_name if message.document else None


async def _drop_rejected_cookies(row, order_id: int) -> None:
    """Credentials that failed verification are useless — do not let them sit out the TTL."""
    if row.auth_type == YandexAuthType.COOKIE:
        await purge_yandex_cookies(order_id)


async def _store_cookies(message: Message, order_id: int) -> CookieJar | None:
    """Parse what the customer sent and park it in the vault for this deployment only.

    Cookies never reach the database: they go to Redis under a TTL and are deleted the moment
    the last Yandex step succeeds.
    """
    raw = (await _read_payload(message)) or ""
    try:
        jar = parse_cookies(raw, filename=_uploaded_name(message))
    except Exception as exc:  # noqa: BLE001 — the reason is actionable, show it verbatim
        await message.answer(f"{exc}")
        return None

    # The jar is stored whole, not flattened to a header: the worker needs the issuing
    # domains and the expiry, and the vault entry is given the session's own lifetime.
    await store_yandex_cookies(order_id, jar)
    return jar


# --------------------------------------------------------------------- Remnawave


@router.message(CollectData.panel_url)
async def panel_url(message: Message, state: FSMContext, session: AsyncSession) -> None:
    url = (message.text or "").strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        await message.answer("Нужен полный URL, например <code>https://panel.example.com</code>")
        return
    infra = InfraRepository(session)
    row = await infra.remnawave_or_create(await _order_id(state))
    row.panel_url = url
    await state.set_state(CollectData.panel_token)
    await message.answer(texts.ASK_PANEL_TOKEN)


@router.message(CollectData.panel_token)
async def panel_token(message: Message, state: FSMContext, session: AsyncSession) -> None:
    token = (message.text or "").strip()
    if len(token) < 10:
        await message.answer("Токен выглядит слишком коротким. Проверьте и отправьте снова.")
        return
    row = await InfraRepository(session).remnawave_or_create(await _order_id(state))
    row.api_token_enc = secret_box().encrypt(token)
    await message.delete()
    await message.answer(texts.SECRET_RECEIVED)
    await _detect_panel_version(message, row, token)
    await state.set_state(CollectData.origin_ip)
    await message.answer(texts.ASK_ORIGIN_IP)


async def _detect_panel_version(message: Message, row, token: str) -> None:
    """Work out whether this panel speaks API v2 or v3, and remember the answer.

    Best-effort on purpose: an unreachable panel is not a reason to abandon the order here.
    The dialect is detected again when the deployment actually runs, and the customer just
    learns sooner if their panel cannot be reached at all.
    """
    if not row.panel_url:
        return
    try:
        async with RemnawaveClient(row.panel_url, token) as client:
            row.api_version = str(client.version)
            described = client.describe()
    except Exception as exc:  # noqa: BLE001 — a failed probe must not block data collection
        logger.info("Remnawave version probe failed for %s: %s", row.panel_url, exc)
        await message.answer(texts.PANEL_VERSION_UNKNOWN.format(reason=str(exc)[:200]))
        return
    await message.answer(texts.PANEL_VERSION_DETECTED.format(version=described))


# ------------------------------------------------------------------ Origin Server


@router.message(CollectData.origin_ip)
async def origin_ip(message: Message, state: FSMContext, session: AsyncSession) -> None:
    value = (message.text or "").strip()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        await message.answer("Это не похоже на IP-адрес. Отправьте IP Origin Server.")
        return
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    origin.origin_ip = value
    await state.set_state(CollectData.ssh_port)
    await message.answer(texts.ASK_SSH_PORT)


@router.message(CollectData.ssh_port)
async def ssh_port(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip()
    port = int(raw) if raw.isdigit() else 2222
    if not 1 <= port <= 65535:
        await message.answer("Порт должен быть в диапазоне 1–65535.")
        return
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    origin.ssh_port = port
    await state.set_state(CollectData.ssh_user)
    await message.answer(texts.ASK_SSH_USER)


@router.message(CollectData.ssh_user)
async def ssh_user(message: Message, state: FSMContext, session: AsyncSession) -> None:
    username = (message.text or "").strip() or "root"
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    origin.ssh_username = username
    await state.set_state(CollectData.ssh_auth)
    await message.answer(texts.ASK_SSH_AUTH, reply_markup=ssh_auth_keyboard())


@router.callback_query(CollectData.ssh_auth, F.data.startswith("ssh:"))
async def ssh_auth(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    mode = callback.data.split(":")[1]
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    if mode == "key":
        origin.ssh_auth_type = SSHAuthType.KEY
        await state.set_state(CollectData.ssh_key)
        await callback.message.answer(texts.ASK_SSH_KEY)
    else:
        origin.ssh_auth_type = SSHAuthType.PASSWORD
        await state.set_state(CollectData.ssh_password)
        await callback.message.answer(texts.ASK_SSH_PASSWORD)
    await callback.answer()


@router.message(CollectData.ssh_key)
async def ssh_key(message: Message, state: FSMContext, session: AsyncSession) -> None:
    payload = await _read_payload(message)
    if not payload or "PRIVATE KEY" not in payload:
        await message.answer("Не похоже на приватный ключ. Отправьте содержимое файла целиком.")
        return
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    origin.ssh_private_key_enc = secret_box().encrypt(payload)
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    await message.answer(texts.SECRET_RECEIVED)
    await state.set_state(CollectData.origin_domain)
    await message.answer(texts.ASK_ORIGIN_DOMAIN)


@router.message(CollectData.ssh_password)
async def ssh_password(message: Message, state: FSMContext, session: AsyncSession) -> None:
    password = (message.text or "").strip()
    if not password:
        await message.answer("Пустой пароль не подойдёт.")
        return
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    origin.ssh_password_enc = secret_box().encrypt(password)
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    await message.answer(texts.SECRET_RECEIVED)
    await state.set_state(CollectData.origin_domain)
    await message.answer(texts.ASK_ORIGIN_DOMAIN)


# ----------------------------------------------------------------------- domains


@router.message(CollectData.origin_domain)
async def origin_domain(message: Message, state: FSMContext, session: AsyncSession) -> None:
    domain = (message.text or "").strip().lower().rstrip(".")
    if not DOMAIN_RE.match(domain):
        await message.answer("Некорректный домен. Пример: <code>origin.example.com</code>")
        return
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    origin.origin_domain = domain
    await state.set_state(CollectData.cdn_domain)
    await message.answer(texts.ASK_CDN_DOMAIN)


@router.message(CollectData.cdn_domain)
async def cdn_domain(message: Message, state: FSMContext, session: AsyncSession) -> None:
    domain = (message.text or "").strip().lower().rstrip(".")
    if not DOMAIN_RE.match(domain):
        await message.answer("Некорректный домен. Пример: <code>cdn.example.com</code>")
        return
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    if domain == origin.origin_domain:
        await message.answer("CDN Domain должен отличаться от Origin Domain.")
        return
    origin.cdn_domain = domain
    await state.set_state(CollectData.email)
    await message.answer(texts.ASK_EMAIL)


@router.message(CollectData.email)
async def email(message: Message, state: FSMContext, session: AsyncSession) -> None:
    value = (message.text or "").strip()
    if not EMAIL_RE.match(value):
        await message.answer("Некорректный email.")
        return
    origin = await InfraRepository(session).origin_or_create(await _order_id(state))
    origin.letsencrypt_email = value
    await state.set_state(CollectData.yandex_auth_mode)
    await message.answer(
        texts.ASK_YANDEX_AUTH_MODE,
        reply_markup=yandex_auth_keyboard(get_settings().yandex_cookie_auth_enabled),
    )


# ------------------------------------------------------------------ Yandex Cloud


@router.message(CollectData.yandex_cloud_id)
async def yandex_cloud_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    row = await InfraRepository(session).yandex_or_create(await _order_id(state))
    row.cloud_id = (message.text or "").strip()
    await state.set_state(CollectData.yandex_folder_id)
    await message.answer(texts.ASK_YANDEX_FOLDER_ID)


@router.message(CollectData.yandex_folder_id)
async def yandex_folder_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    folder = (message.text or "").strip()
    if len(folder) < 5:
        await message.answer("Folder ID выглядит некорректно.")
        return
    row = await InfraRepository(session).yandex_or_create(await _order_id(state))
    row.folder_id = folder
    await _after_scope(message, state, session, row)


@router.callback_query(CollectData.yandex_auth_mode, F.data.startswith("yauth:"))
async def yandex_auth_mode(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    mode = callback.data.split(":")[1]
    settings = get_settings()
    if mode == YandexAuthType.COOKIE and not settings.yandex_cookie_auth_enabled:
        await callback.answer("Этот способ отключён", show_alert=True)
        return

    row = await InfraRepository(session).yandex_or_create(await _order_id(state))
    row.auth_type = mode
    await session.flush()

    next_state, prompt = {
        YandexAuthType.SERVICE_ACCOUNT: (CollectData.yandex_key, texts.ASK_YANDEX_KEY),
        YandexAuthType.OAUTH: (CollectData.yandex_oauth, texts.ASK_YANDEX_OAUTH),
        YandexAuthType.COOKIE: (CollectData.yandex_cookies, texts.ASK_YANDEX_COOKIES),
    }[mode]
    await state.set_state(next_state)
    await callback.message.answer(prompt)
    await callback.answer()


async def _verify_and_continue(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    row,
    *,
    cookies: str | None = None,
) -> None:
    """Prove the credential works before it is accepted.

    Failing here costs the customer one more message. Failing three hours later, mid-deploy,
    costs a stuck order — so the check happens now.
    """
    order_id = await _order_id(state)
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass

    settings = get_settings()
    box = secret_box()
    try:
        auth = build_auth(
            auth_type=row.auth_type or YandexAuthType.SERVICE_ACCOUNT,
            service_account_key=box.decrypt(row.service_account_key_enc),
            oauth_token=box.decrypt(row.oauth_token_enc),
            cookies=cookies,
            cookie_exchange_url=settings.yandex_cookie_exchange_url,
            cookie_token_field=settings.yandex_cookie_token_field,
        )
        # Obtain a token first: if that fails, the cause is the credential itself, and
        # reporting it per-service would point the customer at the wrong thing.
        await auth.token()
        client = YandexCloudClient(folder_id=row.folder_id or "", auth=auth)
        report = await client.check_access(need_dns=False)
    except Exception as exc:  # noqa: BLE001 — the reason goes back to the customer verbatim
        await _drop_rejected_cookies(row, order_id)
        await message.answer(texts.YANDEX_AUTH_FAILED.format(reason=str(exc)[:400]))
        return

    if report.denied:
        await _drop_rejected_cookies(row, order_id)
        await message.answer(texts.YANDEX_ACCESS_DENIED.format(details=report.describe_denied()))
        return
    if report.failed:
        # Nothing to do with roles: the probes never got an answer.
        await _drop_rejected_cookies(row, order_id)
        await message.answer(texts.YANDEX_CHECK_FAILED.format(reason=report.describe_failed()))
        return

    row.auth_checked_at = datetime.now(UTC)
    await session.flush()
    await message.answer(texts.YANDEX_AUTH_OK)
    await _resolve_scope(message, state, session, row, client)


@router.message(CollectData.yandex_key)
async def yandex_key(message: Message, state: FSMContext, session: AsyncSession) -> None:
    payload = await _read_payload(message)
    if not payload:
        await message.answer("Не удалось прочитать ключ.")
        return
    try:
        parsed = json.loads(payload)
        if not {"id", "service_account_id", "private_key"} <= set(parsed):
            raise ValueError
    except ValueError:
        await message.answer(
            "Нужен JSON авторизованного ключа с полями id, service_account_id, private_key."
        )
        return
    row = await InfraRepository(session).yandex_or_create(await _order_id(state))
    row.service_account_key_enc = secret_box().encrypt(payload)
    await _verify_and_continue(message, state, session, row)


@router.message(CollectData.yandex_oauth)
async def yandex_oauth(message: Message, state: FSMContext, session: AsyncSession) -> None:
    token = ((await _read_payload(message)) or "").strip()
    if len(token) < 20:
        await message.answer("Токен выглядит слишком коротким.")
        return
    row = await InfraRepository(session).yandex_or_create(await _order_id(state))
    row.oauth_token_enc = secret_box().encrypt(token)
    await _verify_and_continue(message, state, session, row)


@router.message(CollectData.yandex_cookies)
async def yandex_cookies(message: Message, state: FSMContext, session: AsyncSession) -> None:
    order_id = await _order_id(state)
    row = await InfraRepository(session).yandex_or_create(order_id)
    jar = await _store_cookies(message, order_id)
    if jar is None:
        return
    await _verify_and_continue(message, state, session, row, cookies=jar.dumps())


async def _resolve_scope(
    message: Message, state: FSMContext, session: AsyncSession, row, client
) -> None:
    """Fill in Cloud ID and Folder ID from what the credential can actually see.

    The customer should not have to dig IDs out of the console. One cloud with one folder
    needs no question at all; several get a picker; and if the listing is unavailable (a
    service account without resource-manager access, say) we fall back to asking by hand.
    """
    try:
        scope = await client.discover_scope()
    except Exception as exc:  # noqa: BLE001 — falling back to manual entry is fine
        logger.info("Cannot list clouds/folders automatically: %s", exc)
        await state.set_state(CollectData.yandex_cloud_id)
        await message.answer(texts.ASK_YANDEX_CLOUD_ID)
        return

    clouds = scope.get("clouds") or []
    if not clouds:
        await state.set_state(CollectData.yandex_cloud_id)
        await message.answer(texts.ASK_YANDEX_CLOUD_ID)
        return

    if len(clouds) > 1:
        await state.update_data(scope_folders=scope["folders"])
        await state.set_state(CollectData.yandex_cloud_pick)
        await message.answer(
            texts.PICK_CLOUD,
            reply_markup=_pick_keyboard("ycloud", [(c["id"], c.get("name") or c["id"]) for c in clouds]),
        )
        return

    cloud = clouds[0]
    row.cloud_id = str(cloud["id"])
    await _offer_folders(message, state, session, row, scope["folders"].get(cloud["id"]) or [])


async def _offer_folders(
    message: Message, state: FSMContext, session: AsyncSession, row, folders: list[dict]
) -> None:
    if not folders:
        await state.set_state(CollectData.yandex_folder_id)
        await message.answer(texts.ASK_YANDEX_FOLDER_ID)
        return

    if len(folders) > 1:
        await state.set_state(CollectData.yandex_folder_pick)
        await message.answer(
            texts.PICK_FOLDER,
            reply_markup=_pick_keyboard(
                "yfolder", [(f["id"], f.get("name") or f["id"]) for f in folders]
            ),
        )
        return

    row.folder_id = str(folders[0]["id"])
    await session.flush()
    await message.answer(
        texts.SCOPE_RESOLVED.format(
            cloud=row.cloud_id or "—",
            folder=f"{folders[0].get('name') or ''} ({row.folder_id})".strip(),
        )
    )
    await _after_scope(message, state, session, row)


def _pick_keyboard(prefix: str, items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name[:60], callback_data=f"{prefix}:{ident}")]
            for ident, name in items[:20]
        ]
    )


@router.callback_query(CollectData.yandex_cloud_pick, F.data.startswith("ycloud:"))
async def pick_cloud(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    cloud_id = callback.data.split(":", 1)[1]
    row = await InfraRepository(session).yandex_or_create(await _order_id(state))
    row.cloud_id = cloud_id
    data = await state.get_data()
    folders = (data.get("scope_folders") or {}).get(cloud_id) or []
    await callback.answer()
    await _offer_folders(callback.message, state, session, row, folders)


@router.callback_query(CollectData.yandex_folder_pick, F.data.startswith("yfolder:"))
async def pick_folder(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    row = await InfraRepository(session).yandex_or_create(await _order_id(state))
    row.folder_id = callback.data.split(":", 1)[1]
    await session.flush()
    await callback.answer()
    await _after_scope(callback.message, state, session, row)


async def _after_scope(message: Message, state: FSMContext, session: AsyncSession, row) -> None:
    """Now that the folder is known, check roles there — and grant them if we may."""
    order_id = await _order_id(state)
    settings = get_settings()
    box = secret_box()
    auth = build_auth(
        auth_type=row.auth_type or YandexAuthType.SERVICE_ACCOUNT,
        service_account_key=box.decrypt(row.service_account_key_enc),
        oauth_token=box.decrypt(row.oauth_token_enc),
        cookies=await read_yandex_cookies(order_id),
        cookie_exchange_url=settings.yandex_cookie_exchange_url,
        cookie_token_field=settings.yandex_cookie_token_field,
    )
    client = YandexCloudClient(folder_id=row.folder_id or "", auth=auth)

    try:
        report = await client.check_access(need_dns=False)
    except Exception as exc:  # noqa: BLE001
        await message.answer(texts.YANDEX_CHECK_FAILED.format(reason=str(exc)[:400]))
        return

    if report.denied:
        granted = False
        subject = await _subject_for(client, row)
        if subject:
            try:
                granted = await client.ensure_roles(row.folder_id or "", report, subject=subject)
            except Exception as exc:  # noqa: BLE001 — granting is best-effort
                logger.info("Role self-grant failed: %s", exc)
        if granted:
            await message.answer(texts.ROLES_GRANTED.format(roles=", ".join(report.missing_roles())))
            report = await client.check_access(need_dns=False)

    if report.denied:
        await message.answer(texts.YANDEX_ACCESS_DENIED.format(details=report.describe_denied()))
        await state.set_state(CollectData.yandex_login)
        await message.answer(texts.ASK_YANDEX_LOGIN)
        return
    if report.failed:
        await message.answer(texts.YANDEX_CHECK_FAILED.format(reason=report.describe_failed()))
        return

    await session.flush()
    await state.set_state(CollectData.dns_mode)
    await message.answer(texts.ASK_DNS_MODE, reply_markup=dns_mode_keyboard())


async def _subject_for(client, row) -> dict | None:
    """Who to grant the roles to.

    A service account grants to itself. A user credential needs the account id, which is only
    resolvable from a login — so it is used if the customer supplied one earlier.
    """
    if row.auth_type == YandexAuthType.SERVICE_ACCOUNT and row.service_account_key_enc:
        import json

        from app.core.crypto import secret_box as _box

        try:
            key = json.loads(_box().decrypt(row.service_account_key_enc) or "{}")
        except ValueError:
            return None
        sa_id = key.get("service_account_id")
        return {"id": sa_id, "type": "serviceAccount"} if sa_id else None

    login = (row.yandex_login or "").strip()
    if not login:
        return None
    user_id = await client.user_id_by_login(login)
    return {"id": user_id, "type": "userAccount"} if user_id else None


@router.message(CollectData.yandex_login)
async def yandex_login(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Login is only needed to resolve the account id for granting roles."""
    login = (message.text or "").strip().lstrip("@")
    if len(login) < 2:
        await message.answer("Логин выглядит некорректно.")
        return
    row = await InfraRepository(session).yandex_or_create(await _order_id(state))
    row.yandex_login = login
    await session.flush()
    await _after_scope(message, state, session, row)


# -------------------------------------------------------------------------- DNS


@router.callback_query(CollectData.dns_mode, F.data.in_({"dns:cloudflare", "dns:yandex", "dns:manual"}))
async def dns_mode(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    mode = callback.data.split(":")[1]
    order_id = await _order_id(state)
    deployments = DeploymentRepository(session)
    deployment = await deployments.get_or_create(order_id)

    if mode == "cloudflare":
        await state.set_state(CollectData.cloudflare_token)
        await callback.message.answer(texts.ASK_CLOUDFLARE_TOKEN)
        await callback.answer()
        return

    await deployments.update_context(deployment, {"dns_provider": mode})
    await callback.answer()
    await _finish(callback.message, state, session, order_id)


@router.message(CollectData.cloudflare_token)
async def cloudflare_token(message: Message, state: FSMContext, session: AsyncSession) -> None:
    token = (message.text or "").strip()
    if len(token) < 20:
        await message.answer("Токен выглядит некорректно.")
        return
    order_id = await _order_id(state)
    deployments = DeploymentRepository(session)
    deployment = await deployments.get_or_create(order_id)
    await deployments.update_context(
        deployment,
        {"dns_provider": "cloudflare", "cloudflare_token_enc": secret_box().encrypt(token)},
    )
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    await message.answer(texts.SECRET_RECEIVED)
    await _finish(message, state, session, order_id)


async def _finish(message: Message, state: FSMContext, session: AsyncSession, order_id: int) -> None:
    orders = OrderRepository(session)
    order = await orders.get(order_id)
    if order is not None:
        await orders.set_status(order, OrderStatus.DEPLOYING)
    await state.clear()
    await message.answer(texts.DATA_SAVED)
    await session.commit()

    await ensure_progress_message(message.bot, order_id, message.chat.id)
    queue = JobQueue.from_settings()
    try:
        await queue.enqueue_deployment(order_id, reason="data_collected")
    finally:
        await queue.close()


# ------------------------------------------------------- manual DNS verification


@router.callback_query(F.data.startswith("dns:check:"))
async def dns_check(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    order_id = int(callback.data.split(":")[2])
    order = await OrderRepository(session).get(order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    infra = InfraRepository(session)
    origin = await infra.origin(order_id)
    yandex = await infra.yandex(order_id)
    ok = True
    if origin and origin.origin_domain and origin.origin_ip:
        ok = ok and await verify_a_record(origin.origin_domain, origin.origin_ip)
    if yandex and yandex.cdn_cname and origin and origin.cdn_domain:
        ok = ok and await verify_cname_record(origin.cdn_domain, yandex.cdn_cname)

    if not ok:
        await callback.answer(texts.DNS_NOT_YET, show_alert=True)
        return

    await callback.answer(texts.DNS_OK, show_alert=True)
    queue = JobQueue.from_settings()
    try:
        await queue.enqueue_deployment(order_id, reason="dns_confirmed")
    finally:
        await queue.close()


# ------------------------------------------------------------------- re-auth


@commands_router.message(F.text.regexp(r"^/reauth\s+(\d+)$").as_("match"))
async def reauth_start(message: Message, state: FSMContext, session: AsyncSession, match, user: User) -> None:
    """Resume an order parked because its Yandex credentials died."""
    order_id = int(match.group(1))
    order = await OrderRepository(session).get(order_id)
    if order is None or order.user_id != user.id:
        await message.answer("Заказ не найден.")
        return

    row = await InfraRepository(session).yandex(order_id)
    if row is None:
        await message.answer("Для этого заказа ещё не заданы данные Yandex Cloud.")
        return

    await state.clear()
    await state.update_data(order_id=order_id, reauth=True)
    await state.set_state(CollectData.reauth_value)
    prompt = {
        YandexAuthType.SERVICE_ACCOUNT: texts.ASK_YANDEX_KEY,
        YandexAuthType.OAUTH: texts.ASK_YANDEX_OAUTH,
        YandexAuthType.COOKIE: texts.ASK_YANDEX_COOKIES,
    }.get(row.auth_type, texts.ASK_YANDEX_KEY)
    await message.answer(prompt)


@router.message(CollectData.reauth_value)
async def reauth_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    order_id = await _order_id(state)
    infra = InfraRepository(session)
    row = await infra.yandex_or_create(order_id)
    box = secret_box()

    cookies: str | None = None
    if row.auth_type == YandexAuthType.COOKIE:
        jar = await _store_cookies(message, order_id)
        if jar is None:
            return
        cookies = jar.dumps()
    else:
        payload = ((await _read_payload(message)) or "").strip()
        if not payload:
            await message.answer("Не удалось прочитать значение.")
            return
        if row.auth_type == YandexAuthType.OAUTH:
            row.oauth_token_enc = box.encrypt(payload)
        else:
            row.service_account_key_enc = box.encrypt(payload)

    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass

    settings = get_settings()
    try:
        auth = build_auth(
            auth_type=row.auth_type or YandexAuthType.SERVICE_ACCOUNT,
            service_account_key=box.decrypt(row.service_account_key_enc),
            oauth_token=box.decrypt(row.oauth_token_enc),
            cookies=cookies,
            cookie_exchange_url=settings.yandex_cookie_exchange_url,
            cookie_token_field=settings.yandex_cookie_token_field,
        )
        await auth.token()
        client = YandexCloudClient(folder_id=row.folder_id or "", auth=auth)
        report = await client.check_access(need_dns=False)
    except Exception as exc:  # noqa: BLE001
        await _drop_rejected_cookies(row, order_id)
        await message.answer(texts.YANDEX_AUTH_FAILED.format(reason=str(exc)[:400]))
        return

    if report.denied:
        await _drop_rejected_cookies(row, order_id)
        await message.answer(texts.YANDEX_ACCESS_DENIED.format(details=report.describe_denied()))
        return
    if report.failed:
        await _drop_rejected_cookies(row, order_id)
        await message.answer(texts.YANDEX_CHECK_FAILED.format(reason=report.describe_failed()))
        return

    row.auth_checked_at = datetime.now(UTC)
    await state.clear()
    await session.commit()

    queue = JobQueue.from_settings()
    try:
        await queue.enqueue_deployment(order_id, reason="reauth")
    finally:
        await queue.close()
    await message.answer(texts.YANDEX_AUTH_OK + "\nПродолжаю настройку с того же места.")
