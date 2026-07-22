window.PlasmonApi = (() => {
  const errorMessageKeyByCode = Object.freeze({
    invalid_input: "api.invalidInput",
    simulation_failed: "api.simulateFailed",
    large_cda_requires_stream: "api.largeCdaRequiresStream",
    qcm_metadata_unavailable: "api.qcmMetadataUnavailable",
    material_data_unavailable: "api.materialDataUnavailable",
    qcm_parameter_table_unavailable: "api.qcmParameterTableUnavailable",
    random_cluster_generation_failed: "api.randomClusterUnavailable",
    preset_layout_invalid: "api.presetLayoutInvalid",
    simulation_job_not_found: "api.jobNotFound",
  });

  function errorForCode(errorCode, fallbackKey, parameters = {}) {
    return window.PlasmonI18n.createLocalizedError(
      errorMessageKeyByCode[errorCode] ?? fallbackKey,
      parameters,
    );
  }

  async function parseResponse(response, fallbackKey) {
    let body;
    try {
      body = await response.json();
    } catch {
      if (!response.ok) {
        throw errorForCode(undefined, fallbackKey);
      }
      return {};
    }
    if (!response.ok) {
      const errorCode = body.error?.code ?? body.detail?.code;
      const parameters = body.error?.parameters ?? body.detail?.parameters ?? {};
      throw errorForCode(errorCode, fallbackKey, parameters);
    }
    return body;
  }

  async function request(url, options) {
    try {
      return await fetch(url, options);
    } catch {
      throw window.PlasmonI18n.createLocalizedError("api.networkFailed");
    }
  }

  async function simulate(payload) {
    const response = await request("/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return parseResponse(response, "api.simulateFailed");
  }

  async function startSimulationJob(payload) {
    const response = await request("/simulate/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return parseResponse(response, "api.jobStartFailed");
  }

  async function cancelSimulationJob(jobId) {
    const response = await request(`/simulate/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
    return parseResponse(response, "api.cancelFailed");
  }

  async function generateRandomCluster(payload) {
    const response = await request("/layouts/random-cluster", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return parseResponse(response, "api.randomFailed");
  }

  async function roundLayoutForDisplay(particles) {
    const response = await request("/layouts/round-for-display", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ particles }),
    });
    return parseResponse(response, "api.roundFailed");
  }

  return {
    simulate,
    startSimulationJob,
    cancelSimulationJob,
    errorForCode,
    generateRandomCluster,
    roundLayoutForDisplay,
  };
})();
