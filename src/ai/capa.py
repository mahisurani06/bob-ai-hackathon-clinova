"""
capa.py — CAPA recommendation generator for the AI Advisor module (Member 4).

Generates structured Corrective and Preventive Action (CAPA) recommendations
from the actual outputs of Members 1–3's pipeline:

  * Member 2: list[DeviationRecord]  — each record carries observation_id,
      patient_id, site_id, visit_type, deviation_type, expected, actual,
      difference, allowed_window, severity, status.
  * Member 3: SiteRiskScore — carries risk_score, risk_level, trend,
      severity counts, period-over-period change, top_risk_drivers.

Generation strategy
-------------------
One CAPA item is produced **per individual DeviationRecord** so that every
detected deviation is traceable to a specific corrective action.  After the
per-deviation items, up to two site-level CAPAs are appended when the
evidence supports them (increasing trend, open-deviation backlog).

This replaces the previous one-per-severity-bucket approach and satisfies
the full field set required by clinical CAPA documentation:

    site_id            — from DeviationRecord / SiteRiskScore
    issue              — built from DeviationRecord fields (obs ID, patient,
                         visit, expected vs actual day, direction, overshoot)
    severity           — the SeverityLevel string from Member 2's classifier
                         ("Major" / "Minor" / "Administrative")
    risk_level         — the RiskLevel string from Member 3's scorer
                         ("CRITICAL" / "HIGH" / "MEDIUM" / "LOW")
    root_cause         — inferred from visit direction, overshoot magnitude,
                         multi-patient pattern, and trend.  Explicitly states
                         "Unavailable — insufficient evidence" when inference
                         is not supported by the available data.
    corrective_action  — immediate remediation action referencing real values
    preventive_action  — structural prevention referencing the visit type
    priority           — derived from deviation severity + site risk level
    rationale          — cites the live risk_score, risk_level, and
                         top_risk_drivers strings produced by Member 3

Public API
----------
    from src.ai.capa import generate_capa

    capas = generate_capa(site_score, site_deviations)
    for c in capas:
        print(c.capa_id, c.priority, c.issue)
"""

from __future__ import annotations

from src.deviation.models import DeviationRecord
from src.risk.models       import SiteRiskScore

from .models import CAPARecommendation, CAPAPriority


# ---------------------------------------------------------------------------
# Thresholds — mirrors Member 2's classifier logic so root-cause labels
# match the severity classification already applied.
# (Imported values not used to avoid coupling; constants are copied here.)
# ---------------------------------------------------------------------------

_ADMIN_MAX_OVERSHOOT = 3   # matches classifier.ADMIN_MAX_OVERSHOOT
_MINOR_MAX_OVERSHOOT = 7   # matches classifier.MINOR_MAX_OVERSHOOT

# Number of site-level aggregate CAPAs appended per risk level
# (trend + open-backlog; each is conditional on evidence being present)
_MAX_SITE_CAPAS: dict[str, int] = {
    "CRITICAL": 2,
    "HIGH":     2,
    "MEDIUM":   1,
    "LOW":      0,
}

# Priority lookup: deviation severity → CAPA priority
_DEV_SEVERITY_PRIORITY: dict[str, CAPAPriority] = {
    "Major":          "Critical",
    "Minor":          "High",
    "Administrative": "Medium",
}

# Priority lookup: site risk level → base priority (for site-level CAPAs)
_RISK_LEVEL_PRIORITY: dict[str, CAPAPriority] = {
    "CRITICAL": "Critical",
    "HIGH":     "High",
    "MEDIUM":   "Medium",
    "LOW":      "Low",
}

