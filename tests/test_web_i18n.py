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
        "warning.cdaGapLimitation",
        "warning.qcmApplied",
        "warning.qcmClassicalLimit",
        "warning.qcmValidationOverride",
        "warning.experimentalQuadrupoleCoupling",
        "experimental.quadrupoleLabel",
        "mode.exactMie",
        "mode.exactMieHelp",
        "validation.exactMieParticleCount",
        "actions.calculate",
        "actions.cancel",
        "preset.maximumSurfaceGap",
        "api.randomClusterUnavailable",
        "result.cExt",
        "result.cSca",
        "result.cAbs",
        "history.title",
        "preview.showParticleNumbers",
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
    assert index.index('/static/js/history.js') < index.index('/static/js/results.js')
    assert index.index('/static/js/history_comparison.js') < index.index('/static/js/results.js')
    assert 'data-language="ja"' in index
    assert 'data-language="en"' in index


def test_japanese_is_the_default_language_and_manual_choice_is_remembered() -> None:
    """ブラウザlocaleに依存せず、日本語を初期表示し、手動選択を保存する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    i18n = (WEB_ROOT / "js" / "i18n.js").read_text(encoding="utf-8")

    assert '<html lang="ja">' in index
    assert 'const defaultLanguage = "ja";' in i18n
    assert 'const languageStorageKey = "plasmon-coupling-simulator.language.v1";' in i18n
    assert 'await setLanguage(rememberedLanguage(), { remember: false });' in i18n
    assert 'rememberLanguage(currentLanguage);' in i18n
    assert 'document.documentElement.dataset.uiReady = "false";' in index
    assert 'html[data-ui-ready="false"] body { visibility: hidden; }' in index
    assert 'document.documentElement.dataset.uiReady = "true";' in i18n
    assert "navigator.language" not in i18n


def test_random_cluster_uses_a_twenty_nanometre_default_maximum_gap() -> None:
    """既定のランダムクラスタは過度に疎な250 nm上限を使わない。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'id="random-maximum-gap-nm" type="number" min="5" step="0.1" value="20"' in index


def test_index_translation_attributes_reference_catalogue_keys() -> None:
    """静的DOMの翻訳属性に未定義キーを置かない。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    referenced_keys = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', index))

    assert referenced_keys <= _translation_keys("ja")


def test_experimental_quadrupole_toggle_is_off_by_default_and_localized() -> None:
    """The incomplete ED--EQ path must be an explicit, translated opt-in."""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")
    results = (WEB_ROOT / "js" / "results.js").read_text(encoding="utf-8")

    assert 'id="experimental-quadrupole-coupling" type="checkbox"' in index
    assert 'data-i18n="experimental.quadrupoleLabel"' in index
    assert 'payload.experimental_quadrupole_coupling =' in input_form
    assert "experimental_quadrupole_coupling" in results
    assert (
        'experimental_quadrupole_coupling: "warning.experimentalQuadrupoleCoupling"'
        in results
    )


def test_exact_mie_mode_is_a_distinct_single_particle_choice() -> None:
    """The exact-Mie path must remain visibly and structurally separate from CDA."""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")

    assert 'id="simulation-mode"' in index
    assert 'value="exact_mie"' in index
    assert 'data-i18n="mode.exactMie"' in index
    assert 'class="multi-particle-only"' in index
    assert "const exactMieMinimumDiameterNm = 2;" in input_form
    assert "const exactMieMaximumDiameterNm = 500;" in input_form
    assert "validation.exactMieParticleCount" in input_form
    assert "simulation_mode: simulationMode" in input_form


def test_experimental_quadrupole_warning_keeps_the_required_japanese_limit_text() -> None:
    """The opt-in result warning must not be weakened or silently omitted."""
    with (WEB_ROOT / "js" / "i18n" / "ja.json").open(encoding="utf-8") as source:
        japanese = json.load(source)

    assert japanese["warning.experimentalQuadrupoleCoupling"] == (
        "この結果は近似的な電気四極子結合を含みます。磁気多重極を含まないため、"
        "エネルギー保存則は厳密には満たされません。定量的な精度は保証されず、"
        "近赤外域での傾向確認のみを目的としています。"
    )


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
    assert "const maximumParticleCount = 50;" in input_form
    assert "function sphereMeshResolution(particleCount)" in input_form
    assert "return particleCount > maximumQcmParticleCount" in input_form


def test_preview_particle_number_toggle_preserves_text_trace_hovering() -> None:
    """番号だけを空文字へ切り替え、球とホバー用のトレースは残す。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")

    assert 'id="show-particle-numbers" type="checkbox" checked' in index
    assert 'data-i18n="preview.showParticleNumbers"' in index
    assert "function particleNumberLabelsVisible()" in input_form
    assert "const labelText = particleNumberLabelsVisible()" in input_form
    assert input_form.count("text: labelText,") == 2
    assert 'addEventListener("change", renderPreview)' in input_form


