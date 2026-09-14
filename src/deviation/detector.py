"""
detector.py — Deviation detection for the Clinical Trial Risk Monitor.

This module compares clinical observations against the protocol rules
supplied by Member 1's data layer and identifies visits that fell
outside their mandated time window.

How it works
------------
1. Build an index of VISIT_WINDOW rules keyed by visit_type for fast lookup.
2. For every Observation:
   a. Skip if actual_day is None (visit not yet recorded — nothing to check).
   b. Find the matching VISIT_WINDOW rule by visit_type.
   c. Compute: difference = abs(actual_day - expected_day)
   d. If difference > allowed_window → deviation detected.
3. Classify the severity of every detected deviation using the classifier.
4. Return a list of DeviationRecord objects (only deviations, never clean visits).

What this module does NOT do
-----------------------------
- It does NOT load or generate data.  Call Member 1's interface for that.
- It does NOT modify any Observation or ProtocolRule object.
- It does NOT handle non-VISIT_WINDOW rule types (ELIGIBILITY, DOSING,
  LAB_RANGE) — those are out of scope for this module.
- It does NOT write results to a file or database.

Typical usage
-------------
    from src.protocol.interface import load_project_data
    from src.deviation.detector import detect_deviations

    data       = load_project_data()
    deviations = detect_deviations(
        observations   = data["observations"],
        protocol_rules = data["protocol_rules"],
    )

    print(f"Found {len(deviations)} deviation(s).")
    for dev in deviations:
        print(dev)
"""

from __future__ import annotations

from src.protocol.models import Observation, ProtocolRule

from .classifier import classify_severity
from .models import DeviationRecord


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_deviations(
    observations: list[Observation],
    protocol_rules: list[ProtocolRule],
) -> list[DeviationRecord]:
    """Detect protocol deviations in a list of clinical observations.

    Compares each observation against the matching VISIT_WINDOW rule.
    Observations that fall outside the allowed window produce a
    :class:`~src.deviation.models.DeviationRecord` entry.

    Observations where ``actual_day`` is ``None`` (visit not yet recorded)
    are silently skipped — there is nothing to compare.

    Args:
        observations:   List of :class:`~src.protocol.models.Observation`
                        instances, typically from
                        ``load_project_data()["observations"]``.
        protocol_rules: List of :class:`~src.protocol.models.ProtocolRule`
                        instances, typically from
                        ``load_project_data()["protocol_rules"]``.
                        Only rules with ``rule_type == "VISIT_WINDOW"`` are
                        used; all others are ignored.

    Returns:
        A list of :class:`~src.deviation.models.DeviationRecord` objects,
        one per observation that deviated.  The list is empty when every
        observation is within its allowed window.

    Example::

        from src.protocol.interface import load_project_data
        from src.deviation.detector import detect_deviations

        data = load_project_data()
        deviations = detect_deviations(
            data["observations"],
            data["protocol_rules"],
        )
        print(f"{len(deviations)} deviation(s) found.")
    """
    # Build a lookup dict: visit_type → ProtocolRule for VISIT_WINDOW rules only.
    # This makes the inner loop O(1) per observation instead of O(rules).
    window_rules: dict[str, ProtocolRule] = _index_window_rules(protocol_rules)

    deviations: list[DeviationRecord] = []

    for obs in observations:
        # Skip observations where the visit has not yet been recorded.
        if obs.actual_day is None:
            continue

        # Find the matching VISIT_WINDOW rule for this visit type.
        rule = window_rules.get(obs.visit_type)
        if rule is None:
            # No VISIT_WINDOW rule exists for this visit type — skip it.
            # We do not raise an error because non-VISIT_WINDOW visit types
            # are valid; they simply have no window to check against here.
            continue

        # The rule's expected_value is stored as a string (e.g. "28").
        # Convert it to int for numeric comparison.
        # We trust that the loader/validator already verified this field
        # is a valid integer string for VISIT_WINDOW rules.
        try:
            rule_expected_day = int(rule.expected_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            # Malformed rule — skip gracefully rather than crashing the loop.
            continue

        # Core deviation check:
        #   difference = absolute gap between when the visit happened and
        #                when it was supposed to happen.
        difference: int = abs(obs.actual_day - obs.expected_day)

        # A deviation exists only when the gap EXCEEDS the allowed window.
        if difference <= rule.allowed_window:
            # Visit is within the permitted ± window — no deviation.
            continue

        # --- Deviation confirmed ---
        # Build an initial record with a placeholder severity so we can
        # pass it to classify_severity() which reads .difference and
        # .allowed_window from the record itself.
        partial_record = DeviationRecord(
            observation_id=obs.observation_id,
            patient_id=obs.patient_id,
            site_id=obs.site_id,
            visit_type=obs.visit_type,
            deviation_type=rule.rule_type,   # "VISIT_WINDOW"
            expected=obs.expected_day,
            actual=obs.actual_day,
            difference=difference,
            allowed_window=rule.allowed_window,
            severity="Administrative",        # placeholder — overwritten below
            status="OPEN",
        )

        # Classify severity based on how far past the window the visit is.
        severity = classify_severity(partial_record)

        # Rebuild with the real severity (model is frozen/immutable).
        record = DeviationRecord(
            observation_id=obs.observation_id,
            patient_id=obs.patient_id,
            site_id=obs.site_id,
            visit_type=obs.visit_type,
            deviation_type=rule.rule_type,
            expected=obs.expected_day,
            actual=obs.actual_day,
            difference=difference,
            allowed_window=rule.allowed_window,
            severity=severity,
            status="OPEN",
        )

        deviations.append(record)

    return deviations


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _index_window_rules(
    protocol_rules: list[ProtocolRule],
) -> dict[str, ProtocolRule]:
    """Build a visit_type → ProtocolRule dict for VISIT_WINDOW rules only.

    If more than one VISIT_WINDOW rule exists for the same visit_type,
    the last one wins (unusual in practice but handled safely).

    Args:
        protocol_rules: Full list of protocol rules from the data layer.

    Returns:
        Dict mapping visit_type strings to their VISIT_WINDOW rule.
    """
    index: dict[str, ProtocolRule] = {}
    for rule in protocol_rules:
        if rule.rule_type == "VISIT_WINDOW" and rule.visit_type is not None:
            index[rule.visit_type] = rule
    return index
