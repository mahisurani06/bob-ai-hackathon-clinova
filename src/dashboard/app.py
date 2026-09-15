"""
app.py — Clinical Trial Risk Monitor Dashboard (Member 3)

Run from the bob-ai-hackathon-clinova directory:
    streamlit run src/dashboard/app.py

All data loading and risk calculations are performed by the existing
risk engine (src.risk.interface.compute_site_risks).  This file contains
only presentation logic — it does not duplicate or reimplement any scoring.

Dashboard structure
-------------------
  Page header
    KPI cards (Total Sites, Critical, High-Risk, Total Deviations, Open Deviations)
    Risk Distribution chart
    Sidebar filters (Risk Level, Trend, Site)
    Site Risk Ranking table
    Selected Site Details (score, counts, trend, risk drivers)
    Deviation Trend by Visit Sequence chart
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — ensure `src.*` imports resolve when Streamlit is launched from
# the bob-ai-hackathon-clinova directory.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent          # …/src/dashboard/
_SRC  = _HERE.parent                             # …/src/
_ROOT = _SRC.parent                              # …/bob-ai-hackathon-clinova/
for _p in (_ROOT, _SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import plotly.graph_objects as go
import streamlit as st

from src.risk.interface import compute_site_risks
from src.risk.models    import SiteRiskScore
from src.risk.scorer    import VISIT_SEQUENCE
from src.deviation.detector import detect_deviations
from src.protocol.interface import load_project_data


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Clinical Trial Risk Monitor",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Theme state — must be initialised before any rendering
# ---------------------------------------------------------------------------

if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False

_dark: bool = st.session_state["dark_mode"]


# ---------------------------------------------------------------------------
# Design tokens — single source of truth for every colour/size in the UI
# ---------------------------------------------------------------------------

# Risk level palette
_C_CRITICAL  = "#c0392b"   # red
_C_HIGH      = "#d35400"   # deep orange
_C_MEDIUM    = "#d97706"   # amber
_C_LOW       = "#16a34a"   # green

# Trend palette
_C_INC       = "#c0392b"   # increasing → red
_C_DEC       = "#16a34a"   # decreasing → green
_C_STABLE    = "#1e3a5f"   # stable → navy
_C_INSUF     = "#64748b"   # insufficient → slate

# Brand / layout
_C_NAVY      = "#0f2044"   # deep navy — primary brand
_C_NAVY_MID  = "#1e3a5f"   # mid navy — section headings
_C_BLUE      = "#1d4ed8"   # interactive blue
_C_BG        = "#f1f4f8"   # page background
_C_SURFACE   = "#ffffff"   # card / panel surface
_C_BORDER    = "#dde3ed"   # subtle border
_C_TEXT      = "#1a2332"   # primary text
_C_MUTED     = "#64748b"   # secondary / muted text

# Chart palette (lines in multi-site chart)
_CHART_LINES = ["#1d4ed8", "#c0392b", "#16a34a", "#d97706"]

# Plotly chart background / grid
_PLOT_BG     = "#f8fafc"
_PAPER_BG    = "#ffffff"
_GRID_COLOR  = "#e2e8f0"
_AXIS_COLOR  = "#64748b"
_FONT_FAMILY = "Inter, -apple-system, 'Segoe UI', Arial, sans-serif"

# Badge foreground — always white on coloured backgrounds
_BADGE_FG: dict[str, str] = {
    "CRITICAL": "#ffffff",
    "HIGH":     "#ffffff",
    "MEDIUM":   "#ffffff",
    "LOW":      "#ffffff",
}

# ---------------------------------------------------------------------------
# Global CSS — single st.markdown injection
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <style>
    /* ── Import Inter from Google Fonts ─────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* ── Reset & base ────────────────────────────────────────────────── */
    html, body, [class*="css"] {{
        font-family: {_FONT_FAMILY};
        color: {_C_TEXT};
    }}

    /* ── Page background ─────────────────────────────────────────────── */
    .stApp {{
        background-color: {_C_BG};
    }}

    /* ── Streamlit block container spacing ───────────────────────────── */
    .block-container {{
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1400px !important;
    }}

    /* ── Sidebar ─────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {{
        background: {_C_NAVY} !important;
    }}
    section[data-testid="stSidebar"] * {{
        color: #cbd5e1 !important;
    }}
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown li {{
        color: #94a3b8 !important;
        font-size: 0.82rem !important;
    }}
    section[data-testid="stSidebar"] h3 {{
        color: #e2e8f0 !important;
        font-size: 0.9rem !important;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 1rem;
    }}
    section[data-testid="stSidebar"] h4 {{
        color: #94a3b8 !important;
        font-size: 0.78rem !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-top: 0.5rem;
    }}
    section[data-testid="stSidebar"] .stSelectbox > div > div {{
        background: rgba(255,255,255,0.07) !important;
        border: 1px solid rgba(255,255,255,0.12) !important;
        border-radius: 6px !important;
        color: #e2e8f0 !important;
    }}

    /* ── Dashboard header panel ──────────────────────────────────────── */
    .dash-header {{
        background: {_C_NAVY};
        border-radius: 10px;
        padding: 24px 32px 20px;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .dash-header-left h1 {{
        margin: 0 0 3px;
        font-size: 1.5rem;
        font-weight: 800;
        color: #f0f4fa;
        letter-spacing: -0.01em;
        line-height: 1.2;
    }}
    .dash-header-left p {{
        margin: 0;
        font-size: 0.82rem;
        color: #94a3b8;
        font-weight: 400;
        letter-spacing: 0.01em;
    }}
    .dash-header-right {{
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .status-pill {{
        background: rgba(22,163,74,0.15);
        border: 1px solid rgba(22,163,74,0.35);
        border-radius: 20px;
        padding: 5px 14px 5px 10px;
        font-size: 0.78rem;
        font-weight: 600;
        color: #86efac;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
    }}
    .status-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #4ade80;
        flex-shrink: 0;
    }}
    .meta-tag {{
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 0.75rem;
        color: #94a3b8;
        white-space: nowrap;
    }}

    /* ── Section titles ──────────────────────────────────────────────── */
    .section-title {{
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: {_C_MUTED};
        margin: 0 0 1rem 0;
        padding-bottom: 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .section-title::after {{
        content: "";
        flex: 1;
        height: 1px;
        background: {_C_BORDER};
        margin-left: 4px;
    }}

    /* ── KPI cards ───────────────────────────────────────────────────── */
    .kpi-box {{
        background: {_C_SURFACE};
        border: 1px solid {_C_BORDER};
        border-radius: 8px;
        padding: 16px 16px 14px;
        position: relative;
        overflow: hidden;
    }}
    .kpi-box::before {{
        content: "";
        position: absolute;
        left: 0; top: 0; bottom: 0;
        width: 3px;
        background: var(--kpi-accent, {_C_BLUE});
        border-radius: 8px 0 0 8px;
    }}
    .kpi-val {{
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.1;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.02em;
        color: var(--kpi-accent, {_C_TEXT});
        margin-bottom: 3px;
    }}
    .kpi-lbl {{
        font-size: 0.73rem;
        font-weight: 600;
        color: {_C_MUTED};
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }}

    /* ── Risk / Trend badges ─────────────────────────────────────────── */
    .badge {{
        display: inline-block;
        padding: 2px 9px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        line-height: 1.6;
        white-space: nowrap;
    }}
    .badge-trend {{
        display: inline-block;
        padding: 2px 9px;
        border-radius: 4px;
        font-size: 0.78rem;
        font-weight: 600;
        line-height: 1.6;
        white-space: nowrap;
    }}

    /* ── Site risk table ─────────────────────────────────────────────── */
    .risk-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.88rem;
        background: {_C_SURFACE};
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid {_C_BORDER};
    }}
    .risk-table thead tr {{
        background: #f8fafc;
        border-bottom: 1px solid {_C_BORDER};
    }}
    .risk-table thead th {{
        padding: 10px 14px;
        text-align: left;
        font-size: 0.71rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {_C_MUTED};
        white-space: nowrap;
    }}
    .risk-table thead th.num {{
        text-align: right;
    }}
    .risk-table tbody tr {{
        border-bottom: 1px solid #f1f4f8;
        transition: background 0.12s;
    }}
    .risk-table tbody tr:last-child {{
        border-bottom: none;
    }}
    .risk-table tbody tr:hover {{
        background: #f0f5ff;
    }}
    .risk-table tbody td {{
        padding: 11px 14px;
        vertical-align: middle;
        color: {_C_TEXT};
    }}
    .risk-table tbody td.num {{
        text-align: right;
        font-variant-numeric: tabular-nums;
        font-weight: 500;
    }}
    .risk-table .rank-cell {{
        font-size: 0.78rem;
        font-weight: 600;
        color: {_C_MUTED};
        min-width: 28px;
    }}
    .risk-table .site-id {{
        font-weight: 700;
        color: {_C_NAVY_MID};
        font-size: 0.92rem;
        letter-spacing: 0.02em;
    }}
    .risk-table .score-cell {{
        font-size: 1rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.01em;
    }}

    /* ── Site details panel ──────────────────────────────────────────── */
    .detail-panel {{
        background: {_C_SURFACE};
        border: 1px solid {_C_BORDER};
        border-radius: 8px;
        padding: 20px 24px 20px;
    }}
    .detail-label {{
        font-size: 0.71rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {_C_MUTED};
        margin: 0 0 3px;
    }}
    .detail-site-id {{
        font-size: 1.15rem;
        font-weight: 800;
        color: {_C_NAVY};
        margin: 0 0 16px;
        letter-spacing: 0.01em;
    }}
    .score-display {{
        font-size: 3rem;
        font-weight: 900;
        line-height: 1;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.03em;
        margin-bottom: 2px;
    }}
    .score-denom {{
        font-size: 1rem;
        font-weight: 500;
        color: {_C_MUTED};
        margin-left: 2px;
    }}
    .score-bar-wrap {{
        margin: 8px 0 14px;
        height: 6px;
        background: #e2e8f0;
        border-radius: 3px;
        overflow: hidden;
    }}
    .score-bar-fill {{
        height: 100%;
        border-radius: 3px;
        transition: width 0.4s ease;
    }}

    /* ── Compact metric grid ─────────────────────────────────────────── */
    .metric-grid {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
        margin-top: 4px;
    }}
    .metric-block {{
        background: #f8fafc;
        border: 1px solid {_C_BORDER};
        border-radius: 6px;
        padding: 10px 12px;
    }}
    .metric-block .m-label {{
        font-size: 0.69rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: {_C_MUTED};
        margin-bottom: 2px;
    }}
    .metric-block .m-val {{
        font-size: 1.35rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
        color: {_C_TEXT};
        line-height: 1.1;
    }}

    /* ── Period comparison row ───────────────────────────────────────── */
    .period-row {{
        display: flex;
        gap: 8px;
        margin-top: 8px;
        font-size: 0.82rem;
        color: {_C_MUTED};
    }}
    .period-chip {{
        background: #f1f4f8;
        border: 1px solid {_C_BORDER};
        border-radius: 5px;
        padding: 4px 10px;
        flex: 1;
        text-align: center;
    }}
    .period-chip strong {{
        display: block;
        font-size: 1rem;
        font-weight: 700;
        color: {_C_TEXT};
        margin-bottom: 1px;
    }}

    /* ── Risk drivers list ───────────────────────────────────────────── */
    .drivers-section {{
        margin-top: 16px;
        padding-top: 14px;
        border-top: 1px solid {_C_BORDER};
    }}
    .drivers-label {{
        font-size: 0.71rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {_C_MUTED};
        margin-bottom: 10px;
    }}
    .driver-row {{
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 8px 0;
        border-bottom: 1px solid #f1f4f8;
        font-size: 0.88rem;
        color: {_C_TEXT};
    }}
    .driver-row:last-child {{
        border-bottom: none;
        padding-bottom: 0;
    }}
    .driver-num {{
        flex-shrink: 0;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background: #e2e8f0;
        font-size: 0.7rem;
        font-weight: 700;
        color: {_C_MUTED};
        display: flex;
        align-items: center;
        justify-content: center;
        margin-top: 1px;
    }}
    .driver-row.major .driver-num {{
        background: #fee2e2;
        color: #b91c1c;
    }}
    .driver-text {{
        flex: 1;
        line-height: 1.4;
    }}
    .driver-row.major .driver-text {{
        font-weight: 600;
        color: #991b1b;
    }}

    /* ── Info note (temporal proxy) ──────────────────────────────────── */
    .info-note {{
        font-size: 0.78rem;
        color: {_C_MUTED};
        background: #f8fafc;
        border-left: 3px solid {_C_BORDER};
        border-radius: 0 5px 5px 0;
        padding: 7px 12px;
        margin: 0 0 12px;
        line-height: 1.5;
    }}

    /* ── Trend summary strip ─────────────────────────────────────────── */
    .trend-summary {{
        background: #f8fafc;
        border: 1px solid {_C_BORDER};
        border-radius: 6px;
        padding: 10px 16px;
        margin-top: 8px;
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
        font-size: 0.85rem;
        color: {_C_TEXT};
    }}
    .trend-summary .ts-item {{
        display: flex;
        flex-direction: column;
        gap: 1px;
    }}
    .trend-summary .ts-label {{
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: {_C_MUTED};
    }}
    .trend-summary .ts-value {{
        font-size: 0.9rem;
        font-weight: 700;
        color: {_C_TEXT};
    }}

    /* ── Filter active note ──────────────────────────────────────────── */
    .filter-active {{
        font-size: 0.78rem;
        color: {_C_MUTED};
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 5px;
        padding: 5px 12px;
        margin-bottom: 10px;
        display: inline-block;
    }}

    /* ── Dashboard footer ────────────────────────────────────────────── */
    .dash-footer {{
        margin-top: 2rem;
        padding-top: 1.25rem;
        border-top: 1px solid {_C_BORDER};
        font-size: 0.73rem;
        color: {_C_MUTED};
        text-align: center;
        letter-spacing: 0.02em;
        line-height: 1.8;
    }}

    /* ── Streamlit divider override ──────────────────────────────────── */
    hr {{
        border: none !important;
        border-top: 1px solid {_C_BORDER} !important;
        margin: 1.5rem 0 !important;
    }}

    /* ── Suppress default Streamlit metric widget chrome ─────────────── */
    [data-testid="stMetric"] {{
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Dark-mode CSS overrides
# Scoped to #dash-root.dk — applied when session_state.dark_mode is True.
# The sidebar toggle button flips the flag and triggers a Streamlit rerun.
# ---------------------------------------------------------------------------

_DK_BG       = "#0d1117"   # page background
_DK_SURFACE  = "#161b22"   # card / panel surface
_DK_SURFACE2 = "#1c2230"   # table header / metric block / chip
_DK_BORDER   = "#2d3748"   # border
_DK_TEXT     = "#e2e8f0"   # primary text
_DK_MUTED    = "#8b98ab"   # muted / secondary text
_DK_NAVY     = "#1e2a45"   # header panel bg (lighter than pure black)

st.markdown(
    f"""
    <style>
    /* ================================================================
       DARK MODE — activates when #dash-root carries class "dk".
       Every selector is prefixed "#dash-root.dk" so light styles
       are completely unaffected.
    ================================================================ */

    /* ── Page & app background ───────────────────────────────────── */
    #dash-root.dk,
    #dash-root.dk * {{
        color: {_DK_TEXT};
    }}

    /* ── Header panel ────────────────────────────────────────────── */
    #dash-root.dk .dash-header {{
        background: {_DK_NAVY};
        border: 1px solid {_DK_BORDER};
    }}
    #dash-root.dk .dash-header-left h1 {{ color: #e2e8f0; }}
    #dash-root.dk .dash-header-left p  {{ color: {_DK_MUTED}; }}
    #dash-root.dk .meta-tag {{
        background: rgba(255,255,255,0.06);
        border-color: rgba(255,255,255,0.1);
        color: {_DK_MUTED};
    }}
    #dash-root.dk .status-pill {{
        background: rgba(22,163,74,0.2);
        border-color: rgba(22,163,74,0.4);
    }}

    /* ── Section titles ──────────────────────────────────────────── */
    #dash-root.dk .section-title        {{ color: {_DK_MUTED}; }}
    #dash-root.dk .section-title::after {{ background: {_DK_BORDER}; }}

    /* ── KPI cards ───────────────────────────────────────────────── */
    #dash-root.dk .kpi-box  {{ background: {_DK_SURFACE}; border-color: {_DK_BORDER}; }}
    #dash-root.dk .kpi-lbl  {{ color: {_DK_MUTED}; }}

    /* ── Site risk table ─────────────────────────────────────────── */
    #dash-root.dk .risk-table                  {{ background: {_DK_SURFACE}; border-color: {_DK_BORDER}; }}
    #dash-root.dk .risk-table thead tr         {{ background: {_DK_SURFACE2}; border-bottom-color: {_DK_BORDER}; }}
    #dash-root.dk .risk-table thead th         {{ color: {_DK_MUTED}; }}
    #dash-root.dk .risk-table tbody tr         {{ border-bottom-color: rgba(255,255,255,0.04); }}
    #dash-root.dk .risk-table tbody tr:hover   {{ background: rgba(29,78,216,0.15); }}
    #dash-root.dk .risk-table tbody td         {{ color: {_DK_TEXT}; }}
    #dash-root.dk .risk-table .rank-cell       {{ color: {_DK_MUTED}; }}
    #dash-root.dk .risk-table .site-id         {{ color: #93c5fd; }}

    /* ── Detail panels ───────────────────────────────────────────── */
    #dash-root.dk .detail-panel   {{ background: {_DK_SURFACE}; border-color: {_DK_BORDER}; }}
    #dash-root.dk .detail-label   {{ color: {_DK_MUTED}; }}
    #dash-root.dk .detail-site-id {{ color: #93c5fd; }}
    #dash-root.dk .score-denom    {{ color: {_DK_MUTED}; }}
    #dash-root.dk .score-bar-wrap {{ background: {_DK_BORDER}; }}

    /* ── Metric grid ─────────────────────────────────────────────── */
    #dash-root.dk .metric-block          {{ background: {_DK_SURFACE2}; border-color: {_DK_BORDER}; }}
    #dash-root.dk .metric-block .m-label {{ color: {_DK_MUTED}; }}
    #dash-root.dk .metric-block .m-val   {{ color: {_DK_TEXT}; }}

    /* ── Period chips ────────────────────────────────────────────── */
    #dash-root.dk .period-chip        {{ background: {_DK_SURFACE2}; border-color: {_DK_BORDER}; color: {_DK_MUTED}; }}
    #dash-root.dk .period-chip strong {{ color: {_DK_TEXT}; }}

    /* ── Risk drivers ────────────────────────────────────────────── */
    #dash-root.dk .drivers-section               {{ border-top-color: {_DK_BORDER}; }}
    #dash-root.dk .drivers-label                 {{ color: {_DK_MUTED}; }}
    #dash-root.dk .driver-row                    {{ border-bottom-color: rgba(255,255,255,0.05); color: {_DK_TEXT}; }}
    #dash-root.dk .driver-num                    {{ background: {_DK_SURFACE2}; color: {_DK_MUTED}; }}
    #dash-root.dk .driver-row.major .driver-num  {{ background: rgba(185,28,28,0.25); color: #fca5a5; }}
    #dash-root.dk .driver-row.major .driver-text {{ color: #fca5a5; }}

    /* ── Info note ───────────────────────────────────────────────── */
    #dash-root.dk .info-note {{ background: {_DK_SURFACE2}; border-left-color: {_DK_BORDER}; color: {_DK_MUTED}; }}

    /* ── Trend summary ───────────────────────────────────────────── */
    #dash-root.dk .trend-summary           {{ background: {_DK_SURFACE2}; border-color: {_DK_BORDER}; color: {_DK_TEXT}; }}
    #dash-root.dk .trend-summary .ts-label {{ color: {_DK_MUTED}; }}
    #dash-root.dk .trend-summary .ts-value {{ color: {_DK_TEXT}; }}

    /* ── Filter note ─────────────────────────────────────────────── */
    #dash-root.dk .filter-active {{ background: rgba(29,78,216,0.12); border-color: rgba(29,78,216,0.3); color: {_DK_MUTED}; }}

    /* ── Footer ──────────────────────────────────────────────────── */
    #dash-root.dk .dash-footer {{ border-top-color: {_DK_BORDER}; color: {_DK_MUTED}; }}

    /* ── Divider ─────────────────────────────────────────────────── */
    #dash-root.dk hr {{ border-top-color: {_DK_BORDER} !important; }}

    /* ── Streamlit page background (dark) ────────────────────────── */
    body.dark-page {{ background-color: {_DK_BG} !important; }}
    .stApp.dark-page {{ background-color: {_DK_BG} !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Inject the page-level background colour and open the root wrapper div.
# class="dk" activates all dark CSS rules above; absent = light mode.
_root_cls = "dk" if _dark else ""
_page_bg  = _DK_BG if _dark else "#f1f4f8"
st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {_page_bg} !important; }}
    </style>
    <div id="dash-root" class="{_root_cls}">
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers — unchanged logic, updated HTML templates only
# ---------------------------------------------------------------------------

