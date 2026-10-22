from dataclasses import FrozenInstanceError
from datetime import UTC
from types import SimpleNamespace

import pandas as pd
import pytest

from clearsignal_wq.contracts import EvidenceItem, EvidenceStrength, PointFlag
from clearsignal_wq.detectors import (
    ArimaConfig,
    FittedRuleDetector,
    RuleConfig,
    detect_arima_anomalies,
    detect_rule_anomalies,
    fit_arima_detector,
    fit_rule_detector,
)

ALLOWED_CODES = {
    "missing_interval",
    "out_of_physical_range",
    "stuck_value",
    "sudden_jump",
}
INVALID_TIME_INDEX_CASES = (
    (pd.Index([0, 1, 2]), TypeError, "DatetimeIndex"),
    (
        pd.date_range("2019-01-02", periods=3, freq="15min"),
        ValueError,
        "timezone-aware",
    ),
    (
        pd.DatetimeIndex(
            [
                "2019-01-02 00:00:00+00:00",
                "2019-01-02 00:15:00+00:00",
                "2019-01-02 00:15:00+00:00",
            ]
        ),
        ValueError,
        "duplicate",
    ),
    (
        pd.DatetimeIndex(
            [
                "2019-01-02 00:15:00+00:00",
                "2019-01-02 00:00:00+00:00",
                "2019-01-02 00:30:00+00:00",
            ]
        ),
        ValueError,
        "strictly increasing",
    ),
)
INVALID_RAW_SENSOR_DTYPES = (
    (["1.0", "2.0", "3.0"], "string"),
    ([True, False, True], "bool"),
    ([1 + 0j, 2 + 0j, 3 + 0j], "complex128"),
)
VALID_RAW_SENSOR_DTYPES = (
    ([1, 2, 3], "int64"),
    ([1.0, 2.0, 3.0], "float64"),
    ([1, pd.NA, 3], "Int64"),
    ([1.0, pd.NA, 3.0], "Float64"),
)


def _frame(
    rows: int,
    *,
    start: str = "2019-01-01 00:00",
    frequency: str = "15min",
    include_turb: bool = False,
) -> pd.DataFrame:
    index = pd.date_range(start, periods=rows, freq=frequency, tz="UTC")
    values = {
        "temp": [10.0 + index for index in range(rows)],
        "cond": [100.0 + 2 * index for index in range(rows)],
        "ph": [7.0 + 0.01 * index for index in range(rows)],
        "do": [8.0 + 0.02 * index for index in range(rows)],
        "temp_cor": [999.0] * rows,
        "temp_qual": [1.0] * rows,
    }
    if include_turb:
        values["turb"] = [1.0 + 0.1 * index for index in range(rows)]
        values["turb_cor"] = [999.0] * rows
        values["turb_qual"] = [1.0] * rows
    return pd.DataFrame(values, index=index)


def _flags_with_code(flags: tuple[PointFlag, ...], code: str) -> list[PointFlag]:
    return [flag for flag in flags if flag.code == code]


def _single_sensor_frame(values: list[float], start: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"temp": values},
        index=pd.date_range(start, periods=len(values), freq="15min", tz="UTC"),
    )


def test_rule_config_is_frozen_slotted_and_validates_positive_types() -> None:
    config = RuleConfig()

    assert config.expected_interval_minutes == 15
    assert config.stuck_run_points == 8
    assert config.jump_mad_multiplier == 8.0
    assert not hasattr(config, "__dict__")
    with pytest.raises(FrozenInstanceError):
        config.stuck_run_points = 9

    for changes in (
        {"expected_interval_minutes": True},
        {"expected_interval_minutes": 0},
        {"stuck_run_points": 8.0},
        {"stuck_run_points": -1},
        {"jump_mad_multiplier": True},
        {"jump_mad_multiplier": 0.0},
    ):
        with pytest.raises((TypeError, ValueError)):
            RuleConfig(**changes)


