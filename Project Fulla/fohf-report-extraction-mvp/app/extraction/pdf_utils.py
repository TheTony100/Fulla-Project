from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pdfplumber


def norm_whitespace(s: str) -> str:
    return " ".join(s.split())


def snippet_around(text: str, span_start: int, span_end: int, radius: int = 120) -> str:
    lo = max(0, span_start - radius)
    hi = min(len(text), span_end + radius)
    return norm_whitespace(text[lo:hi].replace("\n", " "))


def load_page_texts(pdf_path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    plumb_by_page: dict[int, str] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            plumb_by_page[i + 1] = page.extract_text() or ""

    doc = fitz.open(pdf_path)
    try:
        n = max(len(plumb_by_page), len(doc))
        for page_no in range(1, n + 1):
            fitz_text = ""
            if page_no <= len(doc):
                fitz_text = doc.load_page(page_no - 1).get_text() or ""
            combined = (plumb_by_page.get(page_no, "") + "\n" + fitz_text).strip()
            out.append((page_no, combined))
    finally:
        doc.close()

    return out


def load_tables_by_page(pdf_path: Path, max_pages: int = 15) -> dict[int, list[list[list[str | None]]]]:
    tables: dict[int, list[list[list[str | None]]]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[:max_pages]):
            raw = page.extract_tables() or []
            tables[i + 1] = raw
    return tables


def get_page_text_layers(pdf_path: Path, page_no: int) -> tuple[str, str, int]:
    pl_pages = 0
    pl_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        pl_pages = len(pdf.pages)
        if 1 <= page_no <= pl_pages:
            pl_text = pdf.pages[page_no - 1].extract_text() or ""

    doc = fitz.open(pdf_path)
    try:
        fz_n = len(doc)
        total = max(pl_pages, fz_n)
        fz_text = ""
        if 1 <= page_no <= fz_n:
            fz_text = doc.load_page(page_no - 1).get_text() or ""
    finally:
        doc.close()

    return pl_text, fz_text, total


def line_for_match(full_text: str, start: int, end: int) -> str:
    ls = full_text.rfind("\n", 0, start)
    ls = 0 if ls < 0 else ls + 1
    le = full_text.find("\n", end)
    le = len(full_text) if le < 0 else le
    return full_text[ls:le]