LEVEL_COLOURS = {
    "CRITICAL": _C_CRITICAL,
    "HIGH":     _C_HIGH,
    "MEDIUM":   _C_MEDIUM,
    "LOW":      _C_LOW,
}

LEVEL_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

TREND_ICONS = {
    "Increasing":        "↑",
    "Decreasing":        "↓",
    "Stable":            "→",
    "Insufficient Data": "—",
}


def _fmt_trend_change(pct: float | None) -> str:
    """Format trend_change_percent for display; never show Python None."""
    if pct is None:
        return "N/A (New activity)"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f} %"


def _risk_badge(level: str) -> str:
    """Return a styled HTML badge for a risk level."""
    bg = LEVEL_COLOURS.get(level, "#4b5563")
    fg = _BADGE_FG.get(level, "#ffffff")
    return (
        f'<span class="badge" style="background:{bg};color:{fg}">'
        f"{level}</span>"
    )


def _trend_badge(trend: str) -> str:
    """Return a styled HTML trend badge."""
    icon = TREND_ICONS.get(trend, "")
    trend_colours = {
        "Increasing":        (_C_INC,    "#fee2e2"),
        "Decreasing":        (_C_DEC,    "#dcfce7"),
        "Stable":            (_C_STABLE, "#dbeafe"),
        "Insufficient Data": (_C_INSUF,  "#f1f5f9"),
    }
    fg, bg = trend_colours.get(trend, (_C_INSUF, "#f1f5f9"))
    return (
        f'<span class="badge-trend" style="background:{bg};color:{fg}">'
        f"{icon}&nbsp;{trend}</span>"
    )


