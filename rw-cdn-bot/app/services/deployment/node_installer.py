"""Remnanode installer.

Installs the Remnawave Node container on the Origin Server and verifies it actually came up.
Everything here is idempotent: a second run over an already-installed server changes nothing
unless the secret, the port or the image differ.

Two env layouts exist in the wild and both are supported:

    current : NODE_PORT + SECRET_KEY
    legacy  : APP_PORT  + SSL_CERT

`current` is written first; if the container refuses to start because the image expects the
old names, the installer rewrites the env in `legacy` format and retries once. Nothing is
guessed beyond those two documented layouts.

The secret never touches a shell command line — env and compose files are written over SFTP.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.exceptions import PermanentError, TransientError
from app.services.remnawave.templates import NODE_PORT

if TYPE_CHECKING:  # keeps this module importable (and testable) without asyncssh
    from app.services.ssh import SSHClient

logger = logging.getLogger(__name__)

INSTALL_DIR = "/opt/remnanode"
LOG_DIR = "/var/log/remnanode"
CONTAINER = "remnanode"
IMAGE = "remnawave/node:latest"

ENV_CURRENT = "current"
ENV_LEGACY = "legacy"

# Substrings that mean "the image wants the old variable names".
LEGACY_HINTS = (
    "SSL_CERT",
    "APP_PORT",
    "is not defined",
    "is required",
    "ssl_cert",
)
# Substrings that mean the secret itself is wrong — retrying will never help.
BAD_SECRET_HINTS = (
    "invalid certificate",
    "failed to parse",
    "jwt malformed",
    "invalid key",
    "unexpected token",
)


def render_env_file(secret: str, *, node_port: int = NODE_PORT, fmt: str = ENV_CURRENT) -> str:
    """The node's `.env`. Two documented layouts, nothing invented."""
    if fmt == ENV_LEGACY:
        return f"APP_PORT={node_port}\nSSL_CERT={secret}\n"
    return f"NODE_PORT={node_port}\nSECRET_KEY={secret}\n"


def render_compose(*, image: str = IMAGE, log_dir: str = LOG_DIR) -> str:
    """docker-compose.yml for the node.

    Variables live in `.env` (mode 600) rather than inline, so the secret is not readable from
    the compose file and is not echoed by `docker compose config`.
    """
    return (
        "services:\n"
        f"  {CONTAINER}:\n"
        f"    container_name: {CONTAINER}\n"
        f"    hostname: {CONTAINER}\n"
        f"    image: {image}\n"
        "    restart: always\n"
        "    network_mode: host\n"
        "    env_file:\n"
        "      - .env\n"
        "    volumes:\n"
        f"      - '{log_dir}:{log_dir}'\n"
        "    logging:\n"
        "      driver: json-file\n"
        "      options:\n"
        "        max-size: '30m'\n"
        "        max-file: '5'\n"
    )


def render_logrotate(log_dir: str = LOG_DIR) -> str:
    return (
        f"{log_dir}/*.log {{\n"
        "    size 50M\n"
        "    rotate 5\n"
        "    compress\n"
        "    missingok\n"
        "    notifempty\n"
        "    copytruncate\n"
        "}\n"
    )


@dataclass(slots=True)
class NodeInstallResult:
    changed: bool = False
    env_format: str = ENV_CURRENT
    container_status: str = ""
    image_id: str = ""
    restart_count: int = 0
    port_listening: bool = False
    logs_tail: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self.container_status == "running"

    def as_dict(self) -> dict:
        return {
            "changed": self.changed,
            "env_format": self.env_format,
            "status": self.container_status,
            "image": self.image_id,
            "restarts": self.restart_count,
            "listening": self.port_listening,
            "notes": self.notes,
        }


