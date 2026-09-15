"""
loader.py — Data loader for the Clinical Trial Risk Monitor.

Reads the synthetic clinical-trial dataset (CSV files) and the
protocol rules document (JSON) and returns typed Pydantic model
instances that the rest of the project can work with directly.

File layout expected under the data root (default: src/data/):

    synthetic/
        trials.csv          ← Trial records
        sites.csv           ← Site records
        participants.csv    ← Participant records
        observations.csv    ← Visit / observation records

    schemas/
        protocol_rules.json ← Protocol rule instances for the trial

Public functions
----------------
load_trials(data_dir)           → list[Trial]
load_sites(data_dir)            → list[Site]
load_participants(data_dir)     → list[Participant]
load_observations(data_dir)     → list[Observation]
load_protocol_rules(data_dir)   → list[ProtocolRule]
load_all_data(data_dir)         → dict with all five lists

All functions accept an optional ``data_dir`` Path argument.
The default points to  src/data/  relative to this file's location,
so the loader works out-of-the-box when run from anywhere inside
the project tree.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import (
    Observation,
    Participant,
    ProtocolRule,
    Site,
    Trial,
)

# ---------------------------------------------------------------------------
# Default data directory
# ---------------------------------------------------------------------------

# Resolve src/data/ relative to the location of this source file so that
# calling code does not need to know the project layout.
#
#   loader.py  lives at:  src/protocol/loader.py
#   data root  lives at:  src/data/
#
_THIS_FILE = Path(__file__).resolve()          # …/src/protocol/loader.py
_SRC_DIR   = _THIS_FILE.parent.parent          # …/src/
_DEFAULT_DATA_DIR = _SRC_DIR / "data"          # …/src/data/


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def load_trials(data_dir: Path | None = None) -> list[Trial]:
    """Load trial records from ``synthetic/trials.csv``.

    Args:
        data_dir: Root data directory.  Defaults to ``src/data/``.

    Returns:
        A list of :class:`~src.protocol.models.Trial` instances,
        one per row in the CSV.

    Raises:
        FileNotFoundError: If ``trials.csv`` does not exist.
        pydantic.ValidationError: If a row fails model validation.
    """
    path = _resolve(data_dir) / "synthetic" / "trials.csv"
    rows = _read_csv(path)
    return [Trial(**row) for row in rows]


def load_sites(data_dir: Path | None = None) -> list[Site]:
    """Load site records from ``synthetic/sites.csv``.

    ``trial_id`` is stored as a plain string in the CSV; no type
    conversion is needed beyond what Pydantic performs at parse time.

    Args:
        data_dir: Root data directory.  Defaults to ``src/data/``.

    Returns:
        A list of :class:`~src.protocol.models.Site` instances.

    Raises:
        FileNotFoundError: If ``sites.csv`` does not exist.
        pydantic.ValidationError: If a row fails model validation.
    """
    path = _resolve(data_dir) / "synthetic" / "sites.csv"
    rows = _read_csv(path)
    return [Site(**row) for row in rows]


def load_participants(data_dir: Path | None = None) -> list[Participant]:
    """Load participant records from ``synthetic/participants.csv``.

    ``enrollment_date`` is stored in the CSV as an ISO 8601 string
    (``YYYY-MM-DD``); Pydantic converts it automatically to a
    ``datetime.date`` object during model construction.

    Args:
        data_dir: Root data directory.  Defaults to ``src/data/``.

    Returns:
        A list of :class:`~src.protocol.models.Participant` instances.

    Raises:
        FileNotFoundError: If ``participants.csv`` does not exist.
        pydantic.ValidationError: If a row fails model validation.
    """
    path = _resolve(data_dir) / "synthetic" / "participants.csv"
    rows = _read_csv(path)
    # age is read as a string from CSV — cast to int before Pydantic sees it.
    # trial_id is a plain string — no conversion needed.
    for row in rows:
        row["age"] = int(row["age"])
    return [Participant(**row) for row in rows]


def load_observations(data_dir: Path | None = None) -> list[Observation]:
    """Load observation records from ``synthetic/observations.csv``.

    ``expected_day`` and ``actual_day`` are stored as plain integers in
    the CSV.  ``actual_day`` may be empty (blank cell) which is treated
    as ``None`` (visit not yet recorded).

    Args:
        data_dir: Root data directory.  Defaults to ``src/data/``.

    Returns:
        A list of :class:`~src.protocol.models.Observation` instances.

    Raises:
        FileNotFoundError: If ``observations.csv`` does not exist.
        pydantic.ValidationError: If a row fails model validation.
    """
    path = _resolve(data_dir) / "synthetic" / "observations.csv"
    rows = _read_csv(path)
    for row in rows:
        row["expected_day"] = int(row["expected_day"])
        # actual_day is optional — blank cell → None
        raw_actual = row.get("actual_day", "").strip()
        row["actual_day"] = int(raw_actual) if raw_actual != "" else None
        # dose_mg is optional — blank cell → None; present → float
        raw_dose = row.get("dose_mg", "").strip()
        row["dose_mg"] = float(raw_dose) if raw_dose != "" else None
        # lab_value is optional — blank cell → None; present → float
        raw_lab = row.get("lab_value", "").strip()
        row["lab_value"] = float(raw_lab) if raw_lab != "" else None
        # lab_unit is optional — blank cell → None
        raw_unit = row.get("lab_unit", "").strip()
        row["lab_unit"] = raw_unit if raw_unit != "" else None
    return [Observation(**row) for row in rows]


def load_protocol_rules(data_dir: Path | None = None) -> list[ProtocolRule]:
    """Load protocol rules from ``schemas/protocol_rules.json``.

    The JSON file must conform to the schema defined in
    ``schemas/protocol_schema.json``.  The top-level ``rules`` array
    is extracted and each element is converted to a
    :class:`~src.protocol.models.ProtocolRule` instance.

    Args:
        data_dir: Root data directory.  Defaults to ``src/data/``.

    Returns:
        A list of :class:`~src.protocol.models.ProtocolRule` instances.

    Raises:
        FileNotFoundError: If ``protocol_rules.json`` does not exist.
        KeyError: If the JSON document has no ``rules`` key.
        pydantic.ValidationError: If a rule object fails model validation.
    """
    path = _resolve(data_dir) / "schemas" / "protocol_rules.json"
    _require_file(path)

    with open(path, encoding="utf-8") as fh:
        document: dict[str, Any] = json.load(fh)

    if "rules" not in document:
        raise KeyError(
            f"'rules' key not found in {path}. "
            "The protocol rules file must contain a top-level 'rules' array."
        )

    return [ProtocolRule(**rule) for rule in document["rules"]]


def load_all_data(data_dir: Path | None = None) -> dict[str, list]:
    """Load all five datasets in one call.

    Convenience wrapper that calls each individual loader and returns
    a single dictionary.  Useful for bootstrapping other modules:

    .. code-block:: python

        from src.protocol.loader import load_all_data

        data = load_all_data()
        trials        = data["trials"]
        sites         = data["sites"]
        participants  = data["participants"]
        observations  = data["observations"]
        rules         = data["protocol_rules"]

    Args:
        data_dir: Root data directory.  Defaults to ``src/data/``.

    Returns:
        Dictionary with keys:
        ``"trials"``, ``"sites"``, ``"participants"``,
        ``"observations"``, ``"protocol_rules"``.
        Each value is the typed list returned by the corresponding
        individual loader.

    Raises:
        FileNotFoundError: If any required data file is missing.
        pydantic.ValidationError: If any record fails model validation.
    """
    resolved = _resolve(data_dir)
    return {
        "trials":         load_trials(resolved),
        "sites":          load_sites(resolved),
        "participants":   load_participants(resolved),
        "observations":   load_observations(resolved),
        "protocol_rules": load_protocol_rules(resolved),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve(data_dir: Path | None) -> Path:
    """Return *data_dir* if provided, otherwise the package default."""
    return Path(data_dir) if data_dir is not None else _DEFAULT_DATA_DIR


def _require_file(path: Path) -> None:
    """Raise a clear ``FileNotFoundError`` if *path* does not exist."""
    if not path.exists():
        raise FileNotFoundError(
            f"Required data file not found: {path}\n"
            "Run the data generator first:\n"
            "    python -m src.protocol.generator"
        )


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file and return a list of row dicts (all values are strings).

    Args:
        path: Path to the CSV file.

    Returns:
        List of dicts, one per data row, keyed by the header names.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    _require_file(path)
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


# ---------------------------------------------------------------------------
# Command-line entry point — quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    data = load_all_data()
    print("Loaded data summary")
    print("-------------------")
    print(f"  trials         : {len(data['trials'])}")
    print(f"  sites          : {len(data['sites'])}")
    print(f"  participants   : {len(data['participants'])}")
    print(f"  observations   : {len(data['observations'])}")
    print(f"  protocol rules : {len(data['protocol_rules'])}")
