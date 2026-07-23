"""ヘッドレスChromeで、結果完了後のUI状態をDOMレベルで検証する。"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPOSITORY_ROOT / "web"
LANGUAGE_STORAGE_KEY = "plasmon-coupling-simulator.language.v1"


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
    raise AssertionError("Headless Chrome is required for the browser DOM workflow test")


def _dump_dom_in_chrome(tmp_path: Path, html: str) -> str:
    harness = tmp_path / "workflow.html"
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
    match = re.search(rf'{re.escape(name)}="([^"]*)"', document)
    assert match is not None, f"{name} was not rendered into the browser DOM"
    return match.group(1)


def test_completed_results_render_history_and_localized_legend_in_the_browser_dom(
    tmp_path: Path,
) -> None:
    """完了結果を2回渡すと、履歴と日本語/英語の凡例が実際のDOMへ反映される。"""
    japanese = json.loads((WEB_ROOT / "js" / "i18n" / "ja.json").read_text(encoding="utf-8"))
    english = json.loads((WEB_ROOT / "js" / "i18n" / "en.json").read_text(encoding="utf-8"))
    i18n_uri = (WEB_ROOT / "js" / "i18n.js").as_uri()
    history_uri = (WEB_ROOT / "js" / "history.js").as_uri()
    history_comparison_uri = (WEB_ROOT / "js" / "history_comparison.js").as_uri()
    results_uri = (WEB_ROOT / "js" / "results.js").as_uri()
    catalogues = json.dumps({"ja": japanese, "en": english}, ensure_ascii=False)
    result = json.dumps(
        {
            "input": {
                "particles": [
                    {"diameter_nm": 5.0, "x_nm": 148.0, "y_nm": -135.0, "z_nm": 76.0},
                    {"diameter_nm": 5.0, "x_nm": 148.0, "y_nm": -140.0, "z_nm": 73.0},
                    {"diameter_nm": 8.0, "x_nm": 10.0, "y_nm": 20.0, "z_nm": 30.0},
                    {"diameter_nm": 10.0, "x_nm": -1.0, "y_nm": -2.0, "z_nm": -3.0},
                ],
                "spectrum": {
                    "start_wavelength_nm": 600.0,
                    "end_wavelength_nm": 620.0,
                    "step_nm": 20.0,
                },
            },
            "spectrum": {
                "wavelength_nm": [600.0, 620.0],
                "c_ext_m2": [1.0e-18, 2.0e-18],
                "c_sca_m2": [0.2e-18, 0.4e-18],
                "c_abs_m2": [0.8e-18, 1.6e-18],
                "q_ext": [1.0, 2.0],
                "q_sca": [0.2, 0.4],
                "q_abs": [0.8, 1.6],
                "geometric_cross_section_m2": 1.0e-18,
            },
            "qcm_metadata": {"qcm_applied": False},
            "experimental_quadrupole_metadata": {"applied": False},
            "warnings": [],
        },
    )
    html = f"""<!doctype html>
