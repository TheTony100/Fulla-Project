from __future__ import annotations

from datetime import datetime, timezone

import sqlite3

from extraction.models import ExtractionException
from projects.store import fetch_extracted_values_for_project, fetch_historical_performance, list_project_documents

LOW_CONFIDENCE_THRESHOLD = 0.72
REQUIRED_DOC_FIELDS = frozenset({"report_month", "monthly_net_return", "aum_or_nav"})


def collect_project_exceptions(conn: sqlite3.Connection, project_id: int) -> list[ExtractionException]:
    """Aggregate exceptions across all documents in a project."""
    exceptions: list[ExtractionException] = []
    docs = list_project_documents(conn, project_id)
    rows = fetch_extracted_values_for_project(conn, project_id)

    by_doc: dict[str, list] = {}
    for r in rows:
        by_doc.setdefault(r["source_pdf_filename"], []).append(r)

    for doc in docs:
        doc_rows = by_doc.get(doc.filename, [])
        field_names = {r["field_name"] for r in doc_rows}
        for req in REQUIRED_DOC_FIELDS:
            if req not in field_names:
                exceptions.append(
                    ExtractionException(
                        field_name=req,
                        exception_type="missing_field",
                        message=f"Required field '{req}' not extracted from document.",
                        source_pdf_filename=doc.filename,
                    )
                )
        if doc.status == "failed":
            exceptions.append(
                ExtractionException(
                    field_name="(document)",
                    exception_type="extraction_failed",
                    message=doc.error_message or "Document extraction failed.",
                    source_pdf_filename=doc.filename,
                )
            )

    for r in rows:
        if r["field_name"].startswith("monthly_return_"):
            continue
        conf = float(r["confidence"])
        if conf < LOW_CONFIDENCE_THRESHOLD:
            exceptions.append(
                ExtractionException(
                    field_name=r["field_name"],
                    exception_type="low_confidence",
                    message=f"Confidence {conf:.3f} below {LOW_CONFIDENCE_THRESHOLD}.",
                    source_pdf_filename=r["source_pdf_filename"],
                )
            )
        if r["review_status"] == "needs_review":
            exceptions.append(
                ExtractionException(
                    field_name=r["field_name"],
                    exception_type="needs_review",
                    message="Value flagged for human review.",
                    source_pdf_filename=r["source_pdf_filename"],
                )
            )
        if r["field_name"] in ("monthly_net_return", "ytd_return"):
            if not r["source_table"] or not r["matched_row_label"] or not r["matched_column_label"]:
                exceptions.append(
                    ExtractionException(
                        field_name=r["field_name"],
                        exception_type="missing_table_evidence",
                        message="Performance value lacks table row/column provenance.",
                        source_pdf_filename=r["source_pdf_filename"],
                    )
                )

    hist = fetch_historical_performance(conn, project_id)
    for h in hist:
        if h["review_status"] == "needs_review":
            exceptions.append(
                ExtractionException(
                    field_name="monthly_return",
                    exception_type="merge_conflict",
                    message=f"Conflicting values merged for {h['period_label']}.",
                    source_pdf_filename=h["source_pdf_filename"],
                )
            )

    return exceptions


def utc_export_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%d %H:%M UTC")
