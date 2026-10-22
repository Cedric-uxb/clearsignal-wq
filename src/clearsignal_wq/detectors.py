from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.arima.model import ARIMA

from clearsignal_wq.contracts import EvidenceItem, EvidenceStrength, PointFlag

_RAW_SENSORS = ("temp", "cond", "ph", "do", "turb")


@dataclass(frozen=True, slots=True)
class RuleConfig:
    expected_interval_minutes: int = 15
    stuck_run_points: int = 8
    jump_mad_multiplier: float = 8.0

    def __post_init__(self) -> None:
        for field_name in ("expected_interval_minutes", "stuck_run_points"):
            value = getattr(self, field_name)
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an int")
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if type(self.jump_mad_multiplier) not in (int, float):
            raise TypeError("jump_mad_multiplier must be a number")
        if not math.isfinite(self.jump_mad_multiplier):
            raise ValueError("jump_mad_multiplier must be finite")
        if self.jump_mad_multiplier <= 0:
            raise ValueError("jump_mad_multiplier must be positive")


@dataclass(frozen=True, slots=True)
class ArimaConfig:
    order: tuple[int, int, int] = (2, 1, 2)
    residual_mad_multiplier: float = 6.0

    def __post_init__(self) -> None:
        if self.order != (2, 1, 2):
            raise ValueError("ARIMA order is fixed at (2, 1, 2)")
        if type(self.residual_mad_multiplier) is not float:
            raise TypeError("residual_mad_multiplier must be a float")
        if (
            not math.isfinite(self.residual_mad_multiplier)
            or self.residual_mad_multiplier <= 0
        ):
            raise ValueError("residual_mad_multiplier must be finite and positive")


@dataclass(frozen=True, slots=True)
class ArimaSensorModel:
    sensor: str
    params: tuple[float, ...]
    residual_median: float
    residual_mad: float

    def __post_init__(self) -> None:
        if self.sensor not in _RAW_SENSORS:
            raise ValueError("sensor must be an allowed raw sensor")
        if not self.params or any(
            type(value) is not float or not math.isfinite(value)
            for value in self.params
        ):
            raise ValueError("params must contain finite floats")
        if (
            type(self.residual_median) is not float
            or type(self.residual_mad) is not float
        ):
            raise TypeError("residual statistics must be exact floats")
        if not math.isfinite(self.residual_median) or not math.isfinite(
            self.residual_mad
        ):
            raise ValueError("residual statistics must be finite")
        if self.residual_mad < 0:
            raise ValueError("residual MAD must be nonnegative")


@dataclass(frozen=True, slots=True)
class FittedArimaDetector:
    config: ArimaConfig
    rule_detector: FittedRuleDetector
    models: tuple[ArimaSensorModel, ...]
    fallback_sensors: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.config, ArimaConfig):
            raise TypeError("config must be an ArimaConfig")
        if not isinstance(self.rule_detector, FittedRuleDetector):
            raise TypeError("rule_detector must be a FittedRuleDetector")
        if not isinstance(self.models, tuple) or not all(
            isinstance(model, ArimaSensorModel) for model in self.models
        ):
            raise TypeError("models must be a tuple of ArimaSensorModel")
        model_sensors = tuple(model.sensor for model in self.models)
        if model_sensors != tuple(sorted(set(model_sensors))):
            raise ValueError("model sensors must be unique and sorted")
        if not isinstance(self.fallback_sensors, tuple) or not all(
            sensor in _RAW_SENSORS for sensor in self.fallback_sensors
        ):
            raise TypeError("fallback_sensors must be a tuple of raw sensors")
        if self.fallback_sensors != tuple(sorted(set(self.fallback_sensors))):
            raise ValueError("fallback_sensors must be unique and sorted")
        if set(model_sensors).intersection(self.fallback_sensors):
            raise ValueError("a sensor cannot be both modelled and fallback")


