window.PlasmonApi = (() => {
  function t(key, parameters) {
    return window.PlasmonI18n.t(key, parameters);
  }

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
    return parseResponse(response, t("api.simulateFailed"));
  }

  async function startSimulationJob(payload) {
    const response = await fetch("/simulate/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return parseResponse(response, t("api.jobStartFailed"));
  }

  async function cancelSimulationJob(jobId) {
    const response = await fetch(`/simulate/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
    return parseResponse(response, t("api.cancelFailed"));
  }

  async function generateRandomCluster(payload) {
    const response = await fetch("/layouts/random-cluster", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return parseResponse(response, t("api.randomFailed"));
  }

  async function roundLayoutForDisplay(particles) {
    const response = await fetch("/layouts/round-for-display", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ particles }),
    });
    return parseResponse(response, t("api.roundFailed"));
  }

  return {
    simulate,
    startSimulationJob,
    cancelSimulationJob,
    generateRandomCluster,
    roundLayoutForDisplay,
  };
})();
