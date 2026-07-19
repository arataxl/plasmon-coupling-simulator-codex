"""Validation Test 2: CDA の孤立極限と剛体変換不変性。"""

from __future__ import annotations

import numpy as np
import pytest

from src.physics.cda_solver import (
    CdaIllConditionedMatrixError,
    CdaCrossSections,
    calculate_cda_cross_sections,
    phase_correct_induced_dipoles,
    solve_cda,
)
from src.physics.material_data import OpticalConstants, load_au_optical_constants
from src.physics.polarizability import calculate_fcda_polarizability


ACCEPTANCE_RTOL = 1.0e-4
DIAMETER_M = 20.0e-9
WAVELENGTH_M = 600.0e-9
MEDIUM_REFRACTIVE_INDEX = 1.33
PROPAGATION_DIRECTION = (0.0, 0.0, 1.0)
POLARIZATION = (1.0, 0.0, 0.0)


@pytest.fixture(scope="module")
def optical_constants() -> OpticalConstants:
    return load_au_optical_constants()


def _single_solution(optical_constants: OpticalConstants):
    return solve_cda(
        positions_m=np.array([[0.0, 0.0, 0.0]]),
        diameters_m=np.array([DIAMETER_M]),
        wavelength_m=WAVELENGTH_M,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
    )


def _dimer_solution(*, gap_m: float, optical_constants: OpticalConstants):
    center_distance_m = DIAMETER_M + gap_m
    return solve_cda(
        positions_m=np.array(
            [
                [-center_distance_m / 2.0, 0.0, 0.0],
                [center_distance_m / 2.0, 0.0, 0.0],
            ]
        ),
        diameters_m=np.array([DIAMETER_M, DIAMETER_M]),
        wavelength_m=WAVELENGTH_M,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
    )


def _cross_section_relative_errors(
    dimer: CdaCrossSections, single: CdaCrossSections
) -> np.ndarray:
    return np.asarray(
        [
            abs(dimer.c_ext_m2 - 2.0 * single.c_ext_m2)
            / abs(2.0 * single.c_ext_m2),
            abs(dimer.c_sca_m2 - 2.0 * single.c_sca_m2)
            / abs(2.0 * single.c_sca_m2),
            abs(dimer.c_abs_m2 - 2.0 * single.c_abs_m2)
            / abs(2.0 * single.c_abs_m2),
        ],
        dtype=np.float64,
    )


def test_fcda_maps_a1_to_dipole_cross_sections_and_defaults_to_bulk_data(
    optical_constants: OpticalConstants,
) -> None:
    """FCDAのSI写像と、Kreibig補正が既定OFFであることを確認する。"""
    polarizability = calculate_fcda_polarizability(
        wavelength_m=WAVELENGTH_M,
        diameter_m=DIAMETER_M,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        optical_constants=optical_constants,
    )
    assert not polarizability.kreibig_correction_applied
    expected_extinction_m2 = (
        6.0
        * np.pi
        * polarizability.electric_dipole_mie_coefficient.real
        / polarizability.wave_number_m_inv**2
    )
    expected_scattering_m2 = (
        6.0
        * np.pi
        * abs(polarizability.electric_dipole_mie_coefficient) ** 2
        / polarizability.wave_number_m_inv**2
    )
    cross_sections = calculate_cda_cross_sections(_single_solution(optical_constants))
    np.testing.assert_allclose(
        (cross_sections.c_ext_m2, cross_sections.c_sca_m2),
        (expected_extinction_m2, expected_scattering_m2),
        rtol=1.0e-12,
    )
    with pytest.raises(ValueError, match="kreibig_parameters"):
        calculate_fcda_polarizability(
            wavelength_m=WAVELENGTH_M,
            diameter_m=DIAMETER_M,
            medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
            optical_constants=optical_constants,
            apply_kreibig_correction=True,
        )


