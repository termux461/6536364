import hashlib
import hmac
import uuid
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.i18n import t
from bot.services.app_settings import get_appearance
from bot.services.fulfillment import fulfil_payment
from bot.services.payments.cryptobot import CryptoBotProvider
from bot.services.payments.yookassa import YooKassaProvider
from bot.services.referral import referral_stats
from bot.services.support import ensure_categories_seeded
from config import settings
from database.db import async_session, init_db
from database.models import (
    Payment, PaymentStatus, SenderType, Subscription, SubscriptionStatus,
    Ticket, TicketCategory, TicketMessage, TicketStatus, User,
)
from webapp.security import validate_init_data

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="VPN Bot Support Mini App API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/webapp/static", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static"), name="webapp-static")
app.mount("/webapp/uploads", StaticFiles(directory=UPLOAD_DIR), name="webapp-uploads")


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.get("/webapp")
@app.get("/webapp/")
async def webapp_index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "static" / "index.html")


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def get_current_user(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    session: AsyncSession = Depends(get_session),
) -> User:
    tg_data = validate_init_data(x_telegram_init_data, settings.BOT_TOKEN)
    if not tg_data:
        raise HTTPException(status_code=401, detail="Invalid Telegram init data")

    tg_id = tg_data["id"]
    user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalar_one_or_none()
    if not user:
        user = User(tg_id=tg_id, username=tg_data.get("username"), full_name=tg_data.get("first_name"))
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def notify_admins_new_ticket(ticket: Ticket, first_message: str) -> None:
    text = f"🎫 Новый тикет #{ticket.id}: {ticket.subject}\n\n{first_message}"
    reply_markup = {"inline_keyboard": [[{"text": "✏️ Ответить", "callback_data": f"admin_ticket_reply:{ticket.id}"}]]}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for admin_id in settings.admin_ids:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                    json={"chat_id": admin_id, "text": text, "reply_markup": reply_markup},
                )
            except httpx.HTTPError:
                pass


async def notify_user_payment_success(payment: Payment, user: User, sub) -> None:
    text = t(user.locale, "buy.payment_success") + "\n\n" + t(
        user.locale, "buy.config_caption",
        expires=sub.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
        url=sub.subscription_url or "—",
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                json={"chat_id": user.tg_id, "text": text},
            )
        except httpx.HTTPError:
            pass


@app.get("/api/config")
async def get_config(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
    appearance = await get_appearance(session)
    await ensure_categories_seeded(session)
    categories = (
        await session.execute(select(TicketCategory).where(TicketCategory.is_active.is_(True)).order_by(TicketCategory.sort_order))
    ).scalars().all()
    return {
        "locale": user.locale,
        "brand_name": appearance["webapp_brand_name"],
        "accent_color": appearance["webapp_accent_color"],
        "logo_url": appearance["webapp_logo_url"] or None,
        "categories": [
            {"id": c.id, "title": c.title_ru if user.locale == "ru" else c.title_en}
            for c in categories
        ],
    }


@app.get("/api/me")
async def get_me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
    sub = (
        await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.tariff))
            .where(Subscription.user_id == user.id, Subscription.status == SubscriptionStatus.ACTIVE)
            .order_by(Subscription.expires_at.desc())
        )
    ).scalars().first()
    stats = await referral_stats(session, user)
    return {
        "tg_id": user.tg_id,
        "username": user.username,
        "full_name": user.full_name,
        "locale": user.locale,
        "balance": stats["balance"],
        "referral_count": stats["count"],
        "referral_earned": stats["earned"],
        "subscription": {
            "tariff_name": sub.tariff.name if sub else None,
            "expires_at": sub.expires_at.isoformat() if sub else None,
            "subscription_url": sub.subscription_url if sub else None,
        } if sub else None,
    }


def _serialize_message(m: TicketMessage) -> dict:
    return {
        "id": m.id,
        "sender_type": m.sender_type.value,
        "text": m.text,
        "attachment_url": f"/webapp/uploads/{Path(m.attachment_path).name}" if m.attachment_path else None,
        "attachment_type": m.attachment_type,
        "created_at": m.created_at.isoformat(),
    }


def _serialize_ticket(t: Ticket, locale: str, messages: list[TicketMessage] | None = None) -> dict:
    category = None
    if t.category:
        category = t.category.title_ru if locale == "ru" else t.category.title_en
    data = {
        "id": t.id, "subject": t.subject, "status": t.status.value, "category": category,
        "created_at": t.created_at.isoformat(), "updated_at": t.updated_at.isoformat(),
    }
    if messages is not None:
        data["messages"] = [_serialize_message(m) for m in messages]
    return data


