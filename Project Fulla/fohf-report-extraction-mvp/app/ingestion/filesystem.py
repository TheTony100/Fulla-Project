from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.getenv("FOHF_DATA_DIR", "/app/data"))


def input_dir() -> Path:
    d = data_dir() / "input_pdfs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def processed_dir() -> Path:
    d = data_dir() / "processed_pdfs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def failed_dir() -> Path:
    d = data_dir() / "failed_pdfs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_pdfs(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])


def all_known_pdfs() -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for folder in (input_dir(), processed_dir(), failed_dir()):
        for p in list_pdfs(folder):
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                out.append(p)
    return sorted(out, key=lambda x: (x.name.lower(), str(x)))

