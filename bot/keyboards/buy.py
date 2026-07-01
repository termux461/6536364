from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import PaymentMethod, Tariff


def tariffs_keyboard(tariffs: list[Tariff]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{tr.name} — {tr.price} ₽ / {tr.duration_days} дн.", callback_data=f"tariff:{tr.id}")]
        for tr in tariffs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_methods_keyboard(methods: list[PaymentMethod], tariff_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=m.title, callback_data=f"pay:{tariff_id}:{m.code}")]
        for m in methods
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def check_payment_keyboard(payment_id: int, locale: str) -> InlineKeyboardMarkup:
    from bot.i18n import t
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(locale, "buy.check_payment"), callback_data=f"check_pay:{payment_id}")]
    ])
