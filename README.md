# 🚀 CliNova — Clinical Trial Risk Monitor & Protocol Deviation Detector

> **An AI-powered platform for detecting clinical trial protocol deviations, assessing severity and site-level risk, and generating actionable CAPA recommendations.**

---

## 👥 Team

| Field         | Value                                             |
| ------------- | ------------------------------------------------- |
| **Team Name** | **CliNova**                                       |
| **Track**     | **AI**                                            |
| **Team Lead** | **Mahi Surani**                                   |
| **Members**   | **Mahi Surani, Khushi Donda, Ritu Gajera, Nensi** |

---

## 🎯 Problem Statement

Clinical trial teams must continuously monitor participant data to ensure that visits, eligibility criteria, dosing activities, laboratory observations, and other clinical activities comply with the approved study protocol. Manual monitoring is time-consuming and can make it difficult to identify important deviations and high-risk clinical sites quickly.

**CliNova** addresses this challenge by automatically comparing clinical trial data against structured protocol rules, detecting deviations, classifying their severity, and identifying site-level risk.

---

## 💡 Solution

**CliNova** is an end-to-end clinical trial risk monitoring platform that converts protocol requirements into structured, machine-checkable rules and validates clinical trial data against those rules.

The platform detects protocol deviations, evaluates their severity, calculates site-level risk scores, and uses IBM AI capabilities to provide understandable explanations and CAPA-oriented recommendations for remediation.

---

## ✨ Key Features

* **Protocol Rule Engine:** Represents clinical trial requirements as structured rules containing expected values, acceptable windows, and validation conditions.

* **Clinical Data Validation:** Validates trial, site, participant, observation, and protocol data before processing.

* **Automated Protocol Deviation Detection:** Identifies issues such as delayed visits, eligibility violations, dosing deviations, and laboratory-related deviations.

* **Deviation Severity Classification:** Categorizes detected deviations according to their potential impact and priority.

* **Site Risk Scoring:** Aggregates deviation information to calculate and monitor risk at the clinical-site level.

* **IBM AI-Powered Explanations:** Generates human-readable explanations for detected risks and deviations.

* **CAPA Recommendations:** Provides corrective and preventive action recommendations based on identified issues.

* **Risk Monitoring Dashboard:** Presents deviations, severity, site risk, and AI-generated insights through an interactive dashboard.

* **Synthetic Clinical Trial Data:** Provides reproducible trial, site, participant, observation, and protocol-rule data for testing and demonstration.

---

## 🛠️ Tech Stack

| Category             | Technologies                                   |
| -------------------- | ---------------------------------------------- |
| **Languages**        | Python                                         |
| **Frameworks**       | Streamlit, Pydantic                            |
| **AI / ML**          | IBM watsonx.ai, rule-based clinical monitoring |
| **IBM Technologies** | IBM Bob, IBM watsonx.ai                        |
| **Data Formats**     | JSON, CSV                                      |
| **Testing**          | Pytest                                         |
| **CI/CD**            | GitHub Actions                                 |
| **Version Control**  | Git, GitHub                                    |

---

## 📁 Repository Structure

```text
├── .github/
│   └── workflows/
│       └── validate.yml
│
├── src/
│   ├── ai/
│   │   ├── capa.py
│   │   ├── explainer.py
│   │   ├── models.py
│   │   ├── report.py
│   │   └── watsonx.py
│   │
│   ├── dashboard/
│   │   └── app.py
│   │
│   ├── data/
│   │   ├── schemas/
│   │   └── synthetic/
│   │
│   ├── deviation/
│   │   └── detector.py
│   │
│   ├── protocol/
│   │   ├── generator.py
│   │   ├── interface.py
│   │   ├── loader.py
│   │   ├── models.py
│   │   └── validator.py
│   │
│   ├── risk/
│   │   └── scorer.py
│   │
│   └── tests/
│
├── docs/
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   └── setup-guide.md
│
├── demo/
│   ├── screenshots/
│   ├── demo-video-link.txt
│   └── live-demo-url.txt
│
├── presentation/
│
├── generate_data.py
├── submission.yaml
└── README.md
```

---

## ⚡ How to Run

### 1. Clone the repository

