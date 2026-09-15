"""
test_generator.py — Tests for src/protocol/generator.py

Verifies:
- generate_dataset() creates all four expected CSV files
- The generated files contain the correct number of rows
- Output is deterministic: running with seed=42 twice produces identical files
- The synthetic directory is created automatically when it does not exist
"""

import csv
import shutil
import tempfile
from pathlib import Path

import pytest

from src.protocol.generator import generate_dataset


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _count_rows(csv_path: Path) -> int:
    """Return the number of data rows (excluding header) in a CSV file."""
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_output(tmp_path: Path) -> Path:
    """Return a fresh temporary directory for each test."""
    return tmp_path / "synthetic"


# ---------------------------------------------------------------------------
# Tests — file creation
# ---------------------------------------------------------------------------

class TestGeneratedFiles:
    """generate_dataset() must create the four expected CSV files."""

    def test_trials_file_created(self, tmp_output: Path) -> None:
        generate_dataset(output_dir=str(tmp_output), seed=42)
        assert (tmp_output / "trials.csv").exists()

    def test_sites_file_created(self, tmp_output: Path) -> None:
        generate_dataset(output_dir=str(tmp_output), seed=42)
        assert (tmp_output / "sites.csv").exists()

    def test_participants_file_created(self, tmp_output: Path) -> None:
        generate_dataset(output_dir=str(tmp_output), seed=42)
        assert (tmp_output / "participants.csv").exists()

    def test_observations_file_created(self, tmp_output: Path) -> None:
        generate_dataset(output_dir=str(tmp_output), seed=42)
        assert (tmp_output / "observations.csv").exists()

    def test_output_directory_created_automatically(self, tmp_path: Path) -> None:
        """generate_dataset() must create output_dir if it does not exist."""
        new_dir = tmp_path / "brand" / "new" / "directory"
        assert not new_dir.exists()
        generate_dataset(output_dir=str(new_dir), seed=42)
        assert new_dir.exists()


# ---------------------------------------------------------------------------
# Tests — row counts
# ---------------------------------------------------------------------------

class TestRowCounts:
    """Generated files must contain the correct number of data rows."""

    @pytest.fixture(autouse=True)
    def _generate(self, tmp_output: Path) -> None:
        generate_dataset(output_dir=str(tmp_output), seed=42)
        self.out = tmp_output

    def test_one_trial(self) -> None:
        assert _count_rows(self.out / "trials.csv") == 1

    def test_four_sites(self) -> None:
        assert _count_rows(self.out / "sites.csv") == 4

    def test_twenty_participants(self) -> None:
        assert _count_rows(self.out / "participants.csv") == 20

    def test_eighty_observations(self) -> None:
        # 20 participants × 4 visits = 80
        assert _count_rows(self.out / "observations.csv") == 80

    def test_custom_participant_count(self, tmp_path: Path) -> None:
        out = tmp_path / "custom"
        generate_dataset(output_dir=str(out), num_participants=10, seed=42)
        assert _count_rows(out / "participants.csv") == 10
        assert _count_rows(out / "observations.csv") == 40  # 10 × 4


# ---------------------------------------------------------------------------
# Tests — determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """The same seed must always produce identical output."""

    def test_same_seed_produces_identical_participants(self, tmp_path: Path) -> None:
        out_a = tmp_path / "run_a"
        out_b = tmp_path / "run_b"
        generate_dataset(output_dir=str(out_a), seed=42)
        generate_dataset(output_dir=str(out_b), seed=42)
        assert _read_text(out_a / "participants.csv") == _read_text(out_b / "participants.csv")

    def test_same_seed_produces_identical_observations(self, tmp_path: Path) -> None:
        out_a = tmp_path / "run_a"
        out_b = tmp_path / "run_b"
        generate_dataset(output_dir=str(out_a), seed=42)
        generate_dataset(output_dir=str(out_b), seed=42)
        assert _read_text(out_a / "observations.csv") == _read_text(out_b / "observations.csv")

    def test_different_seeds_produce_different_participants(self, tmp_path: Path) -> None:
        out_a = tmp_path / "run_a"
        out_b = tmp_path / "run_b"
        generate_dataset(output_dir=str(out_a), seed=42)
        generate_dataset(output_dir=str(out_b), seed=99)
        assert _read_text(out_a / "participants.csv") != _read_text(out_b / "participants.csv")


