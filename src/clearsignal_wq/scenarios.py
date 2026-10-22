from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from clearsignal_wq.contracts import DataProvenance

_SCENARIOS = frozenset(
    {
        "correlated_shift_v1",
        "single_sensor_drift_v1",
        "missing_interval_v1",
    }
)
_CORRELATED_OFFSETS = {"ph": 0.5, "cond": 16.0, "do": 1.0}
_DRIFT_OFFSET = 0.75
_MISSING_POINTS = 8


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    name: str
    seed: int = 20261011
    start_fraction: float = 0.55
    duration_points: int = 16
    amplitude: float = 1.0

    def __post_init__(self) -> None:
        if self.name not in _SCENARIOS:
            raise ValueError("name must identify a supported scenario")
        if type(self.seed) is not int:
            raise TypeError("seed must be an int")
        if type(self.start_fraction) is not float:
            raise TypeError("start_fraction must be a float")
        if not math.isfinite(self.start_fraction) or not 0 <= self.start_fraction < 1:
            raise ValueError("start_fraction must be finite and within [0, 1)")
        if type(self.duration_points) is not int:
            raise TypeError("duration_points must be an int")
        if self.duration_points < 2:
            raise ValueError("duration_points must be at least 2")
        if type(self.amplitude) is not float:
            raise TypeError("amplitude must be a float")
        if not math.isfinite(self.amplitude) or not 0 < self.amplitude <= 2:
            raise ValueError("amplitude must be finite and within (0, 2]")


@dataclass(frozen=True, slots=True)
class ScenarioManifest:
    name: str
    version: str
    seed: int
    start_at: datetime
    end_at: datetime
    parameters: tuple[tuple[str, float | int | str], ...]
    provenance: DataProvenance = DataProvenance.SYNTHETIC_SCENARIO


def inject_scenario(
    frame: pd.DataFrame,
    config: ScenarioConfig,
) -> tuple[pd.DataFrame, ScenarioManifest]:
    """Inject one deterministic scenario without changing the source frame."""
    if not isinstance(config, ScenarioConfig):
        raise TypeError("config must be a ScenarioConfig")
    _validate_frame(frame)

    duration = (
        _MISSING_POINTS
        if config.name == "missing_interval_v1"
        else config.duration_points
    )
    start = _window_start(len(frame), duration, config)
    stop = start + duration
    window = frame.index[start:stop]
    modified = frame.copy(deep=True)

    if config.name == "correlated_shift_v1":
        _require_observed_sensors(frame, window, tuple(_CORRELATED_OFFSETS))
        for sensor, offset in _CORRELATED_OFFSETS.items():
            modified.loc[window, sensor] = (
                modified.loc[window, sensor] + offset * config.amplitude
            )
        end_at = window[-1]
    elif config.name == "single_sensor_drift_v1":
        _require_observed_sensors(frame, window, ("ph",))
        offsets = [
            _DRIFT_OFFSET * config.amplitude * point / duration
            for point in range(1, duration + 1)
        ]
        modified.loc[window, "ph"] = modified.loc[window, "ph"] + offsets
        if "ph_qual" not in modified:
            modified["ph_qual"] = pd.NA
        modified["ph_qual"] = modified["ph_qual"].astype("object")
        quality_window = frame.index[start : stop + 1]
        modified.loc[quality_window, "ph_qual"] = config.name
        end_at = quality_window[-1]
    else:
        modified = modified.drop(index=window)
        end_at = window[-1]

    parameters: tuple[tuple[str, float | int | str], ...] = (
        ("amplitude", config.amplitude),
        ("duration_points", duration),
        ("start_fraction", config.start_fraction),
    )
    return modified, ScenarioManifest(
        name=config.name,
        version="1",
        seed=config.seed,
        start_at=window[0].tz_convert(UTC).to_pydatetime(),
        end_at=end_at.tz_convert(UTC).to_pydatetime(),
        parameters=parameters,
    )


def _window_start(length: int, duration: int, config: ScenarioConfig) -> int:
    latest_start = length - duration - 1
    if latest_start < 1:
        raise ValueError("frame is too short for the requested scenario")
    base = round(latest_start * config.start_fraction)
    radius = min(max(1, duration // 2), latest_start)
    digest = hashlib.sha256(f"{config.name}|{config.seed}".encode()).digest()
    offset = int.from_bytes(digest[:8], "big") % (2 * radius + 1) - radius
    return min(latest_start, max(1, base + offset))


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


def _require_observed_sensors(
    frame: pd.DataFrame,
    window: pd.DatetimeIndex,
    sensors: tuple[str, ...],
) -> None:
    for sensor in sensors:
        if sensor not in frame:
            raise ValueError(f"frame is missing required sensor: {sensor}")
        series = frame[sensor]
        if is_bool_dtype(series.dtype) or not is_numeric_dtype(series.dtype):
            raise TypeError(f"{sensor} must have a real numeric dtype")
        values = series.loc[window]
        if values.isna().any() or not all(
            math.isfinite(float(value)) for value in values
        ):
            raise ValueError(f"{sensor} scenario window must contain finite values")
