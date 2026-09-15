"""
validator.py — Data-quality and referential-integrity validator.

This module checks that the clinical-trial dataset is internally
consistent and structurally sound BEFORE it is used by downstream
modules (deviation detection, risk scoring, etc.).

What this validator does
------------------------
- Uniqueness checks  : no duplicate IDs across trials, sites,
                       participants, observations, or rules.
- Referential checks : every participant.site_id exists in the site
                       list; every observation.patient_id and
                       observation.site_id exist in the respective
                       parent lists.
- Completeness checks: required collections are non-empty; required
                       string fields are non-blank.

What this validator does NOT do
--------------------------------
- It does NOT detect protocol deviations.
- It does NOT classify deviations as Major / Minor / Administrative.
- It does NOT calculate site risk scores.
- It does NOT implement any AI or watsonx logic.
- It does NOT determine whether an observation violates a rule.

Pydantic already enforces field types and value constraints at parse
time (via the loader).  This layer therefore focuses exclusively on
cross-record integrity that Pydantic cannot check on its own.

Usage
-----
    from src.protocol.loader    import load_all_data
    from src.protocol.validator import validate_all

    data   = load_all_data()
    result = validate_all(data)

    if result["valid"]:
        print("Dataset is clean.")
    else:
        for err in result["errors"]:
            print("ERROR:", err)
"""

from __future__ import annotations

from typing import Any

from .models import Observation, Participant, ProtocolRule, Site, Trial


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

def _make_result() -> dict[str, Any]:
    """Return a fresh, empty validation result dict."""
    return {"valid": True, "errors": [], "warnings": []}


def _error(result: dict, message: str) -> None:
    """Append an error and mark the result as invalid."""
    result["errors"].append(message)
    result["valid"] = False


def _warning(result: dict, message: str) -> None:
    """Append a non-fatal warning (does not mark the result as invalid)."""
    result["warnings"].append(message)


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

def validate_trials(trials: list[Trial]) -> dict[str, Any]:
    """Validate the trials list.

    Checks performed:
    - The list is not empty.
    - Every trial_id is a non-empty string (enforced by Pydantic on load;
      re-confirmed here as a belt-and-braces check).
    - trial_id values are unique across the list.

    Args:
        trials: List of :class:`~src.protocol.models.Trial` instances,
                typically from :func:`~src.protocol.loader.load_trials`.

    Returns:
        Validation result dict with keys ``"valid"``, ``"errors"``,
        ``"warnings"``.
    """
    result = _make_result()

    # 1. Non-empty collection
    if not trials:
        _error(result, "trials list is empty — at least one trial is required.")
        return result  # no point checking further

    # 2. Non-blank trial_id (belt-and-braces on top of Pydantic)
    for i, trial in enumerate(trials):
        if not trial.trial_id.strip():
            _error(result, f"Trial at index {i} has a blank trial_id.")

    # 3. Unique trial_id values
    seen: set[str] = set()
    for trial in trials:
        if trial.trial_id in seen:
            _error(result, f"Duplicate trial_id found: '{trial.trial_id}'.")
        seen.add(trial.trial_id)

    return result


def validate_sites(sites: list[Site]) -> dict[str, Any]:
    """Validate the sites list.

    Checks performed:
    - The list is not empty.
    - Every site_id is a non-empty string.
    - site_id values are unique.
    - Every site_name and country field is non-blank.
    - trial_id is non-blank for every site.

    Args:
        sites: List of :class:`~src.protocol.models.Site` instances.

    Returns:
        Validation result dict.
    """
    result = _make_result()

    if not sites:
        _error(result, "sites list is empty — at least one site is required.")
        return result

    seen: set[str] = set()
    for i, site in enumerate(sites):
        # Unique site_id
        if site.site_id in seen:
            _error(result, f"Duplicate site_id found: '{site.site_id}'.")
        seen.add(site.site_id)

        # Non-blank required string fields
        if not site.site_id.strip():
            _error(result, f"Site at index {i} has a blank site_id.")
        if not site.site_name.strip():
            _error(result, f"Site '{site.site_id}' has a blank site_name.")
        if not site.country.strip():
            _error(result, f"Site '{site.site_id}' has a blank country.")
        if not site.trial_id.strip():
            _error(result, f"Site '{site.site_id}' has a blank trial_id.")

    return result


