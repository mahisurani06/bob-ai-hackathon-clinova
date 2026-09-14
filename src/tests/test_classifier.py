"""
test_classifier.py — Tests for src/deviation/classifier.py

Verifies:
- Overshoot <= ADMIN_MAX_OVERSHOOT → Administrative
- ADMIN_MAX_OVERSHOOT < overshoot <= MINOR_MAX_OVERSHOOT → Minor
- Overshoot > MINOR_MAX_OVERSHOOT → Major
- Exact boundary values are classified correctly
- classify_severity reads from the DeviationRecord itself (not separate args)
- Threshold constants are accessible and correctly ordered
"""

import pytest

from src.deviation.classifier import (
    ADMIN_MAX_OVERSHOOT,
    MINOR_MAX_OVERSHOOT,
    classify_severity,
)
from src.deviation.models import DeviationRecord


# ---------------------------------------------------------------------------
# Helper factory — build a DeviationRecord with a given difference + window
# ---------------------------------------------------------------------------

def _record(
    difference: int,
    allowed_window: int,
    observation_id: str = "OBS-0001",
    patient_id: str = "P001",
    site_id: str = "S001",
    visit_type: str = "WEEK_4",
) -> DeviationRecord:
    """Build a DeviationRecord with a specific difference and allowed_window.

    The ``actual`` day is set to ``expected + difference`` for simplicity.
    ``severity`` is set to a placeholder ("Administrative") because
    classify_severity() will compute and return the real level.
    """
    expected = 28
    actual   = expected + difference   # shift actual by difference days

    return DeviationRecord(
        observation_id=observation_id,
        patient_id=patient_id,
        site_id=site_id,
        visit_type=visit_type,
        deviation_type="VISIT_WINDOW",
        expected=expected,
        actual=actual,
        difference=difference,
        allowed_window=allowed_window,
        severity="Administrative",   # placeholder — replaced by classify_severity
        status="OPEN",
    )


# ---------------------------------------------------------------------------
# Tests — threshold constants
# ---------------------------------------------------------------------------

class TestThresholdConstants:
    """The threshold constants must exist and be logically ordered."""

    def test_admin_max_overshoot_is_positive_int(self) -> None:
        assert isinstance(ADMIN_MAX_OVERSHOOT, int)
        assert ADMIN_MAX_OVERSHOOT > 0

    def test_minor_max_overshoot_is_positive_int(self) -> None:
        assert isinstance(MINOR_MAX_OVERSHOOT, int)
        assert MINOR_MAX_OVERSHOOT > 0

    def test_admin_threshold_less_than_minor_threshold(self) -> None:
        """Admin must be a smaller overshoot than Minor, which is smaller than Major."""
        assert ADMIN_MAX_OVERSHOOT < MINOR_MAX_OVERSHOOT


# ---------------------------------------------------------------------------
# Tests — Administrative severity
# ---------------------------------------------------------------------------

class TestAdministrativeSeverity:
    """Small overshoots must be classified as Administrative."""

    def test_overshoot_of_one_is_administrative(self) -> None:
        """Minimum possible overshoot (1 day over) → Administrative."""
        # window=3, difference=4 → overshoot = 4-3 = 1
        rec = _record(difference=4, allowed_window=3)
        assert classify_severity(rec) == "Administrative"

    def test_overshoot_exactly_at_admin_boundary(self) -> None:
        """overshoot == ADMIN_MAX_OVERSHOOT → still Administrative (boundary inclusive)."""
        difference = 3 + ADMIN_MAX_OVERSHOOT   # overshoot = ADMIN_MAX_OVERSHOOT exactly
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) == "Administrative"

    def test_zero_window_small_overshoot(self) -> None:
        """Window of 0 means any deviation exists; small difference → Administrative."""
        # window=0, difference=2 → overshoot=2; if 2 <= ADMIN_MAX_OVERSHOOT → Admin
        if ADMIN_MAX_OVERSHOOT >= 2:
            rec = _record(difference=2, allowed_window=0)
            assert classify_severity(rec) == "Administrative"


# ---------------------------------------------------------------------------
# Tests — Minor severity
# ---------------------------------------------------------------------------

class TestMinorSeverity:
    """Moderate overshoots must be classified as Minor."""

    def test_one_over_admin_boundary_is_minor(self) -> None:
        """overshoot = ADMIN_MAX_OVERSHOOT + 1 → Minor."""
        overshoot  = ADMIN_MAX_OVERSHOOT + 1
        difference = 3 + overshoot   # window=3
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) == "Minor"

    def test_overshoot_exactly_at_minor_boundary(self) -> None:
        """overshoot == MINOR_MAX_OVERSHOOT → still Minor (boundary inclusive)."""
        difference = 3 + MINOR_MAX_OVERSHOOT   # overshoot = MINOR_MAX_OVERSHOOT exactly
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) == "Minor"

    def test_midpoint_between_admin_and_minor_is_minor(self) -> None:
        """A value strictly between the two thresholds → Minor."""
        midpoint   = ADMIN_MAX_OVERSHOOT + 1
        difference = 3 + midpoint
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) == "Minor"


