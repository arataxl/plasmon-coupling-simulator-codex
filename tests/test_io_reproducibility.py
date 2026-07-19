"""Validation Test 6: 保存しないCSV/JSON出力の再現性。"""

from __future__ import annotations

import csv
import io
import json
import math

import pytest

from src.io.exporters import CSV_HEADER, simulation_result_to_csv, simulation_result_to_json
from src.io.importers import simulation_result_from_json
from src.io.qcm_parameter_table import load_gamma_g_au_digitized
from src.physics.material_data import OpticalConstants, load_au_optical_constants
from src.schemas.simulation import (
    LightSourceInput,
    MediumInput,
    ParticleInput,
    SimulationInput,
    SpectrumRangeInput,
)
from src.services.simulation_service import run_simulation


@pytest.fixture(scope="module")
def optical_constants() -> OpticalConstants:
    return load_au_optical_constants()


@pytest.fixture(scope="module")
def qcm_parameter_table():
    return load_gamma_g_au_digitized()


def _qcm_simulation_input() -> SimulationInput:
    diameter_nm = 20.0
    return SimulationInput(
        particles=[
            ParticleInput(diameter_nm=diameter_nm, x_nm=0.0, y_nm=0.0, z_nm=0.0),
            ParticleInput(
                diameter_nm=diameter_nm,
                x_nm=diameter_nm + 0.5,
                y_nm=0.0,
                z_nm=0.0,
            ),
        ],
        medium=MediumInput(name="water", refractive_index=1.33),
        light_source=LightSourceInput(
            wavelength_nm=600.0,
            propagation_direction=(0.0, 0.0, 1.0),
            polarization=(1.0, 0.0, 0.0),
        ),
        spectrum=SpectrumRangeInput(
            start_wavelength_nm=580.0,
            end_wavelength_nm=620.0,
            step_nm=20.0,
        ),
    )


def test_io_output_is_byte_reproducible_and_efficiencies_are_consistent(
    optical_constants: OpticalConstants,
    qcm_parameter_table,
) -> None:
    """同一入力のCSV/JSONは同一で、効率列は定義どおりの値を持つ。"""
    simulation = _qcm_simulation_input()
    first_result = run_simulation(
        simulation,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    second_result = run_simulation(
        simulation,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )

    first_csv = simulation_result_to_csv(first_result)
    second_csv = simulation_result_to_csv(second_result)
    first_json = simulation_result_to_json(first_result)
    second_json = simulation_result_to_json(second_result)
    assert first_csv == second_csv
    assert first_json == second_json

    rows = list(csv.DictReader(io.StringIO(first_csv)))
    assert tuple(rows[0]) == CSV_HEADER
    assert len(rows) == len(first_result.spectrum.wavelength_nm)
    for row in rows:
        geometric_cross_section_m2 = float(row["geometric_cross_section_m2"])
        for cross_section_column, efficiency_column in (
            ("c_ext_m2", "q_ext"),
            ("c_sca_m2", "q_sca"),
            ("c_abs_m2", "q_abs"),
        ):
            expected_efficiency = float(row[cross_section_column]) / geometric_cross_section_m2
            assert math.isclose(
                float(row[efficiency_column]),
                expected_efficiency,
                rel_tol=1.0e-12,
                abs_tol=1.0e-14,
            )


def test_json_round_trip_retains_qcm_metadata_and_recalculates_identically(
    optical_constants: OpticalConstants,
    qcm_parameter_table,
) -> None:
    """QCM来歴を含むJSONを再読込しても、同一条件を再計算できる。"""
    original = run_simulation(
        _qcm_simulation_input(),
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    serialized = simulation_result_to_json(original)
    restored = simulation_result_from_json(serialized)
    recalculated = run_simulation(
        restored.input,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )

    assert restored.qcm_metadata == original.qcm_metadata
    assert restored.qcm_metadata.qcm_applied is True
    assert restored.qcm_metadata.qcm_parameter_status == "provisional_digitized"
    assert simulation_result_to_json(recalculated) == serialized


def test_json_import_keeps_recalculation_compatible_with_browser_download_metadata(
    optical_constants: OpticalConstants,
    qcm_parameter_table,
) -> None:
    """ブラウザが付加する条件・時刻来歴を含んでも、再計算入力は失わない。"""
    original = run_simulation(
        _qcm_simulation_input(),
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    browser_export = json.loads(simulation_result_to_json(original))
    browser_export["download_metadata"] = {
        "particle_count": 2,
        "minimum_surface_gap_nm": 0.5,
        "qcm_applied": True,
        "result_timestamp_utc": "2026-07-20T00:00:00.000Z",
    }

    restored = simulation_result_from_json(json.dumps(browser_export))

    assert restored.input == original.input
    assert restored.qcm_metadata == original.qcm_metadata
