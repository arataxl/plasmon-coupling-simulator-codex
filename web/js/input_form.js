window.PlasmonInputForm = (() => {
  const maximumParticleCount = 20;
  const minimumDiameterNm = 2;
  const maximumDiameterNm = 100;
  const minimumGapNm = 0.5;
  const mediumPresets = {
    water: { name: "water", refractiveIndex: 1.33 },
    ethanol: { name: "ethanol", refractiveIndex: 1.361 },
  };
  let particles = [];

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
      errors.push(`粒子数は1〜${maximumParticleCount}個にしてください。`);
      return { errors, warnings };
    }
    candidateParticles.forEach((particle, index) => {
      const label = `粒子${index + 1}`;
      if (!Number.isFinite(particle.diameter_nm)) {
        errors.push(`${label}の径を数値で入力してください。`);
      } else if (
        particle.diameter_nm < minimumDiameterNm ||
        particle.diameter_nm > maximumDiameterNm
      ) {
        errors.push(`${label}の径は${minimumDiameterNm}〜${maximumDiameterNm} nmです。`);
      }
      ["x_nm", "y_nm", "z_nm"].forEach((field) => {
        if (!Number.isFinite(particle[field])) {
          errors.push(`${label}の${field.slice(0, 1)}座標を数値で入力してください。`);
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
        const pairLabel = `粒子${left + 1}–${right + 1}`;
        if (surfaceGapNm < minimumGapNm - 1e-12) {
          errors.push(`${pairLabel}の表面間ギャップ ${surfaceGapNm.toFixed(3)} nm は0.5 nm未満です。`);
        } else if (surfaceGapNm < 1.0) {
          warnings.push(`${pairLabel}: ${surfaceGapNm.toFixed(3)} nmのためQCMを自動適用します。`);
        } else if (surfaceGapNm <= 5.0) {
          warnings.push(`${pairLabel}: ${surfaceGapNm.toFixed(3)} nmはCDAの近似限界に注意してください。`);
        }
      }
    }
    return { errors, warnings };
  }

  function updateQcmInputStatus(validation) {
    const target = document.getElementById("qcm-input-status");
    if (!target) {
      return;
    }
    if (validation.errors.length > 0) {
      target.textContent = "配置を修正してからQCM適用範囲を確認してください。";
      return;
    }
    if (validation.warnings.some((warning) => warning.includes("QCMを自動適用"))) {
      target.textContent = "この配置ではQCMを自動適用します。ユーザーによる無効化はできません。";
      return;
    }
    target.textContent = "この配置ではQCMは適用されません。0.5〜1.0 nm未満で自動適用されます。";
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
      target.textContent = "配置は入力範囲内です。";
    }
    updateQcmInputStatus(result);
    return result;
  }

  function axisRange(values, maximumDiameterNm) {
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const span = Math.max(maximum - minimum, maximumDiameterNm, 1.0);
    const padding = Math.max(span * 0.22, maximumDiameterNm * 0.65, 5.0);
    return [minimum - padding, maximum + padding];
  }

  function renderPreview() {
    const finiteParticles = readParticles().filter((particle) =>
      [particle.diameter_nm, particle.x_nm, particle.y_nm, particle.z_nm].every(Number.isFinite),
    );
    if (!window.Plotly || finiteParticles.length === 0) {
      return;
    }
    const maximumDiameter = Math.max(...finiteParticles.map((particle) => particle.diameter_nm));
    const xValues = finiteParticles.map((particle) => particle.x_nm);
    const yValues = finiteParticles.map((particle) => particle.y_nm);
    const zValues = finiteParticles.map((particle) => particle.z_nm);
    window.Plotly.react(
      "geometry-preview",
      [
        {
          type: "scatter3d",
          mode: "markers+text",
          x: xValues,
          y: yValues,
          z: zValues,
          text: finiteParticles.map((particle, index) => ` ${index + 1}`),
          customdata: finiteParticles.map((particle) => [particle.diameter_nm]),
          textposition: "top center",
          textfont: { color: "#17324d", size: 12 },
          marker: {
            // scatter3d の marker.size は px。ズーム後も読める固定表示で相対径を示す。
            size: finiteParticles.map((particle) => Math.max(12, (30 * particle.diameter_nm) / maximumDiameter)),
            sizemode: "diameter",
            sizeref: 1,
            sizemin: 12,
            color: "#d69e2e",
            line: { color: "#6b4200", width: 1.5 },
            opacity: 0.9,
          },
          hovertemplate:
            "粒子 %{text}<br>径=%{customdata[0]:.1f} nm<br>x=%{x:.1f} nm<br>y=%{y:.1f} nm<br>z=%{z:.1f} nm<extra></extra>",
        },
      ],
      {
        margin: { t: 28, r: 28, b: 52, l: 56 },
        scene: {
          xaxis: {
            title: { text: "x (nm)", font: { size: 12 } },
            range: axisRange(xValues, maximumDiameter),
            tickfont: { size: 11 },
            nticks: 5,
            gridcolor: "#d6e2ef",
            backgroundcolor: "#f8fbff",
          },
          yaxis: {
            title: { text: "y (nm)", font: { size: 12 } },
            range: axisRange(yValues, maximumDiameter),
            tickfont: { size: 11 },
            nticks: 5,
            gridcolor: "#d6e2ef",
            backgroundcolor: "#f8fbff",
          },
          zaxis: {
            title: { text: "z (nm)", font: { size: 12 } },
            range: axisRange(zValues, maximumDiameter),
            tickfont: { size: 11 },
            nticks: 5,
            gridcolor: "#d6e2ef",
            backgroundcolor: "#f8fbff",
          },
          aspectmode: "data",
          dragmode: "orbit",
          camera: {
            eye: { x: 1.7, y: 1.7, z: 1.35 },
            up: { x: 0, y: 0, z: 1 },
            projection: { type: "orthographic" },
          },
        },
        paper_bgcolor: "#ffffff",
      },
      { responsive: true, displaylogo: false, scrollZoom: true },
    );
  }

  function refreshGeometry() {
    renderValidation();
    renderPreview();
  }

  function makeParticleInput(value, field) {
    const input = document.createElement("input");
    input.type = "number";
    input.step = "0.1";
    input.value = formatFormValue(value, field);
    input.dataset.field = field;
    input.setAttribute("aria-label", field);
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
      removeButton.textContent = "削除";
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
      throw new Error("波長範囲と媒質屈折率を数値で入力してください。");
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
    initializeTabs();
    updateMediumInput();
    applyDimer().catch(showPresetError);
  }

  return { buildPayload, initialize, refreshGeometry };
})();
