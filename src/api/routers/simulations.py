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
    ParticleInput,
    RandomClusterLayoutInput,
    SimulationInput,
)
from src.services.job_manager import SimulationJobManager, SimulationJobNotFoundError
from src.services.particle_layouts import (
    ParticleLayoutError,
    generate_random_nonoverlapping_configuration,
    recommended_placement_half_width_m,
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
    simulation: SimulationInput,
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
    simulation: SimulationInput,
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
        raise HTTPException(status_code=404, detail="simulation job was not found") from error
    return {"job_id": job_id, "cancellation_requested": accepted}


@router.post("/layouts/random-cluster")
def random_cluster_layout(
    request: RandomClusterLayoutInput,
) -> dict[str, list[ParticleInput]]:
    """Test 5と同じ棄却サンプリングでUI用3Dランダムクラスタを作る。"""
    diameter_m = float(nanometres_to_metres(request.mean_diameter_nm))
    minimum_gap_m = float(nanometres_to_metres(request.minimum_surface_gap_nm))
    try:
        positions_m, diameters_m = generate_random_nonoverlapping_configuration(
            diameters_m=[diameter_m] * request.particle_count,
            seed=request.seed,
            minimum_surface_gap_m=minimum_gap_m,
            placement_half_width_m=recommended_placement_half_width_m(
                particle_count=request.particle_count,
                mean_diameter_m=diameter_m,
                minimum_surface_gap_m=minimum_gap_m,
            ),
        )
    except ParticleLayoutError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "particles": [
            ParticleInput(
                diameter_nm=float(metres_to_nanometres(diameter)),
                x_nm=float(metres_to_nanometres(position[0])),
                y_nm=float(metres_to_nanometres(position[1])),
                z_nm=float(metres_to_nanometres(position[2])),
            )
            for position, diameter in zip(positions_m, diameters_m, strict=True)
        ]
    }
