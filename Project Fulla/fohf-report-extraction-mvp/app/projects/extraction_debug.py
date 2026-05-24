from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractionDebugInfo:
    """Trace one extraction run for the hard-debug panel."""

    pdf_filename: str
    extraction_function: str
    raw_monthly_return_before_db: str
    deleted_extracted_values: int = 0
    deleted_historical_performance: int = 0
    deleted_audit_trail: int = 0
    deleted_extraction_results: int = 0
    inserted_field_names: list[str] = field(default_factory=list)
    inserted_monthly_net_return: str = ""
    ui_display_monthly_return: str = ""
    ui_display_source: str = ""
