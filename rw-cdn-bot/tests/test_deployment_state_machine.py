
from app.models.enums import DeploymentStatus, StepStatus
from app.repositories import DeploymentRepository
from app.services.deployment.steps import STEP_ORDER


async def test_steps_are_created_once(session, seeded):
    repo = DeploymentRepository(session)
    deployment = await repo.get_or_create(seeded["order"].id)
    await repo.ensure_steps(deployment, STEP_ORDER)
    await repo.ensure_steps(deployment, STEP_ORDER)  # restart must not duplicate
    steps = await repo.steps(deployment.id)
    assert len(steps) == len(STEP_ORDER)
    assert [step.step for step in steps] == STEP_ORDER


async def test_completed_steps_are_skipped_on_resume(session, seeded):
    repo = DeploymentRepository(session)
    deployment = await repo.get_or_create(seeded["order"].id)
    await repo.ensure_steps(deployment, STEP_ORDER)
    first = await repo.get_step(deployment.id, STEP_ORDER[0])
    await repo.start_step(first)
    await repo.finish_step(first, StepStatus.SUCCESS)

    remaining = [
        step.step for step in await repo.steps(deployment.id) if step.status != StepStatus.SUCCESS
    ]
    assert STEP_ORDER[0] not in remaining
    assert remaining[0] == STEP_ORDER[1]


async def test_waiting_status_is_not_failure(session, seeded):
    repo = DeploymentRepository(session)
    deployment = await repo.get_or_create(seeded["order"].id)
    await repo.set_status(deployment, DeploymentStatus.WAITING_DNS, current_step="verify_dns")
    assert deployment.status == DeploymentStatus.WAITING_DNS
    assert deployment.finished_at is None


def test_no_cascade_steps_exist():
    """The scheme is deliberately cascade-free — nothing foreign may appear in the pipeline."""
    forbidden = ("cascade", "foreign", "geoip", "geosite", "exit")
    assert not [step for step in STEP_ORDER if any(word in step for word in forbidden)]


def test_cookies_are_dropped_only_after_the_last_step_that_can_need_yandex():
    """Cloud DNS runs in configure_dns with the same credentials — purging before it broke
    every order whose zone lives in the folder."""
    import inspect

    from app.services.deployment import steps as S
    from app.services.deployment.service import DeploymentService

    source = inspect.getsource(DeploymentService._step_configure_dns)
    assert "_forget_cookies" in source
    assert "_forget_cookies" not in inspect.getsource(DeploymentService._step_get_yandex_cname)
    assert S.STEP_ORDER.index(S.CONFIGURE_DNS) > S.STEP_ORDER.index(S.GET_YANDEX_CNAME)


async def test_remnawave_api_version_defaults_to_auto(session):
    """A fresh order has no recorded dialect, so the client detects one on connect."""
    from app.repositories import InfraRepository

    row = await InfraRepository(session).remnawave_or_create(order_id=1)
    await session.flush()
    assert row.api_version == "auto"


async def test_a_recorded_api_version_reaches_the_client(session, seeded):
    """Once the panel has answered, the worker stops re-probing on every step."""
    from unittest.mock import MagicMock

    from app.services.deployment.context import DeployContext
    from app.services.remnawave.dialects import ApiVersion

    remnawave = MagicMock()
    remnawave.api_version = "v2"
    remnawave.panel_url = "https://panel.example.com"
    remnawave.api_token_enc = None

    context = DeployContext(
        order=seeded["order"],
        deployment=MagicMock(),
        origin=MagicMock(),
        remnawave=remnawave,
        resources=MagicMock(),
        yandex=MagicMock(),
    )
    assert context.remnawave_api_version == "v2"

    from app.services.remnawave import RemnawaveClient

    client = RemnawaveClient("https://panel.example.com", "t", api_version=context.remnawave_api_version)
    assert client.version is ApiVersion.V2


def test_the_env_default_applies_only_while_the_order_says_auto(monkeypatch):
    """A recorded dialect always wins over the environment fallback."""
    from unittest.mock import MagicMock

    from app.config import get_settings
    from app.services.deployment.context import DeployContext

    settings = get_settings()
    monkeypatch.setattr(settings, "remnawave_api_version", "v2", raising=False)

    def context_with(recorded: str) -> DeployContext:
        remnawave = MagicMock()
        remnawave.api_version = recorded
        return DeployContext(
            order=MagicMock(), deployment=MagicMock(), origin=MagicMock(),
            remnawave=remnawave, resources=MagicMock(), yandex=MagicMock(),
        )

    assert context_with("auto").remnawave_api_version == "v2"   # env fallback
    assert context_with("v3").remnawave_api_version == "v3"     # recorded wins
