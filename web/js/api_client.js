window.PlasmonApi = (() => {
  async function parseResponse(response, fallbackMessage) {
    const body = await response.json();
    if (!response.ok) {
      const message = body.error?.message ?? body.detail ?? fallbackMessage;
      throw new Error(message);
    }
    return body;
  }

  async function simulate(payload) {
    const response = await fetch("/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return parseResponse(response, "計算リクエストに失敗しました。");
  }

  async function startSimulationJob(payload) {
    const response = await fetch("/simulate/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return parseResponse(response, "進捗付き計算を開始できませんでした。");
  }

  async function cancelSimulationJob(jobId) {
    const response = await fetch(`/simulate/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
    return parseResponse(response, "取消要求を送信できませんでした。");
  }

  async function generateRandomCluster(payload) {
    const response = await fetch("/layouts/random-cluster", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return parseResponse(response, "ランダム配置を生成できませんでした。");
  }

  return {
    simulate,
    startSimulationJob,
    cancelSimulationJob,
    generateRandomCluster,
  };
})();
