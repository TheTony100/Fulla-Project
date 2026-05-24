from __future__ import annotations

import re

import sqlite3

from extraction.models import GroupedValue, ProjectAnalysisView, ProjectKpis, ReviewQueueItem
from extraction.report_metadata_extractor import parse_report_period
from projects.exceptions import LOW_CONFIDENCE_THRESHOLD, collect_project_exceptions
from projects.store import (
    fetch_extracted_values_for_project,
    fetch_historical_performance,
    list_project_documents,
    quarter_label_from_period,
)

REVIEW_QUEUE_TYPES = frozenset({"needs_review", "low_confidence", "missing_field"})


_MONTHLY_HISTORY_TABLE = "Monthly Performance History"


def _is_trusted_monthly_row(row: sqlite3.Row) -> bool:
    section = (row["source_section_name"] or row["source_table"] or "").strip()
    if section != _MONTHLY_HISTORY_TABLE:
        return False
    val = (row["extracted_value"] or "").strip()
    if val in ("", "needs_review"):
        return True
    if val == "20%" and "(2/20%)" in (row["snippet"] or ""):
        return False
    return True


def _display_label(field_name: str, report_period: str, extracted_value: str) -> str:
    if field_name == "monthly_net_return" and report_period:
        return f"{report_period} return"
    if field_name == "ytd_return" and report_period:
        return f"YTD {report_period.split()[-1] if report_period else ''}".strip()
    if field_name == "aum_or_nav" and report_period:
        return report_period
    if field_name.startswith("exposure_"):
        base = field_name.replace("exposure_", "").replace("_", " ").title()
        q = quarter_label_from_period(report_period)
        return f"{base} {q}".strip() if q else base
    if field_name.startswith("attribution_"):
        base = field_name.replace("attribution_", "").replace("_", " ").title()
        q = quarter_label_from_period(report_period)
        return f"{base} {q}".strip() if q else base
    return field_name.replace("_", " ").title()


def _period_key_from_row(report_period: str) -> tuple[int, int] | None:
    parsed = parse_report_period(report_period or "")
    return parsed


def _build_review_queue(conn: sqlite3.Connection, project_id: int) -> list[ReviewQueueItem]:
    items: list[ReviewQueueItem] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(issue_type: str, metric: str, value: str, source_pdf: str, details: str) -> None:
        key = (issue_type, source_pdf, metric)
        if key in seen:
            return
        seen.add(key)
        label = issue_type.replace("_", " ").title()
        items.append(
            ReviewQueueItem(
                issue_type=label,
                metric=metric,
                value=value,
                source_pdf=source_pdf,
                details=details,
            )
        )

    for e in collect_project_exceptions(conn, project_id):
        if e.exception_type not in REVIEW_QUEUE_TYPES:
            continue
        _add(e.exception_type, e.field_name.replace("_", " ").title(), "", e.source_pdf_filename, e.message)

    rows = fetch_extracted_values_for_project(conn, project_id)
    for r in rows:
        conf = float(r["confidence"])
        issue: str | None = None
        if r["review_status"] == "needs_review":
            issue = "needs_review"
        elif conf < LOW_CONFIDENCE_THRESHOLD:
            issue = "low_confidence"
        if issue is None:
            continue
        _add(
            issue,
            r["field_name"].replace("_", " ").title(),
            r["extracted_value"] or "",
            r["source_pdf_filename"],
            f"Confidence {int(round(conf * 100))}%.",
        )
    return items


def _build_kpis(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    performance: list[GroupedValue],
    aum_history: list[GroupedValue],
    review_queue: list[ReviewQueueItem],
) -> ProjectKpis:
    latest_aum = "—"
    latest_aum_period = ""
    if aum_history:
        latest = max(aum_history, key=lambda x: _period_sort_key(x.report_period))
        latest_aum = latest.value or "—"
        latest_aum_period = latest.report_period or ""

    latest_return = "—"
    latest_return_period = ""
    if performance:
        latest = max(performance, key=lambda x: _period_sort_key(x.report_period))
        latest_return = latest.value or "—"
        latest_return_period = latest.report_period or ""

    rows = fetch_extracted_values_for_project(conn, project_id)
    total = sum(
        1
        for r in rows
        if r["field_name"] not in ("manager_name", "fund_name") and not r["field_name"].startswith("monthly_return_")
    )

    return ProjectKpis(
        latest_aum=latest_aum,
        latest_aum_period=latest_aum_period,
        latest_monthly_return=latest_return,
        latest_monthly_period=latest_return_period,
        total_extracted_metrics=total,
        review_issues=len(review_queue),
    )


