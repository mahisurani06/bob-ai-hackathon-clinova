"""
classifier.py — Severity classification for detected protocol deviations.

Assigns one of three severity levels to a confirmed deviation:

    Administrative  — small overshoot, low clinical significance
    Minor           — moderate overshoot, requires documentation
    Major           — large overshoot, requires immediate review / CAPA

Design decisions
----------------
* The thresholds are defined as module-level constants so a team member
  can change them in one place without touching the logic.
* The classifier is purely deterministic — no AI, no probability, no
  randomness.  Given the same inputs it always produces the same output.
* Severity depends on both the deviation_type and the numeric overshoot.

VISIT_WINDOW classification
----------------------------
Uses the overshoot calculation (days beyond the allowed window):

    overshoot = difference - allowed_window
    overshoot <= ADMIN_MAX_OVERSHOOT  →  Administrative
    overshoot <= MINOR_MAX_OVERSHOOT  →  Minor
    overshoot >  MINOR_MAX_OVERSHOOT  →  Major

ELIGIBILITY classification
--------------------------
An age-ineligibility violation is a protocol failure in participant
selection.  It is classified as Major regardless of the numeric distance
from the threshold, because an ineligible participant should not have
been enrolled.

Limitation: this rule is pragmatic, not clinically validated.  A proper
clinical trial system would define severity on each individual rule.
The current ProtocolRule model has no severity field, so we use the
deviation_type as the best available proxy.

MISSING_DATA classification
----------------------------
A visit that was never recorded is a documentation failure.  It is
classified as Minor by default: the visit may still have occurred but
was not captured.  This is more serious than a small timing slip
(Administrative) but less severe than a confirmed protocol violation
with a large overshoot (Major).

Limitation: same as ELIGIBILITY — no protocol-level severity field
exists, so this is a pragmatic default.
"""

from __future__ import annotations

from .models import DeviationRecord, SeverityLevel


# ---------------------------------------------------------------------------
# VISIT_WINDOW severity thresholds
# ---------------------------------------------------------------------------

# Maximum overshoot (days beyond the allowed window) still considered
# Administrative.  At or below this value the deviation is low-risk.
ADMIN_MAX_OVERSHOOT: int = 3

# Maximum overshoot still considered Minor.
# Above this value the deviation escalates to Major.
MINOR_MAX_OVERSHOOT: int = 7


# ---------------------------------------------------------------------------
# Fixed severity by deviation type
# ---------------------------------------------------------------------------

# These mappings assign a severity to non-VISIT_WINDOW deviation types
# where a numeric overshoot is not meaningful.
#
# Rationale:
#   ELIGIBILITY  → Major:  an ineligible participant being enrolled is a
#                          serious protocol violation; there is no tolerance.
#   MISSING_DATA → Minor:  a missing visit record is a documentation failure;
#                          more serious than a small window slip, but the visit
#                          may still have occurred and simply not been logged.
#
# These defaults are intentionally conservative.  They do NOT encode
# clinical domain knowledge and should be reviewed if clinical rule
# severity is ever added to the ProtocolRule model.
DEVIATION_TYPE_SEVERITY: dict[str, SeverityLevel] = {
    "ELIGIBILITY":  "Major",
    "MISSING_DATA": "Minor",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_severity(deviation: DeviationRecord) -> SeverityLevel:
    """Return the severity level for a confirmed deviation.

    Dispatches to the appropriate classification strategy based on
    ``deviation.deviation_type``.

    VISIT_WINDOW — overshoot-based classification:

        overshoot = difference - allowed_window
        overshoot <= ADMIN_MAX_OVERSHOOT  →  Administrative
        overshoot <= MINOR_MAX_OVERSHOOT  →  Minor
        overshoot >  MINOR_MAX_OVERSHOOT  →  Major

    ELIGIBILITY — always Major (ineligible participant enrolled).

    MISSING_DATA — always Minor (required visit not recorded).

    Unknown deviation types fall back to VISIT_WINDOW overshoot logic so
    future rule types degrade gracefully rather than crashing.

    Args:
        deviation: A :class:`~src.deviation.models.DeviationRecord` that
                   represents a confirmed deviation (difference > allowed_window).

    Returns:
        One of ``"Administrative"``, ``"Minor"``, or ``"Major"``.

    Example::

        from src.deviation.classifier import classify_severity
        from src.deviation.models import DeviationRecord

        rec = DeviationRecord(
            observation_id="OBS-0001",
            patient_id="P001",
            site_id="S001",
            visit_type="WEEK_4",
            deviation_type="VISIT_WINDOW",
            expected=28,
            actual=33,      # 5 days late, window ±3 → overshoot = 2
            difference=5,
            allowed_window=3,
            severity="Administrative",  # placeholder
            status="OPEN",
        )
        level = classify_severity(rec)   # → "Administrative" (overshoot 2 ≤ 3)
    """
    # 1. Check for fixed-severity deviation types (ELIGIBILITY, MISSING_DATA).
    fixed = DEVIATION_TYPE_SEVERITY.get(deviation.deviation_type)
    if fixed is not None:
        return fixed

    # 2. VISIT_WINDOW (and unknown types): overshoot-based classification.
    #    deviation.difference > deviation.allowed_window is guaranteed by the
    #    detector, so overshoot will always be >= 1 here.
    overshoot: int = deviation.difference - deviation.allowed_window

    if overshoot <= ADMIN_MAX_OVERSHOOT:
        return "Administrative"

    if overshoot <= MINOR_MAX_OVERSHOOT:
        return "Minor"

    return "Major"
