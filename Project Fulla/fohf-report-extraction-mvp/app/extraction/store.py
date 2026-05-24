from __future__ import annotations

from datetime import datetime, timezone

import sqlite3

from extraction.models import ExtractedField


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def delete_extractions_for_pdf(conn: sqlite3.Connection, source_pdf_filename: str) -> None:
    conn.execute(
        "DELETE FROM extraction_results WHERE source_pdf_filename = ?",
        (source_pdf_filename,),
    )
    conn.commit()


def delete_export_identity_extractions_for_pdf(conn: sqlite3.Connection, source_pdf_filename: str) -> None:
    """Remove legacy fund/manager rows before refresh (IDs used only for Excel export)."""
    conn.execute(
        """
        DELETE FROM extraction_results
        WHERE source_pdf_filename = ? AND field_name IN ('manager_name', 'fund_name')
        """,
        (source_pdf_filename,),
    )
    conn.commit()


def insert_extractions(conn: sqlite3.Connection, rows: list[ExtractedField]) -> None:
    ts = utc_now_iso()
    for r in rows:
        conn.execute(
            """
            INSERT INTO extraction_results (
                field_name, extracted_value, source_pdf_filename, source_page,
                snippet, confidence, review_status, created_at,
                source_table, source_section_name, matched_row_label, matched_column_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r.field_name,
                r.extracted_value,
                r.source_pdf_filename,
                r.source_page,
                r.snippet,
                r.confidence,
                r.review_status,
                ts,
                r.source_table,
                r.source_section_name,
                r.matched_row_label,
                r.matched_column_label,
            ),
        )
    conn.commit()


def fetch_extractions_for_pdf(conn: sqlite3.Connection, filename: str) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT id, field_name, extracted_value, source_pdf_filename, source_page,
               snippet, confidence, review_status, created_at,
               source_table, source_section_name, matched_row_label, matched_column_label
        FROM extraction_results
        WHERE source_pdf_filename = ?
        ORDER BY field_name
        """,
        (filename,),
    )
    return cur.fetchall()


def update_extraction_value(
    conn: sqlite3.Connection,
    row_id: int,
    extracted_value: str,
    *,
    human_verified: bool = False,
) -> None:
    """Persist edited value. When ``human_verified`` (UI Save), mark row ok and full confidence for export/review logic."""
    if human_verified:
        conn.execute(
            """
            UPDATE extraction_results
            SET extracted_value = ?, review_status = 'ok', confidence = 1.0
            WHERE id = ?
            """,
            (extracted_value, row_id),
        )
    else:
        conn.execute(
            "UPDATE extraction_results SET extracted_value = ? WHERE id = ?",
            (extracted_value, row_id),
        )
    conn.commit()


def insert_manual_field(
    conn: sqlite3.Connection, *, filename: str, field_name: str, field_value: str
) -> None:
    conn.execute(
        """
        INSERT INTO manual_field (source_pdf_filename, field_name, field_value, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (filename, field_name, field_value, utc_now_iso()),
    )
    conn.commit()


def get_manual_fund_name(conn: sqlite3.Connection, filename: str) -> str:
    cur = conn.execute(
        """
        SELECT field_value FROM manual_field
        WHERE source_pdf_filename = ? AND field_name = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (filename, "fund_name"),
    )
    row = cur.fetchone()
    return (row[0] or "").strip() if row else ""


def set_manual_fund_name(conn: sqlite3.Connection, *, filename: str, value: str) -> None:
    conn.execute(
        "DELETE FROM manual_field WHERE source_pdf_filename = ? AND field_name = ?",
        (filename, "fund_name"),
    )
    v = value.strip()
    if v:
        conn.execute(
            """
            INSERT INTO manual_field (source_pdf_filename, field_name, field_value, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (filename, "fund_name", v, utc_now_iso()),
        )
    conn.commit()


def fetch_manual_fields(conn: sqlite3.Connection, filename: str) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT id, source_pdf_filename, field_name, field_value, created_at
        FROM manual_field
        WHERE source_pdf_filename = ?
        ORDER BY id
        """,
        (filename,),
    )
    return cur.fetchall()


def delete_manual_fields_for_pdf(conn: sqlite3.Connection, filename: str) -> None:
    conn.execute("DELETE FROM manual_field WHERE source_pdf_filename = ?", (filename,))
    conn.commit()


def get_document_review(conn: sqlite3.Connection, filename: str) -> sqlite3.Row | None:
    cur = conn.execute(
        "SELECT filename, notes, human_reviewed, reviewed_at FROM document_review WHERE filename = ?",
        (filename,),
    )
    return cur.fetchone()


def upsert_document_notes(conn: sqlite3.Connection, filename: str, notes: str) -> None:
    conn.execute(
        """
        INSERT INTO document_review (filename, notes, human_reviewed, reviewed_at)
        VALUES (?, ?, 0, NULL)
        ON CONFLICT(filename) DO UPDATE SET notes = excluded.notes
        """,
        (filename, notes),
    )
    conn.commit()


def mark_document_reviewed(conn: sqlite3.Connection, filename: str) -> None:
    row = get_document_review(conn, filename)
    notes = (row["notes"] if row else "") or ""
    ts = utc_now_iso()
    conn.execute(
        """
        INSERT INTO document_review (filename, notes, human_reviewed, reviewed_at)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(filename) DO UPDATE SET
            human_reviewed = 1,
            reviewed_at = ?
        """,
        (filename, notes, ts, ts),
    )
    conn.commit()


def delete_document_data(conn: sqlite3.Connection, filename: str) -> None:
    conn.execute("DELETE FROM document_review WHERE filename = ?", (filename,))
    delete_manual_fields_for_pdf(conn, filename)
    delete_extractions_for_pdf(conn, filename)
    conn.execute("DELETE FROM file_registry WHERE filename = ?", (filename,))
    conn.commit()
