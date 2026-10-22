from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pandas as pd

from clearsignal_wq.contracts import (
    DetectionEvent,
    EvidenceItem,
    EvidenceStrength,
    PointFlag,
)

_TECHNICIAN_SOURCE_LABEL = "technician_data_quality"
_TECHNICIAN_FLAG_CODE = "technician_quality_label"


def group_flags_into_events(
    flags: Iterable[PointFlag],
    max_gap_minutes: int = 30,
) -> tuple[DetectionEvent, ...]:
    _validate_max_gap(max_gap_minutes)
    ordered = tuple(sorted(_validate_flags(flags), key=_flag_sort_key))
    if not ordered:
        return ()

    max_gap = timedelta(minutes=max_gap_minutes)
    groups: list[tuple[PointFlag, ...]] = []
    current: list[PointFlag] = [ordered[0]]
    for flag in ordered[1:]:
        if flag.timestamp - current[-1].timestamp <= max_gap:
            current.append(flag)
            continue
        groups.append(tuple(current))
        current = [flag]
    groups.append(tuple(current))

    return tuple(_event_from_flags(group) for group in groups)


def labelled_quality_events(frame: pd.DataFrame) -> tuple[DetectionEvent, ...]:
    _validate_time_index(frame.index)
    events: list[DetectionEvent] = []
    for column in sorted(
        name
        for name in frame.columns
        if isinstance(name, str) and name.endswith("_qual")
    ):
        sensor = column.removesuffix("_qual")
        if not sensor:
            raise ValueError("quality column must include a sensor name before _qual")

        run: list[PointFlag] = []
        for timestamp, value in frame[column].items():
            if pd.notna(value):
                run.append(_quality_flag(timestamp, sensor, value))
                continue
            if run:
                events.append(
                    _event_from_flags(
                        tuple(run),
                        source_label=_TECHNICIAN_SOURCE_LABEL,
                    )
                )
                run = []
        if run:
            events.append(
                _event_from_flags(
                    tuple(run),
                    source_label=_TECHNICIAN_SOURCE_LABEL,
                )
            )

    return tuple(
        sorted(
            events,
            key=lambda event: (event.start_at, event.end_at, event.event_id),
        )
    )


def _validate_max_gap(max_gap_minutes: object) -> None:
    if type(max_gap_minutes) is not int:
        raise TypeError("max_gap_minutes must be an int")
    if max_gap_minutes <= 0:
        raise ValueError("max_gap_minutes must be positive")


def _validate_flags(flags: Iterable[PointFlag]) -> tuple[PointFlag, ...]:
    try:
        items = tuple(flags)
    except TypeError as exc:
        raise TypeError("flags must be an iterable of PointFlag") from exc
    if not all(isinstance(flag, PointFlag) for flag in items):
        raise TypeError("flags must contain only PointFlag items")
    return items


def _validate_time_index(index: pd.Index) -> None:
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("frame index must be a DatetimeIndex")
    if index.tz is None:
        raise ValueError("frame DatetimeIndex must be timezone-aware")
    if index.has_duplicates:
        raise ValueError("frame DatetimeIndex must not contain duplicate timestamps")
    if not index.is_monotonic_increasing:
        raise ValueError("frame DatetimeIndex must be strictly increasing")


def _flag_sort_key(flag: PointFlag) -> tuple[object, ...]:
    detail_key = tuple(
        (detail.code, detail.message, detail.sensor or "") for detail in flag.details
    )
    return (
        flag.timestamp,
        flag.sensor,
        flag.code,
        flag.severity.value,
        detail_key,
    )


def _event_from_flags(
    flags: tuple[PointFlag, ...],
    source_label: str | None = None,
) -> DetectionEvent:
    ordered = tuple(sorted(flags, key=_flag_sort_key))
    start_at = ordered[0].timestamp
    end_at = ordered[-1].timestamp
    sensors = tuple(sorted({flag.sensor for flag in ordered}))
    return DetectionEvent(
        event_id=_stable_event_id(start_at, end_at, sensors),
        start_at=start_at,
        end_at=end_at,
        affected_sensors=sensors,
        flags=ordered,
        source_label=source_label,
    )


def _stable_event_id(
    start_at: datetime,
    end_at: datetime,
    sensors: tuple[str, ...],
) -> str:
    canonical = f"{start_at.isoformat()}|{end_at.isoformat()}|{','.join(sensors)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _quality_flag(timestamp: object, sensor: str, value: object) -> PointFlag:
    message = f"Technician data-quality label for {sensor}: {value!r}."
    return PointFlag(
        timestamp=_as_utc_datetime(timestamp),
        sensor=sensor,
        code=_TECHNICIAN_FLAG_CODE,
        severity=EvidenceStrength.HIGH,
        details=(
            EvidenceItem(
                code=_TECHNICIAN_FLAG_CODE,
                message=message,
                sensor=sensor,
            ),
        ),
    )


def _as_utc_datetime(timestamp: object) -> datetime:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.tz_convert(UTC).to_pydatetime()
