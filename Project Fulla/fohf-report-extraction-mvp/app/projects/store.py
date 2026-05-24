from __future__ import annotations

import re
from datetime import datetime, timezone

import sqlite3

from extraction.models import ExtractedField, PerformanceTimelinePoint, Project, ProjectDocument
from projects.filesystem import project_failed_dir, project_input_dir, project_processed_dir


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def infer_document_type(filename: str) -> str:
    lo = filename.lower()
    if "capital" in lo or "statement" in lo:
        return "capital_statement"
    if "exposure" in lo:
        return "exposure_report"
    if re.search(r"\bq1\b", lo):
        return "quarterly_q1"
    if re.search(r"\bq2\b", lo):
        return "quarterly_q2"
    if re.search(r"\bq3\b", lo):
        return "quarterly_q3"
    if re.search(r"\bq4\b", lo):
        return "quarterly_q4"
    return "report"


def field_category(field_name: str) -> str:
    if field_name in ("report_month", "manager_name"):
        return "metadata"
    if field_name in ("monthly_net_return", "ytd_return") or field_name.startswith("monthly_return_"):
        return "performance"
    if field_name == "aum_or_nav":
        return "aum"
    if field_name.startswith("exposure_"):
        return "exposure"
    if field_name.startswith("attribution_"):
        return "attribution"
    return "other"


def quarter_label_from_period(period: str) -> str:
    m = re.search(
        r"(?i)\b(January|February|March|April|May|June|July|August|September|October|November|December"
        r"|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b",
        period or "",
    )
    if not m:
        qm = re.search(r"(?i)\bQ([1-4])\s+(\d{4})\b", period or "")
        if qm:
            return f"Q{qm.group(1)} {qm.group(2)}"
        return ""
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    month_num = month_map.get(m.group(1).lower()[:3])
    year = int(m.group(2))
    if not month_num:
        return ""
    return f"Q{(month_num - 1) // 3 + 1} {year}"


