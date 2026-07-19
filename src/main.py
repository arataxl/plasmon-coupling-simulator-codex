"""ローカル専用FastAPIアプリケーションの組み立て。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.error_handlers import register_error_handlers
from src.api.routers.simulations import router as simulations_router


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPOSITORY_ROOT / "web"
INDEX_FILE = WEB_ROOT / "index.html"


def create_app() -> FastAPI:
    """APIと同一オリジンの静的UIを提供するFastAPIアプリを生成する。"""
    if not INDEX_FILE.is_file():
        raise RuntimeError(f"web UI entry point was not found: {INDEX_FILE}")

    application = FastAPI(
        title="Plasmonic Coupling Simulator",
        version="0.1.0",
    )
    register_error_handlers(application)
    application.include_router(simulations_router)
    application.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")

    @application.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(INDEX_FILE)

    return application


app = create_app()
