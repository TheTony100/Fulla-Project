from __future__ import annotations

import pytest

from database.db import get_connection, init_db
from extraction.models import ExtractedField
from projects.aggregation import build_project_analysis
from projects.store import create_project, insert_extracted_values


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.sqlite"
    connection = get_connection(db_path)
    init_db(connection)
    return connection


def test_stale_20_percent_not_shown_in_ui(conn):
    project_id = create_project(conn, name="Stale Test")
    conn.execute(
        """
        INSERT INTO project_documents (project_id, filename, path, document_type, upload_time, status, report_period)
        VALUES (?, 'bad.pdf', '/tmp/bad.pdf', 'report', '2025-01-01', 'processed', 'January 2025')
        """,
        (project_id,),
    )
    conn.commit()
    doc_id = int(conn.execute("SELECT id FROM project_documents").fetchone()["id"])

    stale = ExtractedField(
        field_name="monthly_net_return",
        extracted_value="20%",
        source_pdf_filename="bad.pdf",
        source_page=2,
        snippet="fees (2/20%)",
        confidence=0.5,
        review_status="needs_review",
        source_section_name="",
    )
    insert_extracted_values(conn, project_id=project_id, document_id=doc_id, fields=[stale], report_period="January 2025")

    analysis = build_project_analysis(conn, project_id)
    monthly_vals = [p.value for p in analysis.performance if "return" in p.label.lower()]
    assert "20%" not in monthly_vals