def create_project(conn: sqlite3.Connection, *, name: str, manager_name: str = "") -> int:
    ts = utc_now_iso()
    cur = conn.execute(
        "INSERT INTO projects (name, manager_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (name.strip(), manager_name.strip(), ts, ts),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_projects(conn: sqlite3.Connection) -> list[Project]:
    rows = conn.execute(
        "SELECT id, name, manager_name, created_at, updated_at FROM projects ORDER BY updated_at DESC"
    ).fetchall()
    return [
        Project(
            id=int(r["id"]),
            name=r["name"],
            manager_name=r["manager_name"] or "",
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def get_project(conn: sqlite3.Connection, project_id: int) -> Project | None:
    r = conn.execute(
        "SELECT id, name, manager_name, created_at, updated_at FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if r is None:
        return None
    return Project(
        id=int(r["id"]),
        name=r["name"],
        manager_name=r["manager_name"] or "",
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def touch_project(conn: sqlite3.Connection, project_id: int) -> None:
    conn.execute(
        "UPDATE projects SET updated_at = ? WHERE id = ?",
        (utc_now_iso(), project_id),
    )
    conn.commit()


def upsert_project_document(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    filename: str,
    path: str,
    status: str = "unprocessed",
    error_message: str | None = None,
    document_type: str | None = None,
    report_period: str = "",
    upload_time: str | None = None,
) -> int:
    ts = upload_time or utc_now_iso()
    dtype = document_type or infer_document_type(filename)
    conn.execute(
        """
        INSERT INTO project_documents (
            project_id, filename, path, document_type, upload_time, status, error_message, report_period
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, filename) DO UPDATE SET
            path = excluded.path,
            document_type = excluded.document_type,
            status = excluded.status,
            error_message = excluded.error_message,
            report_period = COALESCE(NULLIF(excluded.report_period, ''), project_documents.report_period)
        """,
        (project_id, filename, path, dtype, ts, status, error_message, report_period),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM project_documents WHERE project_id = ? AND filename = ?",
        (project_id, filename),
    ).fetchone()
    return int(row["id"])


def list_project_documents(conn: sqlite3.Connection, project_id: int) -> list[ProjectDocument]:
    rows = conn.execute(
        """
        SELECT id, project_id, filename, path, document_type, upload_time, status, error_message, report_period
        FROM project_documents
        WHERE project_id = ?
        ORDER BY upload_time DESC, filename
        """,
        (project_id,),
    ).fetchall()
    return [
        ProjectDocument(
            id=int(r["id"]),
            project_id=int(r["project_id"]),
            filename=r["filename"],
            path=r["path"],
            document_type=r["document_type"],
            upload_time=r["upload_time"],
            status=r["status"],
            error_message=r["error_message"],
            report_period=r["report_period"] or "",
        )
        for r in rows
    ]


def get_project_document(conn: sqlite3.Connection, document_id: int) -> ProjectDocument | None:
    r = conn.execute(
        """
        SELECT id, project_id, filename, path, document_type, upload_time, status, error_message, report_period
        FROM project_documents WHERE id = ?
        """,
        (document_id,),
    ).fetchone()
    if r is None:
        return None
    return ProjectDocument(
        id=int(r["id"]),
        project_id=int(r["project_id"]),
        filename=r["filename"],
        path=r["path"],
        document_type=r["document_type"],
        upload_time=r["upload_time"],
        status=r["status"],
        error_message=r["error_message"],
        report_period=r["report_period"] or "",
    )


def update_document_status(
    conn: sqlite3.Connection,
    *,
    document_id: int,
    path: str,
    status: str,
    error_message: str | None = None,
    report_period: str | None = None,
) -> None:
    if report_period is not None:
        conn.execute(
            """
            UPDATE project_documents
            SET path = ?, status = ?, error_message = ?, report_period = ?
            WHERE id = ?
            """,
            (path, status, error_message, report_period, document_id),
        )
    else:
        conn.execute(
            """
            UPDATE project_documents SET path = ?, status = ?, error_message = ? WHERE id = ?
            """,
            (path, status, error_message, document_id),
        )
    conn.commit()


def delete_document_extractions(conn: sqlite3.Connection, *, project_id: int, document_id: int) -> int:
    cur = conn.execute(
        "DELETE FROM extracted_values WHERE project_id = ? AND document_id = ?",
        (project_id, document_id),
    )
    conn.commit()
    return int(cur.rowcount)


def delete_all_extractions_for_project(conn: sqlite3.Connection, project_id: int) -> dict[str, int]:
    """Remove all extracted rows for a project (values, timeline, audit, legacy results)."""
    docs = list_project_documents(conn, project_id)
    filenames = [d.filename for d in docs]

    ev = conn.execute("DELETE FROM extracted_values WHERE project_id = ?", (project_id,))
    hp = conn.execute("DELETE FROM historical_performance WHERE project_id = ?", (project_id,))
    at = conn.execute("DELETE FROM audit_trail WHERE project_id = ?", (project_id,))

    legacy = 0
    if filenames:
        placeholders = ",".join("?" * len(filenames))
        leg = conn.execute(
            f"DELETE FROM extraction_results WHERE source_pdf_filename IN ({placeholders})",
            filenames,
        )
        legacy = int(leg.rowcount)

    conn.commit()
    return {
        "extracted_values": int(ev.rowcount),
        "historical_performance": int(hp.rowcount),
        "audit_trail": int(at.rowcount),
        "extraction_results": legacy,
    }


def insert_extracted_values(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    document_id: int,
    fields: list[ExtractedField],
    report_period: str = "",
) -> list[int]:
    ts = utc_now_iso()
    quarter = quarter_label_from_period(report_period)
    ids: list[int] = []
    for f in fields:
        if f.field_name in ("manager_name", "fund_name"):
            continue
        period = report_period
        if f.field_name == "report_month":
            period = f.extracted_value
        elif f.field_name.startswith("monthly_return_"):
            m = re.match(r"monthly_return_(\d{4})_(\d{2})", f.field_name)
            if m:
                year, month = int(m.group(1)), int(m.group(2))
                names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                if 1 <= month <= 12:
                    period = f"{names[month]} {year}"
        cur = conn.execute(
            """
            INSERT INTO extracted_values (
                project_id, document_id, category, field_name, extracted_value,
                report_period, report_quarter, source_pdf_filename, source_page, snippet,
                confidence, review_status, source_table, source_section_name,
                matched_row_label, matched_column_label, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                document_id,
                field_category(f.field_name),
                f.field_name,
                f.extracted_value,
                period,
                quarter_label_from_period(period) or quarter,
                f.source_pdf_filename,
                f.source_page,
                f.snippet,
                f.confidence,
                f.review_status,
                f.source_table,
                f.source_section_name,
                f.matched_row_label,
                f.matched_column_label,
                ts,
            ),
        )
        ids.append(int(cur.lastrowid))
    conn.commit()
    return ids


def insert_audit_entries(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    document_id: int | None,
    entries: list[dict[str, object]],
) -> None:
    ts = utc_now_iso()
    for e in entries:
        conn.execute(
            """
            INSERT INTO audit_trail (
                project_id, document_id, extracted_value_id, event_type, field_name, value,
                source_pdf, source_page, source_table, snippet, report_period, confidence,
                review_status, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                document_id,
                e.get("extracted_value_id"),
                e.get("event_type", "extraction"),
                e.get("field_name"),
                e.get("value"),
                e.get("source_pdf"),
                e.get("source_page"),
                e.get("source_table"),
                e.get("snippet"),
                e.get("report_period"),
                e.get("confidence"),
                e.get("review_status"),
                e.get("details"),
                ts,
            ),
        )
    conn.commit()


def fetch_extracted_values_for_project(conn: sqlite3.Connection, project_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM extracted_values
        WHERE project_id = ?
        ORDER BY category, report_period, field_name
        """,
        (project_id,),
    ).fetchall()


def fetch_historical_performance(conn: sqlite3.Connection, project_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM historical_performance
        WHERE project_id = ?
        ORDER BY period_year, period_month
        """,
        (project_id,),
    ).fetchall()


def fetch_audit_trail(conn: sqlite3.Connection, project_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM audit_trail
        WHERE project_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (project_id,),
    ).fetchall()


def delete_project_document(conn: sqlite3.Connection, document_id: int) -> ProjectDocument | None:
    doc = get_project_document(conn, document_id)
    if doc is None:
        return None
    conn.execute("DELETE FROM extracted_values WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM audit_trail WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM project_documents WHERE id = ?", (document_id,))
    conn.commit()
    return doc


def document_bucket(project_id: int, path: Path) -> str:
    parent = path.resolve().parent
    if parent == project_input_dir(project_id).resolve():
        return "input"
    if parent == project_processed_dir(project_id).resolve():
        return "processed"
    if parent == project_failed_dir(project_id).resolve():
        return "failed"
    return "unknown"
