from __future__ import annotations

import hashlib
import io
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

import clearsignal_wq.data as data_module
import scripts.download_data as download_cli
from clearsignal_wq.data import (
    DATA_FILES,
    DataContractError,
    DatasetSplit,
    chronological_split,
    download_data_file,
    load_sensor_csv,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_sensor_data.csv"
DATA_README_PATH = Path(__file__).parents[1] / "data" / "README.md"
RAW_BASE_URL = (
    "https://raw.githubusercontent.com/AmberSJones/pyhydroqc/"
    "1260f16ae254abadcd43d71ee1705c3eea1ea2d4/LRO_data/"
)
REQUIRED_SENSOR_COLUMNS = [
    "temp",
    "temp_cor",
    "temp_qual",
    "cond",
    "cond_cor",
    "cond_qual",
    "ph",
    "ph_cor",
    "ph_qual",
    "do",
    "do_cor",
    "do_qual",
]
TURB_COLUMNS = ["turb", "turb_cor", "turb_qual"]


def test_data_readme_distinguishes_code_and_dataset_licenses() -> None:
    readme = DATA_README_PATH.read_text()

    assert "BSD-3-Clause" in readme
    assert "CC BY 4.0" in readme
    assert (
        "https://www.hydroshare.org/resource/451c4f9697654b1682d87ee619cd7924/"
        in readme
    )


def _fixture_csv(tmp_path: Path, transform=None) -> Path:
    frame = pd.read_csv(FIXTURE_PATH, keep_default_na=False)
    if transform is not None:
        transform(frame)
    path = tmp_path / "sensor.csv"
    frame.to_csv(path, index=False)
    return path


def _quality_mask(frame: pd.DataFrame) -> pd.Series:
    return frame.filter(like="_qual").notna().any(axis=1)


def test_data_files_are_pinned_to_exact_upstream_revision() -> None:
    assert DATA_FILES == {
        "MainStreet2019.csv": (
            f"{RAW_BASE_URL}MainStreet2019.csv",
            "752f04c363ac6e2667c0099dfdd3592d2ff99a25013dfeeac80a10bccbbdb7f8",
        ),
        "FranklinBasin2017.csv": (
            f"{RAW_BASE_URL}FranklinBasin2017.csv",
            "802b429e06b351a9289c8acfffe440c9a31c6c82a938553138454c00b2acdbc1",
        ),
    }


def test_load_sensor_csv_returns_utc_contract_columns(tmp_path: Path) -> None:
    path = _fixture_csv(tmp_path, lambda frame: frame.__setitem__("ignored", "x"))

    frame = load_sensor_csv(path)

    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "datetime"
    assert str(frame.index.tz) == "UTC"
    assert frame.index[0] == datetime(2019, 1, 1, 7, tzinfo=UTC)
    assert list(frame.columns) == REQUIRED_SENSOR_COLUMNS + TURB_COLUMNS
    assert "ignored" not in frame.columns
    assert pd.isna(frame.iloc[4]["cond_cor"])
    assert all(pd.api.types.is_numeric_dtype(frame[column]) for column in frame)


@pytest.mark.parametrize(
    ("transform", "message"),
    [
        (lambda frame: frame.drop(columns="do", inplace=True), "do"),
        (
            lambda frame: frame.__setitem__(
                "datetime", [frame.loc[0, "datetime"], *frame["datetime"].iloc[1:-1], frame.loc[0, "datetime"]]
            ),
            "duplicate.*datetime",
        ),
        (
            lambda frame: frame.__setitem__(
                "datetime", [frame.loc[1, "datetime"], frame.loc[0, "datetime"], *frame["datetime"].iloc[2:]]
            ),
            "datetime.*increasing",
        ),
        (lambda frame: frame.__setitem__("temp", ["bad", *frame["temp"].iloc[1:]]), "temp"),
    ],
)
def test_load_sensor_csv_rejects_invalid_required_data(
    tmp_path: Path, transform, message: str
) -> None:
    path = _fixture_csv(tmp_path, transform)

    with pytest.raises(DataContractError, match=message):
        load_sensor_csv(path)


def test_load_sensor_csv_rejects_partial_optional_turbidity_columns(
    tmp_path: Path,
) -> None:
    path = _fixture_csv(
        tmp_path,
        lambda frame: frame.drop(columns="turb_qual", inplace=True),
    )

    with pytest.raises(DataContractError, match="turb_qual"):
        load_sensor_csv(path)


def test_load_sensor_csv_rejects_timezone_markers(tmp_path: Path) -> None:
    path = _fixture_csv(
        tmp_path,
        lambda frame: frame.__setitem__(
            "datetime", frame["datetime"].astype(str) + "+00:00"
        ),
    )

    with pytest.raises(DataContractError, match="datetime.*timezone|timezone.*datetime"):
        load_sensor_csv(path)


def test_load_sensor_csv_accepts_naive_millisecond_timestamps(
    tmp_path: Path,
) -> None:
    path = _fixture_csv(
        tmp_path,
        lambda frame: frame.__setitem__(
            "datetime", frame["datetime"].astype(str) + ":00.000"
        ),
    )

    frame = load_sensor_csv(path)

    assert frame.index[0] == datetime(2019, 1, 1, 7, tzinfo=UTC)


def test_chronological_split_moves_boundaries_outside_quality_event() -> None:
    frame = load_sensor_csv(FIXTURE_PATH)

    split = chronological_split(frame)

    assert isinstance(split, DatasetSplit)
    assert (len(split.train), len(split.validation), len(split.test)) == (11, 6, 3)
    combined = pd.concat([split.train, split.validation, split.test])
    pd.testing.assert_frame_equal(combined, frame)
    assert split.train.index[-1] < split.validation.index[0] < split.test.index[0]
    assert split.train.index.intersection(split.validation.index).empty
    assert split.validation.index.intersection(split.test.index).empty

    mask = _quality_mask(frame).to_numpy()
    first_boundary = len(split.train)
    second_boundary = first_boundary + len(split.validation)
    assert not (mask[first_boundary - 1] and mask[first_boundary])
    assert not (mask[second_boundary - 1] and mask[second_boundary])

    split.train.iloc[0, 0] = -999
    assert frame.iloc[0, 0] != -999


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame({"temp_qual": [None, None]}),
        pd.DataFrame({"temp_qual": [1, 1, 1, 1]}),
    ],
)
def test_chronological_split_rejects_data_without_two_legal_boundaries(
    frame: pd.DataFrame,
) -> None:
    with pytest.raises(DataContractError, match="boundar|short|split"):
        chronological_split(frame)