def test_input_limit_is_rendered_once_as_an_inline_scope_note() -> None:
    """上限説明は一つの通常テキスト要素だけで表示する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    stylesheet = (WEB_ROOT / "css" / "app.css").read_text(encoding="utf-8")
    with (WEB_ROOT / "js" / "i18n" / "en.json").open(encoding="utf-8") as source:
        english = json.load(source)
    with (WEB_ROOT / "js" / "i18n" / "ja.json").open(encoding="utf-8") as source:
        japanese = json.load(source)

    assert index.count('data-i18n="input.limit"') == 1
    assert 'class="input-scope-note" data-i18n="input.limit"' in index
    assert index.index('data-i18n="input.help"') < index.index('data-i18n="input.limit"')
    assert "input.limit.lineOne" not in index
    assert "input.limit.lineTwo" not in index
    assert "input.limit.lineOne" not in english
    assert "input.limit.lineTwo" not in japanese
    assert english["input.limit"] == "Up to 50 particles (more than 20: classical CDA, all gaps > 5 nm)."
    assert japanese["input.limit"] == "最大50粒子（21粒子以上は古典CDA・全gap > 5 nm）。"
    assert ".input-limit" not in stylesheet
    assert ".input-limit-line" not in stylesheet


def test_input_limit_note_does_not_use_fixed_badge_css() -> None:
    """見出し横の固定バッジ用スタイルを再導入しない。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    stylesheet = (WEB_ROOT / "css" / "app.css").read_text(encoding="utf-8")

    assert index.count('data-i18n="input.limit"') == 1
    assert 'class="input-scope-note" data-i18n="input.limit"' in index
    assert ".input-limit" not in stylesheet
    assert ":root[lang=\"en\"] .input-panel .panel-heading" not in stylesheet


def test_random_cluster_form_and_request_include_a_maximum_surface_gap() -> None:
    """ランダムクラスタの上限はUIとAPI要求の両方で明示する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")

    assert 'id="random-maximum-gap-nm"' in index
    assert 'data-i18n="preset.maximumSurfaceGap"' in index
    assert 'data-i18n="preset.randomGapHelp"' in index
    assert 'maximum_surface_gap_nm: maximumSurfaceGapNm' in input_form
    assert 'createLocalizedError("validation.randomGapRange")' in input_form


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


def test_existing_results_errors_and_progress_are_retranslated_after_language_switch() -> None:
    """構造化警告と表示中の状態は、言語切替後に翻訳カタログから描画し直す。"""
    api_client = (WEB_ROOT / "js" / "api_client.js").read_text(encoding="utf-8")
    app = (WEB_ROOT / "js" / "app.js").read_text(encoding="utf-8")
    i18n = (WEB_ROOT / "js" / "i18n.js").read_text(encoding="utf-8")
    input_form = (WEB_ROOT / "js" / "input_form.js").read_text(encoding="utf-8")
    results = (WEB_ROOT / "js" / "results.js").read_text(encoding="utf-8")

    assert "errorForCode," in api_client
    assert "createLocalizedError" in i18n
    assert "errorMessage" in i18n
    assert "currentError" in app
    assert "progressStatus" in app
    assert 'window.addEventListener("plasmonlanguagechange"' in app
    assert "translationDescriptors" in input_form
    assert "warningTranslationKeyByCode" in results
    assert 'window.addEventListener("plasmonlanguagechange"' in results


def test_preview_uses_a_dedicated_panel_with_minimum_display_area() -> None:
    """プレビューを結果グラフから分離し、400px以上の表示領域を確保する。"""
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    stylesheet = (WEB_ROOT / "css" / "app.css").read_text(encoding="utf-8")

    assert index.index('class="panel preview-panel"') < index.index('class="panel result-panel"')
    assert ".preview-panel" in stylesheet
    assert ".geometry-preview" in stylesheet
    assert "min-height: 28rem;" in stylesheet
