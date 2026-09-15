"""
test_loader.py — Tests for src/protocol/loader.py

Verifies:
- Each loader function returns the correct count of objects
- Returned objects are the correct Pydantic model types
- enrollment_date is parsed as datetime.date (not a raw string)
- actual_day=None is handled correctly when the CSV cell is empty
- FileNotFoundError is raised when required files are missing
- load_all_data() returns a dict with all five expected keys
"""

import csv
import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.protocol.loader import (
    load_all_data,
    load_observations,
    load_participants,
    load_protocol_rules,
    load_sites,
    load_trials,
)
from src.protocol.models import (
    Observation,
    Participant,
    ProtocolRule,
    Site,
    Trial,
)


# ---------------------------------------------------------------------------
# Fixtures — use the real generated data in src/data/synthetic/
# ---------------------------------------------------------------------------

# The loader resolves src/data/ relative to its own file location, so
# all tests that omit data_dir use the already-generated synthetic files.


# ---------------------------------------------------------------------------
# Tests — load_trials()
# ---------------------------------------------------------------------------

class TestLoadTrials:

    def test_returns_list(self) -> None:
        result = load_trials()
        assert isinstance(result, list)

    def test_returns_one_trial(self) -> None:
        assert len(load_trials()) == 1

    def test_items_are_trial_instances(self) -> None:
        for item in load_trials():
            assert isinstance(item, Trial)

    def test_trial_id_is_non_empty_string(self) -> None:
        trial = load_trials()[0]
        assert isinstance(trial.trial_id, str)
        assert len(trial.trial_id) > 0

    def test_known_trial_id(self) -> None:
        assert load_trials()[0].trial_id == "TRIAL-001"

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        empty_data_dir = tmp_path / "data"
        (empty_data_dir / "synthetic").mkdir(parents=True)
        with pytest.raises(FileNotFoundError):
            load_trials(data_dir=empty_data_dir)


# ---------------------------------------------------------------------------
# Tests — load_sites()
# ---------------------------------------------------------------------------

class TestLoadSites:

    def test_returns_four_sites(self) -> None:
        assert len(load_sites()) == 4

    def test_items_are_site_instances(self) -> None:
        for item in load_sites():
            assert isinstance(item, Site)

    def test_site_ids_are_non_empty(self) -> None:
        for site in load_sites():
            assert isinstance(site.site_id, str)
            assert len(site.site_id) > 0

    def test_known_site_ids_present(self) -> None:
        ids = {s.site_id for s in load_sites()}
        assert {"S001", "S002", "S003", "S004"}.issubset(ids)


# ---------------------------------------------------------------------------
# Tests — load_participants()
# ---------------------------------------------------------------------------

class TestLoadParticipants:

    def test_returns_twenty_participants(self) -> None:
        assert len(load_participants()) == 20

    def test_items_are_participant_instances(self) -> None:
        for item in load_participants():
            assert isinstance(item, Participant)

    def test_enrollment_date_is_date_object(self) -> None:
        """enrollment_date must be a Python date, not a raw string."""
        for p in load_participants():
            assert isinstance(p.enrollment_date, date), (
                f"Expected date for {p.patient_id}, got {type(p.enrollment_date)}"
            )

    def test_ages_within_valid_range(self) -> None:
        """Pydantic constraint: age must be 0–120 (data-quality bounds)."""
        for p in load_participants():
            assert 0 <= p.age <= 120, f"Age out of range for {p.patient_id}: {p.age}"

    def test_participants_have_trial_id(self) -> None:
        """Every participant must have a non-empty trial_id."""
        for p in load_participants():
            assert isinstance(p.trial_id, str)
            assert len(p.trial_id) > 0

    def test_gender_values_are_valid(self) -> None:
        valid_genders = {"MALE", "FEMALE", "OTHER"}
        for p in load_participants():
            assert p.gender in valid_genders

    def test_status_values_are_valid(self) -> None:
        valid_statuses = {"ENROLLED", "COMPLETED", "WITHDRAWN", "SCREEN_FAIL"}
        for p in load_participants():
            assert p.status in valid_statuses


