window.PlasmonProgress = (() => {
  let activeJob = null;

  function closeActiveJob(jobId) {
    if (!activeJob || activeJob.jobId !== jobId) {
      return;
    }
    activeJob.source.close();
    activeJob = null;
  }

  async function start(payload, handlers) {
    if (activeJob) {
      throw new Error("別の計算が実行中です。");
    }
    const { job_id: jobId } = await window.PlasmonApi.startSimulationJob(payload);
    const source = new EventSource(`/simulate/stream/${encodeURIComponent(jobId)}`);
    activeJob = { jobId, source, terminal: false };

    source.addEventListener("progress", (event) => {
      const data = JSON.parse(event.data);
      handlers.onProgress(data);
    });
    source.addEventListener("complete", (event) => {
      const data = JSON.parse(event.data);
      if (!activeJob || activeJob.jobId !== jobId) {
        return;
      }
      activeJob.terminal = true;
      closeActiveJob(jobId);
      handlers.onComplete(data.result);
    });
    source.addEventListener("cancelled", (event) => {
      const data = JSON.parse(event.data);
      if (!activeJob || activeJob.jobId !== jobId) {
        return;
      }
      activeJob.terminal = true;
      closeActiveJob(jobId);
      handlers.onCancelled(data);
    });
    source.addEventListener("error", (event) => {
      if (!event.data || !activeJob || activeJob.jobId !== jobId) {
        return;
      }
      const data = JSON.parse(event.data);
      activeJob.terminal = true;
      closeActiveJob(jobId);
      handlers.onError(new Error(data.message));
    });
    source.onerror = () => {
      if (!activeJob || activeJob.jobId !== jobId || activeJob.terminal) {
        return;
      }
      closeActiveJob(jobId);
      handlers.onError(new Error("進捗ストリームとの接続が切れました。"));
    };
    return jobId;
  }

  async function cancel() {
    if (!activeJob) {
      return false;
    }
    const { cancellation_requested: cancellationRequested } =
      await window.PlasmonApi.cancelSimulationJob(activeJob.jobId);
    return cancellationRequested;
  }

  function isActive() {
    return activeJob !== null;
  }

  return { start, cancel, isActive };
})();
