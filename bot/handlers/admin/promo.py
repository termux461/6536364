from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu, admin_promo_card_menu, admin_promo_menu
from bot.models.promo import Promo
from bot.utils.helpers import admin_filter
from bot.utils.states import AdminPromo

router = Router(name="admin_promo")
router.message.filter(admin_filter)
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:promo")
async def cb_admin_promo(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Promo).order_by(Promo.created_at.desc()))
        promos = list(result.scalars().all())
    await callback.message.edit_text("Промокоды:", reply_markup=admin_promo_menu(promos))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:promo:show:"))
async def cb_admin_promo_show(callback: CallbackQuery) -> None:
    promo_id = int(callback.data.split(":")[3])
    async with async_session() as session:
        promo = await session.get(Promo, promo_id)
    if promo is None:
        await callback.answer("Промокод не найден", show_alert=True)
        return
    text = (
        f"Промокод: {promo.code}\n"
        f"Скидка: {promo.discount_percent}%\n"
        f"Использован: {promo.used_count}/{promo.usage_limit}\n"
        f"Истекает: {promo.expires_at.strftime('%d.%m.%Y') if promo.expires_at else 'без срока'}"
    )
    await callback.message.edit_text(text, reply_markup=admin_promo_card_menu(promo.id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:promo:delete:"))
async def cb_admin_promo_delete(callback: CallbackQuery) -> None:
    promo_id = int(callback.data.split(":")[3])
    async with async_session() as session:
        promo = await session.get(Promo, promo_id)
        if promo is not None:
            await session.delete(promo)
            await session.commit()
    await callback.answer("Промокод удалён")
    async with async_session() as session:
        result = await session.execute(select(Promo).order_by(Promo.created_at.desc()))
        promos = list(result.scalars().all())
    await callback.message.edit_text("Промокоды:", reply_markup=admin_promo_menu(promos))


@router.callback_query(F.data == "admin:promo:add")
async def cb_admin_promo_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminPromo.code)
    await callback.message.edit_text("Введите код промокода (например, MAMMOT2026):", reply_markup=admin_back_menu("admin:promo"))
    await callback.answer()


@router.message(AdminPromo.code)
async def msg_promo_code(message: Message, state: FSMContext) -> None:
    await state.update_data(code=message.text.strip().upper())
    await state.set_state(AdminPromo.discount)
    await message.answer("Введите размер скидки в процентах (например, 15):")


@router.message(AdminPromo.discount)
async def msg_promo_discount(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 100):
        await message.answer("Введите число от 1 до 100:")
        return
    await state.update_data(discount=int(text))
    await state.set_state(AdminPromo.limit)
    await message.answer("Введите лимит использований (например, 100):")


@router.message(AdminPromo.limit)
async def msg_promo_limit(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите целое число:")
        return
    await state.update_data(limit=int(text))
    await state.set_state(AdminPromo.expires)
    await message.answer("Введите срок действия в днях (0 — без срока):")


@router.message(AdminPromo.expires)
async def msg_promo_expires(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Введите целое число:")
        return
    days = int(text)
    data = await state.get_data()

    promo = Promo(
        code=data["code"],
        discount_percent=data["discount"],
        usage_limit=data["limit"],
        expires_at=datetime.utcnow() + timedelta(days=days) if days > 0 else None,
    )
    async with async_session() as session:
        existing = await session.execute(select(Promo).where(Promo.code == promo.code))
        if existing.scalar_one_or_none() is not None:
            await message.answer("Такой код уже существует.")
            await state.clear()
            return
        session.add(promo)
        await session.commit()

    await state.clear()
    await message.answer(f"Промокод {promo.code} создан.", reply_markup=admin_back_menu("admin:promo"))
