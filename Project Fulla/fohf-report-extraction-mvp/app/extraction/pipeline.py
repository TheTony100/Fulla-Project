from __future__ import annotations

from pathlib import Path

from extraction.attribution_extractor import extract_attribution_fields
from extraction.audit_trail import build_audit_trail, collect_exceptions
from extraction.aum_nav_extractor import extract_aum_nav
from extraction.exposure_extractor import extract_exposure_fields
from extraction.models import ExtractionPipelineResult, ExtractedField
from extraction.pdf_utils import load_page_texts
from extraction.performance_table_extractor import extract_performance_fields
from extraction.report_metadata_extractor import extract_report_metadata


def run_extraction_pipeline(pdf_path: Path) -> ExtractionPipelineResult:
    filename = pdf_path.name
    pages = load_page_texts(pdf_path)

    metadata_fields = extract_report_metadata(pdf_path, pages, filename)
    report_month_value = next((f.extracted_value for f in metadata_fields if f.field_name == "report_month"), None)

    performance_fields = extract_performance_fields(
        pages,
        report_month_value=report_month_value,
        filename=filename,
    )
    aum_field = extract_aum_nav(pages, filename)
    exposure_fields = extract_exposure_fields(pages, filename)
    attribution_fields = extract_attribution_fields(pages, filename)

    all_fields: list[ExtractedField] = []
    all_fields.extend(metadata_fields)
    all_fields.extend(performance_fields)
    if aum_field:
        all_fields.append(aum_field)
    all_fields.extend(exposure_fields)
    all_fields.extend(attribution_fields)

    exceptions = collect_exceptions(all_fields, filename=filename)
    audit_records = build_audit_trail(all_fields)

    return ExtractionPipelineResult(
        fields=all_fields,
        exceptions=exceptions,
        audit_records=audit_records,
    )


def extract_all_fields(pdf_path: Path) -> list[ExtractedField]:
    return run_extraction_pipeline(pdf_path).fields
