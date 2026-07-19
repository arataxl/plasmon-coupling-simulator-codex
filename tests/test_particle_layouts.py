"""UIプリセット表示専用の座標丸めを検証する。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.services.particle_layouts import round_layout_coordinates_for_display


def _surface_gap_nm(positions_nm: np.ndarray, diameters_nm: np.ndarray) -> float:
    return float(
        np.linalg.norm(positions_nm[1] - positions_nm[0])
        - (diameters_nm[0] + diameters_nm[1]) / 2.0
    )


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
