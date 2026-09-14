# src/ai/__init__.py
# Clinical Trial Risk Monitor — AI Advisor & CAPA Module (Member 4)
#
# This package provides IBM watsonx.ai–backed (with deterministic fallback)
# AI explanations and CAPA recommendations for site risk scores produced by
# Member 3's risk engine.
#
# Intended usage by the Streamlit dashboard or any other consumer:
#
#     from src.ai import explain_site_risk, generate_capa, build_report
#
#     explanation = explain_site_risk(site_risk_score, site_deviations)
#     capas       = generate_capa(site_risk_score, site_deviations)
#     report_text = build_report(site_risk_score, site_deviations, explanation, capas)
#
# Public surface:
#   models.py     — CAPARecommendation, SiteExplanation Pydantic models
#   explainer.py  — explain_site_risk() natural-language risk explanation
#   capa.py       — generate_capa() CAPA recommendation generator
#   report.py     — build_report() CAPA-ready markdown/text report builder
#   watsonx.py    — thin IBM watsonx.ai wrapper (graceful no-op fallback)

from .models    import CAPARecommendation, SiteExplanation
from .explainer import explain_site_risk
from .capa      import generate_capa
from .report    import build_report

__all__ = [
    # models
    "CAPARecommendation",
    "SiteExplanation",
    # explainer
    "explain_site_risk",
    # capa
    "generate_capa",
    # report
    "build_report",
]
