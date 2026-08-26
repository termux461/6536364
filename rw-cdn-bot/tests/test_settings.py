"""Environment parsing.

These exist because list-typed settings used to be JSON-decoded by pydantic-settings inside
the env source — before any validator could split a comma-separated value — which made a
perfectly ordinary `ADMIN_IDS=111,222` crash the process at startup.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from app.config.settings import Settings


def _settings(**env: str) -> Settings:
    """Build Settings from exactly the given environment and nothing else.

    The variables have to go through `os.environ`, not through keyword arguments: the whole
    point of these tests is the env source, which is where list-typed values used to be
    JSON-decoded before any validator could see them. conftest exports its own BOT_TOKEN,
    ADMIN_IDS and friends for the rest of the suite, so the environment is replaced rather
    than extended — otherwise "absent" can never be tested.
    """
    base = {
        "BOT_TOKEN": "1:x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@postgres/db",
        "REDIS_URL": "redis://redis:6379/0",
        "SECRET_ENCRYPTION_KEY": "key",
    }
    base.update(env)
    clean = {k: v for k, v in os.environ.items() if not _is_setting(k)}
    clean.update(base)
    with patch.dict(os.environ, clean, clear=True):
        return Settings(_env_file=None)


def _is_setting(name: str) -> bool:
    return name.lower() in Settings.model_fields or any(
        (field.validation_alias or "") == name.lower() for field in Settings.model_fields.values()
    )


def test_comma_separated_admin_ids():
    assert _settings(ADMIN_IDS="111,222").admin_ids == [111, 222]


def test_admin_ids_tolerates_spaces_and_blanks():
    assert _settings(ADMIN_IDS=" 111 , , 222 ").admin_ids == [111, 222]


def test_single_admin_id():
    assert _settings(ADMIN_IDS="111").admin_ids == [111]


def test_admin_ids_absent_means_nobody():
    settings = _settings()
    assert settings.admin_ids == []
    assert settings.is_admin(111) is False


def test_admin_ids_json_array_also_works():
    assert _settings(ADMIN_IDS='["111", "222"]').admin_ids == [111, 222]


def test_non_numeric_admin_id_is_skipped_not_fatal():
    assert _settings(ADMIN_IDS="111,oops,222").admin_ids == [111, 222]


def test_allowed_ips_are_cidrs_not_json():
    settings = _settings(YOOKASSA_ALLOWED_IPS="185.71.76.0/27,185.71.77.0/27")
    assert settings.yookassa_allowed_ips == ["185.71.76.0/27", "185.71.77.0/27"]


def test_allowed_ips_default_empty():
    assert _settings().yookassa_allowed_ips == []


def test_retry_delays_default():
    assert _settings().deploy_retry_delays == [5, 15, 30]


def test_retry_delays_override():
    assert _settings(DEPLOY_RETRY_DELAYS="1,2,3").deploy_retry_delays == [1, 2, 3]


def test_retry_delays_fall_back_when_unusable():
    assert _settings(DEPLOY_RETRY_DELAYS="junk").deploy_retry_delays == [5, 15, 30]


def test_is_admin():
    settings = _settings(ADMIN_IDS="111,222")
    assert settings.is_admin(222) is True
    assert settings.is_admin(333) is False


def test_matching_domains_produce_no_warning():
    settings = _settings(
        WEBHOOK_BASE_URL="https://bot.example.com", BOT_PUBLIC_DOMAIN="bot.example.com"
    )
    assert settings.webhook_domain_mismatch() is None


def test_mismatched_domains_are_reported():
    """Silent mismatch = payments look fine and callbacks never arrive. Catch it at startup."""
    settings = _settings(
        WEBHOOK_BASE_URL="https://pay.example.com", BOT_PUBLIC_DOMAIN="bot.example.com"
    )
    warning = settings.webhook_domain_mismatch()
    assert warning is not None
    assert "pay.example.com" in warning and "bot.example.com" in warning


def test_no_warning_when_caddy_is_not_used():
    assert _settings(WEBHOOK_BASE_URL="https://bot.example.com").webhook_domain_mismatch() is None


def test_webhook_urls_are_built_from_the_base():
    settings = _settings(WEBHOOK_BASE_URL="https://bot.example.com/")
    assert settings.platega_webhook_url == "https://bot.example.com/webhooks/platega"
    assert settings.yookassa_webhook_url == "https://bot.example.com/webhooks/yookassa"
