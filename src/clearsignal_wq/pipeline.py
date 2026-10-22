from __future__ import annotations

import hashlib
from dataclasses import replace

import pandas as pd

from clearsignal_wq.contracts import (
    DataProvenance,
    EvidenceStrength,
    PipelineResult,
    TriageEvent,
    TriageStatus,
)
from clearsignal_wq.data import DataContractError, chronological_split
from clearsignal_wq.detectors import (
    detect_arima_anomalies,
    detect_rule_anomalies,
    fit_arima_detector,
    fit_rule_detector,
)
from clearsignal_wq.events import group_flags_into_events
from clearsignal_wq.reliability import assess_event
from clearsignal_wq.triage import triage_event

_REQUIRED_SENSORS = ("temp", "cond", "ph", "do")
_CONFIG_VERSION = "pipeline-1"
_MODEL_VERSIONS = {
    "rules": "rules-1",
    "rules_arima": "rules-arima-1",
}
_STATUS_PRIORITY = {
    TriageStatus.DATA_INTEGRITY_ISSUE: 0,
    TriageStatus.SENSOR_FAULT_OR_DRIFT: 1,
    TriageStatus.POSSIBLE_WATER_QUALITY_EVENT: 2,
    TriageStatus.INSUFFICIENT_EVIDENCE: 3,
}
_DOWNGRADED_STRENGTH = {
    EvidenceStrength.HIGH: EvidenceStrength.MEDIUM,
    EvidenceStrength.MEDIUM: EvidenceStrength.LOW,
    EvidenceStrength.LOW: EvidenceStrength.LOW,
}


def run_pipeline(
    frame: pd.DataFrame,
    provenance: DataProvenance,
    model: str = "rules",
    *,
    training_frame: pd.DataFrame | None = None,
) -> PipelineResult:
    """Run the deterministic detection-to-triage path."""
    if not isinstance(provenance, DataProvenance):
        raise TypeError("provenance must be a DataProvenance")
    if model not in _MODEL_VERSIONS:
        raise ValueError("model must be 'rules' or 'rules_arima'")

    training, target = _resolve_frames(frame, training_frame)
    warnings: tuple[str, ...] = ()
    if model == "rules":
        flags = detect_rule_anomalies(target, fit_rule_detector(training))
    else:
        fitted = fit_arima_detector(training)
        flags = detect_arima_anomalies(target, fitted)
        fallback_sensors = {
            *fitted.fallback_sensors,
            *(
                flag.sensor
                for flag in flags
                if any(detail.code == "model_fallback" for detail in flag.details)
            ),
        }
        if fallback_sensors:
            sensor_names = ", ".join(sorted(fallback_sensors))
            warnings = (
                f"model_fallback: deterministic rules used for {sensor_names}.",
            )

    events = group_flags_into_events(flags)
    triaged = tuple(
        _downgrade_fallback(
            triage_event(
                event,
                assess_event(event, target, flags),
                provenance,
            )
        )
        for event in events
    )
    ordered = tuple(sorted(triaged, key=_triage_sort_key))
    return PipelineResult(
        data_hash=_data_hash(training, target),
        config_version=_CONFIG_VERSION,
        model_version=_MODEL_VERSIONS[model],
        provenance=provenance,
        events=ordered,
        warnings=warnings,
    )


def _resolve_frames(
    frame: object,
    training_frame: object,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _validate_required_sensors(frame, "frame")
    if training_frame is not None:
        _validate_required_sensors(training_frame, "training_frame")
        return training_frame, frame

    split = chronological_split(frame)
    target = pd.concat((split.validation, split.test))
    return split.train, target


def _validate_required_sensors(frame: object, field_name: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{field_name} must be a DataFrame")
    missing = [sensor for sensor in _REQUIRED_SENSORS if sensor not in frame]
    if missing:
        raise DataContractError(f"missing required columns: {', '.join(missing)}")


def _downgrade_fallback(event: TriageEvent) -> TriageEvent:
    if not any(item.code == "model_fallback" for item in event.evidence):
        return event
    return replace(
        event,
        evidence_strength=_DOWNGRADED_STRENGTH[event.evidence_strength],
    )


def _triage_sort_key(event: TriageEvent) -> tuple[object, ...]:
    return (
        _STATUS_PRIORITY[event.triage_status],
        event.start_at,
        event.end_at,
        event.event_id,
    )


def _data_hash(training: pd.DataFrame, target: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for label, current in (("training", training), ("target", target)):
        digest.update(label.encode())
        digest.update(b"\0")
        digest.update(
            current.to_csv(
                date_format="%Y-%m-%dT%H:%M:%S.%f%z",
                float_format="%.17g",
                lineterminator="\n",
                na_rep="<NA>",
            ).encode()
        )
        digest.update(b"\0")
    return digest.hexdigest()
