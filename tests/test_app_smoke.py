from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).parents[1] / "app.py"
SYNTHETIC_MODES = (
    "Correlated sensor shift",
    "Single-sensor drift",
    "Missing data interval",
)
BANNED_CLAIMS = (
    "safe to drink",
    "drinkable",
    "confirmed contamination",
    "水可安全饮用",
    "污染已确认",
)


def _visible_copy(app: AppTest) -> str:
    element_types = (
        "title",
        "header",
        "subheader",
        "caption",
        "markdown",
        "text",
        "info",
        "warning",
        "success",
        "error",
    )
    return "\n".join(
        str(element.value)
        for element_type in element_types
        for element in app.get(element_type)
    ).lower()


def test_dashboard_supports_the_operator_review_flow() -> None:
    app = AppTest.from_file(APP_PATH).run(timeout=120)

    assert not app.exception
    assert app.title[0].value == "ClearSignal WQ"
    assert {item.label for item in app.selectbox} >= {"Site", "Mode", "Event"}
    assert {item.value for item in app.subheader} >= {
        "Event queue",
        "Sensor timeline",
        "Evidence and actions",
    }
    assert app.get_by_key("sensor-timeline") is not None
    assert "operator review required" in _visible_copy(app)

    for mode in SYNTHETIC_MODES:
        app.selectbox(key="mode-select").set_value(mode)
        app.run(timeout=120)
        assert not app.exception
        assert "synthetic scenario / 合成场景" in _visible_copy(app)

    app.segmented_control(key="action-select").set_value("Pending retest / 待复测")
    app.button(key="save-action").click()
    app.run(timeout=120)

    assert "saved for this demo session only" in _visible_copy(app)
    assert not any(claim in _visible_copy(app) for claim in BANNED_CLAIMS)
