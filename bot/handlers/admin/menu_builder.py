from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.common import ensure_menu_seeded
from database.models import MenuButton

router = Router(name="admin_menu_builder")


def _menu_keyboard(buttons: list[MenuButton]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{'👁' if b.is_visible else '🚫'} {b.title_ru} ({b.sort_order})",
            callback_data=f"admin_menu_toggle:{b.id}",
        )]
        for b in buttons
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(lambda m: m.text == "🧩 Меню бота")
async def list_menu_buttons(message: Message, session: AsyncSession, is_admin: bool) -> None:
    if not is_admin:
        return
    await ensure_menu_seeded(session)
    buttons = (await session.execute(select(MenuButton).order_by(MenuButton.sort_order))).scalars().all()
    await message.answer(
        "Кнопки главного меню (нажмите, чтобы показать/скрыть для пользователей).\n"
        "Порядок и тексты можно изменить только через панель администратора в браузере.",
        reply_markup=_menu_keyboard(buttons),
    )


@router.callback_query(F.data.startswith("admin_menu_toggle:"))
async def toggle_menu_button(callback: CallbackQuery, session: AsyncSession) -> None:
    btn_id = int(callback.data.split(":")[1])
    btn = (await session.execute(select(MenuButton).where(MenuButton.id == btn_id))).scalar_one_or_none()
    if btn:
        btn.is_visible = not btn.is_visible
        await session.commit()
        buttons = (await session.execute(select(MenuButton).order_by(MenuButton.sort_order))).scalars().all()
        await callback.message.edit_reply_markup(reply_markup=_menu_keyboard(buttons))
    await callback.answer()