<html><body>
  <button data-language="ja">日本語</button><button data-language="en">English</button>
  <span id="translated-cross-section" data-i18n="result.cExt">Cext</span>
  <button id="download-csv"></button><button id="download-json"></button>
  <label id="result-smoothing-control" hidden><select id="smoothing-toggle"><option value="off">off</option><option value="medium" selected>medium</option></select></label>
  <button id="history-compare"></button><button id="history-select-all"></button>
  <button id="history-deselect-all"></button><button id="history-download-all"></button>
  <button id="history-clear"></button><div id="history-list"></div>
  <select id="history-compare-quantity"><option value="c_ext">Cext</option><option value="c_sca">Csca</option><option value="c_abs">Cabs</option></select>
  <select id="history-normalization-mode"><option value="absolute">absolute</option><option value="peak">peak</option><option value="reference">reference</option></select>
  <label id="history-reference-wavelength-container"><input id="history-reference-wavelength-nm" /></label>
  <p id="history-comparison-error" hidden></p>
  <dialog id="history-detail-dialog"><h3 id="history-detail-title"></h3><button id="history-detail-close"></button><p id="history-detail-summary"></p><ol id="history-detail-particles"></ol></dialog>
  <div id="spectrum-plot"></div><details id="qcm-notice"></details><ul id="warning-list"></ul>
  <dd id="qcm-detail-status"></dd><dd id="qcm-detail-source"></dd><dd id="qcm-detail-figure"></dd>
  <dd id="qcm-detail-curve"></dd><dd id="qcm-detail-uncertainty"></dd>
  <dd id="qcm-detail-calibration"></dd><dd id="qcm-detail-interpolation"></dd>
  <script>
    const storage = new Map();
    Object.defineProperty(window, "localStorage", {{ value: {{
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    }} }});
    const catalogues = {catalogues};
    window.fetch = async (url) => {{
      const language = String(url).includes("/en.json") ? "en" : "ja";
      return {{ ok: true, json: async () => catalogues[language] }};
    }};
    window.Plotly = {{ newPlot: (_target, traces, layout) => {{
      const plot = document.getElementById("spectrum-plot");
      plot.textContent = traces.map((trace) => trace.name).join("|");
      plot.dataset.traceValues = JSON.stringify(traces.map((trace) => trace.y));
      plot.dataset.yAxisTitle = String(layout.yaxis.title);
    }} }};
  </script>
  <script src="{i18n_uri}"></script><script src="{history_uri}"></script><script src="{history_comparison_uri}"></script><script src="{results_uri}"></script>
  <script>
    (async () => {{
      await window.PlasmonI18n.initialize();
      window.PlasmonResults.initialize();
      const result = {result};
      window.PlasmonResults.completeResult(result);
      window.PlasmonResults.completeResult({{
        ...result,
        experimental_quadrupole_metadata: {{ applied: true }},
      }});
      document.body.setAttribute("data-initial-language", window.PlasmonI18n.getLanguage());
      document.body.setAttribute("data-history-count", document.querySelectorAll(".history-entry").length);
      document.body.setAttribute("data-stored-history-count", JSON.parse(window.localStorage.getItem("plasmon-coupling-simulator.history.v1")).length);
      document.body.setAttribute("data-japanese-legend", document.getElementById("spectrum-plot").textContent);
      document.body.setAttribute(
        "data-japanese-history-labels",
        [...document.querySelectorAll(".history-entry-label")].map((item) => item.textContent).join("|"),
      );
      document.getElementById("history-select-all").click();
      document.body.setAttribute(
        "data-all-selected",
        String([...document.querySelectorAll('.history-entry input[type="checkbox"]')].every((item) => item.checked)),
      );
      document.body.setAttribute(
        "data-compare-enabled",
        String(!document.getElementById("history-compare").disabled),
      );
      document.querySelector('[data-language="en"]').click();
      await new Promise((resolve) => window.setTimeout(resolve, 10));
      document.body.setAttribute("data-english-legend", document.getElementById("spectrum-plot").textContent);
      document.body.setAttribute(
        "data-english-history-labels",
        [...document.querySelectorAll(".history-entry-label")].map((item) => item.textContent).join("|"),
      );
      document.body.setAttribute("data-stored-language", window.localStorage.getItem("{LANGUAGE_STORAGE_KEY}"));
      await window.PlasmonI18n.setLanguage("ja", {{ remember: false }});
      await window.PlasmonI18n.initialize();
      document.body.setAttribute("data-remembered-language", window.PlasmonI18n.getLanguage());
      await window.PlasmonI18n.setLanguage("ja", {{ remember: false }});
      document.body.setAttribute(
        "data-history-summary",
        document.querySelector(".history-entry-particle-summary").textContent,
      );
      document.querySelector(".history-detail-button").click();
      document.body.setAttribute(
        "data-history-detail-open",
        String(document.getElementById("history-detail-dialog").open),
      );
      document.body.setAttribute(
        "data-history-detail-particle-count",
        String(document.querySelectorAll("#history-detail-particles li").length),
      );
      document.body.setAttribute(
        "data-history-detail-first-particle",
        document.querySelector("#history-detail-particles li").textContent,
      );
      document.getElementById("history-detail-close").click();
      document.getElementById("history-compare-quantity").value = "c_sca";
      document.getElementById("history-normalization-mode").value = "peak";
      document.getElementById("history-normalization-mode").dispatchEvent(new Event("change"));
      document.getElementById("history-compare").click();
      document.body.setAttribute(
        "data-peak-comparison-values",
        document.getElementById("spectrum-plot").dataset.traceValues,
      );
      document.body.setAttribute(
        "data-peak-comparison-axis",
        document.getElementById("spectrum-plot").dataset.yAxisTitle,
      );
      document.getElementById("history-compare-quantity").value = "c_abs";
      document.getElementById("history-compare-quantity").dispatchEvent(new Event("change"));
      document.getElementById("history-normalization-mode").value = "absolute";
      document.getElementById("history-normalization-mode").dispatchEvent(new Event("change"));
      document.body.setAttribute(
        "data-absorption-comparison-values",
        document.getElementById("spectrum-plot").dataset.traceValues,
      );
      document.getElementById("history-normalization-mode").value = "reference";
      document.getElementById("history-normalization-mode").dispatchEvent(new Event("change"));
      document.getElementById("history-reference-wavelength-nm").value = "610";
      document.getElementById("history-reference-wavelength-nm").dispatchEvent(new Event("change"));
      document.body.setAttribute(
        "data-reference-comparison-values",
        document.getElementById("spectrum-plot").dataset.traceValues,
      );
      document.getElementById("history-deselect-all").click();
      document.body.setAttribute(
        "data-all-deselected",
        String([...document.querySelectorAll('.history-entry input[type="checkbox"]')].every((item) => !item.checked)),
      );
    }})();
  </script>
