"""
models.py — Shared data models for the Clinical Trial Risk Monitor.

These Pydantic models define the data contract between:
  - Member 1 (data layer)  →  the rest of the team

Every other module should import from here and work with these
typed objects instead of raw dicts or DataFrames.  This guarantees
that data passed across module boundaries has already been validated
at parse time by Pydantic.

Models defined here:
    Trial          — a registered clinical trial
    Site           — a participating clinical site
    Participant    — an enrolled patient
    Observation    — a clinical visit / measurement event
    ProtocolRule   — a single requirement from the trial protocol
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Trial
# ---------------------------------------------------------------------------

class Trial(BaseModel):
    """A registered clinical trial.

    Represents the top-level study record.  All sites, participants,
    and observations belong to one trial.

    Attributes:
        trial_id:    Unique identifier (e.g. "TRIAL-001").
        trial_name:  Human-readable study name.
        version:     Protocol version string (e.g. "v2.1").
        status:      Lifecycle state of the trial.
    """

    trial_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the trial (e.g. 'TRIAL-001').",
    )
    trial_name: str = Field(
        ...,
        min_length=1,
        description="Human-readable name of the clinical study.",
    )
    version: str = Field(
        ...,
        min_length=1,
        description="Protocol version (e.g. 'v1.0', 'v2.3').",
    )
    status: Literal["ACTIVE", "COMPLETED", "SUSPENDED", "TERMINATED"] = Field(
        ...,
        description="Current lifecycle state of the trial.",
    )

    model_config = {"frozen": True}  # immutable once created


# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------

class Site(BaseModel):
    """A clinical site participating in the trial.

    Sites are physical locations (hospitals, clinics) where participants
    are enrolled and visits are conducted.

    Attributes:
        site_id:    Unique identifier (e.g. "SITE-01").
        site_name:  Name of the hospital or clinic.
        country:    ISO country name or code where the site is located.
        status:     Whether the site is currently active.
    """

    site_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the site (e.g. 'SITE-01').",
    )
    site_name: str = Field(
        ...,
        min_length=1,
        description="Name of the hospital or clinic.",
    )
    country: str = Field(
        ...,
        min_length=1,
        description="Country where the site is located.",
    )
    status: Literal["ACTIVE", "CLOSED", "ON_HOLD"] = Field(
        ...,
        description="Operational status of the site.",
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Participant
# ---------------------------------------------------------------------------

class Participant(BaseModel):
    """An enrolled patient in the clinical trial.

    Represents one human subject from the point of consent through
    the end of their participation.

    Attributes:
        patient_id:       Unique de-identified patient identifier.
        site_id:          The site where the patient is enrolled.
        age:              Age in years at the time of enrollment (18–99).
        gender:           Biological sex recorded at enrollment.
        enrollment_date:  Calendar date the patient was consented and enrolled.
        status:           Current participation status.
    """

    patient_id: str = Field(
        ...,
        min_length=1,
        description="Unique de-identified patient identifier.",
    )
    site_id: str = Field(
        ...,
        min_length=1,
        description="ID of the site where the patient is enrolled.",
    )
    age: int = Field(
        ...,
        ge=18,
        le=99,
        description="Age in years at enrollment (must be 18–99).",
    )
    gender: Literal["MALE", "FEMALE", "OTHER"] = Field(
        ...,
        description="Biological sex recorded at enrollment.",
    )
    enrollment_date: date = Field(
        ...,
        description="Calendar date the patient was enrolled (ISO 8601).",
    )
    status: Literal["ENROLLED", "COMPLETED", "WITHDRAWN", "SCREEN_FAIL"] = Field(
        ...,
        description="Current participation status of the patient.",
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

class Observation(BaseModel):
    """A single clinical visit or measurement event for a participant.

    An Observation records *when* a protocol-mandated visit actually
    occurred relative to when it was *expected* to occur.  Member 2
    (Deviation Detector) compares ``actual_day`` against
    ``expected_day`` ± the visit window defined in the matching
    ``ProtocolRule`` to decide whether a deviation occurred.

    Attributes:
        observation_id:  Unique identifier for this observation record.
        patient_id:      The patient this observation belongs to.
        site_id:         The site at which the visit took place.
        visit_type:      Name of the visit as defined in the protocol
                         (e.g. "BASELINE", "WEEK_4", "WEEK_8").
        expected_day:    Day number relative to Day 0 (enrollment) on
                         which this visit was *scheduled* per protocol.
        actual_day:      Day number on which the visit *actually* occurred.
                         ``None`` means the visit has not yet happened or
                         was not recorded.
    """

    observation_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this observation record.",
    )
    patient_id: str = Field(
        ...,
        min_length=1,
        description="ID of the patient this observation belongs to.",
    )
    site_id: str = Field(
        ...,
        min_length=1,
        description="ID of the site where the visit took place.",
    )
    visit_type: str = Field(
        ...,
        min_length=1,
        description="Protocol visit name (e.g. 'BASELINE', 'WEEK_4').",
    )
    expected_day: int = Field(
        ...,
        ge=0,
        description="Scheduled day number relative to Day 0 (enrollment).",
    )
    actual_day: Optional[int] = Field(
        default=None,
        description=(
            "Day the visit actually occurred relative to Day 0. "
            "None if the visit has not yet been recorded."
        ),
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# ProtocolRule
# ---------------------------------------------------------------------------

class ProtocolRule(BaseModel):
    """A single requirement defined in the trial protocol document.

    Protocol rules describe what *must* happen during the trial.
    Member 2 (Deviation Detector) loads the full list of rules and
    checks each ``Observation`` against the matching rule to determine
    whether a deviation occurred.

    Common rule types:
        VISIT_WINDOW     — visit must occur within N days of expected_day
        ELIGIBILITY      — participant must meet a demographic requirement
        DOSING           — drug must be administered within a defined window
        LAB_RANGE        — a lab measurement must fall within normal limits

    Attributes:
        rule_id:          Unique identifier (e.g. "RULE-001").
        rule_type:        Category of the rule (see common types above).
        description:      Plain-English description of the requirement.
        visit_type:       The visit or event this rule applies to.
                          ``None`` for rules that are not visit-specific.
        expected_value:   The target value this rule enforces, as a string
                          (e.g. "28" for day 28, "70" for a lab threshold).
                          ``None`` when not applicable.
        allowed_window:   Acceptable deviation from ``expected_value``
                          (e.g. ±3 days for a visit window).
                          ``None`` when the rule has no tolerance band.
    """

    rule_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this protocol rule.",
    )
    rule_type: Literal["VISIT_WINDOW", "ELIGIBILITY", "DOSING", "LAB_RANGE"] = Field(
        ...,
        description="Category of the protocol rule.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Plain-English description of the protocol requirement.",
    )
    visit_type: Optional[str] = Field(
        default=None,
        description="Protocol visit this rule applies to (e.g. 'WEEK_4'). None if not visit-specific.",
    )
    expected_value: Optional[str] = Field(
        default=None,
        description="Target value enforced by this rule (e.g. '28' for day 28).",
    )
    allowed_window: Optional[int] = Field(
        default=None,
        ge=0,
        description="Acceptable ± tolerance around expected_value (e.g. 3 means ±3 days).",
    )

    @field_validator("allowed_window")
    @classmethod
    def window_requires_expected_value(
        cls, window: Optional[int], info
    ) -> Optional[int]:
        """An allowed_window only makes sense when expected_value is also set."""
        if window is not None:
            expected = info.data.get("expected_value")
            if expected is None:
                raise ValueError(
                    "allowed_window requires expected_value to also be set."
                )
        return window

    model_config = {"frozen": True}
