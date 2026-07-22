"""Tests for the separate 100--500 nm exact single-sphere Mie mode."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from src.io.qcm_parameter_table import load_gamma_g_au_digitized
from src.physics.cda_solver import calculate_cda_cross_sections, solve_cda
from src.physics.material_data import OpticalConstants, load_au_optical_constants
from src.physics.mie_reference import (
    EXACT_MIE_MAX_DIAMETER_M,
    EXACT_MIE_MIN_DIAMETER_M,
    calculate_exact_single_sphere_mie_spectrum,
    calculate_single_sphere_spectrum,
)
from src.schemas.simulation import (
    ExactMieSimulationInput,
    LightSourceInput,
    MediumInput,
    SpectrumRangeInput,
)
from src.services.simulation_service import run_simulation, run_simulation_with_progress


@pytest.fixture(scope="module")
def optical_constants() -> OpticalConstants:
    return load_au_optical_constants()


def _exact_mie_input(diameter_nm: float = 20.0) -> ExactMieSimulationInput:
    return ExactMieSimulationInput(
        simulation_mode="exact_mie",
        particles=[{"diameter_nm": diameter_nm}],
        medium=MediumInput(name="water", refractive_index=1.33),
        light_source=LightSourceInput(
            wavelength_nm=700.0,
            propagation_direction=(0.0, 0.0, 1.0),
            polarization=(1.0, 0.0, 0.0),
        ),
        spectrum=SpectrumRangeInput(
            start_wavelength_nm=600.0,
            end_wavelength_nm=800.0,
            step_nm=100.0,
        ),
    )


@pytest.mark.parametrize(
    "diameter_m",
    [
        EXACT_MIE_MIN_DIAMETER_M,
        20e-9,
        100e-9,
        200e-9,
        400e-9,
        EXACT_MIE_MAX_DIAMETER_M,
    ],
)
def test_exact_mie_mode_returns_finite_energy_balanced_all_order_spectrum(
    diameter_m: float,
    optical_constants: OpticalConstants,
) -> None:
    result = calculate_exact_single_sphere_mie_spectrum(
        wavelengths_m=np.asarray([600e-9, 800e-9, 1000e-9]),
        diameter_m=diameter_m,
        medium_refractive_index=1.33,
        optical_constants=optical_constants,
    )

    assert np.all(np.isfinite(result.c_ext_m2))
    assert np.all(np.isfinite(result.c_sca_m2))
    assert np.all(np.isfinite(result.c_abs_m2))
    np.testing.assert_allclose(
        result.c_ext_m2,
        result.c_sca_m2 + result.c_abs_m2,
        rtol=1e-12,
        atol=1e-30,
    )


def test_exact_mie_mode_uses_the_complete_mie_reference_solver(
    optical_constants: OpticalConstants,
) -> None:
    """The dedicated mode is a bounded wrapper around the all-order reference solver."""
    arguments = {
        "wavelengths_m": np.asarray([600e-9, 750e-9, 1000e-9]),
        "diameter_m": 400e-9,
        "medium_refractive_index": 1.33,
        "optical_constants": optical_constants,
    }
    exact = calculate_exact_single_sphere_mie_spectrum(**arguments)
    reference = calculate_single_sphere_spectrum(**arguments)

    np.testing.assert_allclose(exact.c_ext_m2, reference.c_ext_m2, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(exact.c_sca_m2, reference.c_sca_m2, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(exact.c_abs_m2, reference.c_abs_m2, rtol=0.0, atol=0.0)


@pytest.mark.parametrize("diameter_nm", [2.0, 99.9, 100.0, 499.9, 500.0])
def test_exact_mie_schema_accepts_inclusive_diameter_boundaries(
    diameter_nm: float,
) -> None:
    assert _exact_mie_input(diameter_nm).particles[0].diameter_nm == diameter_nm


@pytest.mark.parametrize("diameter_nm", [1.9, 500.1])
def test_exact_mie_schema_rejects_diameters_outside_2_to_500_nm(
    diameter_nm: float,
) -> None:
    with pytest.raises(ValidationError):
        _exact_mie_input(diameter_nm)


def test_exact_mie_service_path_has_no_cda_or_qcm_metadata() -> None:
    result = run_simulation(
        _exact_mie_input(),
        optical_constants=load_au_optical_constants(),
        qcm_parameter_table=load_gamma_g_au_digitized(),
    )

    assert result.input.simulation_mode == "exact_mie"
    assert result.provenance.model_name == "Exact single-sphere Mie theory (all orders)"
    assert result.qcm_metadata.qcm_applied is False
    assert result.experimental_quadrupole_metadata.applied is False
    assert result.warnings == []
    assert result.spectrum.wavelength_nm == [600.0, 700.0, 800.0]


def test_exact_mie_service_accepts_500_nm_after_si_unit_conversion() -> None:
    """500 nm must remain within the inclusive upper bound after nm-to-m conversion."""
    result = run_simulation(
        _exact_mie_input(500.0),
        optical_constants=load_au_optical_constants(),
        qcm_parameter_table=load_gamma_g_au_digitized(),
    )

    assert result.input.particles[0].diameter_nm == 500.0
    assert np.all(np.isfinite(result.spectrum.c_ext_m2))


@pytest.mark.parametrize("diameter_nm", [2.0, 20.0, 50.0, 100.0])
def test_exact_mie_and_single_particle_fcda_agree_over_the_cda_overlap(
    diameter_nm: float,
    optical_constants: OpticalConstants,
) -> None:
    """The overlap is a comparison path, not a change to the CDA size limit.

    The limits are empirical regression bounds over 600--1000 nm.  Absorption can
    be small, so its absolute difference is normalised by the exact peak Cext
    rather than by a near-zero Cabs value.
    """
    wavelengths_m = np.arange(600.0, 1001.0, 10.0) * 1e-9
    exact = calculate_exact_single_sphere_mie_spectrum(
        wavelengths_m=wavelengths_m,
        diameter_m=diameter_nm * 1e-9,
        medium_refractive_index=1.33,
        optical_constants=optical_constants,
    )
    fcda_ext_m2 = np.empty_like(wavelengths_m)
    fcda_sca_m2 = np.empty_like(wavelengths_m)
    fcda_abs_m2 = np.empty_like(wavelengths_m)
    for index, wavelength_m in enumerate(wavelengths_m):
        solution = solve_cda(
            positions_m=np.asarray([[0.0, 0.0, 0.0]]),
            diameters_m=np.asarray([diameter_nm * 1e-9]),
            wavelength_m=float(wavelength_m),
            medium_refractive_index=1.33,
            propagation_direction=(0.0, 0.0, 1.0),
            polarization=(1.0, 0.0, 0.0),
            optical_constants=optical_constants,
        )
        cross_sections = calculate_cda_cross_sections(solution)
        fcda_ext_m2[index] = cross_sections.c_ext_m2
        fcda_sca_m2[index] = cross_sections.c_sca_m2
        fcda_abs_m2[index] = cross_sections.c_abs_m2

    assert np.max(np.abs(fcda_ext_m2 - exact.c_ext_m2) / exact.c_ext_m2) <= 0.10
    assert np.max(np.abs(fcda_sca_m2 - exact.c_sca_m2) / exact.c_sca_m2) <= 0.01
    assert (
        np.max(np.abs(fcda_abs_m2 - exact.c_abs_m2)) / np.max(exact.c_ext_m2)
        <= 0.02
    )


def test_exact_mie_streaming_path_reports_each_completed_wavelength() -> None:
    progress: list[tuple[int, int]] = []
    result = run_simulation_with_progress(
        _exact_mie_input(),
        optical_constants=load_au_optical_constants(),
        qcm_parameter_table=load_gamma_g_au_digitized(),
        cancellation_requested=lambda: False,
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )

    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert result.provenance.model_name == "Exact single-sphere Mie theory (all orders)"
