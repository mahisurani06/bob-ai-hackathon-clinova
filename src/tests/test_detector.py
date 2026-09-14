"""
test_detector.py — Tests for src/deviation/detector.py

Verifies:
- An observation exactly on the expected day → no deviation
- An observation inside the allowed window → no deviation
- An observation outside the allowed window → deviation detected
- Observations where actual_day is None and a matching rule exists → MISSING_DATA deviation
- Observations where actual_day is None and NO rule exists → skipped
- Only VISIT_WINDOW rules drive window checks; other rule types are ignored
- Multiple observations with mixed results → correct subset returned
- DeviationRecord fields are populated correctly
- detect_deviations returns an empty list when all visits are clean
- Works correctly with data produced by Member 1's interface
- ELIGIBILITY violations detected when participants are passed
- MISSING_DATA deviations detected for unrecorded required visits
- New optional fields (rule_id, direction, reason) are correctly populated
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

    def test_actual_day_none_with_matching_rule_produces_missing_data_deviation(self) -> None:
        """actual_day=None with a matching VISIT_WINDOW rule → MISSING_DATA deviation.

        Previously this was silently skipped.  The detector now raises a
        MISSING_DATA deviation so that unrecorded required visits are surfaced.
        """
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert len(result) == 1
        assert result[0].deviation_type == "MISSING_DATA"
        assert result[0].observation_id == obs.observation_id

    def test_actual_day_none_without_matching_rule_is_skipped(self) -> None:
        """actual_day=None with NO matching rule → silently skipped (not a protocol violation)."""
        obs  = _obs(visit_type="CUSTOM_VISIT", actual_day=None, expected_day=28)
        rule = _rule(visit_type="WEEK_4")   # different visit type — no rule for CUSTOM_VISIT

        result = detect_deviations([obs], [rule])

        assert result == [], "Unrecorded visit with no rule must not produce a deviation."

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

    def test_all_none_actual_days_with_matching_rules_produce_missing_data(self) -> None:
        """When all observations are unrecorded and rules exist, MISSING_DATA is raised.

        Previously this returned an empty list.  The detector now surfaces
        unrecorded required visits as MISSING_DATA deviations.
        """
        rule = _rule()   # VISIT_WINDOW for WEEK_4
        observations = [
            _obs("OBS-0001", actual_day=None),
            _obs("OBS-0002", actual_day=None),
        ]
        result = detect_deviations(observations, [rule])

        assert len(result) == 2
        assert all(r.deviation_type == "MISSING_DATA" for r in result)

    def test_all_none_actual_days_no_matching_rules_returns_empty(self) -> None:
        """When all observations are unrecorded and NO rules match, result is empty."""
        rule = _rule(visit_type="WEEK_8")   # VISIT_WINDOW only for WEEK_8
        observations = [
            _obs("OBS-0001", visit_type="BASELINE", actual_day=None),
            _obs("OBS-0002", visit_type="WEEK_4",   actual_day=None),
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

    def test_deviation_types_are_valid(self, live_deviations) -> None:
        """All deviations must be of a recognised type.

        The live fixture calls detect_deviations without participants, so
        results will be VISIT_WINDOW and/or MISSING_DATA only.
        """
        valid_types = {"VISIT_WINDOW", "MISSING_DATA", "ELIGIBILITY"}
        for rec in live_deviations:
            assert rec.deviation_type in valid_types, (
                f"Unexpected deviation_type: {rec.deviation_type!r}"
            )

    def test_visit_window_deviations_are_present(self, live_deviations) -> None:
        """At least some deviations must be VISIT_WINDOW (generator plants anomalies)."""
        visit_window_devs = [r for r in live_deviations if r.deviation_type == "VISIT_WINDOW"]
        assert len(visit_window_devs) > 0, "Expected at least one VISIT_WINDOW deviation."


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


# ---------------------------------------------------------------------------
# New tests — VISIT_WINDOW enrichment fields (rule_id, direction, reason)
# ---------------------------------------------------------------------------

class TestVisitWindowEnrichmentFields:
    """New optional fields added to DeviationRecord must be populated correctly."""

    def test_rule_id_is_populated(self) -> None:
        obs  = _obs(actual_day=40, expected_day=28)
        rule = _rule(rule_id="RULE-002", expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert len(result) == 1
        assert result[0].rule_id == "RULE-002"

    def test_direction_is_late_when_actual_after_expected(self) -> None:
        # actual_day=35, expected_day=28 → late
        obs  = _obs(actual_day=35, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert len(result) == 1
        assert result[0].direction == "late"

    def test_direction_is_early_when_actual_before_expected(self) -> None:
        # actual_day=18, expected_day=28 → early
        obs  = _obs(actual_day=18, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert len(result) == 1
        assert result[0].direction == "early"

    def test_reason_is_non_empty_string(self) -> None:
        obs  = _obs(actual_day=40, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert len(result) == 1
        assert isinstance(result[0].reason, str)
        assert len(result[0].reason) > 0

    def test_clean_observation_has_no_rule_id_in_output(self) -> None:
        """Clean visits never appear in results — no record, no rule_id."""
        obs  = _obs(actual_day=28, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result == []


# ---------------------------------------------------------------------------
# New tests — MISSING_DATA detection
# ---------------------------------------------------------------------------

from datetime import date as _date

def _participant(
    patient_id: str = "P001",
    site_id: str = "S001",
    age: int = 35,
    gender: str = "MALE",
    enrollment_date=None,
    status: str = "ENROLLED",
):
    """Build a minimal valid Participant for testing."""
    from src.protocol.models import Participant
    return Participant(
        patient_id=patient_id,
        site_id=site_id,
        age=age,
        gender=gender,
        enrollment_date=enrollment_date or _date(2023, 1, 1),
        status=status,
    )


class TestMissingDataDetection:
    """Observations with actual_day=None and a matching rule → MISSING_DATA deviation."""

    def test_none_actual_day_with_rule_produces_deviation(self) -> None:
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert len(result) == 1

    def test_missing_data_deviation_type_is_correct(self) -> None:
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result[0].deviation_type == "MISSING_DATA"

    def test_missing_data_direction_is_missing(self) -> None:
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result[0].direction == "missing"

    def test_missing_data_severity_is_minor(self) -> None:
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result[0].severity == "Minor"

    def test_missing_data_difference_exceeds_allowed_window(self) -> None:
        """The downstream invariant difference > allowed_window must hold."""
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result[0].difference > result[0].allowed_window

    def test_missing_data_actual_is_sentinel_minus_one(self) -> None:
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result[0].actual == -1

    def test_missing_data_expected_matches_scheduled_day(self) -> None:
        # visit_type must match the rule's visit_type so the rule is found
        obs  = _obs(visit_type="WEEK_8", actual_day=None, expected_day=56)
        rule = _rule(visit_type="WEEK_8", expected_value="56", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result[0].expected == 56

    def test_missing_data_rule_id_populated(self) -> None:
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(rule_id="RULE-002", expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result[0].rule_id == "RULE-002"

    def test_none_actual_without_matching_rule_is_skipped(self) -> None:
        """If there is no VISIT_WINDOW rule for the visit type, don't flag missing data."""
        obs  = _obs(visit_type="CUSTOM_VISIT", actual_day=None, expected_day=28)
        rule = _rule(visit_type="WEEK_4", expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        assert result == []

    def test_recorded_visit_does_not_produce_missing_data_deviation(self) -> None:
        obs  = _obs(actual_day=28, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        # The visit is within window — no deviation of any kind
        assert result == []

    def test_no_duplicate_for_same_missing_observation(self) -> None:
        """Each observation produces at most one MISSING_DATA record."""
        obs  = _obs(actual_day=None, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])

        missing_data_records = [r for r in result if r.deviation_type == "MISSING_DATA"]
        assert len(missing_data_records) == 1


# ---------------------------------------------------------------------------
# New tests — ELIGIBILITY detection
# ---------------------------------------------------------------------------

def _eligibility_rule_min(
    rule_id: str = "RULE-005",
    expected_value: str = "25",
    description: str = "Patient must be at least 25 years old at enrollment.",
) -> ProtocolRule:
    """Build a minimum-age ELIGIBILITY rule.

    Default threshold is 25 so that a valid Participant (age >= 18 per the
    Participant model) can still violate the rule (e.g. age=19 < 25).
    Tests that need to verify the minimum-age protocol rule from the actual
    dataset (expected_value="18") pass the value explicitly.
    """
    return ProtocolRule(
        rule_id=rule_id,
        rule_type="ELIGIBILITY",
        description=description,
        visit_type=None,
        expected_value=expected_value,
        allowed_window=None,
    )


def _eligibility_rule_max(
    rule_id: str = "RULE-006",
    expected_value: str = "75",
    description: str = "Patient must be no older than 75 years old at enrollment.",
) -> ProtocolRule:
    """Build a maximum-age ELIGIBILITY rule."""
    return ProtocolRule(
        rule_id=rule_id,
        rule_type="ELIGIBILITY",
        description=description,
        visit_type=None,
        expected_value=expected_value,
        allowed_window=None,
    )


class TestEligibilityDetection:
    """Participant age violations against ELIGIBILITY rules.

    All participants are constructed with age values that satisfy the
    Participant model constraint (ge=18, le=99).  Under-minimum scenarios
    use a rule threshold above 18 so that a valid participant age can still
    fall below the protocol threshold.

    Example: rule expected_value="25" (at least 25 years) + participant age=19
    → valid Participant, ELIGIBILITY violation detected (19 < 25).
    """

    def test_under_age_participant_produces_deviation(self) -> None:
        # age=19 is a valid Participant (>= 18) but violates the rule threshold of 25
        participant = _participant(age=19)
        rule = _eligibility_rule_min()  # threshold = 25

        result = detect_deviations([], [rule], participants=[participant])

        assert len(result) == 1

    def test_over_age_participant_produces_deviation(self) -> None:
        participant = _participant(age=80)
        rule = _eligibility_rule_max()

        result = detect_deviations([], [rule], participants=[participant])

        assert len(result) == 1

    def test_eligible_participant_produces_no_deviation(self) -> None:
        participant = _participant(age=40)
        rules = [_eligibility_rule_min(), _eligibility_rule_max()]

        result = detect_deviations([], rules, participants=[participant])

        eligibility_devs = [r for r in result if r.deviation_type == "ELIGIBILITY"]
        assert eligibility_devs == []

    def test_participant_at_min_boundary_is_eligible(self) -> None:
        """Age == rule minimum threshold is exactly eligible (not a violation)."""
        participant = _participant(age=25)
        rule = _eligibility_rule_min()  # threshold = 25

        result = detect_deviations([], [rule], participants=[participant])

        assert result == []

    def test_participant_at_max_boundary_is_eligible(self) -> None:
        """Age == maximum threshold is exactly eligible (<= 75)."""
        participant = _participant(age=75)
        rule = _eligibility_rule_max()

        result = detect_deviations([], [rule], participants=[participant])

        assert result == []

    def test_eligibility_deviation_type_is_correct(self) -> None:
        participant = _participant(age=19)
        rule = _eligibility_rule_min()  # threshold = 25

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].deviation_type == "ELIGIBILITY"

    def test_eligibility_severity_is_major(self) -> None:
        participant = _participant(age=19)
        rule = _eligibility_rule_min()  # threshold = 25

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].severity == "Major"

    def test_eligibility_visit_type_is_enrollment(self) -> None:
        participant = _participant(age=19)
        rule = _eligibility_rule_min()  # threshold = 25

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].visit_type == "ENROLLMENT"

    def test_eligibility_expected_is_threshold(self) -> None:
        participant = _participant(age=19)
        rule = _eligibility_rule_min(expected_value="25")

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].expected == 25

    def test_eligibility_actual_is_participant_age(self) -> None:
        participant = _participant(age=19)
        rule = _eligibility_rule_min(expected_value="25")

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].actual == 19

    def test_eligibility_difference_is_age_gap(self) -> None:
        # age=19, threshold=25 → difference = 6
        participant = _participant(age=19)
        rule = _eligibility_rule_min(expected_value="25")

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].difference == 6

    def test_eligibility_difference_exceeds_allowed_window(self) -> None:
        """Downstream invariant: difference > allowed_window."""
        participant = _participant(age=19)
        rule = _eligibility_rule_min(expected_value="25")

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].difference > result[0].allowed_window

    def test_eligibility_rule_id_populated(self) -> None:
        participant = _participant(age=19)
        rule = _eligibility_rule_min(rule_id="RULE-005")

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].rule_id == "RULE-005"

    def test_eligibility_reason_is_non_empty_string(self) -> None:
        participant = _participant(age=19)
        rule = _eligibility_rule_min()  # threshold = 25

        result = detect_deviations([], [rule], participants=[participant])

        assert isinstance(result[0].reason, str)
        assert len(result[0].reason) > 0

    def test_eligibility_patient_id_matches_participant(self) -> None:
        participant = _participant(patient_id="P042", age=19)
        rule = _eligibility_rule_min()

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].patient_id == "P042"

    def test_eligibility_site_id_matches_participant(self) -> None:
        participant = _participant(site_id="S003", age=19)
        rule = _eligibility_rule_min()

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].site_id == "S003"

    def test_no_participants_skips_eligibility_pass(self) -> None:
        """Without participants argument, ELIGIBILITY detection is skipped."""
        rule = _eligibility_rule_min()

        result = detect_deviations([], [rule])    # no participants kwarg

        assert result == []

    def test_one_record_per_participant_per_rule(self) -> None:
        """Each (participant, rule) pair produces exactly one deviation record.

        Uses two distinct ELIGIBILITY rules with different rule_ids so that
        the two synthetic observation_ids are also distinct.
        """
        participant = _participant(age=19)
        # Two distinct minimum-age rules — different rule_ids, same threshold
        rules = [
            _eligibility_rule_min(rule_id="RULE-A", expected_value="25"),
            _eligibility_rule_min(rule_id="RULE-B", expected_value="25"),
        ]

        result = detect_deviations([], rules, participants=[participant])

        eligibility_devs = [r for r in result if r.deviation_type == "ELIGIBILITY"]
        # One record per rule × participant pair
        assert len(eligibility_devs) == 2
        # Each has a distinct observation_id (includes rule_id in it)
        obs_ids = [r.observation_id for r in eligibility_devs]
        assert len(obs_ids) == len(set(obs_ids)), "Observation IDs must be unique per rule"

    def test_over_age_direction_is_late(self) -> None:
        participant = _participant(age=80)
        rule = _eligibility_rule_max()

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].direction == "late"

    def test_under_age_direction_is_early(self) -> None:
        # age=19 is valid (>= 18) but below the rule threshold of 25 → early
        participant = _participant(age=19)
        rule = _eligibility_rule_min()  # threshold = 25

        result = detect_deviations([], [rule], participants=[participant])

        assert result[0].direction == "early"


