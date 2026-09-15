# src/protocol/constants.py
# Clinical Trial Risk Monitor — Protocol Constants (Member 1)
#
# Shared protocol constants used by both the protocol package and
# downstream modules (risk scorer, dashboard, AI advisor).
#
# Centralising these values here avoids duplicating them in scorer.py
# and prevents circular imports when both packages reference the same value.

# The ordered visit sequence — used as a temporal proxy throughout the system.
# Earlier index = older visit; later index = more recent visit.
VISIT_SEQUENCE: list[str] = ["BASELINE", "WEEK_4", "WEEK_8", "WEEK_12"]
