from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from clearsignal_wq.contracts import (
    DataProvenance,
    PipelineResult,
    TriageEvent,
    TriageStatus,
)
from clearsignal_wq.data import UPSTREAM_COMMIT, chronological_split, load_sensor_csv
from clearsignal_wq.pipeline import run_pipeline
from clearsignal_wq.scenarios import ScenarioConfig, ScenarioManifest, inject_scenario

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data" / "raw" / "MainStreet2019.csv"
DEMO_START = "2019-06-12 01:15:00+00:00"
DEMO_END = "2019-06-13 09:00:00+00:00"
MODE_TO_SCENARIO = {
    "Public real data": None,
    "Correlated sensor shift": "correlated_shift_v1",
    "Single-sensor drift": "single_sensor_drift_v1",
    "Missing data interval": "missing_interval_v1",
}
ACTION_OPTIONS = (
    "Pending retest / 待复测",
    "Pending calibration / 待校准",
    "Check data link / 待检查链路",
    "Escalated / 已升级",
)
SENSOR_COLORS = {
    "temp": "#D1495B",
    "cond": "#00798C",
    "ph": "#30638E",
    "do": "#E09F3E",
}


@dataclass(frozen=True)
class StatusView:
    symbol: str
    label: str
    color: str
    background: str


STATUS_VIEWS = {
    TriageStatus.DATA_INTEGRITY_ISSUE: StatusView(
        "■", "Data integrity issue", "#9B2226", "#FFF3F2"
    ),
    TriageStatus.SENSOR_FAULT_OR_DRIFT: StatusView(
        "▲", "Sensor fault or drift", "#BB6B00", "#FFF8E8"
    ),
    TriageStatus.POSSIBLE_WATER_QUALITY_EVENT: StatusView(
        "◆", "Possible water-quality event", "#087F5B", "#ECF8F3"
    ),
    TriageStatus.INSUFFICIENT_EVIDENCE: StatusView(
        "○", "Insufficient evidence", "#5C677D", "#F3F5F7"
    ),
}


@st.cache_data(show_spinner=False)
def analyze_mode(
    mode: str,
) -> tuple[pd.DataFrame, PipelineResult, ScenarioManifest | None]:
    source = load_sensor_csv(DATA_PATH)
    split = chronological_split(source)
    target = pd.concat((split.validation, split.test))
    scenario_name = MODE_TO_SCENARIO[mode]

    if scenario_name is None:
        return target, run_pipeline(source, DataProvenance.PUBLIC_REAL_DATA), None

    demo_frame = target.loc[DEMO_START:DEMO_END].copy()
    scenario_frame, manifest = inject_scenario(
        demo_frame,
        ScenarioConfig(name=scenario_name),
    )
    result = run_pipeline(
        scenario_frame,
        DataProvenance.SYNTHETIC_SCENARIO,
        training_frame=split.train,
    )
    return scenario_frame, result, manifest


def focus_events(
    result: PipelineResult,
    manifest: ScenarioManifest | None,
) -> tuple[TriageEvent, ...]:
    if manifest is None:
        return result.events[:100]
    window_end = manifest.end_at + timedelta(minutes=30)
    focused = tuple(
        event
        for event in result.events
        if event.start_at <= window_end and event.end_at >= manifest.start_at
    )
    return focused or result.events[:100]


def event_label(event: TriageEvent) -> str:
    status = STATUS_VIEWS[event.triage_status]
    timestamp = event.start_at.strftime("%b %d %H:%M UTC")
    return f"{status.symbol} {status.label} · {timestamp}"