# ---------------------------------------------------------------------------
# New tests — combined detection (VISIT_WINDOW + MISSING_DATA + ELIGIBILITY)
# ---------------------------------------------------------------------------

class TestCombinedDetection:
    """Verify all three detection passes produce independent, non-duplicated results."""

    def test_all_three_types_detected_together(self) -> None:
        window_rule = _rule(rule_id="RULE-002", expected_value="28", allowed_window=3)
        # Rule threshold=25; participant age=19 is valid (>=18) but violates the rule
        elig_rule   = _eligibility_rule_min(rule_id="RULE-005")  # threshold=25

        recorded_out_of_window = _obs("OBS-0001", actual_day=40, expected_day=28)
        missing_visit          = _obs("OBS-0002", actual_day=None, expected_day=28)

        under_threshold_participant = _participant(patient_id="P099", age=19)

        result = detect_deviations(
            observations   = [recorded_out_of_window, missing_visit],
            protocol_rules = [window_rule, elig_rule],
            participants   = [under_threshold_participant],
        )

        types = {r.deviation_type for r in result}
        assert "VISIT_WINDOW"  in types
        assert "MISSING_DATA"  in types
        assert "ELIGIBILITY"   in types

    def test_no_duplicates_across_passes(self) -> None:
        """No observation should appear twice in the output."""
        window_rule = _rule(rule_id="RULE-002", expected_value="28", allowed_window=3)
        obs_out = _obs("OBS-0001", actual_day=40, expected_day=28)
        obs_missing = _obs("OBS-0002", actual_day=None, expected_day=28)

        result = detect_deviations([obs_out, obs_missing], [window_rule])

        obs_ids = [r.observation_id for r in result]
        assert len(obs_ids) == len(set(obs_ids)), "Duplicate observation IDs found"

    def test_all_records_satisfy_downstream_invariant(self) -> None:
        """Every returned record must have difference > allowed_window."""
        window_rule = _rule(rule_id="RULE-002", expected_value="28", allowed_window=3)
        elig_rule   = _eligibility_rule_min(rule_id="RULE-005")  # threshold=25

        obs_out     = _obs("OBS-0001", actual_day=40, expected_day=28)
        obs_missing = _obs("OBS-0002", actual_day=None, expected_day=28)
        participant = _participant(age=19)  # valid (>=18), violates rule threshold of 25

        result = detect_deviations(
            observations   = [obs_out, obs_missing],
            protocol_rules = [window_rule, elig_rule],
            participants   = [participant],
        )

        for rec in result:
            assert rec.difference > rec.allowed_window, (
                f"Invariant violated for {rec.observation_id} "
                f"({rec.deviation_type}): "
                f"difference={rec.difference}, window={rec.allowed_window}"
            )

    def test_all_severities_are_valid(self) -> None:
        window_rule = _rule(rule_id="RULE-002", expected_value="28", allowed_window=3)
        elig_rule   = _eligibility_rule_min(rule_id="RULE-005")  # threshold=25

        obs_out     = _obs("OBS-0001", actual_day=40, expected_day=28)
        obs_missing = _obs("OBS-0002", actual_day=None, expected_day=28)
        participant = _participant(age=19)  # valid (>=18), violates rule threshold of 25

        result = detect_deviations(
            observations   = [obs_out, obs_missing],
            protocol_rules = [window_rule, elig_rule],
            participants   = [participant],
        )

        valid = {"Administrative", "Minor", "Major"}
        for rec in result:
            assert rec.severity in valid, f"Invalid severity {rec.severity!r}"