@app.get("/api/tickets")
async def list_tickets(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    tickets = (
        await session.execute(
            select(Ticket).options(selectinload(Ticket.category))
            .where(Ticket.user_id == user.id).order_by(Ticket.updated_at.desc())
        )
    ).scalars().all()
    return [_serialize_ticket(t, user.locale) for t in tickets]


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ticket = (
        await session.execute(
            select(Ticket).options(selectinload(Ticket.category))
            .where(Ticket.id == ticket_id, Ticket.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    messages = (
        await session.execute(select(TicketMessage).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at))
    ).scalars().all()
    return _serialize_ticket(ticket, user.locale, messages)


async def _save_attachment(file: UploadFile | None) -> tuple[str | None, str | None]:
    if file is None or not file.filename:
        return None, None
    ext = Path(file.filename).suffix
    name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / name
    content = await file.read()
    dest.write_bytes(content)
    attachment_type = "photo" if (file.content_type or "").startswith("image/") else "file"
    return str(dest), attachment_type


@app.post("/api/tickets")
async def create_ticket(
    subject: str = Form(...),
    message: str = Form(...),
    category_id: int | None = Form(None),
    file: UploadFile | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    ticket = Ticket(user_id=user.id, subject=subject[:255], category_id=category_id, status=TicketStatus.OPEN)
    session.add(ticket)
    await session.flush()

    attachment_path, attachment_type = await _save_attachment(file)
    msg = TicketMessage(ticket_id=ticket.id, sender_type=SenderType.USER, text=message,
                         attachment_path=attachment_path, attachment_type=attachment_type)
    session.add(msg)
    await session.commit()
    await session.refresh(ticket, attribute_names=["category"])

    await notify_admins_new_ticket(ticket, message)
    return _serialize_ticket(ticket, user.locale, [msg])


@app.post("/api/tickets/{ticket_id}/messages")
async def add_message(
    ticket_id: int,
    message: str = Form(...),
    file: UploadFile | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user.id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    attachment_path, attachment_type = await _save_attachment(file)
    msg = TicketMessage(ticket_id=ticket.id, sender_type=SenderType.USER, text=message,
                         attachment_path=attachment_path, attachment_type=attachment_type)
    session.add(msg)
    if ticket.status == TicketStatus.CLOSED:
        ticket.status = TicketStatus.OPEN
    await session.commit()

    await notify_admins_new_ticket(ticket, message)
    return _serialize_message(msg)


async def _process_paid_webhook(external_id: str, provider_code: str) -> None:
    async with async_session() as session:
        payment = (
            await session.execute(
                select(Payment).where(Payment.external_id == external_id, Payment.provider == provider_code)
            )
        ).scalar_one_or_none()
        if not payment or payment.status == PaymentStatus.PAID:
            return
        sub = await fulfil_payment(session, payment)
        user = (await session.execute(select(User).where(User.id == payment.user_id))).scalar_one()
        await notify_user_payment_success(payment, user, sub)


@app.post("/api/webhooks/cryptobot")
async def cryptobot_webhook(request: Request) -> dict:
    if not settings.CRYPTOBOT_API_TOKEN:
        raise HTTPException(status_code=404, detail="Not configured")

    body = await request.body()
    signature = request.headers.get("Crypto-Pay-API-Signature", "")
    secret = hashlib.sha256(settings.CRYPTOBOT_API_TOKEN.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    provider = CryptoBotProvider(settings.CRYPTOBOT_API_TOKEN, settings.CRYPTOBOT_API_URL)
    result = await provider.webhook_handler(data)
    if result:
        external_id, is_paid = result
        if is_paid:
            await _process_paid_webhook(external_id, "cryptobot")
    return {"ok": True}


@app.post("/api/webhooks/yookassa")
async def yookassa_webhook(request: Request) -> dict:
    if not (settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY):
        raise HTTPException(status_code=404, detail="Not configured")

    data = await request.json()
    provider = YooKassaProvider(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
    result = await provider.webhook_handler(data)
    if result:
        external_id, is_paid = result
        if is_paid:
            await _process_paid_webhook(external_id, "yookassa")
    return {"ok": True}
