from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncssh

ProgressCallback = Callable[[int, int, str], Awaitable[None]]


@dataclass
class NodeInstallParams:
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_password: str
    protocol: str  # "awg" or "wg"
    wg_port: int
    api_password: str


WG_EASY_COMPOSE = """
services:
  wg-easy:
    image: ghcr.io/wg-easy/wg-easy
    container_name: wg-easy
    environment:
      - WG_HOST={host}
      - PASSWORD={api_password}
      - WG_PORT={wg_port}
    volumes:
      - ./wg-easy-data:/etc/wireguard
    ports:
      - "{wg_port}:{wg_port}/udp"
      - "51821:51821/tcp"
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    restart: unless-stopped
"""

AWG_EASY_COMPOSE = """
services:
  awg-easy:
    image: ghcr.io/spcfox/amnezia-wg-easy
    container_name: awg-easy
    environment:
      - WG_HOST={host}
      - PASSWORD={api_password}
      - WG_PORT={wg_port}
    volumes:
      - ./awg-easy-data:/etc/amnezia/amneziawg
    ports:
      - "{wg_port}:{wg_port}/udp"
      - "51821:51821/tcp"
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    restart: unless-stopped
"""

STEPS = [
    "Подключение по SSH",
    "Обновление пакетов",
    "Установка Docker",
    "Установка UFW и настройка портов",
    "Загрузка docker-compose.yml",
    "Запуск контейнера VPN-панели",
    "Запуск node-exporter (мониторинг)",
    "Получение публичного ключа сервера",
]


class NodeInstaller:
    async def install(self, params: NodeInstallParams, progress: ProgressCallback) -> str:
        """Runs the unattended node setup over SSH. Returns the server's WireGuard public key."""
        total = len(STEPS)
        step = 0

        async def report(text: str) -> None:
            nonlocal step
            step += 1
            await progress(step, total, text)

        await report(STEPS[0])
        async with asyncssh.connect(
            params.ssh_host,
            port=params.ssh_port,
            username=params.ssh_user,
            password=params.ssh_password,
            known_hosts=None,
        ) as conn:
            await report(STEPS[1])
            await conn.run("apt-get update -y", check=True)

            await report(STEPS[2])
            await conn.run(
                "command -v docker >/dev/null 2>&1 || "
                "(curl -fsSL https://get.docker.com | sh)",
                check=True,
            )
            await conn.run(
                "command -v docker-compose >/dev/null 2>&1 || apt-get install -y docker-compose-plugin",
                check=False,
            )

            await report(STEPS[3])
            await conn.run("apt-get install -y ufw", check=True)
            await conn.run(f"ufw allow {params.ssh_port}/tcp", check=False)
            await conn.run(f"ufw allow {params.wg_port}/udp", check=False)
            await conn.run("ufw allow 51821/tcp", check=False)
            await conn.run("ufw allow 9100/tcp", check=False)
            await conn.run("ufw --force enable", check=False)

            await report(STEPS[4])
            compose_template = WG_EASY_COMPOSE if params.protocol == "wg" else AWG_EASY_COMPOSE
            compose_content = compose_template.format(
                host=params.ssh_host, api_password=params.api_password, wg_port=params.wg_port
            )
            await conn.run("mkdir -p /opt/mammot-vpn", check=True)
            async with conn.start_sftp_client() as sftp:
                async with sftp.open("/opt/mammot-vpn/docker-compose.yml", "w") as f:
                    await f.write(compose_content)

            await report(STEPS[5])
            await conn.run("cd /opt/mammot-vpn && (docker compose up -d || docker-compose up -d)", check=True)

            await report(STEPS[6])
            await conn.run(
                "docker rm -f node-exporter >/dev/null 2>&1; "
                "docker run -d --name node-exporter --restart unless-stopped "
                "-p 9100:9100 --pid=host -v /:/host:ro,rslave prom/node-exporter "
                "--path.rootfs=/host",
                check=False,
            )

            await report(STEPS[7])
            container_name = "wg-easy" if params.protocol == "wg" else "awg-easy"
            result = await conn.run(
                f"docker exec {container_name} cat /etc/wireguard/server_publickey "
                f"2>/dev/null || docker exec {container_name} wg show wg0 public-key 2>/dev/null || true",
                check=False,
            )
            public_key = (result.stdout or "").strip()

        return public_key


node_installer = NodeInstaller()
