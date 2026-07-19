"""Validation Test 5: QCM領域外における多粒子CDAの数値安定性。"""

from __future__ import annotations

import numpy as np
import pytest

from src.physics.cda_solver import (
    CDA_WARNING_UP_TO_GAP_M,
    DEFAULT_MAX_CONDITION_NUMBER,
    CdaCrossSections,
    CdaSolution,
    calculate_cda_cross_sections,
    solve_cda,
)
from src.physics.material_data import OpticalConstants, load_au_optical_constants


MEDIUM_REFRACTIVE_INDEX = 1.33
WAVELENGTH_M = 600.0e-9
PROPAGATION_DIRECTION = (0.0, 0.0, 1.0)
POLARIZATION = (1.0, 0.0, 0.0)
PARTICLE_COUNTS_AND_SEEDS = (
    (3, 2026071903),
    (3, 2026072903),
    (5, 2026071905),
    (5, 2026072905),
    (10, 2026071910),
    (10, 2026072910),
    (20, 2026071920),
    (20, 2026072920),
)
DIAMETER_CHOICES_M = np.array((12.0, 16.0, 20.0, 24.0, 28.0)) * 1.0e-9
PLACEMENT_HALF_WIDTH_M = 150.0e-9
MAX_PLACEMENT_ATTEMPTS = 10_000


@pytest.fixture(scope="module")
def optical_constants() -> OpticalConstants:
    return load_au_optical_constants()


def _minimum_surface_gap_m(positions_m: np.ndarray, diameters_m: np.ndarray) -> float:
    minimum_gap_m = float("inf")
    for left_index in range(len(positions_m)):
        for right_index in range(left_index + 1, len(positions_m)):
            center_distance_m = float(
                np.linalg.norm(positions_m[left_index] - positions_m[right_index])
            )
            surface_gap_m = center_distance_m - (
                diameters_m[left_index] + diameters_m[right_index]
            ) / 2.0
            minimum_gap_m = min(minimum_gap_m, surface_gap_m)
    return minimum_gap_m


def _generate_random_configuration(
    *, particle_count: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """指定seedで、5 nm超の表面間ギャップを持つ混合粒径配置を生成する。"""
    random_generator = np.random.default_rng(seed)
    diameters_m = np.resize(DIAMETER_CHOICES_M, particle_count).copy()
    random_generator.shuffle(diameters_m)

    positions_m = np.empty((particle_count, 3), dtype=np.float64)
    for particle_index, diameter_m in enumerate(diameters_m):
        for _ in range(MAX_PLACEMENT_ATTEMPTS):
            candidate_position_m = random_generator.uniform(
                low=-PLACEMENT_HALF_WIDTH_M,
                high=PLACEMENT_HALF_WIDTH_M,
                size=3,
            )
            if all(
                np.linalg.norm(candidate_position_m - positions_m[other_index])
                - (diameter_m + diameters_m[other_index]) / 2.0
                > CDA_WARNING_UP_TO_GAP_M
                for other_index in range(particle_index)
            ):
                positions_m[particle_index] = candidate_position_m
                break
        else:
            raise RuntimeError("could not generate a CDA-safe random configuration")

    return positions_m, diameters_m


def _solve_configuration(
    *, positions_m: np.ndarray, diameters_m: np.ndarray, optical_constants: OpticalConstants
) -> CdaSolution:
    return solve_cda(
        positions_m=positions_m,
        diameters_m=diameters_m,
        wavelength_m=WAVELENGTH_M,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
        max_condition_number=DEFAULT_MAX_CONDITION_NUMBER,
    )


def _as_cross_section_array(cross_sections: CdaCrossSections) -> np.ndarray:
    return np.asarray(
        (
            cross_sections.c_ext_m2,
            cross_sections.c_sca_m2,
            cross_sections.c_abs_m2,
        ),
        dtype=np.float64,
    )


@pytest.mark.parametrize(("particle_count", "seed"), PARTICLE_COUNTS_AND_SEEDS)
def test_multiparticle_cda_is_stable_reproducible_and_order_invariant(
    particle_count: int,
    seed: int,
    optical_constants: OpticalConstants,
) -> None:
    """Test 5の粒子数・有限値・再現性・粒子順序不変性を検証する。"""
    positions_m, diameters_m = _generate_random_configuration(
        particle_count=particle_count,
        seed=seed,
    )
    repeated_positions_m, repeated_diameters_m = _generate_random_configuration(
        particle_count=particle_count,
        seed=seed,
    )

    np.testing.assert_array_equal(repeated_positions_m, positions_m)
    np.testing.assert_array_equal(repeated_diameters_m, diameters_m)
    assert np.unique(diameters_m).size > 1
    assert _minimum_surface_gap_m(positions_m, diameters_m) > CDA_WARNING_UP_TO_GAP_M

    base_solution = _solve_configuration(
        positions_m=positions_m,
        diameters_m=diameters_m,
        optical_constants=optical_constants,
    )
    repeated_solution = _solve_configuration(
        positions_m=repeated_positions_m,
        diameters_m=repeated_diameters_m,
        optical_constants=optical_constants,
    )
    reordered_solution = _solve_configuration(
        positions_m=positions_m[::-1],
        diameters_m=diameters_m[::-1],
        optical_constants=optical_constants,
    )

    base_cross_sections = _as_cross_section_array(
        calculate_cda_cross_sections(base_solution)
    )
    repeated_cross_sections = _as_cross_section_array(
        calculate_cda_cross_sections(repeated_solution)
    )
    reordered_cross_sections = _as_cross_section_array(
        calculate_cda_cross_sections(reordered_solution)
    )

    for solution, cross_sections in (
        (base_solution, base_cross_sections),
        (repeated_solution, repeated_cross_sections),
        (reordered_solution, reordered_cross_sections),
    ):
        assert np.all(np.isfinite(solution.induced_dipoles_c_m))
        assert np.all(np.isfinite(solution.polarizabilities_si))
        assert np.isfinite(solution.condition_number)
        assert np.isfinite(solution.relative_residual)
        assert solution.condition_number <= DEFAULT_MAX_CONDITION_NUMBER
        assert np.all(np.isfinite(cross_sections))
        assert not solution.warnings

    np.testing.assert_allclose(repeated_cross_sections, base_cross_sections, rtol=0.0)
    np.testing.assert_allclose(
        reordered_cross_sections,
        base_cross_sections,
        rtol=1.0e-12,
    )
