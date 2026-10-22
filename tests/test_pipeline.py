from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from clearsignal_wq.contracts import (
    DataProvenance,
    EvidenceStrength,
    PipelineResult,
    TriageStatus,
)
from clearsignal_wq.data import DataContractError
from clearsignal_wq.pipeline import run_pipeline
from clearsignal_wq.scenarios import ScenarioConfig, inject_scenario


def _frame(rows: int = 64) -> pd.DataFrame:
    index = pd.date_range(
        "2019-01-01",
        periods=rows,
        freq="15min",
        tz="UTC",
        name="datetime",
    )
    positions = range(rows)
    return pd.DataFrame(
        {
            "temp": [10.0 + position / 32 for position in positions],
            "cond": [100.0 + position / 2 for position in positions],
            "ph": [7.0 + position / 64 for position in positions],
            "do": [8.0 + position / 64 for position in positions],
            "turb": [2.0 + position / 32 for position in positions],
            "ph_qual": [pd.NA] * rows,
        },
        index=index,
    )


def _case(name: str) -> tuple[pd.DataFrame, DataProvenance, TriageStatus]:
    scenario_name = "correlated_shift_v1" if name == "public_real_data" else name
    modified, _ = inject_scenario(
        _frame(),
        ScenarioConfig(name=scenario_name),
    )
    provenance = (
        DataProvenance.PUBLIC_REAL_DATA
        if name == "public_real_data"
        else DataProvenance.SYNTHETIC_SCENARIO
    )
    expected = {
        "public_real_data": TriageStatus.POSSIBLE_WATER_QUALITY_EVENT,
        "correlated_shift_v1": TriageStatus.POSSIBLE_WATER_QUALITY_EVENT,
        "single_sensor_drift_v1": TriageStatus.SENSOR_FAULT_OR_DRIFT,
        "missing_interval_v1": TriageStatus.DATA_INTEGRITY_ISSUE,
    }[name]
    return modified, provenance, expected


@pytest.mark.parametrize(
    "name",
    [
        "public_real_data",
        "correlated_shift_v1",
        "single_sensor_drift_v1",
        "missing_interval_v1",
    ],
)
def test_pipeline_is_reproducible_sorted_and_traceable(name: str) -> None:
    frame, provenance, expected = _case(name)
    before = frame.copy(deep=True)

    training_frame = None if name == "public_real_data" else _frame()
    first = run_pipeline(frame, provenance, training_frame=training_frame)
    second = run_pipeline(
        frame.copy(deep=True),
        provenance,
        training_frame=(
            None if training_frame is None else training_frame.copy(deep=True)
        ),
    )

    assert isinstance(first, PipelineResult)
    assert first == second
    assert len(first.data_hash) == 64
    assert first.config_version == "pipeline-1"
    assert first.model_version == "rules-1"
    assert first.provenance is provenance
    assert first.events
    assert {event.triage_status for event in first.events} == {expected}
    assert [event.triage_status for event in first.events] == sorted(
        (event.triage_status for event in first.events),
        key=(
            TriageStatus.DATA_INTEGRITY_ISSUE,
            TriageStatus.SENSOR_FAULT_OR_DRIFT,
            TriageStatus.POSSIBLE_WATER_QUALITY_EVENT,
            TriageStatus.INSUFFICIENT_EVIDENCE,
        ).index,
    )
    pd.testing.assert_frame_equal(frame, before)


def test_pipeline_arima_failure_is_visible_and_downgrades_strength(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingArima:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def fit(self) -> object:
            raise RuntimeError("synthetic fit failure")

    monkeypatch.setattr("clearsignal_wq.detectors.ARIMA", FailingArima)
    frame, _ = inject_scenario(
        _frame(),
        ScenarioConfig(name="single_sensor_drift_v1"),
    )

    result = run_pipeline(
        frame,
        DataProvenance.SYNTHETIC_SCENARIO,
        model="rules_arima",
        training_frame=_frame(),
    )

    fallback_event = next(
        event
        for event in result.events
        if any(item.code == "model_fallback" for item in event.evidence)
    )
    assert fallback_event.triage_status is TriageStatus.SENSOR_FAULT_OR_DRIFT
    assert fallback_event.evidence_strength is EvidenceStrength.LOW
    assert any("model_fallback" in warning for warning in result.warnings)


def test_pipeline_sorts_mixed_events_by_triage_priority() -> None:
    training = _frame(128)
    frame = training
    for name, start_fraction in (
        ("correlated_shift_v1", 0.1),
        ("single_sensor_drift_v1", 0.45),
        ("missing_interval_v1", 0.8),
    ):
        frame, _ = inject_scenario(
            frame,
            ScenarioConfig(name=name, start_fraction=start_fraction),
        )

    result = run_pipeline(
        frame,
        DataProvenance.SYNTHETIC_SCENARIO,
        training_frame=training,
    )

    assert [event.triage_status for event in result.events] == [
        TriageStatus.DATA_INTEGRITY_ISSUE,
        TriageStatus.SENSOR_FAULT_OR_DRIFT,
        TriageStatus.POSSIBLE_WATER_QUALITY_EVENT,
        TriageStatus.POSSIBLE_WATER_QUALITY_EVENT,
    ]


def test_pipeline_rejects_missing_required_sensor() -> None:
    frame = _frame().drop(columns="ph")

    with pytest.raises(DataContractError, match="missing required columns: ph"):
        run_pipeline(
            frame,
            DataProvenance.PUBLIC_REAL_DATA,
            training_frame=_frame(),
        )


def test_pipeline_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="rules.*rules_arima"):
        run_pipeline(
            _frame(),
            DataProvenance.PUBLIC_REAL_DATA,
            model="unknown",
        )


def test_evaluation_script_uses_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import scripts.run_evaluation as evaluation_script

    source = tmp_path / "MainStreet2019.csv"
    source.write_text("fixture\n", encoding="utf-8")
    output_dir = tmp_path / "metrics"
    calls: list[tuple[str, int, int]] = []

    def fake_pipeline(
        frame: pd.DataFrame,
        provenance: DataProvenance,
        model: str = "rules",
        *,
        training_frame: pd.DataFrame | None = None,
    ) -> PipelineResult:
        assert provenance is DataProvenance.PUBLIC_REAL_DATA
        assert training_frame is not None
        calls.append((model, len(training_frame), len(frame)))
        return PipelineResult(
            data_hash="a" * 64,
            config_version="pipeline-1",
            model_version="rules-1",
            provenance=provenance,
            events=(),
        )

    monkeypatch.setattr(evaluation_script, "DATA_PATH", source)
    monkeypatch.setattr(evaluation_script, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(evaluation_script, "load_sensor_csv", lambda path: _frame())
    monkeypatch.setattr(evaluation_script, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(evaluation_script, "_git_commit", lambda: "test-commit")

    output_path, payload = evaluation_script.run_evaluation(
        model="rules",
        split="validation",
    )

    assert calls == [("rules", 38, 13)]
    assert output_path == output_dir / "rules-validation.json"
    assert payload["pipeline"]["config_version"] == "pipeline-1"