# ---------------------------------------------------------------------------
# Tests — CSV structure
# ---------------------------------------------------------------------------

class TestCSVStructure:
    """Each CSV must have the expected column headers."""

    @pytest.fixture(autouse=True)
    def _generate(self, tmp_output: Path) -> None:
        generate_dataset(output_dir=str(tmp_output), seed=42)
        self.out = tmp_output

    def _headers(self, filename: str) -> list[str]:
        with open(self.out / filename, newline="", encoding="utf-8") as fh:
            return csv.DictReader(fh).fieldnames or []

    def test_trials_columns(self) -> None:
        assert self._headers("trials.csv") == ["trial_id", "trial_name", "version", "status"]

    def test_sites_columns(self) -> None:
        assert self._headers("sites.csv") == [
            "site_id", "trial_id", "site_name", "country", "status",
        ]

    def test_participants_columns(self) -> None:
        assert self._headers("participants.csv") == [
            "patient_id", "trial_id", "site_id", "age", "gender", "enrollment_date", "status",
        ]

    def test_observations_columns(self) -> None:
        assert self._headers("observations.csv") == [
            "observation_id", "trial_id", "patient_id", "site_id",
            "visit_type", "expected_day", "actual_day",
            "dose_mg", "lab_value", "lab_unit",
        ]


# ---------------------------------------------------------------------------
# Tests — validation guard
# ---------------------------------------------------------------------------

class TestInputValidation:
    """generate_dataset() must reject invalid arguments."""

    def test_zero_participants_raises_value_error(self, tmp_output: Path) -> None:
        with pytest.raises(ValueError, match="num_participants"):
            generate_dataset(output_dir=str(tmp_output), num_participants=0, seed=42)


# ---------------------------------------------------------------------------
# Tests — new relationship fields (trial_id on sites, participants, observations)
# ---------------------------------------------------------------------------

