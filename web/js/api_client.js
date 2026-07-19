window.PlasmonApi = (() => {
  const errorMessageKeyByCode = Object.freeze({
    invalid_input: "api.invalidInput",
    simulation_failed: "api.simulateFailed",
    qcm_metadata_unavailable: "api.qcmMetadataUnavailable",
    material_data_unavailable: "api.materialDataUnavailable",
    qcm_parameter_table_unavailable: "api.qcmParameterTableUnavailable",
    random_cluster_generation_failed: "api.randomClusterUnavailable",
    preset_layout_invalid: "api.presetLayoutInvalid",
    simulation_job_not_found: "api.jobNotFound",
  });

  function t(key, parameters) {
    return window.PlasmonI18n.t(key, parameters);
  }

  function messageForErrorCode(errorCode, fallbackMessage) {
    const translationKey = errorMessageKeyByCode[errorCode];
    return translationKey ? t(translationKey) : fallbackMessage;
  }

  async function parseResponse(response, fallbackMessage) {
    let body;
    try {
      body = await response.json();
    } catch {
      if (!response.ok) {
        throw new Error(fallbackMessage);
      }
      return {};
    }
    if (!response.ok) {
      const errorCode = body.error?.code ?? body.detail?.code;
      throw new Error(messageForErrorCode(errorCode, fallbackMessage));
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
    messageForErrorCode,
    roundLayoutForDisplay,
  };
})();
