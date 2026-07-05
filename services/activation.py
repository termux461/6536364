import logging
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Bot
from aiogram.types import BufferedInputFile
from services.database import Database
from services.wgeasy import WgEasyClient
from config import Config

logger = logging.getLogger(__name__)

PROTO_LABELS = {
    "wg":  ("WireGuard",      "wireguard",  "wg"),
    "awg": ("AmneziaWG 2.0",  "amneziavpn", "awg"),
}


def _wg_client(config: Config, protocol: str) -> WgEasyClient:
    """Возвращает клиента нужного wg-easy инстанса для протокола."""
    if protocol == "awg" and getattr(config, "WG_EASY_URL_AWG", ""):
        return WgEasyClient(config.WG_EASY_URL_AWG, config.WG_EASY_PASS_AWG)
    return WgEasyClient(config.WG_EASY_URL, config.WG_EASY_PASSWORD)


async def _send_config(
    bot: Bot, user_id: int, protocol: str,
    plan_name: str, expires: datetime, conf_text, *, renewed: bool = False
):
    proto_name, _, file_prefix = PROTO_LABELS.get(protocol, ("VPN", "vpn", "vpn"))
    conf_bytes = conf_text.encode() if isinstance(conf_text, str) else conf_text
    filename = f"{file_prefix}_{plan_name.replace(' ', '_')}.conf"

    if protocol == "awg":
        client_note = "📱 Клиент: <a href='https://amnezia.org/download'><b>AmneziaVPN</b></a>"
        import_note = "Нажми <b>+</b> → <b>Добавить из файла</b> → выбери .conf"
    else:
        client_note = "📱 Клиент: <b>WireGuard</b> (App Store / Google Play)"
        import_note = "Нажми <b>+</b> → <b>Импортировать из файла</b>"

    title = "🔄 <b>Подписка продлена!</b>" if renewed else "✅ <b>Подписка активирована!</b>"

    await bot.send_document(
        user_id,
        document=BufferedInputFile(conf_bytes, filename=filename),
        caption=(
            f"{title}\n\n"
            f"🔒 Протокол: <b>{proto_name}</b>\n"
            f"📦 Тариф: <b>{plan_name}</b>\n"
            f"📅 Действует до: <b>{expires.strftime('%d.%m.%Y')}</b>\n\n"
            f"<b>Как подключиться:</b>\n"
            f"1. {client_note}\n"
            f"2. {import_note}\n\n"
            "Используй /start для главного меню."
        ),
        parse_mode="HTML"
    )


async def activate_subscription(
    bot: Bot, db: Database, config: Config,
    user_id: int, plan_id: int
) -> bool:
    """Создаёт новый WG-пир, подписку и отправляет .conf. Возвращает успех."""
    plan = await db.get_plan(plan_id)
    if not plan:
        return False

    protocol = plan["protocol"]  # 'wg' или 'awg'
    _, _, file_prefix = PROTO_LABELS.get(protocol, ("VPN", "vpn", "vpn"))

    wg = _wg_client(config, protocol)
    try:
        peer_name = f"{file_prefix}_user{user_id}_{plan['name'].replace(' ', '_')}"
        peer = await wg.create_peer(peer_name)
        peer_id = peer["id"]
        conf_text = await wg.get_peer_config(peer_id)
    except Exception as e:
        logger.error(f"WG peer creation failed for user {user_id} proto={protocol}: {e}")
        return False
    finally:
        await wg.close()

    now = datetime.utcnow()
    expires = now + timedelta(days=plan["duration_days"])
    await db.create_subscription(user_id, plan_id, protocol, peer_id, now, expires)

    await _send_config(bot, user_id, protocol, plan["name"], expires, conf_text)
    logger.info(f"Activated: user={user_id} plan={plan_id} proto={protocol} peer={peer_id}")
    return True


async def renew_subscription(
    bot: Bot, db: Database, config: Config,
    user_id: int, sub: dict, plan: dict
) -> bool:
    """Продлевает активную подписку: добавляет дни к текущему сроку.

    Пир не пересоздаётся — старый .conf продолжает работать. Отправляем его
    заново для удобства. Возвращает успех.
    """
    protocol = plan["protocol"]
    peer_id = sub.get("wg_peer_id")

    # Достаём текущий конфиг (пир уже существует). Если не вышло — продление
    # всё равно возможно, просто без вложения файла.
    conf_text: Optional[str] = None
    if peer_id:
        wg = _wg_client(config, protocol)
        try:
            conf_text = await wg.get_peer_config(peer_id)
        except Exception as e:
            logger.warning(f"Renew: config fetch failed user={user_id} peer={peer_id}: {e}")
        finally:
            await wg.close()

    # Считаем от текущей даты окончания, а не от «сейчас», чтобы не терять дни.
    current_expires = datetime.fromisoformat(sub["expires_at"])
    base = max(current_expires, datetime.utcnow())
    new_expires = base + timedelta(days=plan["duration_days"])
    await db.extend_subscription(sub["id"], new_expires)

    if conf_text is not None:
        await _send_config(
            bot, user_id, protocol, plan["name"], new_expires, conf_text, renewed=True
        )
    else:
        proto_name, _, _ = PROTO_LABELS.get(protocol, ("VPN", "vpn", "vpn"))
        await bot.send_message(
            user_id,
            f"🔄 <b>Подписка продлена!</b>\n\n"
            f"🔒 Протокол: <b>{proto_name}</b>\n"
            f"📦 Тариф: <b>{plan['name']}</b>\n"
            f"📅 Действует до: <b>{new_expires.strftime('%d.%m.%Y')}</b>\n\n"
            "Старый конфиг продолжает работать — переустанавливать не нужно.",
            parse_mode="HTML"
        )
    logger.info(f"Renewed: user={user_id} sub={sub['id']} proto={protocol} until={new_expires.date()}")
    return True


async def resend_config(
    bot: Bot, db: Database, config: Config, user_id: int, sub: dict
) -> bool:
    """Повторно скачивает и отправляет .conf активной подписки. Возвращает успех."""
    protocol = sub.get("protocol", "wg")
    peer_id = sub.get("wg_peer_id")
    if not peer_id:
        return False

    wg = _wg_client(config, protocol)
    try:
        conf_text = await wg.get_peer_config(peer_id)
    except Exception as e:
        logger.error(f"Resend config failed user={user_id} peer={peer_id}: {e}")
        return False
    finally:
        await wg.close()

    expires = datetime.fromisoformat(sub["expires_at"])
    await _send_config(bot, user_id, protocol, sub["plan_name"], expires, conf_text)
    logger.info(f"Config resent: user={user_id} sub={sub['id']} peer={peer_id}")
    return True
