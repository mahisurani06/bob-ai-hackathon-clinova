"""
detector.py — Deviation detection for the Clinical Trial Risk Monitor.

This module compares clinical observations and participant data against the
protocol rules supplied by Member 1's data layer and identifies violations.

Deviation types detected
------------------------
VISIT_WINDOW
    Visit occurred outside its mandated ±window days of the expected day.
    Source: Observation vs. VISIT_WINDOW ProtocolRule.

MISSING_DATA
    A required visit has no recorded actual_day (actual_day is None).
    Source: Observation with actual_day=None where a VISIT_WINDOW rule exists
    for that visit_type.  Previously these were silently skipped.

ELIGIBILITY
    A participant's age violates a minimum or maximum age criterion.
    Source: Participant.age vs. ELIGIBILITY ProtocolRule.expected_value.
    Requires the optional ``participants`` argument.
    Only available rule fields are used (age from Participant, threshold from
    ProtocolRule.expected_value).  No other eligibility criteria are checked
    because no other participant attributes map to existing rules.

Deviation types NOT detected
-----------------------------
DOSING    — no dosing data exists in observations.csv.
LAB_RANGE — no lab measurement columns in observations.csv.
PROHIBITED_MEDICATION — no medication data in any model.

Public API
----------
    from src.protocol.interface import load_project_data
    from src.deviation.detector import detect_deviations

    data       = load_project_data()
    deviations = detect_deviations(
        observations   = data["observations"],
        protocol_rules = data["protocol_rules"],
        participants   = data["participants"],   # optional; enables ELIGIBILITY
    )
    print(f"Found {len(deviations)} deviation(s).")
"""

from __future__ import annotations

from src.protocol.models import Observation, Participant, ProtocolRule

