"""ブラウザ内の計算履歴UIについて、サーバー不要の構造契約を検証する。"""

from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPOSITORY_ROOT / "web"


def test_history_storage_caps_entries_at_thirty_and_discards_the_oldest() -> None:
    """31件目は先頭へ追加し、``slice(0, 30)``で最古の履歴を除外する。"""
    history = (WEB_ROOT / "js" / "history.js").read_text(encoding="utf-8")

    assert 'const maximumEntries = 30;' in history
    assert 'const entries = [entry, ...read()].slice(0, maximumEntries);' in history
    assert 'entries.slice(0, maximumEntries)' in history


def test_history_supports_deletion_and_individual_and_bulk_csv_exports() -> None:
    """個別削除・全削除・個別CSV・一括CSVの実装経路を保持する。"""
    history = (WEB_ROOT / "js" / "history.js").read_text(encoding="utf-8")
    results = (WEB_ROOT / "js" / "results.js").read_text(encoding="utf-8")
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'filter((entry) => entry.id !== entryId)' in history
    assert 'window.localStorage.removeItem(storageKey)' in history
    assert 'function csvForEntry(entry)' in history
    assert 'function csvForEntries(entries)' in history
    assert '"history_id,result_timestamp_utc,calculation_mode,particle_count' in history
    assert 'id="history-download-all"' in index
    assert 'id="history-clear"' in index
    assert 'window.PlasmonHistoryStore.csvForEntry(entry)' in results
    assert 'window.PlasmonHistoryStore.csvForEntries(entries)' in results
    assert 'function completeResult(result)' in results
    app = (WEB_ROOT / "js" / "app.js").read_text(encoding="utf-8")
    assert 'window.PlasmonResults.completeResult(result);' in app


def test_history_records_required_provenance_and_compares_selected_spectra() -> None:
    """履歴は再比較に必要な入力、スペクトル、QCM・実験近似来歴を持つ。"""
    history = (WEB_ROOT / "js" / "history.js").read_text(encoding="utf-8")
    results = (WEB_ROOT / "js" / "results.js").read_text(encoding="utf-8")

    for key in (
        "timestamp_utc",
        "calculation_mode",
        "particle_count",
        "qcm_applied",
        "smoothing_level",
        "experimental_quadrupole_coupling",
        "input: result.input",
        "spectrum: result.spectrum",
        "qcm_metadata",
        "experimental_quadrupole_metadata",
    ):
        assert key in history
    assert 'selectedHistoryIds.size < 2' in results
    assert 'function compareSelectedHistory()' in results


def test_japanese_cross_section_labels_are_localized_for_the_spectrum_legend() -> None:
    """日本語UIでは略号だけでなく断面積ラベルを日本語で表示する。"""
    with (WEB_ROOT / "js" / "i18n" / "ja.json").open(encoding="utf-8") as source:
        japanese = json.load(source)
    results = (WEB_ROOT / "js" / "results.js").read_text(encoding="utf-8")

    assert japanese["result.cExt"] == "消失強度（Cext）"
    assert japanese["result.cSca"] == "散乱強度（Csca）"
    assert japanese["result.cAbs"] == "吸収強度（Cabs）"
    assert 'name: t("result.cExt")' in results
    assert 'name: t("result.cSca")' in results
    assert 'name: t("result.cAbs")' in results
