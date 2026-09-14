"""
models.py — Output data model for the Site Risk Scoring module (Member 3).

This module defines SiteRiskScore, the single Pydantic model that
represents the computed risk profile for one clinical site.  It is the
shared contract between the scorer (scorer.py) and any downstream
consumer such as the Streamlit dashboard.

Downstream modules should import SiteRiskScore from here (or from the
package's public __init__.py) rather than constructing raw dicts.

Risk levels:
    LOW        — score 0–30    : site is within acceptable norms
    MEDIUM     — score 31–50   : elevated activity; monitor closely
    HIGH       — score 51–75   : significant deviation burden; action needed
    CRITICAL   — score 76–100  : immediate investigation required

Trend values:
    Increasing         — deviation rate is rising across the visit sequence
    Stable             — deviation rate is roughly constant
    Decreasing         — deviation rate is falling across the visit sequence
    Insufficient Data  — fewer than two non-empty visit windows; cannot judge
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

RiskLevel  = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
TrendLabel = Literal["Increasing", "Stable", "Decreasing", "Insufficient Data"]


# ---------------------------------------------------------------------------
# SiteRiskScore
# ---------------------------------------------------------------------------

class SiteRiskScore(BaseModel):
    """Computed risk profile for a single clinical site.

    Produced by :func:`~src.risk.scorer.score_sites` for every site that
    appears in the input deviation list (or site roster).

    Attributes:
        site_id:
            Unique identifier of the site (mirrors ``Site.site_id``).
        risk_score:
            Composite risk score 0–100.  Higher is worse.
            Formula weight breakdown: severity 40 %, frequency 25 %,
            recent-activity 20 %, trend 15 %.
        risk_level:
            Categorical risk band derived from risk_score.
        trend:
            Direction of deviation activity across the visit sequence
            (BASELINE → WEEK_4 → WEEK_8 → WEEK_12).
        major_deviations:
            Count of open deviations classified as Major.
        minor_deviations:
            Count of open deviations classified as Minor.
        administrative_deviations:
            Count of open deviations classified as Administrative.
        total_deviations:
            Total count of all deviations for this site (any severity /
            any status).
        open_deviations:
            Count of deviations with status == "OPEN".
        recent_deviations:
            Count of deviations in the *latter half* of the visit sequence
            (WEEK_8, WEEK_12) — used as the "recent period" indicator.
        previous_period_deviations:
            Count of deviations in the *first half* of the visit sequence
            (BASELINE, WEEK_4) — used as the "previous period" for trend.
        trend_change_percent:
            Percentage change from previous_period_deviations to
            recent_deviations.  ``None`` when trend is "Insufficient Data"
            or when previous_period_deviations == 0.
        top_risk_drivers:
            Ordered list of plain-English strings explaining what is
            driving the site's score.  Derived from actual deviation data;
            never hardcoded.  Empty list when there are no deviations.
    """

    site_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier of the clinical site.",
    )
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Composite risk score 0–100 (higher = more risk).",
    )
    risk_level: RiskLevel = Field(
        ...,
        description="Categorical risk band: LOW / MEDIUM / HIGH / CRITICAL.",
    )
    trend: TrendLabel = Field(
        ...,
        description="Deviation-activity trend across the visit sequence.",
    )
    major_deviations: int = Field(
        ..., ge=0, description="Count of Major-severity deviations."
    )
    minor_deviations: int = Field(
        ..., ge=0, description="Count of Minor-severity deviations."
    )
    administrative_deviations: int = Field(
        ..., ge=0, description="Count of Administrative-severity deviations."
    )
    total_deviations: int = Field(
        ..., ge=0, description="Total deviation count for this site."
    )
    open_deviations: int = Field(
        ..., ge=0, description="Count of deviations with status OPEN."
    )
    recent_deviations: int = Field(
        ...,
        ge=0,
        description=(
            "Deviations in the latter half of the visit sequence "
            "(WEEK_8, WEEK_12)."
        ),
    )
    previous_period_deviations: int = Field(
        ...,
        ge=0,
        description=(
            "Deviations in the first half of the visit sequence "
            "(BASELINE, WEEK_4)."
        ),
    )
    trend_change_percent: float | None = Field(
        default=None,
        description=(
            "Percentage change from previous_period to recent period. "
            "None when Insufficient Data or previous_period == 0."
        ),
    )
    top_risk_drivers: list[str] = Field(
        default_factory=list,
        description="Ordered plain-English explanations of the top risk drivers.",
    )

    model_config = {"frozen": True}  # immutable once created; mirrors DeviationRecord
