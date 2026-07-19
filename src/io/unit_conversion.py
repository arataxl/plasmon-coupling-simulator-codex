"""API/UI境界で使う長さ・断面積の単位変換。物理層はSI単位を維持する。"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


METRES_PER_NANOMETRE = 1.0e-9
SQUARE_METRES_PER_SQUARE_NANOMETRE = METRES_PER_NANOMETRE**2


def nanometres_to_metres(values: float | ArrayLike) -> float | NDArray[np.float64]:
    """nmをmへ変換する。"""
    converted = np.asarray(values, dtype=np.float64) * METRES_PER_NANOMETRE
    if converted.ndim == 0:
        return float(converted)
    return converted


def metres_to_nanometres(values: float | ArrayLike) -> float | NDArray[np.float64]:
    """mをnmへ変換する。"""
    converted = np.asarray(values, dtype=np.float64) / METRES_PER_NANOMETRE
    if converted.ndim == 0:
        return float(converted)
    return converted


def square_metres_to_square_nanometres(
    values: float | ArrayLike,
) -> float | NDArray[np.float64]:
    """m^2をnm^2へ変換する。表示層でのみ使う。"""
    converted = np.asarray(values, dtype=np.float64) / SQUARE_METRES_PER_SQUARE_NANOMETRE
    if converted.ndim == 0:
        return float(converted)
    return converted
