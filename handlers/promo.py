from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from keyboards.inline import back_kb, main_menu
from services.database import Database
from config import Config

router = Router()


class PromoState(StatesGroup):
    waiting_code = State()


@router.callback_query(F.data == "promo")
async def promo_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(PromoState.waiting_code)
    await call.message.edit_text(
        "🎟 <b>Активация промокода</b>\n\n"
        "Введите промокод:",
        parse_mode="HTML",
        reply_markup=back_kb("main")
    )
    await call.answer()


@router.message(PromoState.waiting_code)
async def process_promo(message: Message, state: FSMContext, db: Database):
    code = message.text.strip().upper()
    user_id = message.from_user.id

    promo = await db.get_promo(code)
    if not promo:
        await message.answer(
            "❌ Промокод не найден или уже использован.",
            reply_markup=back_kb("main")
        )
        return

    if await db.has_used_promo(user_id, promo["id"]):
        await message.answer(
            "❌ Вы уже использовали этот промокод.",
            reply_markup=back_kb("main")
        )
        return

    await db.use_promo(user_id, promo["id"])
    await db.change_balance(user_id, promo["bonus"], f"промокод {code}")

    user = await db.get_user(user_id)
    await state.clear()
    await message.answer(
        f"✅ Промокод активирован!\n"
        f"💰 Начислено <b>{promo['bonus']}₽</b> на баланс.\n"
        f"Текущий баланс: <b>{user['balance']}₽</b>",
        parse_mode="HTML",
        reply_markup=main_menu(user["balance"])
    )


@router.callback_query(F.data == "referral")
async def referral_info(call: CallbackQuery, db: Database, config: Config):
    user_id = call.from_user.id
    count = await db.get_referral_count(user_id)
    link = f"https://t.me/{config.BOT_USERNAME}?start=ref{user_id}"

    await call.message.edit_text(
        f"🤝 <b>Партнёрская программа</b>\n\n"
        f"За каждого приглашённого пользователя — "
        f"<b>{config.REFERRAL_BONUS}₽</b> на ваш баланс.\n\n"
        f"👥 Приглашено: <b>{count}</b>\n\n"
        f"🔗 Ваша ссылка:\n<code>{link}</code>",
        parse_mode="HTML",
        reply_markup=back_kb("main")
    )
    await call.answer()
