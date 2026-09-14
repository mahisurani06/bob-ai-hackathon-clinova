# src/tests/test_ai_integration.py
#
# End-to-end integration tests for the Member 4 AI Advisor & CAPA module.
#
# These tests verify the COMPLETE data flow:
#
#   Member 1 (protocol / patient data)
#     -> Member 2 (deviation detection + severity classification)
#     -> Member 3 (site risk scoring)
#     -> Member 4 (AI explanation + CAPA recommendations + report)
#
# No mocks, no stubs, no hardcoded values.
# Every assertion is checked against the actual live data produced by the
# existing engines of Members 1-3.

from __future__ import annotations

import pytest

# Member 1 interface
from src.protocol.interface import load_project_data

# Member 2 output types and entry point
from src.deviation.detector import detect_deviations
from src.deviation.models   import DeviationRecord

# Member 3 output types and entry point
from src.risk.interface import compute_site_risks
from src.risk.models    import SiteRiskScore

# Member 4 AI module
from src.ai.explainer import explain_site_risk
from src.ai.capa      import generate_capa
from src.ai.report    import build_report
from src.ai.models    import CAPARecommendation, SiteExplanation
from src.ai.watsonx   import watsonx_available


# ---------------------------------------------------------------------------
# Shared fixtures — run the real pipeline once per test session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pipeline_data():
    """Run the full Members 1->2->3 pipeline and return all outputs."""
    data       = load_project_data()
    deviations = detect_deviations(data["observations"], data["protocol_rules"])
    scores     = compute_site_risks()
    return {
        "data":       data,
        "deviations": deviations,
        "scores":     scores,
    }


@pytest.fixture(scope="session")
def per_site(pipeline_data):
    """Return a dict keyed by site_id with score + site_devs + explanation + capas + report."""
    result = {}
    for score in pipeline_data["scores"]:
        site_devs = [
            d for d in pipeline_data["deviations"]
            if d.site_id == score.site_id
        ]
        exp   = explain_site_risk(score, site_devs)
        capas = generate_capa(score, site_devs)
        rpt   = build_report(score, site_devs, exp, capas)
        result[score.site_id] = {
            "score":     score,
            "site_devs": site_devs,
            "exp":       exp,
            "capas":     capas,
            "report":    rpt,
        }
    return result


# ---------------------------------------------------------------------------
# Stage 1: Member 1 output integrity
# ---------------------------------------------------------------------------

class TestMember1Output:
    def test_observations_loaded(self, pipeline_data):
        assert len(pipeline_data["data"]["observations"]) == 80

    def test_protocol_rules_loaded(self, pipeline_data):
        assert len(pipeline_data["data"]["protocol_rules"]) == 8

    def test_sites_loaded(self, pipeline_data):
        assert len(pipeline_data["data"]["sites"]) == 4


# ---------------------------------------------------------------------------
# Stage 2: Member 2 output — DeviationRecord objects flow into Member 4
# ---------------------------------------------------------------------------

class TestMember2OutputTypes:
    def test_detect_deviations_returns_list(self, pipeline_data):
        assert isinstance(pipeline_data["deviations"], list)

    def test_all_items_are_deviation_records(self, pipeline_data):
        for d in pipeline_data["deviations"]:
            assert isinstance(d, DeviationRecord)

    def test_deviation_records_have_site_id(self, pipeline_data):
        for d in pipeline_data["deviations"]:
            assert d.site_id, "DeviationRecord.site_id must be non-empty"

    def test_deviation_severity_is_valid(self, pipeline_data):
        valid = {"Administrative", "Minor", "Major"}
        for d in pipeline_data["deviations"]:
            assert d.severity in valid

    def test_deviation_difference_exceeds_window(self, pipeline_data):
        for d in pipeline_data["deviations"]:
            assert d.difference > d.allowed_window, (
                f"{d.observation_id}: difference={d.difference} must exceed "
                f"allowed_window={d.allowed_window}"
            )


# ---------------------------------------------------------------------------
# Stage 3: Member 3 output — SiteRiskScore objects flow into Member 4
# ---------------------------------------------------------------------------

class TestMember3OutputTypes:
    def test_compute_site_risks_returns_list(self, pipeline_data):
        assert isinstance(pipeline_data["scores"], list)

    def test_all_items_are_site_risk_scores(self, pipeline_data):
        for s in pipeline_data["scores"]:
            assert isinstance(s, SiteRiskScore)

    def test_four_sites_scored(self, pipeline_data):
        assert len(pipeline_data["scores"]) == 4

    def test_scores_sorted_descending(self, pipeline_data):
        scores = [s.risk_score for s in pipeline_data["scores"]]
        assert scores == sorted(scores, reverse=True)

    def test_top_risk_drivers_are_strings(self, pipeline_data):
        for s in pipeline_data["scores"]:
            for driver in s.top_risk_drivers:
                assert isinstance(driver, str) and driver