# ---------------------------------------------------------------------------
# Data loading — cached so Streamlit only runs the pipeline once per session
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _load_scores() -> list[SiteRiskScore]:
    """Load and compute site risk scores via the risk engine."""
    return compute_site_risks()


@st.cache_data(ttl=300)
def _load_raw_deviations() -> dict:
    """Load raw deviation records grouped by site_id for trend chart."""
    data = load_project_data()
    devs = detect_deviations(
        observations   = data["observations"],
        protocol_rules = data["protocol_rules"],
    )
    by_site: dict[str, dict[str, int]] = {}
    for d in devs:
        if d.site_id not in by_site:
            by_site[d.site_id] = {v: 0 for v in VISIT_SEQUENCE}
        vt = d.visit_type
        if vt in by_site[d.site_id]:
            by_site[d.site_id][vt] += 1
    return by_site


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="dash-header">
      <div class="dash-header-left">
        <h1>Clinical Trial Risk Monitor</h1>
        <p>Protocol Deviation Intelligence &nbsp;·&nbsp; TRIAL-001 &nbsp;·&nbsp; 4 Sites &nbsp;·&nbsp; India</p>
      </div>
      <div class="dash-header-right">
        <span class="status-pill">
          <span class="status-dot"></span>
          Monitoring Active
        </span>
        <span class="meta-tag">IBM Hackathon</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Load data (with error handling)