def test_dimer_approaches_twice_the_isolated_response(
    optical_constants: OpticalConstants,
) -> None:
    """D-5に従い、距離倍増後の断面積・位相補正双極子を rtol=1e-4 で判定する。"""
    single_solution = _single_solution(optical_constants)
    single_cross_sections = calculate_cda_cross_sections(single_solution)
    isolated_dipole = phase_correct_induced_dipoles(single_solution)[0]

    cross_section_errors: list[np.ndarray] = []
    dipole_errors: list[float] = []
    for gap_nm in (1000.0, 2000.0, 4000.0, 8000.0):
        dimer_solution = _dimer_solution(
            gap_m=gap_nm * 1e-9,
            optical_constants=optical_constants,
        )
        dimer_cross_sections = calculate_cda_cross_sections(dimer_solution)
        cross_section_errors.append(
            _cross_section_relative_errors(dimer_cross_sections, single_cross_sections)
        )
        phase_corrected_dipoles = phase_correct_induced_dipoles(dimer_solution)
        dipole_errors.append(
            float(
                np.max(
                    np.linalg.norm(phase_corrected_dipoles - isolated_dipole, axis=1)
                    / np.linalg.norm(isolated_dipole)
                )
            )
        )

    # 遅延 Green tensor の位相により各倍増ごとの誤差単調減少は要求しない。
    # D-5 の判定どおり、十分遠い最終距離で孤立極限へ収束することを確認する。
    assert np.all(cross_section_errors[-1] <= ACCEPTANCE_RTOL)
    assert dipole_errors[-1] <= ACCEPTANCE_RTOL
    assert np.all(cross_section_errors[-1] < cross_section_errors[0])
    assert dipole_errors[-1] < dipole_errors[0]


def test_cda_is_invariant_to_translation_and_particle_order(
    optical_constants: OpticalConstants,
) -> None:
    """座標原点の移動と粒子順序の入れ替えが物理結果を変えないことを確認する。"""
    base_solution = _dimer_solution(
        gap_m=8000.0e-9,
        optical_constants=optical_constants,
    )
    base_cross_sections = calculate_cda_cross_sections(base_solution)

    translation_m = np.array([350.0e-9, -210.0e-9, 125.0e-9])
    translated_solution = solve_cda(
        positions_m=base_solution.positions_m + translation_m,
        diameters_m=base_solution.diameters_m,
        wavelength_m=WAVELENGTH_M,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
    )
    reordered_solution = solve_cda(
        positions_m=base_solution.positions_m[::-1],
        diameters_m=base_solution.diameters_m[::-1],
        wavelength_m=WAVELENGTH_M,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
    )

    for transformed_cross_sections in (
        calculate_cda_cross_sections(translated_solution),
        calculate_cda_cross_sections(reordered_solution),
    ):
        np.testing.assert_allclose(
            (
                transformed_cross_sections.c_ext_m2,
                transformed_cross_sections.c_sca_m2,
                transformed_cross_sections.c_abs_m2,
            ),
            (
                base_cross_sections.c_ext_m2,
                base_cross_sections.c_sca_m2,
                base_cross_sections.c_abs_m2,
            ),
            rtol=ACCEPTANCE_RTOL,
        )

    base_dipoles = phase_correct_induced_dipoles(base_solution)
    np.testing.assert_allclose(
        phase_correct_induced_dipoles(translated_solution),
        base_dipoles,
        rtol=ACCEPTANCE_RTOL,
        atol=np.linalg.norm(base_dipoles) * 1.0e-12,
    )
    np.testing.assert_allclose(
        phase_correct_induced_dipoles(reordered_solution)[::-1],
        base_dipoles,
        rtol=ACCEPTANCE_RTOL,
        atol=np.linalg.norm(base_dipoles) * 1.0e-12,
    )


def test_cda_rejects_an_ill_conditioned_matrix(
    optical_constants: OpticalConstants,
) -> None:
    """構成可能な条件数上限を超える行列を、解く前に明示的に拒否する。"""
    with pytest.raises(CdaIllConditionedMatrixError, match="ill-conditioned"):
        solve_cda(
            positions_m=np.array([[-11.0e-9, 0.0, 0.0], [11.0e-9, 0.0, 0.0]]),
            diameters_m=np.array([DIAMETER_M, DIAMETER_M]),
            wavelength_m=WAVELENGTH_M,
            medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
            propagation_direction=PROPAGATION_DIRECTION,
            polarization=POLARIZATION,
            optical_constants=optical_constants,
            max_condition_number=1.1,
        )
