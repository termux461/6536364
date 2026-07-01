import hashlib
import hmac
import json
import time
import urllib.parse


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict | None:
    """Validate Telegram WebApp initData per https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Returns the parsed `user` dict on success, None on failure.
    """
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    auth_date = parsed.get("auth_date")
    if auth_date and time.time() - int(auth_date) > max_age_seconds:
        return None

    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    return json.loads(user_raw)
