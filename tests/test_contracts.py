import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from clearsignal_wq import __version__
from clearsignal_wq.contracts import (
    DataProvenance,
    DetectionEvent,
    EventAssessment,
    EventMetrics,
    EvidenceItem,
    EvidenceStrength,
    PipelineResult,
    PointFlag,
    TriageEvent,
    TriageStatus,
    contract_to_dict,
)


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"


def _make_triage_event(**changes: object) -> TriageEvent:
    values = {
        "event_id": "evt-001",
        "start_at": datetime(2019, 1, 1, tzinfo=UTC),
        "end_at": datetime(2019, 1, 1, 0, 30, tzinfo=UTC),
        "triage_status": TriageStatus.SENSOR_FAULT_OR_DRIFT,
        "evidence_strength": EvidenceStrength.HIGH,
        "affected_sensors": ("ph", "conductivity"),
        "evidence": (
            EvidenceItem(code="stuck", message="pH readings are unchanged", sensor="ph"),
        ),
        "recommended_action": "Clean and calibrate the pH sensor",
        "data_provenance": DataProvenance.SYNTHETIC_SCENARIO,
        "limitations": ("This result does not confirm contamination",),
    }
    values.update(changes)
    return TriageEvent(**values)


def _make_point_flag(**changes: object) -> PointFlag:
    values = {
        "timestamp": datetime(2019, 1, 1, tzinfo=UTC),
        "sensor": "ph",
        "code": "range",
        "severity": EvidenceStrength.MEDIUM,
        "details": (),
    }
    values.update(changes)
    return PointFlag(**values)


def _make_detection_event(**changes: object) -> DetectionEvent:
    values = {
        "event_id": "det-001",
        "start_at": datetime(2019, 1, 1, tzinfo=UTC),
        "end_at": datetime(2019, 1, 1, 0, 30, tzinfo=UTC),
        "affected_sensors": ("ph",),
        "flags": (_make_point_flag(),),
    }
    values.update(changes)
    return DetectionEvent(**values)


def _make_assessment(**changes: object) -> EventAssessment:
    values = {
        "reliability": (("ph", 0.9),),
        "corroborating_sensor_count": 1,
        "has_data_integrity_evidence": False,
        "evidence": (EvidenceItem(code="range", message="Out of range"),),
    }
    values.update(changes)
    return EventAssessment(**values)


def _make_metrics(**changes: object) -> EventMetrics:
    values = {
        "recall": 1.0,
        "precision": 1.0,
        "invalid_alerts_per_day": 0.0,
        "detection_delay_minutes": 0.0,
        "matched_events": 1,
        "predicted_events": 1,
        "labelled_events": 1,
    }
    values.update(changes)
    return EventMetrics(**values)


def _make_pipeline_result(**changes: object) -> PipelineResult:
    values = {
        "data_hash": "abc123",
        "config_version": "1",
        "model_version": "rules-1",
        "provenance": DataProvenance.SYNTHETIC_SCENARIO,
        "events": (_make_triage_event(),),
        "warnings": (),
    }
    values.update(changes)
    return PipelineResult(**values)


def test_contract_enums_have_exact_values() -> None:
    assert {status.value for status in TriageStatus} == {
        "possible_water_quality_event",
        "sensor_fault_or_drift",
        "data_integrity_issue",
        "insufficient_evidence",
    }
    assert {strength.value for strength in EvidenceStrength} == {
        "low",
        "medium",
        "high",
    }
    assert {provenance.value for provenance in DataProvenance} == {
        "public_real_data",
        "synthetic_scenario",
    }


def test_all_contract_types_can_be_created() -> None:
    timestamp = datetime(2019, 1, 1, tzinfo=UTC)
    evidence = EvidenceItem(code="range", message="Value exceeds the expected range")
    flag = PointFlag(
        timestamp=timestamp,
        sensor="ph",
        code="range",
        severity=EvidenceStrength.MEDIUM,
        details=(evidence,),
    )
    detection = DetectionEvent(
        event_id="det-001",
        start_at=timestamp,
        end_at=timestamp,
        affected_sensors=("ph",),
        flags=(flag,),
    )
    assessment = EventAssessment(
        reliability=(("ph", 0.9),),
        corroborating_sensor_count=1,
        has_data_integrity_evidence=False,
        evidence=(evidence,),
    )
    metrics = EventMetrics(
        recall=1.0,
        precision=1.0,
        invalid_alerts_per_day=0.0,
        detection_delay_minutes=0.0,
        matched_events=1,
        predicted_events=1,
        labelled_events=1,
    )
    triage = _make_triage_event()
    result = PipelineResult(
        data_hash="abc123",
        config_version="1",
        model_version="rules-1",
        provenance=DataProvenance.SYNTHETIC_SCENARIO,
        events=(triage,),
    )

    assert detection.flags == (flag,)
    assert assessment.evidence == (evidence,)
    assert metrics.matched_events == 1
    assert result.events == (triage,)


