from __future__ import annotations

import os
from pathlib import Path

from ingestion.filesystem import data_dir


def project_root(project_id: int) -> Path:
    d = data_dir() / "projects" / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_input_dir(project_id: int) -> Path:
    d = project_root(project_id) / "input_pdfs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_processed_dir(project_id: int) -> Path:
    d = project_root(project_id) / "processed_pdfs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_failed_dir(project_id: int) -> Path:
    d = project_root(project_id) / "failed_pdfs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_project_pdfs(project_id: int) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for folder in (
        project_input_dir(project_id),
        project_processed_dir(project_id),
        project_failed_dir(project_id),
    ):
        if not folder.exists():
            continue
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() == ".pdf":
                key = str(p.resolve())
                if key not in seen:
                    seen.add(key)
                    out.append(p)
    return sorted(out, key=lambda x: (x.name.lower(), str(x)))


def resolve_project_pdf(project_id: int, filename: str) -> Path | None:
    for folder in (
        project_processed_dir(project_id),
        project_failed_dir(project_id),
        project_input_dir(project_id),
    ):
        candidate = folder / filename
        if candidate.exists():
            return candidate.resolve()
    return None
