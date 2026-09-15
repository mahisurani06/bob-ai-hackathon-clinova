# 🏥 CliNova — Clinical Trial Risk Monitor & Protocol Deviation Detector

> **AI-powered clinical trial monitoring system that detects protocol deviations, classifies their severity, evaluates site-level risk, and generates CAPA-ready recommendations.**

---

## 👥 Team

| **Field**     | **Value**                                         |
| ------------- | ------------------------------------------------- |
| **Team Name** | **CliNova**                                       |
| **Track**     | **AI**                                            |
| **Team Lead** | **Mahi Surani**                                   |
| **Members**   | **Mahi Surani, Khushi Donda, Ritu Gajera, Nensi Shingala** |

---

## 🎯 Problem Statement

Clinical trial teams must continuously verify that participant activities, visits, laboratory observations, eligibility criteria, and dosing events follow the approved study protocol. Manual monitoring is time-consuming and makes it difficult to identify recurring deviations and high-risk clinical sites early.

**CliNova** addresses this problem by automatically comparing structured clinical trial data against protocol-defined rules, identifying deviations, classifying their severity, and providing actionable risk and remediation insights.

---

## 💡 Solution

**CliNova** is an AI-powered clinical trial risk monitoring platform that transforms protocol requirements and clinical observations into structured, machine-checkable rules. The system automatically detects deviations such as missed or delayed visits, eligibility violations, dosing issues, and laboratory-related deviations.

Detected deviations are classified by severity and aggregated into site-level risk scores. IBM AI capabilities are then used to generate understandable explanations and CAPA-oriented recommendations, helping clinical operations teams prioritize the issues that require attention.

---

## ✨ Key Features

* **Protocol Rule Engine:** Converts clinical trial protocol requirements into structured rules containing expected values, acceptable windows, and validation conditions.

* **Clinical Data Validation:** Validates trials, sites, participants, observations, and protocol rules before they enter the monitoring pipeline.

* **Automated Protocol Deviation Detection:** Compares participant clinical events against protocol-defined visit windows, eligibility requirements, dosing schedules, and laboratory requirements.

* **Deviation Severity Classification:** Categorizes detected deviations according to their potential impact and helps prioritize critical issues.

* **Site-Level Risk Scoring:** Aggregates deviation patterns to calculate risk scores for individual clinical sites.

* **AI-Powered Explanations:** Uses IBM AI capabilities to explain detected risks in a human-readable form rather than presenting only raw rule violations.

* **CAPA Recommendations:** Generates corrective and preventive action recommendations for identified deviations and risk patterns.

* **CAPA-Ready Reporting:** Produces structured information that can support clinical operations teams during investigation and remediation.

* **Synthetic Clinical Trial Dataset:** Includes reproducible synthetic trials, sites, participants, observations, and protocol rules for demonstration and testing.

* **Interactive Risk Dashboard:** Provides a centralized view of deviations, severity, site-level risk, and AI-generated insights.

---

## 🛠️ Tech Stack

| **Category**         | **Technologies**                                                              |
| -------------------- | ----------------------------------------------------------------------------- |
| **Languages**        | Python                                                                        |
| **Frameworks**       | Streamlit, Pydantic, Pytest                                                   |
| **IBM Technologies** | IBM Bob, IBM watsonx.ai                                                       |
| **AI / ML**          | IBM AI integration, rule-based clinical monitoring, AI-generated explanations |
| **Data Processing**  | Python, CSV, JSON                                                             |
| **Testing**          | Pytest                                                                        |
| **CI/CD**            | GitHub Actions                                                                |
| **Version Control**  | Git, GitHub                                                                   |

---

## 📁 Repository Structure

```text
├── .github/
│   └── workflows/
│       └── validate.yml
│
├── docs/
│   ├── architecture.md
│   ├── problem-statement.md
│   ├── setup-guide.md
│   ├── solution-overview.md
│   └── template-guide.md
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
│   ├── tests/
│   └── requirements.txt
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

## 🔄 How CliNova Works

```text
Clinical Trial Protocol
          │
          ▼
   Protocol Rules
          │
          ▼
 Synthetic / Clinical Data
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

The architecture separates **data preparation, protocol validation, deviation detection, risk scoring, and AI assistance**, making the monitoring pipeline easier to test, maintain, and extend.

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

### 3. Activate the environment

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

**Windows CMD:**

```cmd
.venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r src/requirements.txt
```

### 5. Generate the synthetic clinical dataset

```bash
python generate_data.py
```

The generated dataset contains structured information for:

* Clinical trial
* Clinical sites
* Participants
* Clinical observations
* Protocol rules

### 6. Configure IBM AI credentials

Copy the environment template:

```powershell
Copy-Item src\.env.example src\.env
```

Then configure the required IBM/watsonx credentials in `src/.env`.

> **Never commit API keys, access tokens, or other credentials to GitHub.**