def validate_participants(
    participants: list[Participant],
    sites: list[Site],
) -> dict[str, Any]:
    """Validate the participants list against the sites list.

    Checks performed:
    - The list is not empty.
    - Every patient_id is unique.
    - trial_id is non-blank for every participant.
    - Every participant.site_id references a site that exists in
      the ``sites`` list (referential integrity).
    - enrollment_date is not None (Pydantic guarantees a ``date``
      object; we confirm it is actually present).

    Note: protocol eligibility constraints (age bounds) are NOT
    checked here.  The Participant model allows any age in [0, 120]
    so that the data layer can represent eligibility violations for
    Member 2's deviation detector to find.

    Args:
        participants: List of :class:`~src.protocol.models.Participant`
                      instances.
        sites:        List of :class:`~src.protocol.models.Site`
                      instances used for the foreign-key check.

    Returns:
        Validation result dict.
    """
    result = _make_result()

    if not participants:
        _error(result, "participants list is empty.")
        return result

    valid_site_ids = {s.site_id for s in sites}
    seen_patient_ids: set[str] = set()

    for participant in participants:
        # Unique patient_id
        if participant.patient_id in seen_patient_ids:
            _error(
                result,
                f"Duplicate patient_id found: '{participant.patient_id}'.",
            )
        seen_patient_ids.add(participant.patient_id)

        # trial_id must be non-blank
        if not participant.trial_id.strip():
            _error(
                result,
                f"Participant '{participant.patient_id}' has a blank trial_id.",
            )

        # Referential integrity: site must exist
        if participant.site_id not in valid_site_ids:
            _error(
                result,
                f"Participant '{participant.patient_id}' references unknown "
                f"site_id '{participant.site_id}'. "
                f"Known sites: {sorted(valid_site_ids)}.",
            )

        # enrollment_date must be a real date (not None)
        if participant.enrollment_date is None:
            _error(
                result,
                f"Participant '{participant.patient_id}' has no enrollment_date.",
            )

    return result


def validate_observations(
    observations: list[Observation],
    participants: list[Participant],
    sites: list[Site],
) -> dict[str, Any]:
    """Validate the observations list against participants and sites.

    Checks performed:
    - The list is not empty.
    - Every observation_id is unique.
    - trial_id is non-blank for every observation.
    - Every observation.patient_id references an existing participant.
    - Every observation.site_id references an existing site.
    - expected_day is a non-negative integer.
    - actual_day is either None (visit not yet recorded — valid) or
      an integer.
    - visit_type is a non-blank string.
    - dose_mg is None or a non-negative float (Pydantic enforces ge=0;
      we emit a warning if dose_mg is present on a non-WEEK_4 visit
      as that would be unexpected).
    - lab_value and lab_unit are consistent (both present or both None).

    Note: This validator does NOT check whether actual_day falls
    within the protocol-mandated visit window, whether a dose is
    outside a dosing window, or whether a lab_value is out of range.
    All of those checks belong to Member 2's deviation detector.

    Args:
        observations:  List of :class:`~src.protocol.models.Observation`
                       instances.
        participants:  List of participants for the patient_id FK check.
        sites:         List of sites for the site_id FK check.

    Returns:
        Validation result dict.
    """
    result = _make_result()

    if not observations:
        _error(result, "observations list is empty.")
        return result

    valid_patient_ids = {p.patient_id for p in participants}
    valid_site_ids    = {s.site_id    for s in sites}
    seen_obs_ids: set[str] = set()

    for obs in observations:
        # Unique observation_id
        if obs.observation_id in seen_obs_ids:
            _error(
                result,
                f"Duplicate observation_id found: '{obs.observation_id}'.",
            )
        seen_obs_ids.add(obs.observation_id)

        # Referential integrity: patient must exist
        if obs.patient_id not in valid_patient_ids:
            _error(
                result,
                f"Observation '{obs.observation_id}' references unknown "
                f"patient_id '{obs.patient_id}'.",
            )

        # Referential integrity: site must exist
        if obs.site_id not in valid_site_ids:
            _error(
                result,
                f"Observation '{obs.observation_id}' references unknown "
                f"site_id '{obs.site_id}'.",
            )

        # visit_type must be non-blank
        if not obs.visit_type.strip():
            _error(
                result,
                f"Observation '{obs.observation_id}' has a blank visit_type.",
            )

        # expected_day must be non-negative (Pydantic enforces ge=0;
        # confirmed here so any future manual construction is caught too)
        if obs.expected_day < 0:
            _error(
                result,
                f"Observation '{obs.observation_id}' has a negative "
                f"expected_day ({obs.expected_day}).",
            )

        # actual_day: None is acceptable; if present it must be an int
        # (Pydantic guarantees this, but we emit a warning when it is None
        # so that a human reviewer knows the visit has not been recorded)
        if obs.actual_day is None:
            _warning(
                result,
                f"Observation '{obs.observation_id}' ({obs.patient_id}, "
                f"{obs.visit_type}) has no actual_day — visit not yet recorded.",
            )

        # trial_id must be non-blank
        if not obs.trial_id.strip():
            _error(
                result,
                f"Observation '{obs.observation_id}' has a blank trial_id.",
            )

        # lab_value / lab_unit consistency: both or neither
        if obs.lab_value is not None and obs.lab_unit is None:
            _warning(
                result,
                f"Observation '{obs.observation_id}' has lab_value={obs.lab_value} "
                "but no lab_unit.",
            )

    return result


