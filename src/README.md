bob-ai-hackathon-clinova/
│
├── src/
│   ├── backend/
│   │   ├── app.py
│   │   ├── config.py
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── protocol_routes.py
│   │   │   ├── patient_routes.py
│   │   │   ├── deviation_routes.py
│   │   │   ├── risk_routes.py
│   │   │   ├── capa_routes.py
│   │   │   └── dashboard_routes.py
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── patient.py
│   │   │   ├── protocol.py
│   │   │   ├── site.py
│   │   │   ├── deviation.py
│   │   │   ├── risk_score.py
│   │   │   └── capa.py
│   │   │
│   │   ├── services/
│   │   │   ├── protocol_engine.py
│   │   │   ├── deviation_detector.py
│   │   │   ├── severity_classifier.py
│   │   │   ├── site_risk_engine.py
│   │   │   ├── capa_generator.py
│   │   │   └── report_generator.py
│   │   │
│   │   ├── utils/
│   │   │   ├── validators.py
│   │   │   ├── date_utils.py
│   │   │   └── audit_logger.py
│   │   │
│   │   └── database/
│   │       ├── db.py
│   │       └── migrations/
│   │
│   ├── frontend/
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── dashboard.html
│   │   │   ├── protocols.html
│   │   │   ├── patients.html
│   │   │   ├── deviations.html
│   │   │   ├── site_risk.html
│   │   │   ├── capa_reports.html
│   │   │   └── reports.html
│   │   │
│   │   └── static/
│   │       ├── css/
│   │       │   └── style.css
│   │       ├── js/
│   │       │   ├── dashboard.js
│   │       │   ├── deviations.js
│   │       │   ├── site_risk.js
│   │       │   └── capa.js
│   │       └── images/
│   │
│   └── shared/
│       ├── constants.py
│       └── schemas.py
│
├── data/
│   ├── sample_patients.csv
│   ├── sample_protocol.json
│   └── sample_sites.csv
│
├── tests/
│   ├── test_protocol_engine.py
│   ├── test_deviation_detector.py
│   ├── test_severity_classifier.py
│   └── test_risk_engine.py
│
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── run.py