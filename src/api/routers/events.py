"""完了スペクトルではなく進捗だけを逐次配信するSSE API。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_simulation_job_manager
from src.services.job_manager import (
    SimulationJobEvent,
    SimulationJobManager,
    SimulationJobNotFoundError,
)


router = APIRouter(tags=["events"])
JobManagerDependency = Annotated[SimulationJobManager, Depends(get_simulation_job_manager)]


def _format_sse(event: SimulationJobEvent) -> str:
    """一つの内部イベントをSSEフレームへ変換する。"""
    serialized_data = json.dumps(
        event.data,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"event: {event.name}\ndata: {serialized_data}\n\n"


@router.get("/simulate/stream/{job_id}")
async def stream_simulation_progress(
    job_id: str,
    job_manager: JobManagerDependency,
) -> StreamingResponse:
    """波長点ごとの進捗と、完了後の結果だけをSSEで配信する。"""
    try:
        job_manager.assert_job_exists(job_id)
    except SimulationJobNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "simulation_job_not_found", "parameters": {}},
        ) from error

    async def event_stream() -> AsyncIterator[str]:
        async for event in job_manager.events_for(job_id):
            yield _format_sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
