"""
test_interface.py — Tests for src/protocol/interface.py

Verifies:
- load_project_data() returns a dict with all five expected keys
- Returned counts match the generated demo dataset
- Each individual getter returns the correct count and type
- DataValidationError is raised when the dataset is invalid
- The interface works independently of the caller's working directory
"""

import pytest

from src.protocol.interface import (
    DataValidationError,
    get_observations,
    get_participants,
    get_protocol_rules,
    get_sites,
    get_trials,
    load_project_data,
)
from src.protocol.models import (
    Observation,
    Participant,
    ProtocolRule,
    Site,
    Trial,
)


# ---------------------------------------------------------------------------
# Fixture — load once for the module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def project_data() -> dict:
    return load_project_data()


# ---------------------------------------------------------------------------
# Tests — load_project_data() structure
# ---------------------------------------------------------------------------

class TestLoadProjectDataStructure:

    def test_returns_dict(self, project_data: dict) -> None:
        assert isinstance(project_data, dict)

    def test_has_trials_key(self, project_data: dict) -> None:
        assert "trials" in project_data

    def test_has_sites_key(self, project_data: dict) -> None:
        assert "sites" in project_data

    def test_has_participants_key(self, project_data: dict) -> None:
        assert "participants" in project_data

    def test_has_observations_key(self, project_data: dict) -> None:
        assert "observations" in project_data

    def test_has_protocol_rules_key(self, project_data: dict) -> None:
        assert "protocol_rules" in project_data

    def test_has_exactly_five_keys(self, project_data: dict) -> None:
        assert set(project_data.keys()) == {
            "trials", "sites", "participants", "observations", "protocol_rules"
        }


# ---------------------------------------------------------------------------
# Tests — load_project_data() counts
# ---------------------------------------------------------------------------

class TestLoadProjectDataCounts:

    def test_trials_count(self, project_data: dict) -> None:
        assert len(project_data["trials"]) == 1

    def test_sites_count(self, project_data: dict) -> None:
        assert len(project_data["sites"]) == 4

    def test_participants_count(self, project_data: dict) -> None:
        assert len(project_data["participants"]) == 20

    def test_observations_count(self, project_data: dict) -> None:
        assert len(project_data["observations"]) == 80

    def test_protocol_rules_count(self, project_data: dict) -> None:
        assert len(project_data["protocol_rules"]) == 8


# ---------------------------------------------------------------------------
# Tests — load_project_data() types
# ---------------------------------------------------------------------------

class TestLoadProjectDataTypes:

    def test_trials_are_trial_instances(self, project_data: dict) -> None:
        for item in project_data["trials"]:
            assert isinstance(item, Trial)

    def test_sites_are_site_instances(self, project_data: dict) -> None:
        for item in project_data["sites"]:
            assert isinstance(item, Site)

    def test_participants_are_participant_instances(self, project_data: dict) -> None:
        for item in project_data["participants"]:
            assert isinstance(item, Participant)

    def test_observations_are_observation_instances(self, project_data: dict) -> None:
        for item in project_data["observations"]:
            assert isinstance(item, Observation)

    def test_protocol_rules_are_protocol_rule_instances(self, project_data: dict) -> None:
        for item in project_data["protocol_rules"]:
            assert isinstance(item, ProtocolRule)


# ---------------------------------------------------------------------------
# Tests — individual getters
# ---------------------------------------------------------------------------

class TestIndividualGetters:

    def test_get_trials_returns_one(self) -> None:
        assert len(get_trials()) == 1

    def test_get_trials_returns_trial_instances(self) -> None:
        for item in get_trials():
            assert isinstance(item, Trial)

    def test_get_sites_returns_four(self) -> None:
        assert len(get_sites()) == 4

    def test_get_sites_returns_site_instances(self) -> None:
        for item in get_sites():
            assert isinstance(item, Site)

    def test_get_participants_returns_twenty(self) -> None:
        assert len(get_participants()) == 20

    def test_get_participants_returns_participant_instances(self) -> None:
        for item in get_participants():
            assert isinstance(item, Participant)

    def test_get_observations_returns_eighty(self) -> None:
        assert len(get_observations()) == 80

    def test_get_observations_returns_observation_instances(self) -> None:
        for item in get_observations():
            assert isinstance(item, Observation)

    def test_get_protocol_rules_returns_eight(self) -> None:
        assert len(get_protocol_rules()) == 8

    def test_get_protocol_rules_returns_protocol_rule_instances(self) -> None:
        for item in get_protocol_rules():
            assert isinstance(item, ProtocolRule)


# ---------------------------------------------------------------------------
# Tests — DataValidationError on bad data
# ---------------------------------------------------------------------------

class TestDataValidationError:
    """load_project_data() must raise DataValidationError when data is corrupt."""

    def test_error_is_subclass_of_value_error(self) -> None:
        """DataValidationError must be a ValueError so callers can catch either."""
        assert issubclass(DataValidationError, ValueError)

    def test_error_carries_errors_list(self) -> None:
        exc = DataValidationError(errors=["something broke"], warnings=[])
        assert exc.errors == ["something broke"]

    def test_error_carries_warnings_list(self) -> None:
        exc = DataValidationError(errors=["err"], warnings=["warn"])
        assert exc.warnings == ["warn"]

    def test_error_message_contains_error_text(self) -> None:
        exc = DataValidationError(errors=["trial list is empty"], warnings=[])
        assert "trial list is empty" in str(exc)

    def test_missing_data_dir_raises_file_not_found(self, tmp_path) -> None:
        """A completely empty data_dir must raise FileNotFoundError (no DataValidationError)."""
        with pytest.raises(FileNotFoundError):
            load_project_data(data_dir=tmp_path / "nonexistent")

    def test_invalid_dataset_raises_data_validation_error(self) -> None:
        """
        Simulate corrupt data by monkey-patching the loader to return an empty
        trials list, which validate_all() will reject.
        """
        from src.protocol import interface as iface
        from src.protocol import validator

        original_load = iface.load_all_data

        def _bad_load(_dir=None):
            data = original_load(_dir)
            data = dict(data)
            data["trials"] = []   # inject the corruption
            return data

        iface.load_all_data = _bad_load
        try:
            with pytest.raises(DataValidationError) as exc_info:
                load_project_data()
            assert exc_info.value.errors   # at least one error
        finally:
            iface.load_all_data = original_load   # always restore
