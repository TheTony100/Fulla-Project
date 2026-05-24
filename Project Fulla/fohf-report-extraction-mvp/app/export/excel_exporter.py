from __future__ import annotations

import io
from typing import Any

import pandas as pd

from extraction.audit_trail import build_audit_trail, collect_exceptions
from extraction.models import ExtractedField, ExtractionException, GroupedValue


def _audit_df(records: list[dict[str, object]]) -> pd.DataFrame:
    cols = [
        "field_name",
        "value",
        "source_pdf",
        "source_page",
        "source_table",
        "source_section_name",
        "matched_row_label",
        "matched_column_label",
        "original_snippet",
        "confidence",
        "review_status",
    ]
    if not records:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(records)[cols]


SUMMARY_FIELDS = (
    "report_month",
    "monthly_net_return",
    "ytd_return",
    "aum_or_nav",
    "manager_name",
)


def _fields_by_name(fields: list[ExtractedField]) -> dict[str, ExtractedField]:
    return {f.field_name: f for f in fields}


def _category_df(fields: list[ExtractedField], names: tuple[str, ...]) -> pd.DataFrame:
    rows = [build_audit_trail([f])[0] for f in fields if f.field_name in names]
    return _audit_df(rows)


def build_workbook_bytes(
    fields: list[ExtractedField],
    *,
    manual_fields: list[dict[str, Any]] | None = None,
    exceptions: list[ExtractionException] | None = None,
) -> bytes:
    """Legacy single-document export (kept for tests)."""
    manual_fields = manual_fields or []
    filename = fields[0].source_pdf_filename if fields else (
        manual_fields[0].get("source_pdf") if manual_fields else "unknown.pdf"
    )
    exceptions = exceptions if exceptions is not None else collect_exceptions(fields, filename=filename)
    audit_records = build_audit_trail(fields)

    by_name = _fields_by_name(fields)
    summary_row: dict[str, object] = {"source_pdf": filename}
    for name in SUMMARY_FIELDS:
        field = by_name.get(name)
        summary_row[name] = field.extracted_value if field else ""
        summary_row[f"{name}_confidence"] = field.confidence if field else ""
        summary_row[f"{name}_review"] = field.review_status if field else "missing"
    summary_df = pd.DataFrame([summary_row])

    monthly_df = _category_df(fields, ("monthly_net_return", "ytd_return"))
    aum_df = _category_df(fields, ("aum_or_nav",))
    exposure_df = _category_df(
        fields,
        ("exposure_long_pct", "exposure_short_pct", "exposure_net_exposure", "exposure_gross_exposure"),
    )
    attribution_df = _category_df(
        fields,
        ("attribution_long", "attribution_short", "attribution_top_winners", "attribution_top_losers"),
    )
    audit_df = _audit_df(audit_records)
    exceptions_df = pd.DataFrame(
        [
            {
                "field_name": e.field_name,
                "exception_type": e.exception_type,
                "message": e.message,
                "source_pdf": e.source_pdf_filename,
                "review_status": e.review_status,
            }
            for e in exceptions
        ]
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Summary")
        monthly_df.to_excel(writer, index=False, sheet_name="Monthly Returns")
        aum_df.to_excel(writer, index=False, sheet_name="AUM_NAV")
        exposure_df.to_excel(writer, index=False, sheet_name="Exposure")
        attribution_df.to_excel(writer, index=False, sheet_name="Attribution")
        audit_df.to_excel(writer, index=False, sheet_name="Audit Trail")
        exceptions_df.to_excel(writer, index=False, sheet_name="Exceptions")
    buf.seek(0)
    return buf.getvalue()


def _grouped_to_audit_row(gv: GroupedValue) -> dict[str, object]:
    return {
        "field_name": gv.field_name,
        "value": gv.value,
        "source_pdf": gv.source_pdf,
        "source_page": gv.source_page,
        "source_table": gv.category,
        "source_section_name": gv.category.title(),
        "matched_row_label": gv.report_period,
        "matched_column_label": gv.report_quarter,
        "original_snippet": gv.snippet,
        "confidence": gv.confidence,
        "review_status": gv.review_status,
        "report_period": gv.report_period,
    }
