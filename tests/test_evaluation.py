from __future__ import annotations

import math
from datetime import datetime
from inspect import signature

import pandas as pd
import pytest

from clearsignal_wq.contracts import DetectionEvent, EventMetrics
from clearsignal_wq.evaluation import (
    arima_meets_gate,
    count_clean_days,
    evaluate_events,
)


def _time(minutes: int) -> datetime:
    return (
        pd.Timestamp("2019-01-01 00:00", tz="UTC") + pd.Timedelta(minutes=minutes)
    ).to_pydatetime()


def _event(
    event_id: str,
    start_minutes: int,
    end_minutes: int,
    sensor: str = "ph",
) -> DetectionEvent:
    return DetectionEvent(
        event_id=event_id,
        start_at=_time(start_minutes),
        end_at=_time(end_minutes),
        affected_sensors=(sensor,),
        flags=(),
    )


def test_event_metrics_match_hand_calculation() -> None:
    labelled = (
        _event("label-1", 10, 20),
        _event("label-2", 100, 110),
    )
    predicted = (
        _event("prediction-3", 200, 210),
        _event("prediction-1", 15, 16),
        _event("prediction-2", 50, 60),
    )

    metrics = evaluate_events(predicted, labelled, clean_days=2.0)

    assert metrics == EventMetrics(
        recall=0.5,
        precision=1 / 3,
        invalid_alerts_per_day=1.0,
        detection_delay_minutes=5.0,
        matched_events=1,
        predicted_events=3,
        labelled_events=2,
    )


def test_matching_is_one_to_one_and_stably_greedy_by_start_time() -> None:
    labelled = (_event("label", 10, 30),)
    predicted = (
        _event("later", 20, 21),
        _event("earlier", 12, 13),
    )

    metrics = evaluate_events(predicted, labelled, clean_days=1.0)

    assert metrics.matched_events == 1
    assert metrics.precision == 0.5
    assert metrics.detection_delay_minutes == 2.0


def test_prediction_before_label_has_zero_not_negative_delay() -> None:
    metrics = evaluate_events(
        (_event("prediction", 0, 15),),
        (_event("label", 10, 20),),
        clean_days=1.0,
    )

    assert metrics.detection_delay_minutes == 0.0


def test_zero_labels_and_predictions_produce_finite_zero_metrics() -> None:
    metrics = evaluate_events((), (), clean_days=0.0)

    assert metrics == EventMetrics(
        recall=0.0,
        precision=0.0,
        invalid_alerts_per_day=0.0,
        detection_delay_minutes=0.0,
        matched_events=0,
        predicted_events=0,
        labelled_events=0,
    )
    assert all(
        math.isfinite(value)
        for value in (
            metrics.recall,
            metrics.precision,
            metrics.invalid_alerts_per_day,
            metrics.detection_delay_minutes,
        )
    )


def test_zero_clean_days_with_invalid_alerts_is_explicit_error() -> None:
    with pytest.raises(ValueError, match="clean_days.*zero"):
        evaluate_events((_event("prediction", 0, 1),), (), clean_days=0.0)


@pytest.mark.parametrize("invalid", [-1.0, float("inf"), float("nan"), True, 1])
def test_clean_days_requires_finite_nonnegative_float(invalid: object) -> None:
    with pytest.raises((TypeError, ValueError), match="clean_days"):
        evaluate_events((), (), clean_days=invalid)  # type: ignore[arg-type]


def test_evaluate_events_rejects_invalid_event_items() -> None:
    with pytest.raises(TypeError, match="DetectionEvent"):
        evaluate_events(("bad",), (), clean_days=1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("predicted", "labelled"),
    [(None, ()), ((), None)],
)
def test_evaluate_events_rejects_non_iterable_inputs(
    predicted: object,
    labelled: object,
) -> None:
    with pytest.raises(TypeError, match="iterable of DetectionEvent"):
        evaluate_events(  # type: ignore[arg-type]
            predicted,
            labelled,
            clean_days=1.0,
        )


