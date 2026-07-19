"""Esteban et al. (2012) Fig. 2dのAu暫定表を用いるQCM物理モデル。

表はAu jelliumの青色実線をWebPlotDigitizerで手動読取りしたものであり、原著者の
数値表・係数表ではない。QCMの局所誘電率はEsteban et al. (2012)の式(3)に基づき、
4層の環状ギャップ領域はCDAでは体積等価の補助双極子へ縮約する。このCDA縮約は
原論文のBEM/FEM実装そのものではなく、適用範囲と限界を
``docs/quantum_corrected_model_integration.md`` に記録する。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.constants import elementary_charge as ELEMENTARY_CHARGE_C
from scipy.constants import epsilon_0 as VACUUM_PERMITTIVITY_F_PER_M
from scipy.constants import hbar as REDUCED_PLANCK_CONSTANT_J_S
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq


ANGSTROMS_PER_NANOMETRE = 10.0
ANGSTROM_M = 1.0e-10
NANOMETRE_M = 1.0e-9
QCM_PARAMETER_STATUS = "provisional_digitized"
AU_JELLIUM_QCM_PLASMA_ENERGY_EV = 7.9
AU_JELLIUM_QCM_BULK_DAMPING_ENERGY_EV = 0.09
DEFAULT_QCM_LAYER_COUNT = 4
SUPPORTED_QCM_LAYER_COUNTS = frozenset((3, 4, 5))

FloatArray = NDArray[np.float64]


class QcmParameterError(ValueError):
    """QCM距離依存パラメータの入力または適用範囲が不正であることを示す。"""


class QcmSeparationBelowDigitizedRangeError(QcmParameterError):
    """デジタイズ表の下限未満に対する外挿を拒否する。"""


@dataclass(frozen=True)
class QcmGapPermittivity:
    """一つの局所ギャップ幅に対応するQCM相対誘電率。"""

    separation_m: float
    angular_frequency_rad_s: float
    medium_relative_permittivity: float
    gamma_g_ev: float | None
    gamma_g_rad_s: float | None
    relative_permittivity: complex
    classical_limit: bool


@dataclass(frozen=True)
class QcmBridgeLayer:
    """CDA補助双極子へ縮約する一つの環状QCM層。"""

    radial_inner_m: float
    radial_outer_m: float
    representative_separation_m: float
    volume_m3: float
    relative_permittivity: complex
    polarizability_si: complex


@dataclass(frozen=True)
class QcmBridge:
    """一つの近接粒子対に対するCDA用の補助双極子。"""

    position_m: FloatArray
    axis: FloatArray
    polarizability_si: complex
    layers: tuple[QcmBridgeLayer, ...]
    classical_limit: bool
    max_relative_permittivity_contrast: float


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


def energy_ev_to_angular_frequency_rad_s(energy_ev: float) -> float:
    """エネルギーeVを ``omega = E / hbar`` により角周波数rad/sへ変換する。

    ``E[eV] * e`` をJへ変換し、SIの換算定義 ``omega = E[J] / hbar[J s]`` を
    用いる。物理定数はNIST/CODATA 2022に対応するSciPy定数から取得する。
    """
    energy_ev = _require_finite_nonnegative(energy_ev, name="energy_ev")
    if energy_ev == 0.0:
        return 0.0
    angular_frequency_rad_s = (
        energy_ev * ELEMENTARY_CHARGE_C / REDUCED_PLANCK_CONSTANT_J_S
    )
    if not math.isfinite(angular_frequency_rad_s) or angular_frequency_rad_s <= 0.0:
        raise QcmParameterError("energy conversion produced an invalid angular frequency")
    return angular_frequency_rad_s


def _require_finite_positive(value: float, *, name: str) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise QcmParameterError(f"{name} must be finite and positive")
    return value


def calculate_qcm_gap_permittivity(
    *,
    separation_m: float,
    angular_frequency_rad_s: float,
    medium_relative_permittivity: float,
    parameter_table: GammaGParameterTable,
) -> QcmGapPermittivity:
    """局所分離距離からQCMの架空トンネル媒質の相対誘電率を構成する。

    Esteban et al., *Nature Communications* 3, 825 (2012), 式(3)は真空中の
    Drude型ギャップ媒質を

    ``epsilon_g(l, omega) = 1 - omega_p^2 / [omega (omega + i gamma_g(l))]``

    と定義する。ここでは同論文のAu jellium例で記録された
    ``hbar omega_p = 7.9 eV`` を用い、``gamma_g(l)`` はFig. 2dの暫定表から
    得る。これはJohnson and Christyのバルク誘電率やKreibig補正のパラメータへ
    転用しない。

    非真空の均一媒質では、Faraday Discussions 178, 151--183 (2015), 式(19)の
    媒質基線を採り、未校正のd電子減衰項を加えず

    ``epsilon_g(l, omega) = epsilon_medium
        - omega_p^2 / [omega (omega + i gamma_g(l))]``

    とする。これは真空では式(3)へ一致し、表の上限超過時に
    ``epsilon_g = epsilon_medium`` という古典極限へ厳密に戻る。Faraday Discussions
    論文はAu局所QCMでこのd電子項を無視しても主要なスペクトルを本質的に変えないと
    報告するが、本CDA縮約の定量精度を保証するものではない。

    すべての長さはm、角周波数はrad/s、誘電率は無次元の相対値である。デジタイズ表の
    上限を超える場合は有限値を外挿せず、媒質そのものを返す。
    """
    separation_m = _require_finite_nonnegative(separation_m, name="separation_m")
    angular_frequency_rad_s = _require_finite_positive(
        angular_frequency_rad_s,
        name="angular_frequency_rad_s",
    )
    medium_relative_permittivity = _require_finite_positive(
        medium_relative_permittivity,
        name="medium_relative_permittivity",
    )
    interpolation = interpolate_gamma_g_from_separation_nm(
        separation_nm=separation_m / NANOMETRE_M,
        parameter_table=parameter_table,
    )
    if interpolation.classical_limit:
        return QcmGapPermittivity(
            separation_m=separation_m,
            angular_frequency_rad_s=angular_frequency_rad_s,
            medium_relative_permittivity=medium_relative_permittivity,
            gamma_g_ev=None,
            gamma_g_rad_s=None,
            relative_permittivity=complex(medium_relative_permittivity),
            classical_limit=True,
        )

    assert interpolation.gamma_g_ev is not None
    plasma_frequency_rad_s = energy_ev_to_angular_frequency_rad_s(
        AU_JELLIUM_QCM_PLASMA_ENERGY_EV
    )
    gamma_g_rad_s = energy_ev_to_angular_frequency_rad_s(interpolation.gamma_g_ev)
    denominator = angular_frequency_rad_s * (
        angular_frequency_rad_s + 1j * gamma_g_rad_s
    )
    relative_permittivity = complex(
        medium_relative_permittivity - plasma_frequency_rad_s**2 / denominator
    )
    if not np.isfinite(relative_permittivity):
        raise FloatingPointError("QCM gap permittivity is non-finite")
    return QcmGapPermittivity(
        separation_m=separation_m,
        angular_frequency_rad_s=angular_frequency_rad_s,
        medium_relative_permittivity=medium_relative_permittivity,
        gamma_g_ev=interpolation.gamma_g_ev,
        gamma_g_rad_s=gamma_g_rad_s,
        relative_permittivity=relative_permittivity,
        classical_limit=False,
    )


def _as_position_m(values: ArrayLike, *, name: str) -> FloatArray:
    position_m = np.asarray(values, dtype=np.float64)
    if position_m.shape != (3,) or not np.all(np.isfinite(position_m)):
        raise QcmParameterError(f"{name} must be a finite vector with shape (3,)")
    return position_m


def _local_sphere_gap_m(
    *,
    center_distance_m: float,
    left_radius_m: float,
    right_radius_m: float,
    radial_distance_m: float,
) -> float:
    """二球の中心軸に平行な線上での局所ギャップ幅を返す。"""
    if radial_distance_m < 0.0 or radial_distance_m > min(left_radius_m, right_radius_m):
        raise QcmParameterError("radial distance is outside the opposing sphere surfaces")
    left_half_chord_m = math.sqrt(
        max(left_radius_m**2 - radial_distance_m**2, 0.0)
    )
    right_half_chord_m = math.sqrt(
        max(right_radius_m**2 - radial_distance_m**2, 0.0)
    )
    return center_distance_m - left_half_chord_m - right_half_chord_m


def _cm_polarizability_for_equivalent_sphere(
    *,
    volume_m3: float,
    inclusion_relative_permittivity: complex,
    medium_relative_permittivity: float,
) -> complex:
    """体積等価の小球に対するClausius--Mossotti SI分極率を返す。"""
    if volume_m3 <= 0.0:
        return 0.0j
    contrast = inclusion_relative_permittivity - medium_relative_permittivity
    denominator = inclusion_relative_permittivity + 2.0 * medium_relative_permittivity
    if denominator == 0.0 or not np.isfinite(denominator):
        raise QcmParameterError("QCM layer polarizability is singular")
    polarizability_si = (
        3.0
        * VACUUM_PERMITTIVITY_F_PER_M
        * medium_relative_permittivity
        * volume_m3
        * contrast
        / denominator
    )
    if not np.isfinite(polarizability_si):
        raise QcmParameterError("QCM layer polarizability is non-finite")
    return complex(polarizability_si)


def build_qcm_bridge_for_sphere_pair(
    *,
    left_position_m: ArrayLike,
    right_position_m: ArrayLike,
    left_radius_m: float,
    right_radius_m: float,
    angular_frequency_rad_s: float,
    medium_relative_permittivity: float,
    parameter_table: GammaGParameterTable,
    layer_count: int = DEFAULT_QCM_LAYER_COUNT,
) -> QcmBridge:
    """二球間のQCM環状層を、CDA用の一つの補助双極子へ縮約する。

    Esteban et al. (2012)は、局所ギャップ幅 ``l(rho)`` ごとの誘電率を同心環状
    シェルへ離散化し、BEM/FEMでMaxwell方程式を解く。CDAには局所面要素がないため、
    本MVPでは、表の上限以内の領域を等投影面積の ``layer_count`` 環状層へ分ける。
    各層は体積等価の小球のClausius--Mossotti分極率に写像し、その和を最接近点の
    中点に置く補助双極子の分極率とする。

    この写像は、QCM媒質と背景媒質のコントラストが小さいときの一次体積積分近似であり、
    環状層間の自己無撞着相互作用と局所場の横方向変化を捨てる。原論文のBEM/FEM実装と
    等価ではない。層数3/4/5の内部感度と、モデル誤差が外部参照なしには未評価であることを
    文書と結果メタデータへ残す。
    """
    if layer_count not in SUPPORTED_QCM_LAYER_COUNTS:
        raise QcmParameterError(
            "layer_count must be one of "
            f"{sorted(SUPPORTED_QCM_LAYER_COUNTS)} for QCM convergence checks"
        )
    left_radius_m = _require_finite_positive(left_radius_m, name="left_radius_m")
    right_radius_m = _require_finite_positive(right_radius_m, name="right_radius_m")
    left_position = _as_position_m(left_position_m, name="left_position_m")
    right_position = _as_position_m(right_position_m, name="right_position_m")
    displacement_m = right_position - left_position
    center_distance_m = float(np.linalg.norm(displacement_m))
    if not math.isfinite(center_distance_m) or center_distance_m <= 0.0:
        raise QcmParameterError("sphere centers must have a finite non-zero separation")
    axis = displacement_m / center_distance_m
    surface_gap_m = center_distance_m - left_radius_m - right_radius_m
    if surface_gap_m < 0.0:
        raise QcmParameterError("QCM bridge cannot be built for overlapping spheres")
    bridge_position = left_position + axis * (left_radius_m + surface_gap_m / 2.0)

    _, maximum_angstrom = parameter_table.separation_range_angstrom
    maximum_table_separation_m = maximum_angstrom * ANGSTROM_M
    if surface_gap_m >= maximum_table_separation_m:
        return QcmBridge(
            position_m=bridge_position,
            axis=axis,
            polarizability_si=0.0j,
            layers=(),
            classical_limit=True,
            max_relative_permittivity_contrast=0.0,
        )

    maximum_radial_distance_m = min(left_radius_m, right_radius_m)
    try:
        radial_limit_m = brentq(
            lambda radial_distance_m: _local_sphere_gap_m(
                center_distance_m=center_distance_m,
                left_radius_m=left_radius_m,
                right_radius_m=right_radius_m,
                radial_distance_m=radial_distance_m,
            )
            - maximum_table_separation_m,
            0.0,
            maximum_radial_distance_m,
        )
    except ValueError as error:
        raise QcmParameterError(
            "could not locate the QCM digitized-range boundary on the sphere pair"
        ) from error
    radial_boundaries_squared_m2 = np.linspace(
        0.0,
        radial_limit_m**2,
        layer_count + 1,
    )
    layers: list[QcmBridgeLayer] = []
    bridge_polarizability_si = 0.0j
    maximum_contrast = 0.0
    for layer_index in range(layer_count):
        radial_inner_m = math.sqrt(radial_boundaries_squared_m2[layer_index])
        radial_outer_m = math.sqrt(radial_boundaries_squared_m2[layer_index + 1])
        representative_radial_distance_m = math.sqrt(
            (radial_boundaries_squared_m2[layer_index]
            + radial_boundaries_squared_m2[layer_index + 1])
            / 2.0
        )
        representative_separation_m = _local_sphere_gap_m(
            center_distance_m=center_distance_m,
            left_radius_m=left_radius_m,
            right_radius_m=right_radius_m,
            radial_distance_m=representative_radial_distance_m,
        )
        permittivity = calculate_qcm_gap_permittivity(
            separation_m=representative_separation_m,
            angular_frequency_rad_s=angular_frequency_rad_s,
            medium_relative_permittivity=medium_relative_permittivity,
            parameter_table=parameter_table,
        )
        annular_area_m2 = math.pi * (radial_outer_m**2 - radial_inner_m**2)
        volume_m3 = annular_area_m2 * representative_separation_m
        polarizability_si = _cm_polarizability_for_equivalent_sphere(
            volume_m3=volume_m3,
            inclusion_relative_permittivity=permittivity.relative_permittivity,
            medium_relative_permittivity=medium_relative_permittivity,
        )
        layers.append(
            QcmBridgeLayer(
                radial_inner_m=radial_inner_m,
                radial_outer_m=radial_outer_m,
                representative_separation_m=representative_separation_m,
                volume_m3=volume_m3,
                relative_permittivity=permittivity.relative_permittivity,
                polarizability_si=polarizability_si,
            )
        )
        bridge_polarizability_si += polarizability_si
        maximum_contrast = max(
            maximum_contrast,
            abs(permittivity.relative_permittivity - medium_relative_permittivity)
            / medium_relative_permittivity,
        )

    if not np.isfinite(bridge_polarizability_si):
        raise QcmParameterError("QCM bridge polarizability is non-finite")
    return QcmBridge(
        position_m=bridge_position,
        axis=axis,
        polarizability_si=complex(bridge_polarizability_si),
        layers=tuple(layers),
        classical_limit=False,
        max_relative_permittivity_contrast=float(maximum_contrast),
    )
