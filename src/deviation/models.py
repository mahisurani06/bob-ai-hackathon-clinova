"""
models.py — Output data model for the Deviation Detection module.

This module defines DeviationRecord, the single Pydantic model that
represents one detected protocol deviation.  It is the shared contract
between the detector (detector.py) and any downstream consumer such as
a risk-scoring module, API layer, or dashboard.

Downstream modules should import DeviationRecord from here (or from
the package's public __init__.py) rather than constructing raw dicts.

Severity levels (used by classifier.py):
    Administrative  — small overshoot, low clinical significance
    Minor           — moderate overshoot, requires documentation
    Major           — large overshoot, requires immediate review / CAPA

Deviation types produced by detector.py:
    VISIT_WINDOW    — visit occurred outside its mandated time window
    ELIGIBILITY     — participant did not meet an enrollment criterion
    MISSING_DATA    — a required visit was never recorded (actual_day is None)
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Severity literal type
# ---------------------------------------------------------------------------

# Keeping this as a separate alias makes it easy to import in other modules
# and to extend with new levels later if needed.
SeverityLevel = Literal["Administrative", "Minor", "Major"]


# ---------------------------------------------------------------------------
# DeviationRecord
# ---------------------------------------------------------------------------

class DeviationRecord(BaseModel):
    """A single detected protocol deviation.

    Produced by :func:`~src.deviation.detector.detect_deviations` for every
    observation or participant that violates a protocol rule.

    Core fields (locked — downstream modules depend on these exact names):
        observation_id: ID of the source Observation or synthetic key.
        patient_id:     ID of the patient this deviation belongs to.
        site_id:        ID of the site where the deviation occurred.
        visit_type:     Protocol visit name (e.g. "WEEK_4") or "ENROLLMENT"
                        for eligibility violations.
        deviation_type: Category of the violated rule.
                        One of "VISIT_WINDOW", "ELIGIBILITY", "MISSING_DATA".
        expected:       Reference value from the protocol rule (day number
                        or age threshold cast to int).
        actual:         Observed value (day number, participant age, or -1
                        as a sentinel for MISSING_DATA where actual_day is None).
        difference:     Absolute distance between actual and expected.
                        Always > allowed_window (deviation is confirmed).
        allowed_window: Permitted tolerance from the matching ProtocolRule
                        (0 when the rule has no tolerance band).
        severity:       Classified severity level — Administrative, Minor, Major.
        status:         Lifecycle status.  "OPEN" when first detected.

    Optional enrichment fields (new — default to None):
        rule_id:   ID of the ProtocolRule that was violated.  Aids traceability.
        direction: Whether the deviation was early, late, or a missing record.
                   None for ELIGIBILITY deviations (direction is not applicable).
        reason:    Short human-readable explanation of why the deviation was
                   raised.  Useful for display and CAPA narrative generation.
    """

    # ── Core fields (locked) ─────────────────────────────────────────────
    observation_id: str = Field(
        ...,
        min_length=1,
        description="ID of the source Observation record (or synthetic key for ELIGIBILITY).",
    )
    patient_id: str = Field(
        ...,
        min_length=1,
        description="ID of the patient this deviation belongs to.",
    )
    site_id: str = Field(
        ...,
        min_length=1,
        description="ID of the site where the deviation occurred.",
    )
    visit_type: str = Field(
        ...,
        min_length=1,
        description=(
            "Protocol visit name (e.g. 'WEEK_4') or 'ENROLLMENT' for "
            "eligibility deviations."
        ),
    )
    deviation_type: str = Field(
        ...,
        min_length=1,
        description=(
            "Category of the violated protocol rule: "
            "'VISIT_WINDOW', 'ELIGIBILITY', or 'MISSING_DATA'."
        ),
    )
    expected: int = Field(
        ...,
        ge=0,
        description=(
            "Reference value from the protocol rule — scheduled day number "
            "or age threshold (cast to int)."
        ),
    )
    actual: int = Field(
        ...,
        description=(
            "Observed value — actual day number, participant age, "
            "or -1 as a sentinel for MISSING_DATA (visit never recorded)."
        ),
    )
    difference: int = Field(
        ...,
        ge=0,
        description="Absolute distance between actual and expected.  Always > allowed_window.",
    )
    allowed_window: int = Field(
        ...,
        ge=0,
        description=(
            "Permitted ± tolerance from the matching ProtocolRule.  "
            "0 when the rule has no tolerance band."
        ),
    )
    severity: SeverityLevel = Field(
        ...,
        description="Classified severity: Administrative, Minor, or Major.",
    )
    status: Literal["OPEN", "RESOLVED", "UNDER_REVIEW"] = Field(
        default="OPEN",
        description="Lifecycle status of this deviation record.",
    )

    # ── Optional enrichment fields (new — safe to ignore downstream) ─────
    rule_id: Optional[str] = Field(
        default=None,
        description="ID of the ProtocolRule that was violated (e.g. 'RULE-001').",
    )
    direction: Optional[Literal["early", "late", "missing"]] = Field(
        default=None,
        description=(
            "'early' — visit/value occurred before expected; "
            "'late' — after expected; "
            "'missing' — MISSING_DATA (actual_day was None); "
            "None — not applicable (e.g. ELIGIBILITY)."
        ),
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            "Short human-readable explanation of why this deviation was raised. "
            "E.g. 'Visit 10 days outside ±3-day window' or "
            "'Patient age 16 below minimum enrollment age of 18'."
        ),
    )

    model_config = {"frozen": True}  # immutable once created, consistent with protocol models
