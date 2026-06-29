from aiogram import Router
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters import MenuAction
from bot.i18n import t
from bot.services.remnawave import http_ping
from database.models import Host

router = Router(name="speedtest")


@router.message(MenuAction("speedtest"))
async def show_status(message: Message, session: AsyncSession, locale: str) -> None:
    hosts = (await session.execute(select(Host).where(Host.is_active.is_(True)))).scalars().all()
    text = t(locale, "speedtest.title")
    for host in hosts:
        ms = await http_ping(host.api_url)
        status = "🟢 online" if ms is not None else "🔴 offline"
        text += "\n" + t(locale, "speedtest.line", name=host.name, status=status, ms=ms if ms is not None else "-")
    await message.answer(text)
