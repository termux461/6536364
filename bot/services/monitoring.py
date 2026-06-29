import time

import aiohttp

from bot.models.server import Server


async def fetch_metrics(server: Server) -> dict:
    host = server.ssh_host or server.endpoint.split(":")[0]
    url = f"http://{host}:9100/metrics"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        async with session.get(url) as resp:
            text = await resp.text()

    values: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("#") or " " not in line:
            continue
        key, _, value = line.rpartition(" ")
        try:
            values[key.split("{")[0]] = float(value)
        except ValueError:
            continue

    load1 = values.get("node_load1", 0.0)
    mem_total = values.get("node_memory_MemTotal_bytes", 0.0)
    mem_available = values.get("node_memory_MemAvailable_bytes", 0.0)
    mem_used_percent = (1 - mem_available / mem_total) * 100 if mem_total else 0.0
    boot_time = values.get("node_boot_time_seconds", 0.0)
    uptime_seconds = time.time() - boot_time if boot_time else 0.0

    return {
        "load1": load1,
        "mem_used_percent": mem_used_percent,
        "uptime_days": uptime_seconds / 86400,
    }
