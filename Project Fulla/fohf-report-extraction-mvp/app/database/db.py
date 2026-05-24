from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path


def _default_db_path() -> Path:
    base = Path(os.getenv("FOHF_DATA_DIR", "/app/data"))
    return base / "database" / "fohf_mvp.sqlite"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            path TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('unprocessed', 'processed', 'failed')),
            error_message TEXT,
            UNIQUE(path)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_file_registry_status ON file_registry(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_file_registry_filename ON file_registry(filename)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extraction_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_name TEXT NOT NULL,
            extracted_value TEXT,
            source_pdf_filename TEXT NOT NULL,
            source_page INTEGER NOT NULL,
            snippet TEXT,
            confidence REAL NOT NULL,
            review_status TEXT NOT NULL CHECK (review_status IN ('ok', 'needs_review')),
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_extraction_pdf ON extraction_results(source_pdf_filename)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_extraction_field ON extraction_results(field_name)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_review (
            filename TEXT PRIMARY KEY,
            notes TEXT DEFAULT '',
            human_reviewed INTEGER NOT NULL DEFAULT 0,
            reviewed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_field (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pdf_filename TEXT NOT NULL,
            field_name TEXT NOT NULL,
            field_value TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_manual_field_pdf ON manual_field(source_pdf_filename)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    conn.commit()
    _migration_cleanup_fund_name_extractions(conn)
    _migration_add_extraction_provenance_columns(conn)
    _migration_create_project_tables(conn)
    _migration_seed_default_project(conn)
    _migration_historical_performance_provenance(conn)


def _migration_create_project_tables(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM app_meta WHERE key = ?",
        ("migration_create_project_tables_v1",),
    ).fetchone()
    if row is not None:
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            manager_name TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            path TEXT NOT NULL,
            document_type TEXT NOT NULL DEFAULT 'report',
            upload_time TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('unprocessed', 'processed', 'failed')),
            error_message TEXT,
            report_period TEXT DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, filename)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_project ON project_documents(project_id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extracted_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            field_name TEXT NOT NULL,
            extracted_value TEXT,
            report_period TEXT DEFAULT '',
            report_quarter TEXT DEFAULT '',
            source_pdf_filename TEXT NOT NULL,
            source_page INTEGER NOT NULL,
            snippet TEXT,
            confidence REAL NOT NULL,
            review_status TEXT NOT NULL CHECK (review_status IN ('ok', 'needs_review')),
            source_table TEXT DEFAULT '',
            source_section_name TEXT DEFAULT '',
            matched_row_label TEXT DEFAULT '',
            matched_column_label TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (document_id) REFERENCES project_documents(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_extracted_values_project ON extracted_values(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_extracted_values_document ON extracted_values(document_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_extracted_values_category ON extracted_values(category)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS historical_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            period_label TEXT NOT NULL,
            return_value TEXT NOT NULL,
            return_pct REAL,
            document_id INTEGER,
            extracted_value_id INTEGER,
            source_pdf_filename TEXT NOT NULL,
            source_page INTEGER,
            snippet TEXT,
            confidence REAL NOT NULL,
            review_status TEXT NOT NULL CHECK (review_status IN ('ok', 'needs_review')),
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, period_year, period_month)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_historical_performance_project ON historical_performance(project_id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            document_id INTEGER,
            extracted_value_id INTEGER,
            event_type TEXT NOT NULL,
            field_name TEXT,
            value TEXT,
            source_pdf TEXT,
            source_page INTEGER,
            source_table TEXT,
            snippet TEXT,
            report_period TEXT,
            confidence REAL,
            review_status TEXT,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_trail_project ON audit_trail(project_id)")

    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?)",
        ("migration_create_project_tables_v1", "1"),
    )
    conn.commit()


def _migration_seed_default_project(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM app_meta WHERE key = ?",
        ("migration_seed_default_project_v1",),
    ).fetchone()
    if row is not None:
        return

    existing = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()
    if existing and int(existing["c"]) > 0:
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?)",
            ("migration_seed_default_project_v1", "1"),
        )
        conn.commit()
        return

    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cur = conn.execute(
        "INSERT INTO projects (name, manager_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("Default Project", "", ts, ts),
    )
    project_id = int(cur.lastrowid)

    legacy_docs = conn.execute(
        "SELECT filename, path, upload_time, status, error_message FROM file_registry ORDER BY upload_time"
    ).fetchall()
    for doc in legacy_docs:
        report_period = ""
        rm = conn.execute(
            """
            SELECT extracted_value FROM extraction_results
            WHERE source_pdf_filename = ? AND field_name = 'report_month'
            ORDER BY id DESC LIMIT 1
            """,
            (doc["filename"],),
        ).fetchone()
        if rm and rm["extracted_value"]:
            report_period = str(rm["extracted_value"])
        conn.execute(
            """
            INSERT OR IGNORE INTO project_documents (
                project_id, filename, path, document_type, upload_time, status, error_message, report_period
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                doc["filename"],
                doc["path"],
                _infer_document_type(doc["filename"]),
                doc["upload_time"],
                doc["status"],
                doc["error_message"],
                report_period,
            ),
        )

    for er in conn.execute("SELECT * FROM extraction_results").fetchall():
        pd_row = conn.execute(
            "SELECT id FROM project_documents WHERE project_id = ? AND filename = ?",
            (project_id, er["source_pdf_filename"]),
        ).fetchone()
        if pd_row is None:
            continue
        category = _field_category(str(er["field_name"]))
        report_period = ""
        if er["field_name"] == "report_month":
            report_period = er["extracted_value"] or ""
        conn.execute(
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
                pd_row["id"],
                category,
                er["field_name"],
                er["extracted_value"],
                report_period,
                _quarter_label_from_period(report_period),
                er["source_pdf_filename"],
                er["source_page"],
                er["snippet"],
                er["confidence"],
                er["review_status"],
                er["source_table"] if "source_table" in er.keys() else "",
                er["source_section_name"] if "source_section_name" in er.keys() else "",
                er["matched_row_label"] if "matched_row_label" in er.keys() else "",
                er["matched_column_label"] if "matched_column_label" in er.keys() else "",
                er["created_at"],
            ),
        )

    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?)",
        ("migration_seed_default_project_v1", "1"),
    )
    conn.commit()
    _sync_legacy_pdfs_to_project(conn, project_id)


def _sync_legacy_pdfs_to_project(conn: sqlite3.Connection, project_id: int) -> None:
    """Attach PDFs found in legacy folders to the default project if not already registered."""
    from datetime import datetime, timezone
    from ingestion.filesystem import all_known_pdfs

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for pdf in all_known_pdfs():
        row = conn.execute(
            "SELECT 1 FROM project_documents WHERE project_id = ? AND filename = ?",
            (project_id, pdf.name),
        ).fetchone()
        if row is not None:
            continue
        status = "processed"
        parent = pdf.resolve().parent.name
        if "failed" in parent:
            status = "failed"
        elif "input" in parent:
            status = "unprocessed"
        conn.execute(
            """
            INSERT INTO project_documents (
                project_id, filename, path, document_type, upload_time, status, error_message, report_period
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, '')
            """,
            (project_id, pdf.name, str(pdf.resolve()), _infer_document_type(pdf.name), ts, status),
        )
    conn.commit()


def _infer_document_type(filename: str) -> str:
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


def _field_category(field_name: str) -> str:
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


def _quarter_label_from_period(period: str) -> str:
    import re as _re

    m = _re.search(
        r"(?i)\b(January|February|March|April|May|June|July|August|September|October|November|December"
        r"|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b",
        period or "",
    )
    if not m:
        qm = _re.search(r"(?i)\bQ([1-4])\s+(\d{4})\b", period or "")
        if qm:
            return f"Q{qm.group(1)} {qm.group(2)}"
        return ""
    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                 "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    month_num = month_map.get(m.group(1).lower()[:3])
    year = int(m.group(2))
    if not month_num:
        return ""
    return f"Q{(month_num - 1) // 3 + 1} {year}"


    conn.commit()


def _migration_historical_performance_provenance(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM app_meta WHERE key = ?",
        ("migration_historical_performance_provenance_v1",),
    ).fetchone()
    if row is not None:
        return
    existing = {r[1] for r in conn.execute("PRAGMA table_info(historical_performance)").fetchall()}
    for col in ("source_table", "source_section_name", "matched_row_label", "matched_column_label"):
        if col not in existing:
            conn.execute(f"ALTER TABLE historical_performance ADD COLUMN {col} TEXT DEFAULT ''")
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?)",
        ("migration_historical_performance_provenance_v1", "1"),
    )
    conn.commit()


def _migration_add_extraction_provenance_columns(conn: sqlite3.Connection) -> None:
    """Add structured provenance columns for audit trail."""
    row = conn.execute(
        "SELECT 1 FROM app_meta WHERE key = ?",
        ("migration_add_extraction_provenance_v1",),
    ).fetchone()
    if row is not None:
        return
    existing = {r[1] for r in conn.execute("PRAGMA table_info(extraction_results)").fetchall()}
    for col in (
        "source_table",
        "source_section_name",
        "matched_row_label",
        "matched_column_label",
    ):
        if col not in existing:
            conn.execute(f"ALTER TABLE extraction_results ADD COLUMN {col} TEXT DEFAULT ''")
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?)",
        ("migration_add_extraction_provenance_v1", "1"),
    )
    conn.commit()


def _migration_cleanup_fund_name_extractions(conn: sqlite3.Connection) -> None:
    """One-time: remove legacy automatic fund_name rows from extraction_results."""
    row = conn.execute(
        "SELECT 1 FROM app_meta WHERE key = ?",
        ("migration_cleanup_fund_name_extractions_v1",),
    ).fetchone()
    if row is not None:
        return
    conn.execute("DELETE FROM extraction_results WHERE field_name = ?", ("fund_name",))
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?)",
        ("migration_cleanup_fund_name_extractions_v1", "1"),
    )
    conn.commit()

