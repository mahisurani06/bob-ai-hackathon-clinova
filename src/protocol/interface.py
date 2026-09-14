"""
interface.py — Public integration boundary for the Protocol & Clinical Data module.

This is the ONLY file that other team members need to import from Member 1's
module.  It hides all internal details (file paths, CSV parsing, validation
logic) behind a clean, typed API.

Intended usage (Member 2, 3, 4, 5)
------------------------------------
    from src.protocol.interface import load_project_data

    data           = load_project_data()
    trials         = data["trials"]
    sites          = data["sites"]
    participants   = data["participants"]
    observations   = data["observations"]
    protocol_rules = data["protocol_rules"]

Or use the individual convenience getters::

    from src.protocol.interface import get_observations, get_protocol_rules

    observations   = get_observations()
    protocol_rules = get_protocol_rules()

All returned objects are validated Pydantic model instances (see
``src/protocol/models.py``).  If the dataset fails validation the
functions raise ``DataValidationError`` with a clear message listing
every problem found.

What this module does NOT do
-----------------------------
- It does not detect protocol deviations.
- It does not classify deviations as Major / Minor / Administrative.
- It does not score site risk.
- It does not call watsonx or any AI service.
- It does not implement CAPA logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader    import load_all_data
from .models    import Observation, Participant, ProtocolRule, Site, Trial
from .validator import validate_all


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class DataValidationError(ValueError):
    """Raised when the loaded dataset fails one or more validation checks.

    Attributes:
        errors:   List of fatal validation error messages.
        warnings: List of non-fatal warning messages.
    """

    def __init__(self, errors: list[str], warnings: list[str]) -> None:
        self.errors   = errors
        self.warnings = warnings
        error_block   = "\n  ".join(errors)
        super().__init__(
            f"Dataset failed validation with {len(errors)} error(s):\n  {error_block}"
        )


# ---------------------------------------------------------------------------
# Default data directory
# ---------------------------------------------------------------------------

# Resolve src/data/ relative to this source file so the interface works
# regardless of the caller's working directory.
#
#   interface.py  →  src/protocol/interface.py
#   data root     →  src/data/
#
_THIS_FILE       = Path(__file__).resolve()
_SRC_DIR         = _THIS_FILE.parent.parent        # …/src/
_DEFAULT_DATA_DIR = _SRC_DIR / "data"              # …/src/data/


# ---------------------------------------------------------------------------
# Primary API
# ---------------------------------------------------------------------------

def load_project_data(data_dir: Path | None = None) -> dict[str, list]:
    """Load, validate, and return the complete clinical-trial dataset.

    This is the main entry point for all other modules.  Internally it:

    1. Calls :func:`~src.protocol.loader.load_all_data` to read all
       CSV and JSON files into typed Pydantic model instances.
    2. Calls :func:`~src.protocol.validator.validate_all` to check
       referential integrity and data-quality constraints.
    3. Raises :class:`DataValidationError` if any validation errors are
       found, so downstream code never works with corrupt data.

    Args:
        data_dir: Optional override for the root data directory.
                  Defaults to ``src/data/`` (resolved relative to this
                  file, so it works from any working directory).

    Returns:
        A dictionary with five keys, each holding a list of validated
        Pydantic model instances::

            {
                "trials":         list[Trial],
                "sites":          list[Site],
                "participants":   list[Participant],
                "observations":   list[Observation],
                "protocol_rules": list[ProtocolRule],
            }

    Raises:
        DataValidationError: If the dataset fails any validation check.
        FileNotFoundError:   If a required CSV or JSON file is missing.
    """
    resolved = Path(data_dir) if data_dir is not None else _DEFAULT_DATA_DIR

    data   = load_all_data(resolved)
    result = validate_all(data)

    if not result["valid"]:
        raise DataValidationError(
            errors=result["errors"],
            warnings=result["warnings"],
        )

    return data


# ---------------------------------------------------------------------------
# Individual convenience getters
# ---------------------------------------------------------------------------

def get_trials(data_dir: Path | None = None) -> list[Trial]:
    """Return the list of :class:`~src.protocol.models.Trial` objects.

    Loads and validates the full dataset, then returns only the trials.
    Use :func:`load_project_data` when you need more than one entity
    type to avoid loading the files multiple times.

    Args:
        data_dir: Optional data root override.

    Returns:
        ``list[Trial]``
    """
    return load_project_data(data_dir)["trials"]


def get_sites(data_dir: Path | None = None) -> list[Site]:
    """Return the list of :class:`~src.protocol.models.Site` objects.

    Args:
        data_dir: Optional data root override.

    Returns:
        ``list[Site]``
    """
    return load_project_data(data_dir)["sites"]


def get_participants(data_dir: Path | None = None) -> list[Participant]:
    """Return the list of :class:`~src.protocol.models.Participant` objects.

    Args:
        data_dir: Optional data root override.

    Returns:
        ``list[Participant]``
    """
    return load_project_data(data_dir)["participants"]


def get_observations(data_dir: Path | None = None) -> list[Observation]:
    """Return the list of :class:`~src.protocol.models.Observation` objects.

    These are the records that Member 2's deviation detector will inspect.
    Each observation has a ``visit_type``, ``expected_day``, and
    ``actual_day`` field.  Member 2 should compare ``actual_day`` against
    the matching :class:`~src.protocol.models.ProtocolRule` to determine
    whether a deviation occurred.

    Args:
        data_dir: Optional data root override.

    Returns:
        ``list[Observation]``
    """
    return load_project_data(data_dir)["observations"]


def get_protocol_rules(data_dir: Path | None = None) -> list[ProtocolRule]:
    """Return the list of :class:`~src.protocol.models.ProtocolRule` objects.

    These rules define what the trial protocol requires.  Member 2's
    deviation detector matches each observation against the rule with
    the same ``visit_type`` and ``rule_type == 'VISIT_WINDOW'`` to
    decide whether the visit occurred within the allowed window.

    Args:
        data_dir: Optional data root override.

    Returns:
        ``list[ProtocolRule]``
    """
    return load_project_data(data_dir)["protocol_rules"]


# ---------------------------------------------------------------------------
# Command-line entry point — integration smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Loading and validating project data via interface.py ...\n")

    data = load_project_data()

    counts: dict[str, Any] = {
        "trials":         len(data["trials"]),
        "sites":          len(data["sites"]),
        "participants":   len(data["participants"]),
        "observations":   len(data["observations"]),
        "protocol_rules": len(data["protocol_rules"]),
    }

    print("Entity counts")
    print("-------------")
    for entity, count in counts.items():
        print(f"  {entity:<16}: {count}")

    print("\nSample Trial          :", data["trials"][0])
    print("Sample Site           :", data["sites"][0])
    print("Sample Participant    :", data["participants"][0])
    print("Sample Observation    :", data["observations"][0])
    print("Sample ProtocolRule   :", data["protocol_rules"][0])
    print("\nInterface is ready for use by other modules.")
