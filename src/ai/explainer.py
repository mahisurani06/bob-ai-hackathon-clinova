"""
explainer.py — AI-powered risk explanation for clinical sites (Member 4).

This module takes the output of Member 3's risk engine (a ``SiteRiskScore``)
and the deviation records for that site (from Member 2's detector), and
produces a natural-language explanation of WHY the site has its current risk
level.

Two-tier explanation strategy
------------------------------
1. **Deterministic template** (always runs): constructs a factual, structured
   explanation directly from ``SiteRiskScore`` fields and the deviation list.
   This tier never fails and does not require any external credentials.

2. **IBM watsonx.ai enrichment** (optional): if WATSONX_API_KEY,
   WATSONX_PROJECT_ID, and WATSONX_URL are set, the template-generated
   context is sent to IBM Granite as a prompt and the LLM-generated
   narrative is used instead of the raw template text.  If the LLM call
   fails for any reason the template output is returned unchanged.

The ``SiteExplanation`` model returned by :func:`explain_site_risk` sets
``ai_enhanced=True`` only when tier 2 actually succeeded.

Public API
----------
    from src.ai.explainer import explain_site_risk

    explanation = explain_site_risk(site_score, site_deviations)
    print(explanation.summary)
    print(explanation.evidence_points)
"""

from __future__ import annotations

from src.deviation.models  import DeviationRecord
from src.risk.models        import SiteRiskScore

from .models   import SiteExplanation
from .watsonx  import query_watsonx


# ---------------------------------------------------------------------------
# Risk-level framing — concise phrases used in the template narrative
# ---------------------------------------------------------------------------

_RISK_CONTEXT: dict[str, dict[str, str]] = {
    "CRITICAL": {
        "headline":    "requires immediate investigation",
        "urgency":     "Immediate action is required.",
        "monitor_cta": "Escalate to the Clinical Operations lead and initiate a root-cause analysis without delay.",
    },
    "HIGH": {
        "headline":    "has a significant deviation burden",
        "urgency":     "Prompt intervention is needed.",
        "monitor_cta": "Schedule an urgent site visit and review all open deviations with the site coordinator.",
    },
    "MEDIUM": {
        "headline":    "shows elevated deviation activity",
        "urgency":     "Close monitoring is recommended.",
        "monitor_cta": "Increase monitoring frequency and request a corrective action plan from the site.",
    },
    "LOW": {
        "headline":    "is performing within acceptable norms",
        "urgency":     "Continue routine monitoring.",
        "monitor_cta": "Maintain standard monitoring cadence and review at the next scheduled data review.",
    },
}

