from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from clearsignal_wq.contracts import (
    DataProvenance,
    DetectionEvent,
    EventAssessment,
    EvidenceItem,
    EvidenceStrength,
    PointFlag,
    TriageStatus,
)
from clearsignal_wq.triage import triage_event


def _timestamp(minutes: int) -> datetime:
    return datetime(2019, 1, 1, tzinfo=UTC) + pd.Timedelta(minutes=minutes)


def _flag(
    minutes: int,
    sensor: str,
    code: str,
    message: str | None = None,
) -> PointFlag:
    return PointFlag(
        timestamp=_timestamp(minutes),
        sensor=sensor,
        code=code,
        severity=EvidenceStrength.MEDIUM,
        details=(
            EvidenceItem(
                code=code,
                message=message or f"Observed {code} for {sensor}.",
                sensor=sensor,
            ),
        ),
    )


def _event(*flags: PointFlag) -> DetectionEvent:
    ordered = tuple(sorted(flags, key=lambda flag: flag.timestamp))
    return DetectionEvent(
        event_id="event-001",
        start_at=ordered[0].timestamp,
        end_at=ordered[-1].timestamp,
        affected_sensors=tuple(sorted({flag.sensor for flag in ordered})),
        flags=ordered,
    )


def _assessment(
    reliability: tuple[tuple[str, float], ...],
    corroborating_sensor_count: int = 0,
    has_data_integrity_evidence: bool = False,
) -> EventAssessment:
    return EventAssessment(
        reliability=reliability,
        corroborating_sensor_count=corroborating_sensor_count,
        has_data_integrity_evidence=has_data_integrity_evidence,
        evidence=(
            EvidenceItem(
                code="assessment_context",
                message="Deterministic assessment context.",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("event", "assessment", "status", "strength", "action_fragment"),
    [
        (
            _event(
                _flag(60, "ph", "sudden_jump"),
                _flag(60, "do", "sudden_jump"),
            ),
            _assessment(
                (("do", 1.0), ("ph", 1.0)),
                corroborating_sensor_count=2,
                has_data_integrity_evidence=True,
            ),
            TriageStatus.DATA_INTEGRITY_ISSUE,
            EvidenceStrength.HIGH,
            "检查数据链路",
        ),
        (
            _event(_flag(60, "ph", "stuck_value")),
            _assessment((("ph", 0.4),)),
            TriageStatus.SENSOR_FAULT_OR_DRIFT,
            EvidenceStrength.MEDIUM,
            "清洁并校准传感器",
        ),
        (
            _event(
                _flag(60, "ph", "sudden_jump"),
                _flag(60, "do", "sudden_jump"),
            ),
            _assessment(
                (("do", 1.0), ("ph", 1.0)),
                corroborating_sensor_count=2,
            ),
            TriageStatus.POSSIBLE_WATER_QUALITY_EVENT,
            EvidenceStrength.HIGH,
            "现场复测",
        ),
        (
            _event(_flag(60, "ph", "sudden_jump")),
            _assessment((("ph", 1.0),)),
            TriageStatus.INSUFFICIENT_EVIDENCE,
            EvidenceStrength.LOW,
            "继续观察",
        ),
    ],
)
def test_triage_event_uses_fixed_priority_and_templates(
    event: DetectionEvent,
    assessment: EventAssessment,
    status: TriageStatus,
    strength: EvidenceStrength,
    action_fragment: str,
) -> None:
    result = triage_event(event, assessment, DataProvenance.PUBLIC_REAL_DATA)

    assert result.triage_status is status
    assert result.evidence_strength is strength
    assert action_fragment in result.recommended_action
    assert result.limitations == ("本结果不是饮用安全或污染确认结论",)
    assert result.event_id == event.event_id
    assert result.start_at == event.start_at
    assert result.end_at == event.end_at
    assert result.affected_sensors == event.affected_sensors
    assert result.data_provenance is DataProvenance.PUBLIC_REAL_DATA
    assert result.evidence


def test_data_integrity_priority_wins_over_cross_sensor_corroboration() -> None:
    event = _event(
        _flag(60, "ph", "out_of_physical_range"),
        _flag(60, "do", "sudden_jump"),
    )
    assessment = _assessment(
        (("do", 1.0), ("ph", 1.0)),
        corroborating_sensor_count=2,
        has_data_integrity_evidence=True,
    )

    result = triage_event(event, assessment, DataProvenance.PUBLIC_REAL_DATA)

    assert result.triage_status is TriageStatus.DATA_INTEGRITY_ISSUE


@pytest.mark.parametrize("code", ["missing_interval", "duplicate_timestamp"])
def test_stream_integrity_codes_trigger_data_integrity_status(code: str) -> None:
    event = _event(_flag(60, "stream", code))

    result = triage_event(
        event,
        _assessment(()),
        DataProvenance.PUBLIC_REAL_DATA,
    )

    assert result.triage_status is TriageStatus.DATA_INTEGRITY_ISSUE


def test_data_integrity_priority_wins_over_low_reliability_sensor_fault() -> None:
    event = _event(
        _flag(60, "stream", "missing_interval"),
        _flag(60, "ph", "stuck_value"),
    )

    result = triage_event(
        event,
        _assessment((("ph", 0.4),)),
        DataProvenance.PUBLIC_REAL_DATA,
    )

    assert result.triage_status is TriageStatus.DATA_INTEGRITY_ISSUE


def test_low_reliability_without_sustained_signal_is_insufficient() -> None:
    event = _event(_flag(60, "ph", "sudden_jump"))

    result = triage_event(
        event,
        _assessment((("ph", 0.4),)),
        DataProvenance.PUBLIC_REAL_DATA,
    )

    assert result.triage_status is TriageStatus.INSUFFICIENT_EVIDENCE


def test_repeated_single_sensor_anomaly_is_treated_as_sustained() -> None:
    event = _event(
        _flag(0, "ph", "sudden_jump"),
        _flag(15, "ph", "sudden_jump"),
    )

    result = triage_event(
        event,
        _assessment((("ph", 0.4),)),
        DataProvenance.PUBLIC_REAL_DATA,
    )

    assert result.triage_status is TriageStatus.SENSOR_FAULT_OR_DRIFT


def test_duplicate_flags_at_one_timestamp_are_not_sustained() -> None:
    first = _flag(60, "ph", "sudden_jump")
    second = _flag(60, "ph", "sudden_jump")
    event = DetectionEvent(
        event_id="event-duplicate-flags",
        start_at=_timestamp(60),
        end_at=_timestamp(60),
        affected_sensors=("ph",),
        flags=(first, second),
    )

    result = triage_event(
        event,
        _assessment((("ph", 0.4),)),
        DataProvenance.PUBLIC_REAL_DATA,
    )

    assert result.triage_status is TriageStatus.INSUFFICIENT_EVIDENCE


def test_synthetic_provenance_adds_scenario_limitation() -> None:
    event = _event(_flag(60, "ph", "sudden_jump"))

    result = triage_event(
        event,
        _assessment((("ph", 1.0),)),
        DataProvenance.SYNTHETIC_SCENARIO,
    )

    assert result.limitations == (
        "本结果不是饮用安全或污染确认结论",
        "本事件由版本化场景生成器注入",
    )


def test_output_never_echoes_prohibited_claims_from_upstream_evidence() -> None:
    event = _event(
        _flag(
            60,
            "ph",
            "unknown_detector_code",
            "confirmed contamination, safe and drinkable; 水安全，可以饮用，污染已确认。",
        )
    )
    assessment = EventAssessment(
        reliability=(("ph", 1.0),),
        corroborating_sensor_count=0,
        has_data_integrity_evidence=False,
        evidence=(
            EvidenceItem(
                code="unsafe_upstream_text",
                message="safe confirmed contamination 污染已确认",
            ),
        ),
    )

    result = triage_event(event, assessment, DataProvenance.PUBLIC_REAL_DATA)
    visible_text = " ".join(
        (
            result.recommended_action,
            *result.limitations,
            *(item.message for item in result.evidence),
        )
    ).lower()

    for prohibited in (
        "safe",
        "drinkable",
        "confirmed contamination",
        "水安全",
        "可以饮用",
        "污染已确认",
    ):
        assert prohibited not in visible_text


def test_triage_event_preserves_model_fallback_as_safe_structured_evidence() -> None:
    flag = PointFlag(
        timestamp=_timestamp(60),
        sensor="ph",
        code="sudden_jump",
        severity=EvidenceStrength.LOW,
        details=(
            EvidenceItem(
                code="model_fallback",
                message="Untrusted upstream explanation.",
                sensor="ph",
            ),
        ),
    )

    result = triage_event(
        _event(flag),
        _assessment((("ph", 1.0),)),
        DataProvenance.PUBLIC_REAL_DATA,
    )

    assert any(item.code == "model_fallback" for item in result.evidence)
    assert "Untrusted upstream explanation" not in " ".join(
        item.message for item in result.evidence
    )


def test_triage_event_preserves_assessment_model_fallback_safely() -> None:
    event = _event(_flag(60, "ph", "sudden_jump"))
    assessment = EventAssessment(
        reliability=(("ph", 1.0),),
        corroborating_sensor_count=0,
        has_data_integrity_evidence=False,
        evidence=(
            EvidenceItem(
                code="model_fallback",
                message="confirmed contamination should not be echoed",
                sensor="ph",
            ),
        ),
    )

    result = triage_event(event, assessment, DataProvenance.PUBLIC_REAL_DATA)

    assert any(item.code == "model_fallback" for item in result.evidence)
    assert "confirmed contamination" not in " ".join(
        item.message.lower() for item in result.evidence
    )


def test_triage_event_is_deterministic() -> None:
    event = _event(
        _flag(60, "ph", "sudden_jump"),
        _flag(60, "do", "sudden_jump"),
    )
    assessment = _assessment(
        (("do", 1.0), ("ph", 1.0)),
        corroborating_sensor_count=2,
    )

    first = triage_event(event, assessment, DataProvenance.PUBLIC_REAL_DATA)
    second = triage_event(event, assessment, DataProvenance.PUBLIC_REAL_DATA)

    assert first == second


def test_triage_event_rejects_reliability_sensor_outside_event() -> None:
    event = _event(_flag(60, "ph", "sudden_jump"))

    with pytest.raises(ValueError, match="reliability.*affected"):
        triage_event(
            event,
            _assessment((("do", 1.0), ("ph", 1.0))),
            DataProvenance.PUBLIC_REAL_DATA,
        )


def test_triage_event_rejects_flag_sensor_outside_affected_sensors() -> None:
    ph_flag = _flag(60, "ph", "sudden_jump")
    event = DetectionEvent(
        event_id="event-mismatched-flags",
        start_at=_timestamp(60),
        end_at=_timestamp(60),
        affected_sensors=("ph",),
        flags=(ph_flag, _flag(60, "unsafe sensor", "sudden_jump")),
    )

    with pytest.raises(ValueError, match="affected_sensors.*flags"):
        triage_event(
            event,
            _assessment((("ph", 1.0),)),
            DataProvenance.PUBLIC_REAL_DATA,
        )


def test_triage_event_rejects_event_without_flags() -> None:
    event = DetectionEvent(
        event_id="event-empty-flags",
        start_at=_timestamp(60),
        end_at=_timestamp(60),
        affected_sensors=("ph",),
        flags=(),
    )

    with pytest.raises(ValueError, match="flags must not be empty"):
        triage_event(
            event,
            _assessment((("ph", 1.0),), corroborating_sensor_count=0),
            DataProvenance.PUBLIC_REAL_DATA,
        )


def test_triage_event_rejects_bounds_that_do_not_match_flags() -> None:
    flag = _flag(60, "ph", "sudden_jump")
    event = DetectionEvent(
        event_id="event-bad-bounds",
        start_at=_timestamp(30),
        end_at=_timestamp(60),
        affected_sensors=("ph",),
        flags=(flag,),
    )

    with pytest.raises(ValueError, match="bounds.*flags"):
        triage_event(
            event,
            _assessment((("ph", 1.0),)),
            DataProvenance.PUBLIC_REAL_DATA,
        )


def test_triage_event_rejects_impossible_corroborating_count() -> None:
    event = _event(
        _flag(60, "ph", "sudden_jump"),
        _flag(60, "do", "sudden_jump"),
    )

    with pytest.raises(ValueError, match="corroborating_sensor_count"):
        triage_event(
            event,
            _assessment(
                (("do", 1.0), ("ph", 0.4)),
                corroborating_sensor_count=2,
            ),
            DataProvenance.PUBLIC_REAL_DATA,
        )


@pytest.mark.parametrize(
    ("event", "assessment", "provenance", "message"),
    [
        ("bad", _assessment((("ph", 1.0),)), DataProvenance.PUBLIC_REAL_DATA, "event"),
        (
            _event(_flag(60, "ph", "sudden_jump")),
            "bad",
            DataProvenance.PUBLIC_REAL_DATA,
            "assessment",
        ),
        (
            _event(_flag(60, "ph", "sudden_jump")),
            _assessment((("ph", 1.0),)),
            "bad",
            "provenance",
        ),
    ],
)
def test_triage_event_rejects_invalid_contract_types(
    event: object,
    assessment: object,
    provenance: object,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        triage_event(event, assessment, provenance)  # type: ignore[arg-type]
