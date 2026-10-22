from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pandas as pd
import pytest

from clearsignal_wq.contracts import (
    DetectionEvent,
    EvidenceItem,
    EvidenceStrength,
    PointFlag,
)
from clearsignal_wq.events import group_flags_into_events, labelled_quality_events


def _timestamp(minutes: int, timezone: str = "UTC") -> datetime:
    value = pd.Timestamp("2019-01-01 00:00", tz="UTC").tz_convert(timezone)
    return (value + pd.Timedelta(minutes=minutes)).to_pydatetime()


def _flag(minutes: int, sensor: str, code: str = "sudden_jump") -> PointFlag:
    return PointFlag(
        timestamp=_timestamp(minutes),
        sensor=sensor,
        code=code,
        severity=EvidenceStrength.MEDIUM,
        details=(
            EvidenceItem(
                code=code,
                message=f"Observed {code} for {sensor}.",
                sensor=sensor,
            ),
        ),
    )


def _event_id(
    start_at: datetime,
    end_at: datetime,
    sensors: tuple[str, ...],
) -> str:
    canonical = f"{start_at.isoformat()}|{end_at.isoformat()}|{','.join(sensors)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def test_group_flags_merges_same_sensor_at_thirty_minute_boundary() -> None:
    events = group_flags_into_events((_flag(0, "ph"), _flag(30, "ph")))

    assert len(events) == 1
    assert events[0].start_at == _timestamp(0)
    assert events[0].end_at == _timestamp(30)
    assert events[0].affected_sensors == ("ph",)
    assert events[0].flags == (_flag(0, "ph"), _flag(30, "ph"))


def test_group_flags_splits_when_adjacent_gap_exceeds_window() -> None:
    events = group_flags_into_events((_flag(0, "ph"), _flag(31, "ph")))

    assert len(events) == 2
    assert [event.start_at for event in events] == [_timestamp(0), _timestamp(31)]


def test_group_flags_merges_different_sensors_in_same_window() -> None:
    events = group_flags_into_events(
        (_flag(15, "do"), _flag(0, "ph"), _flag(30, "temp"))
    )

    assert len(events) == 1
    assert events[0].affected_sensors == ("do", "ph", "temp")
    assert tuple(flag.sensor for flag in events[0].flags) == ("ph", "do", "temp")


def test_group_flags_is_order_independent_and_event_id_is_exact() -> None:
    flags = (_flag(20, "do"), _flag(0, "ph"), _flag(10, "do"))

    first = group_flags_into_events(flags)
    second = group_flags_into_events(tuple(reversed(flags)))

    assert first == second
    assert first[0].event_id == _event_id(
        _timestamp(0),
        _timestamp(20),
        ("do", "ph"),
    )
    assert len(first[0].event_id) == 12
    assert first[0].source_label is None


def test_group_flags_uses_evidence_as_deterministic_tie_breaker() -> None:
    first_flag = PointFlag(
        timestamp=_timestamp(0),
        sensor="ph",
        code="sudden_jump",
        severity=EvidenceStrength.MEDIUM,
        details=(
            EvidenceItem(
                code="sudden_jump",
                message="Evidence B.",
                sensor="ph",
            ),
        ),
    )
    second_flag = PointFlag(
        timestamp=_timestamp(0),
        sensor="ph",
        code="sudden_jump",
        severity=EvidenceStrength.MEDIUM,
        details=(
            EvidenceItem(
                code="sudden_jump",
                message="Evidence A.",
                sensor="ph",
            ),
        ),
    )

    forward = group_flags_into_events((first_flag, second_flag))
    reversed_result = group_flags_into_events((second_flag, first_flag))

    assert forward == reversed_result
    assert [flag.details[0].message for flag in forward[0].flags] == [
        "Evidence A.",
        "Evidence B.",
    ]


@pytest.mark.parametrize("invalid", [0, -1, 30.0, True])
def test_group_flags_rejects_invalid_window(invalid: object) -> None:
    with pytest.raises((TypeError, ValueError), match="max_gap_minutes"):
        group_flags_into_events((_flag(0, "ph"),), invalid)  # type: ignore[arg-type]


def test_group_flags_rejects_non_point_flag_items() -> None:
    with pytest.raises(TypeError, match="PointFlag"):
        group_flags_into_events((_flag(0, "ph"), "bad"))  # type: ignore[arg-type]


def test_group_flags_rejects_non_iterable_input() -> None:
    with pytest.raises(TypeError, match="iterable of PointFlag"):
        group_flags_into_events(None)  # type: ignore[arg-type]


def test_group_flags_empty_input_returns_immutable_empty_result() -> None:
    assert group_flags_into_events(()) == ()


