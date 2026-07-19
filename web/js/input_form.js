window.PlasmonInputForm = (() => {
  const maximumParticleCount = 20;
  const minimumDiameterNm = 2;
  const maximumDiameterNm = 100;
  const minimumGapNm = 0.5;
  const defaultCameraEye = Object.freeze({ x: 1.9, y: 1.9, z: 1.45 });
  const defaultCameraDistance = Math.hypot(
    defaultCameraEye.x,
    defaultCameraEye.y,
    defaultCameraEye.z,
  );
  const mediumPresets = {
    water: { name: "water", refractiveIndex: 1.33 },
    ethanol: { name: "ethanol", refractiveIndex: 1.361 },
  };
  let particles = [];
  let previewState = null;

  function t(key, parameters) {
    return window.PlasmonI18n.t(key, parameters);
  }

  function numberFromInput(input) {
    const value = input.value.trim();
    return value === "" ? Number.NaN : Number(value);
  }

  function numberValue(id) {
    return numberFromInput(document.getElementById(id));
  }

  function formatFormValue(value, field) {
    if (!Number.isFinite(value)) {
      return "";
    }
    if (["x_nm", "y_nm", "z_nm"].includes(field)) {
      return value.toFixed(1);
    }
    return String(value);
  }

  function updateMediumInput() {
    const preset = document.getElementById("medium-preset").value;
    const refractiveIndex = document.getElementById("medium-refractive-index");
    if (preset === "custom") {
      refractiveIndex.readOnly = false;
      return;
    }
    refractiveIndex.value = mediumPresets[preset].refractiveIndex;
    refractiveIndex.readOnly = true;
  }

  function readParticles() {
    return Array.from(document.querySelectorAll("#particle-rows tr")).map((row) => ({
      diameter_nm: numberFromInput(row.querySelector('[data-field="diameter_nm"]')),
      x_nm: numberFromInput(row.querySelector('[data-field="x_nm"]')),
      y_nm: numberFromInput(row.querySelector('[data-field="y_nm"]')),
      z_nm: numberFromInput(row.querySelector('[data-field="z_nm"]')),
    }));
  }

  function validateParticles(candidateParticles) {
    const errors = [];
    const warnings = [];
    if (candidateParticles.length < 1 || candidateParticles.length > maximumParticleCount) {
      errors.push(t("validation.particleCount", { maximumParticleCount }));
      return { errors, warnings };
    }
    candidateParticles.forEach((particle, index) => {
      const label = t("validation.particleLabel", { index: index + 1 });
      if (!Number.isFinite(particle.diameter_nm)) {
        errors.push(t("validation.diameterRequired", { label }));
      } else if (
        particle.diameter_nm < minimumDiameterNm ||
        particle.diameter_nm > maximumDiameterNm
      ) {
        errors.push(
          t("validation.diameterRange", {
            label,
            minimumDiameterNm,
            maximumDiameterNm,
          }),
        );
      }
      ["x_nm", "y_nm", "z_nm"].forEach((field) => {
        if (!Number.isFinite(particle[field])) {
          errors.push(
            t("validation.coordinateRequired", {
              label,
              axis: field.slice(0, 1),
            }),
          );
        }
      });
    });
    if (errors.length > 0) {
      return { errors, warnings };
    }
    for (let left = 0; left < candidateParticles.length; left += 1) {
      for (let right = left + 1; right < candidateParticles.length; right += 1) {
        const first = candidateParticles[left];
        const second = candidateParticles[right];
        const centerDistanceNm = Math.hypot(
          first.x_nm - second.x_nm,
          first.y_nm - second.y_nm,
          first.z_nm - second.z_nm,
        );
        const surfaceGapNm = centerDistanceNm - (first.diameter_nm + second.diameter_nm) / 2;
        const pairLabel = t("validation.pairLabel", {
          leftIndex: left + 1,
          rightIndex: right + 1,
        });
        const formattedSurfaceGapNm = surfaceGapNm.toFixed(3);
        if (surfaceGapNm < minimumGapNm - 1e-12) {
          errors.push(
            t("validation.gapBelow", { pairLabel, surfaceGapNm: formattedSurfaceGapNm }),
          );
        } else if (surfaceGapNm < 1.0) {
          warnings.push(
            t("validation.gapQcm", { pairLabel, surfaceGapNm: formattedSurfaceGapNm }),
          );
        } else if (surfaceGapNm <= 5.0) {
          warnings.push(
            t("validation.gapCda", { pairLabel, surfaceGapNm: formattedSurfaceGapNm }),
          );
        }
      }
    }
    return { errors, warnings };
  }

  function renderValidation() {
    const result = validateParticles(readParticles());
    const target = document.getElementById("geometry-validation");
    target.classList.remove("has-error", "has-warning");
    if (result.errors.length > 0) {
      target.textContent = result.errors.join(" ");
      target.classList.add("has-error");
    } else if (result.warnings.length > 0) {
      target.textContent = result.warnings.join(" ");
      target.classList.add("has-warning");
    } else {
      target.textContent = t("validation.valid");
    }
    return result;
  }

  function axisRange(values, maximumDiameterNm) {
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const span = Math.max(maximum - minimum, maximumDiameterNm, 1.0);
    const padding = Math.max(span * 0.35, maximumDiameterNm * 0.9, 8.0);
    return [minimum - padding, maximum + padding];
  }

  function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), maximum);
  }

  function cameraDistance(eye) {
    if (!eye || ![eye.x, eye.y, eye.z].every(Number.isFinite)) {
      return defaultCameraDistance;
    }
    return Math.hypot(eye.x, eye.y, eye.z);
  }

  function cameraEyeFromRelayout(relayoutData, graphElement) {
    const camera = relayoutData["scene.camera"];
    if (camera?.eye && [camera.eye.x, camera.eye.y, camera.eye.z].every(Number.isFinite)) {
      return camera.eye;
    }
    const eventEye = {
      x: relayoutData["scene.camera.eye.x"],
      y: relayoutData["scene.camera.eye.y"],
      z: relayoutData["scene.camera.eye.z"],
    };
    if ([eventEye.x, eventEye.y, eventEye.z].every(Number.isFinite)) {
      return eventEye;
    }
    const layoutEye = graphElement.layout?.scene?.camera?.eye;
    if (layoutEye && [layoutEye.x, layoutEye.y, layoutEye.z].every(Number.isFinite)) {
      return layoutEye;
    }
    return defaultCameraEye;
  }

  function markerSizesForZoom(state, zoomScale) {
    return state.baseMarkerSizes.map((size) => clamp(size * zoomScale, 10, 148));
  }

  function updatePreviewForCamera(relayoutData, graphElement) {
    const cameraChanged = Object.keys(relayoutData).some(
      (key) => key === "scene.camera" || key.startsWith("scene.camera.eye"),
    );
    if (!cameraChanged || !previewState || !window.Plotly) {
      return;
    }
    const nextDistance = cameraDistance(cameraEyeFromRelayout(relayoutData, graphElement));
    if (Math.abs(nextDistance - previewState.cameraDistance) < 1e-4) {
      return;
    }
    previewState.cameraDistance = nextDistance;
    const zoomScale = clamp(defaultCameraDistance / nextDistance, 0.58, 2.35);
    const markerSizes = markerSizesForZoom(previewState, zoomScale);
    const labelSize = Math.round(clamp(12 * Math.sqrt(zoomScale), 10, 18));
    const tickFontSize = Math.round(clamp(10 * Math.sqrt(zoomScale), 9, 15));
    const axisTitleFontSize = Math.round(clamp(12 * Math.sqrt(zoomScale), 10, 18));

    void window.Plotly.restyle(
      graphElement,
      {
        "marker.size": [markerSizes],
        "textfont.size": [labelSize],
      },
      [0],
    );
    void window.Plotly.relayout(graphElement, {
      "scene.xaxis.tickfont.size": tickFontSize,
      "scene.yaxis.tickfont.size": tickFontSize,
      "scene.zaxis.tickfont.size": tickFontSize,
      "scene.xaxis.title.font.size": axisTitleFontSize,
      "scene.yaxis.title.font.size": axisTitleFontSize,
      "scene.zaxis.title.font.size": axisTitleFontSize,
    });
  }

  function attachPreviewRelayoutHandler(graphElement) {
    if (graphElement.__plasmonRelayoutHandler && typeof graphElement.removeListener === "function") {
      graphElement.removeListener("plotly_relayout", graphElement.__plasmonRelayoutHandler);
    }
    graphElement.__plasmonRelayoutHandler = (relayoutData) => {
      updatePreviewForCamera(relayoutData, graphElement);
    };
    if (typeof graphElement.on === "function") {
      graphElement.on("plotly_relayout", graphElement.__plasmonRelayoutHandler);
    }
  }

  function renderPreview() {
    const graphElement = document.getElementById("geometry-preview");
    const finiteParticles = readParticles().filter((particle) =>
      [particle.diameter_nm, particle.x_nm, particle.y_nm, particle.z_nm].every(Number.isFinite),
    );
    if (!window.Plotly || !graphElement || finiteParticles.length === 0) {
      previewState = null;
      return;
    }
    const maximumDiameter = Math.max(...finiteParticles.map((particle) => particle.diameter_nm));
    const xValues = finiteParticles.map((particle) => particle.x_nm);
    const yValues = finiteParticles.map((particle) => particle.y_nm);
    const zValues = finiteParticles.map((particle) => particle.z_nm);
    const xRange = axisRange(xValues, maximumDiameter);
    const yRange = axisRange(yValues, maximumDiameter);
    const zRange = axisRange(zValues, maximumDiameter);
    const viewSpan = Math.max(
      xRange[1] - xRange[0],
      yRange[1] - yRange[0],
      zRange[1] - zRange[0],
    );
    const baseMarkerSizes = finiteParticles.map((particle) =>
      clamp((particle.diameter_nm / viewSpan) * 190, 10, 96),
    );
    previewState = {
      baseMarkerSizes,
      cameraDistance: defaultCameraDistance,
    };

    const plotPromise = window.Plotly.react(
      graphElement,
      [
        {
          type: "scatter3d",
          mode: "markers+text",
          x: xValues,
          y: yValues,
          z: zValues,
          text: finiteParticles.map((_, index) => ` ${index + 1}`),
          customdata: finiteParticles.map((particle) => [particle.diameter_nm]),
          textposition: "top center",
          textfont: { color: "#17324d", size: 12 },
          marker: {
            size: baseMarkerSizes,
            sizemode: "diameter",
            sizeref: 1,
            sizemin: 10,
            color: "#d69e2e",
            line: { color: "#6b4200", width: 1.5 },
            opacity: 0.9,
          },
          hovertemplate: t("preview.hover"),
        },
      ],
      {
        margin: { t: 34, r: 32, b: 62, l: 64 },
        scene: {
          xaxis: {
            title: { text: t("preview.xAxis"), font: { size: 12 } },
            range: xRange,
            tickfont: { size: 10 },
            nticks: 5,
            gridcolor: "#d6e2ef",
            backgroundcolor: "#f8fbff",
          },
          yaxis: {
            title: { text: t("preview.yAxis"), font: { size: 12 } },
            range: yRange,
            tickfont: { size: 10 },
            nticks: 5,
            gridcolor: "#d6e2ef",
            backgroundcolor: "#f8fbff",
          },
          zaxis: {
            title: { text: t("preview.zAxis"), font: { size: 12 } },
            range: zRange,
            tickfont: { size: 10 },
            nticks: 5,
            gridcolor: "#d6e2ef",
            backgroundcolor: "#f8fbff",
          },
          aspectmode: "data",
          dragmode: "orbit",
          camera: {
            eye: defaultCameraEye,
            up: { x: 0, y: 0, z: 1 },
            projection: { type: "perspective" },
          },
        },
        paper_bgcolor: "#ffffff",
      },
      { responsive: true, displaylogo: false, scrollZoom: true },
    );
    if (plotPromise && typeof plotPromise.then === "function") {
      void plotPromise.then(() => attachPreviewRelayoutHandler(graphElement));
    } else {
      attachPreviewRelayoutHandler(graphElement);
    }
  }

  function refreshGeometry() {
    renderValidation();
    renderPreview();
  }

  function particleFieldLabel(field) {
    const keys = {
      diameter_nm: "coordinates.diameter",
      x_nm: "coordinates.x",
      y_nm: "coordinates.y",
      z_nm: "coordinates.z",
    };
    return t(keys[field]);
  }

  function makeParticleInput(value, field) {
    const input = document.createElement("input");
    input.type = "number";
    input.step = "0.1";
    input.value = formatFormValue(value, field);
    input.dataset.field = field;
    input.setAttribute("aria-label", particleFieldLabel(field));
    input.addEventListener("input", refreshGeometry);
    return input;
  }

  function renderParticleRows() {
    const body = document.getElementById("particle-rows");
    body.replaceChildren();
    particles.forEach((particle, index) => {
      const row = document.createElement("tr");
      const indexCell = document.createElement("th");
      indexCell.scope = "row";
      indexCell.textContent = String(index + 1);
      row.append(indexCell);
      ["diameter_nm", "x_nm", "y_nm", "z_nm"].forEach((field) => {
        const cell = document.createElement("td");
        cell.append(makeParticleInput(particle[field], field));
        row.append(cell);
      });
      const actionCell = document.createElement("td");
      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "compact-button";
      removeButton.textContent = t("coordinates.remove");
      removeButton.disabled = particles.length === 1;
      removeButton.addEventListener("click", () => {
        particles = readParticles();
        particles.splice(index, 1);
        renderParticleRows();
      });
      actionCell.append(removeButton);
      row.append(actionCell);
      body.append(row);
    });
    document.getElementById("add-particle").disabled = particles.length >= maximumParticleCount;
    refreshGeometry();
  }

  function setParticles(nextParticles) {
    particles = nextParticles.slice(0, maximumParticleCount);
    renderParticleRows();
  }

  function showPresetError(error) {
    const target = document.getElementById("geometry-validation");
    target.textContent = error.message;
    target.classList.add("has-error");
  }

  async function normalizePresetParticles(nextParticles) {
    const response = await window.PlasmonApi.roundLayoutForDisplay(nextParticles);
    setParticles(response.particles);
  }

  async function applyDimer() {
    const button = document.getElementById("apply-dimer");
    button.disabled = true;
    try {
      const diameterNm = numberValue("dimer-diameter-nm");
      const gapNm = numberValue("dimer-gap-nm");
      await normalizePresetParticles([
        { diameter_nm: diameterNm, x_nm: 0, y_nm: 0, z_nm: 0 },
        { diameter_nm: diameterNm, x_nm: diameterNm + gapNm, y_nm: 0, z_nm: 0 },
      ]);
    } finally {
      button.disabled = false;
    }
  }

  async function applyTrimer() {
    const button = document.getElementById("apply-trimer");
    button.disabled = true;
    try {
      const diameterNm = numberValue("trimer-diameter-nm");
      const centerDistanceNm = numberValue("trimer-center-distance-nm");
      const heightNm = (Math.sqrt(3) * centerDistanceNm) / 2;
      await normalizePresetParticles([
        { diameter_nm: diameterNm, x_nm: 0, y_nm: 0, z_nm: 0 },
        { diameter_nm: diameterNm, x_nm: centerDistanceNm, y_nm: 0, z_nm: 0 },
        { diameter_nm: diameterNm, x_nm: centerDistanceNm / 2, y_nm: heightNm, z_nm: 0 },
      ]);
    } finally {
      button.disabled = false;
    }
  }

  async function applyRandomCluster() {
    const button = document.getElementById("apply-random-cluster");
    button.disabled = true;
    try {
      const response = await window.PlasmonApi.generateRandomCluster({
        particle_count: numberValue("random-particle-count"),
        mean_diameter_nm: numberValue("random-mean-diameter-nm"),
        minimum_surface_gap_nm: numberValue("random-minimum-gap-nm"),
        seed: numberValue("random-seed"),
      });
      setParticles(response.particles);
    } finally {
      button.disabled = false;
    }
  }

  function addParticle() {
    const currentParticles = readParticles();
    if (currentParticles.length >= maximumParticleCount) {
      return;
    }
    const finiteParticles = currentParticles.filter((particle) =>
      [particle.diameter_nm, particle.x_nm].every(Number.isFinite),
    );
    const last = finiteParticles.at(-1) ?? { diameter_nm: 20, x_nm: 0 };
    const nextDiameterNm = Math.min(Math.max(last.diameter_nm, minimumDiameterNm), maximumDiameterNm);
    const largestXNm = Math.max(0, ...finiteParticles.map((particle) => particle.x_nm));
    currentParticles.push({
      diameter_nm: nextDiameterNm,
      x_nm: largestXNm + nextDiameterNm + 5,
      y_nm: 0,
      z_nm: 0,
    });
    setParticles(currentParticles);
  }

  function buildPayload() {
    const candidateParticles = readParticles();
    const validation = validateParticles(candidateParticles);
    renderValidation();
    if (validation.errors.length > 0) {
      throw new Error(validation.errors.join(" "));
    }
    const mediumPreset = document.getElementById("medium-preset").value;
    const polarizationChoice = document.getElementById("polarization").value;
    const startWavelengthNm = numberValue("start-wavelength-nm");
    const endWavelengthNm = numberValue("end-wavelength-nm");
    const stepNm = numberValue("wavelength-step-nm");
    const refractiveIndex = numberValue("medium-refractive-index");
    if (
      ![startWavelengthNm, endWavelengthNm, stepNm, refractiveIndex].every(Number.isFinite)
    ) {
      throw new Error(t("validation.wavelengthMediumRequired"));
    }
    const polarization = polarizationChoice === "x" ? [1, 0, 0] : [0, 1, 0];
    return {
      material: "Au",
      particles: candidateParticles,
      medium: {
        name: mediumPreset === "custom" ? "custom" : mediumPresets[mediumPreset].name,
        refractive_index: refractiveIndex,
      },
      light_source: {
        wavelength_nm: startWavelengthNm,
        propagation_direction: [0, 0, 1],
        polarization,
      },
      spectrum: {
        start_wavelength_nm: startWavelengthNm,
        end_wavelength_nm: endWavelengthNm,
        step_nm: stepNm,
      },
    };
  }

  function initializeTabs() {
    const buttons = Array.from(document.querySelectorAll("[data-tab-target]"));
    const panels = Array.from(document.querySelectorAll("[data-tab-panel]"));
    function activateTab(button) {
      const targetId = button.dataset.tabTarget;
      buttons.forEach((candidate) => {
        const selected = candidate === button;
        candidate.setAttribute("aria-selected", String(selected));
        candidate.tabIndex = selected ? 0 : -1;
      });
      panels.forEach((panel) => {
        panel.hidden = panel.id !== targetId;
      });
    }
    buttons.forEach((button) => {
      button.addEventListener("click", () => activateTab(button));
    });
  }

  function initialize() {
    document.getElementById("medium-preset").addEventListener("change", updateMediumInput);
    document.getElementById("apply-dimer").addEventListener("click", () => {
      applyDimer().catch(showPresetError);
    });
    document.getElementById("apply-trimer").addEventListener("click", () => {
      applyTrimer().catch(showPresetError);
    });
    document.getElementById("apply-random-cluster").addEventListener("click", () => {
      applyRandomCluster().catch(showPresetError);
    });
    document.getElementById("add-particle").addEventListener("click", addParticle);
    window.addEventListener("plasmonlanguagechange", () => {
      particles = readParticles();
      if (particles.length > 0) {
        renderParticleRows();
      }
    });
    initializeTabs();
    updateMediumInput();
    applyDimer().catch(showPresetError);
  }

  return { buildPayload, initialize, refreshGeometry };
})();
