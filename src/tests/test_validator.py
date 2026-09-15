"""
test_validator.py — Tests for src/protocol/validator.py

Verifies:
- The live generated dataset passes full validation without errors
- Each individual check correctly rejects specific bad-data scenarios
- actual_day=None produces a WARNING, not an error
- Out-of-window observations are NOT flagged as errors here
  (that check belongs to Member 2's deviation detector, not to
   Member 1's data-quality validator)
"""

from datetime import date

import pytest

from src.protocol.loader import load_all_data
from src.protocol.models import (
    Observation,
    Participant,
    ProtocolRule,
    Site,
    Trial,
)
from src.protocol.validator import (
    validate_all,
    validate_observations,
    validate_participants,
    validate_protocol_rules,
    validate_sites,
    validate_trials,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live_data() -> dict:
    """Load the real generated dataset once for the whole module."""
    return load_all_data()


# ---------------------------------------------------------------------------
# Helper factories — build minimal valid objects for injection tests
# ---------------------------------------------------------------------------

def _make_trial(**kwargs) -> Trial:
    defaults = dict(trial_id="TRIAL-T1", trial_name="Test Trial", version="1.0", status="ACTIVE")
    return Trial(**{**defaults, **kwargs})


def _make_site(**kwargs) -> Site:
    defaults = dict(
        site_id="SX01", trial_id="TRIAL-001",
        site_name="Test Site", country="India", status="ACTIVE",
    )
    return Site(**{**defaults, **kwargs})


def _make_participant(**kwargs) -> Participant:
    defaults = dict(
        patient_id="PX01", trial_id="TRIAL-001", site_id="S001", age=30,
        gender="MALE", enrollment_date=date(2023, 1, 1), status="ENROLLED",
    )
    return Participant(**{**defaults, **kwargs})


def _make_observation(**kwargs) -> Observation:
    defaults = dict(
        observation_id="OBS-X001", trial_id="TRIAL-001", patient_id="P001",
        site_id="S001", visit_type="BASELINE", expected_day=0, actual_day=0,
    )
    return Observation(**{**defaults, **kwargs})


def _make_rule(**kwargs) -> ProtocolRule:
    defaults = dict(rule_id="RULE-X1", rule_type="ELIGIBILITY", description="Test rule")
    return ProtocolRule(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# Tests — validate_all() on the live dataset
# ---------------------------------------------------------------------------

class TestValidateAllLiveData:
    """The generated dataset must pass all validation checks."""

    def test_valid_returns_true(self, live_data: dict) -> None:
        result = validate_all(live_data)
        assert result["valid"] is True

    def test_no_errors_on_clean_data(self, live_data: dict) -> None:
        result = validate_all(live_data)
        assert result["errors"] == []

    def test_no_warnings_on_clean_data(self, live_data: dict) -> None:
        """The generated data has no None actual_day rows, so no warnings."""
        result = validate_all(live_data)
        assert result["warnings"] == []

    def test_result_has_required_keys(self, live_data: dict) -> None:
        result = validate_all(live_data)
        assert "valid"    in result
        assert "errors"   in result
        assert "warnings" in result


# ---------------------------------------------------------------------------
# Tests — validate_trials()
# ---------------------------------------------------------------------------

class TestValidateTrials:

    def test_valid_trials_pass(self, live_data: dict) -> None:
        assert validate_trials(live_data["trials"])["valid"] is True

    def test_empty_list_is_invalid(self) -> None:
        result = validate_trials([])
        assert result["valid"] is False
        assert any("empty" in e.lower() for e in result["errors"])

    def test_duplicate_trial_id_is_invalid(self, live_data: dict) -> None:
        dup = _make_trial(trial_id=live_data["trials"][0].trial_id)
        result = validate_trials(live_data["trials"] + [dup])
        assert result["valid"] is False
        assert any("duplicate" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# Tests — validate_sites()
# ---------------------------------------------------------------------------

class TestValidateSites:

    def test_valid_sites_pass(self, live_data: dict) -> None:
        assert validate_sites(live_data["sites"])["valid"] is True

    def test_empty_list_is_invalid(self) -> None:
        result = validate_sites([])
        assert result["valid"] is False

    def test_duplicate_site_id_is_invalid(self, live_data: dict) -> None:
        dup = _make_site(site_id=live_data["sites"][0].site_id)
        result = validate_sites(live_data["sites"] + [dup])
        assert result["valid"] is False
        assert any("duplicate" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# Tests — validate_participants()
# ---------------------------------------------------------------------------

class TestValidateParticipants:

    def test_valid_participants_pass(self, live_data: dict) -> None:
        result = validate_participants(live_data["participants"], live_data["sites"])
        assert result["valid"] is True

    def test_empty_list_is_invalid(self, live_data: dict) -> None:
        result = validate_participants([], live_data["sites"])
        assert result["valid"] is False

    def test_duplicate_patient_id_is_invalid(self, live_data: dict) -> None:
        dup = _make_participant(patient_id=live_data["participants"][0].patient_id)
        result = validate_participants(live_data["participants"] + [dup], live_data["sites"])
        assert result["valid"] is False
        assert any("duplicate" in e.lower() for e in result["errors"])

    def test_unknown_site_id_is_invalid(self, live_data: dict) -> None:
        bad = _make_participant(patient_id="P_NEW", site_id="S_DOES_NOT_EXIST")
        result = validate_participants(live_data["participants"] + [bad], live_data["sites"])
        assert result["valid"] is False
        assert any("unknown" in e.lower() or "s_does_not_exist" in e.lower()
                   for e in result["errors"])


# ---------------------------------------------------------------------------
# Tests — validate_observations()
# ---------------------------------------------------------------------------

class TestValidateObservations:

    def test_valid_observations_pass(self, live_data: dict) -> None:
        result = validate_observations(
            live_data["observations"],
            live_data["participants"],
            live_data["sites"],
        )
        assert result["valid"] is True

    def test_empty_list_is_invalid(self, live_data: dict) -> None:
        result = validate_observations([], live_data["participants"], live_data["sites"])
        assert result["valid"] is False

    def test_unknown_patient_id_is_invalid(self, live_data: dict) -> None:
        bad = _make_observation(observation_id="OBS-NEW1", patient_id="P_GHOST", site_id="S001")
        result = validate_observations(
            live_data["observations"] + [bad],
            live_data["participants"],
            live_data["sites"],
        )
        assert result["valid"] is False
        assert any("p_ghost" in e.lower() or "unknown" in e.lower() for e in result["errors"])

    def test_unknown_site_id_is_invalid(self, live_data: dict) -> None:
        bad = _make_observation(observation_id="OBS-NEW2", patient_id="P001", site_id="S_GHOST")
        result = validate_observations(
            live_data["observations"] + [bad],
            live_data["participants"],
            live_data["sites"],
        )
        assert result["valid"] is False
        assert any("s_ghost" in e.lower() or "unknown" in e.lower() for e in result["errors"])

    def test_duplicate_observation_id_is_invalid(self, live_data: dict) -> None:
        dup = _make_observation(observation_id=live_data["observations"][0].observation_id)
        result = validate_observations(
            live_data["observations"] + [dup],
            live_data["participants"],
            live_data["sites"],
        )
        assert result["valid"] is False
        assert any("duplicate" in e.lower() for e in result["errors"])

    def test_actual_day_none_is_warning_not_error(self, live_data: dict) -> None:
        """A missing actual_day is a non-fatal warning — the dataset is still valid."""
        null_obs = _make_observation(
            observation_id="OBS-NULL",
            patient_id="P001",
            site_id="S001",
            visit_type="WEEK_12",
            expected_day=84,
            actual_day=None,
        )
        result = validate_observations(
            [null_obs],
            live_data["participants"],
            live_data["sites"],
        )
        assert result["valid"] is True, "actual_day=None must not make the dataset invalid"
        assert result["errors"] == []
        assert len(result["warnings"]) == 1
        assert "actual_day" in result["warnings"][0].lower() or "not yet recorded" in result["warnings"][0].lower()

    def test_out_of_window_observation_is_NOT_flagged_as_error(self, live_data: dict) -> None:
        """
        Member 1's validator checks DATA QUALITY only.
        An observation where actual_day is far outside the visit window
        is structurally valid data — it must pass validation here.
        Deviation detection belongs to Member 2's module, not this validator.
        """
        # actual_day=200 is clearly outside any ±3 window,
        # but that is Member 2's problem to detect — not Member 1's.
        out_of_window = _make_observation(
            observation_id="OBS-FAR",
            patient_id="P001",
            site_id="S001",
            visit_type="WEEK_4",
            expected_day=28,
            actual_day=200,   # far outside ±3 window — still structurally valid
        )
        result = validate_observations(
            [out_of_window],
            live_data["participants"],
            live_data["sites"],
        )
        assert result["valid"] is True, (
            "Validator must NOT flag out-of-window observations — "
            "that is deviation detection logic belonging to Member 2."
        )
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Tests — validate_protocol_rules()
# ---------------------------------------------------------------------------

class TestValidateProtocolRules:

    def test_valid_rules_pass(self, live_data: dict) -> None:
        assert validate_protocol_rules(live_data["protocol_rules"])["valid"] is True

    def test_empty_list_is_invalid(self) -> None:
        result = validate_protocol_rules([])
        assert result["valid"] is False

    def test_duplicate_rule_id_is_invalid(self, live_data: dict) -> None:
        dup = _make_rule(rule_id=live_data["protocol_rules"][0].rule_id)
        result = validate_protocol_rules(live_data["protocol_rules"] + [dup])
        assert result["valid"] is False
        assert any("duplicate" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# Tests — trial_id validation on sites
# ---------------------------------------------------------------------------

class TestValidateSitesTrialId:

    def test_blank_trial_id_is_invalid(self, live_data: dict) -> None:
        # Bypass Pydantic's min_length=1 constraint via model_construct so we
        # can inject a whitespace-only trial_id and verify the validator catches it.
        bad_site = Site.model_construct(
            site_id="SNEW", trial_id="  ",
            site_name="Test", country="India", status="ACTIVE",
        )
        result = validate_sites(live_data["sites"] + [bad_site])
        assert result["valid"] is False
        assert any("trial_id" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# Tests — trial_id validation on participants
# ---------------------------------------------------------------------------

class TestValidateParticipantsTrialId:

    def test_blank_trial_id_is_invalid(self, live_data: dict) -> None:
        bad = Participant.model_construct(
            patient_id="P_NEW_BLANK", trial_id="  ", site_id="S001",
            age=30, gender="MALE",
            enrollment_date=date(2023, 1, 1), status="ENROLLED",
        )
        result = validate_participants(live_data["participants"] + [bad], live_data["sites"])
        assert result["valid"] is False
        assert any("trial_id" in e.lower() for e in result["errors"])

    def test_participant_age_outside_protocol_eligibility_is_valid_data(
        self, live_data: dict
    ) -> None:
        """
        A participant aged 80 violates the protocol eligibility rule (age <= 75),
        but the validator must NOT flag it as invalid.  It is structurally valid
        data.  Only Member 2's deviation detector should flag it.
        """
        over_age = _make_participant(patient_id="P_OVER_AGE", age=80)
        result = validate_participants(live_data["participants"] + [over_age], live_data["sites"])
        assert result["valid"] is True, (
            "Participant with age=80 should be structurally valid — "
            "eligibility checks belong to Member 2's deviation detector."
        )
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Tests — trial_id validation on observations
# ---------------------------------------------------------------------------

class TestValidateObservationsTrialId:

    def test_blank_trial_id_is_invalid(self, live_data: dict) -> None:
        bad = Observation.model_construct(
            observation_id="OBS-BLANK-TRIAL", trial_id="  ",
            patient_id="P001", site_id="S001",
            visit_type="BASELINE", expected_day=0, actual_day=0,
        )
        result = validate_observations(
            live_data["observations"] + [bad],
            live_data["participants"],
            live_data["sites"],
        )
        assert result["valid"] is False
        assert any("trial_id" in e.lower() for e in result["errors"])

    def test_lab_value_without_unit_is_warning(self, live_data: dict) -> None:
        """An observation with lab_value set but no lab_unit should produce a warning."""
        no_unit = _make_observation(
            observation_id="OBS-NO-UNIT",
            patient_id="P001",
            site_id="S001",
            visit_type="BASELINE",
            expected_day=0,
            actual_day=0,
            lab_value=14.5,
            lab_unit=None,
        )
        result = validate_observations(
            [no_unit],
            live_data["participants"],
            live_data["sites"],
        )
        assert result["valid"] is True, "Missing lab_unit should be a warning, not an error"
        assert len(result["warnings"]) >= 1
        assert any("lab_unit" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# Tests — protocol rule semantic checks (LAB_RANGE, ELIGIBILITY)
# ---------------------------------------------------------------------------

class TestValidateProtocolRuleSemantics:

    def test_lab_range_rule_with_min_max_passes_cleanly(self) -> None:
        """A LAB_RANGE rule with min_value and max_value must pass without warnings."""
        rule = _make_rule(
            rule_id="RULE-TEST-LAB",
            rule_type="LAB_RANGE",
            description="Haemoglobin must be within range.",
            field="lab_value",
            operator="range",
            min_value=12.0,
            max_value=17.5,
            unit="g/dL",
        )
        result = validate_protocol_rules([rule])
        assert result["valid"] is True
        assert result["warnings"] == []

    def test_lab_range_rule_without_min_max_gives_warning(self) -> None:
        """A LAB_RANGE rule missing min_value or max_value should produce a warning."""
        rule = _make_rule(
            rule_id="RULE-TEST-LAB-OLD",
            rule_type="LAB_RANGE",
            description="Haemoglobin must be within normal range.",
        )
        result = validate_protocol_rules([rule])
        assert result["valid"] is True, "Missing min/max is a warning, not an error"
        assert len(result["warnings"]) >= 1
        assert any("min_value" in w.lower() or "max_value" in w.lower()
                   for w in result["warnings"])

    def test_eligibility_rule_with_operator_and_field_passes_cleanly(self) -> None:
        """An ELIGIBILITY rule with operator and field must pass without warnings."""
        rule = _make_rule(
            rule_id="RULE-TEST-ELIG",
            rule_type="ELIGIBILITY",
            description="Patient must be at least 18.",
            field="age",
            operator=">=",
            expected_value="18",
            min_value=18.0,
        )
        result = validate_protocol_rules([rule])
        assert result["valid"] is True
        assert result["warnings"] == []

    def test_eligibility_rule_without_operator_gives_warning(self) -> None:
        """An ELIGIBILITY rule missing operator or field should produce a warning."""
        rule = _make_rule(
            rule_id="RULE-TEST-ELIG-OLD",
            rule_type="ELIGIBILITY",
            description="Patient must be at least 18 years old at enrollment.",
            expected_value="18",
        )
        result = validate_protocol_rules([rule])
        assert result["valid"] is True, "Missing operator is a warning, not an error"
        assert len(result["warnings"]) >= 1
        assert any("operator" in w.lower() or "field" in w.lower()
                   for w in result["warnings"])

    def test_live_rules_produce_no_warnings(self, live_data: dict) -> None:
        """The generated protocol_rules.json must pass validation with no warnings."""
        result = validate_protocol_rules(live_data["protocol_rules"])
        assert result["valid"] is True
        assert result["warnings"] == [], (
            f"Unexpected warnings from live rules: {result['warnings']}"
        )
