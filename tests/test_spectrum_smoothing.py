"""スペクトル表示用 Savitzky--Golay 後処理の検証。"""

from __future__ import annotations

import numpy as np

from src.services.spectrum_smoothing import (
    SMOOTHING_WINDOW_LENGTH,
    smooth_spectrum_cross_sections,
)


def test_smoothing_preserves_raw_arrays_and_recomputes_absorption() -> None:
    """平滑化済み Cabs は、独立処理でなく Cext - Csca を使う。"""
    raw_c_ext = np.asarray([1.0, 4.0, 2.0, 8.0, 3.0], dtype=np.float64)
    raw_c_sca = np.asarray([0.2, 1.5, 0.5, 2.0, 0.8], dtype=np.float64)
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
    raw_c_ext = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    raw_c_sca = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    raw_c_abs = raw_c_ext - raw_c_sca

    result = smooth_spectrum_cross_sections(
        c_ext_m2=raw_c_ext,
        c_sca_m2=raw_c_sca,
        c_abs_m2=raw_c_abs,
    )

    assert raw_c_ext.size < SMOOTHING_WINDOW_LENGTH
    np.testing.assert_array_equal(result.c_ext_m2, raw_c_ext)
    np.testing.assert_array_equal(result.c_sca_m2, raw_c_sca)
    np.testing.assert_array_equal(result.c_abs_m2, raw_c_abs)
