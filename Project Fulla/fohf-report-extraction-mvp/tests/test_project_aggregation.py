from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from database.db import get_connection, init_db
from extraction.models import ExtractedField
from extraction.pdf_utils import load_page_texts
from extraction.performance_table_extractor import extract_performance_timeline
from projects.aggregation import build_project_analysis
from projects.pipeline import extract_document_for_project
from projects.store import create_project, fetch_historical_performance, insert_extracted_values, list_project_documents
from projects.timeline import rebuild_project_timeline

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed_pdfs"


def _sample_pdf() -> Path | None:
    if not DATA_DIR.exists():
        return None
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    return pdfs[0] if pdfs else None


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.sqlite"
    connection = get_connection(db_path)
    init_db(connection)
    return connection


@pytest.fixture
def sample_pdf_copy(tmp_path):
    src = _sample_pdf()
    if src is None:
        pytest.skip("No sample PDFs available")
    dest = tmp_path / src.name
    shutil.copy(src, dest)
    return dest


def test_performance_timeline_on_available_pdf(sample_pdf_copy):
    pages = load_page_texts(sample_pdf_copy)
    timeline = extract_performance_timeline(pages, filename=sample_pdf_copy.name)
    assert isinstance(timeline, list)


def test_project_pipeline_runs(conn, sample_pdf_copy):
    project_id = create_project(conn, name="Pipeline Test Project")
    ok, err, _dbg = extract_document_for_project(conn, project_id=project_id, pdf_path=sample_pdf_copy)
    assert ok, err

    docs = list_project_documents(conn, project_id)
    assert len(docs) == 1
    assert docs[0].status == "processed"

    analysis = build_project_analysis(conn, project_id)
    assert analysis.document_count == 1


def test_rebuild_timeline_keeps_higher_confidence(conn):
    project_id = create_project(conn, name="Merge Test")
    conn.execute(
        """
        INSERT INTO project_documents (project_id, filename, path, document_type, upload_time, status)
        VALUES (?, 'q1.pdf', '/tmp/q1.pdf', 'report', '2025-01-01', 'processed')
        """,
        (project_id,),
    )
    conn.execute(
        """
        INSERT INTO project_documents (project_id, filename, path, document_type, upload_time, status)
        VALUES (?, 'q1_v2.pdf', '/tmp/q1_v2.pdf', 'report', '2025-01-01', 'processed')
        """,
        (project_id,),
    )
    conn.commit()
    doc1 = conn.execute("SELECT id FROM project_documents WHERE filename='q1.pdf'").fetchone()["id"]
    doc2 = conn.execute("SELECT id FROM project_documents WHERE filename='q1_v2.pdf'").fetchone()["id"]

    low = ExtractedField(
        field_name="monthly_return_2025_03",
        extracted_value="1.25%",
        source_pdf_filename="q1.pdf",
        source_page=1,
        snippet="low",
        confidence=0.8,
        review_status="ok",
        source_table="Monthly Performance History",
        matched_row_label="2025",
        matched_column_label="MAR",
    )
    high = ExtractedField(
        field_name="monthly_return_2025_03",
        extracted_value="1.25%",
        source_pdf_filename="q1_v2.pdf",
        source_page=1,
        snippet="high",
        confidence=0.99,
        review_status="ok",
        source_table="Monthly Performance History",
        matched_row_label="2025",
        matched_column_label="MAR",
    )
    insert_extracted_values(conn, project_id=project_id, document_id=int(doc1), fields=[low], report_period="Mar 2025")
    insert_extracted_values(conn, project_id=project_id, document_id=int(doc2), fields=[high], report_period="Mar 2025")
    rebuild_project_timeline(conn, project_id)

    rows = fetch_historical_performance(conn, project_id)
    match = next(r for r in rows if r["period_year"] == 2025 and r["period_month"] == 3)
    assert float(match["confidence"]) == 0.99
    assert match["source_pdf_filename"] == "q1_v2.pdf"