# ---------------------------------------------------------------------------
# Stage 4a: Member 4 — SiteExplanation
# ---------------------------------------------------------------------------

class TestSiteExplanation:
    def test_returns_site_explanation_instance(self, per_site):
        for sid, ctx in per_site.items():
            assert isinstance(ctx["exp"], SiteExplanation), sid

    def test_site_id_matches_score(self, per_site):
        for sid, ctx in per_site.items():
            assert ctx["exp"].site_id == ctx["score"].site_id

    def test_risk_level_matches_score(self, per_site):
        for sid, ctx in per_site.items():
            assert ctx["exp"].risk_level == ctx["score"].risk_level

    def test_summary_is_non_empty(self, per_site):
        for sid, ctx in per_site.items():
            assert ctx["exp"].summary.strip(), f"summary empty for {sid}"

    def test_evidence_points_non_empty(self, per_site):
        for sid, ctx in per_site.items():
            assert len(ctx["exp"].evidence_points) > 0, f"no evidence for {sid}"

    def test_all_evidence_points_are_strings(self, per_site):
        for sid, ctx in per_site.items():
            for pt in ctx["exp"].evidence_points:
                assert isinstance(pt, str) and pt

    def test_recommendation_headline_non_empty(self, per_site):
        for sid, ctx in per_site.items():
            assert ctx["exp"].recommendation_headline.strip()

    def test_summary_references_site_id(self, per_site):
        for sid, ctx in per_site.items():
            assert sid in ctx["exp"].summary, f"summary doesn't mention {sid}"

    def test_summary_references_risk_score(self, per_site):
        for sid, ctx in per_site.items():
            score_str = str(round(ctx["score"].risk_score, 1))
            assert score_str in ctx["exp"].summary, (
                f"summary for {sid} doesn't mention score {score_str}"
            )

    def test_evidence_contains_risk_score(self, per_site):
        for sid, ctx in per_site.items():
            all_evidence = " ".join(ctx["exp"].evidence_points)
            score_str = str(round(ctx["score"].risk_score, 1))
            assert score_str in all_evidence, (
                f"evidence for {sid} doesn't mention score {score_str}"
            )

    def test_ai_enhanced_is_false_without_credentials(self, per_site):
        # Without watsonx credentials, ai_enhanced must always be False
        if not watsonx_available():
            for sid, ctx in per_site.items():
                assert ctx["exp"].ai_enhanced is False, (
                    f"{sid}: ai_enhanced should be False without credentials"
                )

    def test_clean_site_says_no_deviations(self, per_site):
        # S002 has 0 deviations — summary must reflect this
        if "S002" in per_site:
            assert per_site["S002"]["score"].total_deviations == 0
            assert "No protocol deviation" in per_site["S002"]["exp"].summary


# ---------------------------------------------------------------------------
# Stage 4b: Member 4 — CAPARecommendation
# ---------------------------------------------------------------------------

