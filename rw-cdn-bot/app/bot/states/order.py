from aiogram.fsm.state import State, StatesGroup


class CollectData(StatesGroup):
    panel_url = State()
    panel_token = State()
    origin_ip = State()
    ssh_port = State()
    ssh_user = State()
    ssh_auth = State()
    ssh_key = State()
    ssh_password = State()
    origin_domain = State()
    cdn_domain = State()
    email = State()
    yandex_login = State()
    yandex_cloud_pick = State()
    yandex_folder_pick = State()
    yandex_cloud_id = State()
    yandex_folder_id = State()
    yandex_auth_mode = State()
    yandex_key = State()
    yandex_oauth = State()
    yandex_cookies = State()
    reauth_value = State()
    dns_mode = State()
    cloudflare_token = State()


class AdminStates(StatesGroup):
    price = State()
    tariff_name = State()
    tariff_description = State()
    maintenance_text = State()
    broadcast_text = State()
    message_user = State()
    node_secret = State()
