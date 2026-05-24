from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import sqlite3


STATUSES = ("unprocessed", "processed", "failed")


@dataclass(frozen=True)
class RegistryRow:
    filename: str
    path: str
    upload_time: str
    status: str
    error_message: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def upsert_file(
    conn: sqlite3.Connection,
    *,
    filename: str,
    path: str,
    upload_time: str | None = None,
    status: str = "unprocessed",
    error_message: str | None = None,
) -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")

    ts = upload_time or utc_now_iso()
    conn.execute(
        """
        INSERT INTO file_registry (filename, path, upload_time, status, error_message)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            filename=excluded.filename,
            status=excluded.status,
            error_message=excluded.error_message
        """,
        (filename, path, ts, status, error_message),
    )
    conn.commit()


def set_status(
    conn: sqlite3.Connection, *, path: str, status: str, error_message: str | None = None
) -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    conn.execute(
        "UPDATE file_registry SET status=?, error_message=? WHERE path=?",
        (status, error_message, path),
    )
    conn.commit()


def update_path(
    conn: sqlite3.Connection,
    *,
    old_path: str,
    new_path: str,
    filename: str | None = None,
) -> None:
    fn = filename if filename is not None else Path(new_path).name
    conn.execute(
        """
        UPDATE file_registry
        SET path = ?, filename = ?
        WHERE path = ?
        """,
        (new_path, fn, old_path),
    )
    conn.commit()


def fetch_by_paths(conn: sqlite3.Connection, paths: Iterable[str]) -> dict[str, RegistryRow]:
    paths = list(paths)
    if not paths:
        return {}

    placeholders = ",".join(["?"] * len(paths))
    cur = conn.execute(
        f"""
        SELECT filename, path, upload_time, status, error_message
        FROM file_registry
        WHERE path IN ({placeholders})
        """,
        paths,
    )
    out: dict[str, RegistryRow] = {}
    for row in cur.fetchall():
        out[row["path"]] = RegistryRow(
            filename=row["filename"],
            path=row["path"],
            upload_time=row["upload_time"],
            status=row["status"],
            error_message=row["error_message"],
        )
    return out


def infer_status_from_folders(
    *, input_pdf: Path, processed_dir: Path, failed_dir: Path
) -> str:
    name = input_pdf.name
    if (processed_dir / name).exists():
        return "processed"
    if (failed_dir / name).exists():
        return "failed"
    return "unprocessed"