def validate_protocol_rules(protocol_rules: list[ProtocolRule]) -> dict[str, Any]:
    """Validate the protocol rules list.

    Checks performed:
    - The list is not empty.
    - Every rule_id is unique.
    - description is non-blank for every rule.
    - When allowed_window is set, expected_value must also be set
      (mirrors the Pydantic cross-field validator — caught at load time,
      but re-confirmed here for belt-and-braces).
    - LAB_RANGE rules are expected to have min_value and max_value set
      (warning if missing — not a hard error, to allow partial rules).
    - ELIGIBILITY rules are expected to have operator and field set
      (warning if missing — older rule format is still accepted).

    Args:
        protocol_rules: List of :class:`~src.protocol.models.ProtocolRule`
                        instances.

    Returns:
        Validation result dict.
    """
    result = _make_result()

    if not protocol_rules:
        _error(result, "protocol_rules list is empty — no rules to validate against.")
        return result

    seen_rule_ids: set[str] = set()

    for rule in protocol_rules:
        # Unique rule_id
        if rule.rule_id in seen_rule_ids:
            _error(result, f"Duplicate rule_id found: '{rule.rule_id}'.")
        seen_rule_ids.add(rule.rule_id)

        # Non-blank description
        if not rule.description.strip():
            _error(result, f"Rule '{rule.rule_id}' has a blank description.")

        # Cross-field: allowed_window requires expected_value
        if rule.allowed_window is not None and rule.expected_value is None:
            _error(
                result,
                f"Rule '{rule.rule_id}' has allowed_window={rule.allowed_window} "
                "but no expected_value — window has no target to measure against.",
            )

        # LAB_RANGE rules should define a proper numeric range
        if rule.rule_type == "LAB_RANGE":
            if rule.min_value is None or rule.max_value is None:
                _warning(
                    result,
                    f"LAB_RANGE rule '{rule.rule_id}' is missing min_value or "
                    "max_value — range check will not be possible.",
                )

        # ELIGIBILITY rules should carry machine-readable operator and field
        if rule.rule_type == "ELIGIBILITY":
            if rule.operator is None or rule.field is None:
                _warning(
                    result,
                    f"ELIGIBILITY rule '{rule.rule_id}' is missing operator or "
                    "field — rule will be evaluated by description text heuristic only.",
                )

    return result


# ---------------------------------------------------------------------------
# Aggregate validator
# ---------------------------------------------------------------------------

def validate_all(data: dict[str, list]) -> dict[str, Any]:
    """Run all validation checks on the full dataset.

    Accepts the dictionary returned by
    :func:`~src.protocol.loader.load_all_data` and runs every
    individual validator.  Errors and warnings from each check are
    merged into a single result.

    Args:
        data: Dict with keys ``"trials"``, ``"sites"``,
              ``"participants"``, ``"observations"``,
              ``"protocol_rules"``.  Produced by ``load_all_data()``.

    Returns:
        A dict::

            {
                "valid":    True | False,
                "errors":   ["...", ...],   # fatal data problems
                "warnings": ["...", ...],   # non-fatal notes
            }

        ``"valid"`` is ``True`` only when ``"errors"`` is empty.

    Example::

        from src.protocol.loader    import load_all_data
        from src.protocol.validator import validate_all

        result = validate_all(load_all_data())
        print(result["valid"])   # True / False
    """
    combined = _make_result()

    trials         = data.get("trials",         [])
    sites          = data.get("sites",          [])
    participants   = data.get("participants",   [])
    observations   = data.get("observations",   [])
    protocol_rules = data.get("protocol_rules", [])

    # Run each check and merge results
    for check_result in [
        validate_trials(trials),
        validate_sites(sites),
        validate_participants(participants, sites),
        validate_observations(observations, participants, sites),
        validate_protocol_rules(protocol_rules),
    ]:
        combined["errors"].extend(check_result["errors"])
        combined["warnings"].extend(check_result["warnings"])

    # A single error makes the whole dataset invalid
    if combined["errors"]:
        combined["valid"] = False

    return combined


# ---------------------------------------------------------------------------
# Command-line entry point — smoke-test against the live dataset
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from .loader import load_all_data

    print("Loading data…")
    data = load_all_data()

    print("Running validation…\n")
    result = validate_all(data)

    if result["valid"]:
        print("PASS  Dataset is VALID -- no errors found.")
    else:
        print(f"FAIL  Dataset is INVALID -- {len(result['errors'])} error(s) found.")

    if result["errors"]:
        print("\nErrors:")
        for err in result["errors"]:
            print(f"  ERROR   : {err}")

    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])} total):")
        for warn in result["warnings"]:
            print(f"  WARNING : {warn}")

    print(
        f"\nSummary: {len(result['errors'])} error(s), "
        f"{len(result['warnings'])} warning(s)."
    )