# ---------------------------------------------------------------------------
# Tests — Major severity
# ---------------------------------------------------------------------------

class TestMajorSeverity:
    """Large overshoots must be classified as Major."""

    def test_one_over_minor_boundary_is_major(self) -> None:
        """overshoot = MINOR_MAX_OVERSHOOT + 1 → Major."""
        overshoot  = MINOR_MAX_OVERSHOOT + 1
        difference = 3 + overshoot   # window=3
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) == "Major"

    def test_very_large_overshoot_is_major(self) -> None:
        """A large overshoot (e.g. 30 days past window) → Major."""
        rec = _record(difference=50, allowed_window=3)   # overshoot = 47
        assert classify_severity(rec) == "Major"

    def test_zero_window_large_difference_is_major(self) -> None:
        """Window of 0, large difference → overshoot = difference → Major."""
        overshoot = MINOR_MAX_OVERSHOOT + 5
        rec = _record(difference=overshoot, allowed_window=0)
        assert classify_severity(rec) == "Major"


# ---------------------------------------------------------------------------
# Tests — return type
# ---------------------------------------------------------------------------

class TestReturnType:
    """classify_severity must always return a valid SeverityLevel string."""

    @pytest.mark.parametrize("difference,window", [
        (4,  3),   # small overshoot → Administrative
        (10, 3),   # moderate overshoot → Minor (depends on thresholds)
        (50, 3),   # large overshoot → Major
    ])
    def test_returns_string(self, difference: int, window: int) -> None:
        rec = _record(difference=difference, allowed_window=window)
        result = classify_severity(rec)
        assert isinstance(result, str)

    @pytest.mark.parametrize("difference,window", [
        (4,  3),
        (10, 3),
        (50, 3),
    ])
    def test_returns_valid_severity_level(self, difference: int, window: int) -> None:
        valid = {"Administrative", "Minor", "Major"}
        rec = _record(difference=difference, allowed_window=window)
        assert classify_severity(rec) in valid


# ---------------------------------------------------------------------------
# Tests — boundary consistency
# ---------------------------------------------------------------------------

class TestBoundaryConsistency:
    """Verify that boundaries produce exactly one classification (no gaps/overlaps)."""

    def test_admin_boundary_is_not_minor(self) -> None:
        """The admin upper boundary must NOT be Minor."""
        difference = 3 + ADMIN_MAX_OVERSHOOT
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) != "Minor"
        assert classify_severity(rec) != "Major"

    def test_minor_boundary_is_not_major(self) -> None:
        """The minor upper boundary must NOT be Major."""
        difference = 3 + MINOR_MAX_OVERSHOOT
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) != "Major"
        assert classify_severity(rec) != "Administrative"

    def test_just_above_minor_boundary_is_major(self) -> None:
        difference = 3 + MINOR_MAX_OVERSHOOT + 1
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) == "Major"

    def test_just_above_admin_boundary_is_minor(self) -> None:
        difference = 3 + ADMIN_MAX_OVERSHOOT + 1
        rec = _record(difference=difference, allowed_window=3)
        assert classify_severity(rec) == "Minor"


# ---------------------------------------------------------------------------
# Tests — integration: severity matches thresholds numerically
# ---------------------------------------------------------------------------

class TestSeverityMatchesThresholds:
    """classify_severity output must be consistent with the published constants."""

    def test_all_admin_overshoots_up_to_threshold(self) -> None:
        """Every overshoot from 1 to ADMIN_MAX_OVERSHOOT → Administrative."""
        for overshoot in range(1, ADMIN_MAX_OVERSHOOT + 1):
            rec = _record(difference=3 + overshoot, allowed_window=3)
            assert classify_severity(rec) == "Administrative", (
                f"Expected Administrative for overshoot={overshoot}, got {classify_severity(rec)}"
            )

    def test_all_minor_overshoots_in_range(self) -> None:
        """Every overshoot from ADMIN_MAX_OVERSHOOT+1 to MINOR_MAX_OVERSHOOT → Minor."""
        for overshoot in range(ADMIN_MAX_OVERSHOOT + 1, MINOR_MAX_OVERSHOOT + 1):
            rec = _record(difference=3 + overshoot, allowed_window=3)
            assert classify_severity(rec) == "Minor", (
                f"Expected Minor for overshoot={overshoot}, got {classify_severity(rec)}"
            )

    def test_major_starts_one_above_minor_threshold(self) -> None:
        overshoot = MINOR_MAX_OVERSHOOT + 1
        rec = _record(difference=3 + overshoot, allowed_window=3)
        assert classify_severity(rec) == "Major"


# ---------------------------------------------------------------------------
# New tests — DEVIATION_TYPE_SEVERITY (ELIGIBILITY and MISSING_DATA)
# ---------------------------------------------------------------------------

from src.deviation.classifier import DEVIATION_TYPE_SEVERITY


