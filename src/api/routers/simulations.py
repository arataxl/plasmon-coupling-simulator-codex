"""スペクトル計算を開始し、保存せずに完了結果を返すREST API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import (
    get_optical_constants,
    get_qcm_parameter_table,
    get_simulation_job_manager,
)
from src.io.unit_conversion import metres_to_nanometres, nanometres_to_metres
from src.physics.material_data import OpticalConstants
from src.physics.qcm import GammaGParameterTable
from src.schemas.result import SimulationResult
from src.schemas.simulation import (
    DisplayLayoutInput,
    ParticleInput,
    RandomClusterLayoutInput,
    SimulationRequest,
)
from src.services.job_manager import SimulationJobManager, SimulationJobNotFoundError
from src.services.particle_layouts import (
    DISPLAY_COORDINATE_DECIMALS,
    DISPLAY_COORDINATE_STEP_M,
    ParticleLayoutError,
    generate_random_nonoverlapping_configuration,
    recommended_placement_half_width_m,
    round_layout_coordinates_for_display,
)
from src.services.simulation_service import (
    MAX_STREAM_SPECTRUM_POINTS,
    run_simulation,
    validate_spectrum_point_limit,
)


router = APIRouter(tags=["simulations"])

OpticalConstantsDependency = Annotated[
    OpticalConstants,
    Depends(get_optical_constants),
]
QcmParameterTableDependency = Annotated[
    GammaGParameterTable,
    Depends(get_qcm_parameter_table),
]
JobManagerDependency = Annotated[SimulationJobManager, Depends(get_simulation_job_manager)]


@router.post("/simulate", response_model=SimulationResult)
def simulate(
    simulation: SimulationRequest,
    optical_constants: OpticalConstantsDependency,
    qcm_parameter_table: QcmParameterTableDependency,
) -> SimulationResult:
    """同期的にCDA/QCMスペクトルを計算し、結果を永続化せずに返す。"""
    return run_simulation(
        simulation,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )


@router.post("/simulate/jobs", status_code=status.HTTP_202_ACCEPTED)
def start_simulation_job(
    simulation: SimulationRequest,
    optical_constants: OpticalConstantsDependency,
    qcm_parameter_table: QcmParameterTableDependency,
    job_manager: JobManagerDependency,
) -> dict[str, str]:
    """進捗SSE用の計算を開始し、結果を保存せずジョブIDだけを返す。"""
    validate_spectrum_point_limit(
        simulation.spectrum,
        maximum_points=MAX_STREAM_SPECTRUM_POINTS,
        endpoint_name="streaming API",
    )
    job_id = job_manager.start_job(
        simulation,
        optical_constants=optical_constants,
        qcm_parameter_table=qcm_parameter_table,
    )
    return {"job_id": job_id}


@router.post("/simulate/jobs/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_simulation_job(
    job_id: str,
    job_manager: JobManagerDependency,
) -> dict[str, object]:
    """実行中ジョブに協調的な取消を要求する。"""
    try:
        accepted = job_manager.cancel_job(job_id)
    except SimulationJobNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "simulation_job_not_found", "parameters": {}},
        ) from error
    return {"job_id": job_id, "cancellation_requested": accepted}


@router.post("/layouts/random-cluster")
def random_cluster_layout(
    request: RandomClusterLayoutInput,
) -> dict[str, list[ParticleInput]]:
    """Test 5と同じ棄却サンプリングでUI用3Dランダムクラスタを作る。"""
    diameter_m = float(nanometres_to_metres(request.mean_diameter_nm))
    minimum_gap_m = float(nanometres_to_metres(request.minimum_surface_gap_nm))
    maximum_gap_m = float(nanometres_to_metres(request.maximum_surface_gap_nm))
    try:
        positions_m, diameters_m = generate_random_nonoverlapping_configuration(
            diameters_m=[diameter_m] * request.particle_count,
            seed=request.seed,
            minimum_surface_gap_m=minimum_gap_m,
            maximum_surface_gap_m=maximum_gap_m,
            placement_half_width_m=recommended_placement_half_width_m(
                particle_count=request.particle_count,
                mean_diameter_m=diameter_m,
                minimum_surface_gap_m=minimum_gap_m,
            ),
            coordinate_step_m=DISPLAY_COORDINATE_STEP_M,
        )
    except ParticleLayoutError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "random_cluster_generation_failed", "parameters": {}},
        ) from error
    try:
        display_positions_m = round_layout_coordinates_for_display(
            positions_m=positions_m,
            diameters_m=diameters_m,
            target_minimum_surface_gap_m=minimum_gap_m,
            target_maximum_surface_gap_m=maximum_gap_m,
        )
    except ParticleLayoutError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "preset_layout_invalid", "parameters": {}},
        ) from error
    return {
        "particles": [
            ParticleInput(
                diameter_nm=round(
                    float(metres_to_nanometres(diameter)), DISPLAY_COORDINATE_DECIMALS
                ),
                x_nm=round(
                    float(metres_to_nanometres(position[0])),
                    DISPLAY_COORDINATE_DECIMALS,
                ),
                y_nm=round(
                    float(metres_to_nanometres(position[1])),
                    DISPLAY_COORDINATE_DECIMALS,
                ),
                z_nm=round(
                    float(metres_to_nanometres(position[2])),
                    DISPLAY_COORDINATE_DECIMALS,
                ),
            )
            for position, diameter in zip(display_positions_m, diameters_m, strict=True)
        ]
    }


@router.post("/layouts/round-for-display")
def round_layout_for_display(
    request: DisplayLayoutInput,
) -> dict[str, list[ParticleInput]]:
    """任意プリセットの座標を、物理安全装置を保って 0.1 nm 表示へ整形する。"""
    positions_m = [
        [
            float(nanometres_to_metres(particle.x_nm)),
            float(nanometres_to_metres(particle.y_nm)),
            float(nanometres_to_metres(particle.z_nm)),
        ]
        for particle in request.particles
    ]
    diameters_m = [
        float(nanometres_to_metres(particle.diameter_nm))
        for particle in request.particles
    ]
    try:
        display_positions_m = round_layout_coordinates_for_display(
            positions_m=positions_m,
            diameters_m=diameters_m,
        )
    except ParticleLayoutError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "preset_layout_invalid", "parameters": {}},
        ) from error
    return {
        "particles": [
            ParticleInput(
                diameter_nm=round(particle.diameter_nm, DISPLAY_COORDINATE_DECIMALS),
                x_nm=round(
                    float(metres_to_nanometres(position[0])),
                    DISPLAY_COORDINATE_DECIMALS,
                ),
                y_nm=round(
                    float(metres_to_nanometres(position[1])),
                    DISPLAY_COORDINATE_DECIMALS,
                ),
                z_nm=round(
                    float(metres_to_nanometres(position[2])),
                    DISPLAY_COORDINATE_DECIMALS,
                ),
            )
            for particle, position in zip(
                request.particles, display_positions_m, strict=True
            )
        ]
    }
