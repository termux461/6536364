from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.filters import IsAdmin
from app.bot.states.order import AdminStates
from app.repositories import AuditRepository, OrderRepository, UserRepository

router = Router(name="admin_users")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PAGE = 8


def _nav(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"adm:users:{max(page - 1, 0)}"),
                InlineKeyboardButton(text="➡️", callback_data=f"adm:users:{page + 1}"),
            ],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
        ]
    )


@router.callback_query(F.data.startswith("adm:users:"))
async def list_users(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[2])
    users = await UserRepository(session).list_page(page * PAGE, PAGE)
    if not users:
        await callback.message.edit_text("Пользователей нет.", reply_markup=_nav(page))
        await callback.answer()
        return
    lines = [
        f"<code>{user.telegram_id}</code> {user.display_name}"
        f"{' 🚫' if user.is_blocked else ''} · {user.created_at:%d.%m.%Y}"
        for user in users
    ]
    await callback.message.edit_text(
        "👥 <b>Пользователи</b>\n\n" + "\n".join(lines) + "\n\nКарточка: /user &lt;telegram_id&gt;",
        reply_markup=_nav(page),
    )
    await callback.answer()


@router.message(F.text.regexp(r"^/user\s+(\d+)$").as_("match"))
async def user_card(message: Message, session: AsyncSession, match) -> None:
    telegram_id = int(match.group(1))
    users = UserRepository(session)
    user = await users.get_by_telegram_id(telegram_id)
    if user is None:
        await message.answer("Пользователь не найден.")
        return

    stats = await users.stats(user.id)
    orders = await OrderRepository(session).list_for_user(user.id, limit=5)
    last = orders[0] if orders else None
    text = (
        f"👤 <b>{user.display_name}</b>\n"
        f"Telegram ID: <code>{user.telegram_id}</code>\n"
        f"Username: {('@' + user.username) if user.username else '—'}\n"
        f"Регистрация: {user.created_at:%d.%m.%Y}\n"
        f"Заказов: {stats['orders']}\n"
        f"Потрачено: {stats['spent'] // 100} ₽\n"
        f"Последний заказ: {f'#{last.id} ({last.status})' if last else '—'}\n"
        f"Статус: {'🚫 заблокирован' if user.is_blocked else '✅ активен'}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Разблокировать" if user.is_blocked else "🚫 Заблокировать",
                    callback_data=f"adm:usr:block:{user.telegram_id}",
                )
            ],
            [InlineKeyboardButton(text="📨 Написать", callback_data=f"adm:usr:msg:{user.telegram_id}")],
        ]
    )
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("adm:usr:block:"))
async def toggle_block(callback: CallbackQuery, session: AsyncSession) -> None:
    telegram_id = int(callback.data.split(":")[3])
    users = UserRepository(session)
    user = await users.get_by_telegram_id(telegram_id)
    if user is None:
        await callback.answer("Не найден", show_alert=True)
        return
    await users.set_blocked(telegram_id, not user.is_blocked, "admin")
    await AuditRepository(session).log(
        "user.block_toggled", admin_id=callback.from_user.id, user_id=telegram_id
    )
    await callback.answer("Готово", show_alert=True)


@router.callback_query(F.data.startswith("adm:usr:msg:"))
async def ask_message(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(target=int(callback.data.split(":")[3]))
    await state.set_state(AdminStates.message_user)
    await callback.message.answer("Введите текст сообщения пользователю:")
    await callback.answer()


@router.message(AdminStates.message_user)
async def send_message(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    await state.clear()
    try:
        await message.bot.send_message(int(data["target"]), message.text or "")
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не доставлено: {exc}")
        return
    await AuditRepository(session).log(
        "user.message_sent", admin_id=message.from_user.id, user_id=int(data["target"])
    )
    await message.answer("✅ Отправлено.")