def test_fit_uses_only_raw_sensor_differences_and_is_immutable() -> None:
    train = _frame(5, include_turb=True)
    before = train.copy(deep=True)

    fitted = fit_rule_detector(train)

    pd.testing.assert_frame_equal(train, before)
    assert isinstance(fitted, FittedRuleDetector)
    assert not hasattr(fitted, "__dict__")
    assert tuple(item[0] for item in fitted.difference_stats) == (
        "cond",
        "do",
        "ph",
        "temp",
        "turb",
    )
    assert all(
        not sensor.endswith(("_cor", "_qual"))
        for sensor, _, _ in fitted.difference_stats
    )
    assert fitted == fit_rule_detector(train.copy(deep=True))
    with pytest.raises(FrozenInstanceError):
        fitted.config = RuleConfig(stuck_run_points=9)


@pytest.mark.parametrize(
    ("config", "difference_stats", "error", "message"),
    [
        (object(), (), TypeError, "config"),
        (RuleConfig(), [], TypeError, "difference_stats"),
        (RuleConfig(), (("temp", 0.0),), TypeError, "difference_stats"),
        (RuleConfig(), (("temp_cor", 0.0, 0.0),), ValueError, "sensor"),
        (RuleConfig(), (("temp", 0, 0.0),), TypeError, "median"),
        (RuleConfig(), (("temp", 0.0, 0),), TypeError, "MAD"),
        (RuleConfig(), (("temp", float("inf"), 0.0),), ValueError, "non-finite"),
        (RuleConfig(), (("temp", 0.0, float("nan")),), ValueError, "non-finite"),
        (RuleConfig(), (("temp", 0.0, -1.0),), ValueError, "nonnegative"),
        (
            RuleConfig(),
            (("temp", 0.0, 0.0), ("temp", 1.0, 0.0)),
            ValueError,
            "unique",
        ),
        (
            RuleConfig(),
            (("temp", 0.0, 0.0), ("cond", 1.0, 0.0)),
            ValueError,
            "sorted",
        ),
    ],
)
def test_fitted_rule_detector_rejects_invalid_direct_construction(
    config: object,
    difference_stats: object,
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        FittedRuleDetector(config=config, difference_stats=difference_stats)


@pytest.mark.parametrize("non_finite", [float("inf"), float("-inf")])
def test_fit_rejects_non_finite_raw_sensor_differences(non_finite: float) -> None:
    train = _frame(3)
    train["temp"] = [0.0, non_finite, 1.0]

    with pytest.raises(ValueError, match="temp.*non-finite"):
        fit_rule_detector(train)


@pytest.mark.parametrize("non_finite", [float("inf"), float("-inf")])
def test_fit_rejects_repeated_non_finite_raw_values(non_finite: float) -> None:
    train = _frame(3)
    train["temp"] = [non_finite] * len(train)

    with pytest.raises(ValueError, match="temp.*non-finite"):
        fit_rule_detector(train)


def test_fit_allows_missing_values_without_creating_non_finite_stats() -> None:
    train = _frame(3)
    train["temp"] = [0.0, float("nan"), 1.0]

    fitted = fit_rule_detector(train)

    assert "temp" not in {sensor for sensor, _, _ in fitted.difference_stats}


@pytest.mark.parametrize(("values", "dtype"), INVALID_RAW_SENSOR_DTYPES)
def test_fit_rejects_non_real_numeric_sensor_dtypes(
    values: list[object],
    dtype: str,
) -> None:
    train = _frame(3)
    train["temp"] = pd.array(values, dtype=dtype)

    with pytest.raises(TypeError, match="temp.*real numeric dtype"):
        fit_rule_detector(train)


@pytest.mark.parametrize(("values", "dtype"), VALID_RAW_SENSOR_DTYPES)
def test_fit_accepts_real_numeric_sensor_dtypes(
    values: list[object],
    dtype: str,
) -> None:
    train = _frame(3)
    train["temp"] = pd.array(values, dtype=dtype)

    fitted = fit_rule_detector(train)

    assert isinstance(fitted, FittedRuleDetector)


@pytest.mark.parametrize("dtype", ["uint8", "uint64", "UInt8"])
def test_unsigned_decreases_use_safe_negative_differences(dtype: str) -> None:
    train = _frame(3)
    train["temp"] = pd.array([3, 2, 1], dtype=dtype)
    frame = _frame(3, start="2019-01-02")
    frame["temp"] = pd.array([6, 5, 4], dtype=dtype)
    train_before = train.copy(deep=True)
    frame_before = frame.copy(deep=True)

    fitted = fit_rule_detector(train)
    flags = detect_rule_anomalies(frame, fitted)

    assert [
        (sensor, median, mad)
        for sensor, median, mad in fitted.difference_stats
        if sensor == "temp"
    ] == [("temp", -1.0, 0.0)]
    assert not any(
        flag.sensor == "temp" and flag.code == "sudden_jump" for flag in flags
    )
    pd.testing.assert_frame_equal(train, train_before)
    pd.testing.assert_frame_equal(frame, frame_before)


def test_fit_rejects_non_finite_difference_from_finite_extreme_values() -> None:
    train = _frame(3)
    train["temp"] = [-1e308, 1e308, 1e308]
    before = train.copy(deep=True)

    with pytest.raises(ValueError, match="temp.*non-finite.*difference"):
        fit_rule_detector(train)

    pd.testing.assert_frame_equal(train, before)


@pytest.mark.parametrize(
    ("index", "error", "message"),
    INVALID_TIME_INDEX_CASES,
)
def test_fit_rejects_invalid_time_indexes(
    index: pd.Index,
    error: type[Exception],
    message: str,
) -> None:
    train = _frame(3)
    train.index = index

    with pytest.raises(error, match=message):
        fit_rule_detector(train)


def test_gap_larger_than_expected_interval_flags_later_timestamp() -> None:
    train = _frame(5)
    frame = _frame(3)
    frame.index = pd.DatetimeIndex(
        [
            "2019-01-02 00:00:00+00:00",
            "2019-01-02 00:15:00+00:00",
            "2019-01-02 00:45:00+00:00",
        ]
    )

    flags = _flags_with_code(
        detect_rule_anomalies(frame, fit_rule_detector(train)),
        "missing_interval",
    )

    assert len(flags) == 1
    assert flags[0].timestamp == frame.index[2].to_pydatetime()
    assert flags[0].sensor == "stream"
    assert flags[0].severity is EvidenceStrength.HIGH
    assert flags[0].details == (
        EvidenceItem(
            code="missing_interval",
            message="Observed gap: 30 minutes; expected at most 15 minutes.",
            sensor="stream",
        ),
    )


@pytest.mark.parametrize(
    ("index", "error", "message"),
    INVALID_TIME_INDEX_CASES,
)
def test_detect_rejects_invalid_time_indexes(
    index: pd.Index,
    error: type[Exception],
    message: str,
) -> None:
    train = _frame(5)
    frame = _frame(3, start="2019-01-02")
    frame.index = index

    with pytest.raises(error, match=message):
        detect_rule_anomalies(frame, fit_rule_detector(train))


def test_detect_converts_timezone_aware_index_to_utc_python_datetime() -> None:
    train = _frame(5)
    frame = _frame(3, start="2019-01-02")
    frame.index = frame.index.tz_convert("America/New_York")
    frame.loc[frame.index[1], "ph"] = 15.0

    flags = detect_rule_anomalies(frame, fit_rule_detector(train))
    physical_flag = next(
        flag
        for flag in flags
        if flag.sensor == "ph" and flag.code == "out_of_physical_range"
    )

    assert physical_flag.timestamp == frame.index[1].tz_convert("UTC").to_pydatetime()
    assert physical_flag.timestamp.tzinfo is UTC


@pytest.mark.parametrize("sensor", ["temp", "cond", "ph", "do", "turb"])
@pytest.mark.parametrize("non_finite", [float("inf"), float("-inf")])
def test_detect_rejects_non_finite_raw_sensor_values(
    sensor: str,
    non_finite: float,
) -> None:
    include_turb = sensor == "turb"
    train = _frame(3, include_turb=include_turb)
    frame = _frame(3, start="2019-01-02", include_turb=include_turb)
    frame.loc[frame.index[1], sensor] = non_finite

    with pytest.raises(ValueError, match=rf"{sensor}.*non-finite"):
        detect_rule_anomalies(frame, fit_rule_detector(train))


@pytest.mark.parametrize("sensor", ["temp", "cond", "ph", "do", "turb"])
def test_detect_allows_missing_raw_sensor_values(sensor: str) -> None:
    include_turb = sensor == "turb"
    train = _frame(3, include_turb=include_turb)
    frame = _frame(3, start="2019-01-02", include_turb=include_turb)
    frame.loc[frame.index[1], sensor] = float("nan")

    flags = detect_rule_anomalies(frame, fit_rule_detector(train))

    assert isinstance(flags, tuple)


@pytest.mark.parametrize(("values", "dtype"), INVALID_RAW_SENSOR_DTYPES)
def test_detect_rejects_non_real_numeric_sensor_dtypes(
    values: list[object],
    dtype: str,
) -> None:
    train = _frame(3)
    frame = _frame(3, start="2019-01-02")
    frame["temp"] = pd.array(values, dtype=dtype)

    with pytest.raises(TypeError, match="temp.*real numeric dtype"):
        detect_rule_anomalies(frame, fit_rule_detector(train))


@pytest.mark.parametrize(("values", "dtype"), VALID_RAW_SENSOR_DTYPES)
def test_detect_accepts_real_numeric_sensor_dtypes(
    values: list[object],
    dtype: str,
) -> None:
    train = _frame(3)
    frame = _frame(3, start="2019-01-02")
    frame["temp"] = pd.array(values, dtype=dtype)

    flags = detect_rule_anomalies(frame, fit_rule_detector(train))

    assert isinstance(flags, tuple)


def test_detect_rejects_non_finite_difference_from_finite_extreme_values() -> None:
    train = _frame(3)
    frame = _frame(3, start="2019-01-02")
    frame["temp"] = [-1e308, 1e308, 1e308]
    before = frame.copy(deep=True)

    with pytest.raises(ValueError, match="temp.*non-finite.*difference"):
        detect_rule_anomalies(frame, fit_rule_detector(train))

    pd.testing.assert_frame_equal(frame, before)


def test_stuck_value_flags_only_when_eighth_equal_non_null_value_arrives() -> None:
    train = _frame(5)
    frame = _frame(10, start="2019-01-02")
    frame["temp"] = [1.0] * 9 + [2.0]

    flags = [
        flag
        for flag in detect_rule_anomalies(frame, fit_rule_detector(train))
        if flag.code == "stuck_value" and flag.sensor == "temp"
    ]

    assert len(flags) == 1
    assert flags[0].timestamp == frame.index[7].to_pydatetime()


@pytest.mark.parametrize("sensor", ["temp", "cond", "ph", "do", "turb"])
def test_stuck_detection_does_not_require_fitted_difference_stats(
    sensor: str,
) -> None:
    include_turb = sensor == "turb"
    train = _frame(1, include_turb=include_turb)
    frame = _frame(8, start="2019-01-02", include_turb=include_turb)
    frame[sensor] = [3.0] * len(frame)
    fitted = fit_rule_detector(train)

    flags = detect_rule_anomalies(frame, fitted)

    assert fitted.difference_stats == ()
    assert any(
        flag.sensor == sensor
        and flag.code == "stuck_value"
        and flag.timestamp == frame.index[-1].to_pydatetime()
        for flag in flags
    )
    assert not any(
        flag.sensor == sensor and flag.code == "sudden_jump" for flag in flags
    )


@pytest.mark.parametrize(
    ("sensor", "value"),
    [("ph", -0.1), ("ph", 14.1), ("do", -0.1)],
)
def test_ph_and_do_physical_bounds_are_data_integrity_flags(
    sensor: str, value: float
) -> None:
    train = _frame(5)
    frame = _frame(3, start="2019-01-02")
    frame.loc[frame.index[1], sensor] = value

    flags = [
        flag
        for flag in detect_rule_anomalies(frame, fit_rule_detector(train))
        if flag.code == "out_of_physical_range" and flag.sensor == sensor
    ]

    assert len(flags) == 1
    assert flags[0].severity is EvidenceStrength.HIGH
    message = flags[0].details[0].message.lower()
    assert "data-integrity" in message
    assert "safe to drink" not in message
    assert "contamination" not in message


@pytest.mark.parametrize(
    ("sensor", "value"),
    [("ph", 0.0), ("ph", 14.0), ("do", 0.0)],
)
def test_ph_and_do_physical_boundaries_are_valid(sensor: str, value: float) -> None:
    train = _frame(5)
    frame = _frame(3, start="2019-01-02")
    frame.loc[frame.index[1], sensor] = value

    flags = detect_rule_anomalies(frame, fit_rule_detector(train))

    assert not any(
        flag.code == "out_of_physical_range" and flag.sensor == sensor for flag in flags
    )


def test_training_median_and_mad_control_sudden_jump_threshold() -> None:
    train = _frame(5)
    train["temp"] = [0.0, 1.0, 3.0, 6.0, 10.0]
    fitted = fit_rule_detector(train, RuleConfig(jump_mad_multiplier=2.0))
    frame = _frame(3, start="2019-01-02")
    frame["temp"] = [20.0, 22.0, 30.0]

    flags = [
        flag
        for flag in detect_rule_anomalies(frame, fitted)
        if flag.code == "sudden_jump" and flag.sensor == "temp"
    ]

    assert [
        (sensor, median, mad)
        for sensor, median, mad in fitted.difference_stats
        if sensor == "temp"
    ] == [("temp", 2.5, 1.0)]
    assert [flag.timestamp for flag in flags] == [frame.index[2].to_pydatetime()]


def test_validation_terminal_extreme_does_not_change_earlier_jump_decision() -> None:
    train = _frame(5)
    train["temp"] = [0.0, 1.0, 3.0, 6.0, 10.0]
    fitted = fit_rule_detector(train, RuleConfig(jump_mad_multiplier=2.0))
    validation = _frame(5, start="2019-01-02")
    validation["temp"] = [0.0, 6.0, 7.0, 8.0, 9.0]
    extreme_validation = validation.copy(deep=True)
    extreme_validation.loc[extreme_validation.index[-1], "temp"] = 1_000_000.0
    pd.testing.assert_frame_equal(
        validation.iloc[:-1],
        extreme_validation.iloc[:-1],
    )

    baseline_flags = detect_rule_anomalies(validation, fitted)
    extreme_flags = detect_rule_anomalies(extreme_validation, fitted)
    earlier_timestamp = validation.index[1].to_pydatetime()

    def earlier_temp_jumps(flags: tuple[PointFlag, ...]) -> tuple[PointFlag, ...]:
        return tuple(
            flag
            for flag in flags
            if flag.sensor == "temp"
            and flag.code == "sudden_jump"
            and flag.timestamp < validation.index[-1].to_pydatetime()
        )

    assert [flag.timestamp for flag in earlier_temp_jumps(baseline_flags)] == [
        earlier_timestamp
    ]
    assert earlier_temp_jumps(extreme_flags) == earlier_temp_jumps(baseline_flags)


def test_optional_turbidity_is_fitted_and_detected() -> None:
    train = _frame(5, include_turb=True)
    validation = _frame(3, start="2019-01-02", include_turb=True)
    validation["turb"] = [1.0, 1.1, 5.0]

    fitted = fit_rule_detector(train)
    flags = detect_rule_anomalies(validation, fitted)

    assert "turb" in {sensor for sensor, _, _ in fitted.difference_stats}
    assert any(flag.sensor == "turb" and flag.code == "sudden_jump" for flag in flags)


def test_zero_mad_flags_any_difference_away_from_training_median() -> None:
    train = _frame(5)
    train["cond"] = [0.0, 1.0, 2.0, 3.0, 4.0]
    validation = _frame(3, start="2019-01-02")
    validation["cond"] = [10.0, 11.0, 13.0]

    fitted = fit_rule_detector(train)
    flags = detect_rule_anomalies(validation, fitted)

    assert ("cond", 1.0, 0.0) in fitted.difference_stats
    assert any(
        flag.timestamp == validation.index[2].to_pydatetime()
        and flag.sensor == "cond"
        and flag.code == "sudden_jump"
        for flag in flags
    )


def test_output_is_stably_sorted_deterministic_and_does_not_mutate_input() -> None:
    train = _frame(5, include_turb=True)
    frame = _frame(9, start="2019-01-02", include_turb=True)
    frame["temp"] = [2.0] * 9
    frame.loc[frame.index[3], "ph"] = 15.0
    frame.loc[frame.index[2], "do"] = -1.0
    before = frame.copy(deep=True)
    fitted = fit_rule_detector(train)

    first = detect_rule_anomalies(frame, fitted)
    second = detect_rule_anomalies(frame, fitted)

    assert first == second
    assert first == tuple(
        sorted(first, key=lambda flag: (flag.timestamp, flag.sensor, flag.code))
    )
    assert {flag.code for flag in first} <= ALLOWED_CODES
    assert all(flag.timestamp.tzinfo is UTC for flag in first)
    pd.testing.assert_frame_equal(frame, before)


def test_arima_uses_fixed_order_training_residual_threshold_and_no_future_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[pd.Series, tuple[int, int, int], str]] = []

    class FakeArima:
        def __init__(
            self,
            endog: pd.Series,
            *,
            order: tuple[int, int, int],
            enforce_stationarity: bool,
            enforce_invertibility: bool,
        ) -> None:
            del enforce_stationarity, enforce_invertibility
            self.endog = endog.copy(deep=True)
            self.order = order
            calls.append((self.endog, order, "init"))

        def fit(self) -> SimpleNamespace:
            calls.append((self.endog, self.order, "fit"))
            return SimpleNamespace(
                params=pd.Series([0.1, 0.2, 0.3]),
                resid=pd.Series(
                    [0.0, 1.0, 1.0, 2.0],
                    index=self.endog.index,
                ),
                mle_retvals={"converged": True},
            )

        def filter(self, params: object) -> SimpleNamespace:
            del params
            calls.append((self.endog, self.order, "filter"))
            residuals = [0.0] * len(self.endog)
            residuals[-1] = 10.0
            return SimpleNamespace(resid=pd.Series(residuals, index=self.endog.index))

    monkeypatch.setattr("clearsignal_wq.detectors.ARIMA", FakeArima)
    train = _single_sensor_frame([1.0, 2.0, 3.0, 4.0], "2019-01-01")
    validation = _single_sensor_frame(
        [100.0, 101.0, 102.0, 1_000_000.0],
        "2019-01-02",
    )
    validation_before = validation.copy(deep=True)

    fitted = fit_arima_detector(train)
    flags = detect_arima_anomalies(validation, fitted)

    assert ArimaConfig().order == (2, 1, 2)
    assert ArimaConfig().residual_mad_multiplier == 6.0
    assert fitted.models[0].residual_median == 1.0
    assert fitted.models[0].residual_mad == 0.5
    assert all(order == (2, 1, 2) for _, order, _ in calls)
    assert calls[0][0].tolist() == train["temp"].tolist()
    assert any(
        stage == "filter" and series.tolist() == validation["temp"].tolist()
        for series, _, stage in calls
    )
    assert any(
        flag.code == "arima_residual"
        and flag.sensor == "temp"
        and flag.timestamp == validation.index[-1].to_pydatetime()
        for flag in flags
    )
    pd.testing.assert_frame_equal(validation, validation_before)


