"""Validation Test 4: QCM環状層のCDA補助双極子への統合。"""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from src.io.qcm_parameter_table import load_gamma_g_au_digitized
from src.physics.cda_solver import (
    CdaConfigurationError,
    CdaCrossSections,
    CdaSolution,
    calculate_cda_cross_sections,
    calculate_cda_spectrum,
    phase_correct_induced_dipoles,
    solve_cda,
)
from src.physics.material_data import OpticalConstants, load_au_optical_constants
from src.physics.qcm import GammaGParameterTable
from src.schemas.result import QcmResultMetadata


DIAMETER_M = 20.0e-9
MEDIUM_REFRACTIVE_INDEX = 1.33
WAVELENGTH_M = 600.0e-9
PROPAGATION_DIRECTION = (0.0, 0.0, 1.0)
POLARIZATION = (1.0, 0.0, 0.0)
LAYER_CONVERGENCE_WAVELENGTHS_M = np.arange(520.0, 701.0, 10.0) * 1.0e-9


@pytest.fixture(scope="module")
def optical_constants() -> OpticalConstants:
    return load_au_optical_constants()


@pytest.fixture(scope="module")
def qcm_parameter_table() -> GammaGParameterTable:
    return load_gamma_g_au_digitized()


def _qcm_dimer_solution(
    *,
    gap_nm: float,
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
    apply_qcm: bool | None = None,
    qcm_layer_count: int = 4,
    wavelength_m: float = WAVELENGTH_M,
) -> CdaSolution:
    center_distance_m = DIAMETER_M + gap_nm * 1.0e-9
    return solve_cda(
        positions_m=np.array(
            [
                [-center_distance_m / 2.0, 0.0, 0.0],
                [center_distance_m / 2.0, 0.0, 0.0],
            ]
        ),
        diameters_m=np.array([DIAMETER_M, DIAMETER_M]),
        wavelength_m=wavelength_m,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
        apply_qcm=apply_qcm,
        qcm_layer_count=qcm_layer_count,
    )


