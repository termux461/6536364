"""Renders the single progress message that gets edited in place."""
from __future__ import annotations

from app.models.enums import StepStatus
from app.services.deployment.steps import PROGRESS_STEPS, STEP_TITLES

ICONS = {
    StepStatus.SUCCESS: "✅",
    StepStatus.STARTED: "🔄",
    StepStatus.RETRY: "🔁",
    StepStatus.WAITING: "⏸",
    StepStatus.FAILED: "❌",
    StepStatus.PENDING: "⏳",
    StepStatus.SKIPPED: "➖",
}


def render(order_id: int, statuses: dict[str, str]) -> str:
    lines = ["🚀 <b>Автоматическая настройка</b>", f"Заказ №{order_id}", ""]
    for index, step in enumerate(PROGRESS_STEPS, start=1):
        status = statuses.get(step, StepStatus.PENDING)
        icon = ICONS.get(StepStatus(status), "⏳")
        lines.append(f"{icon} {index}. {STEP_TITLES.get(step, step)}")
    return "\n".join(lines)


def render_success(
    *, order_id: int, origin_domain: str, cdn_domain: str, xhttp_url: str, health_passed: bool
) -> str:
    return (
        "🎉 <b>Настройка успешно завершена!</b>\n\n"
        f"📦 Заказ:\n#{order_id}\n\n"
        f"🖥 Origin Server:\n{origin_domain}\n\n"
        f"☁️ CDN:\n{cdn_domain}\n\n"
        "📡 Remnawave:\n✅ Connected\n\n"
        "🔐 SSL:\n✅ Active\n\n"
        "🌐 Yandex CDN:\n✅ Active\n\n"
        f"🔗 XHTTP:\n{xhttp_url}\n\n"
        f"🧪 Health Check:\n{'✅ Passed' if health_passed else '⚠️ С замечаниями'}"
    )


def render_failure(*, order_id: int, step: str, message: str) -> str:
    return (
        "❌ <b>Настройка остановлена</b>\n\n"
        f"Заказ: #{order_id}\n"
        f"Этап: {STEP_TITLES.get(step, step)}\n\n"
        f"Ошибка:\n<code>{message}</code>\n\n"
        "Состояние сохранено — настройку можно продолжить с этого места."
    )
