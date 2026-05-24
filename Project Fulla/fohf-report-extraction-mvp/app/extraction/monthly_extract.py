from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from extraction.models import ExtractedField
from extraction.pdf_utils import get_page_text_layers
from extraction.pipeline import extract_all_fields, run_extraction_pipeline

_LOG = logging.getLogger(__name__)
FUND_NAME_EXTRACTION_DEBUG: dict[str, Any] = {}


def reset_fund_name_extraction_debug(filename: str) -> None:
    FUND_NAME_EXTRACTION_DEBUG.clear()
    FUND_NAME_EXTRACTION_DEBUG.update({"pipeline_pdf_filename": filename})


def extract_monthly_fields(pdf_path: Path, *, rules: dict[str, Any] | None = None) -> list[ExtractedField]:
    del rules  # Structured pipeline uses module-specific logic; YAML retained for future metadata tuning.
    filename = pdf_path.name
    reset_fund_name_extraction_debug(filename)
    result = run_extraction_pipeline(pdf_path)
    manager = next((f for f in result.fields if f.field_name == "manager_name"), None)
    FUND_NAME_EXTRACTION_DEBUG["final_fund_name_in_payload_value"] = manager.extracted_value if manager else None
    FUND_NAME_EXTRACTION_DEBUG["final_fund_name_in_payload_confidence"] = manager.confidence if manager else None
    return result.fields


def extract_pdf_safe(pdf_path: Path) -> tuple[list[ExtractedField] | None, str | None]:
    try:
        return extract_all_fields(pdf_path), None
    except Exception as e:  # noqa: BLE001
        _LOG.exception("Extraction failed for %s", pdf_path.name)
        return None, str(e)


__all__ = [
    "ExtractedField",
    "FUND_NAME_EXTRACTION_DEBUG",
    "extract_monthly_fields",
    "extract_pdf_safe",
    "get_page_text_layers",
    "reset_fund_name_extraction_debug",
    "run_extraction_pipeline",
]
