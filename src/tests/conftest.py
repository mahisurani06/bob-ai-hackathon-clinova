# src/tests/conftest.py
#
# Pytest configuration shared by all tests in the test suite.
#
# What this file does
# -------------------
# Automatically generates the synthetic dataset before any test runs,
# if the data files are not already present.
#
# This means developers (and CI) can run `pytest` from a fresh checkout
# without having to manually run the generator first.
#
# The generator is deterministic (seed=42), so re-running it always
# produces the same files.
#
# Completeness check
# ------------------
# We verify BOTH observations.csv (CSVs) AND protocol_rules.json (schemas)
# because generate_dataset() writes files into two sibling directories:
#
#   src/data/synthetic/   ← CSV files
#   src/data/schemas/     ← protocol_rules.json
#
# Checking only observations.csv previously caused tests that call
# load_project_data() to fail with FileNotFoundError on protocol_rules.json
# when the schemas/ directory was absent.

from pathlib import Path

from src.protocol.generator import generate_dataset

# Resolve src/data/ relative to this conftest.py's location.
# conftest.py lives at:  src/tests/conftest.py
# data root lives at:    src/data/
_TESTS_DIR     = Path(__file__).resolve().parent        # …/src/tests/
_SRC_DIR       = _TESTS_DIR.parent                      # …/src/
_DATA_DIR      = _SRC_DIR / "data"                      # …/src/data/
_SYNTHETIC_DIR = _DATA_DIR / "synthetic"                # …/src/data/synthetic/
_SCHEMAS_DIR   = _DATA_DIR / "schemas"                  # …/src/data/schemas/


def pytest_configure(config) -> None:
    """Called by pytest before collecting tests.

    If any required data file is missing (e.g. on a fresh checkout),
    generate the full dataset now so every test that depends on real data
    can run.

    The completeness check covers:
    - observations.csv  (synthetic CSV data)
    - protocol_rules.json  (schemas directory)

    Both files are produced by a single generate_dataset() call.
    """
    observations_csv   = _SYNTHETIC_DIR / "observations.csv"
    protocol_rules_json = _SCHEMAS_DIR  / "protocol_rules.json"

    if not observations_csv.exists() or not protocol_rules_json.exists():
        print(
            "\n[conftest] Synthetic dataset not found — generating now "
            f"(output: {_SYNTHETIC_DIR}) …"
        )
        generate_dataset(
            output_dir=str(_SYNTHETIC_DIR),
            num_participants=20,
            seed=42,
        )
        print("[conftest] Dataset ready.\n")
