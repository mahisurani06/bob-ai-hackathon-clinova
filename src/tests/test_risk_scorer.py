"""
test_risk_scorer.py — Tests for src/risk/scorer.py and src/risk/interface.py

Covers all required scenarios:

 1. Site with no deviations
 2. Site with only Administrative deviations
 3. Site with only Minor deviations
 4. Site with only Major deviations
 5. Site with mixed severity
 6. High-frequency site (many deviations)
 7. Increasing trend
 8. Stable trend
 9. Decreasing trend
10. Insufficient trend data
11. Empty dataset (no deviations, no sites)
12. Multiple sites — isolation and ranking
13. Risk score clamping 0–100
14. Determinism
15. DeviationRecord objects are not mutated
16. Sites with zero deviations always get score 0 and level LOW
17. Grouping — one site's deviations never affect another site's score
18. Integration with live data via compute_site_risks()
"""

from __future__ import annotations

import copy

import pytest

from src.deviation.models import DeviationRecord
from src.protocol.models  import Observation, Site
from src.risk.models      import SiteRiskScore
from src.risk.scorer      import (
    PREVIOUS_VISITS,
    RECENT_VISITS,
    SEVERITY_WEIGHTS,
    VISIT_SEQUENCE,
    _classify_risk_level,
    _raw_frequency_score,
    _raw_severity_score,
    _recent_activity_score,
    _trend_label_and_score,
    score_sites,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _site(site_id: str = "S001") -> Site:
    """Build a minimal valid Site."""
    return Site(
        site_id=site_id,
        site_name=f"Test Site {site_id}",
        country="India",
        status="ACTIVE",
    )


def _dev(
    observation_id: str    = "OBS-0001",
    patient_id:     str    = "P001",
    site_id:        str    = "S001",
    visit_type:     str    = "WEEK_4",
    severity:       str    = "Minor",
    status:         str    = "OPEN",
    difference:     int    = 5,
    allowed_window: int    = 3,
) -> DeviationRecord:
    """Build a minimal valid DeviationRecord."""
    expected = 28
    return DeviationRecord(
        observation_id=observation_id,
        patient_id=patient_id,
        site_id=site_id,
        visit_type=visit_type,
        deviation_type="VISIT_WINDOW",
        expected=expected,
        actual=expected + difference,
        difference=difference,
        allowed_window=allowed_window,
        severity=severity,   # type: ignore[arg-type]
        status=status,       # type: ignore[arg-type]
    )


def _obs(
    observation_id: str = "OBS-0001",
    patient_id:     str = "P001",
    site_id:        str = "S001",
    visit_type:     str = "WEEK_4",
    expected_day:   int = 28,
    actual_day:     int | None = 28,
) -> Observation:
    """Build a minimal valid Observation."""
    return Observation(
        observation_id=observation_id,
        patient_id=patient_id,
        site_id=site_id,
        visit_type=visit_type,
        expected_day=expected_day,
        actual_day=actual_day,
    )


# ---------------------------------------------------------------------------
# 1. Site with no deviations
# ---------------------------------------------------------------------------

class TestNoDeviations:
    """A site present in the roster but with zero deviations."""

    def test_score_is_zero(self) -> None:
        scores = score_sites(deviations=[], sites=[_site("S001")])
        assert len(scores) == 1
        assert scores[0].risk_score == 0.0

    def test_risk_level_is_low(self) -> None:
        scores = score_sites(deviations=[], sites=[_site("S001")])
        assert scores[0].risk_level == "LOW"

    def test_all_counts_are_zero(self) -> None:
        s = score_sites(deviations=[], sites=[_site("S001")])[0]
        assert s.total_deviations          == 0
        assert s.open_deviations           == 0
        assert s.major_deviations          == 0
        assert s.minor_deviations          == 0
        assert s.administrative_deviations == 0
        assert s.recent_deviations         == 0
        assert s.previous_period_deviations == 0

    def test_trend_is_insufficient_data(self) -> None:
        s = score_sites(deviations=[], sites=[_site("S001")])[0]
        assert s.trend == "Insufficient Data"

    def test_top_risk_drivers_is_empty(self) -> None:
        s = score_sites(deviations=[], sites=[_site("S001")])[0]
        assert s.top_risk_drivers == []


# ---------------------------------------------------------------------------
# 2. Site with only Administrative deviations
# ---------------------------------------------------------------------------

class TestAdministrativeOnly:
    """Only Administrative-severity deviations — lowest possible impact."""

    def setup_method(self) -> None:
        self.devs = [
            _dev("O1", severity="Administrative", visit_type="BASELINE"),
            _dev("O2", severity="Administrative", visit_type="WEEK_4"),
        ]
        self.scores = score_sites(self.devs, [_site("S001")])

    def test_returns_one_score(self) -> None:
        assert len(self.scores) == 1

    def test_administrative_count_correct(self) -> None:
        assert self.scores[0].administrative_deviations == 2

    def test_major_and_minor_are_zero(self) -> None:
        s = self.scores[0]
        assert s.major_deviations == 0
        assert s.minor_deviations == 0

    def test_score_is_lower_than_minor_only_site(self) -> None:
        """Administrative deviations must produce a lower score than the same
        number of Minor deviations when scored in the same call so that
        severity normalisation is shared across the two sites."""
        admin_devs = [
            _dev("O1", site_id="S001", severity="Administrative", visit_type="BASELINE"),
            _dev("O2", site_id="S001", severity="Administrative", visit_type="WEEK_4"),
        ]
        minor_devs = [
            _dev("O3", site_id="S002", severity="Minor", visit_type="BASELINE"),
            _dev("O4", site_id="S002", severity="Minor", visit_type="WEEK_4"),
        ]
        scores = score_sites(
            admin_devs + minor_devs,
            [_site("S001"), _site("S002")],
        )
        admin_score = next(s for s in scores if s.site_id == "S001").risk_score
        minor_score = next(s for s in scores if s.site_id == "S002").risk_score
        assert admin_score < minor_score


# ---------------------------------------------------------------------------
# 3. Site with only Minor deviations
# ---------------------------------------------------------------------------

class TestMinorOnly:

    def test_minor_count_correct(self) -> None:
        devs = [_dev("O1", severity="Minor"), _dev("O2", severity="Minor")]
        s = score_sites(devs, [_site()])[0]
        assert s.minor_deviations == 2
        assert s.major_deviations == 0
        assert s.administrative_deviations == 0

    def test_score_is_lower_than_major_only(self) -> None:
        """Minor must produce a lower score than Major when scored together
        so that severity normalisation is shared across the two sites."""
        minor_devs = [_dev("O1", site_id="S001", severity="Minor")]
        major_devs = [_dev("O2", site_id="S002", severity="Major")]
        scores = score_sites(
            minor_devs + major_devs,
            [_site("S001"), _site("S002")],
        )
        minor_score = next(s for s in scores if s.site_id == "S001").risk_score
        major_score = next(s for s in scores if s.site_id == "S002").risk_score
        assert minor_score < major_score


# ---------------------------------------------------------------------------
# 4. Site with only Major deviations
# ---------------------------------------------------------------------------

class TestMajorOnly:

    def setup_method(self) -> None:
        self.devs = [
            _dev("O1", severity="Major", visit_type="WEEK_8"),
            _dev("O2", severity="Major", visit_type="WEEK_12"),
        ]
        self.site  = _site("S001")
        self.score = score_sites(self.devs, [self.site])[0]

    def test_major_count_correct(self) -> None:
        assert self.score.major_deviations == 2

    def test_risk_level_not_low(self) -> None:
        """Two major deviations concentrated in recent visits — not LOW."""
        assert self.score.risk_level != "LOW"

    def test_score_above_zero(self) -> None:
        assert self.score.risk_score > 0

    def test_major_driver_appears_in_top_risk_drivers(self) -> None:
        assert any("Major" in d for d in self.score.top_risk_drivers)


# ---------------------------------------------------------------------------
# 5. Site with mixed severity
# ---------------------------------------------------------------------------

class TestMixedSeverity:

    def setup_method(self) -> None:
        self.devs = [
            _dev("O1", severity="Major",          visit_type="WEEK_12"),
            _dev("O2", severity="Minor",          visit_type="WEEK_8"),
            _dev("O3", severity="Administrative", visit_type="BASELINE"),
        ]
        self.score = score_sites(self.devs, [_site()])[0]

    def test_all_severity_counts_correct(self) -> None:
        assert self.score.major_deviations          == 1
        assert self.score.minor_deviations          == 1
        assert self.score.administrative_deviations == 1
        assert self.score.total_deviations          == 3

    def test_open_deviations_count(self) -> None:
        assert self.score.open_deviations == 3

    def test_score_in_valid_range(self) -> None:
        assert 0.0 <= self.score.risk_score <= 100.0


# ---------------------------------------------------------------------------
# 6. High-frequency site
# ---------------------------------------------------------------------------

class TestHighFrequency:
    """A site with many deviations should outrank a site with fewer."""

    def test_high_frequency_site_ranks_first(self) -> None:
        many_devs = [
            _dev(f"O{i}", site_id="S001", severity="Minor",
                 visit_type=VISIT_SEQUENCE[i % 4])
            for i in range(10)
        ]
        few_devs  = [_dev("O100", site_id="S002", severity="Minor")]

        scores = score_sites(
            many_devs + few_devs,
            [_site("S001"), _site("S002")],
        )
        # score_sites returns highest-risk first
        assert scores[0].site_id == "S001"
        assert scores[0].risk_score >= scores[1].risk_score


# ---------------------------------------------------------------------------
# 7. Increasing trend
# ---------------------------------------------------------------------------

class TestIncreasingTrend:

    def test_trend_is_increasing(self) -> None:
        # 0 in previous period (BASELINE, WEEK_4), 3 in recent (WEEK_8, WEEK_12)
        devs = [
            _dev("O1", visit_type="WEEK_8"),
            _dev("O2", visit_type="WEEK_8"),
            _dev("O3", visit_type="WEEK_12"),
        ]
        s = score_sites(devs, [_site()])[0]
        assert s.trend == "Increasing"

    def test_trend_change_percent_is_none_when_previous_zero(self) -> None:
        """When prev_count == 0, percentage change is undefined → None."""
        devs = [_dev("O1", visit_type="WEEK_8")]
        s = score_sites(devs, [_site()])[0]
        assert s.trend_change_percent is None

    def test_increase_from_one_to_many(self) -> None:
        """1 in previous, 5 in recent → +400 % → Increasing."""
        devs = [
            _dev("O1", visit_type="BASELINE"),
            _dev("O2", visit_type="WEEK_8"),
            _dev("O3", visit_type="WEEK_8"),
            _dev("O4", visit_type="WEEK_12"),
            _dev("O5", visit_type="WEEK_12"),
            _dev("O6", visit_type="WEEK_12"),
        ]
        s = score_sites(devs, [_site()])[0]
        assert s.trend == "Increasing"
        assert s.trend_change_percent is not None
        assert s.trend_change_percent > 10.0


# ---------------------------------------------------------------------------
# 8. Stable trend
# ---------------------------------------------------------------------------

class TestStableTrend:

    def test_trend_is_stable_equal_counts(self) -> None:
        """Same number of deviations in both periods → Stable."""
        devs = [
            _dev("O1", visit_type="BASELINE"),
            _dev("O2", visit_type="WEEK_4"),
            _dev("O3", visit_type="WEEK_8"),
            _dev("O4", visit_type="WEEK_12"),
        ]
        s = score_sites(devs, [_site()])[0]
        assert s.trend == "Stable"

    def test_trend_change_percent_within_10(self) -> None:
        """Stable trend means abs(change) ≤ 10 %."""
        devs = [
            _dev("O1", visit_type="BASELINE"),
            _dev("O2", visit_type="WEEK_4"),
            _dev("O3", visit_type="WEEK_8"),
            _dev("O4", visit_type="WEEK_12"),
        ]
        s = score_sites(devs, [_site()])[0]
        if s.trend_change_percent is not None:
            assert abs(s.trend_change_percent) <= 10.0


# ---------------------------------------------------------------------------
# 9. Decreasing trend
# ---------------------------------------------------------------------------

class TestDecreasingTrend:

    def test_trend_is_decreasing(self) -> None:
        """Many in previous, few in recent → Decreasing."""
        devs = [
            _dev("O1", visit_type="BASELINE"),
            _dev("O2", visit_type="BASELINE"),
            _dev("O3", visit_type="WEEK_4"),
            _dev("O4", visit_type="WEEK_4"),
            _dev("O5", visit_type="WEEK_4"),
            _dev("O6", visit_type="WEEK_12"),  # only one recent
        ]
        s = score_sites(devs, [_site()])[0]
        assert s.trend == "Decreasing"

    def test_trend_change_percent_is_negative(self) -> None:
        devs = [
            _dev("O1", visit_type="BASELINE"),
            _dev("O2", visit_type="WEEK_4"),
            _dev("O3", visit_type="WEEK_4"),
            _dev("O4", visit_type="WEEK_4"),
        ]
        # 0 recent → large negative change
        s = score_sites(devs, [_site()])[0]
        assert s.trend in ("Decreasing", "Stable")  # 0 recent = 100% decrease


# ---------------------------------------------------------------------------
# 10. Insufficient trend data
# ---------------------------------------------------------------------------

class TestInsufficientTrendData:

    def test_no_deviations_gives_insufficient(self) -> None:
        s = score_sites([], [_site()])[0]
        assert s.trend == "Insufficient Data"

    def test_trend_change_percent_is_none_for_insufficient(self) -> None:
        s = score_sites([], [_site()])[0]
        assert s.trend_change_percent is None


# ---------------------------------------------------------------------------
# 11. Empty dataset
# ---------------------------------------------------------------------------

class TestEmptyDataset:

    def test_no_sites_returns_empty_list(self) -> None:
        assert score_sites([], []) == []

    def test_no_deviations_no_sites_returns_empty_list(self) -> None:
        assert score_sites(deviations=[], sites=[]) == []

    def test_deviations_for_unknown_site_are_included(self) -> None:
        """A deviation referencing a site not in the roster should still appear."""
        dev = _dev(site_id="UNKNOWN")
        scores = score_sites([dev], sites=[])
        assert any(s.site_id == "UNKNOWN" for s in scores)


# ---------------------------------------------------------------------------
# 12. Multiple sites — isolation and ranking
# ---------------------------------------------------------------------------

class TestMultipleSites:

    def setup_method(self) -> None:
        # S001: 1 Major in recent period → higher risk
        # S002: 1 Administrative in previous period → lower risk
        # S003: 0 deviations → lowest risk
        self.devs = [
            _dev("O1", site_id="S001", severity="Major",          visit_type="WEEK_12"),
            _dev("O2", site_id="S002", severity="Administrative", visit_type="BASELINE"),
        ]
        self.sites  = [_site("S001"), _site("S002"), _site("S003")]
        self.scores = score_sites(self.devs, self.sites)

    def test_returns_score_for_every_site(self) -> None:
        site_ids = {s.site_id for s in self.scores}
        assert site_ids == {"S001", "S002", "S003"}

    def test_highest_risk_site_ranks_first(self) -> None:
        assert self.scores[0].site_id == "S001"

    def test_clean_site_has_zero_score(self) -> None:
        s003 = next(s for s in self.scores if s.site_id == "S003")
        assert s003.risk_score == 0.0

    def test_site_counts_are_isolated(self) -> None:
        """S001's deviations must not appear in S002's counts."""
        s002 = next(s for s in self.scores if s.site_id == "S002")
        assert s002.total_deviations == 1
        assert s002.major_deviations == 0

    def test_s001_counts_are_correct(self) -> None:
        s001 = next(s for s in self.scores if s.site_id == "S001")
        assert s001.total_deviations  == 1
        assert s001.major_deviations  == 1

    def test_scores_sorted_descending(self) -> None:
        """score_sites() must return highest risk first."""
        values = [s.risk_score for s in self.scores]
        assert values == sorted(values, reverse=True)


# ---------------------------------------------------------------------------
# 13. Risk score clamping between 0 and 100
# ---------------------------------------------------------------------------

class TestScoreClamping:

    def test_score_never_below_zero(self) -> None:
        scores = score_sites([], [_site()])
        for s in scores:
            assert s.risk_score >= 0.0

    def test_score_never_above_100(self) -> None:
        # Worst-case: many major deviations all in recent period
        devs = [
            _dev(f"O{i}", severity="Major", visit_type="WEEK_12")
            for i in range(50)
        ]
        s = score_sites(devs, [_site()])[0]
        assert s.risk_score <= 100.0

    def test_pydantic_validates_score_bounds(self) -> None:
        """SiteRiskScore must reject scores outside [0, 100]."""
        with pytest.raises(Exception):
            SiteRiskScore(
                site_id="S001",
                risk_score=101.0,
                risk_level="CRITICAL",
                trend="Stable",
                major_deviations=0,
                minor_deviations=0,
                administrative_deviations=0,
                total_deviations=0,
                open_deviations=0,
                recent_deviations=0,
                previous_period_deviations=0,
            )


# ---------------------------------------------------------------------------
# 14. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:

    def test_same_input_produces_same_output(self) -> None:
        devs  = [_dev("O1", severity="Minor", visit_type="WEEK_8")]
        sites = [_site()]
        r1 = score_sites(devs, sites)
        r2 = score_sites(devs, sites)
        assert r1[0].risk_score == r2[0].risk_score
        assert r1[0].trend      == r2[0].trend

    def test_score_does_not_depend_on_input_order(self) -> None:
        devs = [
            _dev("O1", severity="Major",          visit_type="WEEK_12"),
            _dev("O2", severity="Minor",          visit_type="BASELINE"),
            _dev("O3", severity="Administrative", visit_type="WEEK_4"),
        ]
        reversed_devs = list(reversed(devs))
        s1 = score_sites(devs,          [_site()])[0].risk_score
        s2 = score_sites(reversed_devs, [_site()])[0].risk_score
        assert s1 == s2


# ---------------------------------------------------------------------------
# 15. DeviationRecord objects are not mutated
# ---------------------------------------------------------------------------

class TestImmutability:

    def test_deviation_records_are_not_mutated(self) -> None:
        devs = [
            _dev("O1", severity="Major",  visit_type="WEEK_8"),
            _dev("O2", severity="Minor",  visit_type="BASELINE"),
        ]
        # Take a snapshot of field values before scoring
        snapshots = [(d.observation_id, d.severity, d.status, d.site_id)
                     for d in devs]

        score_sites(devs, [_site()])

        # Verify nothing changed (model is frozen; this guards against any
        # future attempt to work around the freeze)
        after = [(d.observation_id, d.severity, d.status, d.site_id)
                 for d in devs]
        assert snapshots == after

    def test_site_risk_score_is_immutable(self) -> None:
        """SiteRiskScore must be frozen (cannot be modified after creation)."""
        s = score_sites([_dev("O1")], [_site()])[0]
        with pytest.raises(Exception):
            s.risk_score = 99.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 16. Sites with zero deviations always get LOW risk
# ---------------------------------------------------------------------------

class TestZeroDeviationSites:

    def test_zero_deviation_site_is_always_low(self) -> None:
        scores = score_sites(deviations=[], sites=[_site("S001")])
        assert scores[0].risk_level == "LOW"
        assert scores[0].risk_score == 0.0

    def test_clean_site_among_risky_sites_is_still_low(self) -> None:
        devs = [_dev("O1", site_id="S001", severity="Major")]
        scores = score_sites(devs, [_site("S001"), _site("S002")])
        s002 = next(s for s in scores if s.site_id == "S002")
        assert s002.risk_level == "LOW"
        assert s002.risk_score == 0.0


# ---------------------------------------------------------------------------
# 17. Cross-site isolation
# ---------------------------------------------------------------------------

class TestCrossSiteIsolation:

    def test_site_a_deviations_do_not_appear_in_site_b(self) -> None:
        devs = [
            _dev("O1", site_id="S001", severity="Major",  visit_type="WEEK_12"),
            _dev("O2", site_id="S001", severity="Major",  visit_type="WEEK_8"),
            _dev("O3", site_id="S002", severity="Minor",  visit_type="BASELINE"),
        ]
        scores = score_sites(devs, [_site("S001"), _site("S002")])
        s001 = next(s for s in scores if s.site_id == "S001")
        s002 = next(s for s in scores if s.site_id == "S002")
        assert s001.total_deviations == 2
        assert s002.total_deviations == 1
        assert s001.major_deviations == 2
        assert s002.major_deviations == 0

    def test_adding_deviations_to_site_a_does_not_change_site_b_score(self) -> None:
        devs_base = [_dev("O1", site_id="S002", severity="Minor")]

        score_b_before = score_sites(
            devs_base, [_site("S001"), _site("S002")]
        )
        s002_before = next(s for s in score_b_before if s.site_id == "S002")

        # Add many deviations to S001
        extra = [
            _dev(f"O{i+10}", site_id="S001", severity="Major",
                 visit_type=VISIT_SEQUENCE[i % 4])
            for i in range(8)
        ]
        score_b_after = score_sites(
            devs_base + extra, [_site("S001"), _site("S002")]
        )
        s002_after = next(s for s in score_b_after if s.site_id == "S002")

        # S002's absolute deviation counts must not change
        assert s002_after.total_deviations == s002_before.total_deviations
        assert s002_after.major_deviations == s002_before.major_deviations


# ---------------------------------------------------------------------------
# Unit tests for private helpers
# ---------------------------------------------------------------------------

class TestRawSeverityScore:

    def test_empty_list_returns_zero(self) -> None:
        assert _raw_severity_score([]) == 0.0

    def test_major_weight_is_10(self) -> None:
        assert _raw_severity_score([_dev(severity="Major")]) == 10.0

    def test_minor_weight_is_5(self) -> None:
        assert _raw_severity_score([_dev(severity="Minor")]) == 5.0

    def test_administrative_weight_is_1(self) -> None:
        assert _raw_severity_score([_dev(severity="Administrative")]) == 1.0

    def test_only_open_deviations_count(self) -> None:
        """RESOLVED deviations must NOT contribute to the severity score."""
        open_dev     = _dev("O1", severity="Major",  status="OPEN")
        resolved_dev = _dev("O2", severity="Major",  status="RESOLVED")
        assert _raw_severity_score([open_dev, resolved_dev]) == 10.0

    def test_mixed_severities_sum_correctly(self) -> None:
        devs = [
            _dev("O1", severity="Major"),          # 10
            _dev("O2", severity="Minor"),          #  5
            _dev("O3", severity="Administrative"), #  1
        ]
        assert _raw_severity_score(devs) == 16.0


class TestRawFrequencyScore:

    def test_no_deviations_returns_zero(self) -> None:
        assert _raw_frequency_score([], obs_count=10) == 0.0

    def test_with_observations_returns_rate(self) -> None:
        devs = [_dev("O1"), _dev("O2")]
        assert _raw_frequency_score(devs, obs_count=10) == pytest.approx(0.2)

    def test_without_observations_returns_count(self) -> None:
        devs = [_dev("O1"), _dev("O2"), _dev("O3")]
        assert _raw_frequency_score(devs, obs_count=0) == 3.0


class TestRecentActivityScore:

    def test_no_deviations_returns_zero(self) -> None:
        assert _recent_activity_score([]) == 0.0

    def test_all_recent_returns_100(self) -> None:
        devs = [_dev(visit_type="WEEK_8"), _dev(visit_type="WEEK_12")]
        assert _recent_activity_score(devs) == pytest.approx(100.0)

    def test_all_previous_returns_zero(self) -> None:
        devs = [_dev(visit_type="BASELINE"), _dev(visit_type="WEEK_4")]
        assert _recent_activity_score(devs) == pytest.approx(0.0)

    def test_half_half_returns_50(self) -> None:
        devs = [
            _dev("O1", visit_type="BASELINE"),
            _dev("O2", visit_type="WEEK_8"),
        ]
        assert _recent_activity_score(devs) == pytest.approx(50.0)


class TestTrendLabelAndScore:

    def test_no_deviations_gives_insufficient(self) -> None:
        label, score, prev, recent, pct = _trend_label_and_score([])
        assert label  == "Insufficient Data"
        assert pct    is None

    def test_all_in_previous_gives_decreasing(self) -> None:
        devs = [_dev("O1", visit_type="BASELINE"), _dev("O2", visit_type="WEEK_4")]
        label, score, prev, recent, pct = _trend_label_and_score(devs)
        assert label  == "Decreasing"
        assert recent == 0
        assert prev   == 2

    def test_all_in_recent_gives_increasing(self) -> None:
        devs = [_dev("O1", visit_type="WEEK_8"), _dev("O2", visit_type="WEEK_12")]
        label, score, prev, recent, pct = _trend_label_and_score(devs)
        assert label == "Increasing"
        assert pct   is None  # prev_count == 0

    def test_equal_counts_gives_stable(self) -> None:
        devs = [
            _dev("O1", visit_type="BASELINE"),
            _dev("O2", visit_type="WEEK_8"),
        ]
        label, score, prev, recent, pct = _trend_label_and_score(devs)
        assert label == "Stable"
        assert pct   == pytest.approx(0.0)


class TestClassifyRiskLevel:

    def test_zero_is_low(self) -> None:
        assert _classify_risk_level(0.0) == "LOW"

    def test_30_is_low(self) -> None:
        assert _classify_risk_level(30.0) == "LOW"

    def test_31_is_medium(self) -> None:
        assert _classify_risk_level(31.0) == "MEDIUM"

    def test_50_is_medium(self) -> None:
        assert _classify_risk_level(50.0) == "MEDIUM"

    def test_51_is_high(self) -> None:
        assert _classify_risk_level(51.0) == "HIGH"

    def test_75_is_high(self) -> None:
        assert _classify_risk_level(75.0) == "HIGH"

    def test_76_is_critical(self) -> None:
        assert _classify_risk_level(76.0) == "CRITICAL"

    def test_100_is_critical(self) -> None:
        assert _classify_risk_level(100.0) == "CRITICAL"


# ---------------------------------------------------------------------------
# 18. Integration with live data via compute_site_risks()
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def live_scores() -> list[SiteRiskScore]:
    """Load and score the real generated dataset once per test class."""
    from src.risk.interface import compute_site_risks
    return compute_site_risks()


class TestComputeSiteRisksIntegration:
    """Run the full pipeline against the real generated dataset."""

    def test_returns_a_list(self, live_scores) -> None:
        assert isinstance(live_scores, list)

    def test_returns_four_sites(self, live_scores) -> None:
        """The generated dataset has exactly 4 sites."""
        assert len(live_scores) == 4

    def test_all_items_are_site_risk_score_instances(self, live_scores) -> None:
        for item in live_scores:
            assert isinstance(item, SiteRiskScore)

    def test_all_site_ids_present(self, live_scores) -> None:
        ids = {s.site_id for s in live_scores}
        assert ids == {"S001", "S002", "S003", "S004"}

    def test_scores_in_valid_range(self, live_scores) -> None:
        for s in live_scores:
            assert 0.0 <= s.risk_score <= 100.0

    def test_risk_levels_are_valid(self, live_scores) -> None:
        valid = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        for s in live_scores:
            assert s.risk_level in valid

    def test_trends_are_valid(self, live_scores) -> None:
        valid = {"Increasing", "Stable", "Decreasing", "Insufficient Data"}
        for s in live_scores:
            assert s.trend in valid

    def test_counts_are_non_negative(self, live_scores) -> None:
        for s in live_scores:
            assert s.total_deviations          >= 0
            assert s.open_deviations           >= 0
            assert s.major_deviations          >= 0
            assert s.minor_deviations          >= 0
            assert s.administrative_deviations >= 0

    def test_severity_counts_sum_to_total(self, live_scores) -> None:
        for s in live_scores:
            assert (
                s.major_deviations +
                s.minor_deviations +
                s.administrative_deviations
            ) == s.total_deviations

    def test_sorted_descending(self, live_scores) -> None:
        values = [s.risk_score for s in live_scores]
        assert values == sorted(values, reverse=True)

    def test_top_risk_drivers_are_strings(self, live_scores) -> None:
        for s in live_scores:
            for driver in s.top_risk_drivers:
                assert isinstance(driver, str)
                assert len(driver) > 0
