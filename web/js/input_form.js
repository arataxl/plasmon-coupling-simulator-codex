window.PlasmonInputForm = (() => {
  const maximumParticleCount = 20;
  const minimumDiameterNm = 2;
  const maximumDiameterNm = 100;
  const minimumGapNm = 0.5;
  const sphereLatitudeSegments = 16;
  const sphereLongitudeSegments = 16;
  const spherePalette = Object.freeze([
    "#d6a329",
    "#db712a",
    "#bb5139",
    "#b04d5f",
    "#90559a",
    "#526cae",
    "#357fa3",
    "#2f8d87",
    "#4e9567",
    "#879b37",
    "#b3a638",
    "#c48a2d",
    "#d16654",
    "#9b527e",
    "#3e94a0",
    "#39746d",
    "#536f91",
    "#826238",
    "#a46d31",
    "#687784",
  ]);
  const sphereOutlineColor = "#4f3414";
  const labelDirection = Object.freeze({ x: 0.3, y: 0.3, z: 0.9055385138 });
  const mediumPresets = {
    water: { name: "water", refractiveIndex: 1.33 },
    ethanol: { name: "ethanol", refractiveIndex: 1.361 },
  };
  let particles = [];

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

  function equalAxisRanges(candidateParticles) {
    const maximumDiameterNm = Math.max(
      ...candidateParticles.map((particle) => particle.diameter_nm),
    );
    const minimums = [Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY];
    const maximums = [Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY];
    candidateParticles.forEach((particle) => {
      const radiusNm = particle.diameter_nm / 2.0;
      [particle.x_nm, particle.y_nm, particle.z_nm].forEach((coordinate, axis) => {
        minimums[axis] = Math.min(minimums[axis], coordinate - radiusNm);
        maximums[axis] = Math.max(maximums[axis], coordinate + radiusNm);
      });
    });
    const widestSpanNm = Math.max(
      ...maximums.map((maximum, axis) => maximum - minimums[axis]),
      maximumDiameterNm,
      1.0,
    );
    const paddingNm = Math.max(widestSpanNm * 0.2, maximumDiameterNm * 0.5, 8.0);
    const totalSpanNm = widestSpanNm + 2.0 * paddingNm;
    const halfSpanNm = totalSpanNm / 2.0;
    const ranges = maximums.map((maximum, axis) => {
      const centerNm = (minimums[axis] + maximum) / 2.0;
      return [centerNm - halfSpanNm, centerNm + halfSpanNm];
    });
    return {
      xRange: ranges[0],
      yRange: ranges[1],
      zRange: ranges[2],
      viewSpanNm: totalSpanNm,
    };
  }

  function niceTickStep(range) {
    const rawStep = (range[1] - range[0]) / 5.0;
    const powerOfTen = 10 ** Math.floor(Math.log10(Math.max(rawStep, 1.0e-12)));
    const normalizedStep = rawStep / powerOfTen;
    const multiplier = [1.0, 2.0, 5.0, 10.0].find((candidate) => normalizedStep <= candidate);
    return (multiplier ?? 10.0) * powerOfTen;
  }

  function sceneAxis(title, range) {
    return {
      title: { text: title, font: { size: 13 } },
      range,
      tickmode: "linear",
      tick0: 0,
      dtick: niceTickStep(range),
      tickfont: { size: 11 },
      ticks: "outside",
      ticklen: 5,
      tickwidth: 1,
      showgrid: true,
      gridcolor: "#c9d9e7",
      zeroline: true,
      zerolinecolor: "#9ab4c7",
      backgroundcolor: "#f8fbff",
    };
  }

  function createSphereMesh(particle, particleIndex) {
    const radiusNm = particle.diameter_nm / 2.0;
    const verticesPerLatitude = sphereLongitudeSegments + 1;
    const x = [];
    const y = [];
    const z = [];
    const i = [];
    const j = [];
    const k = [];

    for (let latitude = 0; latitude <= sphereLatitudeSegments; latitude += 1) {
      const polarAngle = (Math.PI * latitude) / sphereLatitudeSegments;
      const sinPolarAngle = Math.sin(polarAngle);
      const cosPolarAngle = Math.cos(polarAngle);
      for (let longitude = 0; longitude <= sphereLongitudeSegments; longitude += 1) {
        const azimuthAngle = (2.0 * Math.PI * longitude) / sphereLongitudeSegments;
        x.push(particle.x_nm + radiusNm * sinPolarAngle * Math.cos(azimuthAngle));
        y.push(particle.y_nm + radiusNm * sinPolarAngle * Math.sin(azimuthAngle));
        z.push(particle.z_nm + radiusNm * cosPolarAngle);
      }
    }

    for (let latitude = 0; latitude < sphereLatitudeSegments; latitude += 1) {
      for (let longitude = 0; longitude < sphereLongitudeSegments; longitude += 1) {
        const topLeft = latitude * verticesPerLatitude + longitude;
        const topRight = topLeft + 1;
        const bottomLeft = topLeft + verticesPerLatitude;
        const bottomRight = bottomLeft + 1;
        i.push(topLeft, topRight);
        j.push(bottomLeft, bottomRight);
        k.push(topRight, bottomLeft);
      }
    }

    return {
      type: "mesh3d",
      x,
      y,
      z,
      i,
      j,
      k,
      color: spherePalette[particleIndex % spherePalette.length],
      opacity: 1,
      flatshading: false,
      lighting: { ambient: 0.58, diffuse: 0.82, specular: 0.28, roughness: 0.75 },
      lightposition: { x: 100, y: 120, z: 180 },
      contour: { show: true, color: sphereOutlineColor, width: 1 },
      hoverinfo: "skip",
      showscale: false,
    };
  }

  function labelPosition(particle, viewSpan) {
    const radiusNm = particle.diameter_nm / 2.0;
    const clearanceNm = Math.max(radiusNm * 0.22, viewSpan * 0.025, 0.8);
    const labelDistanceNm = radiusNm + clearanceNm;
    return {
      x: particle.x_nm + labelDirection.x * labelDistanceNm,
      y: particle.y_nm + labelDirection.y * labelDistanceNm,
      z: particle.z_nm + labelDirection.z * labelDistanceNm,
    };
  }

  function renderPreview() {
    const graphElement = document.getElementById("geometry-preview");
    const finiteParticles = readParticles().filter((particle) =>
      [particle.diameter_nm, particle.x_nm, particle.y_nm, particle.z_nm].every(Number.isFinite),
    );
    if (!window.Plotly || !graphElement || finiteParticles.length === 0) {
      if (window.Plotly && graphElement) {
        window.Plotly.purge(graphElement);
      }
      return;
    }
    const { xRange, yRange, zRange, viewSpanNm } = equalAxisRanges(finiteParticles);
    const labelPositions = finiteParticles.map((particle) => labelPosition(particle, viewSpanNm));
    const sphereTraces = finiteParticles.map((particle, index) => createSphereMesh(particle, index));
    // Plotly の 3D テキストにはアウトライン属性がないため、少し大きな暗色テキストを
    // 背面に重ねて、背景ボックスなしの読みやすい縁取りとして扱う。
    const labelOutlineTrace = {
      type: "scatter3d",
      mode: "text",
      x: labelPositions.map((position) => position.x),
      y: labelPositions.map((position) => position.y),
      z: labelPositions.map((position) => position.z),
      text: finiteParticles.map((_, index) => String(index + 1)),
      textposition: "middle center",
      textfont: {
        color: "#071521",
        family: '"Segoe UI Black", "Arial Black", "Noto Sans JP", sans-serif',
        size: 21,
      },
      hoverinfo: "skip",
      showlegend: false,
    };
    const labelTrace = {
      type: "scatter3d",
      mode: "text",
      x: labelPositions.map((position) => position.x),
      y: labelPositions.map((position) => position.y),
      z: labelPositions.map((position) => position.z),
      text: finiteParticles.map((_, index) => String(index + 1)),
      customdata: finiteParticles.map((particle) => [
        particle.diameter_nm,
        particle.x_nm,
        particle.y_nm,
        particle.z_nm,
      ]),
      textposition: "middle center",
      textfont: {
        color: "#fffdf5",
        family: '"Segoe UI Black", "Arial Black", "Noto Sans JP", sans-serif',
        size: 16,
      },
      hovertemplate: t("preview.hover"),
      hoverlabel: { bgcolor: "#17324d", font: { color: "#ffffff" } },
      showlegend: false,
    };

    window.Plotly.react(
      graphElement,
      [...sphereTraces, labelOutlineTrace, labelTrace],
      {
        margin: { t: 38, r: 42, b: 72, l: 78 },
        scene: {
          xaxis: sceneAxis(t("preview.xAxis"), xRange),
          yaxis: sceneAxis(t("preview.yAxis"), yRange),
          zaxis: sceneAxis(t("preview.zAxis"), zRange),
          aspectmode: "cube",
          dragmode: "orbit",
          camera: {
            eye: { x: 1.8, y: 1.8, z: 1.45 },
            up: { x: 0, y: 0, z: 1 },
            projection: { type: "perspective" },
          },
        },
        paper_bgcolor: "#ffffff",
      },
      { responsive: true, displaylogo: false, displayModeBar: true, scrollZoom: true },
    );
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

  function clearPresetError(preset) {
    const target = document.getElementById(`${preset}-preset-error`);
    target.textContent = "";
    target.hidden = true;
  }

  function showPresetError(preset, error) {
    const target = document.getElementById(`${preset}-preset-error`);
    target.textContent = error.message;
    target.hidden = false;
  }

  async function normalizePresetParticles(nextParticles) {
    const response = await window.PlasmonApi.roundLayoutForDisplay(nextParticles);
    setParticles(response.particles);
  }

  async function applyDimer() {
    const button = document.getElementById("apply-dimer");
    clearPresetError("dimer");
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
    clearPresetError("trimer");
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
    clearPresetError("random");
    button.disabled = true;
    try {
      const minimumSurfaceGapNm = numberValue("random-minimum-gap-nm");
      const maximumSurfaceGapNm = numberValue("random-maximum-gap-nm");
      if (
        Number.isFinite(minimumSurfaceGapNm) &&
        Number.isFinite(maximumSurfaceGapNm) &&
        maximumSurfaceGapNm < minimumSurfaceGapNm
      ) {
        throw new Error(t("validation.randomGapRange"));
      }
      const response = await window.PlasmonApi.generateRandomCluster({
        particle_count: numberValue("random-particle-count"),
        mean_diameter_nm: numberValue("random-mean-diameter-nm"),
        minimum_surface_gap_nm: minimumSurfaceGapNm,
        maximum_surface_gap_nm: maximumSurfaceGapNm,
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
      applyDimer().catch((error) => showPresetError("dimer", error));
    });
    document.getElementById("apply-trimer").addEventListener("click", () => {
      applyTrimer().catch((error) => showPresetError("trimer", error));
    });
    document.getElementById("apply-random-cluster").addEventListener("click", () => {
      applyRandomCluster().catch((error) => showPresetError("random", error));
    });
    document.getElementById("random-minimum-gap-nm").addEventListener("input", () => {
      const minimumSurfaceGapNm = numberValue("random-minimum-gap-nm");
      if (Number.isFinite(minimumSurfaceGapNm)) {
        document.getElementById("random-maximum-gap-nm").min = String(minimumSurfaceGapNm);
      }
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
    document.getElementById("random-maximum-gap-nm").min = String(
      numberValue("random-minimum-gap-nm"),
    );
    applyDimer().catch((error) => showPresetError("dimer", error));
  }

  return { buildPayload, initialize, refreshGeometry };
})();
