import asyncio
import zipfile
from datetime import datetime
from pathlib import Path

from bot.config import settings


class BackupError(Exception):
    pass


def _backup_dir() -> Path:
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def create_backup() -> Path:
    backup_dir = _backup_dir()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dump_path = backup_dir / f"backup_{timestamp}.sql"
    zip_path = backup_dir / f"backup_{timestamp}.zip"

    env_args = [
        "pg_dump",
        f"--host={settings.DB_HOST}",
        f"--port={settings.DB_PORT}",
        f"--username={settings.DB_USER}",
        f"--dbname={settings.DB_NAME}",
        "--no-password",
        "-f",
        str(dump_path),
    ]
    process = await asyncio.create_subprocess_exec(
        *env_args,
        env={"PGPASSWORD": settings.DB_PASSWORD},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise BackupError(stderr.decode(errors="replace"))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(dump_path, arcname=dump_path.name)
    dump_path.unlink(missing_ok=True)

    _cleanup_old_backups(backup_dir)
    return zip_path


def _cleanup_old_backups(backup_dir: Path) -> None:
    cutoff = datetime.utcnow().timestamp() - settings.BACKUP_KEEP_DAYS * 86400
    for file in backup_dir.glob("backup_*.zip"):
        if file.stat().st_mtime < cutoff:
            file.unlink(missing_ok=True)


async def restore_backup(zip_path: Path) -> None:
    extract_dir = zip_path.parent / "restore_tmp"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    sql_files = list(extract_dir.glob("*.sql"))
    if not sql_files:
        raise BackupError("В архиве не найден .sql дамп")
    sql_file = sql_files[0]

    process = await asyncio.create_subprocess_exec(
        "psql",
        f"--host={settings.DB_HOST}",
        f"--port={settings.DB_PORT}",
        f"--username={settings.DB_USER}",
        f"--dbname={settings.DB_NAME}",
        "-f",
        str(sql_file),
        env={"PGPASSWORD": settings.DB_PASSWORD},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    sql_file.unlink(missing_ok=True)
    extract_dir.rmdir()
    if process.returncode != 0:
        raise BackupError(stderr.decode(errors="replace"))
