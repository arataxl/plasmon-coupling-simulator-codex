"""UIプリセット表示専用の座標丸めを検証する。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.services.particle_layouts import (
    ParticleLayoutError,
    generate_random_nonoverlapping_configuration,
    recommended_placement_half_width_m,
    round_layout_coordinates_for_display,
)


def _surface_gap_nm(positions_nm: np.ndarray, diameters_nm: np.ndarray) -> float:
    return float(
        np.linalg.norm(positions_nm[1] - positions_nm[0])
        - (diameters_nm[0] + diameters_nm[1]) / 2.0
    )


def _all_surface_gaps_nm(positions_nm: np.ndarray, diameters_nm: np.ndarray) -> list[float]:
    return [
        float(
            np.linalg.norm(positions_nm[right] - positions_nm[left])
            - (diameters_nm[left] + diameters_nm[right]) / 2.0
        )
        for left in range(len(positions_nm))
        for right in range(left + 1, len(positions_nm))
    ]


def test_display_rounding_repairs_a_safe_layout_that_nearest_rounding_would_overlap() -> None:
    """0.1 nm丸め後も、0.5 nm未満へ偶発的に入らない。"""
    positions_nm = np.asarray(((0.0, 0.0, 0.0), (20.449, 1.64, 0.0)))
    diameters_nm = np.asarray((20.0, 20.0))

    raw_gap_nm = _surface_gap_nm(positions_nm, diameters_nm)
    rounded_positions_nm = (
        round_layout_coordinates_for_display(
            positions_m=positions_nm * 1.0e-9,
            diameters_m=diameters_nm * 1.0e-9,
        )
        / 1.0e-9
    )

    assert raw_gap_nm > 0.5
    assert np.allclose(rounded_positions_nm * 10.0, np.rint(rounded_positions_nm * 10.0))
    assert _surface_gap_nm(rounded_positions_nm, diameters_nm) >= 0.5


@pytest.mark.parametrize(
    ("raw_center_distance_nm", "qcm_expected"),
    ((20.54, True), (20.96, False)),
)
def test_display_rounding_keeps_the_0_5_and_1_0_nm_boundaries_explicit(
    raw_center_distance_nm: float,
    qcm_expected: bool,
) -> None:
    """丸めで0.5/1.0 nm境界をまたぐ場合も、表示値の区分を安全に確定する。"""
    positions_nm = np.asarray(
        ((0.0, 0.0, 0.0), (raw_center_distance_nm, 0.0, 0.0))
    )
    diameters_nm = np.asarray((20.0, 20.0))

    rounded_positions_nm = (
        round_layout_coordinates_for_display(
            positions_m=positions_nm * 1.0e-9,
            diameters_m=diameters_nm * 1.0e-9,
        )
        / 1.0e-9
    )
    rounded_gap_nm = _surface_gap_nm(rounded_positions_nm, diameters_nm)

    assert rounded_gap_nm >= 0.5
    assert math.isclose(rounded_gap_nm, 0.5 if qcm_expected else 1.0, abs_tol=1.0e-12)
    assert (0.5 <= rounded_gap_nm < 1.0) is qcm_expected


def test_grid_random_cluster_keeps_every_pair_within_requested_gap_range() -> None:
    """UI用の0.1 nm格子配置でも、全粒子対が最小・最大ギャップを守る。"""
    minimum_gap_nm = 5.0
    maximum_gap_nm = 250.0
    diameter_nm = 20.0
    positions_m, diameters_m = generate_random_nonoverlapping_configuration(
        diameters_m=[diameter_nm * 1.0e-9] * 20,
        seed=20260720,
        minimum_surface_gap_m=minimum_gap_nm * 1.0e-9,
        maximum_surface_gap_m=maximum_gap_nm * 1.0e-9,
        placement_half_width_m=recommended_placement_half_width_m(
            particle_count=20,
            mean_diameter_m=diameter_nm * 1.0e-9,
            minimum_surface_gap_m=minimum_gap_nm * 1.0e-9,
        ),
        coordinate_step_m=0.1e-9,
    )

    positions_nm = positions_m / 1.0e-9
    diameters_nm = diameters_m / 1.0e-9
    surface_gaps_nm = _all_surface_gaps_nm(positions_nm, diameters_nm)

    assert np.allclose(positions_nm * 10.0, np.rint(positions_nm * 10.0))
    assert min(surface_gaps_nm) > minimum_gap_nm
    assert max(surface_gaps_nm) <= maximum_gap_nm + 1.0e-12


def test_random_cluster_rejects_a_maximum_gap_below_the_minimum() -> None:
    """生成層でも逆転したギャップ範囲を受け入れない。"""
    with pytest.raises(ParticleLayoutError, match="maximum_surface_gap_m"):
        generate_random_nonoverlapping_configuration(
            diameters_m=[20.0e-9, 20.0e-9],
            seed=1,
            minimum_surface_gap_m=5.0e-9,
            maximum_surface_gap_m=4.9e-9,
        )
