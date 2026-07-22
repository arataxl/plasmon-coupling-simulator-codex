"""Checks for the explicitly opt-in, incomplete electric ED--EQ extension."""

from __future__ import annotations

import csv
import io

import numpy as np
import pytest

from src.io.exporters import simulation_result_to_csv, simulation_result_to_json
from src.io.qcm_parameter_table import load_gamma_g_au_digitized
from src.physics.cda_solver import (
    WARNING_EXPERIMENTAL_QUADRUPOLE_COUPLING,
    calculate_cda_cross_sections,
    calculate_cda_spectrum,
    solve_cda,
)
from src.physics.material_data import OpticalConstants, load_au_optical_constants
from src.physics.polarizability import (
    calculate_electric_quadrupole_polarizability,
    calculate_fcda_polarizability,
)
from src.schemas.simulation import (
    LightSourceInput,
    MediumInput,
    ParticleInput,
    SimulationInput,
    SpectrumRangeInput,
)
from src.services.simulation_service import run_simulation


MEDIUM_REFRACTIVE_INDEX = 1.33
PROPAGATION_DIRECTION = (0.0, 0.0, 1.0)
POLARIZATION = (1.0, 0.0, 0.0)


@pytest.fixture(scope="module")
def optical_constants() -> OpticalConstants:
    return load_au_optical_constants()


def test_single_sphere_ed_eq_matches_the_a1_plus_a2_mie_partial_cross_sections(
    optical_constants: OpticalConstants,
) -> None:
    """The ED--EQ normalization must reproduce isolated electric a1+a2 terms."""
    wavelength_m = 800.0e-9
    diameter_m = 60.0e-9
    solution = solve_cda(
        positions_m=np.array([[0.0, 0.0, 0.0]]),
        diameters_m=np.array([diameter_m]),
        wavelength_m=wavelength_m,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
        apply_experimental_quadrupole_coupling=True,
    )
    cross_sections = calculate_cda_cross_sections(solution)
    dipole = calculate_fcda_polarizability(
        wavelength_m=wavelength_m,
        diameter_m=diameter_m,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        optical_constants=optical_constants,
    )
    quadrupole = calculate_electric_quadrupole_polarizability(
        wavelength_m=wavelength_m,
        diameter_m=diameter_m,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        optical_constants=optical_constants,
    )
    wave_number_m_inv = dipole.wave_number_m_inv
    expected_extinction_m2 = 2.0 * np.pi / wave_number_m_inv**2 * (
        3.0 * dipole.electric_dipole_mie_coefficient.real
        + 5.0 * quadrupole.electric_quadrupole_mie_coefficient.real
    )
    expected_scattering_m2 = 2.0 * np.pi / wave_number_m_inv**2 * (
        3.0 * abs(dipole.electric_dipole_mie_coefficient) ** 2
        + 5.0 * abs(quadrupole.electric_quadrupole_mie_coefficient) ** 2
    )

    np.testing.assert_allclose(
        (cross_sections.c_ext_m2, cross_sections.c_sca_m2),
        (expected_extinction_m2, expected_scattering_m2),
        rtol=1.0e-10,
    )
    assert solution.experimental_quadrupole_coupling_applied is True
    assert np.allclose(
        solution.induced_electric_quadrupoles_c_m2,
        np.swapaxes(solution.induced_electric_quadrupoles_c_m2, 1, 2),
    )
    assert np.allclose(
        np.trace(solution.induced_electric_quadrupoles_c_m2, axis1=1, axis2=2),
        0.0,
        atol=1.0e-55,
    )


def test_default_off_keeps_the_existing_dipole_spectrum_exactly_unchanged(
    optical_constants: OpticalConstants,
) -> None:
    """The opt-in flag must not alter the established Test 1--6 calculation path."""
    diameter_m = 60.0e-9
    gap_m = 10.0e-9
    common_arguments = dict(
        wavelengths_m=np.arange(600.0, 801.0, 20.0) * 1.0e-9,
        positions_m=np.array(
            [
                [-(diameter_m + gap_m) / 2.0, 0.0, 0.0],
                [(diameter_m + gap_m) / 2.0, 0.0, 0.0],
            ]
        ),
        diameters_m=np.array([diameter_m, diameter_m]),
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
    )
    default_spectrum = calculate_cda_spectrum(**common_arguments)
    explicit_off_spectrum = calculate_cda_spectrum(
        **common_arguments,
        apply_experimental_quadrupole_coupling=False,
    )

    np.testing.assert_array_equal(default_spectrum.c_ext_m2, explicit_off_spectrum.c_ext_m2)
    np.testing.assert_array_equal(default_spectrum.c_sca_m2, explicit_off_spectrum.c_sca_m2)
    np.testing.assert_array_equal(default_spectrum.c_abs_m2, explicit_off_spectrum.c_abs_m2)
    assert default_spectrum.experimental_quadrupole_coupling_applied is False


