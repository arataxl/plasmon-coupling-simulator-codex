"""均一・非吸収性媒質中の遅延 dyadic Green tensor。

時間依存は ``exp(-i omega t)`` とする。観測点 ``r_i`` と双極子源 ``r_j`` の
相対位置 ``R = r_i - r_j``（m）、媒質波数 ``k_m``（m^-1）に対して、

``G(R) = exp(i k_m R) / (4 pi R) * [
    (1 + i/(k_m R) - 1/(k_m R)^2) I
    + (-1 - 3 i/(k_m R) + 3/(k_m R)^2) Rhat Rhat
]``

を返す。電場への変換は ``E(R) = k_m^2 G(R) p / (epsilon_0 epsilon_m)``
であり、テンソル自体の単位は m^-1 である。自己項の実部は発散するためここでは
扱わず、散乱断面積に必要な有限の極限 ``Im G(0) = k_m I / (6 pi)`` だけを
別関数で返す。

出典：Draine & Flatau, "Discrete-dipole approximation for scattering
calculations," *JOSA A* 11, 1491--1499 (1994),
DOI: 10.1364/JOSAA.11.001491。式は同論文で用いる遅延双極子相互作用と
等価な自由空間 Green dyadic ``(I + nabla nabla / k^2) exp(i k R)/(4 pi R)``
の展開形である。
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray


RealMatrix = NDArray[np.float64]
ComplexMatrix = NDArray[np.complex128]
ComplexRankThree = NDArray[np.complex128]


def _validate_wave_number(wave_number_m_inv: float) -> float:
    if not math.isfinite(wave_number_m_inv) or wave_number_m_inv <= 0.0:
        raise ValueError("wave_number_m_inv must be finite and positive")
    return wave_number_m_inv


def _as_relative_position(relative_position_m: ArrayLike) -> NDArray[np.float64]:
    position = np.asarray(relative_position_m, dtype=np.float64)
    if position.shape != (3,):
        raise ValueError("relative_position_m must have shape (3,)")
    if not np.all(np.isfinite(position)):
        raise ValueError("relative_position_m must contain only finite values")
    return position


def retarded_dyadic_green_tensor(
    *,
    relative_position_m: ArrayLike,
    wave_number_m_inv: float,
) -> ComplexMatrix:
    """自己項を除く遅延 dyadic Green tensor を SI 座標から計算する。

    ``relative_position_m`` は必ず観測粒子中心からではなく、
    ``観測点 - 源点``、すなわち ``r_i - r_j`` とする。零ベクトルでは自己項が
    特異になるため ``ValueError`` を返す。
    """
    wave_number_m_inv = _validate_wave_number(wave_number_m_inv)
    relative_position = _as_relative_position(relative_position_m)
    distance_m = float(np.linalg.norm(relative_position))
    if distance_m == 0.0:
        raise ValueError("retarded Green tensor is singular at zero separation")

    unit_vector = relative_position / distance_m
    unit_dyadic = np.outer(unit_vector, unit_vector)
    kr = wave_number_m_inv * distance_m
    inverse_kr = 1.0 / kr
    transverse_coefficient = 1.0 + 1j * inverse_kr - inverse_kr**2
    longitudinal_coefficient = -1.0 - 3j * inverse_kr + 3.0 * inverse_kr**2
    tensor = np.exp(1j * kr) / (4.0 * math.pi * distance_m) * (
        transverse_coefficient * np.eye(3)
        + longitudinal_coefficient * unit_dyadic
    )
    if not np.all(np.isfinite(tensor)):
        raise FloatingPointError("retarded Green tensor is non-finite")
    return np.asarray(tensor, dtype=np.complex128)


def retarded_electric_quadrupole_green_tensor(
    *,
    relative_position_m: ArrayLike,
    wave_number_m_inv: float,
) -> ComplexMatrix:
    """Return the electric-quadrupole-to-electric-field Green tensor.

    ``relative_position_m`` is the target-minus-source centre vector
    ``R = r_target - r_source`` in metres.  The returned tensor has units
    ``m^-2`` and maps the source quadrupole contraction ``Q @ Rhat`` to its
    field contribution through

    ``E_Q = k_m^2 G_Q(R) (Q @ Rhat) / (epsilon_0 epsilon_m)``.

    The expression is Eq. (7) of Evlyukhin et al., *Physical Review B* 85,
    245411 (2012), DOI: 10.1103/PhysRevB.85.245411.  It shares the
    ``exp(-i omega t)`` convention and the host-medium wavenumber ``k_m`` of
    :func:`retarded_dyadic_green_tensor`.
    """
    wave_number_m_inv = _validate_wave_number(wave_number_m_inv)
    relative_position = _as_relative_position(relative_position_m)
    distance_m = float(np.linalg.norm(relative_position))
    if distance_m == 0.0:
        raise ValueError("retarded quadrupole Green tensor is singular at zero separation")

    unit_vector = relative_position / distance_m
    unit_dyadic = np.outer(unit_vector, unit_vector)
    kr = wave_number_m_inv * distance_m
    inverse_kr = 1.0 / kr
    isotropic_coefficient = (
        -1.0
        - 3j * inverse_kr
        + 6.0 * inverse_kr**2
        + 6j * inverse_kr**3
    )
    longitudinal_coefficient = (
        1.0
        + 6j * inverse_kr
        - 15.0 * inverse_kr**2
        - 15j * inverse_kr**3
    )
    tensor = (
        1j
        * wave_number_m_inv
        * np.exp(1j * kr)
        / (24.0 * math.pi * distance_m)
        * (isotropic_coefficient * np.eye(3) + longitudinal_coefficient * unit_dyadic)
    )
    if not np.all(np.isfinite(tensor)):
        raise FloatingPointError("retarded quadrupole Green tensor is non-finite")
    return np.asarray(tensor, dtype=np.complex128)


def gradient_of_retarded_dyadic_green_tensor(
    *,
    relative_position_m: ArrayLike,
    wave_number_m_inv: float,
) -> ComplexRankThree:
    """Return ``dG[a, b, c] = partial_a G[b, c]`` in the target coordinates.

    ``relative_position_m`` is ``r_target - r_source`` in metres, and the
    returned tensor has units ``m^-2``.  This is the analytic spatial
    derivative of Eq. (6) of Evlyukhin et al., *Physical Review B* 85,
    245411 (2012), DOI: 10.1103/PhysRevB.85.245411; it is used in their
    Eq. (2) for the electric-dipole-to-electric-quadrupole interaction.  No
    finite-difference step is introduced.
    """
    wave_number_m_inv = _validate_wave_number(wave_number_m_inv)
    relative_position = _as_relative_position(relative_position_m)
    distance_m = float(np.linalg.norm(relative_position))
    if distance_m == 0.0:
        raise ValueError("retarded Green-tensor gradient is singular at zero separation")

    unit_vector = relative_position / distance_m
    kr = wave_number_m_inv * distance_m
    inverse_kr = 1.0 / kr
    transverse_coefficient = 1.0 + 1j * inverse_kr - inverse_kr**2
    longitudinal_coefficient = -1.0 - 3j * inverse_kr + 3.0 * inverse_kr**2
    radial_prefactor = np.exp(1j * kr) / (4.0 * math.pi * distance_m)
    radial_prefactor_derivative = radial_prefactor * (
        1j * wave_number_m_inv - 1.0 / distance_m
    )
    transverse_derivative = wave_number_m_inv * (
        -1j * inverse_kr**2 + 2.0 * inverse_kr**3
    )
    longitudinal_derivative = wave_number_m_inv * (
        3j * inverse_kr**2 - 6.0 * inverse_kr**3
    )
    isotropic_radial_derivative = (
        radial_prefactor_derivative * transverse_coefficient
        + radial_prefactor * transverse_derivative
    )
    longitudinal_radial_derivative = (
        radial_prefactor_derivative * longitudinal_coefficient
        + radial_prefactor * longitudinal_derivative
    )
    identity = np.eye(3)
    gradient = np.empty((3, 3, 3), dtype=np.complex128)
    for coordinate_index in range(3):
        radial_direction = unit_vector[coordinate_index]
        unit_dyadic_derivative = (
            np.outer(identity[coordinate_index], unit_vector)
            + np.outer(unit_vector, identity[coordinate_index])
            - 2.0 * radial_direction * np.outer(unit_vector, unit_vector)
        ) / distance_m
        gradient[coordinate_index] = (
            isotropic_radial_derivative * radial_direction * identity
            + longitudinal_radial_derivative
            * radial_direction
            * np.outer(unit_vector, unit_vector)
            + radial_prefactor * longitudinal_coefficient * unit_dyadic_derivative
        )
    if not np.all(np.isfinite(gradient)):
        raise FloatingPointError("retarded Green-tensor gradient is non-finite")
    return gradient


def imaginary_part_of_green_tensor(
    *,
    relative_position_m: ArrayLike,
    wave_number_m_inv: float,
) -> RealMatrix:
    """散乱断面積用の ``Im G(r_i - r_j)`` を返す。

    零分離では有限の自己項極限 ``k_m I / (6 pi)`` を返す。非零分離では
    ``retarded_dyadic_green_tensor`` の虚部を使う。
    """
    wave_number_m_inv = _validate_wave_number(wave_number_m_inv)
    relative_position = _as_relative_position(relative_position_m)
    if float(np.linalg.norm(relative_position)) == 0.0:
        return np.eye(3, dtype=np.float64) * wave_number_m_inv / (6.0 * math.pi)
    return np.asarray(
        np.imag(
            retarded_dyadic_green_tensor(
                relative_position_m=relative_position,
                wave_number_m_inv=wave_number_m_inv,
            )
        ),
        dtype=np.float64,
    )
