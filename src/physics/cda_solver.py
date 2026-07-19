"""Au 球集合体の FCDA を用いる結合双極子近似（CDA）ソルバー。

時間依存を ``exp(-i omega t)`` とし、各粒子の誘起双極子を
``p_i = alpha_i [E_inc(r_i) + sum_{j != i} A_ij p_j]`` とする。
``A_ij = k_m^2 G(r_i-r_j)/(epsilon_0 epsilon_m)`` であり、Green tensor は
``src.physics.green_tensor`` の遅延形を使う。入力座標と断面積は SI 単位系で
扱う。

散乱断面積は、遠方場の全立体角積分を ``Im G(r_i-r_j)`` により評価するため、
粒子間のコヒーレント干渉を含む。これは Draine & Flatau, *JOSA A* 11,
1491--1499 (1994), DOI: 10.1364/JOSAA.11.001491 の DDA 断面積の SI 表現に
対応する。
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import linalg
from scipy.constants import epsilon_0 as VACUUM_PERMITTIVITY_F_PER_M

from src.physics.green_tensor import (
    imaginary_part_of_green_tensor,
    retarded_dyadic_green_tensor,
)
from src.physics.material_data import OpticalConstants
from src.physics.polarizability import (
    FcdaPolarizability,
    KreibigParameters,
    calculate_fcda_polarizability,
)


MAX_PARTICLES = 20
MIN_SURFACE_GAP_M = 0.5e-9
QCM_REQUIRED_BELOW_GAP_M = 1.0e-9
CDA_WARNING_UP_TO_GAP_M = 5.0e-9
DEFAULT_MAX_CONDITION_NUMBER = 1.0e10

FloatArray = NDArray[np.float64]
ComplexArray = NDArray[np.complex128]


class CdaError(RuntimeError):
    """CDA 行列の構成または解法に関する基底例外。"""


class CdaConfigurationError(ValueError):
    """CDA の適用範囲外または不正な物理入力を示す。"""


class CdaQcmRequiredError(CdaConfigurationError):
    """0.5 nm 以上 1.0 nm 未満のため QCM が必要であることを示す。"""


class CdaIllConditionedMatrixError(CdaError):
    """CDA 相互作用行列が数値的に悪条件であることを示す。"""


class CdaLinearSolveError(CdaError):
    """CDA 相互作用行列が特異、または数値解が検証を満たさないことを示す。"""


@dataclass(frozen=True)
class CdaSolution:
    """一波長の CDA 解。双極子は ``C m``、電場は ``V/m`` で保持する。"""

    wavelength_m: float
    wave_number_m_inv: float
    medium_refractive_index: float
    positions_m: FloatArray
    diameters_m: FloatArray
    propagation_direction: FloatArray
    polarization: FloatArray
    incident_electric_fields_v_m: ComplexArray
    induced_dipoles_c_m: ComplexArray
    polarizabilities_si: ComplexArray
    condition_number: float
    relative_residual: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CdaCrossSections:
    """一波長の CDA 断面積（すべて m^2）を保持する。"""

    c_ext_m2: float
    c_sca_m2: float
    c_abs_m2: float


@dataclass(frozen=True)
class CdaSpectrum:
    """同一配置を複数波長で解いた CDA スペクトル（断面積は m^2）。"""

    wavelength_m: FloatArray
    c_ext_m2: FloatArray
    c_sca_m2: FloatArray
    c_abs_m2: FloatArray
    condition_numbers: FloatArray
    warnings: tuple[str, ...]


def _require_finite_positive(value: float, *, name: str) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise CdaConfigurationError(f"{name} must be finite and positive")
    return value


def _as_positions(positions_m: ArrayLike) -> FloatArray:
    positions = np.asarray(positions_m, dtype=np.float64)
    if positions.ndim != 2 or positions.shape[1:] != (3,):
        raise CdaConfigurationError("positions_m must have shape (particle_count, 3)")
    if positions.shape[0] == 0 or positions.shape[0] > MAX_PARTICLES:
        raise CdaConfigurationError(
            f"particle count must be between 1 and {MAX_PARTICLES}"
        )
    if not np.all(np.isfinite(positions)):
        raise CdaConfigurationError("positions_m must contain only finite values")
    return positions


def _as_diameters(diameters_m: ArrayLike, *, particle_count: int) -> FloatArray:
    diameters = np.asarray(diameters_m, dtype=np.float64)
    if diameters.shape != (particle_count,):
        raise CdaConfigurationError(
            "diameters_m must be one-dimensional and match positions_m"
        )
    if not np.all(np.isfinite(diameters)) or np.any(diameters <= 0.0):
        raise CdaConfigurationError("diameters_m must contain finite positive values")
    return diameters


def _normalized_vector(values: ArrayLike, *, name: str) -> FloatArray:
    vector = np.asarray(values, dtype=np.float64)
    if vector.shape != (3,):
        raise CdaConfigurationError(f"{name} must have shape (3,)")
    if not np.all(np.isfinite(vector)):
        raise CdaConfigurationError(f"{name} must contain only finite values")
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise CdaConfigurationError(f"{name} must not be the zero vector")
    return vector / norm


def _gap_tolerance_m(center_distance_m: float, diameters_m: FloatArray) -> float:
    scale_m = max(center_distance_m, float(np.max(diameters_m)), 1.0e-12)
    return 32.0 * np.finfo(np.float64).eps * scale_m


def _validate_surface_gaps(
    *, positions_m: FloatArray, diameters_m: FloatArray
) -> tuple[str, ...]:
    """重なり・QCM領域を拒否し、1--5 nm の CDA 警告を返す。"""
    minimum_warning_gap_m: float | None = None
    for left_index in range(len(positions_m)):
        for right_index in range(left_index + 1, len(positions_m)):
            center_distance_m = float(
                np.linalg.norm(positions_m[left_index] - positions_m[right_index])
            )
            surface_gap_m = center_distance_m - (
                diameters_m[left_index] + diameters_m[right_index]
            ) / 2.0
            tolerance_m = _gap_tolerance_m(center_distance_m, diameters_m)
            if surface_gap_m < -tolerance_m:
                raise CdaConfigurationError(
                    f"particles {left_index} and {right_index} overlap"
                )
            if surface_gap_m < MIN_SURFACE_GAP_M - tolerance_m:
                raise CdaConfigurationError(
                    f"surface gap between particles {left_index} and {right_index} "
                    "is below the 0.5 nm model limit"
                )
            if surface_gap_m < QCM_REQUIRED_BELOW_GAP_M - tolerance_m:
                raise CdaQcmRequiredError(
                    f"surface gap between particles {left_index} and {right_index} "
                    "requires QCM; QCM is not part of the Phase 2 solver"
                )
            if surface_gap_m <= CDA_WARNING_UP_TO_GAP_M + tolerance_m:
                if (
                    minimum_warning_gap_m is None
                    or surface_gap_m < minimum_warning_gap_m
                ):
                    minimum_warning_gap_m = surface_gap_m

    if minimum_warning_gap_m is None:
        return ()
    return (
        "CDA approximation warning: at least one surface gap is within the "
        "1--5 nm warning range "
        f"(minimum {minimum_warning_gap_m / 1e-9:.6g} nm).",
    )


def _incident_electric_fields(
    *,
    positions_m: FloatArray,
    wave_number_m_inv: float,
    propagation_direction: FloatArray,
    polarization: FloatArray,
    incident_field_amplitude_v_m: float,
) -> ComplexArray:
    phases = np.exp(1j * wave_number_m_inv * (positions_m @ propagation_direction))
    field_vector = incident_field_amplitude_v_m * polarization
    return np.asarray(phases[:, np.newaxis] * field_vector[np.newaxis, :], dtype=np.complex128)


def _build_interaction_matrix(
    *,
    positions_m: FloatArray,
    polarizabilities_si: ComplexArray,
    wave_number_m_inv: float,
    medium_relative_permittivity: float,
) -> ComplexArray:
    particle_count = len(positions_m)
    matrix = np.eye(3 * particle_count, dtype=np.complex128)
    interaction_scale = wave_number_m_inv**2 / (
        VACUUM_PERMITTIVITY_F_PER_M * medium_relative_permittivity
    )
    for target_index in range(particle_count):
        target_slice = slice(3 * target_index, 3 * target_index + 3)
        for source_index in range(particle_count):
            if target_index == source_index:
                continue
            source_slice = slice(3 * source_index, 3 * source_index + 3)
            green_tensor = retarded_dyadic_green_tensor(
                relative_position_m=positions_m[target_index] - positions_m[source_index],
                wave_number_m_inv=wave_number_m_inv,
            )
            matrix[target_slice, source_slice] = (
                -polarizabilities_si[target_index] * interaction_scale * green_tensor
            )
    return matrix


def solve_cda(
    *,
    positions_m: ArrayLike,
    diameters_m: ArrayLike,
    wavelength_m: float,
    medium_refractive_index: float,
    propagation_direction: ArrayLike,
    polarization: ArrayLike,
    optical_constants: OpticalConstants,
    incident_field_amplitude_v_m: float = 1.0,
    apply_kreibig_correction: bool = False,
    kreibig_parameters: KreibigParameters | None = None,
    max_condition_number: float = DEFAULT_MAX_CONDITION_NUMBER,
) -> CdaSolution:
    """一波長の FCDA-CDA 連立方程式を解く。

    最大20粒子、すなわち最大60複素自由度を対象に ``scipy.linalg.solve`` を
    用いる。行列の2ノルム条件数が ``max_condition_number`` を超える、特異、
    または残差が丸め誤差の見積りを超える場合は、非物理的な結果を返さず例外にする。
    """
    wavelength_m = _require_finite_positive(wavelength_m, name="wavelength_m")
    medium_refractive_index = _require_finite_positive(
        medium_refractive_index,
        name="medium_refractive_index",
    )
    incident_field_amplitude_v_m = _require_finite_positive(
        incident_field_amplitude_v_m,
        name="incident_field_amplitude_v_m",
    )
    max_condition_number = _require_finite_positive(
        max_condition_number,
        name="max_condition_number",
    )
    positions = _as_positions(positions_m)
    diameters = _as_diameters(diameters_m, particle_count=len(positions))
    geometry_warnings = _validate_surface_gaps(
        positions_m=positions,
        diameters_m=diameters,
    )
    normalized_propagation_direction = _normalized_vector(
        propagation_direction,
        name="propagation_direction",
    )
    normalized_polarization = _normalized_vector(polarization, name="polarization")
    if not math.isclose(
        float(np.dot(normalized_propagation_direction, normalized_polarization)),
        0.0,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise CdaConfigurationError(
            "polarization must be perpendicular to propagation_direction"
        )

    polarizability_results: list[FcdaPolarizability] = []
    for diameter_m in diameters:
        polarizability_results.append(
            calculate_fcda_polarizability(
                wavelength_m=wavelength_m,
                diameter_m=float(diameter_m),
                medium_refractive_index=medium_refractive_index,
                optical_constants=optical_constants,
                apply_kreibig_correction=apply_kreibig_correction,
                kreibig_parameters=kreibig_parameters,
            )
        )
    polarizabilities_si = np.asarray(
        [result.polarizability_si for result in polarizability_results],
        dtype=np.complex128,
    )
    wave_number_m_inv = polarizability_results[0].wave_number_m_inv
    medium_relative_permittivity = medium_refractive_index**2
    incident_fields = _incident_electric_fields(
        positions_m=positions,
        wave_number_m_inv=wave_number_m_inv,
        propagation_direction=normalized_propagation_direction,
        polarization=normalized_polarization,
        incident_field_amplitude_v_m=incident_field_amplitude_v_m,
    )
    interaction_matrix = _build_interaction_matrix(
        positions_m=positions,
        polarizabilities_si=polarizabilities_si,
        wave_number_m_inv=wave_number_m_inv,
        medium_relative_permittivity=medium_relative_permittivity,
    )
    condition_number = float(np.linalg.cond(interaction_matrix))
    if not math.isfinite(condition_number) or condition_number > max_condition_number:
        raise CdaIllConditionedMatrixError(
            "CDA interaction matrix is singular or ill-conditioned "
            f"(condition number {condition_number:.6g}, limit {max_condition_number:.6g})"
        )

    right_hand_side = (polarizabilities_si[:, np.newaxis] * incident_fields).reshape(-1)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", linalg.LinAlgWarning)
            flat_dipoles = linalg.solve(
                interaction_matrix,
                right_hand_side,
                assume_a="gen",
                check_finite=True,
            )
    except (linalg.LinAlgError, linalg.LinAlgWarning) as error:
        raise CdaLinearSolveError("CDA interaction matrix could not be solved") from error

    relative_residual = float(
        np.linalg.norm(interaction_matrix @ flat_dipoles - right_hand_side)
        / max(np.linalg.norm(right_hand_side), np.finfo(np.float64).tiny)
    )
    residual_limit = max(
        1.0e-10,
        100.0 * np.finfo(np.float64).eps * condition_number,
    )
    if not math.isfinite(relative_residual) or relative_residual > residual_limit:
        raise CdaLinearSolveError(
            "CDA linear-system residual exceeds the numerical tolerance "
            f"({relative_residual:.6g} > {residual_limit:.6g})"
        )

    induced_dipoles = np.asarray(
        flat_dipoles.reshape((len(positions), 3)),
        dtype=np.complex128,
    )
    if not np.all(np.isfinite(induced_dipoles)):
        raise CdaLinearSolveError("CDA induced dipoles are non-finite")

    return CdaSolution(
        wavelength_m=wavelength_m,
        wave_number_m_inv=wave_number_m_inv,
        medium_refractive_index=medium_refractive_index,
        positions_m=positions,
        diameters_m=diameters,
        propagation_direction=normalized_propagation_direction,
        polarization=normalized_polarization,
        incident_electric_fields_v_m=incident_fields,
        induced_dipoles_c_m=induced_dipoles,
        polarizabilities_si=polarizabilities_si,
        condition_number=condition_number,
        relative_residual=relative_residual,
        warnings=geometry_warnings,
    )


def phase_correct_induced_dipoles(solution: CdaSolution) -> ComplexArray:
    """入射平面波の位置位相を除いた誘起双極子を返す。

    ``E_inc(r) = E_0 exp(i k_m khat dot r)`` を使用しているため、各双極子へ
    ``exp(-i k_m khat dot r_i)`` を掛ける。孤立極限と剛体並進の比較ではこの量を
    用いる。
    """
    phase_correction = np.exp(
        -1j
        * solution.wave_number_m_inv
        * (solution.positions_m @ solution.propagation_direction)
    )
    return np.asarray(
        solution.induced_dipoles_c_m * phase_correction[:, np.newaxis],
        dtype=np.complex128,
    )


def calculate_cda_cross_sections(solution: CdaSolution) -> CdaCrossSections:
    """誘起双極子から ``C_ext``、``C_sca``、``C_abs``（m^2）を求める。

    ``C_ext`` は光学定理の双極子表式、``C_sca`` は遅延 Green tensor の虚部を
    用いた全立体角積分である。吸収はエネルギー保存を明示する
    ``C_abs = C_ext - C_sca`` として返す。
    """
    medium_relative_permittivity = solution.medium_refractive_index**2
    incident_amplitude_squared = float(
        np.vdot(
            solution.incident_electric_fields_v_m[0],
            solution.incident_electric_fields_v_m[0],
        ).real
    )
    if incident_amplitude_squared <= 0.0:
        raise CdaLinearSolveError("incident electric-field amplitude is invalid")

    extinction_overlap = np.vdot(
        solution.incident_electric_fields_v_m,
        solution.induced_dipoles_c_m,
    )
    c_ext_m2 = (
        solution.wave_number_m_inv
        * float(np.imag(extinction_overlap))
        / (
            VACUUM_PERMITTIVITY_F_PER_M
            * medium_relative_permittivity
            * incident_amplitude_squared
        )
    )

    scattering_overlap = 0.0j
    for target_index, target_dipole in enumerate(solution.induced_dipoles_c_m):
        for source_index, source_dipole in enumerate(solution.induced_dipoles_c_m):
            imaginary_green = imaginary_part_of_green_tensor(
                relative_position_m=(
                    solution.positions_m[target_index]
                    - solution.positions_m[source_index]
                ),
                wave_number_m_inv=solution.wave_number_m_inv,
            )
            scattering_overlap += np.vdot(target_dipole, imaginary_green @ source_dipole)
    c_sca_m2 = (
        solution.wave_number_m_inv**3
        * float(np.real(scattering_overlap))
        / (
            VACUUM_PERMITTIVITY_F_PER_M**2
            * medium_relative_permittivity**2
            * incident_amplitude_squared
        )
    )
    c_abs_m2 = c_ext_m2 - c_sca_m2

    cross_sections = (c_ext_m2, c_sca_m2, c_abs_m2)
    if not all(math.isfinite(value) for value in cross_sections):
        raise CdaLinearSolveError("CDA cross section is non-finite")
    scale = max(max(abs(value) for value in cross_sections), 1.0e-300)
    rounding_tolerance = 1_000.0 * np.finfo(np.float64).eps * scale
    if c_ext_m2 < -rounding_tolerance or c_sca_m2 < -rounding_tolerance:
        raise CdaLinearSolveError("CDA produced a negative extinction or scattering cross section")
    if c_abs_m2 < -rounding_tolerance:
        raise CdaLinearSolveError("CDA produced a negative absorption cross section")

    return CdaCrossSections(
        c_ext_m2=c_ext_m2,
        c_sca_m2=c_sca_m2,
        c_abs_m2=c_abs_m2,
    )


def calculate_cda_spectrum(
    *,
    wavelengths_m: ArrayLike,
    positions_m: ArrayLike,
    diameters_m: ArrayLike,
    medium_refractive_index: float,
    propagation_direction: ArrayLike,
    polarization: ArrayLike,
    optical_constants: OpticalConstants,
    incident_field_amplitude_v_m: float = 1.0,
    apply_kreibig_correction: bool = False,
    kreibig_parameters: KreibigParameters | None = None,
    max_condition_number: float = DEFAULT_MAX_CONDITION_NUMBER,
) -> CdaSpectrum:
    """同じ粒子配置について、複数真空波長の CDA スペクトルを計算する。"""
    wavelengths = np.asarray(wavelengths_m, dtype=np.float64)
    if wavelengths.ndim != 1 or wavelengths.size == 0:
        raise CdaConfigurationError("wavelengths_m must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(wavelengths)) or np.any(wavelengths <= 0.0):
        raise CdaConfigurationError("wavelengths_m must contain finite positive values")

    c_ext_m2 = np.empty_like(wavelengths)
    c_sca_m2 = np.empty_like(wavelengths)
    c_abs_m2 = np.empty_like(wavelengths)
    condition_numbers = np.empty_like(wavelengths)
    geometry_warnings: tuple[str, ...] | None = None
    for index, wavelength_m in enumerate(wavelengths):
        solution = solve_cda(
            positions_m=positions_m,
            diameters_m=diameters_m,
            wavelength_m=float(wavelength_m),
            medium_refractive_index=medium_refractive_index,
            propagation_direction=propagation_direction,
            polarization=polarization,
            optical_constants=optical_constants,
            incident_field_amplitude_v_m=incident_field_amplitude_v_m,
            apply_kreibig_correction=apply_kreibig_correction,
            kreibig_parameters=kreibig_parameters,
            max_condition_number=max_condition_number,
        )
        cross_sections = calculate_cda_cross_sections(solution)
        c_ext_m2[index] = cross_sections.c_ext_m2
        c_sca_m2[index] = cross_sections.c_sca_m2
        c_abs_m2[index] = cross_sections.c_abs_m2
        condition_numbers[index] = solution.condition_number
        if geometry_warnings is None:
            geometry_warnings = solution.warnings

    return CdaSpectrum(
        wavelength_m=wavelengths,
        c_ext_m2=c_ext_m2,
        c_sca_m2=c_sca_m2,
        c_abs_m2=c_abs_m2,
        condition_numbers=condition_numbers,
        warnings=geometry_warnings or (),
    )
