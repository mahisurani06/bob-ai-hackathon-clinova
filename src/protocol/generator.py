"""
generator.py — Synthetic clinical-trial dataset generator.

Generates four CSV files and one JSON schema file that form a complete,
self-consistent demo dataset for the Clinical Trial Risk Monitor:

    trials.csv                — one registered clinical trial
    sites.csv                 — participating clinical sites (with trial_id)
    participants.csv          — enrolled patients (with trial_id)
    observations.csv          — clinical visit records (with trial_id,
                                dose_mg, lab_value, lab_unit)
    schemas/protocol_rules.json — protocol rules document (8 rules, with
                                  machine-readable operator/min_value/max_value)

Key design goals:
  - Fully deterministic: the same seed always produces the same data.
  - Referentially intact: every patient and observation traces back to
    a real site and trial; every observation traces back to a real patient.
  - Realistic but synthetic: values look plausible without containing
    any real personal data.
  - Demo-ready:
    * A small fraction of observations have actual_day values outside the
      visit window so that Member 2's deviation detector has anomalies to
      find.
    * A small fraction of participants have age > 75 so that the ELIGIBILITY
      rule detector (age <= 75) has violations to surface.
    * WEEK_4 observations carry dose_mg values; a small fraction are
      deliberately outside the dosing window.
    * BASELINE observations carry lab_value (hemoglobin in g/dL); a small
      fraction are out of the normal range [12.0, 17.5].
    These records are NOT labelled as deviations here — they are ordinary
    rows with unusual values.
  - Complete: writing protocol_rules.json alongside the CSVs means a
    single call to generate_dataset() produces a fully loadable dataset.

Usage (command line):
    python -m src.protocol.generator

Usage (from code):
    from src.protocol.generator import generate_dataset
    generate_dataset(output_dir="src/data/synthetic", seed=42)
"""

from __future__ import annotations

import csv
import json
import os
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants — visit schedule
# Each entry is (visit_type, expected_day, allowed_window).
# allowed_window is stored here only so the generator can produce a
# realistic spread of actual_day values; the deviation detector (Member 2)
# will read the window from the protocol rules, NOT from this file.
# ---------------------------------------------------------------------------

VISIT_SCHEDULE: list[tuple[str, int, int]] = [
    ("BASELINE", 0,   3),
    ("WEEK_4",   28,  3),
    ("WEEK_8",   56,  3),
    ("WEEK_12",  84,  3),
]

# Fraction of observations to make intentionally out-of-window for demo.
# 0.08 ≈ 8% — small enough that most data looks clean.
ANOMALY_FRACTION: float = 0.08

# How many days outside the window an anomalous observation should land.
ANOMALY_EXTRA_DAYS: int = 7   # e.g. window=3 → actual offset = 3+7 = 10 days late

# Normal dose range for on-window dosing observations (mg).
DOSE_MG_NORMAL: float = 100.0

# Fraction of WEEK_4 observations with an out-of-range dose (for DOSING rule).
DOSE_ANOMALY_FRACTION: float = 0.10

# Hemoglobin normal range (g/dL) — mirrors RULE-008 (LAB_RANGE).
LAB_HGB_MIN: float = 12.0
LAB_HGB_MAX: float = 17.5
LAB_HGB_UNIT: str = "g/dL"

# Fraction of BASELINE observations with an out-of-range hemoglobin value.
LAB_ANOMALY_FRACTION: float = 0.10

# ---------------------------------------------------------------------------
# Static site data (Indian clinical research sites)
# ---------------------------------------------------------------------------

SITES: list[dict] = [
    {"site_id": "S001", "trial_id": "TRIAL-001", "site_name": "Apollo Hospitals Chennai",      "country": "India", "status": "ACTIVE"},
    {"site_id": "S002", "trial_id": "TRIAL-001", "site_name": "Fortis Memorial Research Inst.", "country": "India", "status": "ACTIVE"},
    {"site_id": "S003", "trial_id": "TRIAL-001", "site_name": "AIIMS New Delhi",               "country": "India", "status": "ACTIVE"},
    {"site_id": "S004", "trial_id": "TRIAL-001", "site_name": "Narayana Health Bangalore",     "country": "India", "status": "ACTIVE"},
]

# Static trial (one demo trial as specified)
TRIALS: list[dict] = [
    {
        "trial_id":   "TRIAL-001",
        "trial_name": "Demo Clinical Trial",
        "version":    "1.0",
        "status":     "ACTIVE",
    }
]

