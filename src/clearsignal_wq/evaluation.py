from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, date, timedelta

import pandas as pd

from clearsignal_wq.contracts import DetectionEvent, EventMetrics


def arima_meets_gate(
    rules_validation: EventMetrics,
    arima_validation: EventMetrics,
) -> bool:
    if not isinstance(rules_validation, EventMetrics) or not isinstance(
        arima_validation, EventMetrics
    ):
        raise TypeError("ARIMA gate inputs must be EventMetrics")
    recall_threshold = min(1.0, rules_validation.recall + 0.05)
    precision_threshold = max(0.0, rules_validation.precision - 0.05)
    invalid_alert_threshold = rules_validation.invalid_alerts_per_day + 0.10
    tolerance = 1e-12
    return (
        arima_validation.recall + tolerance >= recall_threshold
        and arima_validation.precision + tolerance >= precision_threshold
        and arima_validation.invalid_alerts_per_day
        <= invalid_alert_threshold + tolerance
    )


def evaluate_events(
    predicted_events: Iterable[DetectionEvent],
    labelled_events: Iterable[DetectionEvent],
    *,
    clean_days: float,
) -> EventMetrics:
    _validate_clean_days(clean_days)
    predicted = tuple(sorted(_validate_events(predicted_events), key=_event_sort_key))
    labelled = tuple(sorted(_validate_events(labelled_events), key=_event_sort_key))

    matched_label_indexes: set[int] = set()
    detection_delays: list[float] = []
    for prediction in predicted:
        for label_index, label in enumerate(labelled):
            if label_index in matched_label_indexes:
                continue
            if not _events_overlap(prediction, label):
                continue
            matched_label_indexes.add(label_index)
            delay = (prediction.start_at - label.start_at).total_seconds() / 60
            detection_delays.append(max(0.0, float(delay)))
            break

    matched_count = len(matched_label_indexes)
    invalid_alert_count = len(predicted) - matched_count
    if clean_days == 0.0 and invalid_alert_count:
        raise ValueError(
            "clean_days cannot be zero when unmatched predictions are present"
        )

    recall = matched_count / len(labelled) if labelled else 0.0
    precision = matched_count / len(predicted) if predicted else 0.0
    invalid_alerts_per_day = invalid_alert_count / clean_days if clean_days else 0.0
    detection_delay_minutes = (
        sum(detection_delays) / len(detection_delays) if detection_delays else 0.0
    )
    return EventMetrics(
        recall=float(recall),
        precision=float(precision),
        invalid_alerts_per_day=float(invalid_alerts_per_day),
        detection_delay_minutes=float(detection_delay_minutes),
        matched_events=matched_count,
        predicted_events=len(predicted),
        labelled_events=len(labelled),
    )


def count_clean_days(
    observation_index: pd.Index,
    labelled_events: Iterable[DetectionEvent],
) -> int:
    _validate_time_index(observation_index)
    labelled = _validate_events(labelled_events)
    observed_days = {
        timestamp.date() for timestamp in observation_index.tz_convert(UTC).normalize()
    }
    labelled_days: set[date] = set()
    for event in labelled:
        current = event.start_at.date()
        end = event.end_at.date()
        while current <= end:
            labelled_days.add(current)
            current += timedelta(days=1)
    return len(observed_days - labelled_days)


def _validate_clean_days(clean_days: object) -> None:
    if type(clean_days) is not float:
        raise TypeError("clean_days must be a float")
    if not math.isfinite(clean_days):
        raise ValueError("clean_days must be finite")
    if clean_days < 0:
        raise ValueError("clean_days must be nonnegative")


def _validate_events(
    events: Iterable[DetectionEvent],
) -> tuple[DetectionEvent, ...]:
    try:
        items = tuple(events)
    except TypeError as exc:
        raise TypeError("events must be an iterable of DetectionEvent") from exc
    if not all(isinstance(event, DetectionEvent) for event in items):
        raise TypeError("events must contain only DetectionEvent items")
    return items


def _validate_time_index(index: pd.Index) -> None:
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("observation index must be a DatetimeIndex")
    if index.tz is None:
        raise ValueError("observation DatetimeIndex must be timezone-aware")
    if index.has_duplicates:
        raise ValueError(
            "observation DatetimeIndex must not contain duplicate timestamps"
        )
    if not index.is_monotonic_increasing:
        raise ValueError("observation DatetimeIndex must be strictly increasing")


def _event_sort_key(event: DetectionEvent) -> tuple[object, ...]:
    return (
        event.start_at,
        event.end_at,
        event.event_id,
        event.affected_sensors,
    )


def _events_overlap(prediction: DetectionEvent, label: DetectionEvent) -> bool:
    return prediction.start_at <= label.end_at and label.start_at <= prediction.end_at
