from aiogram.fsm.state import State, StatesGroup


class BuyVPN(StatesGroup):
    choosing_plan = State()
    choosing_server = State()
    confirm = State()


class Support(StatesGroup):
    waiting_message = State()


class AdminBroadcast(StatesGroup):
    waiting_filter = State()
    waiting_content = State()
    confirm = State()


class AdminAddServer(StatesGroup):
    name = State()
    country = State()
    flag = State()
    protocol = State()
    ssh_host = State()
    ssh_port = State()
    ssh_user = State()
    ssh_password = State()
    wg_port = State()
    api_password = State()
    confirm = State()
    installing = State()


class AdminFindUser(StatesGroup):
    waiting_id = State()


class AdminBalance(StatesGroup):
    waiting_amount = State()


class AdminMessageUser(StatesGroup):
    waiting_text = State()


class AdminIssueKey(StatesGroup):
    waiting_tg_id = State()
    choosing_plan = State()
    choosing_server = State()
    confirm = State()


class AdminPromo(StatesGroup):
    code = State()
    discount = State()
    limit = State()
    expires = State()


class AdminAdmins(StatesGroup):
    waiting_tg_id = State()


class AdminRestore(StatesGroup):
    waiting_file = State()