</body></html>"""

    document = _dump_dom_in_chrome(tmp_path, html)

    assert _attribute(document, "data-initial-language") == "ja"
    assert _attribute(document, "data-history-count") == "2"
    assert _attribute(document, "data-stored-history-count") == "2"
    assert _attribute(document, "data-japanese-legend") == "消失強度（Cext）|散乱強度（Csca）|吸収強度（Cabs）"
    assert japanese["history.quadrupoleOn"] in _attribute(document, "data-japanese-history-labels")
    assert japanese["history.quadrupoleOff"] in _attribute(document, "data-japanese-history-labels")
    assert _attribute(document, "data-all-selected") == "true"
    assert _attribute(document, "data-compare-enabled") == "true"
    assert _attribute(document, "data-english-legend") == "Cext|Csca|Cabs"
    assert english["history.quadrupoleOn"] in _attribute(document, "data-english-history-labels")
    assert english["history.quadrupoleOff"] in _attribute(document, "data-english-history-labels")
    assert _attribute(document, "data-stored-language") == "en"
    assert _attribute(document, "data-remembered-language") == "en"
    assert _attribute(document, "data-history-summary") == " / ".join(
        [
            japanese["history.particleCompact"].format(
                index=1, diameterNm="5", xNm="148", yNm="-135", zNm="76"
            ),
            japanese["history.particleCompact"].format(
                index=2, diameterNm="5", xNm="148", yNm="-140", zNm="73"
            ),
            japanese["history.particleCompact"].format(
                index=3, diameterNm="8", xNm="10", yNm="20", zNm="30"
            ),
            japanese["history.additionalParticles"].format(count=1),
        ]
    )
    assert _attribute(document, "data-history-detail-open") == "true"
    assert _attribute(document, "data-history-detail-particle-count") == "4"
    assert _attribute(document, "data-history-detail-first-particle") == japanese[
        "history.particleDetail"
    ].format(index=1, diameterNm="5", xNm="148", yNm="-135", zNm="76")
    peak_values = json.loads(_attribute(document, "data-peak-comparison-values"))
    assert peak_values == [[0.5, 1], [0.5, 1]]
    assert _attribute(document, "data-peak-comparison-axis") == japanese[
        "history.normalizedYAxis"
    ].format(quantity=japanese["result.cSca"])
    for values in json.loads(_attribute(document, "data-absorption-comparison-values")):
        assert math.isclose(values[0], 0.8)
        assert math.isclose(values[1], 1.6)
    reference_values = json.loads(_attribute(document, "data-reference-comparison-values"))
    for values in reference_values:
        assert math.isclose(values[0], 2.0 / 3.0)
        assert math.isclose(values[1], 4.0 / 3.0)
    assert _attribute(document, "data-all-deselected") == "true"
