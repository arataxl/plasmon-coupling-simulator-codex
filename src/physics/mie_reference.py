"""完全Mie理論による単一Au球の参照計算。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

import miepython
import numpy as np
from numpy.typing import ArrayLike, NDArray

from src.physics.material_data import OpticalConstants


FloatArray: TypeAlias = NDArray[np.float64]
EXACT_MIE_MIN_DIAMETER_M = 2.0e-9
EXACT_MIE_MAX_DIAMETER_M = 500.0e-9


@dataclass(frozen=True)
class MieSpectrum:
    """SI単位で保持する単一球Mieスペクトル。"""

    wavelength_m: FloatArray
    c_ext_m2: FloatArray
    c_sca_m2: FloatArray
    c_abs_m2: FloatArray
    q_ext: FloatArray
    q_sca: FloatArray
    q_abs: FloatArray


def _as_one_dimensional_finite_array(
    values: ArrayLike, *, name: str
) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array


def _mie_efficiencies(
    material_refractive_index: complex,
    diameter_m: float,
    wavelength_m: float,
    medium_refractive_index: float,
) -> tuple[float, float]:
    """miepython 2.xのAPIを優先し、開発環境の3.x互換も保つ。

    Johnson and Christy CSVはプロジェクトの約束どおり ``n + i k`` で保持する。
    miepython 2.xは吸収媒質に負の虚部を使うため、外部ライブラリ呼出し時だけ共役を渡す。
    """
    refractive_index = complex(
        material_refractive_index.real,
        -material_refractive_index.imag,
    )
    if hasattr(miepython, "ez_mie"):
        q_ext, q_sca, _, _ = miepython.ez_mie(
            refractive_index,
            diameter_m,
            wavelength_m,
            n_env=medium_refractive_index,
        )
    elif hasattr(miepython, "efficiencies"):
        q_ext, q_sca, _, _ = miepython.efficiencies(
            refractive_index,
            diameter_m,
            wavelength_m,
            n_env=medium_refractive_index,
        )
    else:
        raise RuntimeError("installed miepython does not expose a supported efficiency API")
    return float(q_ext), float(q_sca)


def calculate_single_sphere_spectrum(
    *,
    wavelengths_m: ArrayLike,
    diameter_m: float,
    medium_refractive_index: float,
    optical_constants: OpticalConstants,
) -> MieSpectrum:
    """Au球のMie断面積と効率を計算する。

    Parameters are in SI units except for the dimensionless medium refractive index.
    The material-data layer converts the wavelength only while reading the nm-based CSV.
    """
    wavelength_array_m = _as_one_dimensional_finite_array(
        wavelengths_m, name="wavelengths_m"
    )
    if np.any(wavelength_array_m <= 0):
        raise ValueError("wavelengths_m must be positive")
    if not np.isfinite(diameter_m) or diameter_m <= 0:
        raise ValueError("diameter_m must be finite and positive")
    if not np.isfinite(medium_refractive_index) or medium_refractive_index <= 0:
        raise ValueError("medium_refractive_index must be finite and positive")

    refractive_indices = np.asarray(
        optical_constants.refractive_index_at_wavelength_m(wavelength_array_m),
        dtype=np.complex128,
    )
    q_ext = np.empty_like(wavelength_array_m)
    q_sca = np.empty_like(wavelength_array_m)
    for index, (wavelength_m, refractive_index) in enumerate(
        zip(wavelength_array_m, refractive_indices, strict=True)
    ):
        q_ext[index], q_sca[index] = _mie_efficiencies(
            complex(refractive_index),
            diameter_m,
            float(wavelength_m),
            medium_refractive_index,
        )

    q_abs = q_ext - q_sca
    geometric_cross_section_m2 = np.pi * (diameter_m / 2.0) ** 2
    c_ext_m2 = q_ext * geometric_cross_section_m2
    c_sca_m2 = q_sca * geometric_cross_section_m2
    c_abs_m2 = c_ext_m2 - c_sca_m2

    return MieSpectrum(
        wavelength_m=wavelength_array_m,
        c_ext_m2=c_ext_m2,
        c_sca_m2=c_sca_m2,
        c_abs_m2=c_abs_m2,
        q_ext=q_ext,
        q_sca=q_sca,
        q_abs=q_abs,
    )


def calculate_exact_single_sphere_mie_spectrum(
    *,
    wavelengths_m: ArrayLike,
    diameter_m: float,
    medium_refractive_index: float,
    optical_constants: OpticalConstants,
) -> MieSpectrum:
    """2--500 nmの単一Au球について全次数Mie解を返す。

    ``miepython`` の球Mie解は、電気係数 ``a_l`` と磁気係数 ``b_l`` を
    収束打切り次数まで和する。したがって本関数はFCDAの ``a_1`` のみを使う
    多粒子CDAとは別の、単一・均一球に対する完全Mie参照解である。

    出典：Bohren and Huffman, *Absorption and Scattering of Light by Small
    Particles*, Ch. 4。波長と直径はSI単位系（m）で受け取る。
    """
    # nmからSIへ変換した500 nmは、IEEE 754の丸めで上限の1 ULP外側に
    # なることがある。nextafterで単位変換由来の丸めだけを許容し、
    # 物理的な2--500 nm範囲自体は広げない。
    minimum_diameter_m = np.nextafter(EXACT_MIE_MIN_DIAMETER_M, -np.inf)
    maximum_diameter_m = np.nextafter(EXACT_MIE_MAX_DIAMETER_M, np.inf)
    if not np.isfinite(diameter_m) or not (
        minimum_diameter_m <= diameter_m <= maximum_diameter_m
    ):
        raise ValueError(
            "exact single-sphere Mie mode requires "
            "2 nm <= diameter_m <= 500 nm"
        )
    return calculate_single_sphere_spectrum(
        wavelengths_m=wavelengths_m,
        diameter_m=diameter_m,
        medium_refractive_index=medium_refractive_index,
        optical_constants=optical_constants,
    )
