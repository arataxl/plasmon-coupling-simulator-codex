"""FastAPIの同期シミュレーションAPIに対するASGI統合試験。"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping
from typing import Any

import pytest

from src.main import app
from src.services.simulation_service import QcmMetadataUnavailableError
import src.services.simulation_service as simulation_service


def _simulation_payload(*, gap_nm: float = 5.0) -> dict[str, Any]:
    diameter_nm = 20.0
    return {
        "material": "Au",
        "particles": [
            {"diameter_nm": diameter_nm, "x_nm": 0.0, "y_nm": 0.0, "z_nm": 0.0},
            {
                "diameter_nm": diameter_nm,
                "x_nm": diameter_nm + gap_nm,
                "y_nm": 0.0,
                "z_nm": 0.0,
            },
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


def _post_json(path: str, payload: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
    request_body = json.dumps(payload).encode("utf-8")
    messages: list[dict[str, Any]] = []
    sent_request = False

    async def receive() -> dict[str, Any]:
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": request_body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(request_body)).encode("ascii")),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    response_start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(response_start["status"]), json.loads(response_body.decode("utf-8"))


def test_simulate_returns_spectrum_and_reference_cross_sections() -> None:
    status_code, response = _post_json("/simulate", _simulation_payload())

    assert status_code == 200
    assert response["cross_sections"]["wavelength_nm"] == 600.0
    assert set(response["cross_sections"]) == {
        "wavelength_nm",
        "c_ext_m2",
        "c_sca_m2",
        "c_abs_m2",
        "geometric_cross_section_m2",
        "q_ext",
        "q_sca",
        "q_abs",
    }
    assert response["spectrum"]["wavelength_nm"] == [580.0, 600.0, 620.0]
    assert len(response["spectrum"]["c_ext_m2"]) == 3
    assert len(response["spectrum"]["q_ext"]) == 3
    assert response["provenance"]["model_name"] == "FCDA-CDA with QCM auxiliary bridge dipoles"
    assert response["qcm_metadata"]["qcm_applied"] is False


def test_simulate_includes_complete_qcm_metadata_for_qcm_gap() -> None:
    status_code, response = _post_json("/simulate", _simulation_payload(gap_nm=0.5))

    assert status_code == 200
    metadata = response["qcm_metadata"]
    assert metadata["qcm_applied"] is True
    assert metadata["qcm_parameter_status"] == "provisional_digitized"
    assert metadata["qcm_figure"] == "Fig. 2d"
    assert metadata["qcm_curve"] == "Au jellium, blue solid line"
    assert metadata["qcm_calibration_points"] == "not provided with the digitized data"
    assert metadata["qcm_reading_uncertainty"] == "approximately 5-10%"


def test_simulate_rejects_schema_violation_with_a_clear_422_error() -> None:
    payload = _simulation_payload()
    payload["particles"][0]["diameter_nm"] = 100.1

    status_code, response = _post_json("/simulate", payload)

    assert status_code == 422
    assert response["error"]["code"] == "invalid_input"
    assert response["error"]["details"]


def test_simulate_rejects_gap_below_model_limit_before_calculation() -> None:
    status_code, response = _post_json("/simulate", _simulation_payload(gap_nm=0.3))

    assert status_code == 422
    assert response["error"]["code"] == "invalid_input"
    assert "quantum tunnelling" in json.dumps(response["error"])


def test_simulate_returns_explicit_error_when_qcm_metadata_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_metadata_error(*_: object) -> object:
        raise QcmMetadataUnavailableError("QCM provenance fields are unavailable")

    monkeypatch.setattr(
        simulation_service,
        "build_qcm_result_metadata",
        raise_metadata_error,
    )

    status_code, response = _post_json("/simulate", _simulation_payload(gap_nm=0.5))

    assert status_code == 503
    assert response["error"] == {
        "code": "qcm_metadata_unavailable",
        "message": "QCM provenance fields are unavailable",
    }


def test_synchronous_endpoint_retains_the_301_point_limit() -> None:
    payload = _simulation_payload()
    payload["spectrum"] = {
        "start_wavelength_nm": 200.0,
        "end_wavelength_nm": 1500.0,
        "step_nm": 4.0,
    }

    status_code, response = _post_json("/simulate", payload)

    assert status_code == 422
    assert response["error"]["code"] == "simulation_failed"
    assert "synchronous API limit of 301 points" in response["error"]["message"]


def test_random_cluster_layout_uses_a_valid_seeded_3d_configuration() -> None:
    payload = {
        "particle_count": 5,
        "mean_diameter_nm": 20.0,
        "minimum_surface_gap_nm": 5.0,
        "maximum_surface_gap_nm": 250.0,
        "seed": 20260720,
    }

    status_code, response = _post_json("/layouts/random-cluster", payload)

    assert status_code == 200
    particles = response["particles"]
    assert len(particles) == payload["particle_count"]
    assert all(
        math.isclose(value * 10.0, round(value * 10.0), abs_tol=1.0e-12)
        for particle in particles
        for value in (particle["x_nm"], particle["y_nm"], particle["z_nm"])
    )
    for left_index, left in enumerate(particles):
        for right in particles[left_index + 1 :]:
            center_distance_nm = math.dist(
                (left["x_nm"], left["y_nm"], left["z_nm"]),
                (right["x_nm"], right["y_nm"], right["z_nm"]),
            )
            surface_gap_nm = center_distance_nm - (
                left["diameter_nm"] + right["diameter_nm"]
            ) / 2.0
            assert surface_gap_nm > payload["minimum_surface_gap_nm"]
            assert surface_gap_nm <= payload["maximum_surface_gap_nm"] + 1.0e-12


def test_random_cluster_layout_rejects_a_reversed_surface_gap_range() -> None:
    payload = {
        "particle_count": 5,
        "mean_diameter_nm": 20.0,
        "minimum_surface_gap_nm": 5.0,
        "maximum_surface_gap_nm": 4.9,
        "seed": 20260720,
    }

    status_code, response = _post_json("/layouts/random-cluster", payload)

    assert status_code == 422
    assert response["error"]["code"] == "invalid_input"
    assert "maximum_surface_gap_nm" in json.dumps(response["error"]["details"])


def test_random_cluster_layout_can_generate_a_qcm_range_without_crossing_bounds() -> None:
    payload = {
        "particle_count": 2,
        "mean_diameter_nm": 20.0,
        "minimum_surface_gap_nm": 0.5,
        "maximum_surface_gap_nm": 0.9,
        "seed": 20260720,
    }

    status_code, response = _post_json("/layouts/random-cluster", payload)

    assert status_code == 200
    first, second = response["particles"]
    surface_gap_nm = math.dist(
        (first["x_nm"], first["y_nm"], first["z_nm"]),
        (second["x_nm"], second["y_nm"], second["z_nm"]),
    ) - (first["diameter_nm"] + second["diameter_nm"]) / 2.0
    assert 0.5 <= surface_gap_nm <= 0.9


def test_display_layout_endpoint_rounds_triangle_coordinates_without_breaking_gap_limit() -> None:
    payload = {
        "particles": [
            {"diameter_nm": 20.0, "x_nm": 0.0, "y_nm": 0.0, "z_nm": 0.0},
            {"diameter_nm": 20.0, "x_nm": 30.0, "y_nm": 0.0, "z_nm": 0.0},
            {
                "diameter_nm": 20.0,
                "x_nm": 15.0,
                "y_nm": 25.980762113533157,
                "z_nm": 0.0,
            },
        ]
    }

    status_code, response = _post_json("/layouts/round-for-display", payload)

    assert status_code == 200
    particles = response["particles"]
    assert particles[2]["y_nm"] == 26.0
    assert all(
        math.isclose(value * 10.0, round(value * 10.0), abs_tol=1.0e-12)
        for particle in particles
        for value in (particle["x_nm"], particle["y_nm"], particle["z_nm"])
    )
    for left_index, left in enumerate(particles):
        for right in particles[left_index + 1 :]:
            center_distance_nm = math.dist(
                (left["x_nm"], left["y_nm"], left["z_nm"]),
                (right["x_nm"], right["y_nm"], right["z_nm"]),
            )
            surface_gap_nm = center_distance_nm - (
                left["diameter_nm"] + right["diameter_nm"]
            ) / 2.0
            assert surface_gap_nm >= 0.5
