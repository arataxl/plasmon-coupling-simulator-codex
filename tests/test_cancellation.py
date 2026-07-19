"""SSEジョブ取消時に部分結果を返さず、ファイルを残さないことを確認する。"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

import src.services.job_manager as job_manager_module
from src.schemas.simulation import (
    LightSourceInput,
    MediumInput,
    ParticleInput,
    SimulationInput,
)
from src.services.job_manager import SimulationJobManager
from src.services.simulation_service import SimulationCancelledError


def _simulation_input() -> SimulationInput:
    return SimulationInput(
        particles=[ParticleInput(diameter_nm=20.0, x_nm=0.0, y_nm=0.0, z_nm=0.0)],
        medium=MediumInput(name="water", refractive_index=1.33),
        light_source=LightSourceInput(
            wavelength_nm=600.0,
            propagation_direction=(0.0, 0.0, 1.0),
            polarization=(1.0, 0.0, 0.0),
        ),
    )


def test_cancellation_discards_partial_data_and_leaves_no_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """取消後は進捗数だけを返し、結果・ファイル・ジョブを残さない。"""
    entered_runner = threading.Event()

    def blocked_runner(
        *args: object,
        cancellation_requested,
        progress_callback,
        **kwargs: object,
    ) -> object:
        del args, kwargs
        progress_callback(1, 2)
        entered_runner.set()
        while not cancellation_requested():
            time.sleep(0.001)
        raise SimulationCancelledError("cancelled by test")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(job_manager_module, "run_simulation_with_progress", blocked_runner)
    manager = SimulationJobManager()
    job_id = manager.start_job(
        _simulation_input(),
        optical_constants=object(),  # type: ignore[arg-type]
        qcm_parameter_table=object(),  # type: ignore[arg-type]
    )
    assert entered_runner.wait(timeout=1.0)
    assert manager.cancel_job(job_id) is True

    async def collect_events() -> list[object]:
        return [event async for event in manager.events_for(job_id)]

    events = asyncio.run(collect_events())
    assert [event.name for event in events] == ["progress", "cancelled"]
    assert events[0].data == {
        "job_id": job_id,
        "completed_points": 1,
        "total_points": 2,
        "fraction": 0.5,
    }
    assert events[1].data == {"job_id": job_id}
    assert not manager.job_exists(job_id)
    assert list(tmp_path.iterdir()) == []
