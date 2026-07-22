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

表面間ギャップが0.5--1 nmの粒子対では、Esteban et al. (2012)のQCM局所誘電率を
4層の環状ギャップ体積へ離散化し、その和を補助双極子として同じ連立方程式へ加える。
これは原論文のBEM/FEMシェル解法を単一双極子CDAへ縮約したMVP近似であり、詳細な
式と限界は ``docs/quantum_corrected_model_integration.md`` を正とする。
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import linalg
from scipy.constants import c as SPEED_OF_LIGHT_M_PER_S
from scipy.constants import epsilon_0 as VACUUM_PERMITTIVITY_F_PER_M

from src.physics.green_tensor import (
    gradient_of_retarded_dyadic_green_tensor,
    imaginary_part_of_green_tensor,
    retarded_electric_quadrupole_green_tensor,
    retarded_dyadic_green_tensor,
)
from src.physics.material_data import OpticalConstants
from src.physics.polarizability import (
    ElectricQuadrupolePolarizability,
    FcdaPolarizability,
    KreibigParameters,
    calculate_electric_quadrupole_polarizability,
    calculate_fcda_polarizability,
)
from src.physics.qcm import (
    AU_JELLIUM_QCM_BULK_DAMPING_ENERGY_EV,
    AU_JELLIUM_QCM_PLASMA_ENERGY_EV,
    DEFAULT_QCM_LAYER_COUNT,
    GammaGParameterTable,
    QcmBridge,
    QcmParameterError,
    build_qcm_bridge_for_sphere_pair,
)


MAX_PARTICLES = 50
MAX_QCM_PARTICLES = 20
MIN_SURFACE_GAP_M = 0.5e-9
QCM_REQUIRED_BELOW_GAP_M = 1.0e-9
CDA_WARNING_UP_TO_GAP_M = 5.0e-9
DEFAULT_MAX_CONDITION_NUMBER = 1.0e10

WARNING_CDA_GAP_LIMITATION = "cda_gap_limitation"
WARNING_QCM_APPLIED = "qcm_applied"
WARNING_QCM_CLASSICAL_LIMIT = "qcm_classical_limit"
WARNING_QCM_VALIDATION_OVERRIDE = "qcm_validation_override"
WARNING_EXPERIMENTAL_QUADRUPOLE_COUPLING = "experimental_quadrupole_coupling"

_ELECTRIC_QUADRUPOLE_COMPONENT_COUNT = 5
_EXPERIMENTAL_QUADRUPOLE_SCATTERING_POLAR_ORDER = 24
_EXPERIMENTAL_QUADRUPOLE_SCATTERING_AZIMUTHAL_ORDER = 48

FloatArray = NDArray[np.float64]
ComplexArray = NDArray[np.complex128]


@dataclass(frozen=True)
class CdaWarning:
    """UI/APIで翻訳するための、CDA計算層の構造化された注意情報。

    ``code`` は表示文言ではなく安定した機械可読識別子であり、
    ``parameters`` には表示に必要な数値だけを SI 境界外の単位で格納する。
    物理計算層は自然言語の表示責務を持たず、API/UI 層で現在の表示言語へ
    変換する。
    """

    code: str
    parameters: dict[str, float | int] = field(default_factory=dict)


class CdaError(RuntimeError):
    """CDA 行列の構成または解法に関する基底例外。"""


class CdaConfigurationError(ValueError):
    """CDA の適用範囲外または不正な物理入力を示す。"""


class CdaQcmRequiredError(CdaConfigurationError):
    """後方互換用の例外。Phase 3以降の ``solve_cda`` は送出しない。"""


class CdaQcmParameterTableRequiredError(CdaConfigurationError):
    """QCM必須ギャップなのに、版管理済み表が呼出し側から渡されない。"""


class CdaIllConditionedMatrixError(CdaError):
    """CDA 相互作用行列が数値的に悪条件であることを示す。"""


class CdaLinearSolveError(CdaError):
    """CDA 相互作用行列が特異、または数値解が検証を満たさないことを示す。"""


