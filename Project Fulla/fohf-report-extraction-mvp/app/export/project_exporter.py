from __future__ import annotations

import io
import re

import pandas as pd

from export.workbook_format import finalize_worksheet, format_dataframe_labels, format_header_row
from projects.exceptions import LOW_CONFIDENCE_THRESHOLD, collect_project_exceptions, utc_export_timestamp
from projects.store import fetch_audit_trail, fetch_extracted_values_for_project, fetch_historical_performance, list_project_documents

REVIEW_QUEUE_TYPES = frozenset({"needs_review", "low_confidence", "missing_field"})
ISSUE_SEVERITY = {"missing_field": 0, "needs_review": 1, "low_confidence": 2}

VISIBLE_SHEETS = frozenset(
    {
        "Project Summary",
        "Performance Timeline",
        "Fund Metrics",
        "Attribution",
        "Review Queue",
    }
)

_MONTH_NAMES = [
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

_FUND_METRIC_FIELDS = frozenset({"aum_or_nav", "ytd_return", "monthly_net_return"})
_FUND_METRIC_SUBSTRINGS = ("fee", "lockup", "subscription", "nav", "redemption", "minimum")

_BUSINESS_LABEL_BY_FIELD: dict[str, str] = {
    "aum_or_nav": "AUM / NAV",
    "ytd_return": "YTD Return",
    "monthly_net_return": "Monthly Return (Report Month)",
    "report_month": "Report Month",
    "monthly_return": "Monthly Return",
    "attribution_long": "Long Attribution",
    "attribution_short": "Short Attribution",
    "attribution_top_winners": "Top 5 Winners",
    "attribution_top_losers": "Top 5 Losers",
    "exposure_net_exposure": "Net Exposure",
    "exposure_gross_exposure": "Gross Exposure",
    "exposure_long_pct": "Long Exposure",
    "exposure_short_pct": "Short Exposure",
}

_BUSINESS_LABEL_BY_METRIC_TYPE: dict[str, str] = {
    "monthly_return": "Monthly Return",
    "aum_or_nav": "AUM / NAV",
    "aum or nav": "AUM / NAV",
    "ytd_return": "YTD Return",
    "long": "Long Attribution",
    "short": "Short Attribution",
    "top winners": "Top 5 Winners",
    "top losers": "Top 5 Losers",
    "attribution long": "Long Attribution",
    "attribution short": "Short Attribution",
    "attribution top winners": "Top 5 Winners",
    "attribution top losers": "Top 5 Losers",
    "net exposure": "Net Exposure",
    "gross exposure": "Gross Exposure",
    "long pct": "Long Exposure",
    "short pct": "Short Exposure",
}


def _month_label(month_num: int) -> str:
    if 1 <= month_num <= 12:
        return _MONTH_NAMES[month_num]
    return str(month_num)


def _metric_type_key(field_name: str) -> str:
    if field_name.startswith("monthly_return_"):
        return "monthly_return"
    if field_name.startswith("exposure_"):
        return field_name.replace("exposure_", "").replace("_", " ")
    if field_name.startswith("attribution_"):
        return field_name.replace("attribution_", "").replace("_", " ")
    return field_name.replace("_", " ")


def _standardize_field(field_name: str) -> dict[str, object]:
    m = re.match(r"monthly_return_(\d{4})_(\d{2})", field_name)
    if m:
        year = int(m.group(1))
        month_num = int(m.group(2))
        return {
            "metric_type": "monthly_return",
            "year": year,
            "month": _month_label(month_num),
            "legacy_field_name": field_name,
            "has_period": True,
        }
    return {
        "metric_type": _metric_type_key(field_name),
        "year": "",
        "month": "",
        "legacy_field_name": field_name,
        "has_period": False,
    }


def business_metric_label(field_name: str) -> str:
    if field_name in _BUSINESS_LABEL_BY_FIELD:
        return _BUSINESS_LABEL_BY_FIELD[field_name]
    mt = _metric_type_key(field_name)
    if field_name in _BUSINESS_LABEL_BY_FIELD:
        return _BUSINESS_LABEL_BY_FIELD[field_name]
    if mt in _BUSINESS_LABEL_BY_METRIC_TYPE:
        return _BUSINESS_LABEL_BY_METRIC_TYPE[mt]
    normalized = mt.strip().lower()
    if normalized in _BUSINESS_LABEL_BY_METRIC_TYPE:
        return _BUSINESS_LABEL_BY_METRIC_TYPE[normalized]
    return mt.replace("_", " ").title()


def _format_confidence(conf: object) -> str:
    if conf is None or conf == "":
        return ""
    try:
        val = float(conf)
    except (TypeError, ValueError):
        return str(conf)
    if val <= 1.0:
        val *= 100.0
    return f"{int(round(val))}%"


def _confidence_numeric(conf: object) -> float:
    if conf is None or conf == "":
        return 0.0
    try:
        val = float(conf)
    except (TypeError, ValueError):
        return 0.0
    return val * 100.0 if val <= 1.0 else val


def _drop_empty_period_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in ("Year", "Month"):
        if col not in out.columns:
            continue
        if out[col].replace("", pd.NA).isna().all() or (out[col].astype(str).str.strip() == "").all():
            out = out.drop(columns=[col])
    return out


def _attach_canonical_value(
    df: pd.DataFrame,
    *,
    group_cols: list[str],
    value_col: str = "Value",
    conf_col: str = "_conf_numeric",
) -> pd.DataFrame:
    if df.empty or value_col not in df.columns:
        return df
    out = df.copy()
    canonicals: dict[tuple, str] = {}
    for key, group in out.groupby([c for c in group_cols if c in out.columns], dropna=False):
        if len(group) == 0:
            continue
        best_idx = group[conf_col].astype(float).idxmax()
        canonicals[key] = str(group.loc[best_idx, value_col])
    out["Canonical Value"] = out.apply(
        lambda row: canonicals.get(
            tuple(row[c] for c in group_cols if c in out.columns),
            row.get(value_col, ""),
        ),
        axis=1,
    )
    has_dupes = any(len(g) > 1 for _, g in out.groupby([c for c in group_cols if c in out.columns], dropna=False))
    if not has_dupes:
        out["Canonical Value"] = out[value_col]
    return out


def _finalize_confidence_column(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Confidence" not in df.columns:
        return df
    out = df.copy()
    if "_conf_numeric" not in out.columns:
        out["_conf_numeric"] = out["Confidence"].map(_confidence_numeric)
    out["Confidence"] = out["_conf_numeric"].map(_format_confidence)
    return out.drop(columns=["_conf_numeric"], errors="ignore")


def _is_fund_metric(field_name: str, category: str) -> bool:
    if category == "aum" or field_name in _FUND_METRIC_FIELDS:
        return True
    lo = field_name.lower()
    return any(s in lo for s in _FUND_METRIC_SUBSTRINGS)


def _build_data_quality_summary(extracted: list, exceptions: list) -> pd.DataFrame:
    total = len(extracted)
    needs_review = 0
    low_conf = 0
    validated = 0
    for r in extracted:
        conf = float(r["confidence"])
        if r["review_status"] == "needs_review":
            needs_review += 1
        elif conf < LOW_CONFIDENCE_THRESHOLD:
            low_conf += 1
        else:
            validated += 1
    missing = sum(1 for e in exceptions if e.exception_type == "missing_field")
    return pd.DataFrame(
        [
            {"Field": "Data Quality Summary", "Value": ""},
            {"Field": "Total Extracted Fields", "Value": total},
            {"Field": "Validated Fields", "Value": validated},
            {"Field": "Needs Review", "Value": needs_review},
            {"Field": "Low Confidence", "Value": low_conf},
            {"Field": "Missing Fields", "Value": missing},
        ]
    )


def _build_performance_timeline(hist: list) -> pd.DataFrame:
    rows = []
    for h in hist:
        month_num = int(h["period_month"])
        conf = float(h["confidence"])
        rows.append(
            {
                "Year": int(h["period_year"]),
                "Month": _month_label(month_num),
                "Net Return": h["return_value"],
                "Canonical Value": h["return_value"],
                "Source Document": h["source_pdf_filename"],
                "Confidence": conf,
                "_conf_numeric": _confidence_numeric(conf),
                "Review Status": h["review_status"],
                "_sort_month": month_num,
            }
        )
    cols = ["Year", "Month", "Net Return", "Canonical Value", "Source Document", "Confidence", "Review Status"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    df = df.sort_values(by=["Year", "_sort_month"], kind="stable").drop(columns=["_sort_month"])
    df = _finalize_confidence_column(df)
    return df[cols]


def _build_metric_sheet_rows(extracted: list, category: str) -> list[dict[str, object]]:
    rows = []
    for r in extracted:
        if r["category"] != category:
            continue
        if r["field_name"].startswith("monthly_return_"):
            continue
        std = _standardize_field(r["field_name"])
        row: dict[str, object] = {
            "Metric": business_metric_label(r["field_name"]),
            "Value": r["extracted_value"],
            "Report Period": r["report_period"] or "—",
            "Source Document": r["source_pdf_filename"],
            "Confidence": float(r["confidence"]),
            "_conf_numeric": _confidence_numeric(r["confidence"]),
            "Review Status": r["review_status"],
            "_group_metric": business_metric_label(r["field_name"]),
            "_group_period": r["report_period"] or "—",
        }
        if std["has_period"]:
            row["Year"] = std["year"]
            row["Month"] = std["month"]
            row["_group_year"] = std["year"]
            row["_group_month"] = std["month"]
        rows.append(row)
    return rows


def _rows_to_analytics_df(
    rows: list[dict[str, object]],
    *,
    group_cols: list[str],
    column_order: list[str],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=column_order)
    df = pd.DataFrame(rows)
    df = _attach_canonical_value(df, group_cols=group_cols, value_col="Value")
    df = df.drop(columns=[c for c in df.columns if c.startswith("_group") or c == "_severity"], errors="ignore")
    df = _drop_empty_period_columns(df)
    df = _finalize_confidence_column(df)
    present = [c for c in column_order if c in df.columns]
    return df[present]


def _build_fund_metrics(extracted: list) -> pd.DataFrame:
    rows = []
    for r in extracted:
        if r["field_name"].startswith("monthly_return_"):
            continue
        if not _is_fund_metric(r["field_name"], r["category"]):
            continue
        rows.append(
            {
                "Metric": business_metric_label(r["field_name"]),
                "Value": r["extracted_value"],
                "Report Period": r["report_period"] or "—",
                "Source Document": r["source_pdf_filename"],
                "Confidence": float(r["confidence"]),
                "_conf_numeric": _confidence_numeric(r["confidence"]),
                "Review Status": r["review_status"],
                "_group_metric": business_metric_label(r["field_name"]),
                "_group_period": r["report_period"] or "—",
            }
        )
    order = ["Metric", "Value", "Canonical Value", "Report Period", "Source Document", "Confidence", "Review Status"]
    return _rows_to_analytics_df(rows, group_cols=["_group_metric", "_group_period"], column_order=order)


def _build_exposure_attribution(extracted: list, category: str) -> pd.DataFrame:
    rows = _build_metric_sheet_rows(extracted, category)
    order = ["Metric", "Value", "Canonical Value", "Report Period", "Source Document", "Confidence", "Review Status"]
    return _rows_to_analytics_df(rows, group_cols=["_group_metric", "_group_period"], column_order=order)


def _build_review_queue(extracted: list, hist: list, exceptions: list) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(
        *,
        issue_type: str,
        field_name: str,
        value: str,
        source_pdf: str,
        confidence: float | None,
        message: str,
        year: object = "",
        month: object = "",
    ) -> None:
        std = _standardize_field(field_name)
        key = (issue_type, source_pdf, str(std.get("legacy_field_name", field_name)))
        if key in seen:
            return
        seen.add(key)
        row = {
            "Issue Type": issue_type,
            "Metric": business_metric_label(field_name),
            "Value": value,
            "Source Document": source_pdf,
            "Confidence": confidence if confidence is not None else "",
            "_conf_numeric": _confidence_numeric(confidence) if confidence is not None else 0.0,
            "Details": message,
            "_severity": ISSUE_SEVERITY.get(issue_type, 99),
        }
        if year != "" or std["has_period"]:
            row["Year"] = year if year != "" else std["year"]
            row["Month"] = month if month != "" else std["month"]
        rows.append(row)

    for e in exceptions:
        if e.exception_type not in REVIEW_QUEUE_TYPES:
            continue
        _add(
            issue_type=e.exception_type,
            field_name=e.field_name,
            value="",
            source_pdf=e.source_pdf_filename,
            confidence=None,
            message=e.message,
        )

    for r in extracted:
        conf = float(r["confidence"])
        issue: str | None = None
        if r["review_status"] == "needs_review":
            issue = "needs_review"
        elif conf < LOW_CONFIDENCE_THRESHOLD:
            issue = "low_confidence"
        if issue is None:
            continue
        std = _standardize_field(r["field_name"])
        _add(
            issue_type=issue,
            field_name=r["field_name"],
            value=r["extracted_value"] or "",
            source_pdf=r["source_pdf_filename"],
            confidence=conf,
            message=f"Extracted value flagged ({issue.replace('_', ' ')}).",
            year=std["year"],
            month=std["month"],
        )

    for h in hist:
        if h["review_status"] != "needs_review":
            continue
        month_num = int(h["period_month"])
        _add(
            issue_type="needs_review",
            field_name="monthly_return",
            value=h["return_value"] or "",
            source_pdf=h["source_pdf_filename"],
            confidence=float(h["confidence"]),
            message=f"Timeline period {h['period_label']} needs review.",
            year=int(h["period_year"]),
            month=_month_label(month_num),
        )

    if not rows:
        return pd.DataFrame(
            columns=["Issue Type", "Metric", "Year", "Month", "Value", "Source Document", "Confidence", "Details"]
        )
    df = pd.DataFrame(rows)
    df = df.sort_values(by=["_severity", "_conf_numeric"], ascending=[True, True], kind="stable")
    df = _finalize_confidence_column(df)
    df = _drop_empty_period_columns(df)
    df = _drop_empty_period_columns(df)
    df = _finalize_confidence_column(df)
    cols = ["Issue Type", "Metric", "Year", "Month", "Value", "Source Document", "Confidence", "Details"]
    return df[[c for c in cols if c in df.columns]]


def _build_source_traceability(extracted: list) -> pd.DataFrame:
    rows = []
    for r in extracted:
        std = _standardize_field(r["field_name"])
        row = {
            "Category": r["category"],
            "Metric": business_metric_label(r["field_name"]),
            "Value": r["extracted_value"],
            "Report Period": r["report_period"],
            "Report Quarter": r["report_quarter"],
            "Review Status": r["review_status"],
            "Confidence": _format_confidence(r["confidence"]),
            "Source Document": r["source_pdf_filename"],
            "Source Page": r["source_page"],
        }
        if std["has_period"]:
            row["Year"] = std["year"]
            row["Month"] = std["month"]
        row.update(
            {
                "Source Table": r["source_table"],
                "Source Section": r["source_section_name"],
                "Legacy Field Name": std["legacy_field_name"],
                "Table Row": r["matched_row_label"],
                "Table Column": r["matched_column_label"],
                "Source Snippet": r["snippet"],
            }
        )
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    analytics = ["Category", "Metric", "Year", "Month", "Value", "Report Period", "Report Quarter", "Review Status", "Confidence", "Source Document", "Source Page"]
    provenance = ["Source Table", "Source Section", "Legacy Field Name", "Table Row", "Table Column", "Source Snippet"]
    ordered = [c for c in analytics + provenance if c in df.columns]
    return _drop_empty_period_columns(df)[ordered]


def _build_audit_trail(audit: list) -> pd.DataFrame:
    rows = []
    for a in audit:
        field = a["field_name"] or ""
        std = _standardize_field(field) if field else {"has_period": False, "year": "", "month": "", "legacy_field_name": ""}
        row = {
            "Timestamp": a["created_at"],
            "Event Type": a["event_type"],
            "Metric": business_metric_label(field) if field else "",
            "Value": a["value"],
            "Report Period": a["report_period"],
            "Review Status": a["review_status"],
            "Confidence": _format_confidence(a["confidence"]),
            "Source Document": a["source_pdf"],
            "Source Page": a["source_page"],
            "Details": a["details"],
        }
        if std.get("has_period"):
            row["Year"] = std["year"]
            row["Month"] = std["month"]
        row.update(
            {
                "Source Table": a["source_table"],
                "Legacy Field Name": std.get("legacy_field_name", ""),
                "Source Snippet": a["snippet"],
            }
        )
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    analytics = ["Timestamp", "Event Type", "Metric", "Year", "Month", "Value", "Report Period", "Review Status", "Confidence", "Source Document", "Source Page", "Details"]
    provenance = ["Source Table", "Legacy Field Name", "Source Snippet"]
    ordered = [c for c in analytics + provenance if c in df.columns]
    return _drop_empty_period_columns(df)[ordered]


def build_project_workbook_bytes(conn, project_id: int) -> bytes:
    project = conn.execute("SELECT name, manager_name FROM projects WHERE id = ?", (project_id,)).fetchone()
    project_name = project["name"] if project else f"Project {project_id}"
    manager_name = (project["manager_name"] if project else "") or ""

    docs = list_project_documents(conn, project_id)
    hist = fetch_historical_performance(conn, project_id)
    extracted = fetch_extracted_values_for_project(conn, project_id)
    audit = fetch_audit_trail(conn, project_id)
    exceptions = collect_project_exceptions(conn, project_id)
    exported_at = utc_export_timestamp()

    info_df = pd.DataFrame(
        [
            {"Field": "Project Name", "Value": project_name},
            {"Field": "Manager", "Value": manager_name or "—"},
            {"Field": "Exported (UTC)", "Value": exported_at},
            {"Field": "Documents", "Value": len(docs)},
        ]
    )
    quality_df = _build_data_quality_summary(extracted, exceptions)
    docs_df = pd.DataFrame(
        [
            {
                "Document": doc.filename,
                "Report Period": doc.report_period or "—",
                "Status": doc.status,
                "Type": doc.document_type,
            }
            for doc in docs
        ]
    )

    quality_start = len(info_df) + 2
    doc_start = quality_start + len(quality_df) + 2

    performance_df = _build_performance_timeline(hist)
    fund_metrics_df = _build_fund_metrics(extracted)
    exposure_df = _build_exposure_attribution(extracted, "exposure")
    attribution_df = _build_exposure_attribution(extracted, "attribution")
    review_queue_df = _build_review_queue(extracted, hist, exceptions)
    trace_df = _build_source_traceability(extracted)
    audit_df = _build_audit_trail(audit)

    sheet_specs: list[tuple[str, pd.DataFrame, dict]] = [
        ("Project Summary", info_df, {}),
        ("Performance Timeline", performance_df, {"status_column": "Review Status"}),
        ("Fund Metrics", fund_metrics_df, {"status_column": "Review Status"}),
        ("Attribution", attribution_df, {"status_column": "Review Status"}),
        ("Review Queue", review_queue_df, {"issue_column": "Issue Type"}),
        ("Exposure", exposure_df, {"status_column": "Review Status", "hidden": True}),
        ("Source Traceability", trace_df, {"hidden": True}),
        ("Audit Trail", audit_df, {"status_column": "Review Status", "hidden": True}),
    ]

    docs_export = format_dataframe_labels(docs_df)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df, opts in sheet_specs:
            if sheet_name == "Project Summary":
                df.to_excel(writer, index=False, sheet_name=sheet_name)
                quality_df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=quality_start)
                if not docs_export.empty:
                    docs_export.to_excel(writer, index=False, sheet_name=sheet_name, startrow=doc_start)
            else:
                format_dataframe_labels(df).to_excel(writer, index=False, sheet_name=sheet_name)

        ws_summary = writer.sheets["Project Summary"]
        hidden_summary = "Project Summary" not in VISIBLE_SHEETS
        format_header_row(ws_summary, row=1)
        format_header_row(ws_summary, row=quality_start + 1)
        if not docs_export.empty:
            format_header_row(ws_summary, row=doc_start + 1)
        finalize_worksheet(ws_summary, header_row=1, hidden=hidden_summary)

        for sheet_name, _df, opts in sheet_specs:
            if sheet_name == "Project Summary":
                continue
            ws = writer.sheets[sheet_name]
            hidden = opts.get("hidden", sheet_name not in VISIBLE_SHEETS)
            finalize_worksheet(
                ws,
                status_column=opts.get("status_column"),
                issue_column=opts.get("issue_column"),
                hidden=hidden,
            )

    buf.seek(0)
    return buf.getvalue()
