# ClearSignal WQ

ClearSignal WQ is a decision-support prototype for small water utilities and community monitoring teams. It turns high-frequency aquatic sensor anomalies into a review queue that distinguishes four operational possibilities:

- possible water-quality event;
- sensor fault or drift;
- data-integrity issue; or
- insufficient evidence.

Every result keeps the evidence, limitations, and recommended human action beside the model output. The prototype does not replace field retesting, laboratory analysis, or regulatory review.

Chinese project research and design notes are available in [研究结论.md](研究结论.md).

## Problem

Temperature, conductivity, pH, dissolved oxygen, and turbidity sensors can change because of real environmental conditions, fouling, drift, calibration work, power loss, or transmission gaps. Treating every anomaly as an incident creates alert fatigue; dismissing noisy alerts can hide changes that deserve investigation.

ClearSignal WQ focuses on the response decision: what evidence is present, how strong is it, and what should an operator verify next?

## Target user and workflow

The primary user is an operator with limited time and limited access to advanced analytics.

1. Select the public sensor record or one clearly labelled synthetic scenario.
2. Choose a priority-sorted event.
3. Review the four-sensor timeline, structured evidence, affected sensors, and limitations.
4. Record a demo-session action: retest, calibrate, inspect the data link, or escalate.

Actions are stored only in the current Streamlit session. The application never writes them into the source data.

## Demo modes

- **Public real sensor data:** Main Street 2019 observations from the Logan River Observatory dataset distributed with pyhydroqc.
- **Correlated sensor shift:** a deterministic multi-sensor scenario used to demonstrate a possible water-quality event workflow.
- **Single-sensor drift:** a deterministic pH drift scenario used to demonstrate calibration triage.
- **Missing data interval:** a deterministic timestamp-gap scenario used to demonstrate data-link triage.

Synthetic modes are always labelled `Synthetic scenario / 合成场景`. They demonstrate product behavior and are not real-world accuracy evidence.

## How it works

The deterministic pipeline follows one production path:

1. validate timestamps, required sensors, and source provenance;
2. fit rule thresholds only on the training period;
3. detect missing intervals, physical-range violations, stuck values, and robust-MAD jumps;
4. group point flags into stable events;
5. estimate sensor reliability and same-direction cross-sensor corroboration;
6. apply a fixed-priority triage policy;
7. render structured evidence and human verification actions.

The application calls `clearsignal_wq.pipeline.run_pipeline`; UI code does not recompute detector thresholds or triage decisions. A fixed ARIMA candidate was evaluated, but it did not meet the preregistered validation recall gate, so the simpler rule model remains the selected model.

## Evaluation

The evaluation target is **technician-labelled sensor data-quality events**, not confirmed contamination events.

| Model and split | Event recall | Event precision | Invalid alerts/day | Result |
| --- | ---: | ---: | ---: | --- |
| Rules, validation | 1.000 | 0.0135 | 7.30 | Selected baseline |
| ARIMA candidate, validation | 0.800 | 0.0111 | 7.14 | Rejected by recall gate |
| Frozen rules, test | 0.7368 | 0.0426 | 8.2895 | Final held-out check |

The low precision and high invalid-alert rate are important limitations, not numbers to hide. This prototype demonstrates explainable event triage and a reproducible evaluation path; it has not established field performance for detecting contaminants.

Automated quality evidence at the current commit:

- 310 tests passing, including Streamlit AppTest and two Playwright browser flows;
- 93.50% package coverage;
- desktop `1440x900` and mobile `390x844` visual checks with no horizontal overflow;
- deterministic data hashes, event IDs, scenario manifests, and priority ordering.

See [docs/visual-qa.md](docs/visual-qa.md) for the browser and viewport evidence.

## Data source

The approved files come from the [`AmberSJones/pyhydroqc`](https://github.com/AmberSJones/pyhydroqc) repository at commit [`1260f16ae254abadcd43d71ee1705c3eea1ea2d4`](https://github.com/AmberSJones/pyhydroqc/tree/1260f16ae254abadcd43d71ee1705c3eea1ea2d4).

- `MainStreet2019.csv` is the primary development and evaluation record.
- `FranklinBasin2017.csv` is reserved for an un-tuned cross-site robustness check.
- Raw CSV files are downloaded locally, verified by SHA-256, and excluded from Git.
- `*_qual` columns contain technician sensor/data-quality labels. They do not identify a contaminant or establish a regulatory water-quality condition.

The related [HydroShare teaching resource](https://www.hydroshare.org/resource/451c4f9697654b1682d87ee619cd7924/) is shared under CC BY 4.0. Full attribution is in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and exact hashes and field semantics are in [data/README.md](data/README.md).

## Run locally

Python 3.11 or 3.12 is required. From the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/download_data.py
./scripts/run_app.sh
```

Open `http://127.0.0.1:8501`.

On Windows, activate the environment and run the equivalent module command:

```powershell
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python scripts\download_data.py
.venv\Scripts\python -m streamlit run app.py
```

## Test and reproduce metrics

```bash
.venv/bin/python -m pytest --cov=clearsignal_wq --cov-report=term-missing --cov-fail-under=80
.venv/bin/python -m ruff check app.py src tests scripts
.venv/bin/python scripts/run_evaluation.py --model rules --split validation
```

Evaluation JSON is written to the Git-ignored `artifacts/metrics/` directory. The ARIMA comparison requires the rules validation artifact first:

```bash
.venv/bin/python scripts/run_evaluation.py --model arima --split validation
```

## Responsible use and limitations

- This is a student proof of concept, not a regulatory, laboratory, medical, or emergency-response system.
- Public labels describe sensor data quality rather than confirmed environmental incidents.
- Synthetic scenarios test workflow behavior and reproducibility only.
- Site-specific calibration, maintenance records, operating context, and laboratory sampling are not included.
- The current false-alert burden is too high for unattended deployment.
- Operators must review each event and use independent field or laboratory verification when appropriate.

## Project structure

```text
app.py                       Streamlit operations workspace
src/clearsignal_wq/          contracts, detectors, events, triage, pipeline
scripts/download_data.py     allow-listed downloads with SHA-256 verification
scripts/run_evaluation.py    reproducible event-level evaluation
scripts/run_app.sh           local Streamlit launcher
tests/                       unit, integration, AppTest, and Playwright tests
docs/visual-qa.md            desktop and mobile visual evidence
demo/demo_script.md          recording steps and English narration
```

## Team

ClearSignal WQ is a solo student project by **Qizhong Deng**.