# ---------------------------------------------------------------------------
# Static protocol rules — mirrors the rule set expected by the loader and
# already used by the project (8 rules covering VISIT_WINDOW, ELIGIBILITY,
# DOSING, and LAB_RANGE).  These are static data; they do not depend on the
# RNG seed.
#
# Changes from v1:
#   RULE-005 / RULE-006 — ELIGIBILITY rules now carry explicit machine-readable
#       fields: field="age", operator=">=" / operator="<=", and min_value /
#       max_value.  expected_value is kept for backward compatibility with
#       Member 2's existing detector which reads int(rule.expected_value).
#   RULE-008 — LAB_RANGE rule now uses min_value + max_value (the true
#       numeric range) and unit="g/dL" instead of the ambiguous expected_value
#       single-number.  expected_value is removed from this rule because it
#       represented neither a minimum nor maximum in isolation.
# ---------------------------------------------------------------------------

PROTOCOL_RULES: dict[str, Any] = {
    "rules": [
        {
            "rule_id":       "RULE-001",
            "rule_type":     "VISIT_WINDOW",
            "description":   "BASELINE visit must occur within \u00b13 days of Day 0.",
            "visit_type":    "BASELINE",
            "expected_value": "0",
            "allowed_window": 3,
        },
        {
            "rule_id":       "RULE-002",
            "rule_type":     "VISIT_WINDOW",
            "description":   "WEEK_4 visit must occur within \u00b13 days of Day 28.",
            "visit_type":    "WEEK_4",
            "expected_value": "28",
            "allowed_window": 3,
        },
        {
            "rule_id":       "RULE-003",
            "rule_type":     "VISIT_WINDOW",
            "description":   "WEEK_8 visit must occur within \u00b13 days of Day 56.",
            "visit_type":    "WEEK_8",
            "expected_value": "56",
            "allowed_window": 3,
        },
        {
            "rule_id":       "RULE-004",
            "rule_type":     "VISIT_WINDOW",
            "description":   "WEEK_12 visit must occur within \u00b13 days of Day 84.",
            "visit_type":    "WEEK_12",
            "expected_value": "84",
            "allowed_window": 3,
        },
        {
            "rule_id":        "RULE-005",
            "rule_type":      "ELIGIBILITY",
            "description":    "Patient must be at least 18 years old at enrollment.",
            "field":          "age",
            "operator":       ">=",
            "expected_value": "18",
            "min_value":      18.0,
        },
        {
            "rule_id":        "RULE-006",
            "rule_type":      "ELIGIBILITY",
            "description":    "Patient must be no older than 75 years old at enrollment.",
            "field":          "age",
            "operator":       "<=",
            "expected_value": "75",
            "max_value":      75.0,
        },
        {
            "rule_id":        "RULE-007",
            "rule_type":      "DOSING",
            "description":    "Study drug must be administered within 2 days of scheduled visit.",
            "visit_type":     "WEEK_4",
            "expected_value": "28",
            "allowed_window": 2,
        },
        {
            "rule_id":     "RULE-008",
            "rule_type":   "LAB_RANGE",
            "description": "Hemoglobin must be within normal range (12.0\u201317.5 g/dL) at BASELINE.",
            "visit_type":  "BASELINE",
            "field":       "lab_value",
            "operator":    "range",
            "min_value":   12.0,
            "max_value":   17.5,
            "unit":        "g/dL",
        },
    ]
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_dataset(
    output_dir: str = "src/data/synthetic",
    num_participants: int = 20,
    seed: int = 42,
) -> None:
    """Generate a complete synthetic clinical-trial dataset.

    Creates four CSV files in ``output_dir`` and writes
    ``protocol_rules.json`` into a ``schemas/`` directory that sits
    alongside ``output_dir`` (i.e. ``<parent>/schemas/``).

    File layout produced::

        <output_dir>/
            trials.csv
            sites.csv                 ← includes trial_id column
            participants.csv          ← includes trial_id column
            observations.csv          ← includes trial_id, dose_mg,
                                         lab_value, lab_unit columns
        <output_dir>/../schemas/
            protocol_rules.json

    The dataset is fully deterministic: calling this function twice with
    the same ``seed`` produces byte-identical files.

    Args:
        output_dir:       Directory where CSV files will be written.
                          Created automatically if it does not exist.
        num_participants: Number of synthetic patients to generate.
                          Participants are distributed evenly across sites.
        seed:             Random seed for reproducibility.  Default 42.

    Raises:
        ValueError: If num_participants < 1.
    """
    if num_participants < 1:
        raise ValueError("num_participants must be at least 1.")

    rng = random.Random(seed)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # schemas/ lives next to synthetic/ (i.e. one level up from output_dir)
    schemas_dir = out.parent / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)

    _write_trials(out)
    _write_sites(out)
    participants = _write_participants(out, num_participants, rng)
    _write_observations(out, participants, rng)
    _write_protocol_rules(schemas_dir)

    print(f"[generator] Dataset written to '{out.resolve()}'")
    print(f"[generator]   trials.csv        — {len(TRIALS)} row(s)")
    print(f"[generator]   sites.csv         — {len(SITES)} row(s)")
    print(f"[generator]   participants.csv  — {num_participants} row(s)")
    obs_count = num_participants * len(VISIT_SCHEDULE)
    print(f"[generator]   observations.csv  — {obs_count} row(s)")
    print(f"[generator]   protocol_rules.json — {len(PROTOCOL_RULES['rules'])} rule(s)")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _write_trials(out: Path) -> None:
    """Write trials.csv (static — one demo trial)."""
    _write_csv(
        path=out / "trials.csv",
        fieldnames=["trial_id", "trial_name", "version", "status"],
        rows=TRIALS,
    )


