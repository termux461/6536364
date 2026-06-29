from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import t


def referral_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(locale, "referral.withdraw_button"), callback_data="withdraw_request")]
    ])