# Unavailability sentinel — used when evidence cannot support an inference
_UNAVAILABLE = "Unavailable — insufficient evidence in the available data."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_capa(
    site_score:      SiteRiskScore,
    site_deviations: list[DeviationRecord],
) -> list[CAPARecommendation]:
    """Generate structured CAPA recommendations for a clinical site.

    Produces one CAPA per individual DeviationRecord (so every detected
    deviation has an explicit corrective action) followed by up to two
    site-level CAPAs for increasing trend and open-deviation backlog when
    the evidence supports them.

    Returns an empty list for completely clean sites (zero deviations).

    Args:
        site_score:       ``SiteRiskScore`` for the site (Member 3 output).
        site_deviations:  All ``DeviationRecord`` objects for this site
                          (Member 2 output).  Pass [] for a clean site.

    Returns:
        Ordered list of :class:`~src.ai.models.CAPARecommendation` objects.
    """
    if site_score.total_deviations == 0 or not site_deviations:
        return []

    capas: list[CAPARecommendation] = []
    seq   = _SequenceCounter(site_score.site_id)

    # ── Part A: one CAPA per individual DeviationRecord ───────────────────
    # Sort by severity (Major first) then observation_id for stable ordering.
    _SEV_ORDER = {"Major": 0, "Minor": 1, "Administrative": 2}
    sorted_devs = sorted(
        site_deviations,
        key=lambda d: (_SEV_ORDER.get(d.severity, 9), d.observation_id),
    )

    for dev in sorted_devs:
        capas.append(_capa_for_deviation(dev, site_score, seq))

    # ── Part B: site-level aggregate CAPAs ────────────────────────────────
    max_site = _MAX_SITE_CAPAS.get(site_score.risk_level, 0)
    site_capas_added = 0

    # B1: Increasing trend CAPA
    if (
        site_score.trend == "Increasing"
        and site_capas_added < max_site
    ):
        capas.append(_capa_trend(site_score, seq))
        site_capas_added += 1

    # B2: Open-deviation backlog CAPA
    if (
        site_score.open_deviations > 0
        and site_capas_added < max_site
    ):
        capas.append(_capa_open_backlog(site_score, seq))
        site_capas_added += 1  # noqa: F841 (incremented for symmetry)

    return capas


# ---------------------------------------------------------------------------
# Per-deviation CAPA builder
# ---------------------------------------------------------------------------

def _capa_for_deviation(
    dev:        DeviationRecord,
    score:      SiteRiskScore,
    seq:        "_SequenceCounter",
) -> CAPARecommendation:
    """Build a fully structured CAPA for one DeviationRecord."""

    overshoot  = dev.difference - dev.allowed_window
    direction  = "early" if dev.actual < dev.expected else "late"
    dir_label  = "ahead of" if direction == "early" else "beyond"
    priority   = _DEV_SEVERITY_PRIORITY.get(dev.severity, "Medium")
    drivers    = _fmt_drivers(score.top_risk_drivers)

    # ── issue ──────────────────────────────────────────────────────────────
    issue = (
        f"Observation {dev.observation_id} (patient {dev.patient_id}, site {dev.site_id}): "
        f"{dev.visit_type} visit ({dev.deviation_type}) occurred on day {dev.actual} "
        f"— {dev.difference} days {dir_label} the scheduled day {dev.expected} "
        f"(allowed window: ±{dev.allowed_window} days, overshoot: {overshoot} days). "
        f"Deviation severity: {dev.severity}. Status: {dev.status}."
    )

    # ── root_cause ─────────────────────────────────────────────────────────
    root_cause = _infer_root_cause(dev, overshoot, direction, score)

    # ── corrective_action ──────────────────────────────────────────────────
    corrective = (
        f"Review observation {dev.observation_id} with the site coordinator at {dev.site_id}. "
        f"Confirm why the {dev.visit_type} visit for patient {dev.patient_id} was conducted "
        f"{dev.difference} days {dir_label} the protocol-mandated day {dev.expected} "
        f"(overshoot {overshoot} days beyond the ±{dev.allowed_window}-day window). "
        f"Complete and submit a deviation report to the Trial Master File (TMF) within "
        f"{'2' if dev.severity == 'Major' else '5'} business days."
    )

    # ── preventive_action ─────────────────────────────────────────────────
    preventive = _preventive_for_visit(dev.visit_type, dev.severity, direction)

    # ── rationale ─────────────────────────────────────────────────────────
    rationale = (
        f"Site {score.site_id} risk score: {score.risk_score:.1f}/100 ({score.risk_level}). "
        f"Deviation {dev.observation_id} contributes to the severity component (weight 40 %) "
        f"and frequency component (weight 25 %) of the composite risk formula. "
        f"An overshoot of {overshoot} day(s) for a {dev.severity}-severity deviation "
        f"{'requires immediate investigation per protocol.' if dev.severity == 'Major' else 'requires documentation and monitoring.'} "
        f"Risk drivers identified by Member 3: {drivers}."
    )

    return CAPARecommendation(
        capa_id           = seq.next(),
        site_id           = score.site_id,
        issue             = issue,
        severity          = dev.severity,
        risk_level        = score.risk_level,
        root_cause        = root_cause,
        corrective_action = corrective,
        preventive_action = preventive,
        priority          = priority,
        rationale         = rationale,
        status            = "Open",
    )


