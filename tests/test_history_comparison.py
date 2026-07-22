"""履歴スペクトル比較の正規化ロジックをブラウザ上で検証する。"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPARISON_MODULE = REPOSITORY_ROOT / "web" / "js" / "history_comparison.js"


def _chrome_executable() -> str:
    candidates = (
        os.environ.get("CHROME_PATH"),
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise AssertionError("Headless Chrome is required for the history comparison test")


def _dump_dom_in_chrome(tmp_path: Path, html: str) -> str:
    harness = tmp_path / "comparison.html"
    profile = tmp_path / "chrome-profile"
    harness.write_text(html, encoding="utf-8")
    completed = subprocess.run(
        [
            _chrome_executable(),
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            f"--user-data-dir={profile}",
            "--virtual-time-budget=1000",
            "--dump-dom",
            harness.as_uri(),
        ],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def _attribute(document: str, name: str) -> str:
    marker = f'{name}="'
    start = document.find(marker)
    assert start >= 0, f"{name} was not rendered into the browser DOM"
    value_start = start + len(marker)
    value_end = document.find('"', value_start)
    assert value_end >= 0
    return document[value_start:value_end]


def test_history_comparison_selects_cross_sections_and_normalizes_known_values(
    tmp_path: Path,
) -> None:
    """Csca/Cabs選択、ピーク正規化、線形補間による任意波長正規化を検証する。"""
    entry = {
        "spectrum": {
            "wavelength_nm": [500.0, 600.0, 700.0],
            "c_ext_m2": [2.0e-18, 4.0e-18, 1.0e-18],
            "c_sca_m2": [3.0e-18, 6.0e-18, 9.0e-18],
            "c_abs_m2": [5.0e-18, 10.0e-18, 15.0e-18],
        }
    }
    entry_json = json.dumps(entry)
    module_uri = COMPARISON_MODULE.as_uri()
    html = f"""<!doctype html>
<html><body>
  <script src="{module_uri}"></script>
  <script>
    const entry = {entry_json};
    const comparison = window.PlasmonHistoryComparison;
    const peak = comparison.buildSeries([entry], "c_ext", {{ mode: "peak" }})[0].values;
    const reference = comparison.buildSeries(
      [entry], "c_ext", {{ mode: "reference", referenceWavelengthNm: 550 }}
    )[0].values;
    const scattering = comparison.buildSeries([entry], "c_sca", {{ mode: "absolute" }})[0].values;
    const absorption = comparison.buildSeries([entry], "c_abs", {{ mode: "absolute" }})[0].values;
    let outsideRangeCode = "";
    try {{
      comparison.buildSeries([entry], "c_ext", {{ mode: "reference", referenceWavelengthNm: 800 }});
    }} catch (error) {{
      outsideRangeCode = error.code;
    }}
    document.body.setAttribute("data-peak", JSON.stringify(peak));
    document.body.setAttribute("data-reference", JSON.stringify(reference));
    document.body.setAttribute("data-scattering", JSON.stringify(scattering));
    document.body.setAttribute("data-absorption", JSON.stringify(absorption));
    document.body.setAttribute("data-outside-range-code", outsideRangeCode);
  </script>
</body></html>"""

    document = _dump_dom_in_chrome(tmp_path, html)

    assert json.loads(_attribute(document, "data-peak")) == [0.5, 1, 0.25]
    reference = json.loads(_attribute(document, "data-reference"))
    assert math.isclose(reference[0], 2.0 / 3.0)
    assert math.isclose(reference[1], 4.0 / 3.0)
    assert math.isclose(reference[2], 1.0 / 3.0)
    assert json.loads(_attribute(document, "data-scattering")) == [3, 6, 9]
    assert json.loads(_attribute(document, "data-absorption")) == [5, 10, 15]
    assert _attribute(document, "data-outside-range-code") == "reference_wavelength_out_of_range"