@dataclass(frozen=True, slots=True)
class FittedRuleDetector:
    config: RuleConfig
    difference_stats: tuple[tuple[str, float, float], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.config, RuleConfig):
            raise TypeError("config must be a RuleConfig")
        if not isinstance(self.difference_stats, tuple):
            raise TypeError("difference_stats must be a tuple")

        sensors: list[str] = []
        for item in self.difference_stats:
            if not isinstance(item, tuple) or len(item) != 3:
                raise TypeError("difference_stats items must be three-item tuples")
            sensor, median, mad = item
            if sensor not in _RAW_SENSORS:
                raise ValueError(
                    "difference_stats sensor must be an allowed raw sensor"
                )
            if type(median) is not float:
                raise TypeError("difference_stats median must be an exact float")
            if type(mad) is not float:
                raise TypeError("difference_stats MAD must be an exact float")
            if not math.isfinite(median) or not math.isfinite(mad):
                raise ValueError("difference_stats contain non-finite values")
            if mad < 0:
                raise ValueError("difference_stats MAD must be nonnegative")
            sensors.append(sensor)

        if len(set(sensors)) != len(sensors):
            raise ValueError("difference_stats sensors must be unique")
        if sensors != sorted(sensors):
            raise ValueError("difference_stats sensors must be sorted")


def fit_rule_detector(
    train: pd.DataFrame,
    config: RuleConfig | None = None,
) -> FittedRuleDetector:
    _validate_time_index(train.index)
    _validate_raw_sensor_values(train)
    resolved_config = config if config is not None else RuleConfig()
    difference_stats: list[tuple[str, float, float]] = []
    for sensor in sorted(set(train.columns).intersection(_RAW_SENSORS)):
        differences = _safe_differences(train[sensor], sensor)
        if differences.empty:
            continue
        median = float(differences.median())
        mad = float((differences - median).abs().median())
        if not math.isfinite(median) or not math.isfinite(mad):
            raise ValueError(f"{sensor} produced non-finite median/MAD statistics")
        difference_stats.append((sensor, median, mad))
    return FittedRuleDetector(
        config=resolved_config,
        difference_stats=tuple(difference_stats),
    )


def detect_rule_anomalies(
    frame: pd.DataFrame,
    fitted: FittedRuleDetector,
) -> tuple[PointFlag, ...]:
    _validate_time_index(frame.index)
    _validate_raw_sensor_values(frame)
    flags: list[PointFlag] = []
    raw_sensors = tuple(sensor for sensor in _RAW_SENSORS if sensor in frame.columns)
    jump_sensors = tuple(
        sorted(
            set(frame.columns).intersection(
                sensor for sensor, _, _ in fitted.difference_stats
            )
        )
    )
    flags.extend(_missing_interval_flags(frame.index, fitted.config))
    flags.extend(_physical_range_flags(frame))
    for sensor in raw_sensors:
        flags.extend(_stuck_value_flags(frame[sensor], sensor, fitted.config))
    stats = {sensor: (median, mad) for sensor, median, mad in fitted.difference_stats}
    for sensor in jump_sensors:
        median, mad = stats[sensor]
        flags.extend(
            _sudden_jump_flags(
                frame[sensor],
                sensor,
                median,
                mad,
                fitted.config,
            )
        )
    return tuple(
        sorted(flags, key=lambda flag: (flag.timestamp, flag.sensor, flag.code))
    )


def fit_arima_detector(
    train: pd.DataFrame,
    config: ArimaConfig | None = None,
    rule_config: RuleConfig | None = None,
) -> FittedArimaDetector:
    _validate_time_index(train.index)
    _validate_raw_sensor_values(train)
    resolved_config = config if config is not None else ArimaConfig()
    rule_detector = fit_rule_detector(train, rule_config)
    models: list[ArimaSensorModel] = []
    fallback_sensors: list[str] = []

    for sensor in sorted(set(train.columns).intersection(_RAW_SENSORS)):
        series = _float_series(train[sensor])
        observed = series.dropna()
        if len(observed) < 4 or observed.nunique() <= 1:
            fallback_sensors.append(sensor)
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)
                result = ARIMA(
                    series,
                    order=resolved_config.order,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                ).fit()
            convergence = getattr(result, "mle_retvals", {})
            if isinstance(convergence, dict) and not convergence.get("converged", True):
                raise ValueError("ARIMA fit did not converge")
            residuals = _finite_absolute_residuals(
                result.resid,
                sensor,
                train[sensor].index,
            )
            if residuals.empty:
                raise ValueError("ARIMA fit produced no finite residuals")
            residual_median = float(residuals.median())
            residual_mad = float((residuals - residual_median).abs().median())
            params = tuple(float(value) for value in result.params)
            models.append(
                ArimaSensorModel(
                    sensor=sensor,
                    params=params,
                    residual_median=residual_median,
                    residual_mad=residual_mad,
                )
            )
        except Exception:  # noqa: BLE001 - any model failure must trigger fallback.
            fallback_sensors.append(sensor)

    return FittedArimaDetector(
        config=resolved_config,
        rule_detector=rule_detector,
        models=tuple(models),
        fallback_sensors=tuple(fallback_sensors),
    )


