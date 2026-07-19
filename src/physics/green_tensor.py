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
