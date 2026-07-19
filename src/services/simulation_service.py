"""検証済み入力をCDA/QCM計算へ接続し、保存しない応答データを組み立てる。"""

from __future__ import annotations

import math

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
)
from src.physics.material_data import MaterialDataError, OpticalConstants
from src.physics.qcm import GammaGParameterTable, QcmParameterError
from src.schemas.result import (
    CrossSectionsResult,
    QcmResultMetadata,
    SimulationResult,
    SpectrumResult,
)
from src.schemas.simulation import SimulationInput, SpectrumRangeInput


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


class SimulationServiceError(RuntimeError):
    """APIへ明示的なエラー応答を返すためのサービス層例外。"""

    status_code = 422
    error_code = "simulation_failed"


class QcmMetadataUnavailableError(SimulationServiceError):
    """QCM結果へ必須の出典情報を付与できないことを示す。"""

    status_code = 503
    error_code = "qcm_metadata_unavailable"


def build_wavelength_grid_nm(spectrum: SpectrumRangeInput) -> np.ndarray:
    """入力範囲を含む、上限検証済みの真空波長格子をnmで返す。"""
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
) -> CrossSectionsResult:
    return CrossSectionsResult(
        wavelength_nm=wavelength_nm,
        c_ext_m2=cross_sections.c_ext_m2,
        c_sca_m2=cross_sections.c_sca_m2,
        c_abs_m2=cross_sections.c_abs_m2,
    )


def run_simulation(
    simulation: SimulationInput,
    *,
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
) -> SimulationResult:
    """一回の同期計算を行い、結果を永続化せずにメモリ上で返す。"""
    positions_m = _as_positions_m(simulation)
    diameters_m = _as_diameters_m(simulation)
    reference_wavelength_m = nanometres_to_metres(
        simulation.light_source.wavelength_nm
    )
    wavelength_grid_nm = build_wavelength_grid_nm(simulation.spectrum)
    wavelength_grid_m = nanometres_to_metres(wavelength_grid_nm)

    common_arguments = {
        "positions_m": positions_m,
        "diameters_m": diameters_m,
        "medium_refractive_index": simulation.medium.refractive_index,
        "propagation_direction": simulation.light_source.propagation_direction,
        "polarization": simulation.light_source.polarization,
        "optical_constants": optical_constants,
        "qcm_parameter_table": qcm_parameter_table,
    }
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

    qcm_metadata = build_qcm_result_metadata(reference_solution)
    if spectrum.qcm_applied != qcm_metadata.qcm_applied:
        raise SimulationServiceError(
            "QCM application status is inconsistent between reference and spectrum"
        )

    return SimulationResult(
        input=simulation,
        cross_sections=_as_cross_sections_result(
            reference_cross_sections,
            wavelength_nm=simulation.light_source.wavelength_nm,
        ),
        spectrum=SpectrumResult(
            wavelength_nm=[
                float(value)
                for value in metres_to_nanometres(spectrum.wavelength_m)
            ],
            c_ext_m2=[float(value) for value in spectrum.c_ext_m2],
            c_sca_m2=[float(value) for value in spectrum.c_sca_m2],
            c_abs_m2=[float(value) for value in spectrum.c_abs_m2],
        ),
        qcm_metadata=qcm_metadata,
        warnings=list(spectrum.warnings),
    )