# ---------------------------------------------------------------------------
# New tests — downstream compatibility (existing interface unchanged)
# ---------------------------------------------------------------------------

class TestDownstreamCompatibility:
    """Verify that existing downstream consumers still work with the upgraded module."""

    def test_detect_deviations_original_signature_still_works(self) -> None:
        """The two-argument signature (no participants) must continue to work."""
        obs  = _obs(actual_day=40, expected_day=28)
        rule = _rule(expected_value="28", allowed_window=3)

        result = detect_deviations([obs], [rule])   # no participants argument

        assert isinstance(result, list)
        assert all(isinstance(r, DeviationRecord) for r in result)

    def test_existing_fields_are_still_present_on_visit_window_record(self) -> None:
        """All fields that downstream modules depend on must remain unchanged."""
        obs  = _obs(
            observation_id="OBS-0099",
            patient_id="P010",
            site_id="S002",
            visit_type="WEEK_8",
            expected_day=56,
            actual_day=70,
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

        # Core locked fields
        assert rec.observation_id  == "OBS-0099"
        assert rec.patient_id      == "P010"
        assert rec.site_id         == "S002"
        assert rec.visit_type      == "WEEK_8"
        assert rec.deviation_type  == "VISIT_WINDOW"
        assert rec.expected        == 56
        assert rec.actual          == 70
        assert rec.difference      == 14
        assert rec.allowed_window  == 3
        assert rec.status          == "OPEN"
        assert rec.severity        in {"Administrative", "Minor", "Major"}

        # New optional fields — must exist but may be None for old-style consumers
        assert hasattr(rec, "rule_id")
        assert hasattr(rec, "direction")
        assert hasattr(rec, "reason")

    def test_malformed_rule_expected_value_skipped_gracefully(self) -> None:
        """A rule with a non-integer expected_value must not crash the pipeline."""
        obs = _obs(actual_day=40, expected_day=28)
        bad_rule = ProtocolRule(
            rule_id="RULE-BAD",
            rule_type="VISIT_WINDOW",
            description="Bad rule.",
            visit_type="WEEK_4",
            expected_value="not-a-number",
            allowed_window=3,
        )

        result = detect_deviations([obs], [bad_rule])

        assert result == []

    def test_empty_inputs_return_empty_list(self) -> None:
        assert detect_deviations([], []) == []

    def test_live_data_visit_window_deviations_unchanged(self) -> None:
        """With the original two-arg call, VISIT_WINDOW results are the same as before."""
        from src.protocol.interface import load_project_data
        data = load_project_data()

        result = detect_deviations(
            observations   = data["observations"],
            protocol_rules = data["protocol_rules"],
        )

        assert isinstance(result, list)
        assert len(result) > 0
        # Without participants, all deviations should be VISIT_WINDOW or MISSING_DATA only
        non_visit = [r for r in result if r.deviation_type not in ("VISIT_WINDOW", "MISSING_DATA")]
        assert non_visit == [], f"Unexpected deviation types: {set(r.deviation_type for r in non_visit)}"

    def test_live_data_all_records_satisfy_invariant(self) -> None:
        """difference > allowed_window for every record produced on real data."""
        from src.protocol.interface import load_project_data
        data = load_project_data()

        result = detect_deviations(
            observations   = data["observations"],
            protocol_rules = data["protocol_rules"],
            participants   = data["participants"],
        )

        for rec in result:
            assert rec.difference > rec.allowed_window, (
                f"{rec.observation_id} ({rec.deviation_type}): "
                f"difference={rec.difference} window={rec.allowed_window}"
            )
