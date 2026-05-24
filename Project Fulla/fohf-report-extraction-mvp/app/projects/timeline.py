from __future__ import annotations

import re
from datetime import datetime, timezone

import sqlite3

from extraction.models import PerformanceTimelinePoint


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_pct(value: str) -> float | None:
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def rebuild_project_timeline(conn: sqlite3.Connection, project_id: int) -> None:
    """
    Rebuild canonical historical_performance from all timeline extractions in the project.
    Deterministic merge: highest confidence wins; equal confidence + different value -> needs_review.
    """
    conn.execute("DELETE FROM historical_performance WHERE project_id = ?", (project_id,))
    conn.commit()

    rows = conn.execute(
        """
        SELECT ev.*, pd.id AS doc_id
        FROM extracted_values ev
        JOIN project_documents pd ON pd.id = ev.document_id
        WHERE ev.project_id = ? AND ev.field_name LIKE 'monthly_return_%'
        ORDER BY ev.confidence DESC, ev.id DESC
        """,
        (project_id,),
    ).fetchall()

    ts = utc_now_iso()
    best: dict[tuple[int, int], sqlite3.Row] = {}
    review_overrides: dict[tuple[int, int], str] = {}

    for r in rows:
        m = re.match(r"monthly_return_(\d{4})_(\d{2})", r["field_name"])
        if not m:
            continue
        key = (int(m.group(1)), int(m.group(2)))
        if key not in best:
            best[key] = r
            continue
        existing = best[key]
        if float(r["confidence"]) > float(existing["confidence"]):
            best[key] = r
        elif float(r["confidence"]) == float(existing["confidence"]):
            if (r["extracted_value"] or "") != (existing["extracted_value"] or ""):
                review_overrides[key] = "needs_review"

    for (year, month), r in sorted(best.items()):
        names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        period_label = r["report_period"] or (f"{names[month]} {year}" if 1 <= month <= 12 else f"{year}-{month:02d}")
        review = review_overrides.get((year, month), r["review_status"])
        conn.execute(
            """
            INSERT INTO historical_performance (
                project_id, period_year, period_month, period_label, return_value, return_pct,
                document_id, extracted_value_id, source_pdf_filename, source_page, snippet,
                confidence, review_status, source_table, source_section_name,
                matched_row_label, matched_column_label, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                year,
                month,
                period_label,
                r["extracted_value"],
                _parse_pct(r["extracted_value"] or ""),
                r["doc_id"],
                r["id"],
                r["source_pdf_filename"],
                r["source_page"],
                r["snippet"],
                r["confidence"],
                review,
                r["source_table"] or "",
                r["source_section_name"] or "",
                r["matched_row_label"] or str(year),
                r["matched_column_label"] or "",
                ts,
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_trail (
                project_id, document_id, extracted_value_id, event_type, field_name, value,
                source_pdf, source_page, source_table, snippet, report_period, confidence,
                review_status, details, created_at
            ) VALUES (?, ?, ?, 'merge_timeline', 'monthly_return', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                r["doc_id"],
                r["id"],
                r["extracted_value"],
                r["source_pdf_filename"],
                r["source_page"],
                r["source_table"],
                r["snippet"],
                period_label,
                r["confidence"],
                review,
                f"Canonical timeline row for {period_label}",
                ts,
            ),
        )
    conn.commit()


def merge_historical_performance(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    timeline_points: list[PerformanceTimelinePoint],
    document_id: int,
) -> None:
    """Incremental merge deprecated in favor of full rebuild — kept for compatibility."""
    del timeline_points, document_id
    rebuild_project_timeline(conn, project_id)
