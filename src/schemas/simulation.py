"""Phase 1で必要なシミュレーション入力スキーマ。"""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MIN_DIAMETER_NM = 2.0
MAX_DIAMETER_NM = 100.0
MIN_SURFACE_GAP_NM = 0.5
MIN_WAVELENGTH_NM = 200.0
MAX_WAVELENGTH_NM = 1500.0
_GAP_COMPARISON_ABS_TOLERANCE_NM = 1e-12


def _require_finite(value: float, *, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


class ParticleInput(BaseModel):
    """Au球の直径と中心座標。すべての長さはnm。"""

    model_config = ConfigDict(extra="forbid")

    diameter_nm: float = Field(ge=MIN_DIAMETER_NM, le=MAX_DIAMETER_NM)
    x_nm: float
    y_nm: float
    z_nm: float

    @field_validator("diameter_nm", "x_nm", "y_nm", "z_nm")
    @classmethod
    def validate_finite_values(cls, value: float, info: object) -> float:
        field_name = getattr(info, "field_name", "value")
        return _require_finite(value, field_name=field_name)


class MediumInput(BaseModel):
    """均一・等方・非吸収性媒質の入力。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    refractive_index: float = Field(gt=0)

    @field_validator("refractive_index")
    @classmethod
    def validate_refractive_index(cls, value: float) -> float:
        return _require_finite(value, field_name="refractive_index")


class LightSourceInput(BaseModel):
    """単色平面波の入力。波長は真空波長nm、ベクトルは無次元。"""

    model_config = ConfigDict(extra="forbid")

    wavelength_nm: float = Field(ge=MIN_WAVELENGTH_NM, le=MAX_WAVELENGTH_NM)
    propagation_direction: tuple[float, float, float]
    polarization: tuple[float, float, float]

    @field_validator("wavelength_nm")
    @classmethod
    def validate_wavelength(cls, value: float) -> float:
        return _require_finite(value, field_name="wavelength_nm")

    @field_validator("propagation_direction", "polarization")
    @classmethod
    def validate_vectors(
        cls, value: tuple[float, float, float], info: object
    ) -> tuple[float, float, float]:
        field_name = getattr(info, "field_name", "vector")
        if not all(math.isfinite(component) for component in value):
            raise ValueError(f"{field_name} must contain only finite values")
        if math.isclose(sum(component * component for component in value), 0.0):
            raise ValueError(f"{field_name} must not be the zero vector")
        return value


class SimulationInput(BaseModel):
    """粒子間ギャップを含めて検証するMVP入力。"""

    model_config = ConfigDict(extra="forbid")

    material: Literal["Au"] = "Au"
    particles: list[ParticleInput] = Field(min_length=1, max_length=20)
    medium: MediumInput
    light_source: LightSourceInput

    @model_validator(mode="after")
    def validate_surface_gaps(self) -> Self:
        for left_index, left_particle in enumerate(self.particles):
            for right_index in range(left_index + 1, len(self.particles)):
                right_particle = self.particles[right_index]
                center_distance_nm = math.dist(
                    (left_particle.x_nm, left_particle.y_nm, left_particle.z_nm),
                    (right_particle.x_nm, right_particle.y_nm, right_particle.z_nm),
                )
                surface_gap_nm = center_distance_nm - (
                    left_particle.diameter_nm + right_particle.diameter_nm
                ) / 2.0
                if (
                    surface_gap_nm < MIN_SURFACE_GAP_NM
                    and not math.isclose(
                        surface_gap_nm,
                        MIN_SURFACE_GAP_NM,
                        rel_tol=0.0,
                        abs_tol=_GAP_COMPARISON_ABS_TOLERANCE_NM,
                    )
                ):
                    raise ValueError(
                        "surface gap between particles "
                        f"{left_index} and {right_index} is {surface_gap_nm:.12g} nm; "
                        f"at least {MIN_SURFACE_GAP_NM:g} nm is required"
                    )
        return self
