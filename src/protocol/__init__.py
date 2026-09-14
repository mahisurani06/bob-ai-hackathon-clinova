# src/protocol/__init__.py
# Clinical Trial Risk Monitor — Protocol Data Layer (Member 1)
#
# This package defines the shared data models and utilities for
# loading, validating, and exposing clinical trial data to other
# modules in the project.
#
# Public surface (all steps complete):
#   models.py           — Pydantic data models (shared contract)
#   generator.py        — synthetic dataset generator
#   loader.py           — CSV/JSON → typed model instances
#   validator.py        — data-quality and referential-integrity checks
#   interface.py        — clean public API for other team members

# Data models — shared contract across the whole project
from .models import (
    Observation,
    Participant,
    ProtocolRule,
    Site,
    Trial,
)

# Shared protocol constants
from .constants import VISIT_SEQUENCE

# Public API — the only import other modules need
from .interface import (
    DataValidationError,
    get_observations,
    get_participants,
    get_protocol_rules,
    get_sites,
    get_trials,
    load_project_data,
)

__all__ = [
    # models
    "Trial",
    "Site",
    "Participant",
    "Observation",
    "ProtocolRule",
    # constants
    "VISIT_SEQUENCE",
    # interface
    "load_project_data",
    "get_trials",
    "get_sites",
    "get_participants",
    "get_observations",
    "get_protocol_rules",
    "DataValidationError",
]
