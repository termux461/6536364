import aiohttp
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WgEasyClient:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None

    async def _sess(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _auth(self):
        s = await self._sess()
        async with s.post(f"{self.base_url}/api/session",
                          json={"password": self.password}) as r:
            if r.status != 204:
                raise RuntimeError(f"wg-easy auth failed {r.status}")

    async def _req(self, method: str, path: str, **kw):
        s = await self._sess()
        async with s.request(method, f"{self.base_url}{path}", **kw) as r:
            if r.status == 401:
                await self._auth()
                async with s.request(method, f"{self.base_url}{path}", **kw) as r2:
                    r2.raise_for_status()
                    ct = r2.headers.get("content-type", "")
                    return await r2.json() if "json" in ct else await r2.text()
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            return await r.json() if "json" in ct else await r.text()

    async def create_peer(self, name: str) -> dict:
        result = await self._req("POST", "/api/wireguard/client", json={"name": name})
        logger.info(f"WG peer created: {name} -> {result['id']}")
        return result

    async def get_peer_config(self, peer_id: str) -> str:
        return await self._req("GET", f"/api/wireguard/client/{peer_id}/configuration")

    async def delete_peer(self, peer_id: str):
        await self._req("DELETE", f"/api/wireguard/client/{peer_id}")
        logger.info(f"WG peer deleted: {peer_id}")

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
