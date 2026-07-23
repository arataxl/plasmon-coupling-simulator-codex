"""APIが物理コアへ注入する版管理済みの入力データ。"""

from __future__ import annotations

from functools import lru_cache

from src.io.qcm_parameter_table import load_gamma_g_au_digitized
from src.physics.material_data import OpticalConstants, load_au_optical_constants
from src.physics.qcm import GammaGParameterTable
from src.services.job_manager import SimulationJobManager


@lru_cache(maxsize=1)
def get_optical_constants() -> OpticalConstants:
    """既定のMcPeak et al. (2015) Au光学定数をプロセス内で一度だけ読む。"""
    return load_au_optical_constants()


@lru_cache(maxsize=1)
def get_qcm_parameter_table() -> GammaGParameterTable:
    """QCM暫定デジタイズ表をプロセス内で一度だけ読む。"""
    return load_gamma_g_au_digitized()


@lru_cache(maxsize=1)
def get_simulation_job_manager() -> SimulationJobManager:
    """プロセス内だけで生存するSSE計算ジョブ管理器を返す。"""
    return SimulationJobManager()
