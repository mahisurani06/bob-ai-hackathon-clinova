"""
scorer.py — Site-level risk scoring engine (Member 3).

This module is the core of the Member 3 work.  It consumes a list of
:class:`~src.deviation.models.DeviationRecord` objects (produced by
Member 2's deviation detector) and computes a :class:`~src.risk.models.SiteRiskScore`
for every site that appears in the data.

How the composite score is built
---------------------------------
The final score is a weighted sum of four independent components, each
normalised to the range 0–100 before weighting:

    Component               Weight   What it measures
    ─────────────────────── ──────   ────────────────────────────────────────
    Severity Risk           40 %     How severe are the deviations at the site?
    Frequency Risk          25 %     How many deviations does the site have
                                     relative to the worst-performing site?
    Recent Activity Risk    20 %     Are deviations concentrated in the later
                                     (more recent) visit windows?
    Trend Risk              15 %     Is the deviation rate rising, stable, or
                                     falling across the visit sequence?

    Final score = Σ(component_score × weight), clamped to [0, 100].

Component details
-----------------

1. SEVERITY RISK (weight 0.40)
   Each open deviation contributes a severity point:
       Major          → 10 points
       Minor          →  5 points
       Administrative →  1 point
   Site raw score = Σ severity_points.
   Normalised 0–100 against the maximum raw score across ALL sites so
   that no absolute ceiling is hard-coded.  If all sites have zero
   severity points the component is 0.

2. FREQUENCY RISK (weight 0.25)
   raw_freq = total_deviations / total_observations_at_site
   (total_observations = observations passed in, filtered to this site)
   Normalised 0–100 against the maximum raw frequency across ALL sites.
   Falls back to total_deviations if observations are not supplied.

3. RECENT ACTIVITY RISK (weight 0.20)
   The visit sequence BASELINE→WEEK_4→WEEK_8→WEEK_12 is treated as a
   four-step timeline.  The "recent period" is the latter half
   (WEEK_8, WEEK_12); the "previous period" is the first half
   (BASELINE, WEEK_4).
   recent_ratio = recent_deviations / total_deviations (0 when none).
   Score = recent_ratio × 100.

4. TREND RISK (weight 0.15)
   Compares previous_period_deviations vs. recent_deviations.
   The percentage change determines both the TrendLabel and the
   trend risk contribution:
       Increasing  (change > +10 %)  → 100 points
       Stable      (change ±10 %)    →  50 points
       Decreasing  (change < -10 %)  →   0 points
       Insufficient Data             →  50 points (neutral; no evidence)

Risk level bands
----------------
    LOW      : score   0–30
    MEDIUM   : score  31–50
    HIGH     : score  51–75
    CRITICAL : score  76–100

Top risk drivers
----------------
Derived entirely from the site's own deviation data — never hardcoded.
Conditions are evaluated in priority order; the first N (default 3) that
apply become the site's risk drivers list.

Usage
-----
    from src.deviation.detector import detect_deviations
    from src.protocol.interface import load_project_data
    from src.risk.scorer        import score_sites

    data       = load_project_data()
    deviations = detect_deviations(data["observations"], data["protocol_rules"])
    scores     = score_sites(deviations, data["sites"], data["observations"])

    for s in scores:
        print(s.site_id, s.risk_score, s.risk_level)

What this module does NOT do
-----------------------------
- It does NOT load data from disk.  Use src.risk.interface for that.
- It does NOT modify any DeviationRecord or Site object.
- It does NOT introduce timestamps or fake date logic.
- It does NOT call any external service.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from src.deviation.models import DeviationRecord
from src.protocol.models  import Observation, Site

from .models import RiskLevel, SiteRiskScore, TrendLabel


# ---------------------------------------------------------------------------
# Visit sequence — the only temporal proxy available (no timestamps).
# Earlier index = older visit; later index = more recent visit.
# ---------------------------------------------------------------------------

VISIT_SEQUENCE: list[str] = ["BASELINE", "WEEK_4", "WEEK_8", "WEEK_12"]

# The split point divides the sequence into "previous" (first half) and
# "recent" (second half).  With four visits: previous=[0,1], recent=[2,3].
_HALF: int = len(VISIT_SEQUENCE) // 2

PREVIOUS_VISITS: frozenset[str] = frozenset(VISIT_SEQUENCE[:_HALF])   # BASELINE, WEEK_4
RECENT_VISITS:   frozenset[str] = frozenset(VISIT_SEQUENCE[_HALF:])   # WEEK_8,   WEEK_12


# ---------------------------------------------------------------------------
# Severity weights
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS: dict[str, int] = {
    "Major":          10,
    "Minor":           5,
    "Administrative":  1,
}


# ---------------------------------------------------------------------------
# Component weights (must sum to 1.0)
# ---------------------------------------------------------------------------

W_SEVERITY:       float = 0.40
W_FREQUENCY:      float = 0.25
W_RECENT:         float = 0.20
W_TREND:          float = 0.15

assert abs(W_SEVERITY + W_FREQUENCY + W_RECENT + W_TREND - 1.0) < 1e-9, (
    "Component weights must sum to 1.0"
)


# ---------------------------------------------------------------------------
# Trend classification thresholds
# ---------------------------------------------------------------------------

TREND_INCREASE_THRESHOLD: float =  10.0   # % change → Increasing
TREND_DECREASE_THRESHOLD: float = -10.0   # % change → Decreasing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_sites(
    deviations:   Sequence[DeviationRecord],
    sites:        Sequence[Site],
    observations: Sequence[Observation] | None = None,
) -> list[SiteRiskScore]:
    """Compute a :class:`~src.risk.models.SiteRiskScore` for every site.

    Sites with zero deviations are included and receive a score of 0.

    Args:
        deviations:   All detected protocol deviations (from Member 2's
                      :func:`~src.deviation.detector.detect_deviations`).
                      DeviationRecord objects are not mutated.
        sites:        Full site roster (from Member 1's data layer).
                      Used to ensure every site appears in the output
                      even when it has no deviations.
        observations: Optional.  When provided, the frequency component
                      is normalised by the number of observations at
                      each site rather than by raw deviation count, which
                      gives a more meaningful rate.  When ``None``, raw
                      deviation counts are used directly.

    Returns:
        A list of :class:`~src.risk.models.SiteRiskScore` objects, one
        per site, sorted by ``risk_score`` descending (highest risk first).
    """
    # Build per-site deviation lists.  Any site_id in the sites roster
    # that has no deviations gets an empty list.
    site_devs: dict[str, list[DeviationRecord]] = {
        s.site_id: [] for s in sites
    }
    for dev in deviations:
        if dev.site_id not in site_devs:
            # Deviation references a site not in the roster — include it
            # rather than silently dropping data.
            site_devs[dev.site_id] = []
        site_devs[dev.site_id].append(dev)

    # Build per-site observation counts (for frequency normalisation).
    obs_counts: dict[str, int] = defaultdict(int)
    if observations is not None:
        for obs in observations:
            obs_counts[obs.site_id] += 1

    # --- Pre-compute raw component values so we can normalise across sites ---

    raw_severity:  dict[str, float] = {}
    raw_frequency: dict[str, float] = {}

    for site_id, devs in site_devs.items():
        raw_severity[site_id]  = _raw_severity_score(devs)
        raw_frequency[site_id] = _raw_frequency_score(
            devs, obs_counts.get(site_id, 0)
        )

    max_severity  = max(raw_severity.values(),  default=0.0) or 1.0
    max_frequency = max(raw_frequency.values(), default=0.0) or 1.0

    # --- Compute SiteRiskScore for every site ---

    scores: list[SiteRiskScore] = []
    for site_id, devs in site_devs.items():
        scores.append(
            _compute_score(
                site_id=site_id,
                devs=devs,
                norm_severity=raw_severity[site_id]  / max_severity  * 100.0,
                norm_frequency=raw_frequency[site_id] / max_frequency * 100.0,
            )
        )

    # Sort highest risk first so callers get the most urgent sites up front.
    scores.sort(key=lambda s: s.risk_score, reverse=True)
    return scores


# ---------------------------------------------------------------------------
# Private helpers — one function per concern
# ---------------------------------------------------------------------------

def _raw_severity_score(devs: list[DeviationRecord]) -> float:
    """Sum weighted severity points for all deviations at a site.

    Only open deviations contribute.  The implementation is forward-
    compatible: if future statuses (e.g. RESOLVED) are introduced, those
    records will correctly be excluded.

    Weight table:
        Major → 10,  Minor → 5,  Administrative → 1
    """
    return float(sum(
        SEVERITY_WEIGHTS.get(d.severity, 0)
        for d in devs
        if d.status == "OPEN"
    ))


def _raw_frequency_score(devs: list[DeviationRecord], obs_count: int) -> float:
    """Return the raw frequency metric for a site.

    When ``obs_count > 0`` returns ``total_deviations / obs_count`` (a rate).
    Otherwise returns ``total_deviations`` as an absolute count.
    This keeps the metric meaningful even when observations are not supplied.
    """
    total = len(devs)
    if obs_count > 0:
        return total / obs_count
    return float(total)


def _recent_activity_score(devs: list[DeviationRecord]) -> float:
    """Return a 0–100 score reflecting how much activity is in recent visits.

    "Recent" = WEEK_8 and WEEK_12 (the latter half of the visit sequence).
    Score = (recent_count / total_count) × 100.
    Returns 0 when there are no deviations.
    """
    total = len(devs)
    if total == 0:
        return 0.0
    recent = sum(1 for d in devs if d.visit_type in RECENT_VISITS)
    return (recent / total) * 100.0


def _trend_label_and_score(
    devs: list[DeviationRecord],
) -> tuple[TrendLabel, float, int, int, float | None]:
    """Classify the site's deviation trend and return the trend-risk score.

    Uses the visit sequence as the only available temporal proxy.
    "Previous period" = BASELINE + WEEK_4; "recent period" = WEEK_8 + WEEK_12.

    Returns:
        A 5-tuple of:
        - trend label (TrendLabel)
        - trend risk contribution 0–100 (float)
        - previous_period_deviations (int)
        - recent_deviations (int)
        - trend_change_percent (float | None)

    Trend logic:
        Two non-empty periods are required for a meaningful trend.
        If at least one period has data, compare them.
        If BOTH periods are zero, treat as Insufficient Data.
    """
    prev_count   = sum(1 for d in devs if d.visit_type in PREVIOUS_VISITS)
    recent_count = sum(1 for d in devs if d.visit_type in RECENT_VISITS)

    # Insufficient data: no deviations at all, or only one period has data
    # and the other is zero — we cannot draw a directional conclusion.
    if prev_count == 0 and recent_count == 0:
        return "Insufficient Data", 50.0, 0, 0, None

    # When we have data in at least one period we can compare.
    if prev_count == 0:
        # All deviations are recent — activity is new / increasing.
        return "Increasing", 100.0, 0, recent_count, None

    # Percentage change: positive = getting worse, negative = improving.
    pct_change: float = (recent_count - prev_count) / prev_count * 100.0

    if pct_change > TREND_INCREASE_THRESHOLD:
        label: TrendLabel = "Increasing"
        trend_risk: float = 100.0
    elif pct_change < TREND_DECREASE_THRESHOLD:
        label = "Decreasing"
        trend_risk = 0.0
    else:
        label = "Stable"
        trend_risk = 50.0

    return label, trend_risk, prev_count, recent_count, round(pct_change, 1)


def _classify_risk_level(score: float) -> RiskLevel:
    """Map a numeric score to a RiskLevel band.

    Bands:
        0–30   → LOW
        31–50  → MEDIUM
        51–75  → HIGH
        76–100 → CRITICAL
    """
    if score <= 30.0:
        return "LOW"
    if score <= 50.0:
        return "MEDIUM"
    if score <= 75.0:
        return "HIGH"
    return "CRITICAL"


def _top_risk_drivers(
    devs: list[DeviationRecord],
    risk_score: float,
    trend: TrendLabel,
    recent_count: int,
    prev_count: int,
    max_drivers: int = 3,
) -> list[str]:
    """Build an ordered list of plain-English risk-driver strings.

    Every driver is derived from the site's actual deviation data.
    The list is ordered from most impactful to least impactful, capped
    at ``max_drivers`` entries.  Returns an empty list for clean sites.

    Args:
        devs:        All deviations for this site.
        risk_score:  Final composite score (used to frame severity).
        trend:       Classified trend label.
        recent_count: Deviations in recent visit period.
        prev_count:   Deviations in previous visit period.
        max_drivers:  Maximum number of driver strings to return.
    """
    if not devs:
        return []

    drivers: list[tuple[float, str]] = []  # (priority_key, description)

    total      = len(devs)
    major_n    = sum(1 for d in devs if d.severity == "Major")
    minor_n    = sum(1 for d in devs if d.severity == "Minor")
    admin_n    = sum(1 for d in devs if d.severity == "Administrative")
    open_n     = sum(1 for d in devs if d.status == "OPEN")

    # --- Major deviation driver ---
    if major_n > 0:
        drivers.append((
            major_n * 10.0,
            f"{major_n} Major deviation{'s' if major_n > 1 else ''} requiring immediate review",
        ))

    # --- Minor deviation driver ---
    if minor_n > 0:
        drivers.append((
            minor_n * 5.0,
            f"{minor_n} Minor deviation{'s' if minor_n > 1 else ''} requiring documentation",
        ))

    # --- Trend driver ---
    if trend == "Increasing":
        increase_abs = recent_count - prev_count
        drivers.append((
            80.0,
            f"Increasing deviation trend: {increase_abs:+d} deviation"
            f"{'s' if abs(increase_abs) != 1 else ''} more in recent visits"
            f" ({recent_count}) vs previous ({prev_count})",
        ))
    elif trend == "Stable" and total > 1:
        drivers.append((
            20.0,
            f"Stable deviation pattern across visit sequence "
            f"(previous: {prev_count}, recent: {recent_count})",
        ))

    # --- Recent-activity concentration driver ---
    if recent_count > 0 and recent_count >= prev_count and major_n == 0:
        drivers.append((
            recent_count * 6.0,
            f"{recent_count} deviation{'s' if recent_count > 1 else ''} "
            f"in recent visits (WEEK_8/WEEK_12) indicating ongoing risk",
        ))

    # --- Open deviations driver ---
    if open_n > 0:
        drivers.append((
            open_n * 3.0,
            f"{open_n} open deviation{'s' if open_n > 1 else ''} with no resolution recorded",
        ))

    # --- Administrative burden driver (only when it's the sole category) ---
    if admin_n > 0 and major_n == 0 and minor_n == 0:
        drivers.append((
            admin_n * 1.0,
            f"{admin_n} Administrative deviation{'s' if admin_n > 1 else ''} "
            f"with low individual impact but worth monitoring",
        ))

    # Sort by priority key descending; deduplicate on text; return top N.
    seen: set[str] = set()
    ordered: list[str] = []
    for _, text in sorted(drivers, key=lambda x: x[0], reverse=True):
        if text not in seen:
            seen.add(text)
            ordered.append(text)
        if len(ordered) == max_drivers:
            break

    return ordered


def _compute_score(
    site_id: str,
    devs: list[DeviationRecord],
    norm_severity: float,
    norm_frequency: float,
) -> SiteRiskScore:
    """Build a SiteRiskScore for one site given pre-normalised components.

    Args:
        site_id:        The site identifier.
        devs:           All deviation records for this site.
        norm_severity:  Normalised severity score 0–100.
        norm_frequency: Normalised frequency score 0–100.

    Returns:
        A fully populated, immutable SiteRiskScore.
    """
    # Short-circuit: a site with no deviations is always score 0.
    # Without this guard the neutral trend score (50 × 0.15 = 7.5) would
    # bleed into clean sites, which is misleading.
    if not devs:
        return SiteRiskScore(
            site_id=site_id,
            risk_score=0.0,
            risk_level="LOW",
            trend="Insufficient Data",
            major_deviations=0,
            minor_deviations=0,
            administrative_deviations=0,
            total_deviations=0,
            open_deviations=0,
            recent_deviations=0,
            previous_period_deviations=0,
            trend_change_percent=None,
            top_risk_drivers=[],
        )

    # Component 3 — recent activity (self-contained, no cross-site normalisation)
    recent_score = _recent_activity_score(devs)

    # Component 4 — trend
    trend, trend_score, prev_count, recent_count, pct_change = _trend_label_and_score(devs)

    # Weighted composite
    raw_composite = (
        norm_severity  * W_SEVERITY  +
        norm_frequency * W_FREQUENCY +
        recent_score   * W_RECENT    +
        trend_score    * W_TREND
    )

    # Clamp strictly to [0, 100]
    final_score = max(0.0, min(100.0, raw_composite))
    final_score = round(final_score, 2)

    # Counts
    major_n   = sum(1 for d in devs if d.severity == "Major")
    minor_n   = sum(1 for d in devs if d.severity == "Minor")
    admin_n   = sum(1 for d in devs if d.severity == "Administrative")
    total_n   = len(devs)
    open_n    = sum(1 for d in devs if d.status == "OPEN")

    drivers = _top_risk_drivers(
        devs=devs,
        risk_score=final_score,
        trend=trend,
        recent_count=recent_count,
        prev_count=prev_count,
    )

    return SiteRiskScore(
        site_id=site_id,
        risk_score=final_score,
        risk_level=_classify_risk_level(final_score),
        trend=trend,
        major_deviations=major_n,
        minor_deviations=minor_n,
        administrative_deviations=admin_n,
        total_deviations=total_n,
        open_deviations=open_n,
        recent_deviations=recent_count,
        previous_period_deviations=prev_count,
        trend_change_percent=pct_change,
        top_risk_drivers=drivers,
    )