def detect_arima_anomalies(
    frame: pd.DataFrame,
    fitted: FittedArimaDetector,
) -> tuple[PointFlag, ...]:
    rule_flags = detect_rule_anomalies(frame, fitted.rule_detector)
    arima_flags: list[PointFlag] = []
    fallback_sensors = set(fitted.fallback_sensors)

    for model in fitted.models:
        if model.sensor not in frame:
            continue
        series = _float_series(frame[model.sensor])
        try:
            result = ARIMA(
                series,
                order=fitted.config.order,
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).filter(model.params)
            residuals = _finite_absolute_residuals(
                result.resid,
                model.sensor,
                frame[model.sensor].index,
            )
        except Exception:  # noqa: BLE001 - any model failure must trigger fallback.
            fallback_sensors.add(model.sensor)
            continue

        threshold = (
            model.residual_median
            + fitted.config.residual_mad_multiplier * model.residual_mad
        )
        for timestamp, residual in residuals.items():
            if float(residual) <= threshold:
                continue
            message = (
                f"Observed absolute {model.sensor} ARIMA residual {residual:g}; "
                f"training median {model.residual_median:g}, MAD "
                f"{model.residual_mad:g}, multiplier "
                f"{fitted.config.residual_mad_multiplier:g}."
            )
            arima_flags.append(
                _make_flag(
                    timestamp,
                    model.sensor,
                    "arima_residual",
                    EvidenceStrength.MEDIUM,
                    message,
                )
            )

    annotated_rules = tuple(
        _annotate_rule_fallback(flag) if flag.sensor in fallback_sensors else flag
        for flag in rule_flags
    )
    return tuple(
        sorted(
            (*annotated_rules, *arima_flags),
            key=lambda flag: (flag.timestamp, flag.sensor, flag.code),
        )
    )


def _validate_time_index(index: pd.Index) -> None:
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("index must be a DatetimeIndex")
    if index.tz is None:
        raise ValueError("DatetimeIndex must be timezone-aware")
    if index.has_duplicates:
        raise ValueError("DatetimeIndex must not contain duplicate timestamps")
    if not index.is_monotonic_increasing:
        raise ValueError("DatetimeIndex must be strictly increasing")


def _validate_raw_sensor_values(frame: pd.DataFrame) -> None:
    for sensor in _RAW_SENSORS:
        if sensor not in frame:
            continue
        series = frame[sensor]
        if (
            pd.api.types.is_bool_dtype(series.dtype)
            or pd.api.types.is_complex_dtype(series.dtype)
            or not pd.api.types.is_numeric_dtype(series.dtype)
        ):
            raise TypeError(f"{sensor} must have a real numeric dtype")
        values = series.dropna()
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError(f"{sensor} contains a non-finite raw value")


def _safe_differences(series: pd.Series, sensor: str) -> pd.Series:
    floating = series.astype("Float64").copy(deep=True)
    differences = floating.diff().dropna()
    if not all(math.isfinite(float(value)) for value in differences):
        raise ValueError(f"{sensor} contains a non-finite first difference")
    return differences


def _float_series(series: pd.Series) -> pd.Series:
    return pd.Series(
        series.to_numpy(dtype=float, na_value=float("nan")),
        name=series.name,
    )


def _finite_absolute_residuals(
    residuals: object,
    sensor: str,
    index: pd.Index,
) -> pd.Series:
    values = tuple(residuals)  # type: ignore[arg-type]
    if len(values) > len(index):
        raise ValueError(f"{sensor} produced too many ARIMA residuals")
    residual_index = index[-len(values) :] if values else index[:0]
    series = pd.Series(values, index=residual_index)
    absolute = series.astype("Float64").abs().dropna()
    if not all(math.isfinite(float(value)) for value in absolute):
        raise ValueError(f"{sensor} produced non-finite ARIMA residuals")
    return absolute


