from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timedelta

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from clearsignal_wq.contracts import (
    DetectionEvent,
    EventAssessment,
    EvidenceItem,
    PointFlag,
)

_RAW_SENSORS = ("temp", "cond", "ph", "do", "turb")
_CORROBORATION_WINDOW_MINUTES = 30
_RELIABLE_SENSOR_THRESHOLD = 0.6
_MISSING_WEIGHT = 0.60
_STUCK_WEIGHT = 0.45
_OUT_OF_RANGE_WEIGHT = 0.70
_QUALITY_LABEL_WEIGHT = 0.50
_MIN_DIRECTIONAL_CHANGE = {
    "temp": 0.01,
    "cond": 0.1,
    "ph": 0.01,
    "do": 0.01,
    "turb": 0.01,
}
_DATA_INTEGRITY_CODES = frozenset(
    {
        "duplicate_timestamp",
        "missing_interval",
        "out_of_physical_range",
    }
)

ReliabilityWindow = tuple[datetime, datetime]


def sensor_reliability(
    frame: pd.DataFrame,
    flags: Iterable[PointFlag],
    window: ReliabilityWindow,
) -> tuple[tuple[str, float], ...]:
    """Score raw sensors from deterministic data-quality evidence in a window."""
    _validate_frame(frame)
    ordered_flags = _validate_flags(flags)
    start_at, end_at = _validate_window(window)
    recent = frame.loc[(frame.index >= start_at) & (frame.index <= end_at)]
    recent_flags = tuple(
        flag for flag in ordered_flags if start_at <= flag.timestamp <= end_at
    )
    sensors = tuple(sorted(set(frame.columns).intersection(_RAW_SENSORS)))

    return tuple(
        (sensor, _sensor_score(sensor, recent, recent_flags)) for sensor in sensors
    )


def assess_event(
    event: DetectionEvent,
    frame: pd.DataFrame,
    flags: Iterable[PointFlag],
) -> EventAssessment:
    """Combine sensor trust and same-direction movement for one event."""
    if not isinstance(event, DetectionEvent):
        raise TypeError("event must be a DetectionEvent")
    _validate_frame(frame)
    _validate_event_consistency(event, frame)
    ordered_flags = _validate_flags(flags)
    context_flags = _validate_flags((*event.flags, *ordered_flags))
    window = (
        event.end_at - timedelta(minutes=_CORROBORATION_WINDOW_MINUTES),
        event.end_at,
    )
    all_scores = dict(sensor_reliability(frame, context_flags, window))
    affected = tuple(
        sensor for sensor in sorted(set(event.affected_sensors)) if sensor in all_scores
    )
    reliability = tuple((sensor, all_scores[sensor]) for sensor in affected)
    corroborating_count = _corroborating_sensor_count(
        affected,
        all_scores,
        frame,
        window,
    )
    integrity = _has_data_integrity_evidence(
        affected,
        event,
        context_flags,
        window,
    )
    evidence = _assessment_evidence(
        reliability,
        corroborating_count,
        integrity,
    )
    return EventAssessment(
        reliability=reliability,
        corroborating_sensor_count=corroborating_count,
        has_data_integrity_evidence=integrity,
        evidence=evidence,
    )


def _sensor_score(
    sensor: str,
    recent: pd.DataFrame,
    flags: tuple[PointFlag, ...],
) -> float:
    observation_count = len(recent)
    if observation_count == 0:
        return 0.0

    missing_ratio = float(recent[sensor].isna().mean())
    gap_ratio = _flag_ratio(flags, "stream", "missing_interval", observation_count)
    missing_ratio = max(missing_ratio, gap_ratio)
    stuck_ratio = _flag_ratio(flags, sensor, "stuck_value", observation_count)
    range_ratio = _flag_ratio(
        flags,
        sensor,
        "out_of_physical_range",
        observation_count,
    )
    quality_column = f"{sensor}_qual"
    quality_ratio = (
        float(recent[quality_column].notna().mean())
        if quality_column in recent
        else 0.0
    )
    quality_ratio = max(
        quality_ratio,
        _flag_ratio(
            flags,
            sensor,
            "technician_quality_label",
            observation_count,
        ),
    )
    deduction = (
        _MISSING_WEIGHT * missing_ratio
        + _STUCK_WEIGHT * stuck_ratio
        + _OUT_OF_RANGE_WEIGHT * range_ratio
        + _QUALITY_LABEL_WEIGHT * quality_ratio
    )
    return round(min(1.0, max(0.0, 1.0 - deduction)), 12)


def _flag_ratio(
    flags: tuple[PointFlag, ...],
    sensor: str,
    code: str,
    observation_count: int,
) -> float:
    timestamps = {
        flag.timestamp for flag in flags if flag.sensor == sensor and flag.code == code
    }
    return min(1.0, len(timestamps) / observation_count)


