from __future__ import annotations

from pathlib import Path

import pytest

from extraction.audit_trail import collect_exceptions
from extraction.monthly_extract import extract_monthly_fields
from export.excel_exporter import build_workbook_bytes

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed_pdfs"
MYDA_MAY = DATA_DIR / "MYDA Advantage Tear Sheet - May 2025.pdf"
MYDA_JULY = DATA_DIR / "MYDA Advantage Tear Sheet - July 2025 (1).pdf"
EVR_FEB = DATA_DIR / "2026.02 EVR Research Performance Summary.pdf (SECURED).pdf"


def _field(fields, name: str):
    return next((f for f in fields if f.field_name == name), None)


@pytest.mark.skipif(not MYDA_MAY.exists(), reason="MYDA May sample PDF not available")
class TestMYDAMay2025:
    @pytest.fixture(scope="class")
    def fields(self):
        return extract_monthly_fields(MYDA_MAY)

    def test_monthly_return_not_incentive_fee(self, fields):
        monthly = _field(fields, "monthly_net_return")
        assert monthly is not None, "Expected monthly return from performance table"
        assert monthly.extracted_value != "20%"
        assert monthly.extracted_value == "0.72%"

    def test_aum(self, fields):
        aum = _field(fields, "aum_or_nav")
        assert aum is not None
        assert aum.extracted_value == "$538M"

    def test_report_month(self, fields):
        report_month = _field(fields, "report_month")
        assert report_month is not None
        assert report_month.extracted_value == "May 2025"

    def test_monthly_return_table_provenance(self, fields):
        monthly = _field(fields, "monthly_net_return")
        assert monthly is not None
        assert "performance" in monthly.source_section_name.lower()
        assert monthly.matched_row_label == "2025"
        assert monthly.matched_column_label == "MAY"
        assert monthly.source_table
        assert monthly.review_status == "ok"

    def test_no_fee_snippet_in_monthly_return(self, fields):
        monthly = _field(fields, "monthly_net_return")
        assert monthly is not None
        assert "2/20" not in monthly.snippet
        assert "incentive fee" not in monthly.snippet.lower()


@pytest.mark.skipif(not MYDA_JULY.exists(), reason="MYDA July sample PDF not available")
def test_myda_july_monthly_not_twenty_percent():
    fields = extract_monthly_fields(MYDA_JULY)
    monthly = _field(fields, "monthly_net_return")
    if monthly is not None:
        assert monthly.extracted_value != "20%"


@pytest.mark.skipif(not EVR_FEB.exists(), reason="EVR sample PDF not available")
def test_evr_monthly_from_table():
    fields = extract_monthly_fields(EVR_FEB)
    monthly = _field(fields, "monthly_net_return")
    assert monthly is not None
    assert monthly.extracted_value == "2.8%"
    assert monthly.matched_row_label == "2026"
    assert monthly.matched_column_label == "FEB"
    assert "Monthly Net Returns" in monthly.source_section_name or monthly.source_table


def test_excel_workbook_has_required_sheets():
    if not MYDA_MAY.exists():
        pytest.skip("MYDA May sample PDF not available")
    fields = extract_monthly_fields(MYDA_MAY)
    data = build_workbook_bytes(fields)
    import io

    import pandas as pd

    xl = pd.ExcelFile(io.BytesIO(data))
    assert set(xl.sheet_names) >= {
        "Summary",
        "Monthly Returns",
        "AUM_NAV",
        "Exposure",
        "Attribution",
        "Audit Trail",
        "Exceptions",
    }


def test_exceptions_include_missing_when_no_monthly():
    from extraction.models import ExtractedField

    fields = [
        ExtractedField(
            field_name="report_month",
            extracted_value="May 2025",
            source_pdf_filename="x.pdf",
            source_page=1,
            snippet="May 2025",
            confidence=0.9,
            review_status="ok",
        )
    ]
    exc = collect_exceptions(fields, filename="x.pdf")
    assert any(e.exception_type == "missing_field" and e.field_name == "monthly_net_return" for e in exc)
