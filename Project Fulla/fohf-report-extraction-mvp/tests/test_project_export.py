from __future__ import annotations

import io
from pathlib import Path
import shutil

import pandas as pd
import pytest

from database.db import get_connection, init_db
from export.project_exporter import build_project_workbook_bytes
from projects.pipeline import extract_document_for_project
from projects.store import create_project

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed_pdfs"


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.sqlite"
    connection = get_connection(db_path)
    init_db(connection)
    return connection


@pytest.fixture
def sample_pdf_copy(tmp_path):
    if not DATA_DIR.exists():
        pytest.skip("No sample PDF directory")
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        pytest.skip("No sample PDFs")
    dest = tmp_path / pdfs[0].name
    shutil.copy(pdfs[0], dest)
    return dest


def test_project_workbook_sheets(conn, sample_pdf_copy):
    project_id = create_project(conn, name="Export Test")
    extract_document_for_project(conn, project_id=project_id, pdf_path=sample_pdf_copy)
    data = build_project_workbook_bytes(conn, project_id)
    xl = pd.ExcelFile(io.BytesIO(data))
    assert "Project Summary" in xl.sheet_names
    assert "Performance Timeline" in xl.sheet_names
    assert "Fund Metrics" in xl.sheet_names
    assert "Audit Trail" in xl.sheet_names
