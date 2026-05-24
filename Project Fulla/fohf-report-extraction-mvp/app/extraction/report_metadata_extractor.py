from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from extraction.models import ExtractedField
from extraction.pdf_utils import norm_whitespace, snippet_around
from extraction.rules import load_extraction_rules

_MONTH_YEAR_ANCHOR = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b",
    re.I,
)

_MANAGER_LINE_REJECT = re.compile(
    r"\b(?:MTD|QTD|YTD|CAGR|PERFORMANCE|INDEX|EXPOSURE)\b",
    re.IGNORECASE,
)
_MANAGER_PREFERRED = re.compile(
    r"\b(?:Fund|Capital|Partners?|Management|Opportunity|Advantage|LP|Ltd\.?)\b",
    re.IGNORECASE,
)
_LABELED_FUND_LINE = re.compile(
    r"(?im)^\s*(?:Fund\s+Name|Strategy\s+Name|Investment\s+Vehicle|Portfolio\s+Name)\s*:",
)


def parse_report_period(value: str) -> tuple[int, int] | None:
    """Return (year, month_number) from strings like 'May 2025'."""
    if not value:
        return None
    text = norm_whitespace(value)
    m = re.search(
        r"(?i)\b(January|February|March|April|May|June|July|August|September|October|November|December"
        r"|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b",
        text,
    )
    if not m:
        m2 = re.search(r"\b(\d{1,2})/(\d{4})\b", text)
        if m2:
            return int(m2.group(2)), int(m2.group(1))
        return None
    month_token = m.group(1).lower()[:3]
    month_map = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month_num = month_map.get(month_token)
    if month_num is None:
        return None
    return int(m.group(2)), month_num


def parse_report_period_from_filename(filename: str) -> tuple[int, int] | None:
    stem = Path(filename).stem
    return parse_report_period(stem)


def _match_value(m: re.Match[str], pattern_name: str) -> str | None:
    gd = m.groupdict()
    if "value" in gd and gd["value"]:
        return gd["value"].strip()
    if pattern_name == "mm_yyyy" and m.lastindex and m.lastindex >= 2:
        mm, yyyy = m.group(1), m.group(2)
        return f"{int(mm):02d}/{yyyy}"
    if m.lastindex and m.lastindex >= 1:
        return m.group(1).strip()
    if pattern_name in ("month_year_words", "abbreviated_month_year"):
        return m.group(0).strip()
    return None


def _extract_labeled_field(
    pages: list[tuple[int, str]],
    cfg: dict[str, Any],
    *,
    field_name: str,
    filename: str,
    section_name: str,
) -> ExtractedField | None:
    max_head = int(cfg.get("max_pages_head") or 50)
    patterns = cfg.get("patterns") or []
    candidates: list[tuple[int, int, float, str, re.Match[str], str]] = []

    for page_no, text in pages:
        if page_no > max_head:
            break
        if not text.strip():
            continue
        for pat in patterns:
            if not isinstance(pat, dict):
                continue
            regex = pat.get("regex")
            if not regex:
                continue
            try:
                rx = re.compile(str(regex))
            except re.error:
                continue
            pname = str(pat.get("name") or "pattern")
            base_c = float(pat.get("confidence_base") or 0.6)
            for m in rx.finditer(text):
                val = _match_value(m, pname)
                if val is None or not val.strip():
                    continue
                line_idx = text.count("\n", 0, m.start())
                candidates.append((page_no, line_idx, base_c, pname, m, text))

    if not candidates:
        return None

    candidates.sort(key=lambda t: (-t[2], t[0], t[1]))
    page_no, _line_idx, base_c, pname, m, text_for_page = candidates[0]
    raw_val = _match_value(m, pname) or ""
    normalized_value = norm_whitespace(raw_val)

    conf = float(base_c)
    review = "ok"
    if page_no != 1:
        conf *= 0.9
        review = "needs_review"
    if pname in ("month_year_words", "abbreviated_month_year", "mm_yyyy"):
        conf *= 0.92
    conf = max(0.0, min(1.0, round(conf, 3)))
    if conf < 0.72:
        review = "needs_review"

    return ExtractedField(
        field_name=field_name,
        extracted_value=normalized_value,
        source_pdf_filename=filename,
        source_page=page_no,
        snippet=snippet_around(text_for_page, m.start(), m.end())[:500],
        confidence=conf,
        review_status=review,
        source_section_name=section_name,
        matched_row_label=pname,
    )


