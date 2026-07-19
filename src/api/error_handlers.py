"""物理・スキーマ例外をUIが表示できるHTTPエラーへ変換する。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.physics.material_data import MaterialDataError
from src.physics.qcm import QcmParameterError
from src.services.simulation_service import (
    QcmMetadataUnavailableError,
    SimulationServiceError,
)


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: object | None = None,
) -> JSONResponse:
    """全APIエラーで共通のJSON構造を返す。"""
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


def register_error_handlers(app: FastAPI) -> None:
    """アプリに、入力・計算・QCM来歴の明示的なエラー処理を登録する。"""

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del request
        return _error_response(
            status_code=422,
            code="invalid_input",
            message="入力値を確認してください。",
            details=jsonable_encoder(error.errors()),
        )

    @app.exception_handler(QcmMetadataUnavailableError)
    async def handle_qcm_metadata_error(
        request: Request,
        error: QcmMetadataUnavailableError,
    ) -> JSONResponse:
        del request
        return _error_response(
            status_code=error.status_code,
            code=error.error_code,
            message=str(error),
        )

    @app.exception_handler(SimulationServiceError)
    async def handle_simulation_service_error(
        request: Request,
        error: SimulationServiceError,
    ) -> JSONResponse:
        del request
        return _error_response(
            status_code=error.status_code,
            code=error.error_code,
            message=str(error),
        )

    @app.exception_handler(MaterialDataError)
    async def handle_material_data_error(
        request: Request,
        error: MaterialDataError,
    ) -> JSONResponse:
        del request
        return _error_response(
            status_code=503,
            code="material_data_unavailable",
            message=str(error),
        )

    @app.exception_handler(QcmParameterError)
    async def handle_qcm_parameter_error(
        request: Request,
        error: QcmParameterError,
    ) -> JSONResponse:
        del request
        return _error_response(
            status_code=503,
            code="qcm_parameter_table_unavailable",
            message=str(error),
        )
