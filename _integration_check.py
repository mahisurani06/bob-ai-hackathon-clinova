"""
Member 4 final integration check.
Run from bob-ai-hackathon-clinova/:  python _integration_check.py
"""
import sys
sys.path.insert(0, "src")

SEP = "=" * 60

print(SEP)
print("MEMBER 4 FINAL INTEGRATION CHECK")
print(SEP)

# ── Member 1 ────────────────────────────────────────────────────────────────
print("\n[1] Member 1 — Protocol / data loading")
from src.protocol.interface import load_project_data
data = load_project_data()
assert len(data["trials"])         == 1,  "trials count"
assert len(data["sites"])          == 4,  "sites count"
assert len(data["participants"])   == 20, "participants count"
assert len(data["observations"])   == 80, "observations count"
assert len(data["protocol_rules"]) == 8,  "rules count"
print(
    f"  trials={len(data['trials'])}  sites={len(data['sites'])}"
    f"  participants={len(data['participants'])}"
    f"  observations={len(data['observations'])}"
    f"  rules={len(data['protocol_rules'])}  [OK]"
)

# ── Member 2 ────────────────────────────────────────────────────────────────
print("\n[2] Member 2 — Deviation detection")
from src.deviation.detector   import detect_deviations
from src.deviation.models     import DeviationRecord
from src.deviation.classifier import classify_severity, ADMIN_MAX_OVERSHOOT, MINOR_MAX_OVERSHOOT

devs = detect_deviations(
    observations   = data["observations"],
    protocol_rules = data["protocol_rules"],
)
assert all(isinstance(d, DeviationRecord) for d in devs)
assert all(d.site_id                              for d in devs), "all records have site_id"
assert all(d.difference > d.allowed_window        for d in devs), "difference > window"
assert all(d.severity in ("Administrative", "Minor", "Major") for d in devs), "valid severity"

sev_counts: dict[str, int] = {}
for d in devs:
    sev_counts[d.severity] = sev_counts.get(d.severity, 0) + 1

print(f"  total_deviations={len(devs)}  sites_affected={len(set(d.site_id for d in devs))}")
print(f"  severity_counts={sev_counts}")

# Spot-check classifier thresholds match Member 2 constants
assert ADMIN_MAX_OVERSHOOT == 3
assert MINOR_MAX_OVERSHOOT == 7
print(f"  classifier thresholds: admin<={ADMIN_MAX_OVERSHOOT}, minor<={MINOR_MAX_OVERSHOOT}  [OK]")

# ── Member 3 ────────────────────────────────────────────────────────────────
print("\n[3] Member 3 — Risk scoring")
from src.risk.interface import compute_site_risks
from src.risk.models    import SiteRiskScore

scores = compute_site_risks()
assert all(isinstance(s, SiteRiskScore) for s in scores)
assert scores == sorted(scores, key=lambda s: s.risk_score, reverse=True), "sorted desc"

for s in scores:
    assert 0.0 <= s.risk_score <= 100.0,            "score in range"
    assert s.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"), "valid level"
    assert s.trend in ("Increasing", "Decreasing", "Stable", "Insufficient Data"), "valid trend"

print(
    "  " + "  ".join(
        f"{s.site_id}:{s.risk_level}({s.risk_score:.0f})" for s in scores
    ) + "  [OK]"
)

# ── Member 4 AI pipeline ─────────────────────────────────────────────────────
print("\n[4] Member 4 — AI/CAPA pipeline receives real M1/M2/M3 data")
from src.ai.explainer import explain_site_risk
from src.ai.capa      import generate_capa
from src.ai.report    import build_report
from src.ai.watsonx   import watsonx_available
from src.ai.models    import SiteExplanation, CAPARecommendation