class TestCAPARecommendations:
    def test_returns_list(self, per_site):
        for sid, ctx in per_site.items():
            assert isinstance(ctx["capas"], list), sid

    def test_all_items_are_capa_recommendation(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert isinstance(c, CAPARecommendation)

    def test_capa_id_contains_site_id(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert sid in c.capa_id, f"{c.capa_id} missing {sid}"

    def test_all_capas_are_open(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert c.status == "Open", f"{c.capa_id} status={c.status}"

    # ── New field: issue ─────────────────────────────────────────────────

    def test_issue_field_non_empty(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert c.issue.strip(), f"{c.capa_id}: issue is empty"

    def test_issue_mentions_site_id(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert sid in c.issue, f"{c.capa_id}: issue missing {sid}"

    def test_per_deviation_issue_contains_obs_id(self, per_site):
        """Per-deviation CAPAs must reference the observation_id from Member 2."""
        for sid, ctx in per_site.items():
            for dev in ctx["site_devs"]:
                matched = [c for c in ctx["capas"] if dev.observation_id in c.issue]
                assert matched, (
                    f"No CAPA found for observation {dev.observation_id} at {sid}"
                )

    def test_per_deviation_issue_contains_patient_id(self, per_site):
        """Per-deviation CAPAs must reference the patient_id from Member 2."""
        for sid, ctx in per_site.items():
            for dev in ctx["site_devs"]:
                matched = [c for c in ctx["capas"] if dev.patient_id in c.issue]
                assert matched, (
                    f"No CAPA references patient {dev.patient_id} at {sid}"
                )

    # ── New field: severity (now the actual deviation severity string) ────

    def test_severity_field_non_empty(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert c.severity.strip(), f"{c.capa_id}: severity is empty"

    def test_per_deviation_severity_matches_member2_classifier(self, per_site):
        """Per-deviation CAPA severity must come from Member 2's classifier output."""
        valid_dev_severities = {"Major", "Minor", "Administrative"}
        valid_site_severities = {"High", "Critical", "Medium", "Low"}
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                # Per-deviation CAPAs have obs ID in issue; site-level CAPAs do not
                is_per_dev = any(
                    dev.observation_id in c.issue for dev in ctx["site_devs"]
                )
                if is_per_dev:
                    assert c.severity in valid_dev_severities, (
                        f"{c.capa_id}: per-deviation severity '{c.severity}' "
                        f"must be one of {valid_dev_severities}"
                    )
                else:
                    assert c.severity in valid_site_severities, (
                        f"{c.capa_id}: site-level severity '{c.severity}' invalid"
                    )

    # ── New field: risk_level ─────────────────────────────────────────────

    def test_risk_level_field_present(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert hasattr(c, "risk_level"), f"{c.capa_id}: missing risk_level"
                assert c.risk_level.strip()

    def test_risk_level_matches_member3_score(self, per_site):
        """risk_level must equal the SiteRiskScore.risk_level from Member 3."""
        for sid, ctx in per_site.items():
            expected_level = ctx["score"].risk_level
            for c in ctx["capas"]:
                assert c.risk_level == expected_level, (
                    f"{c.capa_id}: risk_level '{c.risk_level}' != "
                    f"score.risk_level '{expected_level}'"
                )

    def test_risk_level_is_valid_value(self, per_site):
        valid = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert c.risk_level in valid, (
                    f"{c.capa_id}: risk_level '{c.risk_level}' not in {valid}"
                )

    # ── New field: root_cause ─────────────────────────────────────────────

    def test_root_cause_field_present(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert hasattr(c, "root_cause"), f"{c.capa_id}: missing root_cause"
                assert c.root_cause.strip(), f"{c.capa_id}: root_cause is empty"

    def test_root_cause_never_hardcoded_patient_data(self, per_site):
        """Root cause must only reference IDs that exist in the real deviation data."""
        for sid, ctx in per_site.items():
            real_patient_ids = {d.patient_id for d in ctx["site_devs"]}
            real_obs_ids     = {d.observation_id for d in ctx["site_devs"]}
            for c in ctx["capas"]:
                # Any patient ID mentioned in root_cause must be real
                import re
                mentioned_patients = set(re.findall(r'P\d{3}', c.root_cause))
                fake = mentioned_patients - real_patient_ids
                assert not fake, (
                    f"{c.capa_id}: root_cause references non-existent patients: {fake}"
                )
                # Same for observation IDs
                mentioned_obs = set(re.findall(r'OBS-\d{4}', c.root_cause))
                fake_obs = mentioned_obs - real_obs_ids
                assert not fake_obs, (
                    f"{c.capa_id}: root_cause references non-existent obs: {fake_obs}"
                )

    def test_clean_site_root_cause_says_unavailable(self, per_site):
        """Sites with zero deviations produce no CAPAs — this test is informational."""
        # S002 has 0 deviations: no CAPAs, so no root_cause to check
        if "S002" in per_site:
            assert per_site["S002"]["capas"] == []

    # ── Existing fields ───────────────────────────────────────────────────

    def test_rationale_mentions_risk_score(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                score_str = str(round(ctx["score"].risk_score, 1))
                assert score_str in c.rationale, (
                    f"{c.capa_id}: rationale missing risk score {score_str}"
                )

    def test_corrective_action_non_empty(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert c.corrective_action.strip()

    def test_preventive_action_non_empty(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert c.preventive_action.strip()

    def test_low_zero_deviation_site_has_no_capas(self, per_site):
        # S002: LOW risk, 0 deviations -> no CAPA needed
        if "S002" in per_site:
            assert per_site["S002"]["capas"] == []

    def test_critical_site_has_most_capas(self, per_site):
        # S003 is CRITICAL (5 deviations); its count should be >= any MEDIUM/LOW site
        if "S003" in per_site:
            s003_count = len(per_site["S003"]["capas"])
            for sid, ctx in per_site.items():
                if ctx["score"].risk_level in ("MEDIUM", "LOW"):
                    assert s003_count >= len(ctx["capas"]), (
                        f"CRITICAL site S003 ({s003_count}) should have >= "
                        f"capas than {sid} ({len(ctx['capas'])})"
                    )

    def test_capa_ids_are_sequential_per_site(self, per_site):
        for sid, ctx in per_site.items():
            for i, c in enumerate(ctx["capas"], start=1):
                expected_id = f"CAPA-{sid}-{i:03d}"
                assert c.capa_id == expected_id, (
                    f"Expected {expected_id}, got {c.capa_id}"
                )

    def test_one_capa_per_deviation_minimum(self, per_site):
        """Every individual DeviationRecord must have at least one matching CAPA."""
        for sid, ctx in per_site.items():
            for dev in ctx["site_devs"]:
                matched = [c for c in ctx["capas"] if dev.observation_id in c.issue]
                assert len(matched) >= 1, (
                    f"No CAPA found for deviation {dev.observation_id} at {sid}"
                )

    def test_minor_deviation_capa_severity_from_classifier(self, per_site):
        """Per-deviation CAPAs for Minor deviations must have severity='Minor'."""
        for sid, ctx in per_site.items():
            if ctx["score"].minor_deviations > 0:
                for dev in ctx["site_devs"]:
                    if dev.severity == "Minor":
                        matched = [c for c in ctx["capas"] if dev.observation_id in c.issue]
                        assert matched, f"No CAPA for Minor deviation {dev.observation_id}"
                        assert matched[0].severity == "Minor", (
                            f"{matched[0].capa_id}: expected severity=Minor, "
                            f"got {matched[0].severity}"
                        )
                        assert matched[0].priority == "High", (
                            f"{matched[0].capa_id}: expected priority=High, "
                            f"got {matched[0].priority}"
                        )


# ---------------------------------------------------------------------------
# Stage 4c: Member 4 — CAPA Report
# ---------------------------------------------------------------------------

class TestCAPAReport:
    def test_report_is_string(self, per_site):
        for sid, ctx in per_site.items():
            assert isinstance(ctx["report"], str), sid

    def test_report_non_empty(self, per_site):
        for sid, ctx in per_site.items():
            assert len(ctx["report"]) > 200, f"report too short for {sid}"

    def test_report_contains_site_id(self, per_site):
        for sid, ctx in per_site.items():
            assert sid in ctx["report"]

    def test_report_contains_risk_level(self, per_site):
        for sid, ctx in per_site.items():
            assert ctx["score"].risk_level in ctx["report"]

    def test_report_contains_deviation_count(self, per_site):
        for sid, ctx in per_site.items():
            total = str(ctx["score"].total_deviations)
            assert total in ctx["report"], (
                f"report for {sid} missing deviation count {total}"
            )

    def test_report_contains_ai_explanation_section(self, per_site):
        for sid, ctx in per_site.items():
            assert "## AI Risk Explanation" in ctx["report"]

    def test_report_contains_risk_summary_section(self, per_site):
        for sid, ctx in per_site.items():
            assert "## Risk Score Summary" in ctx["report"]

    def test_report_contains_deviation_detail_section(self, per_site):
        for sid, ctx in per_site.items():
            assert "## Deviation Detail" in ctx["report"]

    def test_report_contains_capa_section(self, per_site):
        for sid, ctx in per_site.items():
            assert "## CAPA Recommendations" in ctx["report"]

    def test_report_capa_ids_present(self, per_site):
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert c.capa_id in ctx["report"], (
                    f"{c.capa_id} not found in report for {sid}"
                )

    def test_report_references_real_deviations(self, per_site):
        for sid, ctx in per_site.items():
            for d in ctx["site_devs"]:
                assert d.observation_id in ctx["report"], (
                    f"{d.observation_id} not found in report for {sid}"
                )

    def test_report_references_patient_ids(self, per_site):
        for sid, ctx in per_site.items():
            for d in ctx["site_devs"]:
                assert d.patient_id in ctx["report"], (
                    f"{d.patient_id} not found in report for {sid}"
                )

    def test_report_marks_template_mode_without_credentials(self, per_site):
        if not watsonx_available():
            for sid, ctx in per_site.items():
                assert "deterministic template" in ctx["report"]

    def test_report_is_valid_markdown(self, per_site):
        for sid, ctx in per_site.items():
            # Basic markdown structural checks
            assert ctx["report"].startswith("# CAPA Report")
            assert "---" in ctx["report"]

    def test_report_contains_root_cause_section(self, per_site):
        """Report must render Root Cause for every CAPA that has one."""
        for sid, ctx in per_site.items():
            if ctx["capas"]:
                assert "Root Cause" in ctx["report"], (
                    f"report for {sid} missing Root Cause section"
                )

    def test_report_contains_risk_level_in_capa(self, per_site):
        """Report must render risk_level for each CAPA."""
        for sid, ctx in per_site.items():
            for c in ctx["capas"]:
                assert c.risk_level in ctx["report"], (
                    f"report for {sid} missing risk level {c.risk_level}"
                )

    def test_report_issue_section_present(self, per_site):
        """Report must use 'Issue / Deviation' heading (not 'Problem')."""
        for sid, ctx in per_site.items():
            if ctx["capas"]:
                assert "Issue / Deviation" in ctx["report"], (
                    f"report for {sid} missing 'Issue / Deviation' heading"
                )
