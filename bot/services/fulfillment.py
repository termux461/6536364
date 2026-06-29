from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import PLANS
from bot.models.server import Server
from bot.models.subscription import Subscription
from bot.models.user import User
from bot.services.node_manager import node_manager
from bot.services.referral import accrue_referral_bonus
from bot.utils.crypto import encrypt


class FulfillmentError(Exception):
    pass


async def fulfill_purchase(session: AsyncSession, user: User, plan_key: str, server: Server) -> Subscription:
    plan = PLANS[plan_key]
    try:
        peer = await node_manager.create_peer(server, name=f"user{user.tg_id}_{int(datetime.utcnow().timestamp())}")
    except Exception as exc:
        raise FulfillmentError(f"Сервер временно недоступен: {exc}") from exc

    subscription = Subscription(
        user_id=user.id,
        plan=plan_key,
        protocol=server.protocol,
        server_id=server.id,
        peer_id=peer.peer_id,
        peer_private_key_enc=encrypt(peer.private_key) if peer.private_key else "",
        peer_ip=peer.address.split("/")[0] if peer.address else "",
        expires_at=datetime.utcnow() + timedelta(days=plan["days"]),
        active=True,
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(subscription)

    await accrue_referral_bonus(session, user, Decimal(str(plan["price"])))
    return subscription


async def fulfill_topup(session: AsyncSession, user: User, amount: Decimal) -> None:
    user.balance = Decimal(str(user.balance)) + amount
    await session.commit()
    await accrue_referral_bonus(session, user, amount)