# ---------------------------------------------------------------------------
# Tests — load_observations()
# ---------------------------------------------------------------------------

class TestLoadObservations:

    def test_returns_eighty_observations(self) -> None:
        assert len(load_observations()) == 80

    def test_items_are_observation_instances(self) -> None:
        for item in load_observations():
            assert isinstance(item, Observation)

    def test_expected_day_is_non_negative_int(self) -> None:
        for obs in load_observations():
            assert isinstance(obs.expected_day, int)
            assert obs.expected_day >= 0

    def test_actual_day_is_int_or_none(self) -> None:
        """actual_day must be an int when present, or None when blank."""
        for obs in load_observations():
            assert obs.actual_day is None or isinstance(obs.actual_day, int)

    def test_actual_day_none_when_csv_cell_is_empty(self, tmp_path: Path) -> None:
        """A blank actual_day cell in the CSV must parse to None."""
        # Build a minimal synthetic directory with one row that has no actual_day
        syn_dir = tmp_path / "data" / "synthetic"
        syn_dir.mkdir(parents=True)

        # Write a minimal trials.csv, sites.csv, participants.csv so the
        # loader can satisfy its other reads too
        (syn_dir / "trials.csv").write_text(
            "trial_id,trial_name,version,status\nTRIAL-001,Test,1.0,ACTIVE\n",
            encoding="utf-8",
        )
        (syn_dir / "sites.csv").write_text(
            "site_id,trial_id,site_name,country,status\n"
            "S001,TRIAL-001,Test Site,India,ACTIVE\n",
            encoding="utf-8",
        )
        (syn_dir / "participants.csv").write_text(
            "patient_id,trial_id,site_id,age,gender,enrollment_date,status\n"
            "P001,TRIAL-001,S001,30,MALE,2023-01-01,ENROLLED\n",
            encoding="utf-8",
        )
        # observation with an empty actual_day cell (and empty optional columns)
        (syn_dir / "observations.csv").write_text(
            "observation_id,trial_id,patient_id,site_id,visit_type,expected_day,"
            "actual_day,dose_mg,lab_value,lab_unit\n"
            "OBS-0001,TRIAL-001,P001,S001,BASELINE,0,,,,\n",
            encoding="utf-8",
        )

        observations = load_observations(data_dir=tmp_path / "data")
        assert len(observations) == 1
        assert observations[0].actual_day is None

    def test_visit_types_are_non_empty(self) -> None:
        for obs in load_observations():
            assert isinstance(obs.visit_type, str)
            assert len(obs.visit_type) > 0

    def test_trial_id_on_observations(self) -> None:
        """Every observation must have a non-empty trial_id."""
        for obs in load_observations():
            assert isinstance(obs.trial_id, str)
            assert len(obs.trial_id) > 0

    def test_dose_mg_is_float_or_none(self) -> None:
        """dose_mg must be a float when present, or None when blank."""
        for obs in load_observations():
            assert obs.dose_mg is None or isinstance(obs.dose_mg, float)

    def test_lab_value_is_float_or_none(self) -> None:
        """lab_value must be a float when present, or None when blank."""
        for obs in load_observations():
            assert obs.lab_value is None or isinstance(obs.lab_value, float)

    def test_week4_observations_have_dose_mg(self) -> None:
        """All WEEK_4 observations must have a dose_mg value (not None)."""
        week4 = [obs for obs in load_observations() if obs.visit_type == "WEEK_4"]
        assert len(week4) > 0
        for obs in week4:
            assert obs.dose_mg is not None, (
                f"WEEK_4 observation {obs.observation_id} has no dose_mg"
            )

    def test_baseline_observations_have_lab_value(self) -> None:
        """All BASELINE observations must have a lab_value (not None)."""
        baselines = [obs for obs in load_observations() if obs.visit_type == "BASELINE"]
        assert len(baselines) > 0
        for obs in baselines:
            assert obs.lab_value is not None, (
                f"BASELINE observation {obs.observation_id} has no lab_value"
            )

    def test_trial_id_on_sites(self) -> None:
        """Every site must have a non-empty trial_id."""
        for site in load_sites():
            assert isinstance(site.trial_id, str)
            assert len(site.trial_id) > 0


