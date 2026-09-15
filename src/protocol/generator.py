"""
generator.py — Synthetic clinical-trial dataset generator.

Generates four CSV files and one JSON schema file that form a complete,
self-consistent demo dataset for the Clinical Trial Risk Monitor:

    trials.csv                — one registered clinical trial
    sites.csv                 — participating clinical sites
    participants.csv          — enrolled patients (distributed across sites)
    observations.csv          — clinical visit records
    schemas/protocol_rules.json — protocol rules document (8 rules)

Key design goals:
  - Fully deterministic: the same seed always produces the same data.
  - Referentially intact: every patient and observation traces back to
    a real site; every observation traces back to a real patient.
  - Realistic but synthetic: values look plausible without containing
    any real personal data.
  - Demo-ready: a small number of observations have actual_day values
    that fall outside the normal visit window so that Member 2's
    deviation detector has something to find.  These records are NOT
    labelled as deviations here — they are ordinary rows with unusual
    actual_day numbers.
  - Complete: writing protocol_rules.json alongside the CSVs means a
    single call to generate_dataset() produces a fully loadable dataset.
    Previously the JSON was only written by the root generate_data.py
    script, which caused load_project_data() to fail on fresh checkouts.

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

# ---------------------------------------------------------------------------
# Static site data (Indian clinical research sites)
# ---------------------------------------------------------------------------

SITES: list[dict] = [
    {"site_id": "S001", "site_name": "Apollo Hospitals Chennai",      "country": "India", "status": "ACTIVE"},
    {"site_id": "S002", "site_name": "Fortis Memorial Research Inst.", "country": "India", "status": "ACTIVE"},
    {"site_id": "S003", "site_name": "AIIMS New Delhi",               "country": "India", "status": "ACTIVE"},
    {"site_id": "S004", "site_name": "Narayana Health Bangalore",     "country": "India", "status": "ACTIVE"},
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
# ---------------------------------------------------------------------------

PROTOCOL_RULES: dict[str, Any] = {
    "rules": [
        {
            "rule_id": "RULE-001",
            "rule_type": "VISIT_WINDOW",
            "description": "BASELINE visit must occur within ±3 days of Day 0.",
            "visit_type": "BASELINE",
            "expected_value": "0",
            "allowed_window": 3,
        },
        {
            "rule_id": "RULE-002",
            "rule_type": "VISIT_WINDOW",
            "description": "WEEK_4 visit must occur within ±3 days of Day 28.",
            "visit_type": "WEEK_4",
            "expected_value": "28",
            "allowed_window": 3,
        },
        {
            "rule_id": "RULE-003",
            "rule_type": "VISIT_WINDOW",
            "description": "WEEK_8 visit must occur within ±3 days of Day 56.",
            "visit_type": "WEEK_8",
            "expected_value": "56",
            "allowed_window": 3,
        },
        {
            "rule_id": "RULE-004",
            "rule_type": "VISIT_WINDOW",
            "description": "WEEK_12 visit must occur within ±3 days of Day 84.",
            "visit_type": "WEEK_12",
            "expected_value": "84",
            "allowed_window": 3,
        },
        {
            "rule_id": "RULE-005",
            "rule_type": "ELIGIBILITY",
            "description": "Patient must be at least 18 years old at enrollment.",
            "visit_type": None,
            "expected_value": "18",
            "allowed_window": None,
        },
        {
            "rule_id": "RULE-006",
            "rule_type": "ELIGIBILITY",
            "description": "Patient must be no older than 75 years old at enrollment.",
            "visit_type": None,
            "expected_value": "75",
            "allowed_window": None,
        },
        {
            "rule_id": "RULE-007",
            "rule_type": "DOSING",
            "description": "Study drug must be administered within 2 days of scheduled visit.",
            "visit_type": "WEEK_4",
            "expected_value": "28",
            "allowed_window": 2,
        },
        {
            "rule_id": "RULE-008",
            "rule_type": "LAB_RANGE",
            "description": "Hemoglobin must be within normal range at BASELINE.",
            "visit_type": "BASELINE",
            "expected_value": "13",
            "allowed_window": None,
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
            sites.csv
            participants.csv
            observations.csv          ← includes site_id column
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
    """Write sites.csv (static — four Indian research sites)."""
    _write_csv(
        path=out / "sites.csv",
        fieldnames=["site_id", "site_name", "country", "status"],
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
        patient_id      = f"P{i + 1:03d}"          # P001, P002, …
        site_id         = site_ids[i % len(site_ids)]  # round-robin
        age             = rng.randint(18, 75)
        gender          = rng.choices(genders, weights=[0.48, 0.48, 0.04])[0]
        days_offset     = rng.randint(0, 180)
        enrollment_date = base_date + timedelta(days=days_offset)
        status          = rng.choices(statuses, weights=status_weights)[0]

        participants.append({
            "patient_id":      patient_id,
            "site_id":         site_id,
            "age":             age,
            "gender":          gender,
            "enrollment_date": enrollment_date.isoformat(),
            "status":          status,
        })

    _write_csv(
        path=out / "participants.csv",
        fieldnames=["patient_id", "site_id", "age", "gender", "enrollment_date", "status"],
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

    These out-of-window records are NOT labelled — they are plain rows
    with an unusual actual_day value.
    """
    observations = []
    obs_counter  = 1  # used for unique observation_id

    for participant in participants:
        patient_id = participant["patient_id"]
        site_id    = participant["site_id"]

        for visit_type, expected_day, window in VISIT_SCHEDULE:
            observation_id = f"OBS-{obs_counter:04d}"
            obs_counter += 1

            # Decide whether this record should be out-of-window
            make_anomaly = rng.random() < ANOMALY_FRACTION

            if make_anomaly:
                # Push actual_day clearly beyond the allowed window.
                # Randomly choose early or late.
                direction = rng.choice([-1, 1])
                offset    = direction * (window + ANOMALY_EXTRA_DAYS)
                actual_day: Optional[int] = expected_day + offset
            else:
                # Normal: actual_day within ±window of expected_day
                actual_day = expected_day + rng.randint(-window, window)

            observations.append({
                "observation_id": observation_id,
                "patient_id":     patient_id,
                "site_id":        site_id,
                "visit_type":     visit_type,
                "expected_day":   expected_day,
                "actual_day":     actual_day,
            })

    _write_csv(
        path=out / "observations.csv",
        fieldnames=[
            "observation_id",
            "patient_id",
            "site_id",
            "visit_type",
            "expected_day",
            "actual_day",
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
