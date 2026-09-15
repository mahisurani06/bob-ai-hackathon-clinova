"""
models.py — Output data models for the AI Advisor & CAPA module (Member 4).

Defines two Pydantic models:

    CAPARecommendation
        A single Corrective and Preventive Action recommendation derived
        from one or more detected protocol deviations at a clinical site.

    SiteExplanation
        A natural-language AI explanation of why a site has its computed
        risk level, referencing the actual deviation evidence.

These models are the shared contract between Member 4's AI module and
any downstream consumer (dashboard, report generator, API).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Priority / Severity type aliases — kept explicit so downstream code
# does not need to import Literal from typing.
# ---------------------------------------------------------------------------

CAPAPriority = Literal["Critical", "High", "Medium", "Low"]
CAPAStatus   = Literal["Open", "In Progress", "Closed"]


# ---------------------------------------------------------------------------
# CAPARecommendation
# ---------------------------------------------------------------------------

class CAPARecommendation(BaseModel):
    """A single Corrective and Preventive Action recommendation.

    Produced by :func:`~src.ai.capa.generate_capa` for a site whose
    risk score warrants intervention.  Every field is derived from
    actual deviation evidence — nothing is hardcoded.

    Attributes:
        capa_id:
            Unique identifier for this CAPA item (e.g. "CAPA-S003-001").
        site_id:
            The clinical site this CAPA applies to.
        issue:
            Plain-English description of the specific deviation or finding
            that triggered this CAPA.  References observation IDs, patient
            IDs, visit types, and numeric measurements from the actual
            DeviationRecord.  "Unavailable" when no supporting record exists.
        severity:
            Severity of the underlying deviation as classified by Member 2's
            classifier: "Major", "Minor", "Administrative" — or a CAPA-level
            priority word ("Critical" / "High") for site-level CAPAs.
        risk_level:
            The site's categorical risk band (LOW / MEDIUM / HIGH / CRITICAL)
            as determined by Member 3's risk engine.
        root_cause:
            Likely contributing factor inferred from the available evidence
            (visit direction, overshoot magnitude, patient count, trend).
            Explicitly states "Unavailable — insufficient evidence" when the
            data does not support a specific inference.
        corrective_action:
            Immediate action to remediate the existing deviation(s).
        preventive_action:
            Long-term structural action to prevent recurrence.
        priority:
            Recommended action priority: Critical / High / Medium / Low.
        rationale:
            Evidence-based justification referencing the actual risk score,
            trend, and deviation breakdown from Member 3's risk engine.
        status:
            Lifecycle status of this CAPA item.  Always "Open" when first
            generated; updated externally as work progresses.
    """

    capa_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this CAPA item.",
    )
    site_id: str = Field(
        ...,
        min_length=1,
        description="Clinical site this CAPA applies to.",
    )
    issue: str = Field(
        ...,
        min_length=1,
        description=(
            "Specific deviation or finding that triggered this CAPA. "
            "References observation IDs and real measurement values."
        ),
    )
    severity: str = Field(
        ...,
        min_length=1,
        description=(
            "Severity of the underlying deviation (Major / Minor / Administrative) "
            "as classified by Member 2, or a site-level severity for aggregate CAPAs."
        ),
    )
    risk_level: str = Field(
        ...,
        min_length=1,
        description="Site risk band from Member 3: LOW / MEDIUM / HIGH / CRITICAL.",
    )
    root_cause: str = Field(
        ...,
        min_length=1,
        description=(
            "Likely contributing factor inferred from the evidence. "
            "States 'Unavailable — insufficient evidence' when data is absent."
        ),
    )
    corrective_action: str = Field(
        ...,
        min_length=1,
        description="Immediate action to remediate existing deviations.",
    )
    preventive_action: str = Field(
        ...,
        min_length=1,
        description="Structural action to prevent future recurrences.",
    )
    priority: CAPAPriority = Field(
        ...,
        description="Recommended action priority.",
    )
    rationale: str = Field(
        ...,
        min_length=1,
        description="Evidence-based justification for this CAPA.",
    )
    status: CAPAStatus = Field(
        default="Open",
        description="Lifecycle status of this CAPA item.",
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# SiteExplanation
# ---------------------------------------------------------------------------

class SiteExplanation(BaseModel):
    """Natural-language AI explanation of a site's risk profile.

    Produced by :func:`~src.ai.explainer.explain_site_risk`.

    Attributes:
        site_id:
            The clinical site being explained.
        risk_level:
            The categorical risk band (LOW / MEDIUM / HIGH / CRITICAL)
            as determined by Member 3's risk engine.
        summary:
            A 2-3 sentence summary of the site's overall risk situation.
        evidence_points:
            Ordered list of bullet-point evidence statements, each
            referencing specific numbers drawn from the real data.
        recommendation_headline:
            A single action-oriented sentence recommending what the
            clinical monitor should do next.
        ai_enhanced:
            True when the explanation text was enriched by IBM watsonx.ai.
            False when the explanation was produced by the deterministic
            template engine (watsonx credentials not configured).
    """

    site_id: str = Field(
        ...,
        min_length=1,
        description="Clinical site this explanation applies to.",
    )
    risk_level: str = Field(
        ...,
        description="Risk level: LOW / MEDIUM / HIGH / CRITICAL.",
    )
    summary: str = Field(
        ...,
        min_length=1,
        description="2-3 sentence summary of the site's risk situation.",
    )
    evidence_points: list[str] = Field(
        default_factory=list,
        description="Evidence bullet points derived from real deviation data.",
    )
    recommendation_headline: str = Field(
        ...,
        min_length=1,
        description="Single action-oriented recommendation sentence.",
    )
    ai_enhanced: bool = Field(
        default=False,
        description="True when enriched by IBM watsonx.ai; False for template output.",
    )

    model_config = {"frozen": True}
