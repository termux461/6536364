from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Deployment, DeploymentStep
from app.models.enums import DeploymentStatus, StepStatus


class DeploymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, deployment_id: int) -> Deployment | None:
        return await self.session.get(Deployment, deployment_id)

    async def get_by_order(self, order_id: int) -> Deployment | None:
        return await self.session.scalar(select(Deployment).where(Deployment.order_id == order_id))

    async def get_or_create(self, order_id: int) -> Deployment:
        deployment = await self.get_by_order(order_id)
        if deployment is None:
            deployment = Deployment(order_id=order_id, status=DeploymentStatus.QUEUED, context={})
            self.session.add(deployment)
            await self.session.flush()
        return deployment

    async def ensure_steps(self, deployment: Deployment, step_names: list[str]) -> list[DeploymentStep]:
        existing = {step.step: step for step in await self.steps(deployment.id)}
        created: list[DeploymentStep] = []
        for position, name in enumerate(step_names):
            if name in existing:
                continue
            step = DeploymentStep(
                deployment_id=deployment.id,
                order_id=deployment.order_id,
                step=name,
                position=position,
                status=StepStatus.PENDING,
            )
            self.session.add(step)
            created.append(step)
        if created:
            await self.session.flush()
        return created

    async def steps(self, deployment_id: int) -> list[DeploymentStep]:
        result = await self.session.scalars(
            select(DeploymentStep)
            .where(DeploymentStep.deployment_id == deployment_id)
            .order_by(DeploymentStep.position, DeploymentStep.id)
        )
        return list(result)

    async def get_step(self, deployment_id: int, name: str) -> DeploymentStep | None:
        return await self.session.scalar(
            select(DeploymentStep).where(
                DeploymentStep.deployment_id == deployment_id, DeploymentStep.step == name
            )
        )

    async def start_step(self, step: DeploymentStep) -> None:
        step.status = StepStatus.STARTED
        step.attempt += 1
        step.started_at = datetime.now(UTC)
        step.error = None
        await self.session.flush()

    async def finish_step(
        self, step: DeploymentStep, status: StepStatus, error: str | None = None
    ) -> None:
        step.status = status
        step.error = error
        step.finished_at = datetime.now(UTC)
        await self.session.flush()

    async def set_status(
        self,
        deployment: Deployment,
        status: DeploymentStatus,
        *,
        current_step: str | None = None,
        error: str | None = None,
    ) -> None:
        deployment.status = status
        if current_step is not None:
            deployment.current_step = current_step
        if error is not None:
            deployment.last_error = error
        if status == DeploymentStatus.RUNNING and deployment.started_at is None:
            deployment.started_at = datetime.now(UTC)
        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED, DeploymentStatus.STOPPED):
            deployment.finished_at = datetime.now(UTC)
        await self.session.flush()

    async def update_context(self, deployment: Deployment, patch: dict) -> None:
        context = dict(deployment.context or {})
        context.update(patch)
        deployment.context = context
        await self.session.flush()

    async def counters(self, since: datetime | None = None) -> dict[str, int]:
        query = select(Deployment.status, func.count(Deployment.id))
        if since is not None:
            query = query.where(Deployment.created_at >= since)
        rows = (await self.session.execute(query.group_by(Deployment.status))).all()
        return {str(status): int(count) for status, count in rows}
