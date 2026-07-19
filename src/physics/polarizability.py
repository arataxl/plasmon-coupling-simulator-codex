"""Au 球の完全 Mie 電気双極子係数に基づく FCDA 分極率。

本モジュールは時間依存を ``exp(-i omega t)`` とし、誘起双極子を
``p = alpha_SI E_local`` と定義する。したがって ``alpha_SI`` の SI 単位は
``C m^2 / V``（等価的に ``F m^2``）である。

FCDA には、均一・非吸収性媒質中の波数 ``k_m = 2 pi n_m / lambda_0`` と
完全 Mie 理論の電気双極子係数 ``a_1`` を用いる。

``alpha_FCDA = 6 pi i epsilon_0 epsilon_m a_1 / k_m^3``

ここで ``epsilon_m = n_m^2`` である。``a_1`` は有限サイズ球の厳密な係数

``a_1 = [m psi_1(m x) psi'_1(x) - psi_1(x) psi'_1(m x)]
       / [m psi_1(m x) xi'_1(x) - xi_1(x) psi'_1(m x)]``

（``m = n_p / n_m``, ``x = k_m a``）から評価する。従って小サイズ展開の
放射反作用 ``O(i x^3)`` と動的脱分極 ``O(x^2)`` は ``a_1`` に既に含まれ、
Clausius--Mossotti 分極率へ別途加算しない。

出典：Bohren & Huffman, *Absorption and Scattering of Light by Small
Particles* (1983), Chapter 4（Mie 係数と双極子極限）；Meier & Wokaun,
*Optics Letters* 8, 581--583 (1983), DOI: 10.1364/OL.8.000581
（動的脱分極・放射減衰）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.constants import c as SPEED_OF_LIGHT_M_PER_S
from scipy.constants import epsilon_0 as VACUUM_PERMITTIVITY_F_PER_M
from scipy.special import spherical_jn, spherical_yn

from src.physics.material_data import OpticalConstants


KREIBIG_SURFACE_SCATTERING_PARAMETER = 1.0
GOLD_FERMI_VELOCITY_M_PER_S = 1.4e6


@dataclass(frozen=True)
class KreibigParameters:
    """Kreibig 補正で明示入力する Drude パラメータ。

    ``plasma_frequency_rad_s`` と ``bulk_damping_rad_s`` は、承認済みの
    Johnson and Christy CSV には含まれない。そのため Au 固有の数値を本実装で
    仮定せず、補正を有効にする呼出し側が出典とともに指定する。

    補正は Kreibig & Vollmer, *Optical Properties of Metal Clusters*
    (1995) の ``gamma_R = gamma_bulk + A v_F / R`` に従う。プロジェクトで
    確定した ``A = 1.0`` と ``v_F = 1.4e6 m/s`` は上の定数で固定する。
    """

    plasma_frequency_rad_s: float
    bulk_damping_rad_s: float

    def __post_init__(self) -> None:
        for name, value in (
            ("plasma_frequency_rad_s", self.plasma_frequency_rad_s),
            ("bulk_damping_rad_s", self.bulk_damping_rad_s),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class FcdaPolarizability:
    """一波長・一球の FCDA 分極率と中間量（すべて SI）を保持する。"""

    wavelength_m: float
    wave_number_m_inv: float
    particle_permittivity: complex
    electric_dipole_mie_coefficient: complex
    polarizability_si: complex
    kreibig_correction_applied: bool


def _require_finite_positive(value: float, *, name: str) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _riccati_psi_one(argument: complex) -> complex:
    """一階 Riccati--Bessel 関数 ``psi_1(z)`` を返す。"""
    return complex(argument * spherical_jn(1, argument))


def _riccati_psi_one_derivative(argument: complex) -> complex:
    """``psi_1(z)`` の引数に関する微分を返す。"""
    return complex(
        spherical_jn(1, argument)
        + argument * spherical_jn(1, argument, derivative=True)
    )


def _outgoing_riccati_hankel_one(argument: complex) -> complex:
    """``exp(-i omega t)`` 規約の外向き ``xi_1(z)`` を返す。"""
    return complex(
        argument * spherical_jn(1, argument)
        + 1j * argument * spherical_yn(1, argument)
    )


def _outgoing_riccati_hankel_one_derivative(argument: complex) -> complex:
    """外向き ``xi_1(z)`` の引数に関する微分を返す。"""
    return complex(
        spherical_jn(1, argument)
        + argument * spherical_jn(1, argument, derivative=True)
        + 1j
        * (
            spherical_yn(1, argument)
            + argument * spherical_yn(1, argument, derivative=True)
        )
    )


def calculate_electric_dipole_mie_coefficient(
    *,
    relative_refractive_index: complex,
    size_parameter: float,
) -> complex:
    """完全 Mie 理論の電気双極子散乱係数 ``a_1`` を返す。

    ``relative_refractive_index`` は ``n_p / n_m``、``size_parameter`` は
    ``k_m a`` である。前者は既存材料データと同じ受動媒質表現 ``n + i k`` を
    用いる。Mie 係数の式と位相規約はモジュール docstring の Bohren & Huffman
    の記法に従う。
    """
    _require_finite_positive(size_parameter, name="size_parameter")
    if not (
        np.isfinite(relative_refractive_index.real)
        and np.isfinite(relative_refractive_index.imag)
    ):
        raise ValueError("relative_refractive_index must be finite")
    if relative_refractive_index == 0.0:
        raise ValueError("relative_refractive_index must not be zero")

    x = complex(size_parameter)
    mx = relative_refractive_index * x
    numerator = (
        relative_refractive_index
        * _riccati_psi_one(mx)
        * _riccati_psi_one_derivative(x)
        - _riccati_psi_one(x) * _riccati_psi_one_derivative(mx)
    )
    denominator = (
        relative_refractive_index
        * _riccati_psi_one(mx)
        * _outgoing_riccati_hankel_one_derivative(x)
        - _outgoing_riccati_hankel_one(x) * _riccati_psi_one_derivative(mx)
    )
    if not np.isfinite(denominator) or denominator == 0.0:
        raise FloatingPointError("electric-dipole Mie coefficient is singular")

    coefficient = numerator / denominator
    if not np.isfinite(coefficient):
        raise FloatingPointError("electric-dipole Mie coefficient is non-finite")
    return complex(coefficient)


def _drude_permittivity(
    *, angular_frequency_rad_s: float, parameters: KreibigParameters, damping_rad_s: float
) -> complex:
    """Kreibig の差分補正に使う Drude 成分だけを返す。"""
    denominator = angular_frequency_rad_s * (
        angular_frequency_rad_s + 1j * damping_rad_s
    )
    return complex(-(parameters.plasma_frequency_rad_s**2) / denominator)


def _apply_kreibig_size_correction(
    *,
    bulk_permittivity: complex,
    wavelength_m: float,
    radius_m: float,
    parameters: KreibigParameters,
) -> complex:
    """バルク誘電率の Drude 部分だけをサイズ依存減衰へ置換する。"""
    angular_frequency_rad_s = 2.0 * math.pi * SPEED_OF_LIGHT_M_PER_S / wavelength_m
    size_corrected_damping_rad_s = (
        parameters.bulk_damping_rad_s
        + KREIBIG_SURFACE_SCATTERING_PARAMETER
        * GOLD_FERMI_VELOCITY_M_PER_S
        / radius_m
    )
    bulk_drude = _drude_permittivity(
        angular_frequency_rad_s=angular_frequency_rad_s,
        parameters=parameters,
        damping_rad_s=parameters.bulk_damping_rad_s,
    )
    size_corrected_drude = _drude_permittivity(
        angular_frequency_rad_s=angular_frequency_rad_s,
        parameters=parameters,
        damping_rad_s=size_corrected_damping_rad_s,
    )
    return bulk_permittivity - bulk_drude + size_corrected_drude


def _passive_refractive_index_from_permittivity(permittivity: complex) -> complex:
    """``n + i k``（``n >= 0``, ``k >= 0``）となる平方根の枝を選ぶ。"""
    refractive_index = complex(np.sqrt(permittivity))
    if refractive_index.real < 0.0:
        refractive_index = -refractive_index
    if refractive_index.imag < 0.0:
        refractive_index = complex(
            refractive_index.real,
            -refractive_index.imag,
        )
    if not np.isfinite(refractive_index):
        raise FloatingPointError("Kreibig-corrected refractive index is non-finite")
    return refractive_index


def calculate_fcda_polarizability(
    *,
    wavelength_m: float,
    diameter_m: float,
    medium_refractive_index: float,
    optical_constants: OpticalConstants,
    apply_kreibig_correction: bool = False,
    kreibig_parameters: KreibigParameters | None = None,
) -> FcdaPolarizability:
    """Au 単一球の SI FCDA 分極率を計算する。

    ``wavelength_m`` と ``diameter_m`` は m、媒質屈折率は無次元の正実数で
    指定する。Johnson and Christy データは ``n + i k`` のまま読み、ここで採用
    する ``exp(-i omega t)`` 規約の ``a_1`` に直接渡す。Phase 1 の
    ``miepython`` 境界にある符号変換は、この独自の Mie 係数評価には適用しない。

    Kreibig 補正は既定で無効である。有効化時には文献に基づく
    ``KreibigParameters`` を明示指定し、
    ``epsilon = epsilon_bulk - epsilon_D(gamma_bulk) + epsilon_D(gamma_R)``
    として Drude 部分のみを置換する。Au の ``omega_p`` と ``gamma_bulk`` は
    本プロジェクトで未確定のため、暗黙の既定値を設けない。
    """
    wavelength_m = _require_finite_positive(wavelength_m, name="wavelength_m")
    diameter_m = _require_finite_positive(diameter_m, name="diameter_m")
    medium_refractive_index = _require_finite_positive(
        medium_refractive_index,
        name="medium_refractive_index",
    )
    if apply_kreibig_correction and kreibig_parameters is None:
        raise ValueError(
            "kreibig_parameters are required when apply_kreibig_correction is true"
        )

    bulk_refractive_index = complex(
        optical_constants.refractive_index_at_wavelength_m(wavelength_m)
    )
    particle_permittivity = bulk_refractive_index**2
    if apply_kreibig_correction:
        assert kreibig_parameters is not None
        particle_permittivity = _apply_kreibig_size_correction(
            bulk_permittivity=particle_permittivity,
            wavelength_m=wavelength_m,
            radius_m=diameter_m / 2.0,
            parameters=kreibig_parameters,
        )
        particle_refractive_index = _passive_refractive_index_from_permittivity(
            particle_permittivity
        )
    else:
        particle_refractive_index = bulk_refractive_index

    wave_number_m_inv = 2.0 * math.pi * medium_refractive_index / wavelength_m
    relative_refractive_index = particle_refractive_index / medium_refractive_index
    coefficient = calculate_electric_dipole_mie_coefficient(
        relative_refractive_index=relative_refractive_index,
        size_parameter=wave_number_m_inv * diameter_m / 2.0,
    )
    medium_relative_permittivity = medium_refractive_index**2
    polarizability_si = (
        6.0
        * math.pi
        * 1j
        * VACUUM_PERMITTIVITY_F_PER_M
        * medium_relative_permittivity
        * coefficient
        / wave_number_m_inv**3
    )
    if not np.isfinite(polarizability_si):
        raise FloatingPointError("FCDA polarizability is non-finite")

    return FcdaPolarizability(
        wavelength_m=wavelength_m,
        wave_number_m_inv=wave_number_m_inv,
        particle_permittivity=particle_permittivity,
        electric_dipole_mie_coefficient=coefficient,
        polarizability_si=complex(polarizability_si),
        kreibig_correction_applied=apply_kreibig_correction,
    )