def build_project_analysis(conn: sqlite3.Connection, project_id: int) -> ProjectAnalysisView:
    project = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    project_name = project["name"] if project else f"Project {project_id}"
    docs = list_project_documents(conn, project_id)

    performance: list[GroupedValue] = []
    exposure: list[GroupedValue] = []
    aum_history: list[GroupedValue] = []
    attribution: list[GroupedValue] = []
    metadata: list[GroupedValue] = []

    hist_rows = fetch_historical_performance(conn, project_id)
    for h in hist_rows:
        section = (h["source_section_name"] or h["source_table"] or "").strip()
        if section != _MONTHLY_HISTORY_TABLE:
            continue
        val = h["return_value"] or ""
        if not val:
            continue
        performance.append(
            GroupedValue(
                label=f"{h['period_label']} return",
                value=val,
                report_period=h["period_label"],
                report_quarter=quarter_label_from_period(h["period_label"]),
                source_pdf=h["source_pdf_filename"],
                source_page=int(h["source_page"] or 0),
                snippet=h["snippet"] or "",
                confidence=float(h["confidence"]),
                review_status=h["review_status"],
                field_name="monthly_return",
                category="performance",
            )
        )

    hist_periods = {
        (int(h["period_year"]), int(h["period_month"]))
        for h in hist_rows
        if (h["source_section_name"] or h["source_table"] or "").strip() == _MONTHLY_HISTORY_TABLE
    }

    rows = fetch_extracted_values_for_project(conn, project_id)
    for r in rows:
        if r["field_name"].startswith("monthly_return_"):
            continue
        if r["field_name"] == "monthly_net_return":
            if not _is_trusted_monthly_row(r):
                continue
            period = _period_key_from_row(r["report_period"] or "")
            if period and period in hist_periods:
                continue
        if r["field_name"] == "ytd_return" and hist_rows:
            continue

        gv = GroupedValue(
            label=_display_label(r["field_name"], r["report_period"] or "", r["extracted_value"] or ""),
            value=r["extracted_value"] or "",
            report_period=r["report_period"] or "",
            report_quarter=r["report_quarter"] or "",
            source_pdf=r["source_pdf_filename"],
            source_page=int(r["source_page"]),
            snippet=r["snippet"] or "",
            confidence=float(r["confidence"]),
            review_status=r["review_status"],
            field_name=r["field_name"],
            category=r["category"],
        )
        cat = r["category"]
        if cat == "performance":
            performance.append(gv)
        elif cat == "exposure":
            exposure.append(gv)
        elif cat == "aum":
            aum_history.append(gv)
        elif cat == "attribution":
            attribution.append(gv)
        elif cat == "metadata":
            metadata.append(gv)

    performance.sort(key=lambda x: (_period_sort_key(x.report_period), x.label))
    aum_history.sort(key=lambda x: (_period_sort_key(x.report_period), x.label))
    exposure.sort(key=lambda x: (_period_sort_key(x.report_period), x.label))
    attribution.sort(key=lambda x: (_period_sort_key(x.report_period), x.label))

    review_queue = _build_review_queue(conn, project_id)
    kpis = _build_kpis(
        conn,
        project_id,
        performance=performance,
        aum_history=aum_history,
        review_queue=review_queue,
    )

    return ProjectAnalysisView(
        project_id=project_id,
        project_name=project_name,
        performance=performance,
        exposure=exposure,
        aum_history=aum_history,
        attribution=attribution,
        metadata=metadata,
        historical_performance=[dict(h) for h in hist_rows],
        document_count=len(docs),
        kpis=kpis,
        review_queue=review_queue,
    )


def _period_sort_key(period: str) -> tuple[int, int, str]:
    m = re.search(
        r"(?i)\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b",
        period or "",
    )
    if m:
        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        return (int(m.group(2)), month_map.get(m.group(1).lower()[:3], 0), period)
    qm = re.search(r"(?i)\bQ([1-4])\s+(\d{4})\b", period or "")
    if qm:
        return (int(qm.group(2)), int(qm.group(1)) * 3, period)
    return (0, 0, period or "")