```bash
git clone https://github.com/mahisurani06/bob-ai-hackathon-clinova.git
cd bob-ai-hackathon-clinova
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the virtual environment

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
pip install -r src/requirements.txt
```

### 5. Generate the synthetic clinical dataset

```bash
python generate_data.py
```

### 6. Configure environment variables

Copy the environment template:

```powershell
Copy-Item src\.env.example src\.env
```

Add the required IBM/watsonx configuration to `src/.env`.

> **Do not commit API keys, tokens, or other secrets to GitHub.**

### 7. Start the application

```bash
streamlit run src/dashboard/app.py
```

The CliNova dashboard will then be available through the local Streamlit URL displayed in the terminal.

---

## 🧪 Testing

Run the complete automated test suite:

```bash
pytest
```

The repository also includes GitHub Actions validation to automatically check the project.

---

## 🔄 System Workflow

```text
Clinical Trial Protocol
          │
          ▼
    Protocol Rules
          │
          ▼
   Clinical Trial Data
          │
          ▼
    Data Validation
          │
          ▼
 Protocol Deviation Detection
          │
          ▼
 Severity Classification
          │
          ▼
    Site Risk Scoring
          │
          ▼
   IBM AI Explanation
          │
          ▼
 CAPA Recommendations
          │
          ▼
    Risk Dashboard
```

---

## 🖥️ Demo

| Artifact            | Link                                                     |
| ------------------- | -------------------------------------------------------- |
| 📹 **Demo Video**   | [See demo/demo-video-link.txt](demo/demo-video-link.txt) |
| 🌐 **Live Demo**    | [See demo/live-demo-url.txt](demo/live-demo-url.txt)     |
| 🖼️ **Screenshots** | [See demo/screenshots/](demo/screenshots/)               |
| 📊 **Presentation** | [See presentation/](presentation/)                       |

---

## ⚠️ Known Limitations

* The current demonstration uses **synthetic clinical trial data** rather than real patient records.
* The current protocol engine supports structured protocol rules rather than automatically converting every type of natural-language clinical protocol into machine-readable rules.
* AI-generated explanations and CAPA recommendations should be reviewed by qualified clinical personnel before being used for real clinical or regulatory decisions.
* The system is a **clinical trial monitoring and decision-support platform** and does not replace formal clinical oversight.
* A production deployment would require additional enterprise capabilities such as authentication, role-based access control, audit logging, secure infrastructure, and compliance controls.

---

## 🏅 What We're Most Proud Of

The strongest aspect of **CliNova** is that it provides an end-to-end clinical trial monitoring workflow rather than treating protocol deviation detection as an isolated feature.

Our complete pipeline connects:

**Protocol → Structured Rules → Clinical Data → Validation → Deviation Detection → Severity → Site Risk → IBM AI Explanation → CAPA Recommendations**

This allows clinical operations teams to move from simply identifying a protocol violation to understanding **what happened, how serious it is, where risk is concentrated, and what corrective or preventive action can be considered**.

We are particularly proud of combining a deterministic rule-based foundation with IBM AI-assisted explanations and recommendations, providing both structured validation and human-readable insights.

---

## 🚀 Future Enhancements

* Natural-language protocol ingestion using AI.
* Integration with real clinical trial data sources and EDC systems.
* Predictive site-risk analysis using historical deviation patterns.
* Advanced trend detection for recurring deviations.
* Role-based dashboards for investigators and clinical operations teams.
* Comprehensive audit logging.
* Enterprise authentication and authorization.
* Exportable regulatory and compliance reports.
* Continuous monitoring of incoming clinical trial data.

---

## 📄 Documentation

Detailed documentation is available in the `docs/` directory:

* [Problem Statement](docs/problem-statement.md)
* [Solution Overview](docs/solution-overview.md)
* [Architecture](docs/architecture.md)
* [Setup Guide](docs/setup-guide.md)

---

## 🤝 Team

**CliNova** was developed by a four-member team for the **IBM Bob AI Hackathon — AI Track**.

The team combines protocol and clinical-data engineering, deviation detection, risk analytics, dashboard development, and IBM AI integration to deliver an end-to-end clinical trial monitoring solution.