def test_arima_fit_failure_returns_downgraded_rule_fallback_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingArima:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def fit(self) -> object:
            raise RuntimeError("synthetic fit failure")

    monkeypatch.setattr("clearsignal_wq.detectors.ARIMA", FailingArima)
    train = _single_sensor_frame(
        [float(index) for index in range(12)],
        "2019-01-01",
    )
    validation = _single_sensor_frame([3.0] * 8, "2019-01-02")

    fitted = fit_arima_detector(train)
    flags = detect_arima_anomalies(validation, fitted)
    stuck_flag = next(flag for flag in flags if flag.code == "stuck_value")

    assert fitted.models == ()
    assert fitted.fallback_sensors == ("temp",)
    assert stuck_flag.severity is EvidenceStrength.LOW
    assert any(detail.code == "model_fallback" for detail in stuck_flag.details)
    assert not any(flag.code == "arima_residual" for flag in flags)


def test_arima_constant_training_series_uses_rule_fallback_without_fitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedArima:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise AssertionError("constant series must not be fitted")

    monkeypatch.setattr("clearsignal_wq.detectors.ARIMA", UnexpectedArima)
    train = _single_sensor_frame([2.0] * 12, "2019-01-01")
    validation = _single_sensor_frame([2.0] * 8, "2019-01-02")

    fitted = fit_arima_detector(train)
    flags = detect_arima_anomalies(validation, fitted)

    assert fitted.fallback_sensors == ("temp",)
    assert any(
        flag.code == "stuck_value"
        and any(detail.code == "model_fallback" for detail in flag.details)
        for flag in flags
    )
