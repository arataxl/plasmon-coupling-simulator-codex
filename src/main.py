"""ローカル専用FastAPIアプリケーションの組み立て。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from src.api.error_handlers import register_error_handlers
from src.api.routers.events import router as events_router
from src.api.routers.simulations import router as simulations_router


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPOSITORY_ROOT / "web"
INDEX_FILE = WEB_ROOT / "index.html"


class NoCacheUiStaticFiles(StaticFiles):
    """UIのJavaScript/CSSだけは、ローカル開発時に古い版を再利用させない。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        # StaticFiles には mount 後の相対パスだけが渡される版と、
        # URL パスを渡す版があるため、接頭辞ではなく拡張子で判定する。
        if path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-store"
        return response


def create_app() -> FastAPI:
    """APIと同一オリジンの静的UIを提供するFastAPIアプリを生成する。"""
    if not INDEX_FILE.is_file():
        raise RuntimeError(f"web UI entry point was not found: {INDEX_FILE}")

    application = FastAPI(
        title="Plasmonic Coupling Simulator",
        version="0.2.0",
    )
    register_error_handlers(application)
    application.include_router(simulations_router)
    application.include_router(events_router)
    application.mount("/static", NoCacheUiStaticFiles(directory=WEB_ROOT), name="static")

    @application.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-store"})

    return application


app = create_app()
