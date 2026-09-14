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

from pathlib import Path

from src.protocol.generator import generate_dataset

# Resolve src/data/synthetic/ relative to this conftest.py's location.
# conftest.py lives at:  src/tests/conftest.py
# data dir lives at:     src/data/synthetic/
_TESTS_DIR    = Path(__file__).resolve().parent        # …/src/tests/
_SRC_DIR      = _TESTS_DIR.parent                      # …/src/
_SYNTHETIC_DIR = _SRC_DIR / "data" / "synthetic"       # …/src/data/synthetic/


def pytest_configure(config) -> None:
    """Called by pytest before collecting tests.

    If the synthetic data files are missing (e.g. on a fresh checkout),
    generate them now so every test that depends on real data can run.
    """
    required_file = _SYNTHETIC_DIR / "observations.csv"

    if not required_file.exists():
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