def extract_report_month(
    pages: list[tuple[int, str]],
    filename: str,
    rules: dict[str, Any] | None = None,
) -> ExtractedField | None:
    rules = rules or load_extraction_rules()
    cfg = (rules.get("fields") or {}).get("report_month") or {}
    field = _extract_labeled_field(
        pages,
        cfg,
        field_name="report_month",
        filename=filename,
        section_name="Report Header",
    )
    if field:
        return field

    period = parse_report_period_from_filename(filename)
    if period is None:
        return None
    year, month_num = period
    month_names = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    value = f"{month_names[month_num]} {year}"
    return ExtractedField(
        field_name="report_month",
        extracted_value=value,
        source_pdf_filename=filename,
        source_page=1,
        snippet=f"Derived from filename: {filename}"[:500],
        confidence=0.62,
        review_status="needs_review",
        source_section_name="Filename",
        matched_row_label=str(year),
        matched_column_label=month_names[month_num],
    )


def _manager_line_rejected(raw: str) -> bool:
    t = norm_whitespace(raw).strip()
    if len(t) < 4 or len(t) > 130:
        return True
    if _MANAGER_LINE_REJECT.search(t):
        return True
    if len(re.findall(r"%", t)) >= 2:
        return True
    nums = re.findall(r"(?<![\w.)])(-?\d+(?:\.\d+)?)", t.replace(",", ""))
    if len(nums) >= 4:
        return True
    if len(nums) >= 2 and "%" in t:
        return True
    digit_ratio = sum(c.isdigit() for c in t) / max(len(t), 1)
    if digit_ratio > 0.33:
        return True
    return False


def _manager_clean_value(text: str) -> str:
    return norm_whitespace(
        re.sub(
            r"(?i)^\s*(?:Fund\s+Name|Strategy\s+Name|Investment\s+Vehicle|Portfolio\s+Name)\s*:\s*",
            "",
            text,
        )
    ).strip()


def _fund_name_from_filename_stem(filename: str) -> str | None:
    stem = Path(filename).stem.strip()
    if not stem:
        return None
    s = stem
    s = re.sub(r"^(?:19|20)\d{2}[-_/]\d{1,2}[-_/]\d{1,2}\s*[-–—_:,\s]+\s*", "", s)
    s = re.sub(
        r"\s*[-–—]\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\s*[-–—]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\s*$",
        "",
        s,
        flags=re.I,
    )
    s = norm_whitespace(s).strip(" -–—_")
    return s if len(s) >= 3 else None


def _collect_line_boxes(pdf_path: Path) -> tuple[list[dict[str, Any]], float, float]:
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(0)
        pw, ph = float(page.rect.width), float(page.rect.height)
        td = page.get_text("dict")
        lines_out: list[dict[str, Any]] = []
        for block in td.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                parts: list[str] = []
                xs0: list[float] = []
                ys0: list[float] = []
                xs1: list[float] = []
                ys1: list[float] = []
                for span in line.get("spans", []):
                    tx = (span.get("text") or "").strip()
                    if not tx:
                        continue
                    parts.append(tx)
                    bb = span["bbox"]
                    xs0.append(bb[0])
                    ys0.append(bb[1])
                    xs1.append(bb[2])
                    ys1.append(bb[3])
                if not parts:
                    continue
                lines_out.append(
                    {
                        "text": norm_whitespace(" ".join(parts)),
                        "x0": min(xs0),
                        "y0": min(ys0),
                        "x1": max(xs1),
                        "y1": max(ys1),
                    }
                )
        return lines_out, pw, ph
    finally:
        doc.close()