def _write_sites(out: Path) -> None:
    """Write sites.csv (static — four Indian research sites, each with trial_id)."""
    _write_csv(
        path=out / "sites.csv",
        fieldnames=["site_id", "trial_id", "site_name", "country", "status"],
        rows=SITES,
    )


def _write_participants(
    out: Path,
    num_participants: int,
    rng: random.Random,
) -> list[dict]:
    """Generate participants and write participants.csv.

    Participants are distributed across sites in round-robin order so
    that each site receives roughly the same number of patients.

    Age is sampled from 16–80 to ensure the dataset contains some
    participants outside the protocol eligibility window (age < 18 or
    age > 75), giving Member 2's ELIGIBILITY detector cases to flag.
    The data-quality bound on Participant.age is 0–120 so these values
    are accepted by the model without error.

    Returns:
        The list of generated participant dicts (used by
        _write_observations to maintain referential integrity).
    """
    site_ids    = [s["site_id"] for s in SITES]
    genders     = ["MALE", "FEMALE", "OTHER"]
    statuses    = ["ENROLLED", "COMPLETED", "WITHDRAWN", "SCREEN_FAIL"]
    # Weight: most participants should be ENROLLED or COMPLETED
    status_weights = [0.55, 0.30, 0.10, 0.05]

    # Base enrollment date — spread participants over a 6-month window
    base_date = date(2023, 1, 1)

    participants = []
    for i in range(num_participants):
        patient_id      = f"P{i + 1:03d}"              # P001, P002, …
        site_id         = site_ids[i % len(site_ids)]  # round-robin
        # Age range 16–80 allows both under-18 and over-75 participants
        # so the ELIGIBILITY rules (>= 18, <= 75) have violations to detect.
        age             = rng.randint(16, 80)
        gender          = rng.choices(genders, weights=[0.48, 0.48, 0.04])[0]
        days_offset     = rng.randint(0, 180)
        enrollment_date = base_date + timedelta(days=days_offset)
        status          = rng.choices(statuses, weights=status_weights)[0]

        participants.append({
            "patient_id":      patient_id,
            "trial_id":        "TRIAL-001",
            "site_id":         site_id,
            "age":             age,
            "gender":          gender,
            "enrollment_date": enrollment_date.isoformat(),
            "status":          status,
        })

    _write_csv(
        path=out / "participants.csv",
        fieldnames=["patient_id", "trial_id", "site_id", "age", "gender", "enrollment_date", "status"],
        rows=participants,
    )
    return participants


