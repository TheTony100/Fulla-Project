from __future__ import annotations

import io

import pandas as pd
import pytest
from openpyxl import load_workbook

from database.db import get_connection, init_db
from export.project_exporter import build_project_workbook_bytes
from projects.store import create_project, insert_extracted_values
from extraction.models import ExtractedField


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.sqlite"
    connection = get_connection(db_path)
    init_db(connection)
    return connection


def test_institutional_workbook_columns(conn):
    project_id = create_project(conn, name="Institutional Export")
    doc_id = conn.execute(
        """
        INSERT INTO project_documents (project_id, filename, path, document_type, upload_time, status, report_period)
        VALUES (?, 'test.pdf', '/tmp/test.pdf', 'report', '2025-01-01', 'processed', 'May 2025')
        """,
        (project_id,),
    ).lastrowid
    fields = [
        ExtractedField(
            field_name="monthly_return_2025_05",
            extracted_value="0.72%",
            source_pdf_filename="test.pdf",
            source_page=1,
            snippet="Monthly Performance History | 2025 | 0.72",
            confidence=0.94,
            review_status="ok",
            source_table="Monthly Performance History",
            source_section_name="Monthly Performance History",
            matched_row_label="2025",
            matched_column_label="MAY",
        ),
        ExtractedField(
            field_name="aum_or_nav",
            extracted_value="$538M",
            source_pdf_filename="test.pdf",
            source_page=1,
            snippet="Fund AUM $538M",
            confidence=0.94,
            review_status="ok",
            source_table="Fund Information",
            source_section_name="Fund Information",
            matched_row_label="fund_aum",
            matched_column_label="AUM",
        ),
        ExtractedField(
            field_name="attribution_long",
            extracted_value="1.5%",
            source_pdf_filename="test.pdf",
            source_page=1,
            snippet="Long Attribution 1.5%",
            confidence=0.84,
            review_status="needs_review",
            source_table="Attribution",
            source_section_name="Attribution",
            matched_row_label="long",
            matched_column_label="Long Attribution",
        ),
    ]
    insert_extracted_values(conn, project_id=project_id, document_id=int(doc_id), fields=fields, report_period="May 2025")
    from projects.timeline import rebuild_project_timeline

    rebuild_project_timeline(conn, project_id)

    data = build_project_workbook_bytes(conn, project_id)
    xl = pd.ExcelFile(io.BytesIO(data))
    assert "Project Summary" in xl.sheet_names
    assert "Performance Timeline" in xl.sheet_names
    assert "Fund Metrics" in xl.sheet_names
    assert "Attribution" in xl.sheet_names
    assert "Review Queue" in xl.sheet_names

    timeline = pd.read_excel(io.BytesIO(data), sheet_name="Performance Timeline")
    assert "Canonical Value" in timeline.columns
    assert timeline.iloc[0]["Net Return"] == "0.72%"
    assert timeline.iloc[0]["Confidence"] == "94%"
    assert "Source Snippet" not in timeline.columns

    attribution = pd.read_excel(io.BytesIO(data), sheet_name="Attribution")
    assert "Year" not in attribution.columns
    assert attribution.iloc[0]["Metric"] == "Long Attribution"
    assert attribution.iloc[0]["Confidence"] == "84%"
    assert attribution.iloc[0]["Review Status"] == "Needs Review"

    review = pd.read_excel(io.BytesIO(data), sheet_name="Review Queue")
    assert set(review["Issue Type"].dropna().unique()).issubset(
        {"Needs Review", "Low Confidence", "Missing Field"}
    )

    fund = pd.read_excel(io.BytesIO(data), sheet_name="Fund Metrics")
    assert fund.iloc[0]["Metric"] == "AUM / NAV"
    assert fund.iloc[0]["Confidence"] == "94%"

    trace = pd.read_excel(io.BytesIO(data), sheet_name="Source Traceability")
    monthly_row = trace[trace["Metric"] == "Monthly Return"].iloc[0]
    assert monthly_row["Year"] == 2025
    assert monthly_row["Month"] == "May"
    assert "Source Snippet" in trace.columns
    assert trace.columns.tolist().index("Source Snippet") > trace.columns.tolist().index("Value")

    summary = pd.read_excel(io.BytesIO(data), sheet_name="Project Summary", header=None)
    flat = summary.astype(str).values.flatten().tolist()
    assert "Data Quality Summary" in flat
    assert "Total Extracted Fields" in flat

    wb = load_workbook(io.BytesIO(data))
    assert wb["Exposure"].sheet_state == "hidden"
    assert wb["Source Traceability"].sheet_state == "hidden"
    assert wb["Project Summary"].sheet_state == "visible"
