import hashlib
import hmac
import urllib.parse
from typing import Optional


class PlategaService:
    BASE_URL = "https://platega.ru/pay"

    def __init__(self, shop_id: str, secret: str):
        self.shop_id = shop_id
        self.secret = secret

    def _sign(self, order_id: str, amount: int) -> str:
        raw = f"{self.shop_id}:{amount}:{order_id}:{self.secret}"
        return hashlib.md5(raw.encode()).hexdigest()

    def create_url(self, order_id: str, amount: int, description: str, user_id: int) -> str:
        params = {
            "m":    self.shop_id,
            "oa":   str(amount),
            "o":    order_id,
            "desc": description,
            "s":    self._sign(order_id, amount),
            "us":   str(user_id),
        }
        return f"{self.BASE_URL}?" + urllib.parse.urlencode(params)

    def verify(self, data: dict) -> bool:
        try:
            sign = data.get("s", "")
            order_id = data.get("o", "")
            amount = int(float(data.get("oa", 0)))
            return hmac.compare_digest(sign.lower(), self._sign(order_id, amount).lower())
        except Exception:
            return False

    @staticmethod
    def user_id_from(data: dict) -> Optional[int]:
        try:
            return int(data.get("us", 0)) or None
        except (ValueError, TypeError):
            return None
