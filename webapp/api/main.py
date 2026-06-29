import uuid
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.db import async_session, init_db
from database.models import SenderType, Ticket, TicketMessage, TicketStatus, User
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


def _serialize_message(m: TicketMessage) -> dict:
    return {
        "id": m.id,
        "sender_type": m.sender_type.value,
        "text": m.text,
        "attachment_url": f"/webapp/uploads/{Path(m.attachment_path).name}" if m.attachment_path else None,
        "attachment_type": m.attachment_type,
        "created_at": m.created_at.isoformat(),
    }


def _serialize_ticket(t: Ticket, messages: list[TicketMessage] | None = None) -> dict:
    data = {"id": t.id, "subject": t.subject, "status": t.status.value, "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat()}
    if messages is not None:
        data["messages"] = [_serialize_message(m) for m in messages]
    return data


@app.get("/api/tickets")
async def list_tickets(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    tickets = (
        await session.execute(select(Ticket).where(Ticket.user_id == user.id).order_by(Ticket.updated_at.desc()))
    ).scalars().all()
    return [_serialize_ticket(t) for t in tickets]


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
    ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user.id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    messages = (
        await session.execute(select(TicketMessage).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at))
    ).scalars().all()
    return _serialize_ticket(ticket, messages)


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
    file: UploadFile | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    ticket = Ticket(user_id=user.id, subject=subject[:255], status=TicketStatus.OPEN)
    session.add(ticket)
    await session.flush()

    attachment_path, attachment_type = await _save_attachment(file)
    msg = TicketMessage(ticket_id=ticket.id, sender_type=SenderType.USER, text=message,
                         attachment_path=attachment_path, attachment_type=attachment_type)
    session.add(msg)
    await session.commit()
    await session.refresh(ticket)

    await notify_admins_new_ticket(ticket, message)
    return _serialize_ticket(ticket, [msg])


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
