from __future__ import annotations

import shutil
from pathlib import Path

import sqlite3

from dataclasses import replace

from extraction.audit_trail import build_audit_trail
from extraction.models import ExtractedField
from extraction.pdf_utils import load_page_texts
from extraction.performance_table_extractor import (
    extract_monthly_return_from_table,
    extract_performance_timeline,
)
from extraction.pipeline import run_extraction_pipeline
from extraction.report_metadata_extractor import parse_report_period
from projects.extraction_debug import ExtractionDebugInfo
from projects.timeline import rebuild_project_timeline
from projects.filesystem import project_failed_dir, project_input_dir, project_processed_dir, resolve_project_pdf
from projects.store import (
    delete_all_extractions_for_project,
    delete_document_extractions,
    infer_document_type,
    insert_audit_entries,
    insert_extracted_values,
    touch_project,
    update_document_status,
    upsert_project_document,
)


_MONTHLY_HISTORY_TABLE = "Monthly Performance History"
_PERFORMANCE_EXTRACT_FN = (
    "extract_monthly_return_from_table + extract_performance_timeline "
    f"(table: {_MONTHLY_HISTORY_TABLE} only)"
)


def _safe_move(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        dest.unlink()
    shutil.move(str(src), str(dest))
    return dest


def _timeline_to_fields(points, filename: str) -> list[ExtractedField]:
    out: list[ExtractedField] = []
    for pt in points:
        out.append(
            ExtractedField(
                field_name=f"monthly_return_{pt.period_year}_{pt.period_month:02d}",
                extracted_value=pt.return_value,
                source_pdf_filename=filename,
                source_page=pt.source_page,
                snippet=pt.snippet,
                confidence=pt.confidence,
                review_status=pt.review_status,
                source_table=pt.source_table,
                source_section_name=pt.source_section_name,
                matched_row_label=pt.matched_row_label,
                matched_column_label=pt.matched_column_label,
            )
        )
    return out


def _strip_performance_fields(fields: list[ExtractedField]) -> list[ExtractedField]:
    return [f for f in fields if f.field_name not in ("monthly_net_return", "ytd_return")]


def _merge_monthly_from_timeline(
    monthly: ExtractedField,
    timeline,
    report_period: str,
) -> ExtractedField:
    period = parse_report_period(report_period)
    if period is None:
        return monthly
    year, month = period
    pt = next((p for p in timeline if p.period_year == year and p.period_month == month), None)
    if pt is None:
        return monthly
    if monthly.extracted_value == pt.return_value:
        return monthly
    if monthly.extracted_value == "needs_review":
        return replace(
            monthly,
            extracted_value=pt.return_value,
            source_page=pt.source_page,
            snippet=pt.snippet,
            confidence=pt.confidence,
            review_status="ok",
            source_table=pt.source_table,
            source_section_name=pt.source_section_name,
            matched_row_label=pt.matched_row_label,
            matched_column_label=pt.matched_column_label,
        )
    return replace(
        monthly,
        extracted_value=pt.return_value,
        source_page=pt.source_page,
        snippet=pt.snippet,
        confidence=min(monthly.confidence, pt.confidence),
        review_status="needs_review",
        source_table=pt.source_table,
        source_section_name=pt.source_section_name,
        matched_row_label=pt.matched_row_label,
        matched_column_label=pt.matched_column_label,
    )


def _ui_monthly_for_document(conn: sqlite3.Connection, project_id: int, filename: str) -> tuple[str, str]:
    """Value shown in Project Analysis for this PDF's report-month return."""
    doc = conn.execute(
        "SELECT id, report_period FROM project_documents WHERE project_id = ? AND filename = ?",
        (project_id, filename),
    ).fetchone()
    if doc is None:
        return "", "no document row"

    period = doc["report_period"] or ""
    parsed = parse_report_period(period)
    if parsed:
        year, month = parsed
        hist = conn.execute(
            """
            SELECT return_value, source_section_name FROM historical_performance
            WHERE project_id = ? AND period_year = ? AND period_month = ?
            """,
            (project_id, year, month),
        ).fetchone()
        if hist and hist["return_value"]:
            return str(hist["return_value"]), f"historical_performance ({hist['source_section_name'] or '—'})"

    row = conn.execute(
        """
        SELECT extracted_value, source_section_name, review_status FROM extracted_values
        WHERE project_id = ? AND document_id = ? AND field_name = 'monthly_net_return'
        ORDER BY id DESC LIMIT 1
        """,
        (project_id, int(doc["id"])),
    ).fetchone()
    if row:
        val = row["extracted_value"] or ""
        if row["review_status"] == "needs_review" and val != "needs_review":
            val = f"{val} (needs_review)"
        return val, f"extracted_values ({row['source_section_name'] or '—'})"
    return "", "not in DB"


def extract_document_for_project(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    pdf_path: Path,
    wipe_project_first: bool = False,
) -> tuple[bool, str | None, ExtractionDebugInfo | None]:
    filename = pdf_path.name
    document_id = upsert_project_document(
        conn,
        project_id=project_id,
        filename=filename,
        path=str(pdf_path.resolve()),
        status="unprocessed",
        document_type=infer_document_type(filename),
    )

    deleted_counts = {"extracted_values": 0, "historical_performance": 0, "audit_trail": 0, "extraction_results": 0}
    if wipe_project_first:
        deleted_counts = delete_all_extractions_for_project(conn, project_id)
    else:
        deleted_counts["extracted_values"] = delete_document_extractions(
            conn, project_id=project_id, document_id=document_id
        )

    old_path = str(pdf_path.resolve())
    debug: ExtractionDebugInfo | None = None

    try:
        pipeline_result = run_extraction_pipeline(pdf_path)
        fields = _strip_performance_fields(pipeline_result.fields)

        pages = load_page_texts(pdf_path)
        report_period = next((f.extracted_value for f in fields if f.field_name == "report_month"), "")

        monthly = extract_monthly_return_from_table(
            pages,
            report_month_value=report_period or None,
            filename=filename,
        )
        if monthly is None:
            monthly = ExtractedField(
                field_name="monthly_net_return",
                extracted_value="needs_review",
                source_pdf_filename=filename,
                source_page=0,
                snippet="Monthly Performance History table not parsed.",
                confidence=0.0,
                review_status="needs_review",
            )

        timeline = extract_performance_timeline(pages, filename=filename)
        monthly = _merge_monthly_from_timeline(monthly, timeline, report_period or "")
        timeline_fields = _timeline_to_fields(timeline, filename)

        raw_monthly = monthly.extracted_value
        all_fields = list(fields) + [monthly] + timeline_fields
        insertable = [f for f in all_fields if f.field_name not in ("manager_name", "fund_name")]

        value_ids = insert_extracted_values(
            conn,
            project_id=project_id,
            document_id=document_id,
            fields=insertable,
            report_period=report_period or "",
        )
        rebuild_project_timeline(conn, project_id)

        ui_val, ui_src = _ui_monthly_for_document(conn, project_id, filename)
        debug = ExtractionDebugInfo(
            pdf_filename=filename,
            extraction_function=_PERFORMANCE_EXTRACT_FN,
            raw_monthly_return_before_db=raw_monthly,
            deleted_extracted_values=deleted_counts.get("extracted_values", 0),
            deleted_historical_performance=deleted_counts.get("historical_performance", 0),
            deleted_audit_trail=deleted_counts.get("audit_trail", 0),
            deleted_extraction_results=deleted_counts.get("extraction_results", 0),
            inserted_field_names=[f.field_name for f in insertable],
            inserted_monthly_net_return=raw_monthly,
            ui_display_monthly_return=ui_val,
            ui_display_source=ui_src,
        )

        audit_records = build_audit_trail(insertable)
        for i, rec in enumerate(audit_records):
            rec["event_type"] = "extraction"
            rec["report_period"] = report_period
            if i < len(value_ids):
                rec["extracted_value_id"] = value_ids[i]
        insert_audit_entries(conn, project_id=project_id, document_id=document_id, entries=audit_records)

        try:
            moved = _safe_move(pdf_path, project_processed_dir(project_id))
            update_document_status(
                conn,
                document_id=document_id,
                path=str(moved.resolve()),
                status="processed",
                error_message=None,
                report_period=report_period or None,
            )
        except Exception as move_e:  # noqa: BLE001
            update_document_status(
                conn,
                document_id=document_id,
                path=old_path,
                status="failed",
                error_message=f"Extract ok but move failed: {move_e}",
            )
            touch_project(conn, project_id)
            return False, str(move_e), debug

        touch_project(conn, project_id)
        return True, None, debug

    except Exception as e:  # noqa: BLE001
        err = str(e)
        try:
            moved = _safe_move(pdf_path, project_failed_dir(project_id))
            update_document_status(
                conn,
                document_id=document_id,
                path=str(moved.resolve()),
                status="failed",
                error_message=err,
            )
        except Exception as move_e:  # noqa: BLE001
            update_document_status(
                conn,
                document_id=document_id,
                path=old_path,
                status="failed",
                error_message=f"{err}; move failed: {move_e}",
            )
        touch_project(conn, project_id)
        return False, err, debug


def clear_and_reprocess_project(conn: sqlite3.Connection, project_id: int) -> list[ExtractionDebugInfo]:
    """Delete ALL project extractions, then re-extract every document PDF."""
    delete_all_extractions_for_project(conn, project_id)
    debug_runs: list[ExtractionDebugInfo] = []

    for doc in conn.execute(
        "SELECT filename FROM project_documents WHERE project_id = ? ORDER BY filename",
        (project_id,),
    ).fetchall():
        filename = doc["filename"]
        path = resolve_project_pdf(project_id, filename)
        if path is None or not path.exists():
            continue
        if path.parent != project_input_dir(project_id).resolve():
            dest = project_input_dir(project_id) / path.name
            if dest.exists():
                dest.unlink()
            shutil.copy2(path, dest)
            path = dest
        ok, _err, dbg = extract_document_for_project(
            conn,
            project_id=project_id,
            pdf_path=path,
            wipe_project_first=False,
        )
        if dbg:
            debug_runs.append(dbg)
        if not ok:
            continue
    return debug_runs


def save_upload_to_project(project_id: int, file_name: str, file_bytes: bytes) -> Path:
    dest = project_input_dir(project_id) / Path(file_name).name
    dest.write_bytes(file_bytes)
    return dest
