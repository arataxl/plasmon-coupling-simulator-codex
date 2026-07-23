"""検証済み入力をCDA/QCM計算へ接続し、保存しない応答データを組み立てる。"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping

import numpy as np
from pydantic import ValidationError

from src.io.unit_conversion import metres_to_nanometres, nanometres_to_metres
from src.physics.cda_solver import (
    CdaConfigurationError,
    CdaCrossSections,
    CdaError,
    CdaSolution,
    calculate_cda_cross_sections,
    calculate_cda_spectrum,
    solve_cda,
    CdaWarning,
)
from src.physics.material_data import MaterialDataError, OpticalConstants
from src.physics.mie_reference import (
    MieSpectrum,
    calculate_exact_single_sphere_mie_spectrum,
)
from src.physics.qcm import GammaGParameterTable, QcmParameterError
from src.schemas.result import (
    CrossSectionsResult,
    ExperimentalQuadrupoleMetadata,
    QcmResultMetadata,
    ResultProvenance,
    ResultWarning,
    SimulationResult,
    SpectrumResult,
)
from src.schemas.simulation import (
    ExactMieSimulationInput,
    MAX_QCM_CDA_PARTICLES,
    MAX_STREAM_SPECTRUM_POINTS,
    MAX_SYNCHRONOUS_SPECTRUM_POINTS,
    SimulationInput,
    SimulationRequest,
    SpectrumRangeInput,
)
from src.services.spectrum_smoothing import (
    SMOOTHING_DEFAULT_LEVEL,
    smooth_spectrum_cross_sections,
)


QCM_PARAMETER_SOURCE = "Esteban et al. (2012), DOI: 10.1038/ncomms1806"
QCM_CALIBRATION_POINTS = "not provided with the digitized data"
QCM_READING_UNCERTAINTY = "approximately 5-10%"
QCM_FIGURE = "Fig. 2d"
QCM_CURVE = "Au jellium, blue solid line"
QCM_INTERPOLATION = "shape-preserving PCHIP of log(gamma_g)"
QCM_CDA_MODEL = "volume-equivalent auxiliary bridge dipole"
QCM_MODEL_ERROR_ESTIMATE = (
    "3/4/5-layer sensitivity only; model-form error is unbounded without "
    "BEM/DDA reference"
)
MODEL_NAME = "FCDA-CDA with QCM auxiliary bridge dipoles"
EXPERIMENTAL_QUADRUPOLE_MODEL_NAME = (
    "FCDA-CDA with QCM auxiliary bridge dipoles and experimental electric dipole--quadrupole coupling"
)
EXPERIMENTAL_QUADRUPOLE_SOURCE = (
    "Evlyukhin et al. (2012), DOI: 10.1103/PhysRevB.85.245411, Eqs. (1)-(2), (7), (16), and (23)-(28)"
)
EXPERIMENTAL_QUADRUPOLE_INCLUDED_TERMS = (
    "electric dipoles, single-sphere electric quadrupoles from Mie a2, and approximate dipole--quadrupole coupling"
)
EXPERIMENTAL_QUADRUPOLE_OMITTED_TERMS = (
    "quadrupole--quadrupole coupling, magnetic dipoles, magnetic quadrupoles, and higher multipoles"
)
EXPERIMENTAL_QUADRUPOLE_ENERGY_NOTE = (
    "The incomplete multipole truncation does not guarantee exact energy conservation."
)
EXPERIMENTAL_QUADRUPOLE_INTENDED_USE = (
    "Qualitative near-infrared trend exploration only; not quantitative validation."
)
EXACT_SINGLE_SPHERE_MIE_MODEL_NAME = "Exact single-sphere Mie theory (all orders)"
MATERIAL_DATA_SOURCE = "McPeak et al. (2015) Au n + ik dataset"
MATERIAL_DATA_INTERPOLATION = "linear interpolation of n and k; no extrapolation"
SOFTWARE_VERSION = "0.2.0"
MAX_SYNCHRONOUS_CDA_PARTICLES = MAX_QCM_CDA_PARTICLES


class SimulationServiceError(RuntimeError):
    """APIへ明示的なエラー応答を返すためのサービス層例外。"""

    status_code = 422
    error_code = "simulation_failed"

    def __init__(
        self,
        message: str,
        *,
        parameters: Mapping[str, float | int] | None = None,
    ) -> None:
        super().__init__(message)
        self.parameters = dict(parameters or {})


class QcmMetadataUnavailableError(SimulationServiceError):
    """QCM結果へ必須の出典情報を付与できないことを示す。"""

    status_code = 503
    error_code = "qcm_metadata_unavailable"


class SimulationRequiresStreamingError(SimulationServiceError):
    """大規模CDAを同期APIで実行しないための明示的な拒否。"""

    error_code = "large_cda_requires_stream"


class SimulationCancelledError(RuntimeError):
    """進行中ジョブが波長点の境界で取り消されたことを示す。"""


def spectrum_point_count(spectrum: SpectrumRangeInput) -> int:
    """終端点を必ず含む仕様で必要なスペクトル点数を返す。"""
    interval_count = math.ceil(
        (spectrum.end_wavelength_nm - spectrum.start_wavelength_nm)
        / spectrum.step_nm
    )
    return interval_count + 1


def validate_spectrum_point_limit(
    spectrum: SpectrumRangeInput,
    *,
    maximum_points: int,
    endpoint_name: str,
) -> None:
    """エンドポイントごとに設定した波長点数上限を検証する。"""
    point_count = spectrum_point_count(spectrum)
    if point_count > maximum_points:
        raise SimulationServiceError(
            f"spectrum range exceeds the {endpoint_name} limit of "
            f"{maximum_points} points; increase step_nm or narrow the range",
            parameters={
                "maximum_points": maximum_points,
                "requested_points": point_count,
            },
        )


def build_wavelength_grid_nm(
    spectrum: SpectrumRangeInput,
    *,
    maximum_points: int | None = None,
    endpoint_name: str = "requested",
) -> np.ndarray:
    """入力範囲を含む真空波長格子をnmで返す。"""
    if maximum_points is not None:
        validate_spectrum_point_limit(
            spectrum,
            maximum_points=maximum_points,
            endpoint_name=endpoint_name,
        )
    values = np.arange(
        spectrum.start_wavelength_nm,
        spectrum.end_wavelength_nm + spectrum.step_nm * 0.5,
        spectrum.step_nm,
        dtype=np.float64,
    )
    tolerance_nm = max(1.0e-12, spectrum.step_nm * 1.0e-12)
    values = values[values <= spectrum.end_wavelength_nm + tolerance_nm]
    if values.size == 0:
        values = np.asarray([spectrum.start_wavelength_nm], dtype=np.float64)
    if not math.isclose(
        float(values[-1]),
        spectrum.end_wavelength_nm,
        rel_tol=0.0,
        abs_tol=tolerance_nm,
    ):
        values = np.append(values, spectrum.end_wavelength_nm)
    else:
        values[-1] = spectrum.end_wavelength_nm
    return values


def build_qcm_result_metadata(solution: CdaSolution) -> QcmResultMetadata:
    """CDA解から、仕様で必須のQCM出典メタデータを構成する。"""
    if not solution.qcm_applied:
        return QcmResultMetadata(qcm_applied=False)

    required_values = {
        "qcm_layer_count": solution.qcm_layer_count,
        "qcm_plasma_energy_ev": solution.qcm_plasma_energy_ev,
        "qcm_bulk_damping_energy_ev": solution.qcm_bulk_damping_energy_ev,
    }
    missing_values = [name for name, value in required_values.items() if value is None]
    if missing_values:
        raise QcmMetadataUnavailableError(
            "QCM calculation completed without required metadata values: "
            + ", ".join(missing_values)
        )

    try:
        return QcmResultMetadata(
            qcm_applied=True,
            qcm_parameter_status="provisional_digitized",
            qcm_parameter_source=QCM_PARAMETER_SOURCE,
            qcm_calibration_points=QCM_CALIBRATION_POINTS,
            qcm_reading_uncertainty=QCM_READING_UNCERTAINTY,
            qcm_figure=QCM_FIGURE,
            qcm_curve=QCM_CURVE,
            qcm_interpolation=QCM_INTERPOLATION,
            qcm_layer_count=solution.qcm_layer_count,
            qcm_plasma_energy_ev=solution.qcm_plasma_energy_ev,
            qcm_bulk_damping_energy_ev=solution.qcm_bulk_damping_energy_ev,
            qcm_cda_model=QCM_CDA_MODEL,
            qcm_model_error_estimate=QCM_MODEL_ERROR_ESTIMATE,
            qcm_classical_limit_pair_count=solution.qcm_classical_limit_pair_count,
            qcm_max_relative_permittivity_contrast=(
                solution.qcm_max_relative_permittivity_contrast
            ),
        )
    except ValidationError as error:
        raise QcmMetadataUnavailableError(
            "QCM result metadata does not satisfy the provisional-digitization "
            "provenance contract"
        ) from error


def build_experimental_quadrupole_metadata(
    solution: CdaSolution,
) -> ExperimentalQuadrupoleMetadata:
    """Build mandatory provenance for the opt-in incomplete ED--EQ extension."""
    if not solution.experimental_quadrupole_coupling_applied:
        return ExperimentalQuadrupoleMetadata(applied=False)
    try:
        return ExperimentalQuadrupoleMetadata(
            applied=True,
            model="approximate_electric_dipole_electric_quadrupole_coupling",
            source=EXPERIMENTAL_QUADRUPOLE_SOURCE,
            included_terms=EXPERIMENTAL_QUADRUPOLE_INCLUDED_TERMS,
            omitted_terms=EXPERIMENTAL_QUADRUPOLE_OMITTED_TERMS,
            energy_conservation_note=EXPERIMENTAL_QUADRUPOLE_ENERGY_NOTE,
            intended_use=EXPERIMENTAL_QUADRUPOLE_INTENDED_USE,
        )
    except ValidationError as error:
        raise SimulationServiceError(
            "experimental quadrupole result metadata is incomplete"
        ) from error


def _as_positions_m(simulation: SimulationInput) -> np.ndarray:
    positions_nm = np.asarray(
        [
            (particle.x_nm, particle.y_nm, particle.z_nm)
            for particle in simulation.particles
        ],
        dtype=np.float64,
    )
    return np.asarray(nanometres_to_metres(positions_nm), dtype=np.float64)


def _as_diameters_m(simulation: SimulationInput) -> np.ndarray:
    diameters_nm = np.asarray(
        [particle.diameter_nm for particle in simulation.particles],
        dtype=np.float64,
    )
    return np.asarray(nanometres_to_metres(diameters_nm), dtype=np.float64)


def _as_cross_sections_result(
    cross_sections: CdaCrossSections,
    *,
    wavelength_nm: float,
    geometric_cross_section_m2: float,
) -> CrossSectionsResult:
    return CrossSectionsResult(
        wavelength_nm=wavelength_nm,
        c_ext_m2=cross_sections.c_ext_m2,
        c_sca_m2=cross_sections.c_sca_m2,
        c_abs_m2=cross_sections.c_abs_m2,
        geometric_cross_section_m2=geometric_cross_section_m2,
        q_ext=cross_sections.c_ext_m2 / geometric_cross_section_m2,
        q_sca=cross_sections.c_sca_m2 / geometric_cross_section_m2,
        q_abs=cross_sections.c_abs_m2 / geometric_cross_section_m2,
    )


def _geometric_cross_section_m2(diameters_m: np.ndarray) -> float:
    """集合体効率の基準となる各球の投影面積和を返す。"""
    geometric_cross_section_m2 = float(np.sum(np.pi * (diameters_m / 2.0) ** 2))
    if not math.isfinite(geometric_cross_section_m2) or geometric_cross_section_m2 <= 0.0:
        raise SimulationServiceError("aggregate geometric cross section is invalid")
    return geometric_cross_section_m2


def _spectrum_result(
    *,
    wavelength_nm: np.ndarray,
    c_ext_m2: np.ndarray,
    c_sca_m2: np.ndarray,
    c_abs_m2: np.ndarray,
    geometric_cross_section_m2: float,
    smoothing_level: str | None,
) -> SpectrumResult:
    """生データを残して、API 表示用後処理済みスペクトルを構成する。"""
    cross_sections = smooth_spectrum_cross_sections(
        c_ext_m2=c_ext_m2,
        c_sca_m2=c_sca_m2,
        c_abs_m2=c_abs_m2,
        level=smoothing_level or SMOOTHING_DEFAULT_LEVEL,
    )
    return SpectrumResult(
        wavelength_nm=[float(value) for value in wavelength_nm],
        c_ext_m2=[float(value) for value in cross_sections.c_ext_m2],
        c_sca_m2=[float(value) for value in cross_sections.c_sca_m2],
        c_abs_m2=[float(value) for value in cross_sections.c_abs_m2],
        q_ext=[
            float(value / geometric_cross_section_m2)
            for value in cross_sections.c_ext_m2
        ],
        q_sca=[
            float(value / geometric_cross_section_m2)
            for value in cross_sections.c_sca_m2
        ],
        q_abs=[
            float(value / geometric_cross_section_m2)
            for value in cross_sections.c_abs_m2
        ],
        geometric_cross_section_m2=geometric_cross_section_m2,
        raw_c_ext_m2=[float(value) for value in cross_sections.raw_c_ext_m2],
        raw_c_sca_m2=[float(value) for value in cross_sections.raw_c_sca_m2],
        raw_c_abs_m2=[float(value) for value in cross_sections.raw_c_abs_m2],
    )


def _build_simulation_result(
    *,
    simulation: SimulationInput,
    diameters_m: np.ndarray,
    reference_cross_sections: CdaCrossSections,
    reference_solution: CdaSolution,
    wavelength_grid_nm: np.ndarray,
    c_ext_m2: np.ndarray,
    c_sca_m2: np.ndarray,
    c_abs_m2: np.ndarray,
    warnings: tuple[CdaWarning, ...],
    spectrum_qcm_applied: bool,
    spectrum_experimental_quadrupole_coupling_applied: bool,
) -> SimulationResult:
    """同期・ストリーミング計算で共通の再現可能な結果を組み立てる。"""
    qcm_metadata = build_qcm_result_metadata(reference_solution)
    if spectrum_qcm_applied != qcm_metadata.qcm_applied:
        raise SimulationServiceError(
            "QCM application status is inconsistent between reference and spectrum"
        )
    experimental_quadrupole_metadata = build_experimental_quadrupole_metadata(
        reference_solution
    )
    if (
        spectrum_experimental_quadrupole_coupling_applied
        != experimental_quadrupole_metadata.applied
    ):
        raise SimulationServiceError(
            "experimental quadrupole application status is inconsistent between reference and spectrum"
        )

    geometric_cross_section_m2 = _geometric_cross_section_m2(diameters_m)
    return SimulationResult(
        input=simulation,
        cross_sections=_as_cross_sections_result(
            reference_cross_sections,
            wavelength_nm=simulation.light_source.wavelength_nm,
            geometric_cross_section_m2=geometric_cross_section_m2,
        ),
        spectrum=_spectrum_result(
            wavelength_nm=wavelength_grid_nm,
            c_ext_m2=c_ext_m2,
            c_sca_m2=c_sca_m2,
            c_abs_m2=c_abs_m2,
            geometric_cross_section_m2=geometric_cross_section_m2,
            smoothing_level=simulation.smoothing_level,
        ),
        qcm_metadata=qcm_metadata,
        experimental_quadrupole_metadata=experimental_quadrupole_metadata,
        provenance=ResultProvenance(
            model_name=(
                EXPERIMENTAL_QUADRUPOLE_MODEL_NAME
                if experimental_quadrupole_metadata.applied
                else MODEL_NAME
            ),
            material_data_source=MATERIAL_DATA_SOURCE,
            material_data_interpolation=MATERIAL_DATA_INTERPOLATION,
            software_version=SOFTWARE_VERSION,
        ),
        warnings=[
            ResultWarning(code=warning.code, parameters=warning.parameters)
            for warning in warnings
        ],
        smoothing_level=simulation.smoothing_level or SMOOTHING_DEFAULT_LEVEL,
    )


def _build_exact_mie_result(
    *,
    simulation: ExactMieSimulationInput,
    reference_spectrum: MieSpectrum,
    spectrum: MieSpectrum,
) -> SimulationResult:
    """完全Mie単一球モードの保存しない結果を組み立てる。"""
    reference_index = 0
    geometric_cross_section_m2 = float(
        np.pi * (float(nanometres_to_metres(simulation.particles[0].diameter_nm)) / 2.0)
        ** 2
    )
    return SimulationResult(
        input=simulation,
        cross_sections=CrossSectionsResult(
            wavelength_nm=simulation.light_source.wavelength_nm,
            c_ext_m2=float(reference_spectrum.c_ext_m2[reference_index]),
            c_sca_m2=float(reference_spectrum.c_sca_m2[reference_index]),
            c_abs_m2=float(reference_spectrum.c_abs_m2[reference_index]),
            geometric_cross_section_m2=geometric_cross_section_m2,
            q_ext=float(reference_spectrum.q_ext[reference_index]),
            q_sca=float(reference_spectrum.q_sca[reference_index]),
            q_abs=float(reference_spectrum.q_abs[reference_index]),
        ),
        spectrum=_spectrum_result(
            wavelength_nm=np.asarray(metres_to_nanometres(spectrum.wavelength_m)),
            c_ext_m2=spectrum.c_ext_m2,
            c_sca_m2=spectrum.c_sca_m2,
            c_abs_m2=spectrum.c_abs_m2,
            geometric_cross_section_m2=geometric_cross_section_m2,
            smoothing_level=simulation.smoothing_level,
        ),
        qcm_metadata=QcmResultMetadata(qcm_applied=False),
        experimental_quadrupole_metadata=ExperimentalQuadrupoleMetadata(applied=False),
        provenance=ResultProvenance(
            model_name=EXACT_SINGLE_SPHERE_MIE_MODEL_NAME,
            material_data_source=MATERIAL_DATA_SOURCE,
            material_data_interpolation=MATERIAL_DATA_INTERPOLATION,
            software_version=SOFTWARE_VERSION,
        ),
        warnings=[],
        smoothing_level=simulation.smoothing_level or SMOOTHING_DEFAULT_LEVEL,
    )


def _run_exact_mie_simulation(
    simulation: ExactMieSimulationInput,
    *,
    optical_constants: OpticalConstants,
    maximum_points: int,
    endpoint_name: str,
) -> SimulationResult:
    """同期エンドポイント用に単一球・全次数Mieスペクトルを計算する。"""
    diameter_m = float(nanometres_to_metres(simulation.particles[0].diameter_nm))
    wavelength_grid_nm = build_wavelength_grid_nm(
        simulation.spectrum,
        maximum_points=maximum_points,
        endpoint_name=endpoint_name,
    )
    try:
        reference_spectrum = calculate_exact_single_sphere_mie_spectrum(
            wavelengths_m=[nanometres_to_metres(simulation.light_source.wavelength_nm)],
            diameter_m=diameter_m,
            medium_refractive_index=simulation.medium.refractive_index,
            optical_constants=optical_constants,
        )
        spectrum = calculate_exact_single_sphere_mie_spectrum(
            wavelengths_m=nanometres_to_metres(wavelength_grid_nm),
            diameter_m=diameter_m,
            medium_refractive_index=simulation.medium.refractive_index,
            optical_constants=optical_constants,
        )
    except (MaterialDataError, ValueError, RuntimeError) as error:
        raise SimulationServiceError(str(error)) from error
    return _build_exact_mie_result(
        simulation=simulation,
        reference_spectrum=reference_spectrum,
        spectrum=spectrum,
    )


def _run_exact_mie_simulation_with_progress(
    simulation: ExactMieSimulationInput,
    *,
    optical_constants: OpticalConstants,
    cancellation_requested: Callable[[], bool],
    progress_callback: Callable[[int, int], None],
) -> SimulationResult:
    """Compute the exact single-sphere Mie spectrum point by point for SSE progress."""
    diameter_m = float(nanometres_to_metres(simulation.particles[0].diameter_nm))
    wavelength_grid_nm = build_wavelength_grid_nm(
        simulation.spectrum,
        maximum_points=MAX_STREAM_SPECTRUM_POINTS,
        endpoint_name="streaming API",
    )
    wavelength_grid_m = np.asarray(nanometres_to_metres(wavelength_grid_nm))
    total_points = len(wavelength_grid_m)
    c_ext_m2 = np.empty(total_points, dtype=np.float64)
    c_sca_m2 = np.empty(total_points, dtype=np.float64)
    c_abs_m2 = np.empty(total_points, dtype=np.float64)
    q_ext = np.empty(total_points, dtype=np.float64)
    q_sca = np.empty(total_points, dtype=np.float64)
    q_abs = np.empty(total_points, dtype=np.float64)

    try:
        for index, wavelength_m in enumerate(wavelength_grid_m):
            if cancellation_requested():
                raise SimulationCancelledError("simulation cancelled before a wavelength point")
            point = calculate_exact_single_sphere_mie_spectrum(
                wavelengths_m=np.asarray([wavelength_m]),
                diameter_m=diameter_m,
                medium_refractive_index=simulation.medium.refractive_index,
                optical_constants=optical_constants,
            )
            c_ext_m2[index] = point.c_ext_m2[0]
            c_sca_m2[index] = point.c_sca_m2[0]
            c_abs_m2[index] = point.c_abs_m2[0]
            q_ext[index] = point.q_ext[0]
            q_sca[index] = point.q_sca[0]
            q_abs[index] = point.q_abs[0]
            if cancellation_requested():
                raise SimulationCancelledError("simulation cancelled after a wavelength point")
            progress_callback(index + 1, total_points)

        if cancellation_requested():
            raise SimulationCancelledError("simulation cancelled before finalisation")
        reference_spectrum = calculate_exact_single_sphere_mie_spectrum(
            wavelengths_m=np.asarray(
                [nanometres_to_metres(simulation.light_source.wavelength_nm)]
            ),
            diameter_m=diameter_m,
            medium_refractive_index=simulation.medium.refractive_index,
            optical_constants=optical_constants,
        )
        if cancellation_requested():
            raise SimulationCancelledError("simulation cancelled before returning a result")
    except (MaterialDataError, ValueError, RuntimeError) as error:
        raise SimulationServiceError(str(error)) from error

    return _build_exact_mie_result(
        simulation=simulation,
        reference_spectrum=reference_spectrum,
        spectrum=MieSpectrum(
            wavelength_m=wavelength_grid_m,
            c_ext_m2=c_ext_m2,
            c_sca_m2=c_sca_m2,
            c_abs_m2=c_abs_m2,
            q_ext=q_ext,
            q_sca=q_sca,
            q_abs=q_abs,
        ),
    )


def _common_cda_arguments(
    *,
    simulation: SimulationInput,
    positions_m: np.ndarray,
    diameters_m: np.ndarray,
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
) -> dict[str, object]:
    """同一配置の波長走査に渡すCDA引数を一箇所で構成する。"""
    return {
        "positions_m": positions_m,
        "diameters_m": diameters_m,
        "medium_refractive_index": simulation.medium.refractive_index,
        "propagation_direction": simulation.light_source.propagation_direction,
        "polarization": simulation.light_source.polarization,
        "optical_constants": optical_constants,
        "qcm_parameter_table": qcm_parameter_table,
        "apply_experimental_quadrupole_coupling": (
            simulation.experimental_quadrupole_coupling
        ),
    }


def run_simulation(
    simulation: SimulationRequest,
    *,
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
) -> SimulationResult:
    """一回の同期計算を行い、結果を永続化せずにメモリ上で返す。"""
    if isinstance(simulation, ExactMieSimulationInput):
        return _run_exact_mie_simulation(
            simulation,
            optical_constants=optical_constants,
            maximum_points=MAX_SYNCHRONOUS_SPECTRUM_POINTS,
            endpoint_name="synchronous API",
        )
    if len(simulation.particles) > MAX_SYNCHRONOUS_CDA_PARTICLES:
        raise SimulationRequiresStreamingError(
            "CDA calculations with more than 20 particles require the streaming API",
            parameters={
                "particle_count": len(simulation.particles),
                "maximum_synchronous_particles": MAX_SYNCHRONOUS_CDA_PARTICLES,
            },
        )
    positions_m = _as_positions_m(simulation)
    diameters_m = _as_diameters_m(simulation)
    reference_wavelength_m = nanometres_to_metres(
        simulation.light_source.wavelength_nm
    )
    wavelength_grid_nm = build_wavelength_grid_nm(
        simulation.spectrum,
        maximum_points=MAX_SYNCHRONOUS_SPECTRUM_POINTS,
        endpoint_name="synchronous API",
    )
    wavelength_grid_m = nanometres_to_metres(wavelength_grid_nm)

    common_arguments = _common_cda_arguments(
        simulation=simulation,
        positions_m=positions_m,
        diameters_m=diameters_m,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    try:
        reference_solution = solve_cda(
            wavelength_m=reference_wavelength_m,
            **common_arguments,
        )
        reference_cross_sections = calculate_cda_cross_sections(reference_solution)
        spectrum = calculate_cda_spectrum(
            wavelengths_m=wavelength_grid_m,
            **common_arguments,
        )
    except (CdaConfigurationError, CdaError, MaterialDataError, QcmParameterError) as error:
        raise SimulationServiceError(str(error)) from error

    return _build_simulation_result(
        simulation=simulation,
        diameters_m=diameters_m,
        reference_cross_sections=reference_cross_sections,
        reference_solution=reference_solution,
        wavelength_grid_nm=np.asarray(
            metres_to_nanometres(spectrum.wavelength_m), dtype=np.float64
        ),
        c_ext_m2=spectrum.c_ext_m2,
        c_sca_m2=spectrum.c_sca_m2,
        c_abs_m2=spectrum.c_abs_m2,
        warnings=spectrum.warnings,
        spectrum_qcm_applied=spectrum.qcm_applied,
        spectrum_experimental_quadrupole_coupling_applied=(
            spectrum.experimental_quadrupole_coupling_applied
        ),
    )


def run_simulation_with_progress(
    simulation: SimulationRequest,
    *,
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
    cancellation_requested: Callable[[], bool],
    progress_callback: Callable[[int, int], None],
) -> SimulationResult:
    """波長点境界で取消を確認しながら、完了結果だけを返す。

    この関数は部分スペクトルを返さない。呼出し側は ``progress_callback`` へ点数だけを
    送り、取消時には局所配列を破棄して ``SimulationCancelledError`` を受け取る。
    """
    if isinstance(simulation, ExactMieSimulationInput):
        return _run_exact_mie_simulation_with_progress(
            simulation,
            optical_constants=optical_constants,
            cancellation_requested=cancellation_requested,
            progress_callback=progress_callback,
        )
    positions_m = _as_positions_m(simulation)
    diameters_m = _as_diameters_m(simulation)
    wavelength_grid_nm = build_wavelength_grid_nm(
        simulation.spectrum,
        maximum_points=MAX_STREAM_SPECTRUM_POINTS,
        endpoint_name="streaming API",
    )
    wavelength_grid_m = np.asarray(nanometres_to_metres(wavelength_grid_nm))
    common_arguments = _common_cda_arguments(
        simulation=simulation,
        positions_m=positions_m,
        diameters_m=diameters_m,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    total_points = len(wavelength_grid_m)
    c_ext_m2 = np.empty(total_points, dtype=np.float64)
    c_sca_m2 = np.empty(total_points, dtype=np.float64)
    c_abs_m2 = np.empty(total_points, dtype=np.float64)
    warnings: tuple[CdaWarning, ...] | None = None
    qcm_applied: bool | None = None

    try:
        for index, wavelength_m in enumerate(wavelength_grid_m):
            if cancellation_requested():
                raise SimulationCancelledError("simulation cancelled before a wavelength point")
            solution = solve_cda(wavelength_m=float(wavelength_m), **common_arguments)
            cross_sections = calculate_cda_cross_sections(solution)
            c_ext_m2[index] = cross_sections.c_ext_m2
            c_sca_m2[index] = cross_sections.c_sca_m2
            c_abs_m2[index] = cross_sections.c_abs_m2
            if warnings is None:
                warnings = solution.warnings
                qcm_applied = solution.qcm_applied
            if cancellation_requested():
                raise SimulationCancelledError("simulation cancelled after a wavelength point")
            progress_callback(index + 1, total_points)

        if cancellation_requested():
            raise SimulationCancelledError("simulation cancelled before finalisation")
        reference_solution = solve_cda(
            wavelength_m=float(nanometres_to_metres(simulation.light_source.wavelength_nm)),
            **common_arguments,
        )
        reference_cross_sections = calculate_cda_cross_sections(reference_solution)
        if cancellation_requested():
            raise SimulationCancelledError("simulation cancelled before returning a result")
    except (CdaConfigurationError, CdaError, MaterialDataError, QcmParameterError) as error:
        raise SimulationServiceError(str(error)) from error

    return _build_simulation_result(
        simulation=simulation,
        diameters_m=diameters_m,
        reference_cross_sections=reference_cross_sections,
        reference_solution=reference_solution,
        wavelength_grid_nm=wavelength_grid_nm,
        c_ext_m2=c_ext_m2,
        c_sca_m2=c_sca_m2,
        c_abs_m2=c_abs_m2,
        warnings=warnings or (),
        spectrum_qcm_applied=bool(qcm_applied),
        spectrum_experimental_quadrupole_coupling_applied=(
            simulation.experimental_quadrupole_coupling
        ),
    )