# ---------------------------------------------------------------------------
# Site-level aggregate CAPA builders
# ---------------------------------------------------------------------------

def _capa_trend(
    score: SiteRiskScore,
    seq:   "_SequenceCounter",
) -> CAPARecommendation:
    """Build a CAPA for an increasing deviation trend at the site level."""
    change = _fmt_change(score.trend_change_percent)
    drivers = _fmt_drivers(score.top_risk_drivers)

    issue = (
        f"Site {score.site_id} shows an increasing trend in protocol deviations "
        f"across the visit sequence: {score.previous_period_deviations} deviation(s) "
        f"in the previous period (BASELINE/WEEK_4) vs {score.recent_deviations} "
        f"in the recent period (WEEK_8/WEEK_12) — a change of {change}."
    )

    # Root cause: trend implies a systemic or time-varying factor
    if score.trend_change_percent is not None:
        root_cause = (
            f"An increasing deviation rate ({change}) suggests a systemic or "
            f"time-varying factor at site {score.site_id}: possible causes include "
            f"staff turnover, workload increase in later visit phases, inadequate "
            f"visit-scheduling reminders, or protocol complexity at {score.recent_deviations} "
            f"recent-period visits. Root cause requires on-site investigation to confirm."
        )
    else:
        root_cause = _UNAVAILABLE

    corrective = (
        f"Conduct a root-cause analysis at site {score.site_id} to identify whether "
        f"the {change} increase in recent-period deviations is driven by staffing changes, "
        f"protocol amendments, or systemic scheduling failures. "
        f"Escalate findings to the Clinical Operations lead within 5 business days."
    )

    preventive = (
        f"Implement monthly trend-monitoring as part of the Site Management Plan for "
        f"{score.site_id}. Define a threshold (e.g. >20 % period-over-period increase) "
        f"that triggers an automatic unannounced audit. Require the Principal Investigator "
        f"to review deviation trend data at every monitoring visit and sign off the review."
    )

    rationale = (
        f"Risk score {score.risk_score:.1f}/100 ({score.risk_level}). "
        f"Trend accounts for 15 % of the composite risk score. "
        f"An increasing trend ({change}) from {score.previous_period_deviations} to "
        f"{score.recent_deviations} deviations signals worsening compliance and raises "
        f"the probability of future Major deviations. "
        f"Risk drivers identified by Member 3: {drivers}."
    )

    return CAPARecommendation(
        capa_id           = seq.next(),
        site_id           = score.site_id,
        issue             = issue,
        severity          = "High",
        risk_level        = score.risk_level,
        root_cause        = root_cause,
        corrective_action = corrective,
        preventive_action = preventive,
        priority          = _RISK_LEVEL_PRIORITY[score.risk_level],
        rationale         = rationale,
        status            = "Open",
    )


