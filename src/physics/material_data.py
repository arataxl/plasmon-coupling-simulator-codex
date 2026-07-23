"""McPeak et al. (2015) を既定とするAu光学定数を扱う。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import numpy as np
from numpy.typing import ArrayLike, NDArray


FloatArray: TypeAlias = NDArray[np.float64]
ComplexArray: TypeAlias = NDArray[np.complex128]
METRES_PER_NANOMETRE = 1e-9


class MaterialDataError(ValueError):
    """材料データの形式または値が不正な場合の例外。"""


class WavelengthOutOfRangeError(MaterialDataError):
    """材料データの有効波長範囲外を要求した場合の例外。"""


@dataclass(frozen=True)
class OpticalConstants:
    """波長に対する複素屈折率の補間可能な表。"""

    wavelength_nm: FloatArray
    refractive_index_n: FloatArray
    extinction_coefficient_k: FloatArray
    source_path: Path

    @property
    def wavelength_range_nm(self) -> tuple[float, float]:
        """補間可能な最小・最大波長をnmで返す。"""
        return (float(self.wavelength_nm[0]), float(self.wavelength_nm[-1]))

    def refractive_index(
        self, wavelength_nm: float | ArrayLike
    ) -> complex | ComplexArray:
        """線形補間した複素屈折率 ``n + i k`` を返す。

        CSVの範囲外は外挿せず、明示的に例外を送出する。
        """
        requested = np.asarray(wavelength_nm, dtype=np.float64)
        if requested.ndim > 1:
            raise MaterialDataError("wavelength_nm must be a scalar or one-dimensional array")
        if requested.size == 0:
            raise MaterialDataError("wavelength_nm must not be empty")
        if not np.all(np.isfinite(requested)):
            raise MaterialDataError("wavelength_nm must contain only finite values")

        lower_nm, upper_nm = self.wavelength_range_nm
        if np.any(requested < lower_nm) or np.any(requested > upper_nm):
            raise WavelengthOutOfRangeError(
                "Au optical constants are available only for "
                f"{lower_nm:g} <= wavelength_nm <= {upper_nm:g}; "
                "extrapolation is not supported"
            )

        n_values = np.interp(requested, self.wavelength_nm, self.refractive_index_n)
        k_values = np.interp(
            requested, self.wavelength_nm, self.extinction_coefficient_k
        )
        result = np.asarray(n_values + 1j * k_values, dtype=np.complex128)
        if result.ndim == 0:
            return complex(result)
        return result

    def refractive_index_at_wavelength_m(
        self, wavelength_m: float | ArrayLike
    ) -> complex | ComplexArray:
        """SI単位（m）の波長をCSVのnm軸へ変換して補間する。"""
        wavelength_m_array = np.asarray(wavelength_m, dtype=np.float64)
        if wavelength_m_array.ndim > 1:
            raise MaterialDataError("wavelength_m must be a scalar or one-dimensional array")
        return self.refractive_index(wavelength_m_array / METRES_PER_NANOMETRE)


def default_au_optical_constants_path() -> Path:
    """リポジトリ同梱のMcPeak et al. (2015) CSVへのパスを返す。"""
    repository_root = Path(__file__).resolve().parents[2]
    return repository_root / "data" / "optical_constants" / "au_mcpeak_2015.csv"


def load_au_optical_constants(path: Path | None = None) -> OpticalConstants:
    """McPeak et al. (2015) を既定とするAu CSVを読み込む。

    明示した ``path`` によりJohnson and Christy (1972) を含む同形式の
    CSVも読み込める。必須列は ``wavelength_nm,n,k`` であり、波長は有限値かつ昇順でなければならない。
    """
    source_path = (path or default_au_optical_constants_path()).resolve()
    if not source_path.is_file():
        raise MaterialDataError(f"Au optical constants CSV was not found: {source_path}")

    wavelengths: list[float] = []
    n_values: list[float] = []
    k_values: list[float] = []
    with source_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {"wavelength_nm", "n", "k"}
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise MaterialDataError(
                "Au optical constants CSV must contain wavelength_nm, n, and k columns"
            )
        for row_number, row in enumerate(reader, start=2):
            try:
                wavelength_nm = float(row["wavelength_nm"])
                refractive_index_n = float(row["n"])
                extinction_coefficient_k = float(row["k"])
            except (KeyError, TypeError, ValueError) as exc:
                raise MaterialDataError(
                    f"invalid numeric value in Au optical constants CSV at row {row_number}"
                ) from exc
            wavelengths.append(wavelength_nm)
            n_values.append(refractive_index_n)
            k_values.append(extinction_coefficient_k)

    wavelength_array = np.asarray(wavelengths, dtype=np.float64)
    n_array = np.asarray(n_values, dtype=np.float64)
    k_array = np.asarray(k_values, dtype=np.float64)
    if wavelength_array.size < 2:
        raise MaterialDataError("Au optical constants CSV must contain at least two rows")
    if not (
        np.all(np.isfinite(wavelength_array))
        and np.all(np.isfinite(n_array))
        and np.all(np.isfinite(k_array))
    ):
        raise MaterialDataError("Au optical constants CSV contains non-finite values")
    if np.any(wavelength_array <= 0) or np.any(np.diff(wavelength_array) <= 0):
        raise MaterialDataError("Au optical constants wavelengths must be positive and strictly increasing")

    return OpticalConstants(
        wavelength_nm=wavelength_array,
        refractive_index_n=n_array,
        extinction_coefficient_k=k_array,
        source_path=source_path,
    )
