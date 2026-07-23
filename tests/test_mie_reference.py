"""Validation Test 1: 単一Au球の完全Mie参照計算。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.physics.material_data import (
    WavelengthOutOfRangeError,
    load_au_optical_constants,
)
from src.physics.mie_reference import calculate_single_sphere_spectrum


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mie_reference_baseline.json"
JOHNSON_CHRISTY_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "optical_constants"
    / "au_johnson_christy_1972.csv"
)
RELATIVE_TOLERANCE = 1e-6
_CROSS_SECTION_ABSOLUTE_TOLERANCE_M2 = 1e-30
_EFFICIENCY_ABSOLUTE_TOLERANCE = 1e-12


@pytest.fixture(scope="module")
def mie_baseline() -> dict[str, Any]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def test_material_data_rejects_extrapolation() -> None:
    """既定McPeak CSV外の波長を明示的に拒否する。"""
    material_data = load_au_optical_constants()
    assert material_data.source_path.name == "au_mcpeak_2015.csv"
    assert material_data.wavelength_range_nm == pytest.approx((300.0, 1700.0))
    lower_nm, upper_nm = material_data.wavelength_range_nm

    with pytest.raises(WavelengthOutOfRangeError):
        material_data.refractive_index(lower_nm - 0.1)
    with pytest.raises(WavelengthOutOfRangeError):
        material_data.refractive_index(upper_nm + 0.1)


def test_material_data_interpolates_refractive_index_linearly() -> None:
    """CSVの隣接点の中点で、nとkをそれぞれ線形補間する。"""
    material_data = load_au_optical_constants(path=JOHNSON_CHRISTY_PATH)
    index = 10
    wavelength_nm = (
        material_data.wavelength_nm[index] + material_data.wavelength_nm[index + 1]
    ) / 2.0
    expected = complex(
        (material_data.refractive_index_n[index]
         + material_data.refractive_index_n[index + 1])
        / 2.0,
        (material_data.extinction_coefficient_k[index]
         + material_data.extinction_coefficient_k[index + 1])
        / 2.0,
    )

    assert material_data.refractive_index(wavelength_nm) == pytest.approx(expected)


@pytest.mark.parametrize("diameter_nm", [5.0, 20.0, 50.0, 100.0])
def test_single_au_sphere_matches_mie_baseline(
    diameter_nm: float, mie_baseline: dict[str, Any]
) -> None:
    """Test 1の保存則・有限値・固定Mie基準配列の受入基準を検証する。"""
    material_data = load_au_optical_constants(path=JOHNSON_CHRISTY_PATH)
    wavelengths_nm = np.asarray(mie_baseline["wavelength_nm"], dtype=np.float64)
    result = calculate_single_sphere_spectrum(
        wavelengths_m=wavelengths_nm * 1e-9,
        diameter_m=diameter_nm * 1e-9,
        medium_refractive_index=float(mie_baseline["medium_refractive_index"]),
        optical_constants=material_data,
    )
    expected = mie_baseline["cases"][f"{diameter_nm:g}"]

    scale = np.maximum(np.abs(result.c_ext_m2), np.finfo(np.float64).tiny)
    energy_balance_error = np.abs(
        result.c_ext_m2 - result.c_sca_m2 - result.c_abs_m2
    ) / scale
    assert np.max(energy_balance_error) <= 1e-8
    cross_section_rounding_tolerance = (
        np.finfo(np.float64).eps
        * max(float(np.max(result.c_ext_m2)), np.finfo(np.float64).tiny)
        * 32.0
    )
    assert np.all(result.c_ext_m2 >= 0.0)
    assert np.all(result.c_sca_m2 >= 0.0)
    assert np.all(result.c_abs_m2 >= -cross_section_rounding_tolerance)

    for actual, field_name in (
        (result.c_ext_m2, "c_ext_m2"),
        (result.c_sca_m2, "c_sca_m2"),
        (result.c_abs_m2, "c_abs_m2"),
    ):
        np.testing.assert_allclose(
            actual,
            np.asarray(expected[field_name], dtype=np.float64),
            rtol=RELATIVE_TOLERANCE,
            atol=_CROSS_SECTION_ABSOLUTE_TOLERANCE_M2,
        )
    for actual, field_name in (
        (result.q_ext, "q_ext"),
        (result.q_sca, "q_sca"),
        (result.q_abs, "q_abs"),
    ):
        assert np.all(np.isfinite(actual))
        np.testing.assert_allclose(
            actual,
            np.asarray(expected[field_name], dtype=np.float64),
            rtol=RELATIVE_TOLERANCE,
            atol=_EFFICIENCY_ABSOLUTE_TOLERANCE,
        )