def timeline_figure(frame: pd.DataFrame, event: TriageEvent) -> go.Figure:
    start = event.start_at - timedelta(hours=4)
    end = event.end_at + timedelta(hours=4)
    visible = frame.loc[start:end]
    if visible.empty:
        visible = frame.iloc[-96:]

    figure = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=("Temperature", "Conductivity", "pH", "Dissolved oxygen"),
    )
    for row, sensor in enumerate(SENSOR_COLORS, start=1):
        figure.add_trace(
            go.Scatter(
                x=visible.index,
                y=visible[sensor],
                mode="lines",
                name=sensor,
                line={"color": SENSOR_COLORS[sensor], "width": 1.8},
                connectgaps=False,
            ),
            row=row,
            col=1,
        )
    figure.add_vrect(
        x0=event.start_at,
        x1=event.end_at + timedelta(minutes=1),
        fillcolor="#F4A261",
        opacity=0.18,
        line_width=1,
        line_color="#A44A3F",
    )
    figure.update_yaxes(domain=(0.78, 0.945), row=1, col=1)
    figure.layout.annotations[0].update(y=0.945)
    figure.update_layout(
        height=520,
        margin={"l": 24, "r": 12, "t": 42, "b": 24},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        hovermode="x unified",
        template="plotly_white",
    )
    return figure


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.5rem; max-width: 1500px;}
        h1 {font-size: 2rem !important; letter-spacing: 0 !important;}
        .summary-value {font-size: 1.15rem; font-weight: 650; line-height: 1.3; border-bottom: 1px solid #DDE3E8; padding-bottom: .6rem; min-height: 2.2rem;}
        .triage-status {border-left: 5px solid; border-radius: 6px; padding: .75rem .9rem; margin-bottom: 1rem;}
        .triage-symbol {font-size: 1.15rem; margin-right: .35rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(
    page_title="ClearSignal WQ",
    page_icon=":material/water_drop:",
    layout="wide",
)
inject_styles()
st.title("ClearSignal WQ")
st.caption("Water sensor event triage workspace · Operator review required")

control_site, control_mode = st.columns((1, 2))
with control_site:
    st.selectbox("Site", ("Main Street",), key="site-select")
with control_mode:
    mode = st.selectbox("Mode", tuple(MODE_TO_SCENARIO), key="mode-select")

if not DATA_PATH.is_file():
    st.error("The approved public dataset is not available locally.")
    st.code("python scripts/download_data.py")
    st.stop()

try:
    frame, pipeline_result, scenario_manifest = analyze_mode(mode)
except (OSError, TypeError, ValueError):
    st.error(
        "Analysis stopped because the approved data failed validation. "
        "Run `python scripts/download_data.py` and try again."
    )
    st.stop()

events = focus_events(pipeline_result, scenario_manifest)
if not events:
    st.warning("No reviewable events were found for this mode.")
    st.stop()

source_label = (
    "Synthetic scenario / 合成场景"
    if scenario_manifest is not None
    else "Public real sensor data"
)
summary_source, summary_model, summary_events, summary_hash = st.columns(4)
for column, label, value in (
    (summary_source, "Data source", source_label),
    (summary_model, "Model", pipeline_result.model_version),
    (summary_events, "Review queue", str(len(events))),
    (summary_hash, "Run hash", pipeline_result.data_hash[:10]),
):
    with column:
        st.caption(label)
        st.markdown(f'<div class="summary-value">{value}</div>', unsafe_allow_html=True)

if scenario_manifest is None:
    st.caption(
        "Source: pyhydroqc MainStreet2019.csv · fixed upstream commit "
        f"{UPSTREAM_COMMIT} · technician labels describe sensor data quality, "
        "not laboratory-confirmed water conditions."
    )
else:
    st.info(
        f"Synthetic scenario / 合成场景: {scenario_manifest.name}. "
        "Injected into a fixed clean window; source observations remain unchanged."
    )

queue_column, timeline_column, evidence_column = st.columns((1.05, 2.2, 1.25))
with queue_column:
    st.subheader("Event queue")
    event_ids = tuple(event.event_id for event in events)
    event_by_id = {event.event_id: event for event in events}
    selected_id = st.selectbox(
        "Event",
        event_ids,
        format_func=lambda event_id: event_label(event_by_id[event_id]),
        key="event-select",
    )
    selected_event = event_by_id[selected_id]
    queue_rows = [
        {
            "status": STATUS_VIEWS[event.triage_status].symbol,
            "time": event.start_at.strftime("%m-%d %H:%M"),
            "sensors": ", ".join(event.affected_sensors),
        }
        for event in events[:12]
    ]
    st.dataframe(queue_rows, hide_index=True, width="stretch", height=300)
    st.caption("Priority-sorted. Public mode shows the first 100 events.")

with timeline_column:
    st.subheader("Sensor timeline")
    st.plotly_chart(
        timeline_figure(frame, selected_event),
        width="stretch",
        key="sensor-timeline",
        config={"displayModeBar": False},
    )

with evidence_column:
    st.subheader("Evidence and actions")
    status_view = STATUS_VIEWS[selected_event.triage_status]
    st.markdown(
        f'<div class="triage-status" style="border-color:{status_view.color};'
        f'background:{status_view.background};color:{status_view.color}">'
        f'<span class="triage-symbol">{status_view.symbol}</span>'
        f"<strong>{status_view.label}</strong></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{selected_event.start_at:%Y-%m-%d %H:%M} to "
        f"{selected_event.end_at:%Y-%m-%d %H:%M} UTC · "
        f"Evidence strength: {selected_event.evidence_strength.value}"
    )
    st.markdown(f"**Affected sensors:** {', '.join(selected_event.affected_sensors)}")
    st.markdown("**Structured evidence**")
    for item in selected_event.evidence[:8]:
        sensor = f" `{item.sensor}`" if item.sensor else ""
        st.markdown(f"- **{item.code}**{sensor}: {item.message}")
    st.markdown("**Recommended operator action**")
    st.write(selected_event.recommended_action)
    st.markdown("**Limitations**")
    for limitation in selected_event.limitations:
        st.markdown(f"- {limitation}")

    saved_actions = st.session_state.get("event_actions", {})
    saved_action = saved_actions.get(selected_event.event_id)
    action = st.segmented_control(
        "Operator action",
        ACTION_OPTIONS,
        default=saved_action or ACTION_OPTIONS[0],
        key="action-select",
    )
    if st.button("Save action", icon=":material/save:", key="save-action"):
        st.session_state["event_actions"] = {
            **saved_actions,
            selected_event.event_id: action,
        }
        st.success("Saved for this demo session only; source data was not changed.")

st.caption(
    "Decision support only. Every event requires operator review and, when relevant, "
    "independent field or laboratory verification."
)