from .classifier import classify_severity
from .models import DeviationRecord


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_deviations(
    observations:   list[Observation],
    protocol_rules: list[ProtocolRule],
    participants:   list[Participant] | None = None,
) -> list[DeviationRecord]:
    """Detect protocol deviations in clinical observations and participant data.

    Runs three detection passes in order:

    1. **VISIT_WINDOW** — observations with an actual_day that falls outside
       the ±allowed_window defined by the matching rule.

    2. **MISSING_DATA** — observations where actual_day is None (visit not
       recorded) and a VISIT_WINDOW rule exists for that visit_type.

    3. **ELIGIBILITY** — participants whose age violates a minimum or maximum
       age criterion (ELIGIBILITY rules with expected_value set).
       Requires ``participants`` to be provided; skipped otherwise.

    Deduplication is guaranteed: each (observation_id, rule_id) pair produces
    at most one DeviationRecord.

    Args:
        observations:   List of :class:`~src.protocol.models.Observation`
                        instances from ``load_project_data()["observations"]``.
        protocol_rules: List of :class:`~src.protocol.models.ProtocolRule`
                        instances from ``load_project_data()["protocol_rules"]``.
        participants:   Optional list of :class:`~src.protocol.models.Participant`
                        instances from ``load_project_data()["participants"]``.
                        Required for ELIGIBILITY detection; ignored when None.

    Returns:
        A list of :class:`~src.deviation.models.DeviationRecord` objects,
        one per confirmed violation.  Empty when everything is compliant.
    """
    deviations: list[DeviationRecord] = []

    # Index VISIT_WINDOW rules once for O(1) lookup per observation.
    window_rules: dict[str, ProtocolRule] = _index_rules_by_visit_type(
        protocol_rules, rule_type="VISIT_WINDOW"
    )

    # ── Pass 1: VISIT_WINDOW ──────────────────────────────────────────────
    for obs in observations:
        if obs.actual_day is None:
            # Handled in Pass 2 (MISSING_DATA).
            continue

        rule = window_rules.get(obs.visit_type)
        if rule is None:
            # No VISIT_WINDOW rule for this visit type — nothing to check.
            continue

        try:
            expected_day = int(rule.expected_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            # Malformed rule expected_value — skip gracefully.
            continue

        window = rule.allowed_window if rule.allowed_window is not None else 0
        difference: int = abs(obs.actual_day - obs.expected_day)

        if difference <= window:
            # Within the allowed window — no deviation.
            continue

        # Determine direction: was the visit early or late?
        direction = "late" if obs.actual_day > obs.expected_day else "early"

        overshoot = difference - window
        reason = (
            f"Visit {difference} day(s) from expected day {expected_day} "
            f"({direction}); allowed window ±{window} day(s), "
            f"overshoot {overshoot} day(s)."
        )

        record = _build_record(
            observation_id=obs.observation_id,
            patient_id=obs.patient_id,
            site_id=obs.site_id,
            visit_type=obs.visit_type,
            deviation_type="VISIT_WINDOW",
            expected=obs.expected_day,
            actual=obs.actual_day,
            difference=difference,
            allowed_window=window,
            rule_id=rule.rule_id,
            direction=direction,
            reason=reason,
        )
        deviations.append(record)

    # ── Pass 2: MISSING_DATA ─────────────────────────────────────────────
    for obs in observations:
        if obs.actual_day is not None:
            # Visit was recorded — no missing data issue.
            continue

        rule = window_rules.get(obs.visit_type)
        if rule is None:
            # No VISIT_WINDOW rule for this visit type — not a protocol
            # requirement, so no deviation is raised.
            continue

        reason = (
            f"Visit '{obs.visit_type}' (expected day {obs.expected_day}) "
            f"has no recorded actual_day — visit not yet captured."
        )

        record = _build_record(
            observation_id=obs.observation_id,
            patient_id=obs.patient_id,
            site_id=obs.site_id,
            visit_type=obs.visit_type,
            deviation_type="MISSING_DATA",
            # For MISSING_DATA, expected = scheduled day, actual = -1 sentinel.
            # difference = 1, allowed_window = 0 so difference > allowed_window
            # is satisfied and the downstream invariant holds.
            expected=obs.expected_day,
            actual=-1,
            difference=1,
            allowed_window=0,
            rule_id=rule.rule_id,
            direction="missing",
            reason=reason,
        )
        deviations.append(record)

    # ── Pass 3: ELIGIBILITY ──────────────────────────────────────────────
    if participants:
        eligibility_rules = _index_eligibility_rules(protocol_rules)
        if eligibility_rules:
            deviations.extend(
                _detect_eligibility(participants, eligibility_rules)
            )

    return deviations


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_record(
    observation_id: str,
    patient_id:     str,
    site_id:        str,
    visit_type:     str,
    deviation_type: str,
    expected:       int,
    actual:         int,
    difference:     int,
    allowed_window: int,
    rule_id:        str | None,
    direction:      str | None,
    reason:         str | None,
) -> DeviationRecord:
    """Construct a DeviationRecord with severity already classified.

    Uses a two-step build because the model is frozen (immutable).  A
    placeholder record is built first so classify_severity() can read
    the structured fields, then the final record is built with the real
    severity value.
    """
    placeholder = DeviationRecord(
        observation_id=observation_id,
        patient_id=patient_id,
        site_id=site_id,
        visit_type=visit_type,
        deviation_type=deviation_type,
        expected=expected,
        actual=actual,
        difference=difference,
        allowed_window=allowed_window,
        severity="Administrative",   # placeholder — overwritten below
        rule_id=rule_id,
        direction=direction,         # type: ignore[arg-type]
        reason=reason,
    )

    severity = classify_severity(placeholder)

    return DeviationRecord(
        observation_id=observation_id,
        patient_id=patient_id,
        site_id=site_id,
        visit_type=visit_type,
        deviation_type=deviation_type,
        expected=expected,
        actual=actual,
        difference=difference,
        allowed_window=allowed_window,
        severity=severity,
        rule_id=rule_id,
        direction=direction,         # type: ignore[arg-type]
        reason=reason,
    )


def _index_rules_by_visit_type(
    protocol_rules: list[ProtocolRule],
    rule_type: str,
) -> dict[str, ProtocolRule]:
    """Return a visit_type → ProtocolRule dict for a specific rule_type.

    Only includes rules that have a non-null visit_type.  When multiple
    rules share the same visit_type and rule_type, the last one wins.
    """
    index: dict[str, ProtocolRule] = {}
    for rule in protocol_rules:
        if rule.rule_type == rule_type and rule.visit_type is not None:
            index[rule.visit_type] = rule
    return index


def _index_eligibility_rules(
    protocol_rules: list[ProtocolRule],
) -> list[ProtocolRule]:
    """Return all ELIGIBILITY rules that have a usable expected_value."""
    rules = []
    for rule in protocol_rules:
        if rule.rule_type == "ELIGIBILITY" and rule.expected_value is not None:
            rules.append(rule)
    return rules


def _detect_eligibility(
    participants:      list[Participant],
    eligibility_rules: list[ProtocolRule],
) -> list[DeviationRecord]:
    """Check each participant's age against every ELIGIBILITY rule.

    Uses the convention:
      - Rules with description containing "at least" or with expected_value
        representing a minimum bound (RULE-005: age >= 18) detect under-age.
      - Rules with description containing "no older" represent a maximum bound
        (RULE-006: age <= 75) and detect over-age.

    Because the ProtocolRule model has no explicit operator field, we infer
    the bound type from the rule description.  This relies on the actual
    text in the generated protocol_rules.json and is clearly documented.

    Limitation: if rule descriptions change, this heuristic will break.
    A more robust solution would require an operator field on ProtocolRule.

    One ELIGIBILITY DeviationRecord per (participant, rule) violation.
    Uses a synthetic observation_id: "ELIGIBILITY-{patient_id}-{rule_id}".
    """
    records: list[DeviationRecord] = []

    for participant in participants:
        for rule in eligibility_rules:
            try:
                threshold = int(rule.expected_value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                # Malformed rule — skip gracefully.
                continue

            age = participant.age
            description_lower = rule.description.lower()

            # Infer bound direction from rule description text.
            is_minimum = "at least" in description_lower or "minimum" in description_lower
            is_maximum = (
                "no older" in description_lower
                or "maximum" in description_lower
                or "no more" in description_lower
            )

            violated = False
            direction_label = ""
            reason_text = ""

            if is_minimum and age < threshold:
                violated = True
                diff = threshold - age
                direction_label = "early"   # participant is younger than minimum
                reason_text = (
                    f"Patient age {age} is below the minimum enrollment age "
                    f"of {threshold} (rule: {rule.description})."
                )
            elif is_maximum and age > threshold:
                violated = True
                diff = age - threshold
                direction_label = "late"    # participant is older than maximum
                reason_text = (
                    f"Patient age {age} exceeds the maximum enrollment age "
                    f"of {threshold} (rule: {rule.description})."
                )

            if not violated:
                continue

            # Synthetic observation_id for this participant/rule pair.
            obs_id = f"ELIGIBILITY-{participant.patient_id}-{rule.rule_id}"

            # difference = age distance from threshold (always >= 1 when violated)
            # allowed_window = 0 (no tolerance on eligibility rules)
            records.append(
                _build_record(
                    observation_id=obs_id,
                    patient_id=participant.patient_id,
                    site_id=participant.site_id,
                    visit_type="ENROLLMENT",
                    deviation_type="ELIGIBILITY",
                    expected=threshold,
                    actual=age,
                    difference=diff,
                    allowed_window=0,
                    rule_id=rule.rule_id,
                    direction=direction_label,  # type: ignore[arg-type]
                    reason=reason_text,
                )
            )

    return records


# ---------------------------------------------------------------------------
# Legacy private helper — kept for backward compatibility with tests
# that import _index_window_rules directly.
# ---------------------------------------------------------------------------

def _index_window_rules(
    protocol_rules: list[ProtocolRule],
) -> dict[str, ProtocolRule]:
    """Build a visit_type → ProtocolRule dict for VISIT_WINDOW rules only.

    Deprecated alias for _index_rules_by_visit_type(rules, "VISIT_WINDOW").
    Retained so existing tests that import this private helper continue to
    work without modification.
    """
    return _index_rules_by_visit_type(protocol_rules, rule_type="VISIT_WINDOW")