def _corroborating_sensor_count(
    affected: tuple[str, ...],
    scores: dict[str, float],
    frame: pd.DataFrame,
    window: ReliabilityWindow,
) -> int:
    start_at, end_at = window
    recent = frame.loc[(frame.index >= start_at) & (frame.index <= end_at)]
    directions: list[int] = []
    for sensor in affected:
        if scores[sensor] < _RELIABLE_SENSOR_THRESHOLD:
            continue
        values = recent[sensor].dropna()
        if len(values) < 2:
            continue
        change = float(values.iloc[-1]) - float(values.iloc[0])
        minimum_change = _MIN_DIRECTIONAL_CHANGE[sensor]
        if not math.isfinite(change) or abs(change) < minimum_change * (1 - 1e-9):
            continue
        directions.append(1 if change > 0 else -1)

    largest_group = max(
        (directions.count(1), directions.count(-1)),
        default=0,
    )
    return largest_group if largest_group >= 2 else 0


def _has_data_integrity_evidence(
    affected: tuple[str, ...],
    event: DetectionEvent,
    flags: tuple[PointFlag, ...],
    window: ReliabilityWindow,
) -> bool:
    if any(flag.code in _DATA_INTEGRITY_CODES for flag in event.flags):
        return True
    start_at, end_at = window
    relevant_sensors = {*affected, "stream"}
    return any(
        start_at <= flag.timestamp <= end_at
        and flag.sensor in relevant_sensors
        and flag.code in _DATA_INTEGRITY_CODES
        for flag in flags
    )


def _assessment_evidence(
    reliability: tuple[tuple[str, float], ...],
    corroborating_count: int,
    has_integrity_evidence: bool,
) -> tuple[EvidenceItem, ...]:
    evidence = [
        EvidenceItem(
            code="sensor_reliability",
            message=f"Recent deterministic reliability score: {score:.3f}.",
            sensor=sensor,
        )
        for sensor, score in reliability
    ]
    if has_integrity_evidence:
        evidence.append(
            EvidenceItem(
                code="data_integrity_evidence",
                message="The event contains deterministic data-integrity evidence.",
            )
        )
    corroboration_code = (
        "cross_sensor_corroboration"
        if corroborating_count >= 2
        else "cross_sensor_corroboration_absent"
    )
    evidence.append(
        EvidenceItem(
            code=corroboration_code,
            message=(
                f"{corroborating_count} reliable affected sensors changed in the "
                f"same direction within {_CORROBORATION_WINDOW_MINUTES} minutes."
            ),
        )
    )
    return tuple(evidence)


def _validate_frame(frame: object) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a DataFrame")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("frame index must be a DatetimeIndex")
    if frame.index.tz is None:
        raise ValueError("frame DatetimeIndex must be timezone-aware")
    if frame.index.has_duplicates:
        raise ValueError("frame DatetimeIndex must not contain duplicate timestamps")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("frame DatetimeIndex must be strictly increasing")
    for sensor in set(frame.columns).intersection(_RAW_SENSORS):
        series = frame[sensor]
        if is_bool_dtype(series.dtype) or not is_numeric_dtype(series.dtype):
            raise TypeError(f"{sensor} must have a real numeric dtype")
        if not all(math.isfinite(float(value)) for value in series.dropna()):
            raise ValueError(f"{sensor} contains a non-finite raw value")


def _validate_event_consistency(
    event: DetectionEvent,
    frame: pd.DataFrame,
) -> None:
    affected = set(event.affected_sensors)
    flag_sensors = {flag.sensor for flag in event.flags}
    if len(affected) != len(event.affected_sensors):
        raise ValueError("event affected_sensors must not contain duplicates")
    if affected != flag_sensors:
        raise ValueError("event affected_sensors must match event flags")
    unsupported = affected.difference((*_RAW_SENSORS, "stream"))
    if unsupported:
        raise ValueError("event contains an unsupported affected sensor")
    missing = affected.intersection(_RAW_SENSORS).difference(frame.columns)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"affected sensor missing from frame: {names}")


def _validate_flags(flags: Iterable[PointFlag]) -> tuple[PointFlag, ...]:
    try:
        items = tuple(flags)
    except TypeError as exc:
        raise TypeError("flags must be an iterable of PointFlag") from exc
    if not all(isinstance(flag, PointFlag) for flag in items):
        raise TypeError("flags must contain only PointFlag items")
    return tuple(
        sorted(items, key=lambda flag: (flag.timestamp, flag.sensor, flag.code))
    )


def _validate_window(window: object) -> ReliabilityWindow:
    if not isinstance(window, tuple) or len(window) != 2:
        raise TypeError("window must be a two-item tuple")
    start_at, end_at = window
    for value in (start_at, end_at):
        if not isinstance(value, datetime):
            raise TypeError("window values must be datetimes")
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("window values must be timezone-aware UTC datetimes")
    if start_at > end_at:
        raise ValueError("window start must not be later than window end")
    return start_at, end_at
