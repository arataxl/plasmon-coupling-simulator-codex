"""スペクトル表示用 Savitzky--Golay 後処理の検証。"""

from __future__ import annotations

import numpy as np
import pytest

from src.services.spectrum_smoothing import (
    SMOOTHING_DEFAULT_LEVEL,
    SMOOTHING_LEVELS,
    smooth_spectrum_cross_sections,
)


def test_smoothing_preserves_raw_arrays_and_recomputes_absorption() -> None:
    """平滑化済み Cabs は、独立処理でなく Cext - Csca を使う。"""
    raw_c_ext = np.asarray([1.0, 4.0, 2.0, 8.0, 3.0, 6.0, 2.0, 5.0, 4.0, 7.0], dtype=np.float64)
    raw_c_sca = np.asarray([0.2, 1.5, 0.5, 2.0, 0.8, 1.2, 0.4, 1.0, 0.6, 1.4], dtype=np.float64)
    raw_c_abs = raw_c_ext - raw_c_sca

    result = smooth_spectrum_cross_sections(
        c_ext_m2=raw_c_ext,
        c_sca_m2=raw_c_sca,
        c_abs_m2=raw_c_abs,
    )

    np.testing.assert_array_equal(result.raw_c_ext_m2, raw_c_ext)
    np.testing.assert_array_equal(result.raw_c_sca_m2, raw_c_sca)
    np.testing.assert_array_equal(result.raw_c_abs_m2, raw_c_abs)
    assert not np.array_equal(result.c_ext_m2, raw_c_ext)
    np.testing.assert_allclose(
        result.c_abs_m2,
        result.c_ext_m2 - result.c_sca_m2,
        rtol=0.0,
        atol=0.0,
    )


def test_smoothing_skips_spectra_shorter_than_the_valid_window() -> None:
    """5 点未満では元の配列をそのまま返す。"""
    window_length = SMOOTHING_LEVELS[SMOOTHING_DEFAULT_LEVEL][0]
    raw_c_ext = np.arange(1.0, window_length, dtype=np.float64)
    raw_c_sca = raw_c_ext / 10.0
    raw_c_abs = raw_c_ext - raw_c_sca

    result = smooth_spectrum_cross_sections(
        c_ext_m2=raw_c_ext,
        c_sca_m2=raw_c_sca,
        c_abs_m2=raw_c_abs,
    )

    assert raw_c_ext.size < window_length
    np.testing.assert_array_equal(result.c_ext_m2, raw_c_ext)
    np.testing.assert_array_equal(result.c_sca_m2, raw_c_sca)
    np.testing.assert_array_equal(result.c_abs_m2, raw_c_abs)


def test_all_smoothing_levels_and_invalid_level_are_checked() -> None:
    values = np.linspace(1.0, 40.0, 40, dtype=np.float64) + 0.2 * np.sin(
        np.linspace(0.0, 8.0 * np.pi, 40, dtype=np.float64)
    )
    for level in SMOOTHING_LEVELS:
        result = smooth_spectrum_cross_sections(
            c_ext_m2=values,
            c_sca_m2=values / 3.0,
            c_abs_m2=values * 2.0 / 3.0,
            level=level,
        )
        assert result.smoothing_level == level
        assert not np.array_equal(result.c_ext_m2, values)
        np.testing.assert_allclose(result.c_abs_m2, result.c_ext_m2 - result.c_sca_m2)
    with pytest.raises(ValueError, match="unknown smoothing level"):
        smooth_spectrum_cross_sections(
            c_ext_m2=values,
            c_sca_m2=values / 3.0,
            c_abs_m2=values * 2.0 / 3.0,
            level="invalid",
        )
