# ClearSignal WQ Submission Record

Status: **submitted and publicly published on the challenge platform**

## Challenge

- Challenge: Xylem Global Student Innovation Challenge 2026
- Track: Water Quality
- Participant: Qizhong Deng
- Project type: Solo student project

## Project name

ClearSignal WQ

## Short description

Explainable AI triage for water sensor events, drift, and data-quality failures.

## Full description

Small water utilities and community monitoring teams receive continuous pH, conductivity, temperature, dissolved oxygen, and turbidity readings. When a signal changes, the operator still has to determine whether the cause may be an environmental event, sensor drift, or a broken data link.

ClearSignal WQ turns those anomalies into a priority review queue. A deterministic pipeline validates the data, detects point-level anomalies, groups them into events, measures sensor reliability and cross-sensor agreement, and assigns one of four operational states: possible water-quality event, sensor fault or drift, data-integrity issue, or insufficient evidence. Every event keeps its evidence, limitations, and recommended human verification action beside the result.

The Streamlit prototype supports public Logan River Observatory sensor data and three explicitly labelled synthetic scenarios. Operators can inspect a four-sensor timeline and record a retest, calibration, data-link check, or escalation for the current demo session. The prototype does not alter source observations and does not replace field testing, laboratory analysis, or regulatory review.

## Problem and impact

Sensor fouling, calibration, drift, outages, and telemetry gaps can create large volumes of misleading alerts. Treating every anomaly as an incident creates alert fatigue, while ignoring noisy systems can delay investigation of meaningful changes. ClearSignal WQ aims to reduce the time spent interpreting raw anomalies and make the next verification step explicit.

The immediate target is a small monitoring team that lacks a dedicated data-science staff. The longer-term impact would be measured through fewer avoidable escalations, faster identification of sensor maintenance needs, and more consistent decisions about field retesting and laboratory sampling.

## Technical architecture

- Streamlit single-screen operations workspace
- pandas and NumPy for validated time-series preparation
- deterministic rule detector for gaps, physical-range violations, stuck values, and robust-MAD jumps
- event grouping with stable event IDs
- sensor reliability and same-direction cross-sensor corroboration
- fixed-priority explainable triage engine
- Plotly multi-sensor event timeline
- pytest, Streamlit AppTest, and Playwright regression coverage

The application has one production entry point, `clearsignal_wq.pipeline.run_pipeline`. UI code does not calculate thresholds or change triage decisions.

## Why AI is necessary

The operator's problem is temporal and multivariate: thousands of readings must be compared with site history, sensor reliability, persistence, and concurrent changes in other variables. The pipeline automates that evidence synthesis while keeping the final categories and explanations deterministic and reviewable.

The project deliberately avoids using a generative model as the decision-maker. A fixed ARIMA candidate was tested against a preregistered validation gate but failed the required recall threshold, so the simpler rule model was retained. This is an evidence-based model-selection decision rather than a claim that a more complex model is automatically better.

## Data source and evidence

- Source: `AmberSJones/pyhydroqc`, fixed commit `1260f16ae254abadcd43d71ee1705c3eea1ea2d4`
- Primary record: `MainStreet2019.csv`
- Cross-site record: `FranklinBasin2017.csv`
- Software license: BSD 3-Clause
- Associated HydroShare resource: CC BY 4.0
- Raw files: downloaded locally, SHA-256 verified, excluded from Git

Main Street validation results on technician-labelled **sensor data-quality events**:

- selected rules: recall `1.000`, precision `0.0135`, invalid alerts `7.30/day`;
- rejected ARIMA candidate: recall `0.800`, precision `0.0111`, invalid alerts `7.14/day`;
- frozen rules test: recall `0.7368`, precision `0.0426`, invalid alerts `8.2895/day`.

Untuned Franklin Basin validation check:

- recall `0.7727`;
- precision `0.1977`;
- invalid alerts `9.0/day`;
- detection delay `20 minutes`.

These labels and metrics concern sensor data quality. They do not establish contaminant-detection accuracy.

## Responsible AI and limitations

- Every event requires operator review.
- Public labels are sensor/data-quality annotations rather than confirmed environmental incidents.
- Synthetic scenarios demonstrate workflow behavior, not deployment accuracy.
- Site maintenance history, calibration records, field context, and laboratory samples are not yet integrated.
- The current invalid-alert burden is too high for unattended deployment.
- No output should be used as a regulatory, laboratory, medical, or emergency-response conclusion.

## Verification

- `311 passed`
- package coverage `93.50%`
- three Playwright browser flows
- `1440x900`, `692x752`, and `390x844` visual checks
- clean-clone download, evaluation, and HTTP startup verified
- public-document link and sensitive-information checks passed

## Member role

**Qizhong Deng:** problem research, product design, data contracts, anomaly pipeline, evaluation, interface, testing, responsible-use documentation, and demo.

## Publication fields

- Public GitHub repository: <https://github.com/Cedric-uxb/clearsignal-wq>
- Public demo video: <https://github.com/Cedric-uxb/clearsignal-wq/blob/main/artifacts/demo/ClearSignal-WQ-Demo-Narrated.mp4>
- Public slides/PDF: <https://github.com/Cedric-uxb/clearsignal-wq/blob/main/presentation/ClearSignal-WQ-Deck.pdf>
- Challenge project URL: <https://xyleminnovationchallenge-platform.bemyapp.com/#/projects/6ae27104e24b0f6e951bc990>

## Publication receipt

- Published: 2026-10-28
- Platform confirmation: `Your project is published!`
- Public listing: visible under Project Submissions in the Water Quality - University Track