def test_evaluate_events_is_order_independent_and_does_not_mutate_inputs() -> None:
    predicted = [_event("prediction-2", 50, 60), _event("prediction-1", 15, 16)]
    labelled = [_event("label-2", 100, 110), _event("label-1", 10, 20)]
    predicted_before = list(predicted)
    labelled_before = list(labelled)

    first = evaluate_events(predicted, labelled, clean_days=2.0)
    second = evaluate_events(
        tuple(reversed(predicted)),
        tuple(reversed(labelled)),
        clean_days=2.0,
    )

    assert first == second
    assert predicted == predicted_before
    assert labelled == labelled_before


def test_count_clean_days_excludes_utc_dates_touched_by_labels() -> None:
    index = pd.DatetimeIndex(
        [
            "2019-01-01 00:00:00+00:00",
            "2019-01-01 23:45:00+00:00",
            "2019-01-02 00:00:00+00:00",
            "2019-01-02 23:45:00+00:00",
            "2019-01-03 00:00:00+00:00",
        ]
    )
    labelled = (_event("label", 10, 20),)

    assert count_clean_days(index, labelled) == 2


def test_count_clean_days_handles_event_crossing_midnight() -> None:
    index = pd.date_range("2019-01-01", periods=3, freq="1D", tz="UTC")
    labelled = (
        DetectionEvent(
            event_id="cross-day",
            start_at=pd.Timestamp("2019-01-01 23:50", tz="UTC").to_pydatetime(),
            end_at=pd.Timestamp("2019-01-02 00:10", tz="UTC").to_pydatetime(),
            affected_sensors=("ph",),
            flags=(),
        ),
    )

    assert count_clean_days(index, labelled) == 1


def test_count_clean_days_with_all_dates_labelled_returns_zero() -> None:
    index = pd.date_range("2019-01-01", periods=2, freq="1D", tz="UTC")
    labelled = (
        DetectionEvent(
            event_id="all-days",
            start_at=pd.Timestamp("2019-01-01", tz="UTC").to_pydatetime(),
            end_at=pd.Timestamp("2019-01-02 23:59", tz="UTC").to_pydatetime(),
            affected_sensors=("ph",),
            flags=(),
        ),
    )

    assert count_clean_days(index, labelled) == 0


INVALID_INDEXES = [
    pd.Index([0, 1]),
    pd.date_range("2019-01-01", periods=2, freq="1D"),
    pd.DatetimeIndex(["2019-01-01 00:00:00+00:00", "2019-01-01 00:00:00+00:00"]),
    pd.DatetimeIndex(["2019-01-02 00:00:00+00:00", "2019-01-01 00:00:00+00:00"]),
]


@pytest.mark.parametrize("index", INVALID_INDEXES)
def test_count_clean_days_rejects_invalid_index(index: pd.Index) -> None:
    with pytest.raises((TypeError, ValueError), match="DatetimeIndex"):
        count_clean_days(index, ())


def test_count_clean_days_normalizes_non_utc_index_to_utc_dates() -> None:
    index = pd.date_range(
        "2018-12-31 20:00",
        periods=2,
        freq="8h",
        tz="America/New_York",
    )

    assert count_clean_days(index, ()) == 1


def _metrics(
    *,
    recall: float,
    precision: float,
    invalid_alerts_per_day: float,
) -> EventMetrics:
    return EventMetrics(
        recall=recall,
        precision=precision,
        invalid_alerts_per_day=invalid_alerts_per_day,
        detection_delay_minutes=0.0,
        matched_events=0,
        predicted_events=0,
        labelled_events=0,
    )


def test_arima_gate_signature_has_no_test_metrics() -> None:
    parameter_names = tuple(signature(arima_meets_gate).parameters)

    assert parameter_names == ("rules_validation", "arima_validation")
    assert all("test" not in name for name in parameter_names)


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (
            _metrics(recall=1.0, precision=0.0, invalid_alerts_per_day=7.4),
            True,
        ),
        (
            _metrics(recall=0.99, precision=1.0, invalid_alerts_per_day=0.0),
            False,
        ),
        (
            _metrics(recall=1.0, precision=1.0, invalid_alerts_per_day=7.4001),
            False,
        ),
    ],
)
def test_arima_gate_uses_locked_validation_thresholds(
    candidate: EventMetrics,
    expected: bool,
) -> None:
    baseline = _metrics(
        recall=1.0,
        precision=0.0135135135,
        invalid_alerts_per_day=7.3,
    )

    assert arima_meets_gate(baseline, candidate) is expected
