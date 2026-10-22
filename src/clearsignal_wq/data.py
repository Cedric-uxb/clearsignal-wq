from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, timedelta, timezone
from pathlib import Path

import pandas as pd

UPSTREAM_COMMIT = "1260f16ae254abadcd43d71ee1705c3eea1ea2d4"
RAW_BASE_URL = (
    "https://raw.githubusercontent.com/AmberSJones/pyhydroqc/"
    f"{UPSTREAM_COMMIT}/LRO_data/"
)
DATA_FILES = {
    "MainStreet2019.csv": (
        f"{RAW_BASE_URL}MainStreet2019.csv",
        "752f04c363ac6e2667c0099dfdd3592d2ff99a25013dfeeac80a10bccbbdb7f8",
    ),
    "FranklinBasin2017.csv": (
        f"{RAW_BASE_URL}FranklinBasin2017.csv",
        "802b429e06b351a9289c8acfffe440c9a31c6c82a938553138454c00b2acdbc1",
    ),
}
DOWNLOAD_TIMEOUT_SECONDS = 30

_REQUIRED_SENSOR_COLUMNS = tuple(
    f"{sensor}{suffix}"
    for sensor in ("temp", "cond", "ph", "do")
    for suffix in ("", "_cor", "_qual")
)
_TURBIDITY_COLUMNS = ("turb", "turb_cor", "turb_qual")
_SOURCE_DATETIME_PATTERN = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2}\.\d{3})?"
_SOURCE_TIMEZONE = timezone(timedelta(hours=-7))


class DataContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def load_sensor_csv(path: Path) -> pd.DataFrame:
    try:
        source = pd.read_csv(path, na_values=["NULL"])
    except Exception as exc:
        raise DataContractError(f"unable to read CSV: {path}") from exc

    required_columns = ("datetime", *_REQUIRED_SENSOR_COLUMNS)
    missing = [column for column in required_columns if column not in source.columns]
    if missing:
        raise DataContractError(f"missing required columns: {', '.join(missing)}")

    present_turbidity = [
        column for column in _TURBIDITY_COLUMNS if column in source.columns
    ]
    if present_turbidity and len(present_turbidity) != len(_TURBIDITY_COLUMNS):
        missing_turbidity = [
            column for column in _TURBIDITY_COLUMNS if column not in source.columns
        ]
        raise DataContractError(
            f"incomplete turbidity columns; missing: {', '.join(missing_turbidity)}"
        )

    raw_timestamps = source["datetime"]
    if raw_timestamps.isna().any():
        raise DataContractError("datetime contains a missing value")
    timestamp_text = raw_timestamps.astype("string")
    valid_format = timestamp_text.str.fullmatch(_SOURCE_DATETIME_PATTERN)
    if not valid_format.fillna(False).all():
        raise DataContractError(
            "datetime contains an invalid format or timezone marker"
        )
    try:
        timestamps = pd.to_datetime(timestamp_text, errors="raise", format="mixed")
    except (TypeError, ValueError) as exc:
        raise DataContractError(
            "datetime contains an invalid value or timezone marker"
        ) from exc
    if timestamps.dt.tz is not None:
        raise DataContractError("datetime must not contain a timezone marker")
    timestamps = timestamps.dt.tz_localize(_SOURCE_TIMEZONE).dt.tz_convert(UTC)
    if timestamps.duplicated().any():
        raise DataContractError("duplicate datetime timestamp")
    if not timestamps.is_monotonic_increasing:
        raise DataContractError("datetime must be strictly increasing")

    sensor_columns = list(_REQUIRED_SENSOR_COLUMNS)
    if present_turbidity:
        sensor_columns.extend(_TURBIDITY_COLUMNS)

    result = source.loc[:, sensor_columns].copy()
    for column in sensor_columns:
        try:
            result[column] = pd.to_numeric(result[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise DataContractError(
                f"{column} contains a non-numeric value"
            ) from exc

    result.index = pd.DatetimeIndex(timestamps, name="datetime")
    return result


def chronological_split(
    frame: pd.DataFrame,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> DatasetSplit:
    row_count = len(frame)
    if row_count < 3:
        raise DataContractError("data is too short for three non-empty splits")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise DataContractError("split fractions must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise DataContractError("split fractions must leave a non-empty test split")

    initial_train = int(row_count * train_fraction)
    initial_validation_end = int(
        row_count * (train_fraction + validation_fraction)
    )
    target_validation_size = int(row_count * validation_fraction)

    quality_columns = [
        column for column in frame.columns if column.endswith("_qual")
    ]
    if quality_columns:
        quality_mask = frame.loc[:, quality_columns].notna().any(axis=1).to_numpy()
    else:
        quality_mask = [False] * row_count

    legal_boundaries = [
        boundary
        for boundary in range(1, row_count)
        if not (quality_mask[boundary - 1] and quality_mask[boundary])
    ]
    if len(legal_boundaries) < 2:
        raise DataContractError("no two legal non-empty split boundaries exist")

    def boundary_rank(pair: tuple[int, int]) -> tuple[int, int, int, int, int]:
        first, second = pair
        train_distance = abs(first - initial_train)
        validation_end_distance = abs(second - initial_validation_end)
        validation_size_distance = abs((second - first) - target_validation_size)
        return (
            train_distance + validation_end_distance,
            train_distance,
            validation_size_distance,
            first,
            second,
        )

    best_pair: tuple[int, int] | None = None
    best_rank: tuple[int, int, int, int, int] | None = None
    for second_index, second in enumerate(legal_boundaries):
        insertion = bisect_left(
            legal_boundaries,
            initial_train,
            hi=second_index,
        )
        candidate_indexes = {insertion - 1, insertion}
        for candidate_index in candidate_indexes:
            if not 0 <= candidate_index < second_index:
                continue
            pair = (legal_boundaries[candidate_index], second)
            rank = boundary_rank(pair)
            if best_rank is None or rank < best_rank:
                best_pair = pair
                best_rank = rank

    if best_pair is None:
        raise DataContractError("no two legal non-empty split boundaries exist")
    first, second = best_pair
    if first <= 0 or second <= first or second >= row_count:
        raise DataContractError("split boundaries must produce three non-empty splits")

    return DatasetSplit(
        train=frame.iloc[:first].copy(),
        validation=frame.iloc[first:second].copy(),
        test=frame.iloc[second:].copy(),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_data_file(name: str, destination_dir: Path) -> Path:
    if name not in DATA_FILES:
        raise DataContractError(f"unapproved data filename: {name}")

    url, expected_digest = DATA_FILES[name]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / name
    if destination.is_file() and _sha256_file(destination) == expected_digest:
        return destination

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination_dir,
            prefix=f".{name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            with urllib.request.urlopen(
                url,
                timeout=DOWNLOAD_TIMEOUT_SECONDS,
            ) as response:
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
                    digest.update(chunk)

        actual_digest = digest.hexdigest()
        if actual_digest != expected_digest:
            raise DataContractError(
                f"SHA-256 mismatch for {name}: expected {expected_digest}, "
                f"got {actual_digest}"
            )
        os.replace(temporary_path, destination)
        temporary_path = None
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