def _capa_open_backlog(
    score: SiteRiskScore,
    seq:   "_SequenceCounter",
) -> CAPARecommendation:
    """Build a CAPA for unresolved (open) deviations at the site level."""
    drivers = _fmt_drivers(score.top_risk_drivers)

    issue = (
        f"Site {score.site_id} has {score.open_deviations} open (unresolved) "
        f"protocol deviation(s) out of {score.total_deviations} total. "
        f"Open deviations indicate that corrective documentation or resolution "
        f"actions have not yet been completed."
    )

    if score.open_deviations == score.total_deviations:
        root_cause = (
            f"All {score.total_deviations} detected deviation(s) at {score.site_id} "
            f"remain unresolved (status OPEN). This indicates that the site's deviation "
            f"management process has not been initiated, possibly due to lack of awareness, "
            f"inadequate deviation-tracking procedures, or delayed sponsor notification. "
            f"Specific root cause requires site investigation to confirm."
        )
    elif score.open_deviations > 0:
        resolved = score.total_deviations - score.open_deviations
        root_cause = (
            f"{resolved} of {score.total_deviations} deviations at {score.site_id} have "
            f"been resolved; {score.open_deviations} remain open. Partial resolution "
            f"suggests the deviation management process is active but incomplete, possibly "
            f"due to resource constraints or pending sponsor approval. "
            f"Specific root cause requires site investigation to confirm."
        )
    else:
        root_cause = _UNAVAILABLE

    corrective = (
        f"Assign named ownership for each of the {score.open_deviations} open deviation(s) "
        f"at site {score.site_id} with a resolution deadline of 10 business days. "
        f"Update the deviation tracking log, obtain sponsor acknowledgement, and "
        f"submit resolution evidence to the Trial Master File."
    )

    preventive = (
        f"Implement a deviation resolution SOP at {score.site_id} with: "
        f"(1) 48-hour acknowledgement of any new deviation, "
        f"(2) 10-business-day resolution target, "
        f"(3) escalation to Clinical Operations if unresolved after 7 days. "
        f"Add open-deviation count as a tracked KPI in monthly site performance reviews."
    )

    rationale = (
        f"Risk score {score.risk_score:.1f}/100 ({score.risk_level}). "
        f"{score.open_deviations} open deviation(s) represent unresolved compliance gaps "
        f"that sustain the site's risk exposure. Timely resolution is required to "
        f"demonstrate investigator oversight and protect data integrity. "
        f"Risk drivers identified by Member 3: {drivers}."
    )

    return CAPARecommendation(
        capa_id           = seq.next(),
        site_id           = score.site_id,
        issue             = issue,
        severity          = "High",
        risk_level        = score.risk_level,
        root_cause        = root_cause,
        corrective_action = corrective,
        preventive_action = preventive,
        priority          = _RISK_LEVEL_PRIORITY[score.risk_level],
        rationale         = rationale,
        status            = "Open",
    )


# ---------------------------------------------------------------------------
# Root-cause inference — derived entirely from DeviationRecord fields
# ---------------------------------------------------------------------------

def _infer_root_cause(
    dev:       DeviationRecord,
    overshoot: int,
    direction: str,
    score:     SiteRiskScore,
) -> str:
    """Infer the most likely root cause from the available evidence.

    Uses only fields present in DeviationRecord and SiteRiskScore.
    Never invents patient facts; explicitly states "Unavailable" when
    the evidence is insufficient for a specific inference.
    """
    parts: list[str] = []

    # 1. Direction-based inference
    if direction == "early":
        parts.append(
            f"The visit occurred {dev.difference} days before the scheduled day "
            f"{dev.expected} (actual day: {dev.actual}). Early visits are typically "
            f"associated with site scheduling errors, patient availability conflicts, "
            f"or premature visit completion without protocol authorisation."
        )
    else:
        parts.append(
            f"The visit occurred {dev.difference} days after the scheduled day "
            f"{dev.expected} (actual day: {dev.actual}). Late visits are commonly "
            f"caused by patient non-attendance, site resource constraints (staff or "
            f"equipment unavailability), or inadequate visit-reminder procedures."
        )

    # 2. Overshoot magnitude
    if overshoot <= _ADMIN_MAX_OVERSHOOT:
        parts.append(
            f"The overshoot ({overshoot} day(s)) is within the Administrative threshold, "
            f"suggesting a minor scheduling slip rather than a systemic failure."
        )
    elif overshoot <= _MINOR_MAX_OVERSHOOT:
        parts.append(
            f"The overshoot ({overshoot} day(s)) is in the Minor range, indicating a "
            f"moderate scheduling failure that may reflect process gaps in visit tracking."
        )
    else:
        parts.append(
            f"The overshoot ({overshoot} day(s)) exceeds the Major threshold, indicating "
            f"a significant failure of visit-window compliance that warrants immediate "
            f"investigation of site scheduling and patient follow-up procedures."
        )

    # 3. Cross-patient pattern (if multiple deviations at this site share the same visit type)
    if score.total_deviations > 1:
        parts.append(
            f"Site {dev.site_id} has {score.total_deviations} total deviations, suggesting "
            f"this may be part of a site-wide pattern rather than an isolated incident. "
            f"A systemic factor (e.g. scheduler training gap, CTMS configuration) "
            f"cannot be ruled out without further investigation."
        )

    # 4. Increasing trend amplifies root-cause concern
    if score.trend == "Increasing":
        parts.append(
            f"The site's deviation trend is Increasing (recent: {score.recent_deviations} "
            f"vs previous: {score.previous_period_deviations}), which suggests the "
            f"underlying cause has not been addressed and may be worsening over time."
        )

    # 5. If no inference could be made at all
    if not parts:
        return _UNAVAILABLE

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Preventive action text — visit-type and direction specific
# ---------------------------------------------------------------------------

