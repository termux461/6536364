from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.filters import IsAdmin
from app.bot.states.order import AdminStates
from app.models.setting import MAINTENANCE_TEXT
from app.repositories import AuditRepository, SettingRepository

router = Router(name="admin_maintenance")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _keyboard(enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔴 Выключить техработы" if enabled else "🟢 Включить техработы",
                    callback_data="adm:maint:toggle",
                )
            ],
            [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="adm:maint:text")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
        ]
    )


@router.callback_query(F.data == "adm:maintenance")
async def show(callback: CallbackQuery, session: AsyncSession) -> None:
    repo = SettingRepository(session)
    enabled = await repo.maintenance_enabled()
    await callback.message.edit_text(
        f"🔧 <b>Технические работы</b>\n\nСостояние: {'ON' if enabled else 'OFF'}\n\n"
        f"Текст:\n{await repo.maintenance_text()}",
        reply_markup=_keyboard(enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:maint:toggle")
async def toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    repo = SettingRepository(session)
    enabled = not await repo.maintenance_enabled()
    await repo.set_maintenance(enabled)
    await AuditRepository(session).log(
        "maintenance.toggled", admin_id=callback.from_user.id, message="on" if enabled else "off"
    )
    await callback.answer("Готово")
    await show(callback, session)


@router.callback_query(F.data == "adm:maint:text")
async def ask_text(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.maintenance_text)
    await callback.message.answer("Отправьте новый текст сообщения о техработах:")
    await callback.answer()


@router.message(AdminStates.maintenance_text)
async def set_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await SettingRepository(session).set(MAINTENANCE_TEXT, message.text or "")
    await state.clear()
    await message.answer("✅ Текст обновлён.")
