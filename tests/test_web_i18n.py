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
        "preset.maximumSurfaceGap",
        "api.randomClusterUnavailable",
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
    """粒子径を真球メッシュで描き、カメラ距離へ依存しない。"""
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")

    assert 'type: "mesh3d"' in input_form
    assert "function createSphereMesh" in input_form
    assert "const radiusNm = particle.diameter_nm / 2.0;" in input_form
    assert "const sphereLatitudeSegments = 16;" in input_form
    assert "const sphereLongitudeSegments = 16;" in input_form
    assert "const spherePalette = Object.freeze" in input_form
    assert 'opacity: 1' in input_form
    assert 'aspectmode: "cube"' in input_form
    assert "const labelOutlineTrace" in input_form
    assert 'mode: "markers+text"' not in input_form
    assert 'symbol: "square"' not in input_form
    assert 'marker: {' not in input_form
    assert "labelOutlineTrace, labelTrace" in input_form
    assert '"plotly_relayout"' not in input_form
    assert '"marker.size"' not in input_form
    assert 'tickmode: "linear"' in input_form
    assert "dtick: niceTickStep(range)" in input_form


def test_random_cluster_form_and_request_include_a_maximum_surface_gap() -> None:
    """ランダムクラスタの上限はUIとAPI要求の両方で明示する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")

    assert 'id="random-maximum-gap-nm"' in index
    assert 'data-i18n="preset.maximumSurfaceGap"' in index
    assert 'data-i18n="preset.randomGapHelp"' in index
    assert 'maximum_surface_gap_nm: maximumSurfaceGapNm' in input_form
    assert 't("validation.randomGapRange")' in input_form


def test_preset_errors_are_rendered_directly_below_their_own_actions() -> None:
    """各プリセットの失敗は、座標表ではなく実行ボタン直下で通知する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")

    for preset in ("dimer", "trimer", "random"):
        action_id = "apply-random-cluster" if preset == "random" else f"apply-{preset}"
        error_id = f'{preset}-preset-error'
        assert index.index(f'id="{action_id}"') < index.index(f'id="{error_id}"')
        assert f'showPresetError("{preset}", error)' in input_form


def test_client_uses_i18n_messages_for_structured_backend_errors() -> None:
    """API/SSEの内部例外文を画面にそのまま出さず、現在の言語で表示する。"""
    api_client = (WEB_ROOT / "js" / "api_client.js").read_text(encoding="utf-8")
    progress = (WEB_ROOT / "js" / "progress.js").read_text(encoding="utf-8")

    assert 'random_cluster_generation_failed: "api.randomClusterUnavailable"' in api_client
    assert 'preset_layout_invalid: "api.presetLayoutInvalid"' in api_client
    assert "body.error?.message" not in api_client
    assert "data.message" not in progress


def test_preview_uses_a_dedicated_panel_with_minimum_display_area() -> None:
    """プレビューを結果グラフから分離し、400px以上の表示領域を確保する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    stylesheet = (WEB_ROOT / "css" / "app.css").read_text(encoding="utf-8")

    assert index.index('class="panel preview-panel"') < index.index('class="panel result-panel"')
    assert ".preview-panel" in stylesheet
    assert ".geometry-preview" in stylesheet
    assert "min-height: 28rem;" in stylesheet
