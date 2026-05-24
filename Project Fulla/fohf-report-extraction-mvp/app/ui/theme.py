THEME_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');

  html, body, [class*="css"]  {
    font-family: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif !important;
  }

  #MainMenu {visibility: hidden;}
  footer {visibility: hidden;}
  section[data-testid="stSidebar"] {display: none !important;}
  div[data-testid="collapsedControl"] {display: none !important;}
  header[data-testid="stHeader"] {
    background: rgba(255,255,255,1);
    border-bottom: 1px solid #e8eaee;
  }
  .block-container {
    padding-top: 0.75rem !important;
    padding-bottom: 2rem !important;
    max-width: 100% !important;
  }

  .fohf-brand {
    font-size: 1.2rem;
    font-weight: 600;
    color: #0f172a;
    letter-spacing: -0.02em;
    margin: 0;
  }

  .fohf-pill-user {
    width: 34px; height: 34px; border-radius: 999px;
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    color: #fff;
    font-size: 0.72rem;
    font-weight: 600;
    display: inline-flex; align-items: center; justify-content: center;
    border: 1px solid #e8eaee;
  }

  /* Anchor-scoped 3-panel layout: fixed sidebar + flexible viewer + fixed right panel */
  .dash-anchor + div[data-testid="stHorizontalBlock"] {
    align-items: stretch;
  }
  .dash-anchor + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(1) {
    flex: 0 0 300px !important;
    width: 300px !important;
    max-width: 300px !important;
    min-width: 300px !important;
  }
  .dash-anchor + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(2) {
    flex: 1 1 auto !important;
    min-width: 520px !important;
  }
  .dash-anchor + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(3) {
    flex: 0 0 360px !important;
    width: 360px !important;
    max-width: 360px !important;
    min-width: 360px !important;
  }

  /* Panels */
  div[data-testid="column"]:nth-child(1) {
    background: #f8fafc;
    border-radius: 12px;
    border: 1px solid #e8eaee;
    padding: 0.85rem !important;
    min-height: 760px;
  }
  div[data-testid="column"]:nth-child(2) {
    background: #fafafa;
    border-radius: 12px;
    border: 1px solid #e8eaee;
    padding: 0.85rem !important;
    min-height: 760px;
  }
  div[data-testid="column"]:nth-child(3) {
    background: #ffffff;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
    padding: 0.85rem !important;
    min-height: 760px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.04);
  }

  .fohf-muted { color: #64748b; font-size: 0.8rem; }
  .fohf-section-title {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b;
    margin: 0.25rem 0 0.5rem 0;
  }
  .fohf-card-title {
    font-size: 1rem;
    font-weight: 600;
    color: #0f172a;
    margin: 0 0 0.75rem 0;
  }

  /* Badges */
  .badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    border: 1px solid transparent;
  }
  .badge-processed { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }
  .badge-review { background: #fff7ed; color: #c2410c; border-color: #fed7aa; }
  .badge-processing { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }
  .badge-failed { background: #fef2f2; color: #b91c1c; border-color: #fecaca; }
  .badge-queued { background: #f1f5f9; color: #475569; border-color: #e2e8f0; }

  /* Confidence pills on extraction cards */
  .extraction-confidence {
    display: inline-flex;
    align-items: center;
    font-size: 10px;
    font-weight: 700;
    line-height: 1;
    padding: 3px 7px;
    border-radius: 999px;
    border: 1px solid transparent;
    flex-shrink: 0;
    white-space: nowrap;
  }
  .extraction-confidence.conf-high {
    color: #047857;
    background: #ecfdf5;
    border-color: #a7f3d0;
  }
  .extraction-confidence.conf-med {
    color: #b45309;
    background: #fffbeb;
    border-color: #fde68a;
  }
  .extraction-confidence.conf-low {
    color: #b91c1c;
    background: #fef2f2;
    border-color: #fecaca;
  }
  .extraction-confidence.conf-manual {
    color: #1d4ed8;
    background: #eff6ff;
    border-color: #bfdbfe;
  }

  /* Field row card */
  .field-card {
    border: 1px solid #e8eaee;
    border-radius: 10px;
    padding: 0.65rem 0.75rem;
    margin-bottom: 0.5rem;
    background: #fcfcfd;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .field-card:hover {
    border-color: #cbd5e1;
    box-shadow: 0 2px 8px rgba(15,23,42,0.05);
  }

  /* PDF viewer: style Streamlit’s image block in center column (no fake HTML wrapper around st.image) */
  .dash-anchor + div[data-testid="stHorizontalBlock"]
    > div[data-testid="column"]:nth-child(2)
    div[data-testid="element-container"]:has([data-testid="stImage"]) {
    background: #f1f5f9;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    padding: 1.15rem;
    margin-top: 0.25rem;
    min-height: 480px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    box-sizing: border-box;
  }
  .dash-anchor + div[data-testid="stHorizontalBlock"]
    > div[data-testid="column"]:nth-child(2)
    [data-testid="stImage"] {
    width: 100%;
    display: flex;
    justify-content: center;
    align-items: flex-start;
  }
  .dash-anchor + div[data-testid="stHorizontalBlock"]
    > div[data-testid="column"]:nth-child(2)
    [data-testid="stImage"] img {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  }

  .pdf-placeholder {
    width: 100%;
    max-width: 560px;
    background: #ffffff;
    border: 1px solid #e8eaee;
    border-radius: 14px;
    padding: 28px 22px;
    text-align: left;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
  }
  .pdf-placeholder h3 {
    margin: 0 0 6px 0;
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
  }
  .pdf-placeholder p {
    margin: 0;
    font-size: 12px;
    color: #64748b;
  }

  .upload-zone-hint {
    border: 1px dashed #cbd5e1;
    border-radius: 10px;
    padding: 0.75rem;
    text-align: center;
    color: #64748b;
    font-size: 0.78rem;
    background: #fff;
    margin-top: 0.5rem;
  }

  /* Streamlit button tweaks (single-line labels) */
  .stButton > button {
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: background 0.15s ease, border-color 0.15s ease !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    height: 36px !important;
    padding: 0 12px !important;
  }

  .toolbar-btn .stButton > button {
    height: 32px !important;
    padding: 0 10px !important;
    font-size: 12px !important;
  }

  /* Sidebar report cards (HTML via st.markdown); not Streamlit buttons */
  .report-card {
    box-sizing: border-box;
    background: #ffffff;
    border: 1px solid #e8eaee;
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 8px;
    text-align: left;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 10px;
    align-items: start;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
  }
  .report-card > div:last-child {
    min-width: 0;
  }
  .report-card-icon {
    flex-shrink: 0;
    line-height: 0;
  }
  .report-card-icon svg {
    display: block;
    width: 26px;
    height: auto;
  }
  .report-card-selected {
    background: #f0f4f8;
    border-color: #bfdbfe;
    box-shadow: inset 4px 0 0 #3b82f6, 0 2px 12px rgba(37,99,235,0.10);
  }
  .report-title {
    font-weight: 600;
    font-size: 13px;
    color: #0f172a;
    line-height: 1.35;
    text-align: left;
    word-break: break-word;
    overflow: hidden;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    margin: 0;
  }
  .report-meta {
    margin-top: 6px;
    font-size: 12px;
    font-weight: 500;
    color: #64748b;
    line-height: 1.3;
    text-align: left;
  }
  .report-status {
    margin-top: 8px;
    text-align: left;
  }

  /* Compact “Open” control under each HTML card (widget key prefix pick_doc_) */
  div[class*="st-key-pick-doc-"] .stButton > button {
    height: 32px !important;
    min-height: 32px !important;
    padding: 0 12px !important;
    font-size: 12px !important;
    margin-bottom: 12px !important;
  }

  /* Right panel: dense extraction review stack (HTML cards only; widgets outside cards) */
  .dash-anchor + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(3) div[data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
  }
  .dash-anchor + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(3) div[data-testid="stMarkdownContainer"] p {
    margin: 0 !important;
    line-height: 1.2 !important;
  }

  .extraction-card {
    box-sizing: border-box;
    border: 1px solid #e8eaee;
    border-radius: 9px;
    padding: 8px 9px;
    margin: 0 0 5px 0;
    background: #ffffff;
    overflow: hidden;
    max-width: 100%;
  }
  .extraction-card--editing {
    border: 2px solid #EC1C24 !important;
    border-radius: 10px !important;
    box-shadow:
      0 0 0 1px rgba(236, 28, 36, 0.14),
      0 2px 10px rgba(236, 28, 36, 0.1) !important;
    background: linear-gradient(180deg, rgba(236, 28, 36, 0.06) 0%, #ffffff 52%) !important;
  }

  /* Right panel: extraction field editor open — match primary / brand accent */
  div[class*="st-key-fe_"] > div[data-testid="stVerticalBlockBorderWrapper"],
  div[class*="st-key-fe_"] div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 2px solid #EC1C24 !important;
    border-radius: 10px !important;
    background: rgba(254, 247, 247, 0.98) !important;
    padding: 10px 12px 12px 12px !important;
    margin: 0 0 10px 0 !important;
    box-shadow: 0 1px 5px rgba(236, 28, 36, 0.14) !important;
  }

  .extraction-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    margin: 0;
  }
  .extraction-label {
    font-size: 10px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    line-height: 1.25;
    flex: 1;
    min-width: 0;
    word-break: break-word;
    margin: 0;
    padding: 2px 0 0 0;
    text-align: left;
  }
  .extraction-value-shell {
    min-width: 0;
    margin-top: 5px;
    max-width: 100%;
  }
  .extraction-value {
    box-sizing: border-box;
    font-size: 12px;
    font-weight: 500;
    color: #0f172a;
    background: #f8fafc;
    border: 1px solid #e8eaee;
    border-radius: 7px;
    padding: 5px 7px;
    line-height: 1.35;
    word-break: break-word;
    overflow-wrap: anywhere;
    text-align: left;
    overflow: hidden;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    max-width: 100%;
    cursor: default;
  }
  .extraction-full-details {
    margin-top: 4px;
    max-width: 100%;
  }
  .extraction-full-summary {
    display: inline-block;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    color: #2563eb;
    list-style: none;
    padding: 2px 0;
    user-select: none;
  }
  .extraction-full-summary::-webkit-details-marker {
    display: none;
  }
  .extraction-full-pre {
    box-sizing: border-box;
    margin: 6px 0 0 0;
    padding: 6px 8px;
    background: #f8fafc;
    border: 1px solid #e8eaee;
    border-radius: 6px;
    font-size: 11px;
    line-height: 1.4;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-wrap: anywhere;
    max-height: 200px;
    overflow: auto;
    max-width: 100%;
    color: #0f172a;
  }
  .extraction-stack-gap {
    height: 6px;
  }

  /* Small Edit triggers — scoped to main dashboard right column only */
  .dash-anchor + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(3) div[data-testid="stPopover"] button {
    height: 26px !important;
    min-height: 26px !important;
    padding: 0 10px !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    margin-bottom: 5px !important;
    width: auto !important;
  }

  div[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 0.25rem;
    border-bottom: 1px solid #e8eaee;
  }
  div[data-testid="stTabs"] button {
    border-radius: 8px 8px 0 0 !important;
    font-weight: 500 !important;
  }

  pre.raw-text-preview {
    background: #f8fafc;
    border: 1px solid #e8eaee;
    padding: 14px;
    border-radius: 10px;
    max-height: 520px;
    overflow: auto;
    font-size: 12px;
    line-height: 1.45;
    color: #334155;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .kpi-card {
    background: #ffffff;
    border: 1px solid #e8eaee;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
    min-height: 88px;
  }
  .kpi-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 6px;
  }
  .kpi-value {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.2;
  }
  .kpi-sub {
    font-size: 12px;
    color: #64748b;
    margin-top: 4px;
  }
  .analysis-section-card {
    background: #ffffff;
    border: 1px solid #e8eaee;
    border-radius: 12px;
    padding: 14px;
    text-align: left;
    min-height: 72px;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
  }
  .analysis-section-card-active {
    border-color: #3b82f6;
    box-shadow: inset 0 0 0 1px #3b82f6, 0 2px 10px rgba(37,99,235,0.12);
    background: #f8fafc;
  }
  .analysis-section-title {
    font-weight: 600;
    font-size: 14px;
    color: #0f172a;
  }
  .analysis-section-count {
    font-size: 12px;
    color: #64748b;
    margin-top: 4px;
  }
</style>
"""


def inject_theme() -> None:
    import streamlit as st

    st.markdown(THEME_CSS, unsafe_allow_html=True)

