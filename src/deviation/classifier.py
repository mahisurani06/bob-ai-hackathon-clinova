"""
classifier.py — Severity classification for detected protocol deviations.

Given a detected deviation (represented by the difference between the
actual visit day and the expected day, and the rule's allowed window),
this module assigns one of three severity levels:

    Administrative  — difference is only slightly beyond the allowed window
    Minor           — difference is moderately beyond the allowed window
    Major           — difference is significantly beyond the allowed window

Design decisions
----------------
* The thresholds are defined as module-level constants so a team member
  can change them in one place without touching the logic.
* The classifier is purely deterministic — no AI, no probability, no
  randomness.  Given the same inputs it always produces the same output.
* Only the overshoot (how many days *beyond* the window) matters, not
  the raw difference.  A visit 5 days late on a ±3-day window is only
  2 days over — that is less severe than a visit 5 days late on a ±0-day
  window (5 days over).

Threshold table (overshoot = difference - allowed_window):
    overshoot <= ADMIN_MAX_OVERSHOOT  →  Administrative
    overshoot <= MINOR_MAX_OVERSHOOT  →  Minor
    overshoot >  MINOR_MAX_OVERSHOOT  →  Major
"""

from __future__ import annotations

from .models import DeviationRecord, SeverityLevel


# ---------------------------------------------------------------------------
# Severity thresholds — change these values to tune classification globally.
# ---------------------------------------------------------------------------

# Maximum overshoot (days beyond the allowed window) still considered
# Administrative.  At or below this value the deviation is low-risk.
ADMIN_MAX_OVERSHOOT: int = 3

# Maximum overshoot still considered Minor.
# Above this value the deviation escalates to Major.
MINOR_MAX_OVERSHOOT: int = 7


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_severity(deviation: DeviationRecord) -> SeverityLevel:
    """Return the severity level for a detected deviation.

    The classification is based on how far the deviation overshoots the
    allowed window, not on the raw difference alone.

    Overshoot calculation::

        overshoot = deviation.difference - deviation.allowed_window

    Classification rules (see module-level constants to change thresholds):

    * overshoot <= ``ADMIN_MAX_OVERSHOOT``  →  ``"Administrative"``
    * overshoot <= ``MINOR_MAX_OVERSHOOT``  →  ``"Minor"``
    * overshoot >  ``MINOR_MAX_OVERSHOOT``  →  ``"Major"``

    Args:
        deviation: A :class:`~src.deviation.models.DeviationRecord` that was
                   produced by the detector.  It must already represent a
                   confirmed deviation (i.e. difference > allowed_window).

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
            actual=33,     # 5 days late, window is ±3 → overshoot = 2
            difference=5,
            allowed_window=3,
            severity="Administrative",  # placeholder; classify_severity will return the real value
            status="OPEN",
        )
        level = classify_severity(rec)   # → "Administrative" (overshoot = 2 ≤ 3)
    """
    # How many days the visit falls *beyond* the permitted window.
    # deviation.difference > deviation.allowed_window is guaranteed by the
    # detector, so overshoot will always be >= 1 here.
    overshoot: int = deviation.difference - deviation.allowed_window

    if overshoot <= ADMIN_MAX_OVERSHOOT:
        return "Administrative"

    if overshoot <= MINOR_MAX_OVERSHOOT:
        return "Minor"

    return "Major"
