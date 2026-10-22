from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from clearsignal_wq.contracts import (
    DetectionEvent,
    EvidenceItem,
    EvidenceStrength,
    PointFlag,
)
from clearsignal_wq.reliability import assess_event, sensor_reliability


def _timestamp(minutes: int) -> datetime:
    return datetime(2019, 1, 1, tzinfo=UTC) + pd.Timedelta(minutes=minutes)


def _frame() -> pd.DataFrame:
    index = pd.date_range(
        "2019-01-01 00:00",
        periods=5,
        freq="15min",
        tz="UTC",
        name="datetime",
    )
    return pd.DataFrame(
        {
            "temp": [10.0, 10.1, 10.2, 10.3, 10.4],
            "cond": [100.0, 101.0, 102.0, 103.0, 104.0],
            "ph": [7.0, 7.0, 7.1, 7.2, 7.3],
            "do": [8.0, 8.0, 8.1, 8.2, 8.3],
            "ph_qual": [pd.NA] * 5,
        },
        index=index,
    )


def _flag(
    minutes: int,
    sensor: str,
    code: str,
    severity: EvidenceStrength = EvidenceStrength.MEDIUM,
) -> PointFlag:
    return PointFlag(
        timestamp=_timestamp(minutes),
        sensor=sensor,
        code=code,
        severity=severity,
        details=(
            EvidenceItem(
                code=code,
                message=f"Observed {code} for {sensor}.",
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


def _score(result: tuple[tuple[str, float], ...], sensor: str) -> float:
    return dict(result)[sensor]


def test_each_supported_quality_signal_reduces_sensor_reliability() -> None:
    frame = _frame()
    window = (_timestamp(0), _timestamp(60))
    baseline = _score(sensor_reliability(frame, (), window), "ph")

    missing = frame.copy(deep=True)
    missing.loc[_timestamp(30), "ph"] = pd.NA

    quality = frame.copy(deep=True)
    quality.loc[_timestamp(30), "ph_qual"] = 1.0

    results = (
        sensor_reliability(missing, (), window),
        sensor_reliability(frame, (_flag(30, "ph", "stuck_value"),), window),
        sensor_reliability(
            frame,
            (_flag(30, "ph", "out_of_physical_range"),),
            window,
        ),
        sensor_reliability(quality, (), window),
    )

    assert baseline == 1.0
    assert all(_score(result, "ph") < baseline for result in results)


def test_reliability_is_bounded_deterministic_and_does_not_mutate_frame() -> None:
    frame = _frame()
    frame["ph"] = pd.array([pd.NA] * len(frame), dtype="Float64")
    frame["ph_qual"] = 1.0
    before = frame.copy(deep=True)
    flags = tuple(
        _flag(minutes, "ph", code)
        for minutes in (0, 15, 30, 45, 60)
        for code in ("stuck_value", "out_of_physical_range")
    )
    window = (_timestamp(0), _timestamp(60))

    first = sensor_reliability(frame, flags, window)
    second = sensor_reliability(frame.copy(deep=True), tuple(reversed(flags)), window)

    assert first == second
    assert isinstance(first, tuple)
    assert all(0.0 <= score <= 1.0 for _, score in first)
    assert _score(first, "ph") == 0.0
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("evidence", ["missing", "quality"])
def test_complete_unreliable_evidence_falls_below_threshold(evidence: str) -> None:
    frame = _frame()
    if evidence == "missing":
        frame["ph"] = pd.array([pd.NA] * len(frame), dtype="Float64")
    else:
        frame["ph_qual"] = 1.0

    result = sensor_reliability(frame, (), (_timestamp(0), _timestamp(60)))

    assert _score(result, "ph") < 0.6


def test_assess_event_counts_reliable_same_direction_sensors() -> None:
    frame = _frame()
    event = _event(
        _flag(60, "ph", "sudden_jump"),
        _flag(60, "do", "sudden_jump"),
    )

    assessment = assess_event(event, frame, event.flags)

    assert assessment.corroborating_sensor_count == 2
    assert dict(assessment.reliability) == {"do": 1.0, "ph": 1.0}
    assert assessment.has_data_integrity_evidence is False
    assert any(
        item.code == "cross_sensor_corroboration" for item in assessment.evidence
    )


def test_assess_event_excludes_low_reliability_sensor_from_corroboration() -> None:
    frame = _frame()
    frame["ph_qual"] = 1.0
    event = _event(
        _flag(60, "ph", "sudden_jump"),
        _flag(60, "do", "sudden_jump"),
    )
    reliability_flags = tuple(
        _flag(minutes, "ph", code)
        for minutes in (30, 45, 60)
        for code in ("stuck_value", "out_of_physical_range")
    )

    assessment = assess_event(event, frame, (*event.flags, *reliability_flags))

    assert assessment.corroborating_sensor_count == 0
    assert dict(assessment.reliability)["ph"] < 0.6
    assert dict(assessment.reliability)["do"] == 1.0


def test_assess_event_does_not_count_opposite_direction_changes() -> None:
    frame = _frame()
    frame["do"] = [8.4, 8.3, 8.2, 8.1, 8.0]
    event = _event(
        _flag(60, "ph", "sudden_jump"),
        _flag(60, "do", "sudden_jump"),
    )

    assessment = assess_event(event, frame, event.flags)

    assert assessment.corroborating_sensor_count == 0


def test_assess_event_ignores_floating_point_noise() -> None:
    frame = _frame()
    frame["ph"] = [7.0, 7.0, 7.0, 7.0, 7.0 + 1e-8]
    frame["do"] = [8.0, 8.0, 8.0, 8.0, 8.0 + 1e-8]
    event = _event(
        _flag(60, "ph", "sudden_jump"),
        _flag(60, "do", "sudden_jump"),
    )

    assessment = assess_event(event, frame, event.flags)

    assert assessment.corroborating_sensor_count == 0


def test_assess_event_marks_data_integrity_evidence() -> None:
    frame = _frame()
    flag = _flag(
        60,
        "ph",
        "out_of_physical_range",
        EvidenceStrength.HIGH,
    )

    assessment = assess_event(_event(flag), frame, (flag,))

    assert assessment.has_data_integrity_evidence is True
    assert any(item.code == "data_integrity_evidence" for item in assessment.evidence)


def test_quality_label_reduces_reliability_not_integrity() -> None:
    frame = _frame()
    event = _event(_flag(60, "ph", "sudden_jump"))
    quality_flag = _flag(
        45,
        "ph",
        "technician_quality_label",
        EvidenceStrength.HIGH,
    )

    assessment = assess_event(event, frame, (*event.flags, quality_flag))

    assert assessment.has_data_integrity_evidence is False
    assert dict(assessment.reliability)["ph"] < 1.0


def test_assess_event_never_drops_early_event_integrity_evidence() -> None:
    frame = _frame()
    event = DetectionEvent(
        event_id="event-early-integrity",
        start_at=_timestamp(0),
        end_at=_timestamp(60),
        affected_sensors=("do", "ph", "stream"),
        flags=(
            _flag(0, "stream", "missing_interval", EvidenceStrength.HIGH),
            _flag(60, "ph", "sudden_jump"),
            _flag(60, "do", "sudden_jump"),
        ),
    )

    assessment = assess_event(event, frame, ())

    assert assessment.has_data_integrity_evidence is True


def test_assess_event_accepts_equivalent_affected_sensor_order() -> None:
    frame = _frame()
    event = DetectionEvent(
        event_id="event-order",
        start_at=_timestamp(60),
        end_at=_timestamp(60),
        affected_sensors=("ph", "do"),
        flags=(
            _flag(60, "ph", "sudden_jump"),
            _flag(60, "do", "sudden_jump"),
        ),
    )

    assessment = assess_event(event, frame, event.flags)

    assert assessment.corroborating_sensor_count == 2


def test_assess_event_rejects_inconsistent_affected_sensors() -> None:
    frame = _frame()
    flag = _flag(60, "ph", "sudden_jump")
    event = DetectionEvent(
        event_id="event-002",
        start_at=flag.timestamp,
        end_at=flag.timestamp,
        affected_sensors=("do", "ph"),
        flags=(flag,),
    )

    with pytest.raises(ValueError, match="affected_sensors.*flags"):
        assess_event(event, frame, event.flags)


def test_assess_event_rejects_affected_sensor_missing_from_frame() -> None:
    frame = _frame().drop(columns="ph")
    flag = _flag(60, "ph", "sudden_jump")

    with pytest.raises(ValueError, match="missing from frame"):
        assess_event(_event(flag), frame, (flag,))


@pytest.mark.parametrize(
    "window",
    [
        (_timestamp(60), _timestamp(0)),
        (datetime(2019, 1, 1), _timestamp(60)),
        (_timestamp(0),),
        "bad",
    ],
)
def test_sensor_reliability_rejects_invalid_windows(window: object) -> None:
    with pytest.raises((TypeError, ValueError), match="window"):
        sensor_reliability(_frame(), (), window)  # type: ignore[arg-type]


def test_sensor_reliability_rejects_invalid_flag_items() -> None:
    with pytest.raises(TypeError, match="PointFlag"):
        sensor_reliability(
            _frame(),
            ("bad",),  # type: ignore[arg-type]
            (_timestamp(0), _timestamp(60)),
        )


def test_sensor_reliability_rejects_non_numeric_raw_values() -> None:
    frame = _frame()
    frame["ph"] = frame["ph"].astype(object)
    frame.loc[_timestamp(30), "ph"] = "bad"

    with pytest.raises(TypeError, match="ph.*numeric"):
        sensor_reliability(frame, (), (_timestamp(0), _timestamp(60)))