_VISIT_ACTIONS: dict[str, str] = {
    "BASELINE": (
        "Ensure all baseline assessments are scheduled immediately after patient consent "
        "and before any study intervention. Implement a CTMS alert 7 days before the "
        "protocol window closes for each enrolled patient."
    ),
    "WEEK_4": (
        "Implement a 7-day advance scheduling reminder for WEEK_4 visits sent to both "
        "the patient and site coordinator. Add a CTMS flag if the visit has not been "
        "booked within 14 days of expected day 28."
    ),
    "WEEK_8": (
        "Configure the CTMS to issue automated alerts when WEEK_8 visits are not booked "
        "within 14 days of expected day 56. Review patient retention rates at the midpoint "
        "of the trial to identify and address attendance barriers early."
    ),
    "WEEK_12": (
        "Ensure end-of-study visit scheduling is initiated at least 4 weeks before expected "
        "day 84. Assign a dedicated patient coordinator to follow up with patients who have "
        "missed earlier visits, as late-trial deviations often follow a pattern."
    ),
}

_DEFAULT_VISIT_ACTION = (
    "Implement a standardised visit-scheduling SOP with advance reminders (7 days and "
    "48 hours before each visit window opens) sent to both the patient and the site "
    "coordinator. Configure the CTMS to flag any unscheduled visit within 3 days of "
    "the protocol window opening."
)


def _preventive_for_visit(
    visit_type: str,
    severity:   str,
    direction:  str,
) -> str:
    """Return a preventive action tailored to the visit type and deviation direction."""
    base = _VISIT_ACTIONS.get(visit_type, _DEFAULT_VISIT_ACTION)

    direction_addendum = ""
    if direction == "early":
        direction_addendum = (
            " Additionally, ensure site staff understand that visits must not be "
            "conducted before the protocol window opens without explicit sponsor approval."
        )
    elif severity in ("Major", "Minor"):
        direction_addendum = (
            " Conduct a site staff re-training session on protocol visit-window requirements "
            "and the consequences of late visits for data integrity."
        )

    return base + direction_addendum


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

class _SequenceCounter:
    """Thread-local sequential CAPA ID counter per site."""

    def __init__(self, site_id: str) -> None:
        self._site_id = site_id
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"CAPA-{self._site_id}-{self._n:03d}"


def _fmt_change(pct: float | None) -> str:
    """Format trend_change_percent for display."""
    if pct is None:
        return "change not quantifiable (no baseline period deviations)"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f} %"


def _fmt_drivers(drivers: list[str]) -> str:
    """Format top_risk_drivers list as a readable inline string."""
    if not drivers:
        return "none recorded"
    return "; ".join(f'"{d}"' for d in drivers[:3])