_TREND_PHRASES: dict[str, str] = {
    "Increasing":        "an increasing trend in deviation activity",
    "Decreasing":        "a decreasing trend in deviation activity",
    "Stable":            "a stable deviation rate",
    "Insufficient Data": "insufficient historical data to determine a trend",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain_site_risk(
    site_score:       SiteRiskScore,
    site_deviations:  list[DeviationRecord],
) -> SiteExplanation:
    """Generate a natural-language explanation of a site's risk profile.

    Builds a structured explanation from real Member 3 risk scores and
    Member 2 deviation records.  Optionally enriches the narrative via
    IBM watsonx.ai when credentials are configured.

    Args:
        site_score:       ``SiteRiskScore`` for the site, as returned by
                          ``compute_site_risks()``.
        site_deviations:  All ``DeviationRecord`` objects for this site,
                          as returned by ``detect_deviations()``.
                          May be an empty list (clean site).

    Returns:
        A :class:`~src.ai.models.SiteExplanation` instance.
    """
    ctx      = _RISK_CONTEXT.get(site_score.risk_level, _RISK_CONTEXT["LOW"])
    evidence = _build_evidence_points(site_score, site_deviations)
    summary  = _build_summary(site_score, site_deviations, ctx)
    headline = ctx["monitor_cta"]

    # --- Attempt watsonx enrichment ---
    ai_text  = _try_watsonx_enrichment(site_score, site_deviations, summary, evidence)
    ai_enhanced = ai_text is not None
    if ai_text:
        summary = ai_text

    return SiteExplanation(
        site_id                  = site_score.site_id,
        risk_level               = site_score.risk_level,
        summary                  = summary,
        evidence_points          = evidence,
        recommendation_headline  = headline,
        ai_enhanced              = ai_enhanced,
    )


# ---------------------------------------------------------------------------
# Private helpers — template construction
# ---------------------------------------------------------------------------

def _build_summary(
    score:      SiteRiskScore,
    deviations: list[DeviationRecord],
    ctx:        dict[str, str],
) -> str:
    """Construct the 2–3 sentence summary from live data."""
    trend_phrase = _TREND_PHRASES.get(score.trend, "an undetermined trend")

    if score.total_deviations == 0:
        return (
            f"Site {score.site_id} has a risk score of {score.risk_score:.1f}/100 "
            f"and is currently classified as {score.risk_level} risk. "
            f"No protocol deviations have been detected across all {_total_obs_phrase(score)} visits. "
            f"The site is performing within protocol requirements."
        )

    open_note = (
        f"{score.open_deviations} remain open"
        if score.open_deviations > 0
        else "all deviations have been resolved"
    )

    return (
        f"Site {score.site_id} has a risk score of {score.risk_score:.1f}/100 "
        f"({score.risk_level} risk) and {ctx['headline']}. "
        f"A total of {score.total_deviations} protocol deviation(s) have been recorded "
        f"across this site, of which {open_note}. "
        f"Deviation activity shows {trend_phrase}, "
        f"with {score.recent_deviations} deviation(s) in the recent visit period "
        f"compared to {score.previous_period_deviations} in the previous period. "
        f"{ctx['urgency']}"
    )


def _build_evidence_points(
    score:      SiteRiskScore,
    deviations: list[DeviationRecord],
) -> list[str]:
    """Build a list of specific, data-driven evidence bullet points."""
    points: list[str] = []

    # 1. Risk score breakdown
    points.append(
        f"Risk score: {score.risk_score:.1f} / 100 "
        f"(severity 40 %, frequency 25 %, recency 20 %, trend 15 %)"
    )

    # 2. Deviation severity counts
    if score.total_deviations > 0:
        parts = []
        if score.major_deviations:
            parts.append(f"{score.major_deviations} Major")
        if score.minor_deviations:
            parts.append(f"{score.minor_deviations} Minor")
        if score.administrative_deviations:
            parts.append(f"{score.administrative_deviations} Administrative")
        sev_str = ", ".join(parts) if parts else "none"
        points.append(
            f"Deviation breakdown: {score.total_deviations} total "
            f"({sev_str}); {score.open_deviations} currently open"
        )

        # 3. Visit-type distribution
        visit_counts: dict[str, int] = {}
        for d in deviations:
            visit_counts[d.visit_type] = visit_counts.get(d.visit_type, 0) + 1
        if visit_counts:
            visit_str = ", ".join(
                f"{vt}: {cnt}" for vt, cnt in sorted(visit_counts.items())
            )
            points.append(f"Deviations by visit type: {visit_str}")

        # 4. Severity distribution of actual records
        sev_counts: dict[str, int] = {}
        for d in deviations:
            sev_counts[d.severity] = sev_counts.get(d.severity, 0) + 1
        if sev_counts:
            sev_detail = ", ".join(
                f"{sv}: {cnt}" for sv, cnt in sorted(sev_counts.items())
            )
            points.append(f"Severity distribution: {sev_detail}")

        # 5. Worst overshoot
        if deviations:
            worst = max(deviations, key=lambda d: d.difference - d.allowed_window)
            overshoot = worst.difference - worst.allowed_window
            points.append(
                f"Largest overshoot: {worst.visit_type} visit for patient "
                f"{worst.patient_id} — {worst.difference} days from expected "
                f"(allowed window ±{worst.allowed_window} days, "
                f"overshoot {overshoot} days)"
            )
    else:
        points.append("No protocol deviations detected — all visits within permitted windows")

    # 6. Trend change
    if score.trend_change_percent is not None:
        sign = "+" if score.trend_change_percent > 0 else ""
        points.append(
            f"Period-over-period change: {sign}{score.trend_change_percent:.1f} % "
            f"({score.previous_period_deviations} → {score.recent_deviations} deviations)"
        )
    else:
        points.append(
            f"Trend: {score.trend} "
            f"(previous period: {score.previous_period_deviations}, "
            f"recent period: {score.recent_deviations})"
        )

    # 7. Pass through top_risk_drivers if available
    if score.top_risk_drivers:
        points.append(
            "Key risk drivers: " + "; ".join(score.top_risk_drivers[:3])
        )

    return points


def _total_obs_phrase(score: SiteRiskScore) -> str:
    """Return a phrase describing observation coverage (approximate)."""
    # We don't have the raw observation count here, but we can give context
    return "scheduled"


# ---------------------------------------------------------------------------
# Private helpers — watsonx enrichment
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a clinical trial risk analyst. Based on the following evidence about \
a clinical site, write a clear, professional 3-sentence risk explanation for \
a clinical monitor. Use only the facts provided — do not invent data.

Site ID: {site_id}
Risk Level: {risk_level}
Risk Score: {risk_score}/100
Trend: {trend}
Total Deviations: {total_devs}
Major Deviations: {major}
Minor Deviations: {minor}
Administrative Deviations: {admin}
Open Deviations: {open_devs}
Recent Period Deviations: {recent}
Previous Period Deviations: {previous}
Top Risk Drivers: {drivers}

Write only the 3-sentence explanation. Do not include headers or bullet points.
"""


def _try_watsonx_enrichment(
    score:      SiteRiskScore,
    deviations: list[DeviationRecord],
    template_summary: str,
    evidence:   list[str],
) -> str | None:
    """Attempt to get an LLM-enriched summary from watsonx. Returns None on any failure."""
    drivers = "; ".join(score.top_risk_drivers[:3]) if score.top_risk_drivers else "None identified"

    prompt = _PROMPT_TEMPLATE.format(
        site_id    = score.site_id,
        risk_level = score.risk_level,
        risk_score = f"{score.risk_score:.1f}",
        trend      = score.trend,
        total_devs = score.total_deviations,
        major      = score.major_deviations,
        minor      = score.minor_deviations,
        admin      = score.administrative_deviations,
        open_devs  = score.open_deviations,
        recent     = score.recent_deviations,
        previous   = score.previous_period_deviations,
        drivers    = drivers,
    )

    return query_watsonx(prompt)
