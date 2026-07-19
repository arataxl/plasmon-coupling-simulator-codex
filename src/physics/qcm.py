"""Esteban et al. (2012) Fig. 2dのAu暫定表を用いるQCM距離パラメータ。

このモジュールはQCM薄層やCDAへの統合を行わず、版管理された暫定デジタイズ表を
補間する純粋な物理層だけを提供する。表はAu jelliumの青色実線をWebPlotDigitizerで
手動読取りしたものであり、原著者の数値表・係数表ではない。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import PchipInterpolator


ANGSTROMS_PER_NANOMETRE = 10.0
QCM_PARAMETER_STATUS = "provisional_digitized"

FloatArray = NDArray[np.float64]


class QcmParameterError(ValueError):
    """QCM距離依存パラメータの入力または適用範囲が不正であることを示す。"""


class QcmSeparationBelowDigitizedRangeError(QcmParameterError):
    """デジタイズ表の下限未満に対する外挿を拒否する。"""


@dataclass(frozen=True)
class GammaGParameterTable:
    """`gamma_g(l)` 暫定表。距離はÅ、減衰はeVで保持する。"""

    separation_angstrom: FloatArray
    gamma_g_ev: FloatArray

    def __post_init__(self) -> None:
        separations = np.asarray(self.separation_angstrom, dtype=np.float64)
        gamma_values = np.asarray(self.gamma_g_ev, dtype=np.float64)
        if separations.ndim != 1 or gamma_values.ndim != 1:
            raise QcmParameterError("QCM parameter table columns must be one-dimensional")
        if len(separations) < 2 or len(separations) != len(gamma_values):
            raise QcmParameterError("QCM parameter table must contain matching columns")
        if not (np.all(np.isfinite(separations)) and np.all(np.isfinite(gamma_values))):
            raise QcmParameterError("QCM parameter table must contain finite values")
        if np.any(separations <= 0.0) or np.any(gamma_values <= 0.0):
            raise QcmParameterError("QCM parameter table values must be positive")
        if np.any(np.diff(separations) <= 0.0):
            raise QcmParameterError("QCM separation values must be strictly increasing")
        object.__setattr__(self, "separation_angstrom", separations)
        object.__setattr__(self, "gamma_g_ev", gamma_values)

    @property
    def separation_range_angstrom(self) -> tuple[float, float]:
        """補間可能な最小・最大分離距離をÅで返す。"""
        return (
            float(self.separation_angstrom[0]),
            float(self.separation_angstrom[-1]),
        )


@dataclass(frozen=True)
class GammaGInterpolationResult:
    """`gamma_g` 補間または古典極限への切替結果を保持する。"""

    separation_nm: float
    gamma_g_ev: float | None
    classical_limit: bool
    parameter_status: str = QCM_PARAMETER_STATUS


def _require_finite_nonnegative(value: float, *, name: str) -> float:
    if not math.isfinite(value) or value < 0.0:
        raise QcmParameterError(f"{name} must be finite and non-negative")
    return value


def interpolate_gamma_g_from_separation_nm(
    *,
    separation_nm: float,
    parameter_table: GammaGParameterTable,
) -> GammaGInterpolationResult:
    """分離距離nmから、暫定表の `gamma_g(l)` をeVで補間する。

    入力はこの表参照境界でのみnmとし、内部ではÅへ変換する。nmはSI単位ではないが、
    指定されたQCM表と粒子間ギャップの表示単位に合わせた明示的な変換である。
    ``log(gamma_g)`` に対するPCHIP補間を用いるため、正値と単調なデジタイズ曲線を
    保ちながら、通常のY値線形補間より片対数軸の指数的変化を適切に表現する。

    表の上限5.439 Åを超える場合は外挿せず、`classical_limit=True` と
    ``gamma_g_ev=None`` を返す。QCMの架空導電性媒質では大きい減衰がトンネル伝導を
    ゼロへ近づけるため、この範囲に有限の減衰値を創作するより通常の古典極限として
    扱う方が安全である。`gamma_g=0` は高伝導を意味して逆の物理になるため返さない。
    表の下限未満はデジタイズ根拠がないため、明示的な例外で拒否する。

    出典：Esteban et al., *Nature Communications* 3, 825 (2012), Fig. 2dの
    Au jellium青色実線。デジタイズ値の出典・不確かさは
    ``data/qcm/metadata.yaml`` を正とする。
    """
    separation_nm = _require_finite_nonnegative(
        separation_nm,
        name="separation_nm",
    )
    separation_angstrom = separation_nm * ANGSTROMS_PER_NANOMETRE
    minimum_angstrom, maximum_angstrom = parameter_table.separation_range_angstrom
    if separation_angstrom < minimum_angstrom:
        raise QcmSeparationBelowDigitizedRangeError(
            "separation is below the minimum digitized QCM gamma_g range "
            f"({separation_angstrom:.6g} Å < {minimum_angstrom:.6g} Å)"
        )
    if separation_angstrom > maximum_angstrom:
        return GammaGInterpolationResult(
            separation_nm=separation_nm,
            gamma_g_ev=None,
            classical_limit=True,
        )

    interpolator = PchipInterpolator(
        parameter_table.separation_angstrom,
        np.log(parameter_table.gamma_g_ev),
        extrapolate=False,
    )
    gamma_g_ev = float(np.exp(interpolator(separation_angstrom)))
    if not math.isfinite(gamma_g_ev) or gamma_g_ev <= 0.0:
        raise FloatingPointError("interpolated QCM gamma_g is non-finite or non-positive")
    return GammaGInterpolationResult(
        separation_nm=separation_nm,
        gamma_g_ev=gamma_g_ev,
        classical_limit=False,
    )