for s in scores:
    site_devs = [d for d in devs if d.site_id == s.site_id]
    exp  = explain_site_risk(s, site_devs)
    caps = generate_capa(s, site_devs)

    # Explanation traceability
    assert isinstance(exp, SiteExplanation)
    assert exp.site_id    == s.site_id,    "explanation.site_id matches score"
    assert exp.risk_level == s.risk_level, "explanation.risk_level matches score"
    score_str = str(round(s.risk_score, 1))
    assert score_str in exp.summary or str(int(s.risk_score)) in exp.summary, \
        f"risk score {s.risk_score} present in summary"
    assert s.site_id in exp.summary, "site_id present in summary"
    assert len(exp.evidence_points) > 0, "evidence_points non-empty"

    # Evidence uses actual risk score value
    score_in_evidence = any(score_str in pt for pt in exp.evidence_points)
    assert score_in_evidence, f"risk score {score_str} in evidence_points"

    # CAPA traceability
    assert all(isinstance(c, CAPARecommendation) for c in caps)
    assert all(c.site_id    == s.site_id    for c in caps), "capa.site_id matches"
    assert all(c.risk_level == s.risk_level for c in caps), "capa.risk_level matches M3"
    assert all(c.status     == "Open"       for c in caps), "all CAPAs start Open"

    # Per-deviation CAPAs embed actual DeviationRecord data
    for c in caps:
        assert score_str in c.rationale, f"rationale references score {score_str}"
        assert s.site_id in c.issue,     "issue references site_id"

    # Report contains required sections
    rpt = build_report(s, site_devs, exp, caps)
    assert s.site_id    in rpt
    assert s.risk_level in rpt
    assert "## AI Risk Explanation"    in rpt
    assert "## Risk Score Summary"     in rpt
    assert "## Deviation Detail"       in rpt
    assert "## CAPA Recommendations"   in rpt

    print(
        f"  {s.site_id}: expl=OK  capas={len(caps)}"
        f"  ai_enhanced={exp.ai_enhanced}  report=OK  [OK]"
    )

# ── File integrity ────────────────────────────────────────────────────────────
print("\n[5] File integrity — no original files deleted")
import pathlib

REQUIRED_FILES = [
    # Member 1
    "src/protocol/__init__.py",
    "src/protocol/models.py",
    "src/protocol/loader.py",
    "src/protocol/interface.py",
    "src/protocol/generator.py",
    "src/protocol/validator.py",
    # Member 2
    "src/deviation/__init__.py",
    "src/deviation/models.py",
    "src/deviation/detector.py",
    "src/deviation/classifier.py",
    # Member 3
    "src/risk/__init__.py",
    "src/risk/models.py",
    "src/risk/scorer.py",
    "src/risk/interface.py",
    # Member 3 dashboard (not deleted/replaced)
    "src/dashboard/app.py",
    # Original test suite (untouched)
    "src/tests/test_classifier.py",
    "src/tests/test_detector.py",
    "src/tests/test_generator.py",
    "src/tests/test_interface.py",
    "src/tests/test_loader.py",
    "src/tests/test_risk_scorer.py",
    "src/tests/test_validator.py",
    # Member 4 — new files only
    "src/ai/__init__.py",
    "src/ai/models.py",
    "src/ai/watsonx.py",
    "src/ai/explainer.py",
    "src/ai/capa.py",
    "src/ai/report.py",
    "src/tests/test_ai_integration.py",
]

for f in REQUIRED_FILES:
    assert pathlib.Path(f).exists(), f"MISSING: {f}"
    print(f"  {f}  [exists]")

# ── Dependencies ──────────────────────────────────────────────────────────────
print("\n[6] Dependencies")
import importlib
for pkg in ("pydantic", "streamlit", "plotly"):
    m = importlib.import_module(pkg)
    print(f"  {pkg} {getattr(m, '__version__', '?')}  [ok]")

try:
    import ibm_watsonx_ai
    print(f"  ibm-watsonx-ai {ibm_watsonx_ai.__version__}  [optional, installed]")
except ImportError:
    print("  ibm-watsonx-ai  [optional, not installed — deterministic fallback active]")

print(f"\n  watsonx_available() = {watsonx_available()}")

print()
print(SEP)
print("ALL INTEGRATION CHECKS PASSED")
print(SEP)
