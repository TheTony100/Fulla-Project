from __future__ import annotations

from extraction.models import ExtractedField, ExtractionException

REQUIRED_FIELDS = frozenset({"report_month", "monthly_net_return", "aum_or_nav"})

TABLE_REQUIRED_FIELDS = frozenset({"monthly_net_return", "ytd_return"})

LOW_CONFIDENCE_THRESHOLD = 0.72


def field_to_audit_record(field: ExtractedField) -> dict[str, object]:
    return {
        "field_name": field.field_name,
        "value": field.extracted_value,
        "source_pdf": field.source_pdf_filename,
        "source_page": field.source_page,
        "source_table": field.source_table,
        "source_section_name": field.source_section_name,
        "matched_row_label": field.matched_row_label,
        "matched_column_label": field.matched_column_label,
        "original_snippet": field.snippet,
        "confidence": field.confidence,
        "review_status": field.review_status,
    }


def build_audit_trail(fields: list[ExtractedField]) -> list[dict[str, object]]:
    return [field_to_audit_record(f) for f in fields]


def collect_exceptions(
    fields: list[ExtractedField],
    *,
    filename: str,
) -> list[ExtractionException]:
    by_name = {f.field_name: f for f in fields}
    exceptions: list[ExtractionException] = []

    for required in sorted(REQUIRED_FIELDS):
        if required not in by_name:
            exceptions.append(
                ExtractionException(
                    field_name=required,
                    exception_type="missing_field",
                    message=f"Required field '{required}' was not extracted.",
                    source_pdf_filename=filename,
                )
            )

    for field in fields:
        if field.confidence < LOW_CONFIDENCE_THRESHOLD:
            exceptions.append(
                ExtractionException(
                    field_name=field.field_name,
                    exception_type="low_confidence",
                    message=f"Confidence {field.confidence:.3f} is below threshold {LOW_CONFIDENCE_THRESHOLD}.",
                    source_pdf_filename=filename,
                )
            )
        if field.review_status == "needs_review":
            exceptions.append(
                ExtractionException(
                    field_name=field.field_name,
                    exception_type="needs_review",
                    message="Extracted value flagged for human review.",
                    source_pdf_filename=filename,
                )
            )
        if field.field_name in TABLE_REQUIRED_FIELDS:
            if not field.source_table or not field.matched_row_label or not field.matched_column_label:
                exceptions.append(
                    ExtractionException(
                        field_name=field.field_name,
                        exception_type="missing_table_evidence",
                        message="Performance value lacks table row/column provenance.",
                        source_pdf_filename=filename,
                    )
                )

    monthly_values = [f.extracted_value for f in fields if f.field_name == "monthly_net_return"]
    if len(set(monthly_values)) > 1:
        exceptions.append(
            ExtractionException(
                field_name="monthly_net_return",
                exception_type="ambiguous_match",
                message="Multiple distinct monthly return values detected.",
                source_pdf_filename=filename,
            )
        )

    return exceptions