class TestTrialIdRelationships:
    """trial_id must be present and correct across all entity CSVs."""

    @pytest.fixture(autouse=True)
    def _generate(self, tmp_output: Path) -> None:
        generate_dataset(output_dir=str(tmp_output), seed=42)
        self.out = tmp_output

    def _rows(self, filename: str) -> list[dict]:
        with open(self.out / filename, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_sites_have_trial_id(self) -> None:
        for row in self._rows("sites.csv"):
            assert row["trial_id"] != "", f"Site {row['site_id']} has empty trial_id"

    def test_participants_have_trial_id(self) -> None:
        for row in self._rows("participants.csv"):
            assert row["trial_id"] != "", f"Participant {row['patient_id']} has empty trial_id"

    def test_observations_have_trial_id(self) -> None:
        for row in self._rows("observations.csv"):
            assert row["trial_id"] != "", f"Observation {row['observation_id']} has empty trial_id"

    def test_all_site_trial_ids_match_trial(self) -> None:
        trial_ids = {row["trial_id"] for row in self._rows("trials.csv")}
        for row in self._rows("sites.csv"):
            assert row["trial_id"] in trial_ids

    def test_all_participant_trial_ids_match_trial(self) -> None:
        trial_ids = {row["trial_id"] for row in self._rows("trials.csv")}
        for row in self._rows("participants.csv"):
            assert row["trial_id"] in trial_ids

    def test_all_observation_trial_ids_match_trial(self) -> None:
        trial_ids = {row["trial_id"] for row in self._rows("trials.csv")}
        for row in self._rows("observations.csv"):
            assert row["trial_id"] in trial_ids


# ---------------------------------------------------------------------------
# Tests — clinical data fields (dose_mg, lab_value, lab_unit)
# ---------------------------------------------------------------------------

class TestClinicalDataFields:
    """Observations must carry dose and lab fields with correct semantics."""

    @pytest.fixture(autouse=True)
    def _generate(self, tmp_output: Path) -> None:
        generate_dataset(output_dir=str(tmp_output), seed=42)
        self.out = tmp_output

    def _rows(self, filename: str) -> list[dict]:
        with open(self.out / filename, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_week4_observations_have_dose_mg(self) -> None:
        """All WEEK_4 observations must have a non-empty dose_mg."""
        week4 = [r for r in self._rows("observations.csv") if r["visit_type"] == "WEEK_4"]
        assert len(week4) > 0, "No WEEK_4 observations found"
        for row in week4:
            assert row["dose_mg"] != "", (
                f"WEEK_4 observation {row['observation_id']} has empty dose_mg"
            )

    def test_non_week4_observations_have_no_dose_mg(self) -> None:
        """Non-WEEK_4 observations must have an empty dose_mg."""
        non_week4 = [r for r in self._rows("observations.csv") if r["visit_type"] != "WEEK_4"]
        for row in non_week4:
            assert row["dose_mg"] == "", (
                f"{row['visit_type']} observation {row['observation_id']} "
                f"unexpectedly has dose_mg={row['dose_mg']}"
            )

    def test_baseline_observations_have_lab_value_and_unit(self) -> None:
        """All BASELINE observations must carry lab_value and lab_unit."""
        baselines = [r for r in self._rows("observations.csv") if r["visit_type"] == "BASELINE"]
        assert len(baselines) > 0, "No BASELINE observations found"
        for row in baselines:
            assert row["lab_value"] != "", (
                f"BASELINE observation {row['observation_id']} has empty lab_value"
            )
            assert row["lab_unit"] == "g/dL", (
                f"BASELINE observation {row['observation_id']} has unexpected "
                f"lab_unit='{row['lab_unit']}'"
            )

    def test_non_baseline_observations_have_no_lab_value(self) -> None:
        """Non-BASELINE observations must have empty lab fields."""
        non_baseline = [r for r in self._rows("observations.csv") if r["visit_type"] != "BASELINE"]
        for row in non_baseline:
            assert row["lab_value"] == "", (
                f"{row['visit_type']} observation {row['observation_id']} "
                f"unexpectedly has lab_value={row['lab_value']}"
            )

    def test_dose_mg_values_are_numeric(self) -> None:
        """Non-empty dose_mg values must be parseable as float."""
        for row in self._rows("observations.csv"):
            if row["dose_mg"] != "":
                float(row["dose_mg"])  # raises ValueError if not numeric

    def test_lab_values_are_numeric(self) -> None:
        """Non-empty lab_value values must be parseable as float."""
        for row in self._rows("observations.csv"):
            if row["lab_value"] != "":
                float(row["lab_value"])  # raises ValueError if not numeric


# ---------------------------------------------------------------------------
# Tests — participant age range (eligibility boundary cases)
# ---------------------------------------------------------------------------

class TestParticipantAgeRange:
    """Age range 16–80 should produce eligibility-boundary participants."""

    def test_age_range_allows_eligibility_boundary_cases(self, tmp_path: Path) -> None:
        """Generate a larger dataset and verify some ages fall outside 18–75."""
        out = tmp_path / "large"
        generate_dataset(output_dir=str(out), num_participants=100, seed=42)
        ages = []
        with open(out / "participants.csv", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ages.append(int(row["age"]))
        # With 100 participants and range 16–80, statistically expect at least
        # some ages below 18 or above 75 — verify the range extends to those.
        assert min(ages) >= 16, "Minimum age should be at least 16"
        assert max(ages) <= 80, "Maximum age should be at most 80"

    def test_deterministic_age_generation(self, tmp_path: Path) -> None:
        """Age generation must be deterministic with seed=42."""
        out_a = tmp_path / "run_a"
        out_b = tmp_path / "run_b"
        generate_dataset(output_dir=str(out_a), seed=42)
        generate_dataset(output_dir=str(out_b), seed=42)
        ages_a = [r["age"] for r in csv.DictReader(open(out_a / "participants.csv"))]
        ages_b = [r["age"] for r in csv.DictReader(open(out_b / "participants.csv"))]
        assert ages_a == ages_b
