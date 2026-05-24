from __future__ import annotations

import re

from extraction.models import ExtractedField
from extraction.pdf_utils import line_for_match, norm_whitespace, snippet_around

_AUM_SECTION = re.compile(r"(?i)\b(?:fund\s+information|firm\s+information|fund\s+summary)\b")

_AUM_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    (
        "fund_aum_dollar_suffix",
        re.compile(r"(?i)\b(?:Fund\s+)?AUM\b[^\n$]{0,100}\$\s*([\d,]+(?:\.\d+)?)\s*(million|mn|[MmBb])\b"),
        0.94,
    ),
    (
        "aum_colon_dollar_suffix",
        re.compile(r"(?i)\bAUM\s*:\s*\$\s*([\d,]+(?:\.\d+)?)\s*([MmBb])\b"),
        0.93,
    ),
    (
        "assets_under_management",
        re.compile(
            r"(?i)\bAssets\s+Under\s+Management\b[^\n$]{0,100}\$\s*([\d,]+(?:\.\d+)?)\s*(million|mn|[MmBb])\b"
        ),
        0.91,
    ),
    (
        "nav_dollar_suffix",
        re.compile(r"(?i)\bNAV\b[^\n$]{0,100}\$\s*([\d,]+(?:\.\d+)?)\s*(million|mn|[MmBb])\b"),
        0.9,
    ),
]

_FEE_CONTEXT = re.compile(r"(?i)(?:management\s+fee|incentive\s+fee|minimum\s+subscription|lockup|redemptions)")


def _normalize_aum_display(num: str, suffix: str) -> str:
    suf = suffix.lower()
    if suf in ("billion", "bn", "b"):
        letter = "B"
    else:
        letter = "M"
    return f"${num.replace(',', '')}{letter}"


def extract_aum_nav(
    pages: list[tuple[int, str]],
    filename: str,
) -> ExtractedField | None:
    candidates: list[tuple[float, ExtractedField]] = []

    for page_no, text in pages:
        if page_no > 15:
            break
        for pname, pattern, base_conf in _AUM_PATTERNS:
            for m in pattern.finditer(text):
                line = line_for_match(text, m.start(), m.end())
                if _FEE_CONTEXT.search(line) and "aum" not in line.lower():
                    continue
                num = m.group(1)
                suffix = m.group(2)
                value = _normalize_aum_display(num, suffix)
                section = "Fund Information"
                if _AUM_SECTION.search(text[max(0, m.start() - 400) : m.start()]):
                    section = "Fund Information"
                conf = base_conf
                review = "ok"
                if page_no > 3:
                    conf *= 0.9
                    review = "needs_review"
                candidates.append(
                    (
                        conf,
                        ExtractedField(
                            field_name="aum_or_nav",
                            extracted_value=value,
                            source_pdf_filename=filename,
                            source_page=page_no,
                            snippet=snippet_around(text, m.start(), m.end())[:500],
                            confidence=round(conf, 3),
                            review_status=review,
                            source_table=section,
                            source_section_name=section,
                            matched_row_label=pname,
                            matched_column_label="AUM",
                        ),
                    )
                )

    if not candidates:
        return None
    candidates.sort(key=lambda t: -t[0])
    return candidates[0][1]
