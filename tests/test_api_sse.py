"""SSEの進捗配信と完了時一括結果のASGI統合試験。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from src.main import app


def _simulation_payload() -> dict[str, Any]:
    return {
        "material": "Au",
        "particles": [
            {"diameter_nm": 20.0, "x_nm": 0.0, "y_nm": 0.0, "z_nm": 0.0},
            {"diameter_nm": 20.0, "x_nm": 25.0, "y_nm": 0.0, "z_nm": 0.0},
        ],
        "medium": {"name": "water", "refractive_index": 1.33},
        "light_source": {
            "wavelength_nm": 600.0,
            "propagation_direction": [0.0, 0.0, 1.0],
            "polarization": [1.0, 0.0, 0.0],
        },
        "spectrum": {
            "start_wavelength_nm": 580.0,
            "end_wavelength_nm": 620.0,
            "step_nm": 20.0,
        },
    }


def _large_classical_payload() -> dict[str, Any]:
    payload = _simulation_payload()
    payload["particles"] = [
        {
            "diameter_nm": 20.0,
            "x_nm": float(index * 26.0),
            "y_nm": 0.0,
            "z_nm": 0.0,
        }
        for index in range(50)
    ]
    payload["spectrum"] = {
        "start_wavelength_nm": 600.0,
        "end_wavelength_nm": 600.0,
        "step_nm": 10.0,
    }
    return payload


def test_ui_entry_point_and_mutable_ui_assets_disable_http_caching() -> None:
    """ローカルUIは、更新後に古いJavaScript/CSSを混在させない。"""
    index_status, _, index_headers = asyncio.run(_request("GET", "/"))
    script_status, _, script_headers = asyncio.run(_request("GET", "/static/js/app.js"))
    stylesheet_status, _, stylesheet_headers = asyncio.run(
        _request("GET", "/static/css/app.css")
    )

    assert index_status == 200
    assert script_status == 200
    assert stylesheet_status == 200
    assert (b"cache-control", b"no-store") in index_headers
    assert (b"cache-control", b"no-store") in script_headers
    assert (b"cache-control", b"no-store") in stylesheet_headers


async def _request(
    method: str,
    path: str,
    *,
    payload: Mapping[str, Any] | None = None,
) -> tuple[int, bytes, list[tuple[bytes, bytes]]]:
    request_body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    messages: list[dict[str, Any]] = []
    sent_request = False
    wait_for_disconnect = asyncio.Event()

    async def receive() -> dict[str, Any]:
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": request_body, "more_body": False}
        await wait_for_disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    headers = []
    if payload is not None:
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(request_body)).encode("ascii")),
        ]
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    response_start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(response_start["status"]), response_body, response_start["headers"]


def _parse_sse(body: bytes) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.decode("utf-8").strip().split("\n\n"):
        lines = dict(line.split(": ", maxsplit=1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_sse_emits_point_progress_and_only_returns_spectrum_on_completion() -> None:
    """進捗には数値列を含めず、完了イベントだけに全スペクトルを持たせる。"""
    start_status, start_body, _ = asyncio.run(
        _request("POST", "/simulate/jobs", payload=_simulation_payload())
    )
    assert start_status == 202
    job_id = json.loads(start_body.decode("utf-8"))["job_id"]

    stream_status, stream_body, headers = asyncio.run(
        _request("GET", f"/simulate/stream/{job_id}")
    )
    assert stream_status == 200
    assert (b"content-type", b"text/event-stream; charset=utf-8") in headers
    events = _parse_sse(stream_body)
    progress_events = [data for name, data in events if name == "progress"]
    complete_events = [data for name, data in events if name == "complete"]
    assert len(progress_events) == 3
    assert len(complete_events) == 1
    assert progress_events[-1]["fraction"] == 1.0
    assert all("result" not in event for event in progress_events)
    assert complete_events[0]["result"]["spectrum"]["wavelength_nm"] == [580.0, 600.0, 620.0]


def test_sse_completes_a_fifty_particle_classical_cda_calculation() -> None:
    """21〜50粒子は同期APIではなくSSE経路でのみ完了させる。"""
    start_status, start_body, _ = asyncio.run(
        _request("POST", "/simulate/jobs", payload=_large_classical_payload())
    )
    assert start_status == 202
    job_id = json.loads(start_body.decode("utf-8"))["job_id"]

    stream_status, stream_body, _ = asyncio.run(
        _request("GET", f"/simulate/stream/{job_id}")
    )

    assert stream_status == 200
    events = _parse_sse(stream_body)
    complete_events = [data for name, data in events if name == "complete"]
    assert len(complete_events) == 1
    result = complete_events[0]["result"]
    assert result["qcm_metadata"]["qcm_applied"] is False
    assert result["spectrum"]["wavelength_nm"] == [600.0]
