"""Phase 1の入力スキーマ検証。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.simulation import (
    LightSourceInput,
    MediumInput,
    ParticleInput,
    SimulationInput,
)


def _medium() -> MediumInput:
    return MediumInput(name="water", refractive_index=1.33)


def _light_source() -> LightSourceInput:
    return LightSourceInput(
        wavelength_nm=532.0,
        propagation_direction=(0.0, 0.0, 1.0),
        polarization=(1.0, 0.0, 0.0),
    )


@pytest.mark.parametrize("diameter_nm", [1.99, 100.01])
def test_particle_schema_rejects_out_of_range_diameter(diameter_nm: float) -> None:
    with pytest.raises(ValidationError):
        ParticleInput(diameter_nm=diameter_nm, x_nm=0.0, y_nm=0.0, z_nm=0.0)


@pytest.mark.parametrize("wavelength_nm", [299.9, 1700.1])
def test_light_source_schema_rejects_wavelength_outside_mcpeak_range(
    wavelength_nm: float,
) -> None:
    with pytest.raises(ValidationError):
        LightSourceInput(
            wavelength_nm=wavelength_nm,
            propagation_direction=(0.0, 0.0, 1.0),
            polarization=(1.0, 0.0, 0.0),
        )


def test_simulation_schema_rejects_gap_below_half_nanometre() -> None:
    with pytest.raises(ValidationError, match="at least 0.5 nm"):
        SimulationInput(
            particles=[
                ParticleInput(diameter_nm=20.0, x_nm=0.0, y_nm=0.0, z_nm=0.0),
                ParticleInput(diameter_nm=20.0, x_nm=20.49, y_nm=0.0, z_nm=0.0),
            ],
            medium=_medium(),
            light_source=_light_source(),
        )


def test_simulation_schema_allows_gap_of_exactly_half_nanometre() -> None:
    simulation = SimulationInput(
        particles=[
            ParticleInput(diameter_nm=20.0, x_nm=0.0, y_nm=0.0, z_nm=0.0),
            ParticleInput(diameter_nm=20.0, x_nm=20.5, y_nm=0.0, z_nm=0.0),
        ],
        medium=_medium(),
        light_source=_light_source(),
    )

    assert len(simulation.particles) == 2


def test_simulation_schema_rejects_non_au_material() -> None:
    with pytest.raises(ValidationError):
        SimulationInput(
            material="Ag",
            particles=[
                ParticleInput(diameter_nm=20.0, x_nm=0.0, y_nm=0.0, z_nm=0.0),
            ],
            medium=_medium(),
            light_source=_light_source(),
        )


def test_more_than_twenty_particles_require_every_gap_to_exceed_five_nanometres() -> None:
    particles = [
        ParticleInput(diameter_nm=20.0, x_nm=float(index * 25), y_nm=0.0, z_nm=0.0)
        for index in range(21)
    ]

    with pytest.raises(ValidationError, match="every surface gap to exceed 5 nm"):
        SimulationInput(
            particles=particles,
            medium=_medium(),
            light_source=_light_source(),
        )


def test_more_than_twenty_particles_allow_classical_gaps_above_five_nanometres() -> None:
    simulation = SimulationInput(
        particles=[
            ParticleInput(
                diameter_nm=20.0,
                x_nm=float(index * 25.1),
                y_nm=0.0,
                z_nm=0.0,
            )
            for index in range(50)
        ],
        medium=_medium(),
        light_source=_light_source(),
    )

    assert len(simulation.particles) == 50
