"""スペクトル計算を開始し、保存せずに完了結果を返すREST API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_optical_constants, get_qcm_parameter_table
from src.physics.material_data import OpticalConstants
from src.physics.qcm import GammaGParameterTable
from src.schemas.result import SimulationResult
from src.schemas.simulation import SimulationInput
from src.services.simulation_service import run_simulation


router = APIRouter(tags=["simulations"])

OpticalConstantsDependency = Annotated[
    OpticalConstants,
    Depends(get_optical_constants),
]
QcmParameterTableDependency = Annotated[
    GammaGParameterTable,
    Depends(get_qcm_parameter_table),
]


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