# ---------------------------------------------------------------------------

try:
    with st.spinner("Loading risk data …"):
        scores: list[SiteRiskScore] = _load_scores()
        dev_by_site: dict = _load_raw_deviations()
    load_error: str | None = None
except Exception as exc:
    scores = []
    dev_by_site = {}
    load_error = str(exc)

if load_error:
    st.error(f"⚠️ Failed to load risk data: {load_error}")
    st.stop()

if not scores:
    st.warning("No risk data available. Ensure the dataset has been generated.")
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------

with st.sidebar:
    # ── Theme toggle ────────────────────────────────────────────────
    _btn_label = "☀️  Switch to Light Mode" if _dark else "🌙  Switch to Dark Mode"
    if st.button(_btn_label, width="stretch"):
        st.session_state["dark_mode"] = not _dark
        st.rerun()

    st.divider()
    st.markdown("### 🔍 Filters")

    all_levels   = ["All"] + LEVEL_ORDER
    all_trends   = ["All", "Increasing", "Stable", "Decreasing", "Insufficient Data"]
    all_site_ids = ["All"] + sorted({s.site_id for s in scores})

    sel_level        = st.selectbox("Risk Level", all_levels,   index=0)
    sel_trend        = st.selectbox("Trend",      all_trends,   index=0)
    sel_site_filter  = st.selectbox("Site ID",    all_site_ids, index=0)

    st.divider()
    st.markdown("#### ℹ️ Score formula")
    st.markdown(
        "- Severity &nbsp;&nbsp;&nbsp; **40 %**\n"
        "- Frequency &nbsp; **25 %**\n"
        "- Recent &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; **20 %**\n"
        "- Trend &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; **15 %**",
        unsafe_allow_html=True,
    )
    st.caption("Score 0–100 · Higher = more risk")


# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------

def _apply_filters(
    src: list[SiteRiskScore],
    level: str,
    trend: str,
    site: str,
) -> list[SiteRiskScore]:
    out = src
    if level != "All":
        out = [s for s in out if s.risk_level == level]
    if trend != "All":
        out = [s for s in out if s.trend == trend]
    if site != "All":
        out = [s for s in out if s.site_id == site]
    return out


filtered: list[SiteRiskScore] = _apply_filters(
    scores, sel_level, sel_trend, sel_site_filter
)


# ---------------------------------------------------------------------------
# A. KPI Cards — always from ALL scores (not filtered)
# ---------------------------------------------------------------------------

st.markdown('<p class="section-title">Summary</p>', unsafe_allow_html=True)

total_sites    = len(scores)
critical_sites = sum(1 for s in scores if s.risk_level == "CRITICAL")
high_sites     = sum(1 for s in scores if s.risk_level == "HIGH")
total_devs     = sum(s.total_deviations for s in scores)
open_devs      = sum(s.open_deviations  for s in scores)

kpi_cols = st.columns(5)
kpi_data = [
    ("Total Sites",      total_sites,    _C_BLUE,     _C_BLUE),
    ("Critical Sites",   critical_sites, _C_CRITICAL, _C_CRITICAL),
    ("High-Risk Sites",  high_sites,     _C_HIGH,     _C_HIGH),
    ("Total Deviations", total_devs,     _C_NAVY_MID, _C_NAVY_MID),
    ("Open Deviations",  open_devs,      _C_MUTED,    _C_MUTED),
]
for col, (label, value, val_colour, accent) in zip(kpi_cols, kpi_data):
    with col:
        st.markdown(
            f'<div class="kpi-box" style="--kpi-accent:{accent}">'
            f'<div class="kpi-val" style="color:{val_colour}">{value}</div>'
            f'<div class="kpi-lbl">{label}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# B. Risk Distribution chart
# ---------------------------------------------------------------------------

st.markdown('<p class="section-title">Risk Distribution</p>', unsafe_allow_html=True)

dist_counts = {lvl: sum(1 for s in scores if s.risk_level == lvl) for lvl in LEVEL_ORDER}

fig_dist = go.Figure(
    go.Bar(
        x=list(dist_counts.keys()),
        y=list(dist_counts.values()),
        marker_color=[LEVEL_COLOURS[lvl] for lvl in LEVEL_ORDER],
        marker_line_width=0,
        text=list(dist_counts.values()),
        textposition="outside",
        textfont=dict(size=13, color=_C_TEXT, family=_FONT_FAMILY, weight=700),
        hovertemplate="%{x}: %{y} site(s)<extra></extra>",
    )
)
fig_dist.update_layout(
    height=220,
    margin=dict(l=0, r=0, t=28, b=0),
    yaxis=dict(
        title=dict(text="Sites", font=dict(color=_AXIS_COLOR, size=11)),
        dtick=1,
        rangemode="tozero",
        gridcolor=_GRID_COLOR,
        tickfont=dict(color=_AXIS_COLOR, size=11),
        zeroline=False,
        showgrid=True,
    ),
    xaxis=dict(
        title=dict(text="Risk Level", font=dict(color=_AXIS_COLOR, size=11)),
        tickfont=dict(size=12, color=_C_TEXT, family=_FONT_FAMILY, weight=600),
        showgrid=False,
    ),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family=_FONT_FAMILY, color=_C_TEXT),
    showlegend=False,
    bargap=0.45,
)
st.plotly_chart(fig_dist, width="stretch")


