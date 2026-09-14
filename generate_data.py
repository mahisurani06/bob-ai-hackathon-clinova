"""
Run from the bob-ai-hackathon-clinova directory:
    python generate_data.py

This will write:
  src/data/synthetic/sites.csv
  src/data/synthetic/trials.csv
  src/data/synthetic/participants.csv
  src/data/synthetic/observations.csv
  src/data/schemas/protocol_rules.json
"""
import random, csv, json, pathlib
from datetime import date, timedelta

BASE = pathlib.Path(__file__).parent
SYNTHETIC_DIR = BASE / "src/data/synthetic"
SCHEMAS_DIR   = BASE / "src/data/schemas"

# ─── RNG ──────────────────────────────────────────────────────────────────────
rng = random.Random(42)

# ─── Reference data ───────────────────────────────────────────────────────────
SITES = [
    ("S001", "Apollo Hospitals Chennai",       "India", "ACTIVE"),
    ("S002", "Fortis Memorial Research Inst.", "India", "ACTIVE"),
    ("S003", "AIIMS New Delhi",                "India", "ACTIVE"),
    ("S004", "Narayana Health Bangalore",      "India", "ACTIVE"),
]
SITE_IDS = [s[0] for s in SITES]
GENDERS  = ["MALE", "FEMALE", "OTHER"]
STATUSES = ["ENROLLED", "COMPLETED", "WITHDRAWN", "SCREEN_FAIL"]
VISIT_SCHEDULE = [
    ("BASELINE",  0,  3),
    ("WEEK_4",   28,  3),
    ("WEEK_8",   56,  3),
    ("WEEK_12",  84,  3),
]

# ─── Participants (seed=42, calls in order) ───────────────────────────────────
participants = []
for i in range(1, 21):
    pid    = f"P{i:03d}"
    sid    = SITE_IDS[(i - 1) % 4]
    age    = rng.randint(18, 75)
    gender = rng.choices(GENDERS, weights=[0.48, 0.48, 0.04])[0]
    enroll = date(2023, 1, 1) + timedelta(days=rng.randint(0, 180))
    status = rng.choices(STATUSES, weights=[0.55, 0.30, 0.10, 0.05])[0]
    participants.append(dict(patient_id=pid, site_id=sid, age=age,
                             gender=gender,
                             enrollment_date=enroll.strftime("%Y-%m-%d"),
                             status=status))

# ─── Observations ─────────────────────────────────────────────────────────────
observations = []
obs_id = 1
for p in participants:
    for visit_type, expected_day, window in VISIT_SCHEDULE:
        make_anomaly = rng.random() < 0.08
        if make_anomaly:
            direction  = rng.choice([-1, 1])
            actual_day = expected_day + direction * (window + 7)
        else:
            actual_day = expected_day + rng.randint(-window, window)
        observations.append(dict(
            observation_id=f"OBS-{obs_id:04d}",
            patient_id=p["patient_id"],
            visit_type=visit_type,
            expected_day=expected_day,
            actual_day=actual_day,
            is_anomaly=make_anomaly,
        ))
        obs_id += 1

# ─── protocol_rules.json ──────────────────────────────────────────────────────
PROTOCOL_RULES = {
    "rules": [
        {"rule_id": "RULE-001", "rule_type": "VISIT_WINDOW",
         "description": "BASELINE visit must occur within ±3 days of Day 0.",
         "visit_type": "BASELINE", "expected_value": "0", "allowed_window": 3},
        {"rule_id": "RULE-002", "rule_type": "VISIT_WINDOW",
         "description": "WEEK_4 visit must occur within ±3 days of Day 28.",
         "visit_type": "WEEK_4", "expected_value": "28", "allowed_window": 3},
        {"rule_id": "RULE-003", "rule_type": "VISIT_WINDOW",
         "description": "WEEK_8 visit must occur within ±3 days of Day 56.",
         "visit_type": "WEEK_8", "expected_value": "56", "allowed_window": 3},
        {"rule_id": "RULE-004", "rule_type": "VISIT_WINDOW",
         "description": "WEEK_12 visit must occur within ±3 days of Day 84.",
         "visit_type": "WEEK_12", "expected_value": "84", "allowed_window": 3},
        {"rule_id": "RULE-005", "rule_type": "ELIGIBILITY",
         "description": "Patient must be at least 18 years old at enrollment.",
         "visit_type": None, "expected_value": "18", "allowed_window": None},
        {"rule_id": "RULE-006", "rule_type": "ELIGIBILITY",
         "description": "Patient must be no older than 75 years old at enrollment.",
         "visit_type": None, "expected_value": "75", "allowed_window": None},
        {"rule_id": "RULE-007", "rule_type": "DOSING",
         "description": "Study drug must be administered within 2 days of scheduled visit.",
         "visit_type": "WEEK_4", "expected_value": "28", "allowed_window": 2},
        {"rule_id": "RULE-008", "rule_type": "LAB_RANGE",
         "description": "Hemoglobin must be within normal range at BASELINE.",
         "visit_type": "BASELINE", "expected_value": "13", "allowed_window": None},
    ]
}

# ─── Write helpers ────────────────────────────────────────────────────────────
def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

# ─── Write all files ──────────────────────────────────────────────────────────
write_csv(SYNTHETIC_DIR / "sites.csv",
          [dict(site_id=s[0], site_name=s[1], country=s[2], status=s[3]) for s in SITES],
          ["site_id", "site_name", "country", "status"])

write_csv(SYNTHETIC_DIR / "trials.csv",
          [dict(trial_id="TRIAL-001", trial_name="Demo Clinical Trial",
                version="1.0", status="ACTIVE")],
          ["trial_id", "trial_name", "version", "status"])

write_csv(SYNTHETIC_DIR / "participants.csv", participants,
          ["patient_id", "site_id", "age", "gender", "enrollment_date", "status"])

write_csv(SYNTHETIC_DIR / "observations.csv", observations,
          ["observation_id", "patient_id", "visit_type",
           "expected_day", "actual_day", "is_anomaly"])

SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
with open(SCHEMAS_DIR / "protocol_rules.json", "w") as f:
    json.dump(PROTOCOL_RULES, f, indent=2)

print(f"✓ sites.csv          ({len(SITES)} rows)")
print(f"✓ trials.csv         (1 row)")
print(f"✓ participants.csv   ({len(participants)} rows)")
print(f"✓ observations.csv   ({len(observations)} rows)")
print(f"✓ protocol_rules.json (8 rules)")
print("\nAll files written to bob-ai-hackathon-clinova/src/data/")
