"""静的UIの言語切替とQCM説明の配置を軽量に検証する。"""

from __future__ import annotations

import json
from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPOSITORY_ROOT / "web"


def _translation_keys(language: str) -> set[str]:
    translation_path = WEB_ROOT / "js" / "i18n" / f"{language}.json"
    with translation_path.open(encoding="utf-8") as translation_file:
        translations = json.load(translation_file)
    assert isinstance(translations, dict)
    assert all(isinstance(key, str) and isinstance(value, str) for key, value in translations.items())
    return set(translations)


def test_japanese_and_english_translation_catalogues_have_matching_keys() -> None:
    """言語切替時に未翻訳キーを露出させない。"""
    japanese_keys = _translation_keys("ja")
    english_keys = _translation_keys("en")

    assert japanese_keys == english_keys
    assert {
        "qcm.scopeTooltip",
        "result.qcmStatus",
        "warning.nirCdaLimit",
        "actions.calculate",
        "actions.cancel",
    } <= japanese_keys


def test_qcm_scope_is_not_a_configuration_tab_and_is_available_at_gap_inputs() -> None:
    """QCMの適用範囲は入力タブでなく、ギャップ入力の補助情報へ集約する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'id="qcm-tab-button"' not in index
    assert 'id="qcm-tab"' not in index
    assert index.count('data-i18n-tooltip="qcm.scopeTooltip"') == 3
    assert 'id="qcm-notice"' in index
    assert 'data-i18n="result.qcmStatus"' in index


def test_i18n_loader_precedes_ui_modules() -> None:
    """動的に生成する入力行・警告より先に翻訳関数を読み込む。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert index.index('/static/js/i18n.js') < index.index('/static/js/input_form.js')
    assert 'data-language="ja"' in index
    assert 'data-language="en"' in index


def test_index_translation_attributes_reference_catalogue_keys() -> None:
    """静的DOMの翻訳属性に未定義キーを置かない。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    referenced_keys = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', index))

    assert referenced_keys <= _translation_keys("ja")


def test_preview_uses_nm_meshes_without_camera_distance_resizing() -> None:
    """粒子径をデータ座標系の球メッシュで描き、カメラ距離へ依存しない。"""
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")

    assert 'type: "mesh3d"' in input_form
    assert "function createSphereMesh" in input_form
    assert "const radiusNm = particle.diameter_nm / 2.0;" in input_form
    assert "const sphereLatitudeSegments = 8;" in input_form
    assert "const sphereLongitudeSegments = 12;" in input_form
    assert '"plotly_relayout"' not in input_form
    assert '"marker.size"' not in input_form
    assert 'tickmode: "linear"' in input_form
    assert "dtick: niceTickStep(range)" in input_form


def test_preview_uses_a_dedicated_panel_with_minimum_display_area() -> None:
    """プレビューを結果グラフから分離し、400px以上の表示領域を確保する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    stylesheet = (WEB_ROOT / "css" / "app.css").read_text(encoding="utf-8")

    assert index.index('class="panel preview-panel"') < index.index('class="panel result-panel"')
    assert ".preview-panel" in stylesheet
    assert ".geometry-preview" in stylesheet
    assert "min-height: 28rem;" in stylesheet
