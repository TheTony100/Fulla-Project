from __future__ import annotations

from pathlib import Path

import fitz

# Rasterize above screen DPI so the preview stays sharp when scaled down in the browser.
_BASE_RENDER_SCALE = 2.0
_MAX_RENDER_SCALE = 4.0


def pdf_page_count(path: Path) -> int:
    doc = fitz.open(path)
    try:
        return len(doc)
    finally:
        doc.close()


def render_page_png(path: Path, page_one_based: int, zoom_pct: float = 100.0) -> bytes:
    # e.g. 100% UI zoom → 2.0 matrix scale; 150% → 3.0; capped to limit pixmap size.
    zoom_factor = max(0.1, float(zoom_pct)) / 100.0
    scale = min(_MAX_RENDER_SCALE, _BASE_RENDER_SCALE * zoom_factor)
    scale = max(0.5, scale)
    doc = fitz.open(path)
    try:
        pg = doc.load_page(page_one_based - 1)
        mat = fitz.Matrix(scale, scale)
        pix = pg.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def file_size_mb(path: Path) -> float:
    try:
        return round(path.stat().st_size / (1024 * 1024), 2)
    except OSError:
        return 0.0