@pytest.mark.parametrize("gap_nm", (0.5, 0.7, 0.9))
def test_qcm_auto_application_is_finite_for_subnanometre_gaps(
    gap_nm: float,
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
) -> None:
    """0.5、0.7、0.9 nmではQCM経路を選び、NaN/Infを返さない。"""
    solution = _qcm_dimer_solution(
        gap_nm=gap_nm,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    cross_sections = calculate_cda_cross_sections(solution)

    assert solution.qcm_applied
    assert solution.qcm_layer_count == 4
    assert solution.qcm_plasma_energy_ev == pytest.approx(7.9)
    assert solution.qcm_bulk_damping_energy_ev == pytest.approx(0.09)
    assert np.all(np.isfinite(solution.interaction_induced_dipoles_c_m))
    assert np.all(np.isfinite(solution.interaction_polarizabilities_si))
    assert math.isfinite(solution.condition_number)
    assert all(
        math.isfinite(value)
        for value in (
            cross_sections.c_ext_m2,
            cross_sections.c_sca_m2,
            cross_sections.c_abs_m2,
        )
    )
    if gap_nm == 0.5:
        assert solution.qcm_bridge_count == 1
        assert solution.qcm_classical_limit_pair_count == 0
        assert solution.qcm_max_relative_permittivity_contrast is not None
        assert solution.qcm_max_relative_permittivity_contrast > 0.0
    else:
        assert solution.qcm_bridge_count == 0
        assert solution.qcm_classical_limit_pair_count == 1


@pytest.mark.parametrize("gap_nm", (0.5, 0.7, 0.9))
def test_qcm_does_not_strengthen_longitudinal_particle_coupling(
    gap_nm: float,
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
) -> None:
    """検証用off/on比較で、QCMは粒子双極子の結合を増強しない。"""
    qcm_solution = _qcm_dimer_solution(
        gap_nm=gap_nm,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    classical_solution = _qcm_dimer_solution(
        gap_nm=gap_nm,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
        apply_qcm=False,
    )
    qcm_dipole_norm = float(np.linalg.norm(phase_correct_induced_dipoles(qcm_solution)))
    classical_dipole_norm = float(
        np.linalg.norm(phase_correct_induced_dipoles(classical_solution))
    )

    # Extinctionはブリッジの散逸で増え得るため、結合の直接指標として粒子双極子を使う。
    # 0.544 nm超は表の方針どおり古典極限となり、両者の一致は「飽和」を表す。
    assert qcm_dipole_norm <= classical_dipole_norm * (1.0 + 1.0e-12)


def _cross_section_array(cross_sections: CdaCrossSections) -> np.ndarray:
    return np.asarray(
        (
            cross_sections.c_ext_m2,
            cross_sections.c_sca_m2,
            cross_sections.c_abs_m2,
        ),
        dtype=np.float64,
    )


def test_qcm_correction_vanishes_smoothly_at_digitized_upper_limit(
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
) -> None:
    """5.439 Å境界では、補正量がゼロへ近付き、上側で外挿しない。"""
    below_limit_qcm = _qcm_dimer_solution(
        gap_nm=0.5439,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    below_limit_classical = _qcm_dimer_solution(
        gap_nm=0.5439,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
        apply_qcm=False,
    )
    above_limit_qcm = _qcm_dimer_solution(
        gap_nm=0.5440,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    above_limit_classical = _qcm_dimer_solution(
        gap_nm=0.5440,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
        apply_qcm=False,
    )
    below_difference = np.max(
        np.abs(
            _cross_section_array(calculate_cda_cross_sections(below_limit_qcm))
            - _cross_section_array(calculate_cda_cross_sections(below_limit_classical))
        )
        / np.maximum(
            np.abs(_cross_section_array(calculate_cda_cross_sections(below_limit_classical))),
            1.0e-300,
        )
    )
    above_difference = _cross_section_array(
        calculate_cda_cross_sections(above_limit_qcm)
    ) - _cross_section_array(calculate_cda_cross_sections(above_limit_classical))

    # 最終表点の大きなgamma_gにより補正が既に十分小さいことを数値的に確認する。
    assert below_difference < 1.0e-6
    np.testing.assert_allclose(above_difference, 0.0, atol=1.0e-30)


@pytest.mark.parametrize("gap_nm", (0.5, 0.7, 0.9))
def test_qcm_four_layers_pass_the_internal_three_to_five_layer_check(
    gap_nm: float,
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
) -> None:
    """D-3の0.5、0.7、0.9 nmにおける4層内部感度を確認する。"""
    center_distance_m = DIAMETER_M + gap_nm * 1.0e-9
    common = dict(
        wavelengths_m=LAYER_CONVERGENCE_WAVELENGTHS_M,
        positions_m=np.array(
            [
                [-center_distance_m / 2.0, 0.0, 0.0],
                [center_distance_m / 2.0, 0.0, 0.0],
            ]
        ),
        diameters_m=np.array([DIAMETER_M, DIAMETER_M]),
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    spectra = {
        layer_count: calculate_cda_spectrum(**common, qcm_layer_count=layer_count)
        for layer_count in (3, 4, 5)
    }
    for first_count, second_count in ((3, 4), (4, 5)):
        for first_values, second_values in zip(
            (
                spectra[first_count].c_ext_m2,
                spectra[first_count].c_sca_m2,
                spectra[first_count].c_abs_m2,
            ),
            (
                spectra[second_count].c_ext_m2,
                spectra[second_count].c_sca_m2,
                spectra[second_count].c_abs_m2,
            ),
            strict=True,
        ):
            first_peak = float(np.max(first_values))
            second_peak = float(np.max(second_values))
            normalized_difference = np.max(
                np.abs(first_values / first_peak - second_values / second_peak)
            )
            peak_height_difference = abs(first_peak - second_peak) / second_peak
            peak_position_difference_m = abs(
                LAYER_CONVERGENCE_WAVELENGTHS_M[int(np.argmax(first_values))]
                - LAYER_CONVERGENCE_WAVELENGTHS_M[int(np.argmax(second_values))]
            )
            assert normalized_difference <= 1.0e-2
            assert peak_height_difference <= 1.0e-2
            assert peak_position_difference_m <= 10.0e-9


def test_qcm_metadata_schema_requires_provisional_provenance() -> None:
    """QCM結果には出典・校正状況・読取誤差・図と曲線を必須化する。"""
    metadata = QcmResultMetadata(
        qcm_applied=True,
        qcm_parameter_status="provisional_digitized",
        qcm_parameter_source="Esteban et al. (2012), DOI: 10.1038/ncomms1806",
        qcm_calibration_points="not provided with the digitized data",
        qcm_reading_uncertainty="approximately 5-10%",
        qcm_figure="Fig. 2d",
        qcm_curve="Au jellium, blue solid line",
        qcm_interpolation="shape-preserving PCHIP of log(gamma_g)",
        qcm_layer_count=4,
        qcm_plasma_energy_ev=7.9,
        qcm_bulk_damping_energy_ev=0.09,
        qcm_cda_model="volume-equivalent auxiliary bridge dipole",
        qcm_model_error_estimate="3/4/5-layer sensitivity; model-form error unbounded",
    )
    assert metadata.qcm_parameter_status == "provisional_digitized"
    with pytest.raises(ValidationError, match="qcm_calibration_points"):
        QcmResultMetadata(
            qcm_applied=True,
            qcm_parameter_status="provisional_digitized",
        )


def test_cda_keeps_the_half_nanometre_lower_limit(
    optical_constants: OpticalConstants,
    qcm_parameter_table: GammaGParameterTable,
) -> None:
    """QCMを統合してもgap < 0.5 nmは拒否する。"""
    with pytest.raises(CdaConfigurationError, match="below the 0.5 nm model limit"):
        _qcm_dimer_solution(
            gap_nm=0.3,
            optical_constants=optical_constants,
            qcm_parameter_table=qcm_parameter_table,
        )
