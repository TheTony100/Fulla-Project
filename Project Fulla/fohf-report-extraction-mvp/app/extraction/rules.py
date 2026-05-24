from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def rules_path() -> Path:
    env = os.getenv("FOHF_CONFIG_DIR")
    if env:
        return Path(env) / "extraction_rules.yaml"
    here = Path(__file__).resolve()
    candidate = here.parents[2] / "configs" / "extraction_rules.yaml"
    if candidate.exists():
        return candidate
    return Path("/app/configs/extraction_rules.yaml")


def load_extraction_rules(path: Path | None = None) -> dict[str, Any]:
    p = path or rules_path()
    if not p.exists():
        return {"fields": {}}
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"fields": {}}
    return data

