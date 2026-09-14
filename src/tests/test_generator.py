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
        assert self._headers("sites.csv") == ["site_id", "site_name", "country", "status"]

    def test_participants_columns(self) -> None:
        assert self._headers("participants.csv") == [
            "patient_id", "site_id", "age", "gender", "enrollment_date", "status",
        ]

    def test_observations_columns(self) -> None:
        assert self._headers("observations.csv") == [
            "observation_id", "patient_id", "site_id",
            "visit_type", "expected_day", "actual_day",
        ]


# ---------------------------------------------------------------------------
# Tests — validation guard
# ---------------------------------------------------------------------------

class TestInputValidation:
    """generate_dataset() must reject invalid arguments."""

    def test_zero_participants_raises_value_error(self, tmp_output: Path) -> None:
        with pytest.raises(ValueError, match="num_participants"):
            generate_dataset(output_dir=str(tmp_output), num_participants=0, seed=42)
