import asyncio
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.db.base import async_session
from bot.keyboards.admin import admin_back_menu, admin_broadcast_confirm_menu, admin_broadcast_filters_menu
from bot.models.subscription import Subscription
from bot.models.user import User
from bot.utils.helpers import admin_filter
from bot.utils.states import AdminBroadcast

router = Router(name="admin_broadcast")
router.message.filter(admin_filter)
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBroadcast.waiting_filter)
    await callback.message.edit_text("Выберите аудиторию рассылки:", reply_markup=admin_broadcast_filters_menu())
    await callback.answer()


@router.callback_query(AdminBroadcast.waiting_filter, F.data.startswith("admin:broadcast:filter:"))
async def cb_broadcast_filter(callback: CallbackQuery, state: FSMContext) -> None:
    audience = callback.data.split(":")[3]
    await state.update_data(audience=audience)
    await state.set_state(AdminBroadcast.waiting_content)
    await callback.message.edit_text(
        "Отправьте текст рассылки (можно с фото/видео — приложите медиа с подписью):",
        reply_markup=admin_back_menu(),
    )
    await callback.answer()


@router.message(AdminBroadcast.waiting_content)
async def msg_broadcast_content(message: Message, state: FSMContext) -> None:
    content: dict = {"text": message.html_text or message.caption or ""}
    if message.photo:
        content["photo"] = message.photo[-1].file_id
    elif message.video:
        content["video"] = message.video.file_id

    await state.update_data(content=content)
    await state.set_state(AdminBroadcast.confirm)

    if message.photo:
        await message.answer_photo(content["photo"], caption=content["text"])
    elif message.video:
        await message.answer_video(content["video"], caption=content["text"])
    else:
        await message.answer(content["text"])

    await message.answer("Отправить эту рассылку?", reply_markup=admin_broadcast_confirm_menu())


async def _get_audience_tg_ids(audience: str) -> list[int]:
    async with async_session() as session:
        if audience == "active":
            result = await session.execute(
                select(User.tg_id)
                .join(Subscription, Subscription.user_id == User.id)
                .where(User.is_blocked.is_(False), Subscription.active.is_(True), Subscription.expires_at > datetime.utcnow())
                .distinct()
            )
        elif audience == "expired":
            result = await session.execute(
                select(User.tg_id)
                .join(Subscription, Subscription.user_id == User.id)
                .where(User.is_blocked.is_(False), (Subscription.active.is_(False)) | (Subscription.expires_at <= datetime.utcnow()))
                .distinct()
            )
        else:
            result = await session.execute(select(User.tg_id).where(User.is_blocked.is_(False)))
        return [row[0] for row in result.all()]


@router.callback_query(F.data == "admin:broadcast:send")
async def cb_broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    content = data.get("content")
    audience = data.get("audience", "all")
    await state.clear()

    if not content:
        await callback.answer("Контент рассылки не найден", show_alert=True)
        return

    tg_ids = await _get_audience_tg_ids(audience)
    await callback.message.edit_text(f"Рассылка запущена для {len(tg_ids)} пользователей...")

    sent = 0
    for i, tg_id in enumerate(tg_ids, start=1):
        try:
            if content.get("photo"):
                await callback.bot.send_photo(tg_id, content["photo"], caption=content["text"])
            elif content.get("video"):
                await callback.bot.send_video(tg_id, content["video"], caption=content["text"])
            else:
                await callback.bot.send_message(tg_id, content["text"])
            sent += 1
        except Exception:
            pass
        if i % 25 == 0:
            await asyncio.sleep(0.05)

    await callback.message.answer(f"Рассылка завершена. Отправлено: {sent}/{len(tg_ids)}", reply_markup=admin_back_menu())
    await callback.answer()
