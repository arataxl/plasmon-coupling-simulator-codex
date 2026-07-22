"""SSE用の一時的な計算ジョブ、進捗、協調的取消を管理する。"""

from __future__ import annotations

import asyncio
import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Literal

from src.physics.material_data import OpticalConstants
from src.physics.qcm import GammaGParameterTable
from src.schemas.simulation import SimulationRequest
from src.services.simulation_service import (
    SimulationCancelledError,
    SimulationServiceError,
    run_simulation_with_progress,
)


JobEventName = Literal["progress", "complete", "cancelled", "error"]
TERMINAL_STATES = frozenset(("complete", "cancelled", "error"))
TERMINAL_JOB_RETENTION_SECONDS = 60.0


class SimulationJobNotFoundError(KeyError):
    """要求された一時ジョブが存在しない。"""


@dataclass(frozen=True)
class SimulationJobEvent:
    """SSEへ変換する、部分スペクトルを含まないジョブイベント。"""

    name: JobEventName
    data: dict[str, object]


@dataclass
class _SimulationJob:
    job_id: str
    cancellation_requested: threading.Event = field(default_factory=threading.Event)
    events: queue.Queue[SimulationJobEvent] = field(default_factory=queue.Queue)
    state: str = "running"
    discard_when_terminal: bool = False


class SimulationJobManager:
    """結果を永続化せず、完了時だけSSEへ結果を渡すジョブ管理器。

    ワーカースレッドは波長点の境界で取消要求を確認する。計算点の途中でSciPyの線形
    ソルバーを強制停止はしないが、進捗イベントに数値・部分スペクトルを含めず、取消後は
    局所配列を返さず破棄する。完了結果はSSEの一つの ``complete`` イベントにだけ保持し、
    ストリーム終了時にジョブから削除する。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, _SimulationJob] = {}
        self._lock = threading.Lock()

    def start_job(
        self,
        simulation: SimulationRequest,
        *,
        optical_constants: OpticalConstants,
        qcm_parameter_table: GammaGParameterTable,
    ) -> str:
        """ジョブを開始し、SSE購読に使う一意なIDを返す。"""
        job = _SimulationJob(job_id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.job_id] = job
        worker = threading.Thread(
            target=self._run_job,
            kwargs={
                "job": job,
                "simulation": simulation,
                "optical_constants": optical_constants,
                "qcm_parameter_table": qcm_parameter_table,
            },
            name=f"simulation-{job.job_id[:8]}",
            daemon=True,
        )
        worker.start()
        return job.job_id

    def cancel_job(self, job_id: str) -> bool:
        """実行中ジョブへ取消を要求し、受理できた場合だけTrueを返す。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise SimulationJobNotFoundError(job_id)
            if job.state in TERMINAL_STATES:
                return False
            job.state = "cancelling"
            job.cancellation_requested.set()
            return True

    def job_exists(self, job_id: str) -> bool:
        """テストおよびAPIの存在確認用に一時ジョブの有無を返す。"""
        with self._lock:
            return job_id in self._jobs

    def assert_job_exists(self, job_id: str) -> None:
        """SSE開始前に、削除済みでないジョブであることを検証する。"""
        self._get_job(job_id)

    async def events_for(self, job_id: str):
        """指定ジョブの進捗または終端イベントを逐次返す。"""
        job = self._get_job(job_id)
        try:
            while True:
                event = await asyncio.to_thread(job.events.get)
                yield event
                if event.name in {"complete", "cancelled", "error"}:
                    return
        finally:
            self._close_stream(job_id)

    def _get_job(self, job_id: str) -> _SimulationJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise SimulationJobNotFoundError(job_id)
        return job

    def _close_stream(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.state in TERMINAL_STATES:
                self._jobs.pop(job_id, None)
                return
            job.discard_when_terminal = True
            job.state = "cancelling"
            job.cancellation_requested.set()

    def _run_job(
        self,
        *,
        job: _SimulationJob,
        simulation: SimulationRequest,
        optical_constants: OpticalConstants,
        qcm_parameter_table: GammaGParameterTable,
    ) -> None:
        def progress_callback(completed_points: int, total_points: int) -> None:
            if job.cancellation_requested.is_set():
                raise SimulationCancelledError("simulation cancellation was requested")
            job.events.put(
                SimulationJobEvent(
                    name="progress",
                    data={
                        "job_id": job.job_id,
                        "completed_points": completed_points,
                        "total_points": total_points,
                        "fraction": completed_points / total_points,
                    },
                )
            )

        try:
            result = run_simulation_with_progress(
                simulation,
                optical_constants=optical_constants,
                qcm_parameter_table=qcm_parameter_table,
                cancellation_requested=job.cancellation_requested.is_set,
                progress_callback=progress_callback,
            )
            if job.cancellation_requested.is_set():
                raise SimulationCancelledError("simulation cancelled before completion event")
        except SimulationCancelledError:
            self._publish_terminal_event(
                job,
                state="cancelled",
                event=SimulationJobEvent(
                    name="cancelled",
                    data={"job_id": job.job_id},
                ),
            )
        except SimulationServiceError as error:
            self._publish_terminal_event(
                job,
                state="error",
                event=SimulationJobEvent(
                    name="error",
                    data={
                        "job_id": job.job_id,
                        "code": error.error_code,
                        "parameters": error.parameters,
                    },
                ),
            )
        except Exception:
            self._publish_terminal_event(
                job,
                state="error",
                event=SimulationJobEvent(
                    name="error",
                    data={
                        "job_id": job.job_id,
                        "code": "simulation_failed",
                        "parameters": {},
                    },
                ),
            )
        else:
            self._publish_terminal_event(
                job,
                state="complete",
                event=SimulationJobEvent(
                    name="complete",
                    data={
                        "job_id": job.job_id,
                        "result": result.model_dump(mode="json"),
                    },
                ),
            )

    def _publish_terminal_event(
        self,
        job: _SimulationJob,
        *,
        state: str,
        event: SimulationJobEvent,
    ) -> None:
        with self._lock:
            job.state = state
            discard = job.discard_when_terminal
            if discard:
                self._jobs.pop(job.job_id, None)
        if not discard:
            job.events.put(event)
            expiry_timer = threading.Timer(
                TERMINAL_JOB_RETENTION_SECONDS,
                self._discard_terminal_job,
                args=(job.job_id,),
            )
            expiry_timer.daemon = True
            expiry_timer.start()

    def _discard_terminal_job(self, job_id: str) -> None:
        """未購読の完了イベントを短時間で破棄し、メモリに残さない。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.state in TERMINAL_STATES:
                self._jobs.pop(job_id, None)
