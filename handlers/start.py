from datetime import datetime
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from keyboards.inline import main_menu, back_kb
from services.database import Database
from config import Config

router = Router()

PROTO_LABELS = {
    "wg":  ("⚡", "WireGuard"),
    "awg": ("🛡", "AmneziaWG 2.0"),
}


async def build_main_text(user_id: int, db: Database) -> tuple[str, int]:
    user = await db.get_user(user_id)
    balance = user["balance"] if user else 0

    # Активные подписки по обоим протоколам
    sub_wg  = await db.get_active_subscription_by_proto(user_id, "wg")
    sub_awg = await db.get_active_subscription_by_proto(user_id, "awg")

    lines = ["📋 <b>Подписки:</b>"]
    for proto, sub in [("wg", sub_wg), ("awg", sub_awg)]:
        emoji, name = PROTO_LABELS[proto]
        if sub:
            exp = datetime.fromisoformat(sub["expires_at"])
            days = max((exp - datetime.utcnow()).days, 0)
            lines.append(f"┗ 🟢 {emoji} {name} — до {exp.strftime('%d.%m.%Y')} ({days} дн.)")
        else:
            lines.append(f"┗ ⚫ {emoji} {name} — нет подписки")

    lines.append("\nВыберите действие:")
    return "\n".join(lines), balance


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, config: Config):
    user_id = message.from_user.id

    # Реферальная система
    args = message.text.split()
    ref_by = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            ref_by = int(args[1][3:])
            if ref_by == user_id:
                ref_by = None
        except ValueError:
            pass

    is_new = await db.is_new_user(user_id)
    await db.upsert_user(user_id, message.from_user.username, ref_by)

    if is_new and ref_by:
        referer = await db.get_user(ref_by)
        if referer:
            await db.change_balance(ref_by, config.REFERRAL_BONUS, f"реферал {user_id}")
            try:
                await message.bot.send_message(
                    ref_by,
                    f"🎉 Новый пользователь по вашей реф. ссылке!\n"
                    f"Начислено <b>{config.REFERRAL_BONUS}₽</b> на баланс.",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    text, balance = await build_main_text(user_id, db)
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu(balance))


@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, db: Database):
    text, balance = await build_main_text(call.from_user.id, db)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=main_menu(balance))
    await call.answer()


@router.callback_query(F.data == "info")
async def cb_info(call: CallbackQuery):
    await call.message.edit_text(
        "ℹ️ <b>О сервисе</b>\n\n"
        "Продаём VPN-конфигурации двух типов:\n\n"
        "⚡ <b>WireGuard</b> — быстрый и лёгкий VPN\n"
        "   Клиент: WireGuard (App Store / Google Play)\n\n"
        "🛡 <b>AmneziaWG 2.0</b> — WireGuard с обфускацией\n"
        "   Не блокируется ТСПУ и DPI провайдеров\n"
        "   Клиент: <a href='https://amnezia.org/download'>AmneziaVPN</a>\n\n"
        "⚡ Скорость до 1 Гбит/с\n"
        "📱 iOS, Android, Windows, macOS, Linux",
        parse_mode="HTML",
        reply_markup=back_kb("main")
    )
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    await call.message.edit_text(
        "🔧 <b>Техподдержка</b>\n\n"
        "По всем вопросам: @your_support_username",
        parse_mode="HTML",
        reply_markup=back_kb("main")
    )
    await call.answer()
