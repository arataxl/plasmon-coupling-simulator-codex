"""UIプリセットとValidation Test 5で共有する決定的な粒子配置生成。"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray


DEFAULT_PLACEMENT_HALF_WIDTH_M = 150.0e-9
DEFAULT_MAX_PLACEMENT_ATTEMPTS = 10_000
DISPLAY_COORDINATE_DECIMALS = 1
DISPLAY_COORDINATE_STEP_M = 10.0 ** (-DISPLAY_COORDINATE_DECIMALS) * 1.0e-9
MINIMUM_DISPLAY_SURFACE_GAP_M = 0.5e-9
_DISPLAY_GAP_TOLERANCE_M = 1.0e-18

FloatArray = NDArray[np.float64]


class ParticleLayoutError(ValueError):
    """指定された箱内で非重複配置を生成できないことを示す。"""


def _surface_gap_m(
    first_position_m: FloatArray,
    second_position_m: FloatArray,
    first_diameter_m: float,
    second_diameter_m: float,
) -> float:
    """二粒子の中心座標と直径から表面間ギャップを返す。"""
    return float(
        np.linalg.norm(first_position_m - second_position_m)
        - (first_diameter_m + second_diameter_m) / 2.0
    )


def _round_to_display_grid_m(values_m: FloatArray) -> FloatArray:
    """座標を 0.1 nm 格子へ、符号に対して対称な最近傍丸めで写す。"""
    grid_values = np.abs(values_m) / DISPLAY_COORDINATE_STEP_M
    rounded_grid_values = np.floor(grid_values + 0.5 + 1.0e-12)
    return np.copysign(rounded_grid_values, values_m) * DISPLAY_COORDINATE_STEP_M


def _round_away_from_origin_to_grid_m(
    *, value_m: float, direction: float
) -> float:
    """指定方向で原点から遠ざかる 0.1 nm 格子点を選ぶ。"""
    if direction > 0.0:
        return (
            math.ceil(value_m / DISPLAY_COORDINATE_STEP_M - 1.0e-12)
            * DISPLAY_COORDINATE_STEP_M
        )
    if direction < 0.0:
        return (
            math.floor(value_m / DISPLAY_COORDINATE_STEP_M + 1.0e-12)
            * DISPLAY_COORDINATE_STEP_M
        )
    return float(_round_to_display_grid_m(np.asarray([value_m]))[0])


def round_layout_coordinates_for_display(
    *,
    positions_m: ArrayLike,
    diameters_m: ArrayLike,
    target_minimum_surface_gap_m: float = MINIMUM_DISPLAY_SURFACE_GAP_M,
) -> FloatArray:
    """UIプリセット表示用に座標だけを安全な 0.1 nm 格子へ丸める。

    この関数は計算コアに渡すランダム配置を変更しない。プリセットの座標を
    HTML の ``step=0.1`` 入力へ書き込む直前だけに使う表示層用の整形である。
    最近傍丸めで表面間ギャップが小さくなった場合は、一方の粒子を丸め格子上で
    外向きに移し、少なくとも ``target_minimum_surface_gap_m`` を保つ。
    生の配置自体が 0.5 nm 未満なら、危険な入力を隠すことなくエラーにする。
    """
    position_array_m = np.asarray(positions_m, dtype=np.float64).copy()
    diameter_array_m = np.asarray(diameters_m, dtype=np.float64).copy()
    if (
        position_array_m.ndim != 2
        or position_array_m.shape[1:] != (3,)
        or position_array_m.shape[0] == 0
    ):
        raise ParticleLayoutError("positions_m must have shape (particle_count, 3)")
    if diameter_array_m.shape != (position_array_m.shape[0],):
        raise ParticleLayoutError("diameters_m must match the number of positions")
    if not np.all(np.isfinite(position_array_m)):
        raise ParticleLayoutError("positions_m must contain only finite values")
    if not np.all(np.isfinite(diameter_array_m)) or np.any(diameter_array_m <= 0.0):
        raise ParticleLayoutError("diameters_m must contain finite positive values")
    if (
        not math.isfinite(target_minimum_surface_gap_m)
        or target_minimum_surface_gap_m < MINIMUM_DISPLAY_SURFACE_GAP_M
    ):
        raise ParticleLayoutError(
            "target_minimum_surface_gap_m must be finite and at least 0.5 nm"
        )

    for left_index in range(len(position_array_m)):
        for right_index in range(left_index + 1, len(position_array_m)):
            raw_gap_m = _surface_gap_m(
                position_array_m[left_index],
                position_array_m[right_index],
                diameter_array_m[left_index],
                diameter_array_m[right_index],
            )
            if raw_gap_m < MINIMUM_DISPLAY_SURFACE_GAP_M - _DISPLAY_GAP_TOLERANCE_M:
                raise ParticleLayoutError(
                    "source layout contains a surface gap below the 0.5 nm model limit"
                )

    rounded_positions_m = _round_to_display_grid_m(position_array_m)
    maximum_adjustments = max(1, len(rounded_positions_m) ** 2 * 8)
    for _ in range(maximum_adjustments):
        violation: tuple[int, int] | None = None
        for left_index in range(len(rounded_positions_m)):
            for right_index in range(left_index + 1, len(rounded_positions_m)):
                rounded_gap_m = _surface_gap_m(
                    rounded_positions_m[left_index],
                    rounded_positions_m[right_index],
                    diameter_array_m[left_index],
                    diameter_array_m[right_index],
                )
                if (
                    rounded_gap_m
                    < target_minimum_surface_gap_m - _DISPLAY_GAP_TOLERANCE_M
                ):
                    violation = (left_index, right_index)
                    break
            if violation is not None:
                break
        if violation is None:
            return rounded_positions_m

        left_index, right_index = violation
        origin_m = rounded_positions_m[left_index]
        displacement_m = rounded_positions_m[right_index] - origin_m
        displacement_norm_m = float(np.linalg.norm(displacement_m))
        if displacement_norm_m <= _DISPLAY_GAP_TOLERANCE_M:
            displacement_m = position_array_m[right_index] - position_array_m[left_index]
            displacement_norm_m = float(np.linalg.norm(displacement_m))
        if displacement_norm_m <= _DISPLAY_GAP_TOLERANCE_M:
            displacement_m = np.asarray((1.0, 0.0, 0.0), dtype=np.float64)
            displacement_norm_m = 1.0
        direction = displacement_m / displacement_norm_m
        target_center_distance_m = (
            (diameter_array_m[left_index] + diameter_array_m[right_index]) / 2.0
            + target_minimum_surface_gap_m
        )
        target_position_m = origin_m + direction * target_center_distance_m
        rounded_positions_m[right_index] = np.asarray(
            [
                _round_away_from_origin_to_grid_m(
                    value_m=float(value_m), direction=float(direction_component)
                )
                for value_m, direction_component in zip(
                    target_position_m, direction, strict=True
                )
            ],
            dtype=np.float64,
        )

    raise ParticleLayoutError(
        "could not round the display layout without violating the required surface gap"
    )


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
