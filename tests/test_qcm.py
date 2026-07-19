"""Validation Test 4の基礎: Au `gamma_g(l)` 暫定デジタイズ表。"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from scipy.constants import c as SPEED_OF_LIGHT_M_PER_S

from src.io.qcm_parameter_table import load_gamma_g_au_digitized
from src.physics.qcm import (
    AU_JELLIUM_QCM_PLASMA_ENERGY_EV,
    GammaGParameterTable,
    QcmSeparationBelowDigitizedRangeError,
    calculate_qcm_gap_permittivity,
    energy_ev_to_angular_frequency_rad_s,
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


def test_qcm_gap_permittivity_uses_the_documented_drude_form(
    parameter_table: GammaGParameterTable,
) -> None:
    """Eq. (3)由来のDrude項を媒質基線へ正しく加える。"""
    angular_frequency_rad_s = 2.0 * math.pi * SPEED_OF_LIGHT_M_PER_S / 600.0e-9
    medium_relative_permittivity = 1.33**2
    result = calculate_qcm_gap_permittivity(
        separation_m=0.5e-9,
        angular_frequency_rad_s=angular_frequency_rad_s,
        medium_relative_permittivity=medium_relative_permittivity,
        parameter_table=parameter_table,
    )
    assert not result.classical_limit
    assert result.gamma_g_ev is not None
    assert result.gamma_g_rad_s is not None
    expected_permittivity = medium_relative_permittivity - (
        energy_ev_to_angular_frequency_rad_s(AU_JELLIUM_QCM_PLASMA_ENERGY_EV) ** 2
        / (
            angular_frequency_rad_s
            * (angular_frequency_rad_s + 1j * result.gamma_g_rad_s)
        )
    )
    assert result.relative_permittivity == pytest.approx(expected_permittivity)


def test_qcm_gap_permittivity_returns_the_medium_in_the_classical_limit(
    parameter_table: GammaGParameterTable,
) -> None:
    """表の上限超過時に有限gammaを外挿せず、媒質へ厳密に戻す。"""
    medium_relative_permittivity = 1.33**2
    result = calculate_qcm_gap_permittivity(
        separation_m=0.7e-9,
        angular_frequency_rad_s=2.0 * math.pi * SPEED_OF_LIGHT_M_PER_S / 600.0e-9,
        medium_relative_permittivity=medium_relative_permittivity,
        parameter_table=parameter_table,
    )
    assert result.classical_limit
    assert result.gamma_g_ev is None
    assert result.relative_permittivity == complex(medium_relative_permittivity)
