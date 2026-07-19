"""Validation Test 3 の基礎: Au 球二量体の偏光依存結合。"""

from __future__ import annotations

import numpy as np
import pytest

from src.physics.cda_solver import CdaSpectrum, calculate_cda_spectrum
from src.physics.material_data import OpticalConstants, load_au_optical_constants


DIAMETER_NM = 20.0
MEDIUM_REFRACTIVE_INDEX = 1.33
WAVELENGTHS_M = np.arange(450.0, 701.0, 2.0) * 1.0e-9
GAPS_NM = (2.0, 5.0, 10.0, 20.0, 50.0)


@pytest.fixture(scope="module")
def optical_constants() -> OpticalConstants:
    return load_au_optical_constants()


def _dimer_spectrum(
    *,
    gap_nm: float,
    polarization: tuple[float, float, float],
    optical_constants: OpticalConstants,
) -> CdaSpectrum:
    center_distance_m = (DIAMETER_NM + gap_nm) * 1.0e-9
    return calculate_cda_spectrum(
        wavelengths_m=WAVELENGTHS_M,
        positions_m=np.array(
            [
                [-center_distance_m / 2.0, 0.0, 0.0],
                [center_distance_m / 2.0, 0.0, 0.0],
            ]
        ),
        diameters_m=np.array([DIAMETER_NM, DIAMETER_NM]) * 1.0e-9,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=(0.0, 0.0, 1.0),
        polarization=polarization,
        optical_constants=optical_constants,
    )


def _peak_wavelength_m(spectrum: CdaSpectrum) -> float:
    return float(spectrum.wavelength_m[int(np.argmax(spectrum.c_ext_m2))])


def test_dimer_has_polarization_dependent_continuous_resonance_shift(
    optical_constants: OpticalConstants,
) -> None:
    """gap 2--50 nm で偏光依存性・連続的な縦モード赤方移動を確認する。"""
    parallel_peak_wavelengths_m: list[float] = []
    perpendicular_peak_wavelengths_m: list[float] = []

    for gap_nm in GAPS_NM:
        parallel = _dimer_spectrum(
            gap_nm=gap_nm,
            polarization=(1.0, 0.0, 0.0),
            optical_constants=optical_constants,
        )
        perpendicular = _dimer_spectrum(
            gap_nm=gap_nm,
            polarization=(0.0, 1.0, 0.0),
            optical_constants=optical_constants,
        )
        for spectrum in (parallel, perpendicular):
            assert np.all(np.isfinite(spectrum.c_ext_m2))
            assert np.all(np.isfinite(spectrum.c_sca_m2))
            assert np.all(np.isfinite(spectrum.c_abs_m2))
            assert np.all(np.isfinite(spectrum.condition_numbers))
            assert np.all(spectrum.c_ext_m2 >= 0.0)
            assert np.all(spectrum.c_sca_m2 >= 0.0)
            assert np.all(spectrum.c_abs_m2 >= 0.0)

        # 二量体軸に平行な偏光（縦モード）と垂直偏光の応答は一致しない。
        assert not np.array_equal(parallel.c_ext_m2, perpendicular.c_ext_m2)
        assert np.max(parallel.c_ext_m2) > np.max(perpendicular.c_ext_m2)
        parallel_peak_wavelengths_m.append(_peak_wavelength_m(parallel))
        perpendicular_peak_wavelengths_m.append(_peak_wavelength_m(perpendicular))

        # UI 実装前のため、将来の表示に渡す警告データをここで検証する。
        assert bool(parallel.warnings) == (gap_nm <= 5.0)
        assert bool(perpendicular.warnings) == (gap_nm <= 5.0)

    parallel_peaks = np.asarray(parallel_peak_wavelengths_m)
    perpendicular_peaks = np.asarray(perpendicular_peak_wavelengths_m)
    assert parallel_peaks[0] > parallel_peaks[-1]
    assert np.all(np.diff(parallel_peaks) <= 0.0)
    assert parallel_peaks[0] > perpendicular_peaks[0]