def test_download_rejects_unapproved_filename(tmp_path: Path) -> None:
    with pytest.raises(DataContractError, match="filename"):
        download_data_file("other.csv", tmp_path)


def test_download_streams_verified_bytes_and_reuses_valid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "MainStreet2019.csv"
    payload = b"locally constructed test bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(DATA_FILES, name, (DATA_FILES[name][0], digest))
    calls: list[tuple[str, int]] = []

    def fake_urlopen(url: str, *, timeout: int):
        calls.append((url, timeout))
        return io.BytesIO(payload)

    monkeypatch.setattr(data_module.urllib.request, "urlopen", fake_urlopen)

    result = download_data_file(name, tmp_path)

    assert result == tmp_path / name
    assert result.read_bytes() == payload
    assert calls == [(DATA_FILES[name][0], data_module.DOWNLOAD_TIMEOUT_SECONDS)]
    assert data_module.DOWNLOAD_TIMEOUT_SECONDS == 30
    assert [path for path in tmp_path.iterdir() if path != result] == []

    monkeypatch.setattr(
        data_module.urllib.request,
        "urlopen",
        lambda _url, *, timeout: pytest.fail(
            f"valid existing file should be reused, not timeout after {timeout}"
        ),
    )
    assert download_data_file(name, tmp_path) == result


def test_hash_failure_removes_temporary_file_without_overwriting_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "FranklinBasin2017.csv"
    destination = tmp_path / name
    destination.write_bytes(b"existing bytes")
    expected_digest = hashlib.sha256(b"expected bytes").hexdigest()
    monkeypatch.setitem(DATA_FILES, name, (DATA_FILES[name][0], expected_digest))
    monkeypatch.setattr(
        data_module.urllib.request,
        "urlopen",
        lambda _url, *, timeout: io.BytesIO(b"wrong bytes"),
    )

    with pytest.raises(DataContractError, match="SHA-256"):
        download_data_file(name, tmp_path)

    assert destination.read_bytes() == b"existing bytes"
    assert list(tmp_path.iterdir()) == [destination]


def test_download_timeout_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "MainStreet2019.csv"

    def raise_timeout(_url: str, *, timeout: int) -> None:
        assert timeout == 30
        raise TimeoutError("offline")

    monkeypatch.setattr(data_module.urllib.request, "urlopen", raise_timeout)

    with pytest.raises(TimeoutError, match="offline"):
        download_data_file(name, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_download_cli_returns_nonzero_on_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def raise_timeout(_name: str, _destination: Path) -> Path:
        raise TimeoutError("offline")

    monkeypatch.setattr(download_cli, "download_data_file", raise_timeout)
    monkeypatch.setattr(
        sys,
        "argv",
        ["download_data.py", "--destination", str(tmp_path)],
    )

    assert download_cli.main() == 1
    assert "下载失败" in capsys.readouterr().err
