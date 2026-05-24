from __future__ import annotations

import html
import re
import shutil
from datetime import datetime
from pathlib import Path

import streamlit as st

from export.project_exporter import build_project_workbook_bytes
from extraction.monthly_extract import get_page_text_layers
from projects.aggregation import build_project_analysis
from projects.filesystem import (
    project_failed_dir,
    project_input_dir,
    project_processed_dir,
    resolve_project_pdf,
)
from projects.pipeline import (
    clear_and_reprocess_project,
    extract_document_for_project,
    save_upload_to_project,
)
from projects.store import (
    create_project,
    delete_project_document,
    document_bucket,
    list_project_documents,
    list_projects,
    upsert_project_document,
)
from ui.pdf_preview import file_size_mb, pdf_page_count, render_page_png
from ui.project_views import render_analysis_workspace
from ui.theme import inject_theme


def _fmt_ts(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d.strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")
    except Exception:
        return ts


def _badge_label(status: str) -> str:
    if status == "failed":
        return "Failed"
    if status in ("queued", "unprocessed"):
        return "Queued"
    if status == "needs_review":
        return "Needs Review"
    return "Processed"


def _move_doc_to_input(project_id: int, src: Path) -> Path:
    dest = project_input_dir(project_id) / src.name
    if dest.exists():
        dest.unlink()
    shutil.move(str(src), str(dest))
    return dest.resolve()


def _project_excel_download(
    conn,
    project_id: int,
    projects: list,
) -> tuple[bytes | None, str]:
    docs = list_project_documents(conn, project_id)
    if not docs:
        return None, "project_analysis.xlsx"
    export_buf = build_project_workbook_bytes(conn, project_id)
    proj = next((p for p in projects if p.id == project_id), None)
    safe = re.sub(r"[^\w\-]+", "_", (proj.name if proj else "project")).strip("_") or "project"
    return export_buf, f"{safe}_analysis.xlsx"


def _get_doc_page(doc_id: int, max_pages: int) -> int:
    pages = st.session_state.setdefault("doc_viewer_pages", {})
    pg = int(pages.get(str(doc_id), 1))
    return max(1, min(pg, max(1, max_pages)))


def _set_doc_page(doc_id: int, page: int) -> None:
    st.session_state.doc_viewer_pages[str(doc_id)] = page


def _render_project_sidebar(conn, projects: list, project_id: int | None) -> int | None:
    st.markdown('<div class="fohf-section-title">Workspace</div>', unsafe_allow_html=True)

    action_a, action_b = st.columns(2)
    has_projects = bool(projects)
    with action_a:
        if st.button("New", use_container_width=True, type="primary", key="btn_create_project"):
            st.session_state.show_create_project = True
            st.session_state.show_add_documents = False
    with action_b:
        if st.button("Add PDFs", use_container_width=True, key="btn_add_documents", disabled=not has_projects):
            st.session_state.show_add_documents = True
            st.session_state.show_create_project = False

    if st.session_state.show_create_project:
        with st.container(border=True):
            new_name = st.text_input("Project name", placeholder="e.g. MYDA Fund 2025", key="new_project_name_input")
            if st.button("Save", use_container_width=True, type="primary", key="btn_save_project"):
                if new_name.strip():
                    pid = create_project(conn, name=new_name.strip())
                    st.session_state.selected_project_id = pid
                    st.session_state.show_create_project = False
                    st.toast(f"Created project: {new_name.strip()}", icon="✅")
                    st.rerun()
                else:
                    st.warning("Enter a project name.")
            if st.button("Cancel", use_container_width=True, key="btn_cancel_project"):
                st.session_state.show_create_project = False
                st.rerun()

    if not projects:
        st.caption("Create a project to begin analysis.")
        return None

    project_names = {p.id: p.name for p in projects}
    if project_id is None or project_id not in project_names:
        project_id = projects[0].id
        st.session_state.selected_project_id = project_id

    selected_pid = st.selectbox(
        "Active project",
        options=[p.id for p in projects],
        format_func=lambda i: project_names[int(i)],
        index=[p.id for p in projects].index(project_id),
        key="project_select",
    )
    project_id = int(selected_pid)
    st.session_state.selected_project_id = project_id

    if st.session_state.show_add_documents:
        with st.container(border=True):
            st.caption(f"Upload to **{project_names[project_id]}**")
            up_files = st.file_uploader(
                "PDFs",
                type=["pdf"],
                accept_multiple_files=True,
                key=f"upload_pdf_{st.session_state.pdf_uploader_key}",
                label_visibility="collapsed",
            )
            if st.button("Upload & Extract", use_container_width=True, type="primary", disabled=not up_files):
                with st.spinner("Extracting…"):
                    for uf in up_files or []:
                        dest = save_upload_to_project(project_id, uf.name, uf.getvalue())
                        upsert_project_document(
                            conn,
                            project_id=project_id,
                            filename=dest.name,
                            path=str(dest.resolve()),
                            status="unprocessed",
                        )
                        extract_document_for_project(conn, project_id=project_id, pdf_path=dest.resolve())
                st.session_state.pdf_uploader_key += 1
                st.session_state.show_add_documents = False
                st.toast("Documents added and extracted.", icon="✅")
                st.rerun()
            if st.button("Done", use_container_width=True, key="btn_upload_done"):
                st.session_state.show_add_documents = False
                st.rerun()

    docs = list_project_documents(conn, project_id)
    st.caption(f"{len(docs)} source PDF(s) · view below in Supporting Evidence")

    if docs and st.button(
        "Clear & reprocess all",
        use_container_width=True,
        key="btn_clear_reprocess_sidebar",
    ):
        with st.spinner("Reprocessing…"):
            clear_and_reprocess_project(conn, project_id)
        st.rerun()

    return project_id


def _render_source_documents(conn, project_id: int, projects: list) -> None:
    docs = list_project_documents(conn, project_id)
    proj = next((p for p in projects if p.id == project_id), None)
    proj_label = proj.name if proj else f"Project {project_id}"

    with st.expander(f"Supporting evidence — source documents ({len(docs)})", expanded=False):
        st.caption(
            f"PDFs for **{proj_label}** are reference material. "
            "Extracted metrics above are the primary analysis output."
        )
        if not docs:
            st.info("No documents uploaded. Use **Add PDFs** in the workspace panel.")
            return

        for doc in docs:
            sp = resolve_project_pdf(project_id, doc.filename)
            if sp is None:
                sp = Path(doc.path) if doc.path else None
            if sp is None or not sp.exists():
                st.warning(f"{doc.filename} — file not found.")
                continue

            pages_n = pdf_page_count(sp)
            badge = _badge_label(doc.status)
            st.markdown(f"**{html.escape(sp.name)}**")
            st.caption(
                f"{doc.report_period or '—'} · {pages_n} pg · {file_size_mb(sp)} MB · {badge}"
            )

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                if st.button("Reprocess", key=f"reprocess_{doc.id}"):
                    with st.spinner("Reprocessing…"):
                        tgt = _move_doc_to_input(project_id, sp) if document_bucket(project_id, sp) != "input" else sp
                        ok, err, _ = extract_document_for_project(conn, project_id=project_id, pdf_path=tgt)
                        if not ok and err:
                            st.error(err)
                    st.rerun()
            with c2:
                st.download_button(
                    "Download PDF",
                    data=sp.read_bytes(),
                    file_name=sp.name,
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_{doc.id}",
                )
            with c3:
                if st.button("Remove", key=f"remove_{doc.id}"):
                    delete_project_document(conn, doc.id)
                    try:
                        sp.unlink(missing_ok=True)
                    except OSError:
                        pass
                    for folder in (
                        project_input_dir(project_id),
                        project_processed_dir(project_id),
                        project_failed_dir(project_id),
                    ):
                        alt = folder / sp.name
                        if alt.exists():
                            alt.unlink()
                    st.rerun()

            pg = _get_doc_page(doc.id, pages_n)
            nav1, nav2, nav3 = st.columns([0.4, 1.2, 0.4])
            if nav1.button("◀", key=f"prev_{doc.id}", disabled=pg <= 1):
                _set_doc_page(doc.id, pg - 1)
                st.rerun()
            nav2.caption(f"Page {pg} / {pages_n}")
            if nav3.button("▶", key=f"next_{doc.id}", disabled=pg >= pages_n):
                _set_doc_page(doc.id, pg + 1)
                st.rerun()

            try:
                png = render_page_png(sp, pg, float(st.session_state.viewer_zoom_pct))
                st.image(png, use_container_width=True)
            except Exception:
                st.warning("Could not render this page.")

            with st.expander("Raw text", expanded=False):
                pl, fz, _ = get_page_text_layers(sp, pg)
                combined = (pl.strip() + "\n\n" + fz.strip()).strip() or "(empty)"
                st.text(combined[:8000])

            st.divider()


def render_dashboard(conn) -> None:
    inject_theme()

    st.session_state.setdefault("selected_project_id", None)
    st.session_state.setdefault("viewer_zoom_pct", 100)
    st.session_state.setdefault("pdf_uploader_key", 0)
    st.session_state.setdefault("show_create_project", False)
    st.session_state.setdefault("show_add_documents", False)
    st.session_state.setdefault("doc_viewer_pages", {})
    st.session_state.setdefault("analysis_section", "performance")

    projects = list_projects(conn)
    project_id = st.session_state.get("selected_project_id")
    if projects and project_id is None:
        project_id = projects[0].id
        st.session_state.selected_project_id = project_id

    t1, t2, t3 = st.columns([4.5, 1.2, 0.35])
    with t1:
        st.markdown('<p class="fohf-brand">FOHF Intelligence Workspace</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="fohf-muted">Project-level extracted fund metrics · PDFs are supporting evidence</p>',
            unsafe_allow_html=True,
        )
    with t2:
        export_buf, export_name = (None, "project_analysis.xlsx")
        if project_id is not None:
            export_buf, export_name = _project_excel_download(conn, project_id, projects)
        st.download_button(
            "Export Excel",
            data=export_buf or b"",
            file_name=export_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            disabled=export_buf is None,
            key="export_project_xlsx",
        )
    with t3:
        st.markdown('<span class="fohf-pill-user">JD</span>', unsafe_allow_html=True)

    sidebar_col, main_col = st.columns([0.95, 3.05], gap="medium")

    with sidebar_col:
        project_id = _render_project_sidebar(conn, projects, project_id)

    with main_col:
        if project_id is None:
            st.info("Create a project in the workspace panel to start analysis.")
            return

        analysis = build_project_analysis(conn, project_id)
        export_buf, export_name = _project_excel_download(conn, project_id, projects)
        render_analysis_workspace(analysis, export_buf=export_buf, export_name=export_name)

        st.divider()
        _render_source_documents(conn, project_id, projects)