def _manager_layout_pick(pdf_path: Path, filename: str) -> ExtractedField | None:
    try:
        lines, pw, ph = _collect_line_boxes(pdf_path)
    except Exception:
        return None
    if not lines or ph <= 1:
        return None

    month_y = None
    hits = [ln for ln in lines if _MONTH_YEAR_ANCHOR.search(ln["text"])]
    if hits:
        hits.sort(key=lambda ln: (ln["y0"], ln["x0"]))
        ln0 = hits[0]
        month_y = ((ln0["y0"] + ln0["y1"]) / 2.0) / ph

    best_score = -1.0
    best_text = ""
    for ln in lines:
        cleaned = _manager_clean_value(ln.get("text") or "")
        if len(cleaned) < 4 or _manager_line_rejected(cleaned):
            continue
        if not (_MANAGER_PREFERRED.search(cleaned) or re.search(r",\s*LP\b", cleaned)):
            continue
        ty_mid = ((ln["y0"] + ln["y1"]) / 2.0) / ph
        score = max(0.0, 0.55 - ty_mid) * 140.0
        if month_y is not None and 0.0 <= ty_mid - month_y <= 0.16:
            score += 72.0
        if score > best_score:
            best_score = score
            best_text = cleaned

    if best_score < 0 or not best_text:
        return None

    conf = max(0.0, min(0.88, round(0.42 + min(best_score / 520.0, 0.4), 3)))
    return ExtractedField(
        field_name="manager_name",
        extracted_value=best_text,
        source_pdf_filename=filename,
        source_page=1,
        snippet=best_text[:500],
        confidence=conf,
        review_status="needs_review",
        source_section_name="Page Header",
    )


def extract_manager_name(
    pdf_path: Path,
    pages: list[tuple[int, str]],
    filename: str,
    rules: dict[str, Any] | None = None,
) -> ExtractedField | None:
    rules = rules or load_extraction_rules()
    cfg = (rules.get("fields") or {}).get("manager_name") or {}
    max_head = int(cfg.get("max_pages_head") or 3)
    patterns = cfg.get("patterns") or []

    for page_no, text in pages:
        if page_no > max_head:
            break
        for pat in patterns:
            regex = pat.get("regex")
            if not regex:
                continue
            rx = re.compile(str(regex))
            pname = str(pat.get("name") or "pattern")
            base_c = float(pat.get("confidence_base") or 0.6)
            for m in rx.finditer(text):
                val = _match_value(m, pname)
                if not val or _manager_line_rejected(val):
                    continue
                cleaned = _manager_clean_value(val)
                return ExtractedField(
                    field_name="manager_name",
                    extracted_value=cleaned,
                    source_pdf_filename=filename,
                    source_page=page_no,
                    snippet=snippet_around(text, m.start(), m.end())[:500],
                    confidence=base_c,
                    review_status="ok" if base_c >= 0.72 else "needs_review",
                    source_section_name="Labeled Field",
                    matched_row_label=pname,
                )

    layout = _manager_layout_pick(pdf_path, filename)
    if layout:
        return layout

    fb = _fund_name_from_filename_stem(filename)
    if fb and not _manager_line_rejected(fb):
        return ExtractedField(
            field_name="manager_name",
            extracted_value=_manager_clean_value(fb),
            source_pdf_filename=filename,
            source_page=1,
            snippet=f"Filename fallback: {filename}"[:500],
            confidence=0.46,
            review_status="needs_review",
            source_section_name="Filename",
        )
    return None


def extract_report_metadata(
    pdf_path: Path,
    pages: list[tuple[int, str]],
    filename: str,
    rules: dict[str, Any] | None = None,
) -> list[ExtractedField]:
    rules = rules or load_extraction_rules()
    out: list[ExtractedField] = []
    report_month = extract_report_month(pages, filename, rules)
    if report_month:
        out.append(report_month)
    manager = extract_manager_name(pdf_path, pages, filename, rules)
    if manager:
        out.append(manager)
    return out
