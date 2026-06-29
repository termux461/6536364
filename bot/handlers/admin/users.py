from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu, admin_user_card_menu, admin_users_menu
from bot.services.users import get_user_by_tg_id
from bot.utils.helpers import admin_filter
from bot.utils.states import AdminBalance, AdminFindUser, AdminMessageUser

router = Router(name="admin_users")
router.message.filter(admin_filter)
router.callback_query.filter(admin_filter)


def _user_card_text(user) -> str:
    return (
        f"Пользователь {user.tg_id}\n"
        f"Юзернейм: {'@' + user.username if user.username else '-'}\n"
        f"Баланс: {user.balance}₽\n"
        f"Заработано с рефералов: {user.referral_earned}₽\n"
        f"Блокирован: {'да' if user.is_blocked else 'нет'}\n"
        f"Дата регистрации: {user.created_at.strftime('%d.%m.%Y')}"
    )


@router.callback_query(F.data == "admin:users")
async def cb_admin_users(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Раздел «Пользователи»:", reply_markup=admin_users_menu())
    await callback.answer()


@router.callback_query(F.data == "admin:users:find")
async def cb_admin_find_user(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminFindUser.waiting_id)
    await callback.message.edit_text("Введите TG ID пользователя:", reply_markup=admin_back_menu("admin:users"))
    await callback.answer()


@router.message(AdminFindUser.waiting_id)
async def msg_admin_find_user(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Некорректный TG ID.", reply_markup=admin_back_menu("admin:users"))
        return

    tg_id = int(message.text.strip())
    async with async_session() as session:
        user = await get_user_by_tg_id(session, tg_id)

    if user is None:
        await message.answer("Пользователь не найден.", reply_markup=admin_back_menu("admin:users"))
        return

    await message.answer(_user_card_text(user), reply_markup=admin_user_card_menu(user.tg_id, user.is_blocked))


@router.callback_query(F.data.startswith("admin:user:message:"))
async def cb_admin_user_message(callback: CallbackQuery, state: FSMContext) -> None:
    tg_id = int(callback.data.split(":")[3])
    await state.set_state(AdminMessageUser.waiting_text)
    await state.update_data(tg_id=tg_id)
    await callback.message.edit_text(f"Введите сообщение для пользователя {tg_id}:", reply_markup=admin_back_menu("admin:users"))
    await callback.answer()


@router.message(AdminMessageUser.waiting_text)
async def msg_admin_user_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    tg_id = data.get("tg_id")
    await state.clear()
    try:
        await message.bot.send_message(tg_id, f"Сообщение от поддержки МАМОНТ ВПН:\n\n{message.text}")
        await message.answer("Сообщение отправлено.", reply_markup=admin_back_menu("admin:users"))
    except Exception as exc:
        await message.answer(f"Не удалось отправить сообщение: {exc}", reply_markup=admin_back_menu("admin:users"))


@router.callback_query(F.data.startswith("admin:user:toggleblock:"))
async def cb_toggle_block(callback: CallbackQuery) -> None:
    tg_id = int(callback.data.split(":")[3])
    async with async_session() as session:
        user = await get_user_by_tg_id(session, tg_id)
        if user is None:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        user.is_blocked = not user.is_blocked
        await session.commit()
        await session.refresh(user)

    await callback.message.edit_text(_user_card_text(user), reply_markup=admin_user_card_menu(user.tg_id, user.is_blocked))
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin:user:balance:"))
async def cb_balance_start(callback: CallbackQuery, state: FSMContext) -> None:
    tg_id = int(callback.data.split(":")[3])
    await state.set_state(AdminBalance.waiting_amount)
    await state.update_data(tg_id=tg_id)
    await callback.message.edit_text(
        "Введите сумму изменения баланса (например, 100 или -50):",
        reply_markup=admin_back_menu("admin:users"),
    )
    await callback.answer()


@router.message(AdminBalance.waiting_amount)
async def msg_balance_amount(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    tg_id = data.get("tg_id")
    await state.clear()

    try:
        amount = Decimal(message.text.strip().replace(",", "."))
    except Exception:
        await message.answer("Некорректная сумма.", reply_markup=admin_back_menu("admin:users"))
        return

    async with async_session() as session:
        user = await get_user_by_tg_id(session, tg_id)
        if user is None:
            await message.answer("Пользователь не найден.", reply_markup=admin_back_menu("admin:users"))
            return
        user.balance = Decimal(str(user.balance)) + amount
        await session.commit()
        await session.refresh(user)

    await message.answer(_user_card_text(user), reply_markup=admin_user_card_menu(user.tg_id, user.is_blocked))