# ---------------------------------------------------------------------------
# C. Site Risk Ranking table
# ---------------------------------------------------------------------------

st.markdown('<p class="section-title">Site Risk Ranking</p>', unsafe_allow_html=True)

filter_note = []
if sel_level       != "All": filter_note.append(f"Level: <strong>{sel_level}</strong>")
if sel_trend       != "All": filter_note.append(f"Trend: <strong>{sel_trend}</strong>")
if sel_site_filter != "All": filter_note.append(f"Site: <strong>{sel_site_filter}</strong>")
if filter_note:
    st.markdown(
        '<span class="filter-active">Active filters: ' + " &nbsp;·&nbsp; ".join(filter_note) + "</span>",
        unsafe_allow_html=True,
    )

if not filtered:
    st.info("No sites match the current filters.")
else:
    # Build a single HTML table — better alignment than Streamlit columns
    rows_html = ""
    for rank, s in enumerate(filtered, start=1):
        score_colour = LEVEL_COLOURS.get(s.risk_level, _C_TEXT)
        rows_html += (
            f"<tr>"
            f'<td class="rank-cell">{rank}</td>'
            f'<td class="site-id">{s.site_id}</td>'
            f'<td class="score-cell" style="color:{score_colour}">{s.risk_score:.1f}</td>'
            f"<td>{_risk_badge(s.risk_level)}</td>"
            f"<td>{_trend_badge(s.trend)}</td>"
            f'<td class="num">{s.major_deviations}</td>'
            f'<td class="num">{s.minor_deviations}</td>'
            f'<td class="num">{s.total_deviations}</td>'
            f'<td class="num">{s.open_deviations}</td>'
            f"</tr>"
        )
    st.markdown(
        f"""
        <table class="risk-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Site ID</th>
              <th>Score</th>
              <th>Risk Level</th>
              <th>Trend</th>
              <th class="num">Major</th>
              <th class="num">Minor</th>
              <th class="num">Total</th>
              <th class="num">Open</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# D. Selected Site Details + Risk Drivers
# ---------------------------------------------------------------------------

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
st.markdown('<p class="section-title">Site Details</p>', unsafe_allow_html=True)

site_options = [s.site_id for s in scores]  # always full list for detail selector
sel_detail = st.selectbox(
    "Select a site to inspect",
    options=site_options,
    index=0,
    key="detail_site",
)

detail: SiteRiskScore | None = next(
    (s for s in scores if s.site_id == sel_detail), None
)

if detail is None:
    st.info("Select a site to see its risk details.")
else:
    _score_colour = LEVEL_COLOURS.get(detail.risk_level, _C_TEXT)
    _score_pct    = min(100.0, max(0.0, detail.risk_score))

    det_left, det_right = st.columns([1, 1], gap="medium")

    with det_left:
        st.markdown(
            f"""
            <div class="detail-panel">
              <p class="detail-label">Site ID</p>
              <p class="detail-site-id">{detail.site_id}</p>

              <p class="detail-label">Risk Score</p>
              <div class="score-display" style="color:{_score_colour}">
                {detail.risk_score:.1f}<span class="score-denom">/ 100</span>
              </div>
              <div class="score-bar-wrap">
                <div class="score-bar-fill"
                     style="width:{_score_pct:.1f}%;background:{_score_colour}">
                </div>
              </div>

              <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
                <div>
                  <p class="detail-label" style="margin-bottom:4px">Risk Level</p>
                  {_risk_badge(detail.risk_level)}
                </div>
                <div style="margin-left:16px">
                  <p class="detail-label" style="margin-bottom:4px">Trend</p>
                  {_trend_badge(detail.trend)}
                </div>
              </div>

              <p style="font-size:0.82rem;color:{_C_MUTED};margin:6px 0 0">
                Trend change: <strong style="color:{_C_TEXT}">
                {_fmt_trend_change(detail.trend_change_percent)}</strong>
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with det_right:
        st.markdown(
            f"""
            <div class="detail-panel">
              <p class="detail-label">Deviation Breakdown</p>
              <div class="metric-grid">
                <div class="metric-block">
                  <div class="m-label">Major</div>
                  <div class="m-val">{detail.major_deviations}</div>
                </div>
                <div class="metric-block">
                  <div class="m-label">Minor</div>
                  <div class="m-val">{detail.minor_deviations}</div>
                </div>
                <div class="metric-block">
                  <div class="m-label">Administrative</div>
                  <div class="m-val">{detail.administrative_deviations}</div>
                </div>
                <div class="metric-block">
                  <div class="m-label">Open</div>
                  <div class="m-val">{detail.open_deviations}</div>
                </div>
              </div>

              <div class="period-row">
                <div class="period-chip">
                  <strong>{detail.previous_period_deviations}</strong>
                  Previous period
                </div>
                <div class="period-chip">
                  <strong>{detail.recent_deviations}</strong>
                  Recent period
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Risk drivers — numbered list
    if detail.top_risk_drivers:
        driver_rows = ""
        for i, driver in enumerate(detail.top_risk_drivers, start=1):
            row_cls  = "driver-row major" if "Major" in driver else "driver-row"
            driver_rows += (
                f'<div class="{row_cls}">'
                f'<div class="driver-num">{i:02d}</div>'
                f'<div class="driver-text">{driver}</div>'
                f"</div>"
            )
        st.markdown(
            f"""
            <div class="drivers-section">
              <p class="drivers-label">Top Risk Drivers</p>
              {driver_rows}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.success("✅ No risk drivers — this site has no recorded deviations.")


# ---------------------------------------------------------------------------
# E. Deviation Trend by Visit Sequence
# ---------------------------------------------------------------------------

st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)
st.markdown('<p class="section-title">Deviation Trend by Visit Sequence</p>', unsafe_allow_html=True)

st.markdown(
    '<div class="info-note">'
    'ⓘ &nbsp;Visit sequence is used as a temporal proxy — the prototype dataset does not '
    'contain calendar timestamps. Sequence: BASELINE → WEEK_4 → WEEK_8 → WEEK_12.'
    '</div>',
    unsafe_allow_html=True,
)

trend_site = st.selectbox(
    "Select site for trend view",
    options=site_options,
    index=site_options.index(sel_detail) if sel_detail in site_options else 0,
    key="trend_site",
)

trend_counts = dev_by_site.get(trend_site, {v: 0 for v in VISIT_SEQUENCE})
visit_labels = VISIT_SEQUENCE
visit_values = [trend_counts.get(v, 0) for v in VISIT_SEQUENCE]

# Colour bars: previous period = blue-steel, recent period = risk-red
bar_colours = [
    "#2563eb" if v in ("BASELINE", "WEEK_4") else "#dc2626"
    for v in VISIT_SEQUENCE
]

fig_trend = go.Figure()

fig_trend.add_trace(
    go.Bar(
        x=visit_labels,
        y=visit_values,
        marker_color=bar_colours,
        marker_line_width=0,
        name="Deviations",
        text=visit_values,
        textposition="outside",
        textfont=dict(size=12, color=_C_TEXT, family=_FONT_FAMILY),
        hovertemplate="%{x}: %{y} deviation(s)<extra></extra>",
    )
)

# Highlight the split between previous and recent
fig_trend.add_vline(
    x=1.5,
    line_dash="dash",
    line_color="#94a3b8",
    line_width=1,
    annotation_text="← Previous | Recent →",
    annotation_position="top",
    annotation_font_size=10,
    annotation_font_color=_AXIS_COLOR,
)

fig_trend.update_layout(
    height=300,
    margin=dict(l=0, r=0, t=40, b=0),
    yaxis=dict(
        title=dict(text="Deviations", font=dict(color=_AXIS_COLOR, size=11)),
        dtick=1,
        rangemode="tozero",
        gridcolor=_GRID_COLOR,
        tickfont=dict(color=_AXIS_COLOR, size=11),
        zeroline=False,
    ),
    xaxis=dict(
        title=dict(text="Visit (sequence proxy — not calendar time)",
                   font=dict(color=_AXIS_COLOR, size=11)),
        tickfont=dict(size=12, color=_C_TEXT, family=_FONT_FAMILY),
        showgrid=False,
    ),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family=_FONT_FAMILY, color=_C_TEXT),
    showlegend=False,
    bargap=0.4,
)
st.plotly_chart(fig_trend, width="stretch")