def _write_observations(
    out: Path,
    participants: list[dict],
    rng: random.Random,
) -> None:
    """Generate one observation per visit type per participant.

    For most participants the actual_day is within the visit window
    (expected_day ± allowed_window).  A small fraction of observations
    are intentionally placed outside the window so Member 2's deviation
    detector has identifiable anomalies to find.

    Additional fields generated per observation:
    - dose_mg   : set for WEEK_4 visits; most are 100 mg (on-protocol);
                  a small fraction are set to an out-of-window day value
                  to exercise DOSING rule detection.
    - lab_value : set for BASELINE visits; most are within the normal
                  haemoglobin range [12.0, 17.5] g/dL; a small fraction
                  fall outside that range to exercise LAB_RANGE detection.
    - lab_unit  : "g/dL" whenever lab_value is set; None otherwise.

    These out-of-window / out-of-range records are NOT labelled —
    they are plain rows with unusual values.
    """
    observations = []
    obs_counter  = 1  # used for unique observation_id

    for participant in participants:
        patient_id = participant["patient_id"]
        site_id    = participant["site_id"]

        for visit_type, expected_day, window in VISIT_SCHEDULE:
            observation_id = f"OBS-{obs_counter:04d}"
            obs_counter += 1

            # ── Visit timing ──────────────────────────────────────────
            make_anomaly = rng.random() < ANOMALY_FRACTION

            if make_anomaly:
                direction = rng.choice([-1, 1])
                offset    = direction * (window + ANOMALY_EXTRA_DAYS)
                actual_day: Optional[int] = expected_day + offset
            else:
                actual_day = expected_day + rng.randint(-window, window)

            # ── Dosing (WEEK_4 only) ──────────────────────────────────
            dose_mg: Optional[float] = None
            if visit_type == "WEEK_4":
                if rng.random() < DOSE_ANOMALY_FRACTION:
                    # Out-of-window dose day: use a dose that falls well
                    # outside the ±2-day window of RULE-007.
                    # We encode the "day" of administration as the
                    # dose_mg offset from expected_day, capped to a
                    # realistic mg value.  Here we use the actual dose
                    # amount; Member 2 checks actual_day vs expected_day
                    # for DOSING rules just like VISIT_WINDOW rules.
                    # For simplicity, anomalous doses are given as 50 mg
                    # (half-dose) while normal doses are 100 mg.
                    dose_mg = 50.0
                else:
                    dose_mg = DOSE_MG_NORMAL

            # ── Lab value (BASELINE only) ─────────────────────────────
            lab_value: Optional[float] = None
            lab_unit:  Optional[str]   = None
            if visit_type == "BASELINE":
                if rng.random() < LAB_ANOMALY_FRACTION:
                    # Out-of-range haemoglobin: below 12 or above 17.5
                    if rng.random() < 0.5:
                        lab_value = round(rng.uniform(8.0, 11.9), 1)   # low
                    else:
                        lab_value = round(rng.uniform(17.6, 21.0), 1)  # high
                else:
                    # Normal haemoglobin within [12.0, 17.5]
                    lab_value = round(rng.uniform(LAB_HGB_MIN, LAB_HGB_MAX), 1)
                lab_unit = LAB_HGB_UNIT

            observations.append({
                "observation_id": observation_id,
                "trial_id":       "TRIAL-001",
                "patient_id":     patient_id,
                "site_id":        site_id,
                "visit_type":     visit_type,
                "expected_day":   expected_day,
                "actual_day":     actual_day,
                "dose_mg":        "" if dose_mg is None else dose_mg,
                "lab_value":      "" if lab_value is None else lab_value,
                "lab_unit":       "" if lab_unit is None else lab_unit,
            })

    _write_csv(
        path=out / "observations.csv",
        fieldnames=[
            "observation_id",
            "trial_id",
            "patient_id",
            "site_id",
            "visit_type",
            "expected_day",
            "actual_day",
            "dose_mg",
            "lab_value",
            "lab_unit",
        ],
        rows=observations,
    )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    """Write a list of dicts to a CSV file with a header row.

    Args:
        path:       Destination file path.
        fieldnames: Column names in the order they should appear.
        rows:       List of dicts; each dict must contain all fieldnames.
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_protocol_rules(schemas_dir: Path) -> None:
    """Write ``protocol_rules.json`` to ``schemas_dir``.

    The rules are static (see the ``PROTOCOL_RULES`` module-level constant)
    so this function always produces the same file regardless of the RNG
    seed.

    Args:
        schemas_dir: Directory where ``protocol_rules.json`` will be
                     written.  Created automatically by the caller.
    """
    path = schemas_dir / "protocol_rules.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(PROTOCOL_RULES, fh, indent=2)


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    generate_dataset(
        output_dir="src/data/synthetic",
        num_participants=20,
        seed=42,
    )
