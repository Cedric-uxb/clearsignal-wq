from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).parents[2]
START_SCRIPT = ROOT / "scripts" / "run_app.sh"

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="module")
def app_url() -> Iterator[str]:
    port = _free_port()
    process = subprocess.Popen(
        [START_SCRIPT],
        cwd=ROOT,
        env={**os.environ, "PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Streamlit exited before becoming ready")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("Streamlit did not become ready within 120 seconds")

    yield url
    process.terminate()
    process.wait(timeout=10)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


def _open_dashboard(
    browser: Browser,
    app_url: str,
    *,
    width: int = 1440,
    height: int = 900,
) -> Page:
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(app_url, wait_until="domcontentloaded", timeout=120_000)
    page.get_by_role("heading", name="Evidence and actions").wait_for(timeout=120_000)
    return page


def _select_mode(page: Page, mode: str) -> None:
    page.get_by_role("combobox", name="Mode").click()
    page.get_by_text(mode, exact=True).click()
    page.get_by_text("Synthetic scenario / 合成场景:", exact=False).wait_for(
        timeout=120_000
    )


def test_drift_scenario_shows_calibration_triage(
    browser: Browser,
    app_url: str,
) -> None:
    page = _open_dashboard(browser, app_url)
    _select_mode(page, "Single-sensor drift")

    page.get_by_text("Sensor fault or drift", exact=True).wait_for()
    assert page.get_by_text("清洁并校准传感器", exact=False).is_visible()
    assert page.locator(".js-plotly-plot").count() == 1
    page.close()


def test_correlated_shift_shows_retest_triage(
    browser: Browser,
    app_url: str,
) -> None:
    page = _open_dashboard(browser, app_url)
    _select_mode(page, "Correlated sensor shift")

    page.get_by_text("Possible water-quality event", exact=True).wait_for()
    assert page.get_by_text("现场复测", exact=False).is_visible()
    assert page.locator(".js-plotly-plot").count() == 1
    page.close()


def test_timeline_legend_does_not_overlap_temperature_title(
    browser: Browser,
    app_url: str,
) -> None:
    page = _open_dashboard(browser, app_url, width=692, height=752)

    legend = page.locator(".legend").bounding_box()
    temperature_title = (
        page.locator(".annotation-text").filter(has_text="Temperature").bounding_box()
    )

    assert legend is not None
    assert temperature_title is not None
    assert legend["y"] + legend["height"] + 4 <= temperature_title["y"]
    page.close()
