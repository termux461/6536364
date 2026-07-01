from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    choosing_tariff = State()
    entering_promo = State()
    choosing_payment = State()
    waiting_payment = State()


class WithdrawFlow(StatesGroup):
    entering_amount = State()


class AdminHostFlow(StatesGroup):
    entering_name = State()
    entering_url = State()
    entering_token = State()


class AdminTariffFlow(StatesGroup):
    choosing_host = State()
    entering_name = State()
    entering_price = State()
    entering_duration = State()
    entering_traffic = State()


class AdminBroadcastFlow(StatesGroup):
    entering_text = State()
    confirming = State()


class AdminTicketReplyFlow(StatesGroup):
    entering_text = State()
