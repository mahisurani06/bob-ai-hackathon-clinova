"""
report.py — CAPA-ready report generator for the AI Advisor module (Member 4).

Builds a structured, plain-text Markdown report from the full AI advisor
pipeline output (SiteExplanation + CAPARecommendation list).

The report is designed to be:
  - Human-readable: a clinical monitor can read it directly.
  - Machine-parseable: consistent Markdown structure with clear section headers.
  - Self-contained: every fact it states comes from the live data pipeline;
    nothing is hardcoded.

Usage
-----
    from src.ai.report import build_report

    report_md = build_report(
        site_score     = site_risk_score,
        site_deviations= site_deviation_records,
        explanation    = site_explanation,
        capas          = capa_recommendations,
    )
    print(report_md)         # display in terminal
    # or write to file:
    Path("report.md").write_text(report_md)
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.deviation.models import DeviationRecord
from src.risk.models       import SiteRiskScore

from .models import CAPARecommendation, SiteExplanation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report(
    site_score:      SiteRiskScore,
    site_deviations: list[DeviationRecord],
    explanation:     SiteExplanation,
    capas:           list[CAPARecommendation],
) -> str:
    """Build a CAPA-ready Markdown report for one clinical site.

    Args:
        site_score:       ``SiteRiskScore`` for the site.
        site_deviations:  All deviation records for this site.
        explanation:      ``SiteExplanation`` produced by ``explain_site_risk()``.
        capas:            ``CAPARecommendation`` list from ``generate_capa()``.

    Returns:
        A multi-section Markdown string suitable for display or file export.
    """
    sections: list[str] = []

    sections.append(_section_header(site_score))
    sections.append(_section_ai_explanation(explanation))
    sections.append(_section_risk_summary(site_score))
    sections.append(_section_deviation_detail(site_deviations))
    sections.append(_section_capa(capas, site_score))
    sections.append(_section_footer(explanation))

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_header(score: SiteRiskScore) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"# CAPA Report — Site {score.site_id}\n\n"
        f"**Trial:** TRIAL-001 &nbsp;|&nbsp; "
        f"**Site:** {score.site_id} &nbsp;|&nbsp; "
        f"**Risk Level:** {score.risk_level} &nbsp;|&nbsp; "
        f"**Generated:** {now}\n\n"
        f"---"
    )


def _section_ai_explanation(explanation: SiteExplanation) -> str:
    ai_tag = " *(IBM watsonx.ai enhanced)*" if explanation.ai_enhanced else " *(deterministic template)*"
    lines = [
        f"## AI Risk Explanation{ai_tag}\n",
        explanation.summary,
        "",
        "**Evidence:**",
    ]
    for point in explanation.evidence_points:
        lines.append(f"- {point}")
    lines.append("")
    lines.append(f"**Recommended action:** {explanation.recommendation_headline}")
    return "\n".join(lines)


def _section_risk_summary(score: SiteRiskScore) -> str:
    change_str = (
        f"{score.trend_change_percent:+.1f} %"
        if score.trend_change_percent is not None
        else "N/A"
    )
    rows = [
        ("Risk Score",            f"{score.risk_score:.1f} / 100"),
        ("Risk Level",            score.risk_level),
        ("Trend",                 score.trend),
        ("Period-over-period",    change_str),
        ("Total Deviations",      str(score.total_deviations)),
        ("Major",                 str(score.major_deviations)),
        ("Minor",                 str(score.minor_deviations)),
        ("Administrative",        str(score.administrative_deviations)),
        ("Open Deviations",       str(score.open_deviations)),
        ("Previous Period",       str(score.previous_period_deviations)),
        ("Recent Period",         str(score.recent_deviations)),
    ]
    table_lines = [
        "## Risk Score Summary\n",
        "| Metric | Value |",
        "|---|---|",
    ]
    for label, value in rows:
        table_lines.append(f"| {label} | {value} |")

    if score.top_risk_drivers:
        table_lines.append("")
        table_lines.append("**Top Risk Drivers:**")
        for i, driver in enumerate(score.top_risk_drivers, 1):
            table_lines.append(f"{i}. {driver}")

    return "\n".join(table_lines)


def _section_deviation_detail(deviations: list[DeviationRecord]) -> str:
    if not deviations:
        return "## Deviation Detail\n\n*No protocol deviations detected at this site.*"

    lines = [
        "## Deviation Detail\n",
        "| Obs ID | Patient | Visit | Expected Day | Actual Day | Diff | Window | Severity | Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for d in sorted(deviations, key=lambda x: (x.severity, x.observation_id)):
        diff_str = f"{d.difference} days"
        lines.append(
            f"| {d.observation_id} | {d.patient_id} | {d.visit_type} "
            f"| {d.expected} | {d.actual} | {diff_str} "
            f"| ±{d.allowed_window} | {d.severity} | {d.status} |"
        )
    return "\n".join(lines)


def _section_capa(
    capas: list[CAPARecommendation],
    score: SiteRiskScore,
) -> str:
    if not capas:
        return (
            "## CAPA Recommendations\n\n"
            f"*No CAPA items required — site {score.site_id} is classified as "
            f"{score.risk_level} risk with no actionable deviations.*"
        )

    lines = ["## CAPA Recommendations\n"]
    for i, c in enumerate(capas, 1):
        lines.append(
            f"### {i}. {c.capa_id}"
            f"  |  Priority: {c.priority}"
            f"  |  Risk Level: {c.risk_level}"
            f"  |  Status: {c.status}\n"
        )
        lines.append(f"**Issue / Deviation:**  \n{c.issue}\n")
        lines.append(f"**Severity:** {c.severity}  |  **Risk Level:** {c.risk_level}\n")
        lines.append(f"**Root Cause / Contributing Factor:**  \n{c.root_cause}\n")
        lines.append(f"**Corrective Action:**  \n{c.corrective_action}\n")
        lines.append(f"**Preventive Action:**  \n{c.preventive_action}\n")
        lines.append(f"**Rationale:**  \n{c.rationale}\n")
        lines.append("---")
    return "\n".join(lines)


def _section_footer(explanation: SiteExplanation) -> str:
    ai_status = (
        "IBM watsonx.ai (Granite 13B Instruct v2)"
        if explanation.ai_enhanced
        else "Deterministic template engine (watsonx.ai credentials not configured)"
    )
    return (
        f"---\n\n"
        f"*Report generated by Clinical Trial Risk Monitor — Member 4 AI Advisor module.*  \n"
        f"*AI engine: {ai_status}*  \n"
        f"*Data source: synthetic prototype (seed=42 · 20 patients · 4 sites)*"
    )
