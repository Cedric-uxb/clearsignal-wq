from __future__ import annotations

import math
from datetime import timedelta

from clearsignal_wq.contracts import (
    DataProvenance,
    DetectionEvent,
    EventAssessment,
    EvidenceItem,
    EvidenceStrength,
    TriageEvent,
    TriageStatus,
)

_RAW_SENSORS = frozenset({"temp", "cond", "ph", "do", "turb"})
_SUPPORTED_EVENT_SENSORS = _RAW_SENSORS | {"stream"}
_RELIABLE_SENSOR_THRESHOLD = 0.6
_PERSISTENCE_WINDOW = timedelta(minutes=30)
_DATA_INTEGRITY_CODES = frozenset(
    {
        "duplicate_timestamp",
        "missing_interval",
        "out_of_physical_range",
    }
)
_FLAG_MESSAGES = {
    "duplicate_timestamp": "A duplicate timestamp signal was recorded.",
    "missing_interval": "A timestamp gap signal was recorded.",
    "out_of_physical_range": "A physical-range violation was recorded.",
    "technician_quality_label": "A technician data-quality label was recorded.",
    "stuck_value": "A sustained identical-reading signal was recorded.",
    "sudden_jump": "A sudden-change signal was recorded.",
    "arima_residual": "A time-series residual signal was recorded.",
}
_ACTIONS = {
    TriageStatus.DATA_INTEGRITY_ISSUE: (
        "检查数据链路、时间戳和原始记录，修复后重新运行分析。"
    ),
    TriageStatus.SENSOR_FAULT_OR_DRIFT: ("清洁并校准传感器，然后使用独立仪器复测。"),
    TriageStatus.POSSIBLE_WATER_QUALITY_EVENT: (
        "进行现场复测，并根据复测结果决定是否送实验室确认。"
    ),
    TriageStatus.INSUFFICIENT_EVIDENCE: "继续观察，并安排下一次人工复测。",
}
_STRENGTHS = {
    TriageStatus.DATA_INTEGRITY_ISSUE: EvidenceStrength.HIGH,
    TriageStatus.SENSOR_FAULT_OR_DRIFT: EvidenceStrength.MEDIUM,
    TriageStatus.POSSIBLE_WATER_QUALITY_EVENT: EvidenceStrength.HIGH,
    TriageStatus.INSUFFICIENT_EVIDENCE: EvidenceStrength.LOW,
}
_DECISION_MESSAGES = {
    TriageStatus.DATA_INTEGRITY_ISSUE: (
        "Deterministic data-integrity evidence takes priority."
    ),
    TriageStatus.SENSOR_FAULT_OR_DRIFT: (
        "One low-reliability sensor has a sustained anomaly signal."
    ),
    TriageStatus.POSSIBLE_WATER_QUALITY_EVENT: (
        "At least two reliable sensors provide same-direction corroboration."
    ),
    TriageStatus.INSUFFICIENT_EVIDENCE: (
        "The structured evidence does not satisfy a higher-priority rule."
    ),
}
_COMMON_LIMITATION = "本结果不是饮用安全或污染确认结论"
_SYNTHETIC_LIMITATION = "本事件由版本化场景生成器注入"


def triage_event(
    event: DetectionEvent,
    assessment: EventAssessment,
    provenance: DataProvenance,
) -> TriageEvent:
    """Map structured event evidence to one deterministic triage result."""
    _validate_inputs(event, assessment, provenance)
    reliability = dict(assessment.reliability)
    has_integrity_evidence = assessment.has_data_integrity_evidence or any(
        flag.code in _DATA_INTEGRITY_CODES for flag in event.flags
    )

    if has_integrity_evidence:
        status = TriageStatus.DATA_INTEGRITY_ISSUE
    elif _is_single_sensor_fault(event, reliability):
        status = TriageStatus.SENSOR_FAULT_OR_DRIFT
    elif assessment.corroborating_sensor_count >= 2:
        status = TriageStatus.POSSIBLE_WATER_QUALITY_EVENT
    else:
        status = TriageStatus.INSUFFICIENT_EVIDENCE

    return TriageEvent(
        event_id=event.event_id,
        start_at=event.start_at,
        end_at=event.end_at,
        triage_status=status,
        evidence_strength=_STRENGTHS[status],
        affected_sensors=event.affected_sensors,
        evidence=_build_evidence(
            event,
            assessment,
            status,
            has_integrity_evidence,
        ),
        recommended_action=_ACTIONS[status],
        data_provenance=provenance,
        limitations=_limitations(provenance),
    )


