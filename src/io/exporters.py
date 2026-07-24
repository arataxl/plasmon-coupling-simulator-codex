"""サーバーへ保存しない、再現可能なCSV/JSON出力の組立て。"""

from __future__ import annotations

import csv
import io
import json

from src.schemas.result import SimulationResult


CSV_HEADER = (
    "wavelength_nm",
    "c_ext_m2",
    "c_sca_m2",
    "c_abs_m2",
    "q_ext",
    "q_sca",
    "q_abs",
    "geometric_cross_section_m2",
)


def simulation_result_to_csv(result: SimulationResult) -> str:
    """スペクトルを固定列順・LF改行でCSV文字列へ変換する。"""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    spectrum = result.spectrum
    for values in zip(
        spectrum.wavelength_nm,
        spectrum.c_ext_m2,
        spectrum.c_sca_m2,
        spectrum.c_abs_m2,
        spectrum.q_ext,
        spectrum.q_sca,
        spectrum.q_abs,
        strict=True,
    ):
        writer.writerow((*values, spectrum.geometric_cross_section_m2))
    return output.getvalue()


def simulation_result_to_json(result: SimulationResult) -> str:
    """キー順・空白なしの固定表現でJSON文字列へ変換する。"""
    return (
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
