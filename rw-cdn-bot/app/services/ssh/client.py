"""SSH access to the Origin Server.

Key-based auth is preferred; a password is accepted as a fallback. Commands are logged
without their secrets (see app.core.logging.redact) and every command has a timeout.
"""
from __future__ import annotations

import asyncio
import logging
import shlex
from dataclasses import dataclass

import asyncssh

from app.core.exceptions import SSHCommandError, SSHError
from app.core.logging import redact
from app.core.retry import retry_async

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SSHCredentials:
    host: str
    port: int = 2222
    username: str = "root"
    private_key: str | None = None
    passphrase: str | None = None
    password: str | None = None


@dataclass(slots=True)
class ServerFacts:
    os_name: str
    cpu_cores: int
    ram_mb: int
    disk_free_mb: int
    has_internet: bool


@dataclass(slots=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SSHClient:
    def __init__(self, credentials: SSHCredentials, *, connect_timeout: int = 30,
                 command_timeout: int = 900) -> None:
        self.credentials = credentials
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self._conn: asyncssh.SSHClientConnection | None = None

    # ------------------------------------------------------------- lifecycle

    async def connect(self) -> None:
        creds = self.credentials
        options: dict = {
            "host": creds.host,
            "port": creds.port,
            "username": creds.username,
            "known_hosts": None,  # customer machines are not in any known_hosts file
            "connect_timeout": self.connect_timeout,
        }
        if creds.private_key:
            try:
                key = asyncssh.import_private_key(creds.private_key, passphrase=creds.passphrase)
            except Exception as exc:
                raise SSHError("SSH private key could not be parsed") from exc
            options["client_keys"] = [key]
        elif creds.password:
            options["password"] = creds.password
        else:
            raise SSHError("Neither an SSH key nor a password was provided")

        async def _open() -> asyncssh.SSHClientConnection:
            try:
                return await asyncssh.connect(**options)
            except asyncssh.PermissionDenied as exc:
                raise SSHError(f"Authentication rejected by {creds.host}:{creds.port}") from exc
            except (TimeoutError, OSError, asyncssh.Error) as exc:
                raise SSHError(f"Cannot reach {creds.host}:{creds.port}: {exc}") from exc

        self._conn = await retry_async(_open, attempts=3, label="ssh.connect", retry_on=(SSHError,))
        logger.info("SSH connected to %s:%s as %s", creds.host, creds.port, creds.username)

    async def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None

    async def __aenter__(self) -> SSHClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # --------------------------------------------------------------- commands

    async def execute(
        self, command: str, *, check: bool = True, timeout: int | None = None, quiet: bool = False
    ) -> CommandResult:
        if self._conn is None:
            raise SSHError("SSH connection is not established")
        if not quiet:
            logger.info("origin$ %s", redact(command if len(command) < 400 else command[:400] + "…"))
        try:
            completed = await asyncio.wait_for(
                self._conn.run(command, check=False), timeout=timeout or self.command_timeout
            )
        except TimeoutError as exc:
            raise SSHError(f"Command timed out after {timeout or self.command_timeout}s") from exc
        except asyncssh.Error as exc:
            raise SSHError(f"SSH channel error: {exc}") from exc

        result = CommandResult(
            command=command,
            exit_code=int(completed.exit_status or 0),
            stdout=str(completed.stdout or ""),
            stderr=str(completed.stderr or ""),
        )
        if check and not result.ok:
            raise SSHCommandError(command, result.exit_code, result.stderr)
        return result

    async def run_script(
        self, script: str, *, name: str = "step", timeout: int | None = None
    ) -> CommandResult:
        """Upload a bash script and run it with `set -euo pipefail`."""
        remote_path = f"/tmp/.rwsetup_{name}.sh"
        await self.write_file(remote_path, "#!/usr/bin/env bash\nset -euo pipefail\n" + script, mode=0o700)
        try:
            return await self.execute(f"bash {shlex.quote(remote_path)}", timeout=timeout)
        finally:
            await self.execute(f"rm -f {shlex.quote(remote_path)}", check=False, quiet=True)

    # ------------------------------------------------------------------ files

    async def write_file(self, path: str, content: str, *, mode: int = 0o644) -> None:
        if self._conn is None:
            raise SSHError("SSH connection is not established")
        async with self._conn.start_sftp_client() as sftp:
            async with sftp.open(path, "w") as handle:
                await handle.write(content)
            await sftp.chmod(path, mode)

    async def upload(self, local_path: str, remote_path: str) -> None:
        if self._conn is None:
            raise SSHError("SSH connection is not established")
        async with self._conn.start_sftp_client() as sftp:
            await sftp.put(local_path, remote_path)

    async def download(self, remote_path: str, local_path: str) -> None:
        if self._conn is None:
            raise SSHError("SSH connection is not established")
        async with self._conn.start_sftp_client() as sftp:
            await sftp.get(remote_path, local_path)

    async def read_file(self, remote_path: str) -> str:
        if self._conn is None:
            raise SSHError("SSH connection is not established")
        async with self._conn.start_sftp_client() as sftp, sftp.open(remote_path, "r") as handle:
            return str(await handle.read())

    async def file_exists(self, remote_path: str) -> bool:
        result = await self.execute(f"test -e {shlex.quote(remote_path)}", check=False, quiet=True)
        return result.ok

    # ------------------------------------------------------------------ checks

    async def check_connection(self) -> bool:
        try:
            result = await self.execute("echo ok", check=False, timeout=20, quiet=True)
            return result.ok and "ok" in result.stdout
        except SSHError:
            return False

    async def gather_facts(self) -> ServerFacts:
        os_name = (await self.execute(
            ". /etc/os-release 2>/dev/null && echo \"$PRETTY_NAME\" || uname -sr",
            check=False, quiet=True)).stdout.strip()
        cpu = (await self.execute("nproc", check=False, quiet=True)).stdout.strip()
        ram = (
            await self.execute("free -m | awk '/^Mem:/{print $2}'", check=False, quiet=True)
        ).stdout.strip()
        disk = (
            await self.execute("df -Pm / | awk 'NR==2{print $4}'", check=False, quiet=True)
        ).stdout.strip()
        net = await self.execute(
            "curl -fsS --max-time 15 -o /dev/null -w '%{http_code}' https://deb.debian.org/ "
            "|| curl -fsS --max-time 15 -o /dev/null -w '%{http_code}' https://1.1.1.1/",
            check=False, quiet=True,
        )
        return ServerFacts(
            os_name=os_name or "unknown",
            cpu_cores=int(cpu) if cpu.isdigit() else 0,
            ram_mb=int(ram) if ram.isdigit() else 0,
            disk_free_mb=int(disk) if disk.isdigit() else 0,
            has_internet=net.stdout.strip().startswith(("2", "3")),
        )