def _is_single_sensor_fault(
    event: DetectionEvent,
    reliability: dict[str, float],
) -> bool:
    if len(reliability) != 1:
        return False
    sensor, score = next(iter(reliability.items()))
    if score >= _RELIABLE_SENSOR_THRESHOLD:
        return False
    sensor_flags = tuple(flag for flag in event.flags if flag.sensor == sensor)
    sustained = (
        any(flag.code == "stuck_value" for flag in sensor_flags)
        or len({flag.timestamp for flag in sensor_flags}) >= 2
        or event.end_at - event.start_at >= _PERSISTENCE_WINDOW
    )
    return sustained


def _build_evidence(
    event: DetectionEvent,
    assessment: EventAssessment,
    status: TriageStatus,
    has_integrity_evidence: bool,
) -> tuple[EvidenceItem, ...]:
    evidence: list[EvidenceItem] = [
        EvidenceItem(
            code="triage_decision",
            message=_DECISION_MESSAGES[status],
        )
    ]
    for flag in sorted(
        event.flags,
        key=lambda item: (item.timestamp, item.sensor, item.code),
    ):
        evidence.append(
            EvidenceItem(
                code="event_signal",
                message=_FLAG_MESSAGES.get(
                    flag.code,
                    "An additional detector signal was recorded.",
                ),
                sensor=flag.sensor,
            )
        )
    for sensor, score in sorted(assessment.reliability):
        evidence.append(
            EvidenceItem(
                code="sensor_reliability",
                message=f"Deterministic reliability score: {score:.3f}.",
                sensor=sensor,
            )
        )
    if has_integrity_evidence:
        evidence.append(
            EvidenceItem(
                code="data_integrity_evidence",
                message="Data-integrity evidence is present for this event.",
            )
        )
    evidence.append(
        EvidenceItem(
            code="cross_sensor_corroboration",
            message=(
                f"Reliable same-direction sensor count: "
                f"{assessment.corroborating_sensor_count}."
            ),
        )
    )
    event_has_fallback = any(
        detail.code == "model_fallback"
        for flag in event.flags
        for detail in flag.details
    )
    assessment_has_fallback = any(
        item.code == "model_fallback" for item in assessment.evidence
    )
    if event_has_fallback or assessment_has_fallback:
        evidence.append(
            EvidenceItem(
                code="model_fallback",
                message="The time-series model was unavailable; rule evidence was used.",
            )
        )
    return tuple(evidence)


def _limitations(provenance: DataProvenance) -> tuple[str, ...]:
    if provenance is DataProvenance.SYNTHETIC_SCENARIO:
        return (_COMMON_LIMITATION, _SYNTHETIC_LIMITATION)
    return (_COMMON_LIMITATION,)


def _validate_inputs(
    event: object,
    assessment: object,
    provenance: object,
) -> None:
    if not isinstance(event, DetectionEvent):
        raise TypeError("event must be a DetectionEvent")
    if not isinstance(assessment, EventAssessment):
        raise TypeError("assessment must be an EventAssessment")
    if not isinstance(provenance, DataProvenance):
        raise TypeError("provenance must be a DataProvenance")
    if len(set(event.affected_sensors)) != len(event.affected_sensors):
        raise ValueError("event affected_sensors must not contain duplicates")
    if not set(event.affected_sensors).issubset(_SUPPORTED_EVENT_SENSORS):
        raise ValueError("event contains an unsupported affected sensor")
    if not event.flags:
        raise ValueError("event flags must not be empty")
    flag_sensors = {flag.sensor for flag in event.flags}
    if flag_sensors != set(event.affected_sensors):
        raise ValueError("event affected_sensors must match event flags")
    flag_timestamps = tuple(flag.timestamp for flag in event.flags)
    if event.start_at != min(flag_timestamps) or event.end_at != max(flag_timestamps):
        raise ValueError("event bounds must match event flags")

    reliability_sensors: list[str] = []
    reliable_count = 0
    for sensor, score in assessment.reliability:
        if sensor in reliability_sensors:
            raise ValueError("assessment reliability sensors must be unique")
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("assessment reliability scores must be within [0, 1]")
        reliability_sensors.append(sensor)
        if score >= _RELIABLE_SENSOR_THRESHOLD:
            reliable_count += 1

    expected_sensors = set(event.affected_sensors).intersection(_RAW_SENSORS)
    if set(reliability_sensors) != expected_sensors:
        raise ValueError(
            "assessment reliability sensors must match affected raw sensors"
        )
    corroborating_count = assessment.corroborating_sensor_count
    if corroborating_count < 0 or corroborating_count == 1:
        raise ValueError("corroborating_sensor_count must be 0 or at least 2")
    if corroborating_count > reliable_count:
        raise ValueError(
            "corroborating_sensor_count cannot exceed reliable sensor count"
        )
