from __future__ import annotations

import re

from extraction.models import ExtractedField
from extraction.pdf_utils import snippet_around

_ATTRIBUTION_SECTION = re.compile(
    r"(?i)\b(?:attribution|top\s+5\s+winners|top\s+5\s+losers|long\s+attribution|short\s+attribution)\b"
)

_ATTRIBUTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("attribution_long", re.compile(r"(?i)\bLong\s+Attribution\b[^\n%]{0,30}([-+]?\d+(?:\.\d+)?)\s*%"), "Long Attribution"),
    ("attribution_short", re.compile(r"(?i)\bShort\s+Attribution\b[^\n%]{0,30}([-+]?\d+(?:\.\d+)?)\s*%"), "Short Attribution"),
    ("attribution_top_winners", re.compile(r"(?i)\bTop\s+5\s+Winners\b[^\n%]{0,30}([-+]?\d+(?:\.\d+)?)\s*%"), "Top 5 Winners"),
    ("attribution_top_losers", re.compile(r"(?i)\bTop\s+5\s+Losers\b[^\n%]{0,30}([-+]?\d+(?:\.\d+)?)\s*%"), "Top 5 Losers"),
]


def extract_attribution_fields(
    pages: list[tuple[int, str]],
    filename: str,
) -> list[ExtractedField]:
    results: list[ExtractedField] = []
    seen: set[str] = set()

    for page_no, text in pages:
        if page_no > 15:
            break
        if not _ATTRIBUTION_SECTION.search(text):
            continue

        for field_name, pattern, label in _ATTRIBUTION_PATTERNS:
            if field_name in seen:
                continue
            for m in pattern.finditer(text):
                raw = m.group(1)
                value = f"{raw}%" if not raw.endswith("%") else raw
                seen.add(field_name)
                results.append(
                    ExtractedField(
                        field_name=field_name,
                        extracted_value=value,
                        source_pdf_filename=filename,
                        source_page=page_no,
                        snippet=snippet_around(text, m.start(), m.end())[:500],
                        confidence=0.84,
                        review_status="needs_review",
                        source_table="Attribution",
                        source_section_name="Attribution",
                        matched_row_label=label,
                        matched_column_label="Value",
                    )
                )
                break
    return results
