# src/deviation/__init__.py
# Clinical Trial Risk Monitor — Deviation Detection + Severity Classification (Member 2)
#
# This package detects protocol deviations in clinical trial observations
# and classifies each deviation by severity (Administrative / Minor / Major).
#
# Intended usage by other modules:
#
#     from src.deviation import detect_deviations, DeviationRecord
#
#     deviations = detect_deviations(
#         observations   = data["observations"],
#         protocol_rules = data["protocol_rules"],
#     )
#
# Public surface:
#   models.py      — DeviationRecord Pydantic model (output contract)
#   classifier.py  — classify_severity() and severity thresholds
#   detector.py    — detect_deviations() main entry point

# Output data model — import this when you need the DeviationRecord type
from .models import DeviationRecord, SeverityLevel

# Classifier — import when you need to re-classify or inspect thresholds
from .classifier import (
    ADMIN_MAX_OVERSHOOT,
    MINOR_MAX_OVERSHOOT,
    classify_severity,
)

# Detector — main entry point for the whole module
from .detector import detect_deviations

__all__ = [
    # models
    "DeviationRecord",
    "SeverityLevel",
    # classifier
    "classify_severity",
    "ADMIN_MAX_OVERSHOOT",
    "MINOR_MAX_OVERSHOOT",
    # detector
    "detect_deviations",
]
