# src/risk/__init__.py
# Clinical Trial Risk Monitor — Site Risk Scoring Module (Member 3)
#
# This package computes a composite risk score for every clinical site
# by aggregating detected protocol deviations from Member 2's output.
#
# Intended usage by other modules (e.g. a Streamlit dashboard):
#
#     from src.risk import compute_site_risks, SiteRiskScore
#
#     scores = compute_site_risks()          # loads live data automatically
#     for s in scores:
#         print(s.site_id, s.risk_score, s.risk_level)
#
# Or with pre-loaded data:
#
#     from src.risk import score_sites, SiteRiskScore
#     from src.deviation import detect_deviations
#     from src.protocol.interface import load_project_data
#
#     data       = load_project_data()
#     deviations = detect_deviations(data["observations"], data["protocol_rules"])
#     scores     = score_sites(deviations, data["sites"], data["observations"])
#
# Public surface:
#   models.py    — SiteRiskScore Pydantic model (output contract)
#   scorer.py    — score_sites() main scoring entry point
#   interface.py — compute_site_risks() convenience wrapper (auto-loads data)

# Output data model — import when you need the SiteRiskScore type
from .models import RiskLevel, SiteRiskScore, TrendLabel

# Scorer — main entry point when you already have deviation data
from .scorer import (
    PREVIOUS_VISITS,
    RECENT_VISITS,
    SEVERITY_WEIGHTS,
    VISIT_SEQUENCE,
    W_FREQUENCY,
    W_RECENT,
    W_SEVERITY,
    W_TREND,
    score_sites,
)

# Interface — convenience wrapper that loads data and runs the full pipeline
from .interface import compute_site_risks

__all__ = [
    # models
    "SiteRiskScore",
    "RiskLevel",
    "TrendLabel",
    # scorer
    "score_sites",
    "VISIT_SEQUENCE",
    "PREVIOUS_VISITS",
    "RECENT_VISITS",
    "SEVERITY_WEIGHTS",
    "W_SEVERITY",
    "W_FREQUENCY",
    "W_RECENT",
    "W_TREND",
    # interface
    "compute_site_risks",
]
