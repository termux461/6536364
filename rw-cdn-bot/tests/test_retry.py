
import pytest

from app.core.exceptions import PermanentError, TransientError
from app.core.retry import poll_until, retry_async


async def test_retries_transient_then_succeeds():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("not yet")
        return "ok"

    assert await retry_async(flaky, attempts=3, delays=[0, 0, 0]) == "ok"
    assert calls["n"] == 3


async def test_gives_up_after_attempts():
    async def always_fails():
        raise TransientError("nope")

    with pytest.raises(TransientError):
        await retry_async(always_fails, attempts=2, delays=[0, 0])


async def test_permanent_error_is_not_retried():
    calls = {"n": 0}

    async def hard_fail():
        calls["n"] += 1
        raise PermanentError("bad config")

    with pytest.raises(PermanentError):
        await retry_async(hard_fail, attempts=3, delays=[0, 0, 0])
    assert calls["n"] == 1


async def test_poll_until_times_out():
    async def never():
        return False

    assert await poll_until(never, timeout=1, interval=1, label="test") is False
