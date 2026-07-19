"""再計算用にブラウザ出力JSONを検証して読み込む。"""

from __future__ import annotations

import json

from pydantic import ValidationError

from src.schemas.result import SimulationResult


class SimulationResultImportError(ValueError):
    """JSONの構文または結果スキーマが出力契約を満たさない。"""


def simulation_result_from_json(serialized: str | bytes) -> SimulationResult:
    """出力JSONをPydantic契約で検証し、再計算可能な結果として返す。"""
    try:
        return SimulationResult.model_validate_json(serialized)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
        raise SimulationResultImportError(
            "simulation result JSON does not match the reproducibility schema"
        ) from error
