from __future__ import annotations

import pandas as pd
import pytest

from clearsignal_wq.contracts import DataProvenance, TriageStatus
from clearsignal_wq.detectors import detect_rule_anomalies, fit_rule_detector
from clearsignal_wq.events import group_flags_into_events
from clearsignal_wq.reliability import assess_event
from clearsignal_wq.scenarios import ScenarioConfig, inject_scenario
from clearsignal_wq.triage import triage_event


def _frame() -> pd.DataFrame:
    index = pd.date_range(
        "2019-01-01",
        periods=64,
        freq="15min",
        tz="UTC",
        name="datetime",
    )
    positions = range(len(index))
    return pd.DataFrame(
        {
            "temp": [10.0 + position / 32 for position in positions],
            "cond": [100.0 + position / 2 for position in positions],
            "ph": [7.0 + position / 64 for position in positions],
            "do": [8.0 + position / 64 for position in positions],
            "turb": [2.0 + position / 32 for position in positions],
            "ph_qual": [pd.NA] * len(index),
        },
        index=index,
    )


def _statuses(frame: pd.DataFrame) -> tuple[TriageStatus, ...]:
    baseline = _frame()
    fitted = fit_rule_detector(baseline)
    flags = detect_rule_anomalies(frame, fitted)
    events = group_flags_into_events(flags)
    return tuple(
        triage_event(
            event,
            assess_event(event, frame, flags),
            DataProvenance.SYNTHETIC_SCENARIO,
        ).triage_status
        for event in events
    )


@pytest.mark.parametrize(
    "name",
    [
        "correlated_shift_v1",
        "single_sensor_drift_v1",
        "missing_interval_v1",
    ],
)
def test_same_seed_is_reproducible_and_input_is_unchanged(name: str) -> None:
    frame = _frame()
    before = frame.copy(deep=True)
    config = ScenarioConfig(name=name)

    first_frame, first_manifest = inject_scenario(frame, config)
    second_frame, second_manifest = inject_scenario(frame, config)

    pd.testing.assert_frame_equal(frame, before)
    assert first_frame.to_csv().encode() == second_frame.to_csv().encode()
    assert first_manifest == second_manifest
    assert first_manifest.start_at.utcoffset() == pd.Timedelta(0)
    assert first_manifest.provenance is DataProvenance.SYNTHETIC_SCENARIO


def test_different_seed_only_moves_the_injection_window() -> None:
    frame = _frame()
    first, first_manifest = inject_scenario(
        frame,
        ScenarioConfig(name="correlated_shift_v1", seed=1),
    )
    second, second_manifest = inject_scenario(
        frame,
        ScenarioConfig(name="correlated_shift_v1", seed=2),
    )

    first_delta = (
        first.loc[:, ["ph", "cond", "do"]] - frame.loc[:, ["ph", "cond", "do"]]
    )
    second_delta = (
        second.loc[:, ["ph", "cond", "do"]] - frame.loc[:, ["ph", "cond", "do"]]
    )
    first_values = first_delta.loc[first_delta.ne(0).any(axis=1)].reset_index(drop=True)
    second_values = second_delta.loc[second_delta.ne(0).any(axis=1)].reset_index(
        drop=True
    )

    assert first_manifest.start_at != second_manifest.start_at
    assert first_manifest.parameters == second_manifest.parameters
    pd.testing.assert_frame_equal(first_values, second_values)


def test_scenarios_only_apply_declared_changes() -> None:
    frame = _frame()

    correlated, correlated_manifest = inject_scenario(
        frame, ScenarioConfig(name="correlated_shift_v1")
    )
    drift, drift_manifest = inject_scenario(
        frame, ScenarioConfig(name="single_sensor_drift_v1")
    )
    missing, missing_manifest = inject_scenario(
        frame, ScenarioConfig(name="missing_interval_v1")
    )

    assert tuple(
        column
        for column in frame.columns
        if not correlated[column].equals(frame[column])
    ) == ("cond", "ph", "do")
    assert tuple(
        column
        for column in ("temp", "cond", "ph", "do", "turb")
        if not drift[column].equals(frame[column])
    ) == ("ph",)
    assert drift["ph_qual"].notna().sum() == 17
    assert len(missing) == len(frame) - 8
    pd.testing.assert_frame_equal(
        missing, frame.drop(index=frame.index.difference(missing.index))
    )
    assert all(
        manifest.name.endswith("_v1")
        and manifest.version == "1"
        and manifest.provenance is DataProvenance.SYNTHETIC_SCENARIO
        for manifest in (correlated_manifest, drift_manifest, missing_manifest)
    )


def test_drift_accepts_an_all_missing_numeric_quality_column() -> None:
    frame = _frame()
    frame["ph_qual"] = float("nan")

    modified, _ = inject_scenario(
        frame,
        ScenarioConfig(name="single_sensor_drift_v1"),
    )

    assert modified["ph_qual"].dropna().eq("single_sensor_drift_v1").all()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("correlated_shift_v1", TriageStatus.POSSIBLE_WATER_QUALITY_EVENT),
        ("single_sensor_drift_v1", TriageStatus.SENSOR_FAULT_OR_DRIFT),
        ("missing_interval_v1", TriageStatus.DATA_INTEGRITY_ISSUE),
    ],
)
def test_scenario_reaches_expected_triage_status(
    name: str,
    expected: TriageStatus,
) -> None:
    modified, _ = inject_scenario(_frame(), ScenarioConfig(name=name))

    statuses = _statuses(modified)
    assert statuses
    assert set(statuses) == {expected}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "unknown"},
        {"name": "correlated_shift_v1", "amplitude": 0.0},
        {"name": "correlated_shift_v1", "amplitude": 2.1},
        {"name": "correlated_shift_v1", "amplitude": float("inf")},
        {"name": "correlated_shift_v1", "duration_points": 1},
        {"name": "correlated_shift_v1", "start_fraction": 1.0},
    ],
)
def test_invalid_scenario_configuration_is_rejected(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ScenarioConfig(**kwargs)
