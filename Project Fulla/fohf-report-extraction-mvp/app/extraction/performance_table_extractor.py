from __future__ import annotations

import re

from extraction.models import ExtractedField, PerformanceTimelinePoint
from extraction.pdf_utils import norm_whitespace
from extraction.report_metadata_extractor import parse_report_period, parse_report_period_from_filename

_PERFORMANCE_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Monthly Performance History", re.compile(r"(?i)\bmonthly\s+performance\s+history\b")),
    ("Monthly Net Returns", re.compile(r"(?i)\bmonthly\s+net\s+returns?\b")),
    ("Fund Performance", re.compile(r"(?i)\bfund\s+performance\b")),
    ("Monthly Returns", re.compile(r"(?i)\bmonthly\s+returns?\b")),
]

_MONTH_TOKEN = re.compile(
    r"(?i)\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
)

_MONTH_CANONICAL = {
    "jan": "JAN",
    "feb": "FEB",
    "mar": "MAR",
    "apr": "APR",
    "may": "MAY",
    "jun": "JUN",
    "jul": "JUL",
    "aug": "AUG",
    "sep": "SEP",
    "sept": "SEP",
    "oct": "OCT",
    "nov": "NOV",
    "dec": "DEC",
}

_MONTH_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_FEE_DISQUALIFIERS = re.compile(
    r"(?i)(?:incentive\s+fee|management\s+fee|\(\s*2\s*/\s*20\s*%\s*\)|"
    r"fee\s+\d+\s*%|payable\s+quarterly|of\s+profits|net\s+of\s+all\s+fees)"
)

_YEAR_ROW = re.compile(r"^\s*(\d{4})\s+(.+)$")
_VALUE_TOKEN = re.compile(r"[-+]?\d+(?:\.\d+)?%?")


def _month_key(token: str) -> str:
    return token.lower()[:4].rstrip(".")[:3]


def _find_month_columns(header_line: str) -> list[tuple[str, int]]:
    """Return ordered month labels found in a header line."""
    cols: list[tuple[str, int]] = []
    seen: set[str] = set()
    for m in _MONTH_TOKEN.finditer(header_line):
        key = _month_key(m.group(1))
        canon = _MONTH_CANONICAL.get(key)
        if not canon or canon in seen:
            continue
        seen.add(canon)
        cols.append((canon, m.start()))
    return cols


_SECTION_PRIORITY = {
    "Monthly Performance History": 100,
    "Monthly Net Returns": 95,
    "Fund Performance": 70,
    "Monthly Returns": 65,
}


def _locate_sections(pages: list[tuple[int, str]]) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    for page_no, text in pages:
        if page_no > 15:
            break
        for section_name, pattern in _PERFORMANCE_SECTION_PATTERNS:
            for m in pattern.finditer(text):
                start = m.start()
                window = text[start : start + 4500]
                sections.append(
                    {
                        "page": page_no,
                        "section_name": section_name,
                        "matched_label": m.group(0),
                        "window": window,
                        "full_text": text,
                        "start": start,
                    }
                )
    sections.sort(key=_section_sort_key)
    return sections


def _section_sort_key(section: dict[str, object]) -> tuple[int, int]:
    name = str(section["section_name"])
    return (-_SECTION_PRIORITY.get(name, 50), int(section["page"]))


def _find_header_and_rows(window: str) -> tuple[str, list[str], list[str]] | None:
    lines = [ln.strip() for ln in window.splitlines() if ln.strip()]
    header_idx = -1
    month_cols: list[tuple[str, int]] = []
    for i, line in enumerate(lines[:40]):
        cols = _find_month_columns(line)
        if len(cols) >= 4:
            header_idx = i
            month_cols = cols
            break
    if header_idx < 0:
        return None

    header_line = lines[header_idx]
    year_rows: list[str] = []
    for line in lines[header_idx + 1 : header_idx + 35]:
        if _YEAR_ROW.match(line):
            year_rows.append(line)
        elif year_rows and not re.match(r"^\s*\d{4}\b", line):
            break
    if not year_rows:
        return None
    return header_line, [c[0] for c in month_cols], year_rows


def _values_for_year_row(row_line: str) -> tuple[str, list[str]] | None:
    m = _YEAR_ROW.match(row_line.strip())
    if not m:
        return None
    year = m.group(1)
    rest = m.group(2)
    values = _VALUE_TOKEN.findall(rest)
    return year, values


def _format_percent(raw: str) -> str:
    s = raw.strip().replace(",", "")
    if s.endswith("%"):
        return s
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", s):
        return f"{s}%"
    return s


