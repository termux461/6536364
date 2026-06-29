from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import async_session

templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