def _annotate_rule_fallback(flag: PointFlag) -> PointFlag:
    downgraded = {
        EvidenceStrength.HIGH: EvidenceStrength.MEDIUM,
        EvidenceStrength.MEDIUM: EvidenceStrength.LOW,
        EvidenceStrength.LOW: EvidenceStrength.LOW,
    }[flag.severity]
    fallback = EvidenceItem(
        code="model_fallback",
        message=(
            f"ARIMA unavailable for {flag.sensor}; retained deterministic rule "
            "evidence with downgraded strength."
        ),
        sensor=flag.sensor,
    )
    return PointFlag(
        timestamp=flag.timestamp,
        sensor=flag.sensor,
        code=flag.code,
        severity=downgraded,
        details=(*flag.details, fallback),
    )


def _missing_interval_flags(
    index: pd.DatetimeIndex,
    config: RuleConfig,
) -> list[PointFlag]:
    flags: list[PointFlag] = []
    for position in range(1, len(index)):
        gap_minutes = (index[position] - index[position - 1]).total_seconds() / 60
        if gap_minutes <= config.expected_interval_minutes:
            continue
        message = (
            f"Observed gap: {gap_minutes:g} minutes; expected at most "
            f"{config.expected_interval_minutes} minutes."
        )
        flags.append(
            _make_flag(
                index[position],
                "stream",
                "missing_interval",
                EvidenceStrength.HIGH,
                message,
            )
        )
    return flags


def _physical_range_flags(frame: pd.DataFrame) -> list[PointFlag]:
    checks = {
        "ph": (lambda value: value < 0 or value > 14, "[0, 14]"),
        "do": (lambda value: value < 0, "[0, infinity)"),
    }
    flags: list[PointFlag] = []
    for sensor, (is_invalid, physical_range) in checks.items():
        if sensor not in frame:
            continue
        for timestamp, value in frame[sensor].items():
            if pd.isna(value) or not is_invalid(value):
                continue
            message = (
                f"Observed {sensor} value {value:g} outside physical range "
                f"{physical_range}; data-integrity rule only, with no health conclusion."
            )
            flags.append(
                _make_flag(
                    timestamp,
                    sensor,
                    "out_of_physical_range",
                    EvidenceStrength.HIGH,
                    message,
                )
            )
    return flags


def _stuck_value_flags(
    series: pd.Series,
    sensor: str,
    config: RuleConfig,
) -> list[PointFlag]:
    flags: list[PointFlag] = []
    previous: object = None
    run_length = 0
    for timestamp, value in series.items():
        if pd.isna(value):
            previous = None
            run_length = 0
            continue
        if run_length and value == previous:
            run_length += 1
        else:
            previous = value
            run_length = 1
        if run_length == config.stuck_run_points:
            message = (
                f"Observed {config.stuck_run_points} consecutive identical "
                f"non-missing {sensor} values ({value:g})."
            )
            flags.append(
                _make_flag(
                    timestamp,
                    sensor,
                    "stuck_value",
                    EvidenceStrength.MEDIUM,
                    message,
                )
            )
    return flags


def _sudden_jump_flags(
    series: pd.Series,
    sensor: str,
    median: float,
    mad: float,
    config: RuleConfig,
) -> list[PointFlag]:
    flags: list[PointFlag] = []
    threshold = config.jump_mad_multiplier * mad
    for timestamp, difference in _safe_differences(series, sensor).items():
        deviation = abs(float(difference) - median)
        if deviation <= threshold:
            continue
        message = (
            f"Observed {sensor} difference {difference:g}; training median "
            f"{median:g}, MAD {mad:g}, multiplier {config.jump_mad_multiplier:g}."
        )
        flags.append(
            _make_flag(
                timestamp,
                sensor,
                "sudden_jump",
                EvidenceStrength.MEDIUM,
                message,
            )
        )
    return flags


def _make_flag(
    timestamp: object,
    sensor: str,
    code: str,
    severity: EvidenceStrength,
    message: str,
) -> PointFlag:
    return PointFlag(
        timestamp=_as_utc_datetime(timestamp),
        sensor=sensor,
        code=code,
        severity=severity,
        details=(EvidenceItem(code=code, message=message, sensor=sensor),),
    )


def _as_utc_datetime(timestamp: object) -> datetime:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.tz_convert(UTC).to_pydatetime()
