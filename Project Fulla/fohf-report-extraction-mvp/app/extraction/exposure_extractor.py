from __future__ import annotations

import re

from extraction.models import ExtractedField
from extraction.pdf_utils import norm_whitespace, snippet_around

_EXPOSURE_SECTION = re.compile(r"(?i)\b(?:historical\s+exposure|average\s+exposure|net\s+exposure|gross\s+exposure)\b")

_EXPOSURE_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("net_exposure", re.compile(r"(?i)\bNet\s+Exposure\b[^\n\d]{0,40}(\d{1,3})%"), "Net Exposure"),
    ("gross_exposure", re.compile(r"(?i)\bGross\s+Exposure\b[^\n\d]{0,40}(\d{1,3})%"), "Gross Exposure"),
    (
        "exposure_table_row",
        re.compile(r"(?i)\bLong\b[^\n%]{0,30}(\d{1,3})%[^\n]{0,40}\bShort\b[^\n%]{0,30}(\d{1,3})%"),
        "Exposure Table",
    ),
]


def extract_exposure_fields(
    pages: list[tuple[int, str]],
    filename: str,
) -> list[ExtractedField]:
    results: list[ExtractedField] = []
    seen: set[str] = set()

    for page_no, text in pages:
        if page_no > 15:
            break
        if not _EXPOSURE_SECTION.search(text):
            continue

        for pname, pattern, label in _EXPOSURE_PATTERNS:
            for m in pattern.finditer(text):
                if pname == "exposure_table_row":
                    long_val = m.group(1)
                    short_val = m.group(2)
                    pairs = [
                        ("exposure_long_pct", long_val, "Long"),
                        ("exposure_short_pct", short_val, "Short"),
                    ]
                else:
                    pairs = [(f"exposure_{pname}", m.group(1), label)]

                for field_name, raw, col_label in pairs:
                    if field_name in seen:
                        continue
                    seen.add(field_name)
                    value = f"{raw}%"
                    results.append(
                        ExtractedField(
                            field_name=field_name,
                            extracted_value=value,
                            source_pdf_filename=filename,
                            source_page=page_no,
                            snippet=snippet_around(text, m.start(), m.end())[:500],
                            confidence=0.82,
                            review_status="needs_review",
                            source_table="Exposure",
                            source_section_name="Historical Exposure",
                            matched_row_label=pname,
                            matched_column_label=col_label,
                        )
                    )
    return results
