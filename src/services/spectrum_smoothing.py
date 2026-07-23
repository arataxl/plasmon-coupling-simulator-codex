"""API 応答用スペクトルの表示後処理を提供する。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import savgol_filter


SMOOTHING_LEVELS: dict[str, tuple[int, int]] = {
    "low": (5, 2),
    "medium": (9, 3),
    "high": (15, 3),
    "very_high": (21, 4),
    "extreme": (31, 4),
}
SMOOTHING_DEFAULT_LEVEL = "medium"


@dataclass(frozen=True)
class SmoothedCrossSections:
    """生データと Savitzky--Golay 後処理済み断面積を保持する。"""

    raw_c_ext_m2: np.ndarray
    raw_c_sca_m2: np.ndarray
    raw_c_abs_m2: np.ndarray
    c_ext_m2: np.ndarray
    c_sca_m2: np.ndarray
    c_abs_m2: np.ndarray
    smoothing_level: str


def smooth_spectrum_cross_sections(
    *,
    c_ext_m2: np.ndarray,
    c_sca_m2: np.ndarray,
    c_abs_m2: np.ndarray,
    level: str = SMOOTHING_DEFAULT_LEVEL,
) -> SmoothedCrossSections:
    """表示用に Cext/Csca を Savitzky--Golay 平滑化する。

    この関数は物理計算値を置き換えるものではなく、API 応答直前の
    スペクトル表示用後処理である。5 点未満ではフィルタの有効窓を
    構成できないため、生データをそのまま返す。Cabs は独立に平滑化
    せず、常に返却する Cext - Csca から再計算してエネルギー収支を
    保つ。
    """
    if level not in SMOOTHING_LEVELS:
        raise ValueError(f"unknown smoothing level: {level}")
    window_length, polyorder = SMOOTHING_LEVELS[level]
    raw_c_ext = np.asarray(c_ext_m2, dtype=np.float64).copy()
    raw_c_sca = np.asarray(c_sca_m2, dtype=np.float64).copy()
    raw_c_abs = np.asarray(c_abs_m2, dtype=np.float64).copy()
    lengths = {raw_c_ext.size, raw_c_sca.size, raw_c_abs.size}
    if len(lengths) != 1 or raw_c_ext.ndim != raw_c_sca.ndim or raw_c_ext.ndim != raw_c_abs.ndim:
        raise ValueError("cross-section arrays must be one-dimensional and have matching lengths")

    if raw_c_ext.size < window_length:
        smoothed_c_ext = raw_c_ext.copy()
        smoothed_c_sca = raw_c_sca.copy()
        smoothed_c_abs = raw_c_abs.copy()
    else:
        smoothed_c_ext = savgol_filter(
            raw_c_ext,
            window_length=window_length,
            polyorder=polyorder,
        )
        smoothed_c_sca = savgol_filter(
            raw_c_sca,
            window_length=window_length,
            polyorder=polyorder,
        )
        smoothed_c_abs = np.asarray(
            smoothed_c_ext - smoothed_c_sca,
            dtype=np.float64,
        )

    return SmoothedCrossSections(
        raw_c_ext_m2=raw_c_ext,
        raw_c_sca_m2=raw_c_sca,
        raw_c_abs_m2=raw_c_abs,
        c_ext_m2=np.asarray(smoothed_c_ext, dtype=np.float64),
        c_sca_m2=np.asarray(smoothed_c_sca, dtype=np.float64),
        c_abs_m2=np.asarray(smoothed_c_abs, dtype=np.float64),
        smoothing_level=level,
    )
