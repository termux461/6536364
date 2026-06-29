from aiogram.fsm.state import State, StatesGroup


class BuyVPN(StatesGroup):
    choosing_plan = State()
    choosing_server = State()
    confirm = State()


class Support(StatesGroup):
    waiting_message = State()


class AdminBroadcast(StatesGroup):
    waiting_text = State()
    confirm = State()


class AdminAddServer(StatesGroup):
    name = State()
    country = State()
    flag = State()
    protocol = State()
    endpoint = State()


class AdminFindUser(StatesGroup):
    waiting_id = State()


class AdminBalance(StatesGroup):
    waiting_amount = State()