def _pick_month_value(
    *,
    year_rows: list[str],
    month_labels: list[str],
    target_year: int,
    target_month: int,
) -> tuple[str, str, str, str] | None:
    target_month_label = None
    for label in month_labels:
        key = label.lower()[:3]
        if _MONTH_NUM.get(key) == target_month:
            target_month_label = label
            break
    if target_month_label is None:
        return None

    month_index = month_labels.index(target_month_label)
    for row in year_rows:
        parsed = _values_for_year_row(row)
        if not parsed:
            continue
        year, values = parsed
        if int(year) != target_year:
            continue
        if month_index >= len(values):
            return None
        return year, target_month_label, values[month_index], row
    return None


def _pick_ytd_value(
    *,
    header_line: str,
    year_rows: list[str],
    target_year: int,
) -> tuple[str, str] | None:
    if not re.search(r"(?i)\bytd\b", header_line):
        return None
    for row in year_rows:
        parsed = _values_for_year_row(row)
        if not parsed:
            continue
        year, values = parsed
        if int(year) != target_year or not values:
            continue
        for val in reversed(values):
            if val.endswith("%"):
                return year, val
        return year, _format_percent(values[-1])
    return None


def _build_field(
    *,
    field_name: str,
    value: str,
    filename: str,
    page: int,
    section_name: str,
    row_label: str,
    column_label: str,
    snippet: str,
    confidence: float,
    review_status: str,
) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        extracted_value=value,
        source_pdf_filename=filename,
        source_page=page,
        snippet=snippet[:500],
        confidence=confidence,
        review_status=review_status,
        source_table=section_name,
        source_section_name=section_name,
        matched_row_label=row_label,
        matched_column_label=column_label,
    )


_MONTHLY_RETURN_TABLE_ONLY = "Monthly Performance History"


def _locate_performance_history_sections(pages: list[tuple[int, str]]) -> list[dict[str, object]]:
    """Only sections explicitly labeled Monthly Performance History."""
    sections: list[dict[str, object]] = []
    pattern = _PERFORMANCE_SECTION_PATTERNS[0][1]  # Monthly Performance History regex
    for page_no, text in pages:
        if page_no > 15:
            break
        for m in pattern.finditer(text):
            start = m.start()
            window = text[start : start + 4500]
            sections.append(
                {
                    "page": page_no,
                    "section_name": _MONTHLY_RETURN_TABLE_ONLY,
                    "matched_label": m.group(0),
                    "window": window,
                    "full_text": text,
                    "start": start,
                }
            )
    return sections


def _needs_review_monthly_field(filename: str, *, reason: str) -> ExtractedField:
    return ExtractedField(
        field_name="monthly_net_return",
        extracted_value="needs_review",
        source_pdf_filename=filename,
        source_page=0,
        snippet=reason[:500],
        confidence=0.0,
        review_status="needs_review",
        source_table="",
        source_section_name="",
        matched_row_label="",
        matched_column_label="",
    )


def extract_monthly_return_from_table(
    pages: list[tuple[int, str]],
    *,
    report_month_value: str | None,
    filename: str,
) -> ExtractedField | None:
    """Monthly return ONLY from Monthly Performance History table."""
    period = parse_report_period(report_month_value or "") or parse_report_period_from_filename(filename)
    if period is None:
        return _needs_review_monthly_field(
            filename,
            reason="Could not determine report month for Monthly Performance History lookup.",
        )
    target_year, target_month = period

    sections = _locate_performance_history_sections(pages)
    if not sections:
        return _needs_review_monthly_field(
            filename,
            reason="Monthly Performance History table not found in PDF.",
        )

    best: ExtractedField | None = None
    for section in sections:
        window = str(section["window"])
        page = int(section["page"])
        section_name = str(section["section_name"])

        parsed = _find_header_and_rows(window)
        if not parsed:
            continue
        header_line, month_labels, year_rows = parsed

        picked = _pick_month_value(
            year_rows=year_rows,
            month_labels=month_labels,
            target_year=target_year,
            target_month=target_month,
        )
        if not picked:
            continue

        year, month_label, raw_value, row_line = picked
        if _FEE_DISQUALIFIERS.search(row_line):
            continue
        if not _is_valid_return_cell(raw_value, row_line):
            continue

        formatted = _format_percent(raw_value)
        conf = 0.94
        review = "ok"

        candidate = _build_field(
            field_name="monthly_net_return",
            value=formatted,
            filename=filename,
            page=page,
            section_name=_MONTHLY_RETURN_TABLE_ONLY,
            row_label=year,
            column_label=month_label,
            snippet=norm_whitespace(f"{section_name} | {header_line} | {row_line}"),
            confidence=conf,
            review_status=review,
        )
        if best is None or candidate.confidence > best.confidence:
            best = candidate

    if best is None:
        return _needs_review_monthly_field(
            filename,
            reason="Monthly Performance History found but report-month cell could not be parsed.",
        )
    return best