### 7. Start the dashboard

From the repository root:

```bash
streamlit run src/dashboard/app.py
```

The Streamlit dashboard will open in your browser.

---

## 🧪 Testing

CliNova includes automated tests covering the major components of the monitoring pipeline.

Run the complete test suite with:

```bash
pytest
```

The project also uses GitHub Actions to validate the repository automatically.

---

## 🖥️ Demo

| **Artifact**        | **Link**                                                   |
| ------------------- | ---------------------------------------------------------- |
| 📹 **Demo Video**   | /Users/khushi/Desktop/Khushi/IBM/bob-ai-hackathon-clinova/demo/demo-video-link.txt |
| 🌐 **Live Demo**    |  /Users/khushi/Desktop/Khushi/IBM/bob-ai-hackathon-clinova/demo/live-demo-url.txt   |
| 🖼️ **Screenshots** |   /Users/khushi/Desktop/Khushi/IBM/bob-ai-hackathon-clinova/demo/screenshots          |
| 📊 **Presentation** |   /Users/khushi/Desktop/Khushi/IBM/bob-ai-hackathon-clinova/presentation                    |

---

## 📊 Example Monitoring Scenario

Consider a participant whose Week 4 visit is expected around **Day 28**, with an allowed protocol window of ±3 days.

```text
Protocol:
Week 4 Visit
Expected Day: 28
Allowed Window: ±3 days

Participant Event:
Actual Day: 35

Result:
Deviation Detected
        │
        ▼
Severity Assessment
        │
        ▼
Site Risk Updated
        │
        ▼
AI Explanation
        │
        ▼
CAPA Recommendation
```

This allows the system to move beyond simply saying **"a deviation occurred"** and instead provide information that can help a clinical operations team understand and respond to the issue.

---

## 🔐 Data & Security Considerations

* The demonstration dataset is **synthetic** and does not contain real patient information.
* Credentials and API keys are kept outside the source code through environment configuration.
* Protocol and clinical data are validated before processing.
* The architecture separates clinical data processing from AI-assisted explanation and reporting.
* The system is intended as a **clinical trial monitoring support tool**, not as a replacement for qualified clinical, regulatory, or medical decision-making.

---

## ⚠️ Known Limitations

* The current demonstration uses **synthetic clinical trial data** rather than real-world patient records.
* Protocol rules currently represent a structured subset of possible clinical trial requirements; arbitrary natural-language protocols are not yet fully converted automatically into machine-readable rules.
* AI-generated explanations and CAPA recommendations should be reviewed by qualified clinical operations personnel before being used for real decisions.
* The current system is a monitoring and decision-support platform and does not replace formal clinical trial oversight, regulatory review, or human investigation.
* Production deployment would require additional enterprise capabilities such as role-based access control, audit trails, secure database infrastructure, monitoring, and compliance controls.

---

## 🚀 Future Enhancements

* Natural-language protocol ingestion using AI.
* Integration with real clinical trial data sources and EDC systems.
* Advanced trend detection for recurring site-level deviations.
* Historical risk analysis and predictive site-risk modeling.
* Role-based dashboards for investigators, monitors, and clinical operations teams.
* Comprehensive audit logging.
* Enterprise authentication and authorization.
* Exportable regulatory and compliance reports.
* Continuous monitoring of incoming clinical trial data.

---

## 🏅 What We're Most Proud Of

**CliNova connects the complete clinical trial monitoring workflow instead of treating deviation detection as an isolated feature.**

Our strongest aspect is the end-to-end pipeline:

**Protocol → Structured Rules → Clinical Data → Validation → Deviation Detection → Severity → Site Risk → IBM AI Explanation → CAPA Recommendations**

This architecture makes the system actionable: instead of overwhelming clinical teams with raw protocol violations, CliNova helps identify **which issues matter, where risk is concentrated, why the issue occurred, and what corrective or preventive action can be considered.**

We are particularly proud of combining deterministic protocol validation with AI-assisted explanation, allowing the system to maintain a clear rule-based foundation while using AI where human-readable interpretation and remediation guidance add value.

---

## 📄 Project Documentation

Detailed project documentation is available in the `docs/` directory:

* [`problem-statement.md`](docs/problem-statement.md) — Problem definition and motivation
* [`solution-overview.md`](docs/solution-overview.md) — Solution and workflow
* [`architecture.md`](docs/architecture.md) — System architecture and component interactions
* [`setup-guide.md`](docs/setup-guide.md) — Installation and execution instructions

---

## 🤝 Team

**CliNova** was developed by a four-member team for the **IBM Bob AI Hackathon — AI Track**.

We combined protocol/data engineering, deviation detection, risk analytics, dashboard development, and IBM AI integration to build an end-to-end clinical trial monitoring solution.

---

## 📜 License

This project was created as part of the IBM Bob AI Hackathon.
