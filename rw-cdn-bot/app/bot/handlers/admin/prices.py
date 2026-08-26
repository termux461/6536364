from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.filters import IsAdmin
from app.bot.handlers.admin.keyboards import back_button
from app.bot.states.order import AdminStates
from app.repositories import AuditRepository, TariffRepository

router = Router(name="admin_prices")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _tariff_keyboard(tariff_id: int, enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Цена", callback_data=f"adm:price:set:{tariff_id}")],
            [InlineKeyboardButton(text="📝 Название", callback_data=f"adm:price:name:{tariff_id}")],
            [InlineKeyboardButton(text="🧾 Описание", callback_data=f"adm:price:desc:{tariff_id}")],
            [
                InlineKeyboardButton(
                    text="🔴 Выключить" if enabled else "🟢 Включить",
                    callback_data=f"adm:price:toggle:{tariff_id}",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
        ]
    )


@router.callback_query(F.data == "adm:prices")
async def list_prices(callback: CallbackQuery, session: AsyncSession) -> None:
    repo = TariffRepository(session)
    await repo.ensure_default()
    tariffs = await repo.list_all()
    await callback.message.edit_text("💰 <b>Тарифы</b>", reply_markup=back_button())
    for tariff in tariffs:
        await callback.message.answer(
            f"<b>{tariff.name}</b>\n<code>{tariff.code}</code>\n\n{tariff.description}\n\n"
            f"Цена: <b>{tariff.price_display}</b>\n"
            f"Статус: {'🟢 активен' if tariff.enabled else '🔴 выключен'}",
            reply_markup=_tariff_keyboard(tariff.id, tariff.enabled),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:price:toggle:"))
async def toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff = await TariffRepository(session).get(int(callback.data.split(":")[3]))
    if tariff is None:
        await callback.answer("Не найден", show_alert=True)
        return
    tariff.enabled = not tariff.enabled
    if tariff.enabled and tariff.price <= 0:
        tariff.enabled = False
        await callback.answer("Сначала задайте цену больше нуля", show_alert=True)
        return
    await session.flush()
    await callback.answer("Готово")
    await callback.message.edit_reply_markup(reply_markup=_tariff_keyboard(tariff.id, tariff.enabled))


@router.callback_query(F.data.startswith("adm:price:"))
async def ask_field(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if len(parts) != 4 or parts[2] == "toggle":
        return
    field, tariff_id = parts[2], int(parts[3])
    await state.update_data(tariff_id=tariff_id, field=field)
    prompts = {
        "set": "Введите новую цену в рублях (например 1500 или 1500.50):",
        "name": "Введите новое название тарифа:",
        "desc": "Введите новое описание тарифа:",
    }
    await state.set_state(AdminStates.price)
    await callback.message.answer(prompts[field])
    await callback.answer()


@router.message(AdminStates.price)
async def apply_field(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    tariff = await TariffRepository(session).get(int(data["tariff_id"]))
    if tariff is None:
        await state.clear()
        await message.answer("Тариф не найден.")
        return

    field = data["field"]
    value = (message.text or "").strip()
    if field == "set":
        try:
            from app.services.payments.base import kopecks_from_rubles

            kopecks = kopecks_from_rubles(value.replace(",", "."))
        except Exception:  # noqa: BLE001
            await message.answer("Не удалось разобрать цену. Пример: 1500 или 1500.50")
            return
        if kopecks <= 0:
            await message.answer("Цена должна быть больше нуля.")
            return
        tariff.price = kopecks
    elif field == "name":
        tariff.name = value[:255]
    else:
        tariff.description = value

    await session.flush()
    await AuditRepository(session).log(
        "tariff.updated", admin_id=message.from_user.id, message=f"{tariff.code}:{field}"
    )
    await state.clear()
    await message.answer(f"✅ Обновлено. Текущая цена: <b>{tariff.price_display}</b>")