def test_triage_event_is_frozen_and_requires_evidence() -> None:
    event = _make_triage_event()

    with pytest.raises(FrozenInstanceError):
        event.event_id = "changed"
    with pytest.raises(ValueError, match="evidence"):
        replace(event, evidence=())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"event_id": ""}, "event_id"),
        (
            {
                "start_at": datetime(2019, 1, 2, tzinfo=UTC),
                "end_at": datetime(2019, 1, 1, tzinfo=UTC),
            },
            "start_at",
        ),
        ({"affected_sensors": ("ph", "ph")}, "affected_sensors"),
        ({"affected_sensors": ()}, "affected_sensors"),
        ({"recommended_action": ""}, "recommended_action"),
        ({"limitations": ()}, "limitations"),
    ],
)
def test_triage_event_rejects_invalid_required_values(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _make_triage_event(**changes)


def test_triage_event_preserves_sensor_and_evidence_order() -> None:
    first = EvidenceItem(code="first", message="First observation")
    second = EvidenceItem(code="second", message="Second observation")
    event = _make_triage_event(
        affected_sensors=("conductivity", "ph"),
        evidence=(first, second),
    )

    assert event.affected_sensors == ("conductivity", "ph")
    assert event.evidence == (first, second)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"affected_sensors": ["ph"]}, "affected_sensors"),
        (
            {"evidence": [EvidenceItem(code="range", message="Out of range")]},
            "evidence",
        ),
    ],
)
def test_triage_event_rejects_non_tuple_collections(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        _make_triage_event(**changes)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: _make_point_flag(details=[]), "details"),
        (lambda: _make_detection_event(affected_sensors=["ph"]), "affected_sensors"),
        (lambda: _make_detection_event(flags=[]), "flags"),
        (lambda: _make_assessment(reliability=[]), "reliability"),
        (lambda: _make_assessment(evidence=[]), "evidence"),
        (lambda: _make_triage_event(limitations=[]), "limitations"),
        (lambda: _make_pipeline_result(events=[]), "events"),
        (lambda: _make_pipeline_result(warnings=[]), "warnings"),
    ],
)
def test_all_tuple_fields_reject_non_tuple_values(
    factory: Callable[[], object], message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        factory()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: _make_point_flag(details=({"code": "range"},)), "details"),
        (
            lambda: _make_detection_event(affected_sensors=({"sensor": "ph"},)),
            "affected_sensors",
        ),
        (lambda: _make_detection_event(flags=({"code": "range"},)), "flags"),
        (lambda: _make_assessment(reliability=(["ph", 0.9],)), "reliability"),
        (lambda: _make_assessment(reliability=(("ph", {}),)), "reliability"),
        (lambda: _make_assessment(evidence=({"code": "range"},)), "evidence"),
        (lambda: _make_triage_event(evidence=({"code": "range"},)), "evidence"),
        (lambda: _make_triage_event(limitations=({"text": "limit"},)), "limitations"),
        (lambda: _make_pipeline_result(events=({"event_id": "evt"},)), "events"),
        (lambda: _make_pipeline_result(warnings=({"warning": "x"},)), "warnings"),
    ],
)
def test_tuple_fields_reject_invalid_nested_elements(
    factory: Callable[[], object], message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        factory()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: _make_point_flag(severity="safe"), "severity"),
        (lambda: _make_triage_event(triage_status="certain"), "triage_status"),
        (lambda: _make_triage_event(evidence_strength="high"), "evidence_strength"),
        (
            lambda: _make_triage_event(data_provenance="synthetic_scenario"),
            "data_provenance",
        ),
        (lambda: _make_pipeline_result(provenance="untrusted"), "provenance"),
    ],
)
def test_enum_fields_require_enum_instances(
    factory: Callable[[], object], message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        factory()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: _make_assessment(corroborating_sensor_count=[]),
            "corroborating_sensor_count",
        ),
        (
            lambda: _make_assessment(has_data_integrity_evidence={}),
            "has_data_integrity_evidence",
        ),
        (lambda: _make_metrics(recall=[]), "recall"),
        (lambda: _make_metrics(precision={}), "precision"),
        (lambda: _make_metrics(invalid_alerts_per_day=[]), "invalid_alerts_per_day"),
        (
            lambda: _make_metrics(detection_delay_minutes={}),
            "detection_delay_minutes",
        ),
        (lambda: _make_metrics(matched_events=[]), "matched_events"),
        (lambda: _make_metrics(predicted_events={}), "predicted_events"),
        (lambda: _make_metrics(labelled_events=[]), "labelled_events"),
        (
            lambda: _make_assessment(corroborating_sensor_count=True),
            "corroborating_sensor_count",
        ),
        (
            lambda: _make_assessment(has_data_integrity_evidence=0),
            "has_data_integrity_evidence",
        ),
        (lambda: _make_metrics(recall=1), "recall"),
        (lambda: _make_metrics(precision=1), "precision"),
        (lambda: _make_metrics(invalid_alerts_per_day=0), "invalid_alerts_per_day"),
        (
            lambda: _make_metrics(detection_delay_minutes=0),
            "detection_delay_minutes",
        ),
        (lambda: _make_metrics(matched_events=True), "matched_events"),
        (lambda: _make_metrics(predicted_events=True), "predicted_events"),
        (lambda: _make_metrics(labelled_events=True), "labelled_events"),
    ],
)
def test_scalar_fields_require_exact_runtime_types(
    factory: Callable[[], object], message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        factory()


@pytest.mark.parametrize(
    "invalid_timestamp",
    [
        datetime(2019, 1, 1),
        "2019-01-01T00:00:00+00:00",
        datetime(2019, 1, 1, tzinfo=timezone(timedelta(hours=1))),
    ],
)
@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda value: _make_point_flag(timestamp=value), "timestamp"),
        (lambda value: _make_detection_event(start_at=value), "start_at"),
        (lambda value: _make_detection_event(end_at=value), "end_at"),
        (lambda value: _make_triage_event(start_at=value), "start_at"),
        (lambda value: _make_triage_event(end_at=value), "end_at"),
    ],
)
def test_datetime_fields_require_utc_aware_datetimes(
    factory: Callable[[object], object], message: str, invalid_timestamp: object
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory(invalid_timestamp)


def test_detection_event_rejects_reverse_time_range() -> None:
    with pytest.raises(ValueError, match="start_at"):
        _make_detection_event(
            start_at=datetime(2019, 1, 2, tzinfo=UTC),
            end_at=datetime(2019, 1, 1, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: EvidenceItem(code="", message="Observation"), "code"),
        (lambda: EvidenceItem(code="range", message=""), "message"),
        (
            lambda: EvidenceItem(code="range", message="Observation", sensor=" "),
            "sensor",
        ),
        (lambda: _make_point_flag(sensor=""), "sensor"),
        (lambda: _make_point_flag(code="   "), "code"),
        (lambda: _make_detection_event(event_id=""), "event_id"),
        (lambda: _make_detection_event(source_label=" "), "source_label"),
        (lambda: _make_detection_event(affected_sensors=()), "affected_sensors"),
        (lambda: _make_detection_event(affected_sensors=("",)), "affected_sensors"),
        (lambda: _make_assessment(reliability=(("   ", 0.9),)), "reliability"),
        (lambda: _make_triage_event(affected_sensors=(" ",)), "affected_sensors"),
        (lambda: _make_triage_event(limitations=("   ",)), "limitations"),
        (lambda: _make_pipeline_result(data_hash=""), "data_hash"),
        (lambda: _make_pipeline_result(config_version=""), "config_version"),
        (lambda: _make_pipeline_result(model_version=""), "model_version"),
        (lambda: _make_pipeline_result(warnings=("   ",)), "warnings"),
    ],
)
def test_contracts_reject_empty_required_values(
    factory: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_pipeline_result_rejects_mixed_provenance() -> None:
    with pytest.raises(ValueError, match="provenance"):
        _make_pipeline_result(provenance=DataProvenance.PUBLIC_REAL_DATA)


def test_contract_to_dict_returns_json_safe_stable_values() -> None:
    event = _make_triage_event()

    payload = contract_to_dict(event)

    assert payload["start_at"] == "2019-01-01T00:00:00+00:00"
    assert payload["end_at"] == "2019-01-01T00:30:00+00:00"
    assert payload["triage_status"] == "sensor_fault_or_drift"
    assert payload["evidence_strength"] == "high"
    assert payload["data_provenance"] == "synthetic_scenario"
    assert payload["affected_sensors"] == ["ph", "conductivity"]
    assert payload["evidence"] == [
        {"code": "stuck", "message": "pH readings are unchanged", "sensor": "ph"}
    ]
    assert json.loads(json.dumps(payload)) == payload


def test_contract_to_dict_rejects_non_dataclass_root() -> None:
    with pytest.raises(TypeError, match="dataclass"):
        contract_to_dict({"event_id": "evt-001"})
