from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from clearsignal_wq.contracts import (
    DataProvenance,
    DetectionEvent,
    EventMetrics,
    contract_to_dict,
)
from clearsignal_wq.data import chronological_split, load_sensor_csv
from clearsignal_wq.detectors import ArimaConfig, RuleConfig
from clearsignal_wq.evaluation import (
    arima_meets_gate,
    count_clean_days,
    evaluate_events,
)
from clearsignal_wq.events import labelled_quality_events
from clearsignal_wq.pipeline import run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "MainStreet2019.csv"
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "metrics"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the deterministic ClearSignal WQ rule baseline."
    )
    parser.add_argument("--model", choices=("rules", "arima"), required=True)
    parser.add_argument(
        "--split",
        choices=("train", "validation", "test"),
        required=True,
    )
    args = parser.parse_args()

    output_path, payload = run_evaluation(model=args.model, split=args.split)
    print(f"Wrote {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_evaluation(*, model: str, split: str) -> tuple[Path, dict[str, Any]]:
    if model not in {"rules", "arima"}:
        raise ValueError("model must be 'rules' or 'arima'")
    if split not in {"train", "validation", "test"}:
        raise ValueError("split must be 'train', 'validation', or 'test'")
    if split == "test":
        _require_frozen_model_choice(model)
    if not DATA_PATH.is_file():
        raise FileNotFoundError(
            f"missing {DATA_PATH}; run scripts/download_data.py first"
        )

    frame = load_sensor_csv(DATA_PATH)
    dataset = chronological_split(frame)
    evaluation_frame = {
        "train": dataset.train,
        "validation": dataset.validation,
        "test": dataset.test,
    }[split]

    rule_config = RuleConfig()
    pipeline_model = "rules" if model == "rules" else "rules_arima"
    pipeline_result = run_pipeline(
        evaluation_frame,
        DataProvenance.PUBLIC_REAL_DATA,
        model=pipeline_model,
        training_frame=dataset.train,
    )
    if model == "rules":
        config_payload: dict[str, Any] = {
            "expected_interval_minutes": rule_config.expected_interval_minutes,
            "jump_mad_multiplier": rule_config.jump_mad_multiplier,
            "stuck_run_points": rule_config.stuck_run_points,
        }
    else:
        arima_config = ArimaConfig()
        config_payload = {
            "arima_order": list(arima_config.order),
            "expected_interval_minutes": rule_config.expected_interval_minutes,
            "jump_mad_multiplier": rule_config.jump_mad_multiplier,
            "residual_mad_multiplier": arima_config.residual_mad_multiplier,
            "stuck_run_points": rule_config.stuck_run_points,
        }

    predicted_events = tuple(
        DetectionEvent(
            event_id=event.event_id,
            start_at=event.start_at,
            end_at=event.end_at,
            affected_sensors=event.affected_sensors,
            flags=(),
        )
        for event in pipeline_result.events
    )
    labelled_events = labelled_quality_events(evaluation_frame)
    clean_days = float(count_clean_days(evaluation_frame.index, labelled_events))
    metrics = evaluate_events(
        predicted_events,
        labelled_events,
        clean_days=clean_days,
    )

    payload: dict[str, Any] = {
        "config": config_payload,
        "data": {
            "file": DATA_PATH.name,
            "sha256": _sha256_file(DATA_PATH),
        },
        "event_counts": {
            "clean_days": int(clean_days),
            "labelled": metrics.labelled_events,
            "matched": metrics.matched_events,
            "predicted": metrics.predicted_events,
        },
        "git_commit": _git_commit(),
        "metrics": {
            key: value
            for key, value in contract_to_dict(metrics).items()
            if key
            in {
                "recall",
                "precision",
                "invalid_alerts_per_day",
                "detection_delay_minutes",
            }
        },
        "model": model,
        "pipeline": {
            "config_version": pipeline_result.config_version,
            "data_hash": pipeline_result.data_hash,
            "model_version": pipeline_result.model_version,
            "warnings": list(pipeline_result.warnings),
        },
        "split": split,
    }
    if model == "arima":
        payload["model_status"] = {
            "warnings": list(pipeline_result.warnings),
        }
    if model == "arima" and split == "validation":
        rules_validation = _load_metrics(OUTPUT_DIR / "rules-validation.json")
        promoted = arima_meets_gate(rules_validation, metrics)
        payload["promotion_gate"] = {
            "invalid_alerts_per_day_max": (
                rules_validation.invalid_alerts_per_day + 0.10
            ),
            "precision_min": max(0.0, rules_validation.precision - 0.05),
            "promoted": promoted,
            "recall_min": min(1.0, rules_validation.recall + 0.05),
        }
    output_path = OUTPUT_DIR / f"{model}-{split}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path, payload


def _load_metrics(path: Path) -> EventMetrics:
    if not path.is_file():
        raise FileNotFoundError(f"missing baseline metrics: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload["metrics"]
    counts = payload["event_counts"]
    return EventMetrics(
        recall=float(metrics["recall"]),
        precision=float(metrics["precision"]),
        invalid_alerts_per_day=float(metrics["invalid_alerts_per_day"]),
        detection_delay_minutes=float(metrics["detection_delay_minutes"]),
        matched_events=int(counts["matched"]),
        predicted_events=int(counts["predicted"]),
        labelled_events=int(counts["labelled"]),
    )


def _require_frozen_model_choice(model: str) -> None:
    candidate_path = OUTPUT_DIR / "arima-validation.json"
    if not candidate_path.is_file():
        raise FileNotFoundError(
            "missing ARIMA validation decision; run validation before test"
        )
    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    promoted = bool(candidate_payload["promotion_gate"]["promoted"])
    selected_model = "arima" if promoted else "rules"
    if model != selected_model:
        raise ValueError(
            f"frozen model choice is {selected_model!r}; test split cannot use {model!r}"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    main()
