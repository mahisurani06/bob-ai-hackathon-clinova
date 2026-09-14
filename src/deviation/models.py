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
"""

from __future__ import annotations

from typing import Literal

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
    observation that falls outside its protocol-mandated visit window.

    Attributes:
        observation_id: ID of the source :class:`~src.protocol.models.Observation`.
        patient_id:     ID of the patient the observation belongs to.
        site_id:        ID of the site where the visit took place.
        visit_type:     Protocol visit name that deviated (e.g. "WEEK_4").
        deviation_type: Category of the rule that was violated.
                        Currently always "VISIT_WINDOW".
        expected:       The day number on which the visit was scheduled.
        actual:         The day number on which the visit actually occurred.
        difference:     Absolute difference between actual and expected day.
                        Always >= 0.
        allowed_window: The ± tolerance defined in the matching ProtocolRule.
                        The deviation was confirmed because difference > allowed_window.
        severity:       Classified severity level — Administrative, Minor, or Major.
                        Assigned by :func:`~src.deviation.classifier.classify_severity`.
        status:         Lifecycle status of this deviation record.
                        "OPEN" means it has been detected but not yet resolved.
    """

    observation_id: str = Field(
        ...,
        min_length=1,
        description="ID of the source Observation record.",
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
        description="Protocol visit name that deviated (e.g. 'WEEK_4').",
    )
    deviation_type: str = Field(
        ...,
        min_length=1,
        description="Category of the violated protocol rule (e.g. 'VISIT_WINDOW').",
    )
    expected: int = Field(
        ...,
        ge=0,
        description="Scheduled day number relative to Day 0 (enrollment).",
    )
    actual: int = Field(
        ...,
        description="Day number on which the visit actually occurred.",
    )
    difference: int = Field(
        ...,
        ge=0,
        description="Absolute difference between actual and expected day.",
    )
    allowed_window: int = Field(
        ...,
        ge=0,
        description="Permitted ± tolerance from the matching ProtocolRule.",
    )
    severity: SeverityLevel = Field(
        ...,
        description="Classified severity: Administrative, Minor, or Major.",
    )
    status: Literal["OPEN", "RESOLVED", "UNDER_REVIEW"] = Field(
        default="OPEN",
        description="Lifecycle status of this deviation record.",
    )

    model_config = {"frozen": True}  # immutable once created, consistent with protocol models