def _record_with_type(
    deviation_type: str,
    difference: int = 1,
    allowed_window: int = 0,
    observation_id: str = "OBS-T001",
    patient_id: str = "P001",
    site_id: str = "S001",
    visit_type: str = "ENROLLMENT",
) -> DeviationRecord:
    """Build a DeviationRecord with a specific deviation_type for classifier tests."""
    return DeviationRecord(
        observation_id=observation_id,
        patient_id=patient_id,
        site_id=site_id,
        visit_type=visit_type,
        deviation_type=deviation_type,
        expected=18,
        actual=16,
        difference=difference,
        allowed_window=allowed_window,
        severity="Administrative",   # placeholder
        status="OPEN",
    )


class TestDeviationTypeSeverityConstant:
    """The DEVIATION_TYPE_SEVERITY dict must be exported and correctly valued."""

    def test_constant_is_exported(self) -> None:
        assert DEVIATION_TYPE_SEVERITY is not None

    def test_eligibility_maps_to_major(self) -> None:
        assert DEVIATION_TYPE_SEVERITY["ELIGIBILITY"] == "Major"

    def test_missing_data_maps_to_minor(self) -> None:
        assert DEVIATION_TYPE_SEVERITY["MISSING_DATA"] == "Minor"

    def test_visit_window_is_not_in_fixed_map(self) -> None:
        """VISIT_WINDOW uses the overshoot path, not the fixed map."""
        assert "VISIT_WINDOW" not in DEVIATION_TYPE_SEVERITY


class TestEligibilitySeverity:
    """ELIGIBILITY deviations must always be classified as Major."""

    def test_eligibility_is_always_major(self) -> None:
        rec = _record_with_type("ELIGIBILITY", difference=2, allowed_window=0)
        assert classify_severity(rec) == "Major"

    def test_eligibility_major_regardless_of_small_difference(self) -> None:
        """Even a 1-year age gap on ELIGIBILITY → Major."""
        rec = _record_with_type("ELIGIBILITY", difference=1, allowed_window=0)
        assert classify_severity(rec) == "Major"

    def test_eligibility_major_regardless_of_large_difference(self) -> None:
        """A very large age gap on ELIGIBILITY is still Major (not a fourth level)."""
        rec = _record_with_type("ELIGIBILITY", difference=50, allowed_window=0)
        assert classify_severity(rec) == "Major"


class TestMissingDataSeverity:
    """MISSING_DATA deviations must always be classified as Minor."""

    def test_missing_data_is_always_minor(self) -> None:
        rec = _record_with_type(
            "MISSING_DATA",
            difference=1,
            allowed_window=0,
            visit_type="WEEK_4",
        )
        assert classify_severity(rec) == "Minor"

    def test_missing_data_minor_is_independent_of_expected_day(self) -> None:
        """Changing the expected day value does not change MISSING_DATA severity."""
        rec = DeviationRecord(
            observation_id="OBS-M001",
            patient_id="P001",
            site_id="S001",
            visit_type="WEEK_12",
            deviation_type="MISSING_DATA",
            expected=84,
            actual=-1,
            difference=1,
            allowed_window=0,
            severity="Administrative",
            status="OPEN",
        )
        assert classify_severity(rec) == "Minor"


class TestVisitWindowStillUsesOvershoot:
    """VISIT_WINDOW must still use overshoot-based thresholds, unchanged."""

    def test_visit_window_small_overshoot_is_administrative(self) -> None:
        rec = _record(difference=3 + 1, allowed_window=3)   # overshoot = 1
        assert classify_severity(rec) == "Administrative"

    def test_visit_window_medium_overshoot_is_minor(self) -> None:
        rec = _record(difference=3 + ADMIN_MAX_OVERSHOOT + 1, allowed_window=3)
        assert classify_severity(rec) == "Minor"

    def test_visit_window_large_overshoot_is_major(self) -> None:
        rec = _record(difference=3 + MINOR_MAX_OVERSHOOT + 1, allowed_window=3)
        assert classify_severity(rec) == "Major"

    def test_visit_window_deviation_type_explicit(self) -> None:
        """Explicit VISIT_WINDOW deviation_type uses overshoot, not fixed map."""
        rec = DeviationRecord(
            observation_id="OBS-0001",
            patient_id="P001",
            site_id="S001",
            visit_type="WEEK_4",
            deviation_type="VISIT_WINDOW",
            expected=28,
            actual=33,    # 5 days late, window=3 → overshoot=2 → Administrative
            difference=5,
            allowed_window=3,
            severity="Administrative",
            status="OPEN",
        )
        assert classify_severity(rec) == "Administrative"


class TestUnknownDeviationTypeFallback:
    """Unknown deviation types fall back to overshoot-based classification (safe default)."""

    def test_unknown_type_small_overshoot_is_administrative(self) -> None:
        rec = _record_with_type(
            "FUTURE_RULE_TYPE",
            difference=3 + 1,    # overshoot=1 with window=3
            allowed_window=3,
        )
        assert classify_severity(rec) == "Administrative"

    def test_unknown_type_large_overshoot_is_major(self) -> None:
        rec = _record_with_type(
            "FUTURE_RULE_TYPE",
            difference=3 + MINOR_MAX_OVERSHOOT + 5,
            allowed_window=3,
        )
        assert classify_severity(rec) == "Major"
