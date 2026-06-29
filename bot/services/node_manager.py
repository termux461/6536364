import logging
from dataclasses import dataclass

import aiohttp

from bot.models.server import Server

logger = logging.getLogger(__name__)


class NodeManagerError(Exception):
    pass


@dataclass
class PeerResult:
    peer_id: str
    config_text: str
    private_key: str
    address: str


class NodeManager:
    """Talks to the wg-easy / awg-easy REST API running on a node.

    Both panels expose a password-protected session API plus client CRUD
    endpoints under /api/wireguard/client. AmneziaWG uses the same shape.
    """

    async def _session(self, server: Server) -> aiohttp.ClientSession:
        session = aiohttp.ClientSession(base_url=server.api_url, timeout=aiohttp.ClientTimeout(total=15))
        async with session.post("/api/session", json={"password": server.api_token}) as resp:
            if resp.status >= 400:
                await session.close()
                raise NodeManagerError(f"Не удалось авторизоваться на ноде {server.name}")
        return session

    async def create_peer(self, server: Server, name: str) -> PeerResult:
        async with await self._session(server) as session:
            async with session.post("/api/wireguard/client", json={"name": name}) as resp:
                if resp.status >= 400:
                    raise NodeManagerError(f"Не удалось создать пира на ноде {server.name}")
                created = await resp.json()
                peer_id = str(created.get("id") or created.get("clientId"))

            async with session.get(f"/api/wireguard/client/{peer_id}/configuration") as resp:
                if resp.status >= 400:
                    raise NodeManagerError(f"Не удалось получить конфигурацию пира на ноде {server.name}")
                config_text = await resp.text()

        private_key = ""
        address = ""
        for line in config_text.splitlines():
            line = line.strip()
            if line.startswith("PrivateKey"):
                private_key = line.split("=", 1)[1].strip()
            elif line.startswith("Address"):
                address = line.split("=", 1)[1].strip()

        return PeerResult(peer_id=peer_id, config_text=config_text, private_key=private_key, address=address)

    async def delete_peer(self, server: Server, peer_id: str) -> None:
        async with await self._session(server) as session:
            async with session.delete(f"/api/wireguard/client/{peer_id}") as resp:
                if resp.status >= 400 and resp.status != 404:
                    raise NodeManagerError(f"Не удалось удалить пира на ноде {server.name}")

    async def list_peers(self, server: Server) -> list[dict]:
        async with await self._session(server) as session:
            async with session.get("/api/wireguard/client") as resp:
                if resp.status >= 400:
                    raise NodeManagerError(f"Не удалось получить список пиров на ноде {server.name}")
                return await resp.json()

    async def get_stats(self, server: Server, peer_id: str) -> dict:
        peers = await self.list_peers(server)
        for peer in peers:
            if str(peer.get("id")) == str(peer_id):
                return peer
        return {}


node_manager = NodeManager()
