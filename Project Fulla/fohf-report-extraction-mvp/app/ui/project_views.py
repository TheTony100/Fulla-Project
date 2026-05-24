from __future__ import annotations

import html

import streamlit as st

from extraction.models import GroupedValue, ProjectAnalysisView, ReviewQueueItem


SECTIONS = (
    ("performance", "Performance Timeline"),
    ("fund_metrics", "Fund Metrics"),
    ("attribution", "Attribution"),
    ("review_queue", "Review Queue"),
)


def _confidence_pct(conf: float) -> str:
    return f"{int(round(conf * 100))}%"


def _kpi_markup(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{html.escape(sub)}</div>' if sub else ""
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-value">{html.escape(value)}</div>'
        f"{sub_html}"
        f"</div>"
    )


def _section_card_markup(title: str, count: int, active: bool) -> str:
    cls = "analysis-section-card analysis-section-card-active" if active else "analysis-section-card"
    return (
        f'<div class="{cls}">'
        f'<div class="analysis-section-title">{html.escape(title)}</div>'
        f'<div class="analysis-section-count">{count} item{"s" if count != 1 else ""}</div>'
        f"</div>"
    )


def _render_metric_rows(items: list[GroupedValue]) -> None:
    if not items:
        st.caption("No data extracted yet.")
        return
    for item in items:
        period = f" · {item.report_period}" if item.report_period else ""
        review = ""
        if item.review_status == "needs_review":
            review = " · ⚠ needs review"
        st.markdown(
            f"**{html.escape(item.label)}**{html.escape(period)}: "
            f"{html.escape(item.value)} "
            f"(_{html.escape(_confidence_pct(item.confidence))}, "
            f"{html.escape(item.source_pdf)} p.{item.source_page}_{review})",
            unsafe_allow_html=True,
        )


def _render_review_queue(items: list[ReviewQueueItem]) -> None:
    if not items:
        st.caption("No review issues — all extracted metrics passed validation.")
        return
    for item in items:
        val = f" · {item.value}" if item.value else ""
        st.markdown(
            f"- **{html.escape(item.issue_type)}** · {html.escape(item.metric)}{html.escape(val)} "
            f"(_{html.escape(item.source_pdf)}_)",
            unsafe_allow_html=True,
        )
        if item.details:
            st.caption(html.escape(item.details))


def _section_count(analysis: ProjectAnalysisView, section_id: str) -> int:
    if section_id == "performance":
        return len(analysis.performance)
    if section_id == "fund_metrics":
        return len(analysis.aum_history)
    if section_id == "attribution":
        return len(analysis.attribution)
    if section_id == "review_queue":
        return len(analysis.review_queue or [])
    return 0


def _render_section_detail(analysis: ProjectAnalysisView, section_id: str) -> None:
    if section_id == "performance":
        _render_metric_rows(analysis.performance)
    elif section_id == "fund_metrics":
        _render_metric_rows(analysis.aum_history)
    elif section_id == "attribution":
        _render_metric_rows(analysis.attribution)
    elif section_id == "review_queue":
        _render_review_queue(analysis.review_queue or [])


def render_analysis_workspace(
    analysis: ProjectAnalysisView,
    *,
    export_buf: bytes | None,
    export_name: str,
) -> None:
    """Primary analysis-first workspace (metrics, sections, detail)."""
    st.session_state.setdefault("analysis_section", "performance")

    proj = html.escape(analysis.project_name)
    st.markdown(f'<div class="fohf-card-title">Project Analysis</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="fohf-muted">{proj} · {analysis.document_count} source document(s) · live extracted intelligence</div>',
        unsafe_allow_html=True,
    )

    kpis = analysis.kpis
    if kpis:
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(
                _kpi_markup("Latest AUM", kpis.latest_aum, kpis.latest_aum_period or "—"),
                unsafe_allow_html=True,
            )
        with k2:
            st.markdown(
                _kpi_markup(
                    "Latest Monthly Return",
                    kpis.latest_monthly_return,
                    kpis.latest_monthly_period or "—",
                ),
                unsafe_allow_html=True,
            )
        with k3:
            st.markdown(
                _kpi_markup("Total Extracted Metrics", str(kpis.total_extracted_metrics)),
                unsafe_allow_html=True,
            )
        with k4:
            st.markdown(
                _kpi_markup("Review Issues", str(kpis.review_issues)),
                unsafe_allow_html=True,
            )

    st.markdown('<div class="fohf-section-title">Analysis views</div>', unsafe_allow_html=True)
    sec_cols = st.columns(4)
    active = st.session_state.get("analysis_section", "performance")
    for col, (sid, title) in zip(sec_cols, SECTIONS):
        with col:
            count = _section_count(analysis, sid)
            st.markdown(_section_card_markup(title, count, active == sid), unsafe_allow_html=True)
            if st.button(
                "Open" if active != sid else "Viewing",
                key=f"section_{sid}",
                use_container_width=True,
                type="primary" if active == sid else "secondary",
            ):
                st.session_state.analysis_section = sid
                st.rerun()

    section_title = next(t for s, t in SECTIONS if s == active)
    with st.container(border=True):
        st.markdown(f"**{section_title}**")
        _render_section_detail(analysis, active)

    st.download_button(
        "Extract to Excel",
        data=export_buf or b"",
        file_name=export_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
        disabled=export_buf is None,
        key="extract_to_excel_workspace",
    )


def render_project_analysis_panel(analysis: ProjectAnalysisView) -> None:
    """Legacy entry point — delegates to workspace."""
    render_analysis_workspace(analysis, export_buf=None, export_name="project_analysis.xlsx")
