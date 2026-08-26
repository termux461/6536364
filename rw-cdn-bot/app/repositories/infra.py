from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DNSRecord, OriginServer, RemnawaveInstance, RemnawaveResource, YandexProject


class InfraRepository:
    """One-row-per-order accessors for the infrastructure tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def origin(self, order_id: int) -> OriginServer | None:
        return await self.session.scalar(select(OriginServer).where(OriginServer.order_id == order_id))

    async def origin_or_create(self, order_id: int) -> OriginServer:
        row = await self.origin(order_id)
        if row is None:
            row = OriginServer(order_id=order_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def remnawave(self, order_id: int) -> RemnawaveInstance | None:
        return await self.session.scalar(
            select(RemnawaveInstance).where(RemnawaveInstance.order_id == order_id)
        )

    async def remnawave_or_create(self, order_id: int) -> RemnawaveInstance:
        row = await self.remnawave(order_id)
        if row is None:
            row = RemnawaveInstance(order_id=order_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def resources(self, order_id: int) -> RemnawaveResource | None:
        return await self.session.scalar(
            select(RemnawaveResource).where(RemnawaveResource.order_id == order_id)
        )

    async def resources_or_create(self, order_id: int) -> RemnawaveResource:
        row = await self.resources(order_id)
        if row is None:
            row = RemnawaveResource(order_id=order_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def yandex(self, order_id: int) -> YandexProject | None:
        return await self.session.scalar(select(YandexProject).where(YandexProject.order_id == order_id))

    async def yandex_or_create(self, order_id: int) -> YandexProject:
        row = await self.yandex(order_id)
        if row is None:
            row = YandexProject(order_id=order_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def dns_records(self, order_id: int) -> list[DNSRecord]:
        result = await self.session.scalars(
            select(DNSRecord).where(DNSRecord.order_id == order_id).order_by(DNSRecord.id)
        )
        return list(result)

    async def upsert_dns_record(
        self,
        *,
        order_id: int,
        provider: str,
        record_type: str,
        name: str,
        value: str,
        external_id: str | None,
        status: str,
    ) -> DNSRecord:
        row = await self.session.scalar(
            select(DNSRecord).where(
                DNSRecord.order_id == order_id,
                DNSRecord.name == name,
                DNSRecord.record_type == record_type,
            )
        )
        if row is None:
            row = DNSRecord(order_id=order_id, name=name, record_type=record_type)
            self.session.add(row)
        row.provider = provider
        row.value = value
        row.external_id = external_id
        row.status = status
        await self.session.flush()
        return row