# Trend summary strip below chart
site_risk_for_trend = next((s for s in scores if s.site_id == trend_site), None)
if site_risk_for_trend:
    prev         = site_risk_for_trend.previous_period_deviations
    rec          = site_risk_for_trend.recent_deviations
    trend_label  = site_risk_for_trend.trend
    pct          = _fmt_trend_change(site_risk_for_trend.trend_change_percent)
    st.markdown(
        f"""
        <div class="trend-summary">
          <div class="ts-item">
            <span class="ts-label">Site</span>
            <span class="ts-value">{trend_site}</span>
          </div>
          <div class="ts-item">
            <span class="ts-label">Trend</span>
            <span class="ts-value">{_trend_badge(trend_label)}</span>
          </div>
          <div class="ts-item">
            <span class="ts-label">Previous period</span>
            <span class="ts-value">{prev}</span>
          </div>
          <div class="ts-item">
            <span class="ts-label">Recent period</span>
            <span class="ts-value">{rec}</span>
          </div>
          <div class="ts-item">
            <span class="ts-label">Change</span>
            <span class="ts-value">{pct}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# F. Multi-site trend overlay
# ---------------------------------------------------------------------------

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
st.markdown('<p class="section-title">All Sites — Visit Sequence Comparison</p>', unsafe_allow_html=True)

st.markdown(
    '<div class="info-note">'
    'ⓘ &nbsp;Each line represents one site\'s deviation count per visit. '
    'Visit sequence is a temporal proxy — not calendar time.'
    '</div>',
    unsafe_allow_html=True,
)

fig_multi = go.Figure()
line_colours = _CHART_LINES
for i, s in enumerate(scores):
    counts = dev_by_site.get(s.site_id, {v: 0 for v in VISIT_SEQUENCE})
    y_vals = [counts.get(v, 0) for v in VISIT_SEQUENCE]
    fig_multi.add_trace(
        go.Scatter(
            x=VISIT_SEQUENCE,
            y=y_vals,
            mode="lines+markers",
            name=s.site_id,
            line=dict(color=line_colours[i % len(line_colours)], width=2.5),
            marker=dict(size=7, symbol="circle"),
            hovertemplate=f"{s.site_id} — %{{x}}: %{{y}} deviation(s)<extra></extra>",
        )
    )

fig_multi.update_layout(
    height=300,
    margin=dict(l=0, r=0, t=16, b=0),
    yaxis=dict(
        title=dict(text="Deviations", font=dict(color=_AXIS_COLOR, size=11)),
        dtick=1,
        rangemode="tozero",
        gridcolor=_GRID_COLOR,
        tickfont=dict(color=_AXIS_COLOR, size=11),
        zeroline=False,
    ),
    xaxis=dict(
        title=dict(text="Visit (sequence proxy — not calendar time)",
                   font=dict(color=_AXIS_COLOR, size=11)),
        tickfont=dict(size=12, color=_C_TEXT, family=_FONT_FAMILY),
        showgrid=False,
    ),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family=_FONT_FAMILY, color=_C_TEXT),
    legend=dict(
        orientation="h",
        y=-0.3,
        font=dict(size=12, color=_C_TEXT, family=_FONT_FAMILY),
        bgcolor="rgba(0,0,0,0)",
    ),
)
st.plotly_chart(fig_multi, width="stretch")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="dash-footer">
      Clinical Trial Risk Monitor &nbsp;·&nbsp; Member 3 &nbsp;·&nbsp; IBM Hackathon<br>
      Data: synthetic prototype (seed=42 · 20 patients · 4 sites) &nbsp;·&nbsp;
      Risk engine: <code>src.risk</code> &nbsp;·&nbsp; No calendar timestamps used
    </div>
    </div><!-- /#dash-root -->
    """,
    unsafe_allow_html=True,
)
