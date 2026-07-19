"""版管理されたQCM暫定デジタイズ表を読み込む。"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from src.physics.qcm import GammaGParameterTable, QcmParameterError


class QcmParameterTableLoadError(QcmParameterError):
    """QCMパラメータ表のファイル形式または値が不正であることを示す。"""


def default_gamma_g_au_digitized_path() -> Path:
    """リポジトリ同梱のAu `gamma_g` 暫定デジタイズCSVへのパスを返す。"""
    repository_root = Path(__file__).resolve().parents[2]
    return repository_root / "data" / "qcm" / "gamma_g_au_digitized.csv"


def load_gamma_g_au_digitized(
    path: Path | None = None,
) -> GammaGParameterTable:
    """Esteban et al. Fig. 2dのAu実線をデジタイズした暫定表を読む。

    CSVは ``separation_angstrom,gamma_g_ev`` 列を必須とする。出典、読取誤差、
    有効範囲は同じディレクトリの ``metadata.yaml`` に版管理される。YAMLは物理層へ
    持ち込まず、この関数も数値CSVだけを読み込む。
    """
    source_path = (path or default_gamma_g_au_digitized_path()).resolve()
    if not source_path.is_file():
        raise QcmParameterTableLoadError(
            f"QCM gamma_g parameter table was not found: {source_path}"
        )

    separations_angstrom: list[float] = []
    gamma_g_ev: list[float] = []
    with source_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {"separation_angstrom", "gamma_g_ev"}
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise QcmParameterTableLoadError(
                "QCM gamma_g CSV must contain separation_angstrom and gamma_g_ev columns"
            )
        for row_number, row in enumerate(reader, start=2):
            try:
                separations_angstrom.append(float(row["separation_angstrom"]))
                gamma_g_ev.append(float(row["gamma_g_ev"]))
            except (KeyError, TypeError, ValueError) as error:
                raise QcmParameterTableLoadError(
                    f"invalid numeric value in QCM gamma_g CSV at row {row_number}"
                ) from error

    try:
        return GammaGParameterTable(
            separation_angstrom=np.asarray(separations_angstrom, dtype=np.float64),
            gamma_g_ev=np.asarray(gamma_g_ev, dtype=np.float64),
        )
    except QcmParameterError as error:
        raise QcmParameterTableLoadError(
            f"invalid QCM gamma_g parameter table: {source_path}"
        ) from error