@dataclass(frozen=True)
class _QcmPairGeometry:
    """QCMを自動適用する近接粒子対の内部幾何情報。"""

    left_index: int
    right_index: int
    surface_gap_m: float


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
    interaction_positions_m: FloatArray
    interaction_incident_electric_fields_v_m: ComplexArray
    interaction_induced_dipoles_c_m: ComplexArray
    interaction_polarizabilities_si: ComplexArray
    condition_number: float
    relative_residual: float
    warnings: tuple[CdaWarning, ...]
    qcm_applied: bool
    qcm_layer_count: int | None
    qcm_plasma_energy_ev: float | None
    qcm_bulk_damping_energy_ev: float | None
    qcm_bridge_count: int
    qcm_classical_limit_pair_count: int
    qcm_max_relative_permittivity_contrast: float | None
    experimental_quadrupole_coupling_applied: bool
    electric_quadrupole_polarizabilities_si: ComplexArray
    induced_electric_quadrupoles_c_m2: ComplexArray


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
    warnings: tuple[CdaWarning, ...]
    qcm_applied: bool
    qcm_plasma_energy_ev: float | None
    qcm_bulk_damping_energy_ev: float | None
    qcm_bridge_count: int
    qcm_classical_limit_pair_count: int
    experimental_quadrupole_coupling_applied: bool


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
) -> tuple[tuple[CdaWarning, ...], tuple[_QcmPairGeometry, ...]]:
    """重なりを拒否し、QCM対象対と1--5 nmのCDA警告を返す。"""
    minimum_warning_gap_m: float | None = None
    qcm_pairs: list[_QcmPairGeometry] = []
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
                qcm_pairs.append(
                    _QcmPairGeometry(
                        left_index=left_index,
                        right_index=right_index,
                        surface_gap_m=surface_gap_m,
                    )
                )
            # QCMが自動適用される領域は、1--5 nm の古典CDA警告ではなく
            # QCMの適用状況として報告する。境界近傍の丸め誤差は、既存の
            # QCM選択判定と同じ許容幅で通常CDA側へ分類する。
            if (
                surface_gap_m >= QCM_REQUIRED_BELOW_GAP_M - tolerance_m
                and surface_gap_m <= CDA_WARNING_UP_TO_GAP_M + tolerance_m
            ):
                if (
                    minimum_warning_gap_m is None
                    or surface_gap_m < minimum_warning_gap_m
                ):
                    minimum_warning_gap_m = surface_gap_m

    if minimum_warning_gap_m is None:
        return (), tuple(qcm_pairs)
    return (
        (
            CdaWarning(
                code=WARNING_CDA_GAP_LIMITATION,
                parameters={"minimum_gap_nm": minimum_warning_gap_m / 1e-9},
            ),
        ),
        tuple(qcm_pairs),
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


def _build_qcm_auxiliary_dipoles(
    *,
    positions_m: FloatArray,
    diameters_m: FloatArray,
    qcm_pairs: tuple[_QcmPairGeometry, ...],
    wavelength_m: float,
    medium_relative_permittivity: float,
    qcm_parameter_table: GammaGParameterTable | None,
    apply_qcm: bool | None,
    qcm_layer_count: int,
) -> tuple[
    FloatArray,
    ComplexArray,
    bool,
    int,
    int,
    float | None,
    tuple[CdaWarning, ...],
]:
    """QCM対象対の環状層を、CDA連立方程式に加える補助双極子へ変換する。

    ``apply_qcm=False`` はValidation Test 4で古典CDAとの比較を行うためだけの
    内部フックであり、将来のAPI/UI入力として公開してはならない。既定の ``None`` は
    幾何に従う自動適用を意味する。
    """
    empty_positions = np.empty((0, 3), dtype=np.float64)
    empty_polarizabilities = np.empty((0,), dtype=np.complex128)
    if not qcm_pairs:
        return empty_positions, empty_polarizabilities, False, 0, 0, None, ()
    if apply_qcm is False:
        return (
            empty_positions,
            empty_polarizabilities,
            False,
            0,
            0,
            None,
            (
                CdaWarning(
                    code=WARNING_QCM_VALIDATION_OVERRIDE,
                    parameters={"pair_count": len(qcm_pairs)},
                ),
            ),
        )
    if qcm_parameter_table is None:
        raise CdaQcmParameterTableRequiredError(
            "QCM parameter_table is required for a 0.5--1 nm surface gap; "
            "load the versioned table in src.io and pass it to solve_cda"
        )

    angular_frequency_rad_s = 2.0 * math.pi * SPEED_OF_LIGHT_M_PER_S / wavelength_m
    bridge_positions: list[FloatArray] = []
    bridge_polarizabilities: list[complex] = []
    classical_limit_pair_count = 0
    maximum_contrast = 0.0
    for pair in qcm_pairs:
        try:
            bridge: QcmBridge = build_qcm_bridge_for_sphere_pair(
                left_position_m=positions_m[pair.left_index],
                right_position_m=positions_m[pair.right_index],
                left_radius_m=float(diameters_m[pair.left_index] / 2.0),
                right_radius_m=float(diameters_m[pair.right_index] / 2.0),
                angular_frequency_rad_s=angular_frequency_rad_s,
                medium_relative_permittivity=medium_relative_permittivity,
                parameter_table=qcm_parameter_table,
                layer_count=qcm_layer_count,
            )
        except QcmParameterError as error:
            raise CdaConfigurationError(
                "QCM bridge construction failed for particles "
                f"{pair.left_index} and {pair.right_index}"
            ) from error
        if bridge.classical_limit:
            classical_limit_pair_count += 1
            continue
        bridge_positions.append(bridge.position_m)
        bridge_polarizabilities.append(bridge.polarizability_si)
        maximum_contrast = max(
            maximum_contrast,
            bridge.max_relative_permittivity_contrast,
        )

    if not bridge_positions:
        return (
            empty_positions,
            empty_polarizabilities,
            True,
            0,
            classical_limit_pair_count,
            0.0,
            (
                CdaWarning(
                    code=WARNING_QCM_CLASSICAL_LIMIT,
                    parameters={
                        "classical_limit_pair_count": classical_limit_pair_count,
                    },
                ),
            ),
        )
    return (
        np.asarray(bridge_positions, dtype=np.float64),
        np.asarray(bridge_polarizabilities, dtype=np.complex128),
        True,
        len(bridge_positions),
        classical_limit_pair_count,
        maximum_contrast,
        tuple(
            [
                CdaWarning(
                    code=WARNING_QCM_APPLIED,
                    parameters={
                        "layer_count": qcm_layer_count,
                        "bridge_count": len(bridge_positions),
                    },
                )
            ]
            + (
                [
                    CdaWarning(
                        code=WARNING_QCM_CLASSICAL_LIMIT,
                        parameters={
                            "classical_limit_pair_count": classical_limit_pair_count,
                        },
                    )
                ]
                if classical_limit_pair_count > 0
                else []
            )
        ),
    )


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


def _quadrupole_vector_to_tensor(values: ArrayLike) -> ComplexArray:
    """Map ``(Qxx, Qyy, Qxy, Qxz, Qyz)`` to a symmetric traceless tensor.

    The five-component representation is the one used by Evlyukhin et al.,
    *Physical Review B* 85, 245411 (2012), after their Eqs. (1)--(2):
    ``Qzz = -Qxx - Qyy``.  All components are in ``C m^2``.
    """
    vector = np.asarray(values, dtype=np.complex128)
    if vector.shape != (_ELECTRIC_QUADRUPOLE_COMPONENT_COUNT,):
        raise ValueError("electric quadrupole vector must have shape (5,)")
    q_xx, q_yy, q_xy, q_xz, q_yz = vector
    return np.asarray(
        (
            (q_xx, q_xy, q_xz),
            (q_xy, q_yy, q_yz),
            (q_xz, q_yz, -q_xx - q_yy),
        ),
        dtype=np.complex128,
    )


def _quadrupole_tensor_to_vector(tensor: ArrayLike) -> ComplexArray:
    """Return the five independent components of a symmetric traceless tensor."""
    array = np.asarray(tensor, dtype=np.complex128)
    if array.shape != (3, 3):
        raise ValueError("electric quadrupole tensor must have shape (3, 3)")
    return np.asarray(
        (
            array[0, 0],
            array[1, 1],
            (array[0, 1] + array[1, 0]) / 2.0,
            (array[0, 2] + array[2, 0]) / 2.0,
            (array[1, 2] + array[2, 1]) / 2.0,
        ),
        dtype=np.complex128,
    )


def _symmetric_traceless_part(tensor: ArrayLike) -> ComplexArray:
    """Return ``(T + T.T)/2 - trace(T) I / 3`` for a 3 by 3 tensor."""
    array = np.asarray(tensor, dtype=np.complex128)
    if array.shape != (3, 3):
        raise ValueError("tensor must have shape (3, 3)")
    symmetric = (array + array.T) / 2.0
    return np.asarray(
        symmetric - np.trace(symmetric) * np.eye(3, dtype=np.complex128) / 3.0,
        dtype=np.complex128,
    )


def _quadrupole_to_field_block(
    *,
    green_tensor: ComplexArray,
    source_direction: FloatArray,
) -> ComplexArray:
    """Build the 3 by 5 block mapping independent ``Q`` values to ``E``."""
    basis_vectors = np.eye(_ELECTRIC_QUADRUPOLE_COMPONENT_COUNT, dtype=np.complex128)
    return np.column_stack(
        [
            green_tensor
            @ (_quadrupole_vector_to_tensor(basis) @ source_direction)
            for basis in basis_vectors
        ]
    )


def _dipole_to_quadrupole_block(
    *,
    green_tensor_gradient: NDArray[np.complex128],
) -> ComplexArray:
    """Build the 5 by 3 block mapping a source dipole to ``sym(grad(E))``."""
    basis_vectors = np.eye(3, dtype=np.complex128)
    return np.column_stack(
        [
            _quadrupole_tensor_to_vector(
                _symmetric_traceless_part(
                    np.einsum("abc,c->ab", green_tensor_gradient, basis)
                )
            )
            for basis in basis_vectors
        ]
    )


def _build_experimental_dipole_quadrupole_interaction_matrix(
    *,
    interaction_positions_m: FloatArray,
    interaction_polarizabilities_si: ComplexArray,
    physical_particle_count: int,
    electric_quadrupole_polarizabilities_si: ComplexArray,
    wave_number_m_inv: float,
    medium_relative_permittivity: float,
) -> ComplexArray:
    """Build the experimental ED--EQ system with no quadrupole--quadrupole block.

    This implements the ED--EQ terms of Eqs. (1)--(2) in Evlyukhin et al.,
    *Physical Review B* 85, 245411 (2012), DOI: 10.1103/PhysRevB.85.245411.
    It intentionally excludes their quadrupole--quadrupole terms and all
    magnetic multipoles.  It is therefore not an energy-conserving complete
    multipole model and must only be reached through the explicit experimental
    flag.  The solved quadrupole unknown is ``k_m Q`` rather than ``Q`` so
    that it has the same SI units as a dipole moment.  This is a numerical
    row/column scaling only; the returned solution is converted back to
    ``Q`` in ``C m^2`` after the solve.
    """
    interaction_particle_count = len(interaction_positions_m)
    expected_quadrupole_shape = (physical_particle_count,)
    if electric_quadrupole_polarizabilities_si.shape != expected_quadrupole_shape:
        raise ValueError("electric quadrupole polarizabilities do not match particles")

    dipole_dimension = 3 * interaction_particle_count
    total_dimension = dipole_dimension + (
        _ELECTRIC_QUADRUPOLE_COMPONENT_COUNT * physical_particle_count
    )
    matrix = np.eye(total_dimension, dtype=np.complex128)
    interaction_scale = wave_number_m_inv**2 / (
        VACUUM_PERMITTIVITY_F_PER_M * medium_relative_permittivity
    )

    def dipole_slice(index: int) -> slice:
        return slice(3 * index, 3 * index + 3)

    def quadrupole_slice(index: int) -> slice:
        start = dipole_dimension + _ELECTRIC_QUADRUPOLE_COMPONENT_COUNT * index
        return slice(start, start + _ELECTRIC_QUADRUPOLE_COMPONENT_COUNT)

    for target_index in range(interaction_particle_count):
        target_dipole_slice = dipole_slice(target_index)
        for source_index in range(interaction_particle_count):
            if target_index == source_index:
                continue
            source_dipole_slice = dipole_slice(source_index)
            relative_position = (
                interaction_positions_m[target_index]
                - interaction_positions_m[source_index]
            )
            green_tensor = retarded_dyadic_green_tensor(
                relative_position_m=relative_position,
                wave_number_m_inv=wave_number_m_inv,
            )
            matrix[target_dipole_slice, source_dipole_slice] = (
                -interaction_polarizabilities_si[target_index]
                * interaction_scale
                * green_tensor
            )

        for source_index in range(physical_particle_count):
            if target_index == source_index:
                continue
            relative_position = (
                interaction_positions_m[target_index]
                - interaction_positions_m[source_index]
            )
            source_direction = relative_position / np.linalg.norm(relative_position)
            quadrupole_green_tensor = retarded_electric_quadrupole_green_tensor(
                relative_position_m=relative_position,
                wave_number_m_inv=wave_number_m_inv,
            )
            matrix[target_dipole_slice, quadrupole_slice(source_index)] = (
                -interaction_polarizabilities_si[target_index]
                * interaction_scale
                * _quadrupole_to_field_block(
                    green_tensor=quadrupole_green_tensor,
                    source_direction=source_direction,
                )
                / wave_number_m_inv
            )

    for target_index in range(physical_particle_count):
        target_quadrupole_slice = quadrupole_slice(target_index)
        for source_index in range(interaction_particle_count):
            if target_index == source_index:
                continue
            relative_position = (
                interaction_positions_m[target_index]
                - interaction_positions_m[source_index]
            )
            green_tensor_gradient = gradient_of_retarded_dyadic_green_tensor(
                relative_position_m=relative_position,
                wave_number_m_inv=wave_number_m_inv,
            )
            matrix[target_quadrupole_slice, dipole_slice(source_index)] = (
                -electric_quadrupole_polarizabilities_si[target_index]
                * wave_number_m_inv
                * interaction_scale
                * _dipole_to_quadrupole_block(
                    green_tensor_gradient=green_tensor_gradient
                )
            )
    return matrix


def _experimental_quadrupole_right_hand_side(
    *,
    interaction_polarizabilities_si: ComplexArray,
    interaction_incident_electric_fields_v_m: ComplexArray,
    physical_particle_count: int,
    electric_quadrupole_polarizabilities_si: ComplexArray,
    wave_number_m_inv: float,
    propagation_direction: FloatArray,
) -> ComplexArray:
    """Build the ED--EQ incident vector from Eqs. (1)--(2) of Evlyukhin et al.

    The source is Evlyukhin et al., *Physical Review B* 85, 245411 (2012),
    DOI: 10.1103/PhysRevB.85.245411.
    """
    dipole_right_hand_side = (
        interaction_polarizabilities_si[:, np.newaxis]
        * interaction_incident_electric_fields_v_m
    ).reshape(-1)
    quadrupole_right_hand_side = np.empty(
        _ELECTRIC_QUADRUPOLE_COMPONENT_COUNT * physical_particle_count,
        dtype=np.complex128,
    )
    for particle_index in range(physical_particle_count):
        incident_gradient = 1j * wave_number_m_inv * np.outer(
            propagation_direction,
            interaction_incident_electric_fields_v_m[particle_index],
        )
        quadrupole_tensor = (
            electric_quadrupole_polarizabilities_si[particle_index]
            * wave_number_m_inv
            * _symmetric_traceless_part(incident_gradient)
        )
        start = _ELECTRIC_QUADRUPOLE_COMPONENT_COUNT * particle_index
        quadrupole_right_hand_side[
            start : start + _ELECTRIC_QUADRUPOLE_COMPONENT_COUNT
        ] = _quadrupole_tensor_to_vector(quadrupole_tensor)
    return np.concatenate((dipole_right_hand_side, quadrupole_right_hand_side))


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
    qcm_parameter_table: GammaGParameterTable | None = None,
    apply_qcm: bool | None = None,
    qcm_layer_count: int = DEFAULT_QCM_LAYER_COUNT,
    apply_experimental_quadrupole_coupling: bool = False,
) -> CdaSolution:
    """一波長の FCDA-CDA 連立方程式を解く。

    最大50物理粒子、すなわち最大150複素自由度を対象に ``scipy.linalg.solve`` を
    用いる。QCMでは近接粒子対ごとに補助双極子の3自由度が加わる。行列の2ノルム
    条件数が ``max_condition_number`` を超える、特異、または残差が丸め誤差の見積りを
    超える場合は、非物理的な結果を返さず例外にする。

    ``qcm_parameter_table`` はファイルを知らない物理層へ呼出し側が注入する。0.5 nm
    以上1 nm未満の粒子対で既定の ``apply_qcm=None`` を使うとQCMを自動適用する。
    ``apply_qcm=False`` はValidation Test 4用の古典比較だけに限る内部フックである。
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
    if apply_qcm is not None and not isinstance(apply_qcm, bool):
        raise CdaConfigurationError("apply_qcm must be None or bool")
    if not isinstance(apply_experimental_quadrupole_coupling, bool):
        raise CdaConfigurationError(
            "apply_experimental_quadrupole_coupling must be bool"
        )
    geometry_warnings, qcm_pairs = _validate_surface_gaps(
        positions_m=positions,
        diameters_m=diameters,
    )
    if len(positions) > MAX_QCM_PARTICLES and (qcm_pairs or geometry_warnings):
        raise CdaConfigurationError(
            "more than 20 particles require every surface gap to exceed 5 nm; "
            "QCM and the 1-5 nm CDA warning range remain limited to 20 particles"
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
    if apply_experimental_quadrupole_coupling:
        quadrupole_polarizability_results: list[ElectricQuadrupolePolarizability] = []
        for diameter_m in diameters:
            quadrupole_polarizability_results.append(
                calculate_electric_quadrupole_polarizability(
                    wavelength_m=wavelength_m,
                    diameter_m=float(diameter_m),
                    medium_refractive_index=medium_refractive_index,
                    optical_constants=optical_constants,
                    apply_kreibig_correction=apply_kreibig_correction,
                    kreibig_parameters=kreibig_parameters,
                )
            )
        electric_quadrupole_polarizabilities_si = np.asarray(
            [result.polarizability_si for result in quadrupole_polarizability_results],
            dtype=np.complex128,
        )
    else:
        electric_quadrupole_polarizabilities_si = np.zeros(
            len(positions), dtype=np.complex128
        )
    wave_number_m_inv = polarizability_results[0].wave_number_m_inv
    medium_relative_permittivity = medium_refractive_index**2
    (
        qcm_bridge_positions,
        qcm_bridge_polarizabilities,
        qcm_applied,
        qcm_bridge_count,
        qcm_classical_limit_pair_count,
        qcm_max_relative_permittivity_contrast,
        qcm_warnings,
    ) = _build_qcm_auxiliary_dipoles(
        positions_m=positions,
        diameters_m=diameters,
        qcm_pairs=qcm_pairs,
        wavelength_m=wavelength_m,
        medium_relative_permittivity=medium_relative_permittivity,
        qcm_parameter_table=qcm_parameter_table,
        apply_qcm=apply_qcm,
        qcm_layer_count=qcm_layer_count,
    )
    interaction_positions = np.vstack((positions, qcm_bridge_positions))
    interaction_polarizabilities_si = np.concatenate(
        (polarizabilities_si, qcm_bridge_polarizabilities)
    )
    interaction_incident_fields = _incident_electric_fields(
        positions_m=interaction_positions,
        wave_number_m_inv=wave_number_m_inv,
        propagation_direction=normalized_propagation_direction,
        polarization=normalized_polarization,
        incident_field_amplitude_v_m=incident_field_amplitude_v_m,
    )
    if apply_experimental_quadrupole_coupling:
        interaction_matrix = _build_experimental_dipole_quadrupole_interaction_matrix(
            interaction_positions_m=interaction_positions,
            interaction_polarizabilities_si=interaction_polarizabilities_si,
            physical_particle_count=len(positions),
            electric_quadrupole_polarizabilities_si=(
                electric_quadrupole_polarizabilities_si
            ),
            wave_number_m_inv=wave_number_m_inv,
            medium_relative_permittivity=medium_relative_permittivity,
        )
    else:
        interaction_matrix = _build_interaction_matrix(
            positions_m=interaction_positions,
            polarizabilities_si=interaction_polarizabilities_si,
            wave_number_m_inv=wave_number_m_inv,
            medium_relative_permittivity=medium_relative_permittivity,
        )
    condition_number = float(np.linalg.cond(interaction_matrix))
    if not math.isfinite(condition_number) or condition_number > max_condition_number:
        raise CdaIllConditionedMatrixError(
            "CDA interaction matrix is singular or ill-conditioned "
            f"(condition number {condition_number:.6g}, limit {max_condition_number:.6g})"
        )

    if apply_experimental_quadrupole_coupling:
        right_hand_side = _experimental_quadrupole_right_hand_side(
            interaction_polarizabilities_si=interaction_polarizabilities_si,
            interaction_incident_electric_fields_v_m=interaction_incident_fields,
            physical_particle_count=len(positions),
            electric_quadrupole_polarizabilities_si=(
                electric_quadrupole_polarizabilities_si
            ),
            wave_number_m_inv=wave_number_m_inv,
            propagation_direction=normalized_propagation_direction,
        )
    else:
        right_hand_side = (
            interaction_polarizabilities_si[:, np.newaxis] * interaction_incident_fields
        ).reshape(-1)
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

    interaction_induced_dipoles = np.asarray(
        flat_dipoles[: 3 * len(interaction_positions)].reshape(
            (len(interaction_positions), 3)
        ),
        dtype=np.complex128,
    )
    if not np.all(np.isfinite(interaction_induced_dipoles)):
        raise CdaLinearSolveError("CDA induced dipoles are non-finite")
    induced_dipoles = interaction_induced_dipoles[: len(positions)]
    if apply_experimental_quadrupole_coupling:
        flat_quadrupoles = flat_dipoles[3 * len(interaction_positions) :]
        induced_electric_quadrupoles = np.asarray(
            [
                _quadrupole_vector_to_tensor(
                    flat_quadrupoles[
                        _ELECTRIC_QUADRUPOLE_COMPONENT_COUNT
                        * particle_index : _ELECTRIC_QUADRUPOLE_COMPONENT_COUNT
                        * (particle_index + 1)
                    ]
                    / wave_number_m_inv
                )
                for particle_index in range(len(positions))
            ],
            dtype=np.complex128,
        )
        if not np.all(np.isfinite(induced_electric_quadrupoles)):
            raise CdaLinearSolveError("CDA induced electric quadrupoles are non-finite")
        experimental_warnings = (
            CdaWarning(code=WARNING_EXPERIMENTAL_QUADRUPOLE_COUPLING),
        )
    else:
        induced_electric_quadrupoles = np.zeros(
            (len(positions), 3, 3), dtype=np.complex128
        )
        experimental_warnings = ()

    return CdaSolution(
        wavelength_m=wavelength_m,
        wave_number_m_inv=wave_number_m_inv,
        medium_refractive_index=medium_refractive_index,
        positions_m=positions,
        diameters_m=diameters,
        propagation_direction=normalized_propagation_direction,
        polarization=normalized_polarization,
        incident_electric_fields_v_m=interaction_incident_fields[: len(positions)],
        induced_dipoles_c_m=induced_dipoles,
        polarizabilities_si=polarizabilities_si,
        interaction_positions_m=interaction_positions,
        interaction_incident_electric_fields_v_m=interaction_incident_fields,
        interaction_induced_dipoles_c_m=interaction_induced_dipoles,
        interaction_polarizabilities_si=interaction_polarizabilities_si,
        condition_number=condition_number,
        relative_residual=relative_residual,
        warnings=geometry_warnings + qcm_warnings + experimental_warnings,
        qcm_applied=qcm_applied,
        qcm_layer_count=qcm_layer_count if qcm_applied else None,
        qcm_plasma_energy_ev=(
            AU_JELLIUM_QCM_PLASMA_ENERGY_EV if qcm_applied else None
        ),
        qcm_bulk_damping_energy_ev=(
            AU_JELLIUM_QCM_BULK_DAMPING_ENERGY_EV if qcm_applied else None
        ),
        qcm_bridge_count=qcm_bridge_count,
        qcm_classical_limit_pair_count=qcm_classical_limit_pair_count,
        qcm_max_relative_permittivity_contrast=qcm_max_relative_permittivity_contrast,
        experimental_quadrupole_coupling_applied=(
            apply_experimental_quadrupole_coupling
        ),
        electric_quadrupole_polarizabilities_si=(
            electric_quadrupole_polarizabilities_si
        ),
        induced_electric_quadrupoles_c_m2=induced_electric_quadrupoles,
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


@lru_cache(maxsize=1)
def _experimental_quadrupole_scattering_directions() -> tuple[FloatArray, FloatArray]:
    """Return a deterministic sphere quadrature for experimental ED--EQ scattering.

    The polar coordinate uses Gauss--Legendre nodes and the azimuth uses a
    uniform periodic grid.  This only evaluates the far-field integral in
    Eq. (28) of Evlyukhin et al. (2012); it is not an additional physical
    approximation or fitted parameter.
    """
    cosine_theta, polar_weights = np.polynomial.legendre.leggauss(
        _EXPERIMENTAL_QUADRUPOLE_SCATTERING_POLAR_ORDER
    )
    phi = np.linspace(
        0.0,
        2.0 * math.pi,
        _EXPERIMENTAL_QUADRUPOLE_SCATTERING_AZIMUTHAL_ORDER,
        endpoint=False,
    )
    cosine_grid, phi_grid = np.meshgrid(cosine_theta, phi, indexing="ij")
    sine_grid = np.sqrt(np.maximum(0.0, 1.0 - cosine_grid**2))
    directions = np.column_stack(
        (
            (sine_grid * np.cos(phi_grid)).ravel(),
            (sine_grid * np.sin(phi_grid)).ravel(),
            cosine_grid.ravel(),
        )
    )
    weights = np.repeat(polar_weights, len(phi)) * (2.0 * math.pi / len(phi))
    return (
        np.asarray(directions, dtype=np.float64),
        np.asarray(weights, dtype=np.float64),
    )


def _experimental_quadrupole_extinction_contribution(
    solution: CdaSolution,
    *,
    incident_amplitude_squared: float,
    medium_relative_permittivity: float,
) -> float:
    """Evaluate the electric-quadrupole term in Eq. (23) of Evlyukhin et al."""
    quadrupole_overlap = 0.0j
    for incident_field, quadrupole in zip(
        solution.incident_electric_fields_v_m,
        solution.induced_electric_quadrupoles_c_m2,
        strict=True,
    ):
        conjugated_incident_gradient = -1j * solution.wave_number_m_inv * np.outer(
            solution.propagation_direction,
            incident_field.conjugate(),
        )
        quadrupole_driver = (
            conjugated_incident_gradient + conjugated_incident_gradient.T
        ) / 12.0
        quadrupole_overlap += np.einsum("ab,ab", quadrupole_driver, quadrupole)
    return (
        solution.wave_number_m_inv
        * float(np.imag(quadrupole_overlap))
        / (
            VACUUM_PERMITTIVITY_F_PER_M
            * medium_relative_permittivity
            * incident_amplitude_squared
        )
    )


def _experimental_dipole_quadrupole_scattering_cross_section(
    solution: CdaSolution,
    *,
    incident_amplitude_squared: float,
) -> float:
    """Integrate the ED--EQ far field of Eq. (28) of Evlyukhin et al. (2012).

    Quadrupole--quadrupole and magnetic moments are absent from the solved
    system by design.  The returned value is therefore an experimental
    approximate scattering term, not a replacement for a complete multipole
    method.
    """
    directions, angular_weights = _experimental_quadrupole_scattering_directions()
    source_phases = np.exp(
        -1j
        * solution.wave_number_m_inv
        * (directions @ solution.interaction_positions_m.T)
    )
    dipole_amplitudes = source_phases @ solution.interaction_induced_dipoles_c_m
    quadrupole_directional_moments = np.einsum(
        "qab,db->dqa",
        solution.induced_electric_quadrupoles_c_m2,
        directions,
    )
    quadrupole_amplitudes = np.einsum(
        "dq,dqa->da",
        source_phases[:, : len(solution.positions_m)],
        quadrupole_directional_moments,
    )
    source_amplitudes = dipole_amplitudes - (
        1j * solution.wave_number_m_inv / 6.0
    ) * quadrupole_amplitudes
    transverse_amplitudes = source_amplitudes - directions * np.einsum(
        "da,da->d", directions, source_amplitudes
    )[:, np.newaxis]
    angular_integral = float(
        np.sum(
            angular_weights
            * np.sum(np.abs(transverse_amplitudes) ** 2, axis=1)
        )
    )
    vacuum_wave_number_m_inv = (
        solution.wave_number_m_inv / solution.medium_refractive_index
    )
    return (
        vacuum_wave_number_m_inv**4
        * angular_integral
        / (
            16.0
            * math.pi**2
            * VACUUM_PERMITTIVITY_F_PER_M**2
            * incident_amplitude_squared
        )
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
            solution.interaction_incident_electric_fields_v_m[0],
            solution.interaction_incident_electric_fields_v_m[0],
        ).real
    )
    if incident_amplitude_squared <= 0.0:
        raise CdaLinearSolveError("incident electric-field amplitude is invalid")

    dipole_extinction_overlap = np.vdot(
        solution.interaction_incident_electric_fields_v_m,
        solution.interaction_induced_dipoles_c_m,
    )
    c_ext_m2 = (
        solution.wave_number_m_inv
        * float(np.imag(dipole_extinction_overlap))
        / (
            VACUUM_PERMITTIVITY_F_PER_M
            * medium_relative_permittivity
            * incident_amplitude_squared
        )
    )
    if solution.experimental_quadrupole_coupling_applied:
        c_ext_m2 += _experimental_quadrupole_extinction_contribution(
            solution,
            incident_amplitude_squared=incident_amplitude_squared,
            medium_relative_permittivity=medium_relative_permittivity,
        )
        c_sca_m2 = _experimental_dipole_quadrupole_scattering_cross_section(
            solution,
            incident_amplitude_squared=incident_amplitude_squared,
        )
    else:
        scattering_overlap = 0.0j
        for target_index, target_dipole in enumerate(
            solution.interaction_induced_dipoles_c_m
        ):
            for source_index, source_dipole in enumerate(
                solution.interaction_induced_dipoles_c_m
            ):
                imaginary_green = imaginary_part_of_green_tensor(
                    relative_position_m=(
                        solution.interaction_positions_m[target_index]
                        - solution.interaction_positions_m[source_index]
                    ),
                    wave_number_m_inv=solution.wave_number_m_inv,
                )
                scattering_overlap += np.vdot(
                    target_dipole, imaginary_green @ source_dipole
                )
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
    if (
        not solution.experimental_quadrupole_coupling_applied
        and c_abs_m2 < -rounding_tolerance
    ):
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
    qcm_parameter_table: GammaGParameterTable | None = None,
    apply_qcm: bool | None = None,
    qcm_layer_count: int = DEFAULT_QCM_LAYER_COUNT,
    apply_experimental_quadrupole_coupling: bool = False,
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
    geometry_warnings: tuple[CdaWarning, ...] | None = None
    qcm_applied: bool | None = None
    qcm_bridge_count: int | None = None
    qcm_classical_limit_pair_count: int | None = None
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
            qcm_parameter_table=qcm_parameter_table,
            apply_qcm=apply_qcm,
            qcm_layer_count=qcm_layer_count,
            apply_experimental_quadrupole_coupling=(
                apply_experimental_quadrupole_coupling
            ),
        )
        cross_sections = calculate_cda_cross_sections(solution)
        c_ext_m2[index] = cross_sections.c_ext_m2
        c_sca_m2[index] = cross_sections.c_sca_m2
        c_abs_m2[index] = cross_sections.c_abs_m2
        condition_numbers[index] = solution.condition_number
        if geometry_warnings is None:
            geometry_warnings = solution.warnings
            qcm_applied = solution.qcm_applied
            qcm_bridge_count = solution.qcm_bridge_count
            qcm_classical_limit_pair_count = solution.qcm_classical_limit_pair_count

    return CdaSpectrum(
        wavelength_m=wavelengths,
        c_ext_m2=c_ext_m2,
        c_sca_m2=c_sca_m2,
        c_abs_m2=c_abs_m2,
        condition_numbers=condition_numbers,
        warnings=geometry_warnings or (),
        qcm_applied=bool(qcm_applied),
        qcm_plasma_energy_ev=(
            AU_JELLIUM_QCM_PLASMA_ENERGY_EV if qcm_applied else None
        ),
        qcm_bulk_damping_energy_ev=(
            AU_JELLIUM_QCM_BULK_DAMPING_ENERGY_EV if qcm_applied else None
        ),
        qcm_bridge_count=qcm_bridge_count or 0,
        qcm_classical_limit_pair_count=qcm_classical_limit_pair_count or 0,
        experimental_quadrupole_coupling_applied=(
            apply_experimental_quadrupole_coupling
        ),
    )