def test_dimer_ed_eq_is_finite_and_records_its_experimental_provenance(
    optical_constants: OpticalConstants,
) -> None:
    """A >5 nm dimer produces a finite, visibly different qualitative spectrum."""
    diameter_m = 60.0e-9
    gap_m = 10.0e-9
    common_arguments = dict(
        wavelengths_m=np.arange(600.0, 1000.1, 10.0) * 1.0e-9,
        positions_m=np.array(
            [
                [-(diameter_m + gap_m) / 2.0, 0.0, 0.0],
                [(diameter_m + gap_m) / 2.0, 0.0, 0.0],
            ]
        ),
        diameters_m=np.array([diameter_m, diameter_m]),
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
    )
    dipole_only = calculate_cda_spectrum(**common_arguments)
    experimental = calculate_cda_spectrum(
        **common_arguments,
        apply_experimental_quadrupole_coupling=True,
    )

    assert experimental.experimental_quadrupole_coupling_applied is True
    assert {warning.code for warning in experimental.warnings} == {
        WARNING_EXPERIMENTAL_QUADRUPOLE_COUPLING
    }
    for values in (
        experimental.c_ext_m2,
        experimental.c_sca_m2,
        experimental.c_abs_m2,
        experimental.condition_numbers,
    ):
        assert np.all(np.isfinite(values))
    relative_extinction_change = np.abs(
        (experimental.c_ext_m2 - dipole_only.c_ext_m2) / dipole_only.c_ext_m2
    )
    assert float(np.max(relative_extinction_change)) > 1.0e-4

    dipole_solution = solve_cda(
        positions_m=common_arguments["positions_m"],
        diameters_m=common_arguments["diameters_m"],
        wavelength_m=800.0e-9,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
    )
    experimental_solution = solve_cda(
        positions_m=common_arguments["positions_m"],
        diameters_m=common_arguments["diameters_m"],
        wavelength_m=800.0e-9,
        medium_refractive_index=MEDIUM_REFRACTIVE_INDEX,
        propagation_direction=PROPAGATION_DIRECTION,
        polarization=POLARIZATION,
        optical_constants=optical_constants,
        apply_experimental_quadrupole_coupling=True,
    )
    relative_dipole_change = float(
        np.linalg.norm(
            experimental_solution.induced_dipoles_c_m
            - dipole_solution.induced_dipoles_c_m
        )
        / np.linalg.norm(dipole_solution.induced_dipoles_c_m)
    )
    assert relative_dipole_change > 1.0e-7


def test_experimental_usage_is_retained_in_json_and_csv_metadata(
    optical_constants: OpticalConstants,
) -> None:
    """Both machine-readable export paths record that the approximation was used."""
    diameter_nm = 60.0
    simulation = SimulationInput(
        particles=[
            ParticleInput(diameter_nm=diameter_nm, x_nm=0.0, y_nm=0.0, z_nm=0.0),
            ParticleInput(
                diameter_nm=diameter_nm,
                x_nm=diameter_nm + 10.0,
                y_nm=0.0,
                z_nm=0.0,
            ),
        ],
        medium=MediumInput(name="water", refractive_index=MEDIUM_REFRACTIVE_INDEX),
        light_source=LightSourceInput(
            wavelength_nm=800.0,
            propagation_direction=PROPAGATION_DIRECTION,
            polarization=POLARIZATION,
        ),
        spectrum=SpectrumRangeInput(
            start_wavelength_nm=800.0,
            end_wavelength_nm=800.0,
            step_nm=10.0,
        ),
        experimental_quadrupole_coupling=True,
    )
    result = run_simulation(
        simulation,
        optical_constants=optical_constants,
        qcm_parameter_table=load_gamma_g_au_digitized(),
    )

    assert result.experimental_quadrupole_metadata.applied is True
    assert "Evlyukhin" in (result.experimental_quadrupole_metadata.source or "")
    assert "experimental_quadrupole_coupling" in {
        warning.code for warning in result.warnings
    }
    assert '"experimental_quadrupole_metadata"' in simulation_result_to_json(result)
    csv_rows = list(csv.DictReader(io.StringIO(simulation_result_to_csv(result))))
    assert csv_rows[0]["experimental_quadrupole_coupling"] == "true"
