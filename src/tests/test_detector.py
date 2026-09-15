"""
test_detector.py — Tests for src/deviation/detector.py

Verifies:
- An observation exactly on the expected day → no deviation
- An observation inside the allowed window → no deviation
- An observation outside the allowed window → deviation detected
- Observations where actual_day is None → skipped (no deviation)
- Only VISIT_WINDOW rules are used; other rule types are ignored
- Multiple observations with mixed results → correct subset returned
- DeviationRecord fields are populated correctly
- detect_deviations returns an empty list when all visits are clean
- Works correctly with data produced by Member 1's interface
"""

from datetime import date

import pytest

from src.deviation.detector import detect_deviations, _index_window_rules
from src.deviation.models import DeviationRecord
from src.protocol.models import Observation, ProtocolRule


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _obs(
    observation_id: str = "OBS-0001",
    patient_id: str = "P001",
    site_id: str = "S001",
    visit_type: str = "WEEK_4",
    expected_day: int = 28,
    actual_day: int | None = 28,
) -> Observation:
    """Build a minimal valid Observation for testing."""
    return Observation(
        observation_id=observation_id,
        patient_id=patient_id,
        site_id=site_id,
        visit_type=visit_type,
        expected_day=expected_day,
        actual_day=actual_day,
    )


def _rule(
    rule_id: str = "RULE-001",
    rule_type: str = "VISIT_WINDOW",
    visit_type: str = "WEEK_4",
    expected_value: str = "28",
    allowed_window: int = 3,
    description: str = "WEEK_4 must occur within ±3 days of day 28.",
) -> ProtocolRule:
    """Build a minimal valid ProtocolRule for testing."""
    return ProtocolRule(
        rule_id=rule_id,
        rule_type=rule_type,
        description=description,
        visit_type=visit_type,
        expected_value=expected_value,
        allowed_window=allowed_window,
    )


# ---------------------------------------------------------------------------
# Tests — clean observations (no deviation expected)
# ---------------------------------------------------------------------------