# ---------------------------------------------------------------------------
# Tests — load_protocol_rules()
# ---------------------------------------------------------------------------

class TestLoadProtocolRules:

    def test_returns_eight_rules(self) -> None:
        assert len(load_protocol_rules()) == 8

    def test_items_are_protocol_rule_instances(self) -> None:
        for item in load_protocol_rules():
            assert isinstance(item, ProtocolRule)

    def test_rule_types_are_valid(self) -> None:
        valid_types = {"VISIT_WINDOW", "ELIGIBILITY", "DOSING", "LAB_RANGE"}
        for rule in load_protocol_rules():
            assert rule.rule_type in valid_types

    def test_visit_window_rules_have_expected_value_and_window(self) -> None:
        """Every VISIT_WINDOW rule must carry both expected_value and allowed_window."""
        for rule in load_protocol_rules():
            if rule.rule_type == "VISIT_WINDOW":
                assert rule.expected_value is not None, (
                    f"VISIT_WINDOW rule {rule.rule_id} missing expected_value"
                )
                assert rule.allowed_window is not None, (
                    f"VISIT_WINDOW rule {rule.rule_id} missing allowed_window"
                )

    def test_eligibility_rules_have_operator_and_field(self) -> None:
        """ELIGIBILITY rules must carry machine-readable operator and field."""
        for rule in load_protocol_rules():
            if rule.rule_type == "ELIGIBILITY":
                assert rule.operator is not None, (
                    f"ELIGIBILITY rule {rule.rule_id} missing operator"
                )
                assert rule.field is not None, (
                    f"ELIGIBILITY rule {rule.rule_id} missing field"
                )

    def test_eligibility_rule_operators_are_ge_or_le(self) -> None:
        """ELIGIBILITY operators must be '>=' or '<='."""
        for rule in load_protocol_rules():
            if rule.rule_type == "ELIGIBILITY":
                assert rule.operator in (">=", "<="), (
                    f"ELIGIBILITY rule {rule.rule_id} has unexpected operator '{rule.operator}'"
                )

    def test_lab_range_rule_has_min_max_and_unit(self) -> None:
        """LAB_RANGE rules must carry min_value, max_value, and unit."""
        for rule in load_protocol_rules():
            if rule.rule_type == "LAB_RANGE":
                assert rule.min_value is not None, (
                    f"LAB_RANGE rule {rule.rule_id} missing min_value"
                )
                assert rule.max_value is not None, (
                    f"LAB_RANGE rule {rule.rule_id} missing max_value"
                )
                assert rule.unit is not None, (
                    f"LAB_RANGE rule {rule.rule_id} missing unit"
                )

    def test_lab_range_min_less_than_max(self) -> None:
        """LAB_RANGE min_value must be less than max_value."""
        for rule in load_protocol_rules():
            if rule.rule_type == "LAB_RANGE":
                assert rule.min_value < rule.max_value, (  # type: ignore[operator]
                    f"LAB_RANGE rule {rule.rule_id}: min_value {rule.min_value} "
                    f">= max_value {rule.max_value}"
                )

    def test_missing_rules_file_raises_file_not_found(self, tmp_path: Path) -> None:
        empty_data_dir = tmp_path / "data"
        (empty_data_dir / "schemas").mkdir(parents=True)
        with pytest.raises(FileNotFoundError):
            load_protocol_rules(data_dir=empty_data_dir)


# ---------------------------------------------------------------------------
# Tests — load_all_data()
# ---------------------------------------------------------------------------

class TestLoadAllData:

    def test_returns_dict(self) -> None:
        assert isinstance(load_all_data(), dict)

    def test_has_all_five_keys(self) -> None:
        data = load_all_data()
        expected_keys = {"trials", "sites", "participants", "observations", "protocol_rules"}
        assert expected_keys == set(data.keys())

    def test_counts_match(self) -> None:
        data = load_all_data()
        assert len(data["trials"])         == 1
        assert len(data["sites"])          == 4
        assert len(data["participants"])   == 20
        assert len(data["observations"])   == 80
        assert len(data["protocol_rules"]) == 8
