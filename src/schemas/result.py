"""計算結果に添付するQCM出典・近似情報のスキーマ。"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QcmResultMetadata(BaseModel):
    """QCM適用結果に必須の再現性メタデータ。

    JSON/CSV出力機能は後続で実装する。この型は出力層が、暫定デジタイズ表の出典と
    CDAへの縮約近似を落とさずに保持するための契約である。
    """

    model_config = ConfigDict(extra="forbid")

    qcm_applied: bool
    qcm_parameter_status: Literal["provisional_digitized"] | None = None
    qcm_parameter_source: str | None = None
    qcm_calibration_points: str | None = None
    qcm_reading_uncertainty: str | None = None
    qcm_figure: str | None = None
    qcm_curve: str | None = None
    qcm_interpolation: str | None = None
    qcm_layer_count: int | None = Field(default=None, ge=3, le=5)
    qcm_plasma_energy_ev: float | None = Field(default=None, gt=0)
    qcm_bulk_damping_energy_ev: float | None = Field(default=None, gt=0)
    qcm_cda_model: str | None = None
    qcm_model_error_estimate: str | None = None
    qcm_classical_limit_pair_count: int = Field(default=0, ge=0)
    qcm_max_relative_permittivity_contrast: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_provenance_when_applied(self) -> Self:
        if not self.qcm_applied:
            return self
        required_fields = (
            "qcm_parameter_status",
            "qcm_parameter_source",
            "qcm_calibration_points",
            "qcm_reading_uncertainty",
            "qcm_figure",
            "qcm_curve",
            "qcm_interpolation",
            "qcm_layer_count",
            "qcm_plasma_energy_ev",
            "qcm_bulk_damping_energy_ev",
            "qcm_cda_model",
            "qcm_model_error_estimate",
        )
        missing_fields = [
            field_name
            for field_name in required_fields
            if getattr(self, field_name) is None
        ]
        if missing_fields:
            raise ValueError(
                "QCM-applied results require metadata fields: "
                + ", ".join(missing_fields)
            )
        return self