def _quality_frame(timezone: str = "UTC") -> pd.DataFrame:
    index = pd.date_range(
        "2019-01-01 00:00",
        periods=5,
        freq="15min",
        tz=timezone,
        name="datetime",
    )
    return pd.DataFrame(
        {
            "temp": [10.0, 10.1, 10.2, 10.3, 10.4],
            "temp_qual": [pd.NA, 1.0, 1.0, pd.NA, 2.0],
            "ph_qual": [pd.NA, pd.NA, 3.0, 3.0, pd.NA],
            "comment": ["ignored"] * 5,
        },
        index=index,
    )


def test_labelled_quality_events_extracts_contiguous_runs_per_sensor() -> None:
    events = labelled_quality_events(_quality_frame())

    assert len(events) == 3
    assert [
        (event.start_at, event.end_at, event.affected_sensors) for event in events
    ] == [
        (_timestamp(15), _timestamp(30), ("temp",)),
        (_timestamp(30), _timestamp(45), ("ph",)),
        (_timestamp(60), _timestamp(60), ("temp",)),
    ]
    assert all(event.source_label == "technician_data_quality" for event in events)


def test_labelled_quality_event_flags_preserve_values_without_pollution_claims() -> (
    None
):
    event = labelled_quality_events(_quality_frame())[0]

    assert len(event.flags) == 2
    assert all(flag.code == "technician_quality_label" for flag in event.flags)
    assert all(flag.severity is EvidenceStrength.HIGH for flag in event.flags)
    messages = " ".join(
        detail.message.lower() for flag in event.flags for detail in flag.details
    )
    assert "technician data-quality label" in messages
    assert "1.0" in messages
    for prohibited in ("contamination", "pollution", "safe to drink"):
        assert prohibited not in messages


def test_labelled_quality_events_have_stable_ids_and_order() -> None:
    frame = _quality_frame()

    first = labelled_quality_events(frame)
    second = labelled_quality_events(frame.copy(deep=True))

    assert first == second
    assert first == tuple(
        sorted(first, key=lambda event: (event.start_at, event.end_at, event.event_id))
    )
    assert first[0].event_id == _event_id(
        _timestamp(15),
        _timestamp(30),
        ("temp",),
    )


def test_labelled_quality_events_ignores_non_quality_columns_and_does_not_mutate() -> (
    None
):
    frame = _quality_frame()
    before = frame.copy(deep=True)
    without_comment = frame.drop(columns="comment")

    assert labelled_quality_events(frame) == labelled_quality_events(without_comment)
    pd.testing.assert_frame_equal(frame, before)


def test_labelled_quality_events_without_quality_columns_returns_empty() -> None:
    frame = _quality_frame().loc[:, ["temp", "comment"]]

    assert labelled_quality_events(frame) == ()


def test_labelled_quality_events_rejects_empty_sensor_name() -> None:
    frame = _quality_frame().rename(columns={"temp_qual": "_qual"})

    with pytest.raises(ValueError, match="sensor name"):
        labelled_quality_events(frame)


INVALID_INDEXES = [
    pd.Index(range(5)),
    pd.date_range("2019-01-01", periods=5, freq="15min"),
    pd.DatetimeIndex(
        [
            "2019-01-01 00:00:00+00:00",
            "2019-01-01 00:15:00+00:00",
            "2019-01-01 00:15:00+00:00",
            "2019-01-01 00:45:00+00:00",
            "2019-01-01 01:00:00+00:00",
        ]
    ),
    pd.DatetimeIndex(
        [
            "2019-01-01 00:15:00+00:00",
            "2019-01-01 00:00:00+00:00",
            "2019-01-01 00:30:00+00:00",
            "2019-01-01 00:45:00+00:00",
            "2019-01-01 01:00:00+00:00",
        ]
    ),
]


@pytest.mark.parametrize("index", INVALID_INDEXES)
def test_labelled_quality_events_rejects_invalid_time_index(index: pd.Index) -> None:
    frame = _quality_frame()
    frame.index = index

    with pytest.raises((TypeError, ValueError), match="DatetimeIndex"):
        labelled_quality_events(frame)


def test_labelled_quality_events_converts_aware_index_to_utc() -> None:
    frame = _quality_frame("America/New_York")

    events = labelled_quality_events(frame)

    assert events
    assert all(event.start_at.tzinfo is UTC for event in events)
    assert events[0].start_at == frame.index[1].tz_convert("UTC").to_pydatetime()


def test_labelled_quality_events_return_detection_events() -> None:
    assert all(
        isinstance(event, DetectionEvent)
        for event in labelled_quality_events(_quality_frame())
    )
