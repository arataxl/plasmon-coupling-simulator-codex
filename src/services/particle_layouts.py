"""UIプリセットとValidation Test 5で共有する決定的な粒子配置生成。"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray


DEFAULT_PLACEMENT_HALF_WIDTH_M = 150.0e-9
DEFAULT_MAX_PLACEMENT_ATTEMPTS = 10_000

FloatArray = NDArray[np.float64]


class ParticleLayoutError(ValueError):
    """指定された箱内で非重複配置を生成できないことを示す。"""


def _finite_positive(value: float, *, name: str) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise ParticleLayoutError(f"{name} must be finite and positive")
    return value


def recommended_placement_half_width_m(
    *,
    particle_count: int,
    mean_diameter_m: float,
    minimum_surface_gap_m: float,
) -> float:
    """ランダムクラスタ用の過度に密でない立方体半幅を返す。"""
    if particle_count < 1:
        raise ParticleLayoutError("particle_count must be at least one")
    mean_diameter_m = _finite_positive(mean_diameter_m, name="mean_diameter_m")
    if not math.isfinite(minimum_surface_gap_m) or minimum_surface_gap_m < 0.0:
        raise ParticleLayoutError(
            "minimum_surface_gap_m must be finite and non-negative"
        )
    particles_per_axis = math.ceil(particle_count ** (1.0 / 3.0))
    spacing_m = mean_diameter_m + minimum_surface_gap_m
    return max(
        DEFAULT_PLACEMENT_HALF_WIDTH_M,
        1.25 * particles_per_axis * spacing_m,
    )


def generate_random_nonoverlapping_configuration(
    *,
    diameters_m: ArrayLike,
    seed: int,
    minimum_surface_gap_m: float,
    placement_half_width_m: float = DEFAULT_PLACEMENT_HALF_WIDTH_M,
    max_attempts: int = DEFAULT_MAX_PLACEMENT_ATTEMPTS,
) -> tuple[FloatArray, FloatArray]:
    """指定seedで表面間ギャップを守るランダム3D配置を生成する。

    これはValidation Test 5で用いる逐次の棄却サンプリングそのものである。UIの
    ランダムクラスタも同じ関数をAPI経由で使うため、表示用と試験用で異なる乱数配置
    ロジックを持たない。長さはすべてSI単位（m）である。
    """
    diameter_array_m = np.asarray(diameters_m, dtype=np.float64).copy()
    if diameter_array_m.ndim != 1 or diameter_array_m.size == 0:
        raise ParticleLayoutError("diameters_m must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(diameter_array_m)) or np.any(diameter_array_m <= 0.0):
        raise ParticleLayoutError("diameters_m must contain finite positive values")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ParticleLayoutError("seed must be a non-negative integer")
    if not math.isfinite(minimum_surface_gap_m) or minimum_surface_gap_m < 0.0:
        raise ParticleLayoutError(
            "minimum_surface_gap_m must be finite and non-negative"
        )
    placement_half_width_m = _finite_positive(
        placement_half_width_m,
        name="placement_half_width_m",
    )
    if max_attempts < 1:
        raise ParticleLayoutError("max_attempts must be at least one")

    random_generator = np.random.default_rng(seed)
    random_generator.shuffle(diameter_array_m)
    positions_m = np.empty((len(diameter_array_m), 3), dtype=np.float64)
    for particle_index, diameter_m in enumerate(diameter_array_m):
        for _ in range(max_attempts):
            candidate_position_m = random_generator.uniform(
                low=-placement_half_width_m,
                high=placement_half_width_m,
                size=3,
            )
            if all(
                np.linalg.norm(candidate_position_m - positions_m[other_index])
                - (diameter_m + diameter_array_m[other_index]) / 2.0
                > minimum_surface_gap_m
                for other_index in range(particle_index)
            ):
                positions_m[particle_index] = candidate_position_m
                break
        else:
            raise ParticleLayoutError(
                "could not generate a non-overlapping random configuration"
            )
    return positions_m, diameter_array_m
