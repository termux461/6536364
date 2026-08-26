from __future__ import annotations

import pytest

from app.core.exceptions import PermanentError, TransientError
from app.services.deployment.node_installer import (
    CONTAINER,
    ENV_CURRENT,
    ENV_LEGACY,
    NodeInstaller,
    render_compose,
    render_env_file,
    render_logrotate,
)


class FakeResult:
    def __init__(self, stdout: str = "", exit_code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.exit_code = exit_code

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class FakeSSH:
    """Records what the installer does and replays scripted command output."""

    def __init__(self, responses: dict[str, FakeResult] | None = None) -> None:
        self.responses = responses or {}
        self.commands: list[str] = []
        self.files: dict[str, tuple[str, int]] = {}
        self.state = "running"
        self.logs = ""

    async def execute(self, command: str, *, check: bool = True, timeout=None, quiet: bool = False):
        self.commands.append(command)
        for needle, response in self.responses.items():
            if needle in command:
                return response
        if "docker compose version" in command:
            return FakeResult("Docker Compose version v2.27.0")
        if "State.Status" in command:
            return FakeResult(self.state)
        if ".State.Status" in command or "docker inspect -f '{{.Image}}" in command:
            return FakeResult("sha256:abcdef0123456789 0")
        if "docker inspect" in command:
            return FakeResult("sha256:abcdef0123456789 0")
        if "ss -ltn" in command:
            return FakeResult("1" if self.state == "running" else "0")
        if "docker logs" in command:
            return FakeResult(self.logs)
        return FakeResult("")

    async def write_file(self, path: str, content: str, *, mode: int = 0o644) -> None:
        self.files[path] = (content, mode)

    async def read_file(self, path: str) -> str:
        return self.files.get(path, ("", 0))[0]

    async def file_exists(self, path: str) -> bool:
        return path in self.files


SECRET = "eyJub2RlQ2VydFBlbSI6ICItLS0tLUJFR0lOIn0="


def test_env_layouts_are_the_two_documented_ones():
    current = render_env_file(SECRET, node_port=2222, fmt=ENV_CURRENT)
    assert "NODE_PORT=2222" in current
    assert f"SECRET_KEY={SECRET}" in current

    legacy = render_env_file(SECRET, node_port=2222, fmt=ENV_LEGACY)
    assert "APP_PORT=2222" in legacy
    assert f"SSL_CERT={SECRET}" in legacy


def test_compose_never_contains_the_secret():
    compose = render_compose()
    assert SECRET not in compose
    assert "env_file" in compose
    assert f"container_name: {CONTAINER}" in compose
    assert "network_mode: host" in compose
    assert "restart: always" in compose


def test_logrotate_rotates_node_logs():
    assert "/var/log/remnanode/*.log" in render_logrotate()
    assert "copytruncate" in render_logrotate()


def test_empty_secret_is_rejected_immediately():
    with pytest.raises(PermanentError):
        NodeInstaller(FakeSSH(), secret="   ")


async def test_install_writes_env_600_and_starts_container():
    ssh = FakeSSH()
    result = await NodeInstaller(ssh, secret=SECRET, settle_seconds=0).install()

    assert result.running
    assert result.changed
    assert result.env_format == ENV_CURRENT
    content, mode = ssh.files["/opt/remnanode/.env"]
    assert SECRET in content
    assert mode == 0o600  # the secret is not world-readable
    assert "/opt/remnanode/docker-compose.yml" in ssh.files
    assert "/etc/logrotate.d/remnanode" in ssh.files
    # the secret is never passed on a command line
    assert not any(SECRET in command for command in ssh.commands)


async def test_second_run_with_same_secret_changes_nothing():
    ssh = FakeSSH()
    installer = NodeInstaller(ssh, secret=SECRET, settle_seconds=0)
    await installer.install()
    ssh.commands.clear()

    result = await installer.install()
    assert result.changed is False
    assert not any("docker compose up" in command for command in ssh.commands)


async def test_force_reinstalls_even_when_unchanged():
    ssh = FakeSSH()
    installer = NodeInstaller(ssh, secret=SECRET, settle_seconds=0)
    await installer.install()
    ssh.commands.clear()

    result = await installer.install(force=True)
    assert result.changed is True
    assert any("docker compose up" in command for command in ssh.commands)


async def test_legacy_fallback_when_image_wants_old_variables():
    ssh = FakeSSH()
    ssh.state = "exited"
    ssh.logs = "Error: SSL_CERT is not defined"

    installer = NodeInstaller(ssh, secret=SECRET, settle_seconds=0)

    # after the fallback write the container comes up
    original_write = ssh.write_file

    async def write_and_recover(path, content, *, mode=0o644):
        await original_write(path, content, mode=mode)
        if "SSL_CERT=" in content:
            ssh.state = "running"
            ssh.logs = "started"

    ssh.write_file = write_and_recover  # type: ignore[assignment]

    result = await installer.install()
    assert result.env_format == ENV_LEGACY
    assert result.running
    assert "APP_PORT=2222" in ssh.files["/opt/remnanode/.env"][0]


async def test_bad_secret_is_permanent_not_retried():
    ssh = FakeSSH()
    ssh.state = "exited"
    ssh.logs = "panic: invalid certificate provided"

    with pytest.raises(PermanentError):
        await NodeInstaller(ssh, secret=SECRET, settle_seconds=0).install()


async def test_busy_port_is_permanent():
    ssh = FakeSSH()
    ssh.state = "exited"
    ssh.logs = "listen tcp :2222: bind: address already in use"

    with pytest.raises(PermanentError):
        await NodeInstaller(ssh, secret=SECRET, settle_seconds=0).install()


async def test_unknown_failure_is_transient():
    ssh = FakeSSH()
    ssh.state = "restarting"
    ssh.logs = "connection reset by peer"

    with pytest.raises(TransientError):
        await NodeInstaller(ssh, secret=SECRET, settle_seconds=0).install()


async def test_missing_docker_stops_with_a_clear_message():
    ssh = FakeSSH({"docker compose version": FakeResult("", exit_code=127)})
    with pytest.raises(PermanentError):
        await NodeInstaller(ssh, secret=SECRET, settle_seconds=0).install()


async def test_diagnostics_never_raise_and_hide_nothing_useful():
    ssh = FakeSSH()
    installer = NodeInstaller(ssh, secret=SECRET, settle_seconds=0)
    await installer.install()

    data = await installer.diagnostics()
    assert data["status"] == "running"
    assert data["env_present"] is True
    assert data["env_format"] == ENV_CURRENT
    assert "logs_tail" in data
