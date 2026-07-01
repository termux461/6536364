from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from database.db import init_db
from panel.routes import (
    appearance, audit, broadcasts, categories, dashboard, hosts, login, menu,
    payments, promos, tariffs, tickets, users, withdrawals,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="VPN Bot Admin Panel")
app.mount("/panel/static", StaticFiles(directory=BASE_DIR / "static"), name="panel-static")


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.get("/panel")
async def panel_root() -> RedirectResponse:
    return RedirectResponse("/panel/dashboard")


app.include_router(login.router)
app.include_router(dashboard.router)
app.include_router(hosts.router)
app.include_router(tariffs.router)
app.include_router(payments.router)
app.include_router(tickets.router)
app.include_router(broadcasts.router)
app.include_router(menu.router)
app.include_router(withdrawals.router)
app.include_router(categories.router)
app.include_router(appearance.router)
app.include_router(users.router)
app.include_router(promos.router)
app.include_router(audit.router)
