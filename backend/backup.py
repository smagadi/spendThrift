from __future__ import annotations

import shutil
from pathlib import Path

from backend.database import resolve_db_path
from backend.errors import BackupError


def backup_database(destination: str | Path, db_path: str | Path | None = None) -> str:
    source = Path(resolve_db_path(db_path))
    if str(source) == ":memory:":
        raise BackupError("Cannot backup an in-memory database")
    if not source.exists():
        raise BackupError(f"Database file not found: {source}")
    dest = Path(destination)
    if dest.is_dir() or str(destination).endswith("/"):
        dest = dest / source.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return str(dest)
