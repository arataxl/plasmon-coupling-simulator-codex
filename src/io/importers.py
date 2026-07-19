"""再計算用にブラウザ出力JSONを検証して読み込む。"""

from __future__ import annotations

import json

from pydantic import ValidationError

from src.schemas.result import SimulationResult


class SimulationResultImportError(ValueError):
    """JSONの構文または結果スキーマが出力契約を満たさない。"""


def simulation_result_from_json(serialized: str | bytes) -> SimulationResult:
    """ブラウザ付加のダウンロード来歴を除き、結果を再計算可能な形で読む。"""
    try:
        parsed = json.loads(serialized)
        if isinstance(parsed, dict):
            # ブラウザ出力だけに付加する時刻・ファイル名来歴は、再計算入力ではない。
            parsed.pop("download_metadata", None)
        return SimulationResult.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
        raise SimulationResultImportError(
            "simulation result JSON does not match the reproducibility schema"
        ) from error