class NodeInstaller:
    """Owns everything that happens on the Origin Server for the Remnawave Node."""

    def __init__(
        self,
        ssh: SSHClient,
        *,
        secret: str,
        node_port: int = NODE_PORT,
        image: str = IMAGE,
        install_dir: str = INSTALL_DIR,
        log_dir: str = LOG_DIR,
        settle_seconds: int = 12,
    ) -> None:
        if not secret or not secret.strip():
            raise PermanentError("Пустой SECRET_KEY для Remnawave Node")
        self.ssh = ssh
        self.secret = secret.strip()
        self.node_port = node_port
        self.image = image
        self.dir = install_dir
        self.log_dir = log_dir
        self.settle_seconds = settle_seconds

    # ------------------------------------------------------------- rendering

    def env_file(self, fmt: str = ENV_CURRENT) -> str:
        return render_env_file(self.secret, node_port=self.node_port, fmt=fmt)

    def compose_yaml(self) -> str:
        return render_compose(image=self.image, log_dir=self.log_dir)

    def logrotate_config(self) -> str:
        return render_logrotate(self.log_dir)

    # ---------------------------------------------------------------- install

    async def install(self, *, force: bool = False) -> NodeInstallResult:
        result = NodeInstallResult()
        await self._require_docker()

        desired_env = self.env_file(ENV_CURRENT)
        current_env = await self._read_env()

        if not force and current_env == desired_env and await self._container_state() == "running":
            result.changed = False
            result.notes.append("Remnanode уже установлен с теми же параметрами")
            await self._collect(result)
            return result

        await self._write_files(ENV_CURRENT)
        await self._compose_up()
        await self._collect(result)
        result.changed = True

        if result.running:
            await self._install_logrotate()
            return result

        # Not running — decide whether this is the legacy-env case or a real failure.
        if self._looks_legacy(result.logs_tail):
            logger.info("remnanode: falling back to legacy env layout (APP_PORT/SSL_CERT)")
            await self._write_files(ENV_LEGACY)
            await self._compose_up(recreate=True)
            result = NodeInstallResult(changed=True, env_format=ENV_LEGACY)
            await self._collect(result)
            result.notes.append("Использован legacy-формат переменных (APP_PORT/SSL_CERT)")
            if result.running:
                await self._install_logrotate()
                return result

        self._raise_for_logs(result)
        return result

    async def update(self) -> NodeInstallResult:
        """Pull a newer image and recreate the container."""
        await self._require_docker()
        await self._compose_up(pull=True, recreate=True)
        result = NodeInstallResult(changed=True)
        await self._collect(result)
        if not result.running:
            self._raise_for_logs(result)
        return result

    async def restart(self) -> NodeInstallResult:
        await self._compose("restart", timeout=180)
        result = NodeInstallResult()
        await self._collect(result)
        return result

    async def uninstall(self) -> None:
        await self._compose("down", check=False, timeout=180)

    async def diagnostics(self) -> dict:
        """Everything an admin needs to see, with no secrets in it."""
        result = NodeInstallResult()
        try:
            await self._collect(result)
        except Exception as exc:  # noqa: BLE001 — diagnostics must never raise
            result.notes.append(f"сбор диагностики прерван: {exc}")
        env = await self._read_env()
        data = result.as_dict()
        data["env_present"] = bool(env)
        data["env_format"] = ENV_LEGACY if "SSL_CERT=" in env else ENV_CURRENT if env else "—"
        data["logs_tail"] = result.logs_tail[-2000:]
        return data

    # ------------------------------------------------------------ primitives

    async def _require_docker(self) -> None:
        probe = await self.ssh.execute("docker compose version", check=False, quiet=True)
        if not probe.ok:
            raise PermanentError(
                "На Origin Server нет docker compose — шаг установки Docker не выполнен"
            )

    async def _write_files(self, fmt: str) -> None:
        await self.ssh.execute(
            f"mkdir -p {shlex.quote(self.dir)} {shlex.quote(self.log_dir)}", quiet=True
        )
        await self.ssh.write_file(f"{self.dir}/.env", self.env_file(fmt), mode=0o600)
        await self.ssh.write_file(f"{self.dir}/docker-compose.yml", self.compose_yaml(), mode=0o640)

    async def _read_env(self) -> str:
        if not await self.ssh.file_exists(f"{self.dir}/.env"):
            return ""
        try:
            return await self.ssh.read_file(f"{self.dir}/.env")
        except Exception:  # noqa: BLE001 — an unreadable file is treated as absent
            return ""

    async def _compose(self, *args: str, check: bool = True, timeout: int = 600):
        command = f"cd {shlex.quote(self.dir)} && docker compose {' '.join(args)}"
        return await self.ssh.execute(command, check=check, timeout=timeout)

    async def _compose_up(self, *, pull: bool = True, recreate: bool = False) -> None:
        if pull:
            pulled = await self._compose("pull", check=False, timeout=900)
            if not pulled.ok:
                raise TransientError(f"Не удалось скачать образ {self.image}")
        flags = "-d --force-recreate" if recreate else "-d"
        await self._compose("up", flags, timeout=600)

    async def _container_state(self) -> str:
        probe = await self.ssh.execute(
            f"docker inspect -f '{{{{.State.Status}}}}' {CONTAINER} 2>/dev/null || true",
            check=False,
            quiet=True,
        )
        return probe.stdout.strip()

    async def _collect(self, result: NodeInstallResult) -> None:
        """Give the container a moment, then read its real state."""
        state = await self._container_state()
        deadline = self.settle_seconds
        while state != "running" and deadline > 0:
            await asyncio.sleep(3)
            deadline -= 3
            state = await self._container_state()

        result.container_status = state
        inspect = await self.ssh.execute(
            "docker inspect -f '{{.Image}} {{.RestartCount}}' " + CONTAINER + " 2>/dev/null || true",
            check=False,
            quiet=True,
        )
        parts = inspect.stdout.split()
        if parts:
            result.image_id = parts[0][:19]
        if len(parts) > 1 and parts[1].isdigit():
            result.restart_count = int(parts[1])

        listening = await self.ssh.execute(
            f"ss -ltn | grep -c ':{self.node_port} ' || true", check=False, quiet=True
        )
        result.port_listening = listening.stdout.strip().isdigit() and int(listening.stdout.strip()) > 0

        logs = await self.ssh.execute(
            f"docker logs --tail 60 {CONTAINER} 2>&1 || true", check=False, quiet=True
        )
        result.logs_tail = logs.stdout.strip()

        if result.running and result.restart_count > 3:
            result.notes.append(f"контейнер перезапускался {result.restart_count} раз(а)")
        if result.running and not result.port_listening:
            result.notes.append(f"порт {self.node_port} ещё не слушается")

    async def _install_logrotate(self) -> None:
        await self.ssh.write_file("/etc/logrotate.d/remnanode", self.logrotate_config(), mode=0o644)

    # -------------------------------------------------------------- failures

    @staticmethod
    def _looks_legacy(logs: str) -> bool:
        lowered = logs.lower()
        return any(hint.lower() in lowered for hint in LEGACY_HINTS)

    @staticmethod
    def _looks_bad_secret(logs: str) -> bool:
        lowered = logs.lower()
        return any(hint in lowered for hint in BAD_SECRET_HINTS)

    def _raise_for_logs(self, result: NodeInstallResult) -> None:
        tail = result.logs_tail[-800:]
        if self._looks_bad_secret(tail):
            raise PermanentError(
                "Remnawave Node не принимает SECRET_KEY — ключ повреждён или взят от другой панели"
            )
        if "address already in use" in tail.lower() or "bind" in tail.lower():
            raise PermanentError(
                f"Порт {self.node_port} на Origin Server уже занят другим процессом"
            )
        if not result.container_status:
            raise TransientError("Контейнер remnanode не создан")
        raise TransientError(f"Контейнер remnanode в статусе {result.container_status}")


async def wait_until_connected(
    client, node_uuid: str, *, attempts: int = 12, delay: int = 10
) -> bool:
    """Poll the panel until it reports the node as connected."""
    for _ in range(attempts):
        if await client.node_is_connected(node_uuid):
            return True
        await asyncio.sleep(delay)
    return False


def parse_node_json(stdout: str) -> dict:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}