class TestNoDeviation:
    """Observations that should NOT produce a DeviationRecord."""

    def test_exact_expected_day_no_deviation(self) -> None:
        """actual_day == expected_day → difference is 0 → no deviation."""
        obs  = _obs(actual_day=28, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result == [], "Visit on exact expected day must not be flagged."

    def test_one_day_early_inside_window(self) -> None:
        """actual_day = expected_day - 1, window = 3 → difference 1 ≤ 3 → no deviation."""
        obs  = _obs(actual_day=27, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result == []

    def test_one_day_late_inside_window(self) -> None:
        """actual_day = expected_day + 1, window = 3 → difference 1 ≤ 3 → no deviation."""
        obs  = _obs(actual_day=29, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        assert detect_deviations([obs], [rule]) == []

    def test_exactly_at_window_boundary_no_deviation(self) -> None:
        """difference == allowed_window → still within window → no deviation."""
        obs  = _obs(actual_day=31, expected_day=28)  # difference = 3, window = 3
        rule = _rule(expected_value="28", allowed_window=3)

        assert detect_deviations([obs], [rule]) == []

    def test_actual_day_none_is_skipped(self) -> None:
        """actual_day=None means the visit hasn't been recorded yet — skip it."""
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result == [], "Unrecorded visit (actual_day=None) must not produce a deviation."

    def test_empty_observations_list(self) -> None:
        """No observations → no deviations."""
        rule = _rule()
        assert detect_deviations([], [rule]) == []

    def test_empty_rules_list(self) -> None:
        """No rules → nothing to check against → no deviations."""
        obs = _obs(actual_day=40, expected_day=28)
        assert detect_deviations([obs], []) == []

    def test_no_matching_rule_for_visit_type(self) -> None:
        """Observation has a visit_type with no corresponding rule → skipped."""
        obs  = _obs(visit_type="MONTH_6", actual_day=200, expected_day=180)
        rule = _rule(visit_type="WEEK_4")   # different visit type

        assert detect_deviations([obs], [rule]) == []


# ---------------------------------------------------------------------------
# Tests — deviations detected
# ---------------------------------------------------------------------------

class TestDeviationDetected:
    """Observations that SHOULD produce a DeviationRecord."""

    def test_one_day_beyond_window_is_deviation(self) -> None:
        """difference = allowed_window + 1 → deviation detected."""
        # expected_day=28, actual_day=32, window=3 → difference=4 > 3
        obs  = _obs(actual_day=32, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert len(result) == 1

    def test_deviation_record_fields_are_correct(self) -> None:
        """Every field on the returned DeviationRecord must be correct."""
        obs  = _obs(
            observation_id="OBS-0042",
            patient_id="P007",
            site_id="S002",
            visit_type="WEEK_8",
            expected_day=56,
            actual_day=66,   # 10 days late, window=3 → deviation
        )
        rule = _rule(
            rule_id="RULE-003",
            visit_type="WEEK_8",
            expected_value="56",
            allowed_window=3,
        )

        result = detect_deviations([obs], [rule])

        assert len(result) == 1
        rec = result[0]

        assert rec.observation_id == "OBS-0042"
        assert rec.patient_id     == "P007"
        assert rec.site_id        == "S002"
        assert rec.visit_type     == "WEEK_8"
        assert rec.deviation_type == "VISIT_WINDOW"
        assert rec.expected       == 56
        assert rec.actual         == 66
        assert rec.difference     == 10
        assert rec.allowed_window == 3
        assert rec.status         == "OPEN"

    def test_early_visit_also_flagged(self) -> None:
        """A visit that happened too early is also a deviation."""
        # actual_day=18, expected_day=28, window=3 → difference=10 > 3
        obs  = _obs(actual_day=18, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert len(result) == 1
        assert result[0].difference == 10

    def test_result_is_list_of_deviation_records(self) -> None:
        """detect_deviations must return a list of DeviationRecord instances."""
        obs  = _obs(actual_day=40, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert isinstance(result, list)
        assert all(isinstance(r, DeviationRecord) for r in result)


# ---------------------------------------------------------------------------
# Tests — mixed observations
# ---------------------------------------------------------------------------

class TestMixedObservations:
    """Multiple observations where some deviate and some do not."""

    def test_only_deviating_observations_returned(self) -> None:
        """Clean visits must not appear in the output."""
        rule = _rule(expected_value="28", allowed_window=3)

        observations = [
            _obs("OBS-0001", actual_day=28),    # exact day — clean
            _obs("OBS-0002", actual_day=30),    # +2 within window — clean
            _obs("OBS-0003", actual_day=35),    # +7 beyond window — DEVIATION
            _obs("OBS-0004", actual_day=25),    # -3 exactly at boundary — clean
            _obs("OBS-0005", actual_day=20),    # -8 beyond window — DEVIATION
        ]

        result = detect_deviations(observations, [rule])

        assert len(result) == 2
        returned_ids = {r.observation_id for r in result}
        assert returned_ids == {"OBS-0003", "OBS-0005"}

    def test_multiple_visit_types_each_checked_against_own_rule(self) -> None:
        """Each visit type is checked against its own VISIT_WINDOW rule."""
        rule_week4  = _rule("RULE-001", visit_type="WEEK_4",  expected_value="28", allowed_window=3)
        rule_week8  = _rule("RULE-002", visit_type="WEEK_8",  expected_value="56", allowed_window=3)
        rule_week12 = _rule("RULE-003", visit_type="WEEK_12", expected_value="84", allowed_window=3)

        observations = [
            _obs("OBS-0001", visit_type="WEEK_4",  expected_day=28, actual_day=28),  # clean
            _obs("OBS-0002", visit_type="WEEK_8",  expected_day=56, actual_day=65),  # DEVIATION (+9)
            _obs("OBS-0003", visit_type="WEEK_12", expected_day=84, actual_day=85),  # clean (+1)
        ]

        result = detect_deviations(observations, [rule_week4, rule_week8, rule_week12])

        assert len(result) == 1
        assert result[0].observation_id == "OBS-0002"
        assert result[0].visit_type     == "WEEK_8"

    def test_non_visit_window_rules_are_ignored(self) -> None:
        """ELIGIBILITY, DOSING, and LAB_RANGE rules must not trigger deviations."""
        eligibility_rule = ProtocolRule(
            rule_id="RULE-E01",
            rule_type="ELIGIBILITY",
            description="Patient must be 18+.",
            visit_type="BASELINE",
        )
        dosing_rule = ProtocolRule(
            rule_id="RULE-D01",
            rule_type="DOSING",
            description="Dose must be administered within window.",
            visit_type="WEEK_4",
            expected_value="28",
            allowed_window=3,
        )

        obs = _obs(actual_day=40, expected_day=28)  # would be a deviation under VISIT_WINDOW

        # With only non-VISIT_WINDOW rules, no deviations should be detected.
        result = detect_deviations([obs], [eligibility_rule, dosing_rule])

        assert result == [], (
            "Non-VISIT_WINDOW rules must not be used for deviation detection."
        )

    def test_all_none_actual_days_returns_empty(self) -> None:
        """When all observations are unrecorded, the result must be empty."""
        rule = _rule()
        observations = [
            _obs("OBS-0001", actual_day=None),
            _obs("OBS-0002", actual_day=None),
        ]
        assert detect_deviations(observations, [rule]) == []


# ---------------------------------------------------------------------------
# Tests — integration with Member 1's live data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def live_deviations() -> list[DeviationRecord]:
    """Load the real dataset and run detection once for the whole class."""
    from src.protocol.interface import load_project_data
    data = load_project_data()
    return detect_deviations(data["observations"], data["protocol_rules"])


class TestWithLiveData:
    """Run the detector against the actual generated dataset."""

    def test_returns_a_list(self, live_deviations) -> None:
        assert isinstance(live_deviations, list)

    def test_all_items_are_deviation_records(self, live_deviations) -> None:
        for item in live_deviations:
            assert isinstance(item, DeviationRecord)

    def test_at_least_one_deviation_found(self, live_deviations) -> None:
        """The generator plants ~8% anomalies, so at least one must be found."""
        assert len(live_deviations) > 0, (
            "Expected at least one deviation in the generated dataset "
            "(generator plants ~8% out-of-window observations)."
        )

    def test_all_statuses_are_open(self, live_deviations) -> None:
        """Newly detected deviations must all start as OPEN."""
        for rec in live_deviations:
            assert rec.status == "OPEN"

    def test_difference_always_positive(self, live_deviations) -> None:
        for rec in live_deviations:
            assert rec.difference > 0

    def test_difference_always_exceeds_window(self, live_deviations) -> None:
        """Every returned record must have difference > allowed_window."""
        for rec in live_deviations:
            assert rec.difference > rec.allowed_window, (
                f"Record {rec.observation_id}: difference {rec.difference} "
                f"does not exceed window {rec.allowed_window}."
            )

    def test_severity_is_valid_value(self, live_deviations) -> None:
        valid = {"Administrative", "Minor", "Major"}
        for rec in live_deviations:
            assert rec.severity in valid

    def test_deviation_type_is_visit_window(self, live_deviations) -> None:
        """All deviations from this detector must be of type VISIT_WINDOW."""
        for rec in live_deviations:
            assert rec.deviation_type == "VISIT_WINDOW"


# ---------------------------------------------------------------------------
# Tests — private helper
# ---------------------------------------------------------------------------

class TestIndexWindowRules:
    """Unit tests for the internal _index_window_rules helper."""

    def test_indexes_only_visit_window_rules(self) -> None:
        rules = [
            _rule("R1", rule_type="VISIT_WINDOW", visit_type="WEEK_4"),
            ProtocolRule(
                rule_id="R2",
                rule_type="ELIGIBILITY",
                description="Age requirement.",
                visit_type="BASELINE",
            ),
        ]
        index = _index_window_rules(rules)
        assert "WEEK_4"   in index
        assert "BASELINE" not in index

    def test_returns_empty_dict_for_no_visit_window_rules(self) -> None:
        rules = [
            ProtocolRule(rule_id="R1", rule_type="ELIGIBILITY", description="Age."),
        ]
        assert _index_window_rules(rules) == {}

    def test_returns_empty_dict_for_empty_list(self) -> None:
        assert _index_window_rules([]) == {}
