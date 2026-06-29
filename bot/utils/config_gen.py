import io

import qrcode
from aiogram.types import BufferedInputFile

from bot.models.server import Server
from bot.models.subscription import Subscription
from bot.utils.crypto import decrypt


def build_config_text(subscription: Subscription, server: Server) -> str:
    private_key = decrypt(subscription.peer_private_key_enc) if subscription.peer_private_key_enc else ""
    return (
        "[Interface]\n"
        f"PrivateKey = {private_key}\n"
        f"Address = {subscription.peer_ip}/32\n"
        "DNS = 1.1.1.1, 8.8.8.8\n\n"
        "[Peer]\n"
        f"PublicKey = {server.public_key}\n"
        f"Endpoint = {server.endpoint}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        "PersistentKeepalive = 25\n"
    )


def build_config_file(subscription: Subscription, server: Server) -> BufferedInputFile:
    text = build_config_text(subscription, server)
    filename = f"mammot-vpn-{subscription.id}.conf"
    return BufferedInputFile(text.encode("utf-8"), filename=filename)


def build_config_qr(subscription: Subscription, server: Server) -> BufferedInputFile:
    text = build_config_text(subscription, server)
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return BufferedInputFile(buf.read(), filename=f"mammot-vpn-{subscription.id}.png")