def extract_ytd_return_from_table(
    pages: list[tuple[int, str]],
    *,
    report_month_value: str | None,
    filename: str,
) -> ExtractedField | None:
    period = parse_report_period(report_month_value or "") or parse_report_period_from_filename(filename)
    if period is None:
        return None
    target_year, _target_month = period

    for section in _locate_sections(pages):
        window = str(section["window"])
        page = int(section["page"])
        section_name = str(section["section_name"])
        parsed = _find_header_and_rows(window)
        if not parsed:
            continue
        header_line, _month_labels, year_rows = parsed
        ytd = _pick_ytd_value(header_line=header_line, year_rows=year_rows, target_year=target_year)
        if not ytd:
            continue
        year, raw_value = ytd
        return _build_field(
            field_name="ytd_return",
            value=_format_percent(raw_value),
            filename=filename,
            page=page,
            section_name=section_name,
            row_label=year,
            column_label="YTD",
            snippet=norm_whitespace(f"{section_name} | YTD | {year} {raw_value}"),
            confidence=0.9,
            review_status="ok",
        )
    return None


def _parse_return_pct(raw: str) -> float | None:
    s = raw.strip().replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _period_label(year: int, month_num: int) -> str:
    names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if 1 <= month_num <= 12:
        return f"{names[month_num]} {year}"
    return f"{year}-{month_num:02d}"


def _is_valid_return_cell(raw: str, row_line: str) -> bool:
    s = raw.strip().replace(",", "")
    if s in ("-", "—", ""):
        return False
    if _FEE_DISQUALIFIERS.search(row_line):
        return False
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?", s):
        return False
    num = s.rstrip("%")
    try:
        val = float(num)
    except ValueError:
        return False
    if abs(val) > 100:
        return False
    # Reject bare incentive-fee style integers (e.g. 20 from 2/20%) on fee lines
    if val == 20 and "." not in num and re.search(r"(?i)(?:fee|2\s*/\s*20|incentive|management)", row_line):
        return False
    return True


def extract_performance_timeline(
    pages: list[tuple[int, str]],
    *,
    filename: str,
) -> list[PerformanceTimelinePoint]:
    """Extract month/year cells only from Monthly Performance History tables."""
    points: list[PerformanceTimelinePoint] = []
    best_by_period: dict[tuple[int, int], PerformanceTimelinePoint] = {}

    for section in _locate_performance_history_sections(pages):
        window = str(section["window"])
        page = int(section["page"])
        section_name = str(section["section_name"])
        parsed = _find_header_and_rows(window)
        if not parsed:
            continue
        header_line, month_labels, year_rows = parsed

        for row_line in year_rows:
            if _FEE_DISQUALIFIERS.search(row_line):
                continue
            parsed_row = _values_for_year_row(row_line)
            if not parsed_row:
                continue
            year_str, values = parsed_row
            year = int(year_str)

            for idx, month_label in enumerate(month_labels):
                if idx >= len(values):
                    break
                raw = values[idx]
                if not _is_valid_return_cell(raw, row_line):
                    continue
                month_num = _MONTH_NUM.get(month_label.lower()[:3])
                if not month_num:
                    continue
                key = (year, month_num)
                formatted = _format_percent(raw)
                conf = 0.94 if section_name == _MONTHLY_RETURN_TABLE_ONLY else 0.0
                candidate = PerformanceTimelinePoint(
                    period_year=year,
                    period_month=month_num,
                    period_label=_period_label(year, month_num),
                    return_value=formatted,
                    return_pct=_parse_return_pct(formatted),
                    source_pdf_filename=filename,
                    source_page=page,
                    snippet=norm_whitespace(f"{section_name} | {header_line} | {row_line}")[:500],
                    confidence=conf,
                    review_status="ok",
                    source_table=section_name,
                    source_section_name=section_name,
                    matched_row_label=year_str,
                    matched_column_label=month_label,
                )
                existing = best_by_period.get(key)
                if existing is None or candidate.confidence > existing.confidence:
                    best_by_period[key] = candidate
    return list(best_by_period.values())


def extract_performance_fields(
    pages: list[tuple[int, str]],
    *,
    report_month_value: str | None,
    filename: str,
) -> list[ExtractedField]:
    """Performance fields for project pipeline; monthly return is Performance History only."""
    out: list[ExtractedField] = []
    monthly = extract_monthly_return_from_table(
        pages,
        report_month_value=report_month_value,
        filename=filename,
    )
    if monthly:
        out.append(monthly)
    return out
