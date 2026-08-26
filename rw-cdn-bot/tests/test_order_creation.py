
from app.models.enums import OrderStatus
from app.repositories import OrderRepository


async def test_order_freezes_price(session, seeded):
    order = seeded["order"]
    assert order.amount == 150000
    assert order.status == OrderStatus.CREATED
    assert order.amount_display.endswith("RUB")


async def test_active_order_detection(session, seeded):
    repo = OrderRepository(session)
    order = seeded["order"]
    assert await repo.has_active(order.user_id) is False
    await repo.set_status(order, OrderStatus.DEPLOYING)
    assert await repo.has_active(order.user_id) is True


async def test_paid_at_set_once(session, seeded):
    repo = OrderRepository(session)
    order = seeded["order"]
    await repo.set_status(order, OrderStatus.PAID)
    first = order.paid_at
    await repo.set_status(order, OrderStatus.PAID)
    assert order.paid_at == first
