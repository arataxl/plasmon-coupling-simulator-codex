"""Validation Test 4の基礎: Au `gamma_g(l)` 暫定デジタイズ表。"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from src.io.qcm_parameter_table import load_gamma_g_au_digitized
from src.physics.qcm import (
    GammaGParameterTable,
    QcmSeparationBelowDigitizedRangeError,
    interpolate_gamma_g_from_separation_nm,
)


@pytest.fixture(scope="module")
def parameter_table() -> GammaGParameterTable:
    return load_gamma_g_au_digitized()


def test_digitized_knots_are_reproduced_in_log_space(
    parameter_table: GammaGParameterTable,
) -> None:
    """PCHIPは表の節点を再現し、Åからnmへの変換後も有限値を返す。"""
    assert len(parameter_table.separation_angstrom) == 22
    interpolated_gamma_g_ev: list[float] = []
    for separation_angstrom, expected_gamma_g_ev in zip(
        parameter_table.separation_angstrom,
        parameter_table.gamma_g_ev,
        strict=True,
    ):
        result = interpolate_gamma_g_from_separation_nm(
            separation_nm=float(separation_angstrom / 10.0),
            parameter_table=parameter_table,
        )
        assert not result.classical_limit
        assert result.gamma_g_ev is not None
        interpolated_gamma_g_ev.append(result.gamma_g_ev)
        # 節点再現の丸め誤差だけを許容する。デジタイズ自体の5--10%誤差とは別である。
        assert result.gamma_g_ev == pytest.approx(expected_gamma_g_ev, rel=1.0e-12)

    assert np.all(np.isfinite(interpolated_gamma_g_ev))


@pytest.mark.parametrize("separation_nm", (0.544, 0.7, 1.0))
def test_separation_above_digitized_range_uses_classical_limit(
    separation_nm: float,
    parameter_table: GammaGParameterTable,
) -> None:
    """5.439 Å超は外挿せず、トンネル伝導ゼロの古典極限へ切り替える。"""
    result = interpolate_gamma_g_from_separation_nm(
        separation_nm=separation_nm,
        parameter_table=parameter_table,
    )
    assert result.classical_limit
    assert result.gamma_g_ev is None


def test_separation_below_digitized_range_is_rejected(
    parameter_table: GammaGParameterTable,
) -> None:
    """下限未満は非物理的な外挿をせず明示的に拒否する。"""
    with pytest.raises(QcmSeparationBelowDigitizedRangeError, match="below"):
        interpolate_gamma_g_from_separation_nm(
            separation_nm=0.001,
            parameter_table=parameter_table,
        )


def test_digitized_metadata_records_provisional_status_and_limits() -> None:
    """暫定表の出典・単位・読取誤差・有効範囲を失わない。"""
    metadata_path = (
        Path(__file__).resolve().parents[1] / "data" / "qcm" / "metadata.yaml"
    )
    metadata = metadata_path.read_text(encoding="utf-8")
    for required_text in (
        "parameter_status: provisional_digitized",
        "figure: \"Fig. 2d\"",
        "curve: \"Au jellium, blue solid line\"",
        "separation: angstrom",
        "gamma_g: electron_volt",
        "approximately 5-10%",
        "separation_range_angstrom: [0.011, 5.439]",
    ):
        assert required_text in metadata


def test_interpolated_values_are_finite_within_digitized_range(
    parameter_table: GammaGParameterTable,
) -> None:
    """補間可能な範囲ではNaN/Infを返さない。"""
    minimum_angstrom, maximum_angstrom = parameter_table.separation_range_angstrom
    for separation_angstrom in np.linspace(minimum_angstrom, maximum_angstrom, 101):
        result = interpolate_gamma_g_from_separation_nm(
            separation_nm=float(separation_angstrom / 10.0),
            parameter_table=parameter_table,
        )
        assert not result.classical_limit
        assert result.gamma_g_ev is not None
        assert math.isfinite(result.gamma_g_ev)
