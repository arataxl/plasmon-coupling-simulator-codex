"""APIが物理コアへ注入する版管理済みの入力データ。"""

from __future__ import annotations

from functools import lru_cache

from src.io.qcm_parameter_table import load_gamma_g_au_digitized
from src.physics.material_data import OpticalConstants, load_au_optical_constants
from src.physics.qcm import GammaGParameterTable


@lru_cache(maxsize=1)
def get_optical_constants() -> OpticalConstants:
    """Johnson and ChristyのAu光学定数をプロセス内で一度だけ読む。"""
    return load_au_optical_constants()


@lru_cache(maxsize=1)
def get_qcm_parameter_table() -> GammaGParameterTable:
    """QCM暫定デジタイズ表をプロセス内で一度だけ読む。"""
    return load_gamma_g_au_digitized()
