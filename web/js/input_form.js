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
    return result;
  }

  function renderPreview() {
    const finiteParticles = readParticles().filter((particle) =>
      [particle.diameter_nm, particle.x_nm, particle.y_nm, particle.z_nm].every(Number.isFinite),
    );
    if (!window.Plotly || finiteParticles.length === 0) {
      return;
    }
    const maximumDiameter = Math.max(...finiteParticles.map((particle) => particle.diameter_nm));
    window.Plotly.react(
      "geometry-preview",
      [
        {
          type: "scatter3d",
          mode: "markers+text",
          x: finiteParticles.map((particle) => particle.x_nm),
          y: finiteParticles.map((particle) => particle.y_nm),
          z: finiteParticles.map((particle) => particle.z_nm),
          text: finiteParticles.map((particle, index) => ` ${index + 1}`),
          textposition: "top center",
          marker: {
            size: finiteParticles.map((particle) => 7 + (22 * particle.diameter_nm) / maximumDiameter),
            color: "#d69e2e",
            line: { color: "#6b4200", width: 1 },
            opacity: 0.88,
          },
          hovertemplate:
            "粒子 %{text}<br>x=%{x:.3f} nm<br>y=%{y:.3f} nm<br>z=%{z:.3f} nm<extra></extra>",
        },
      ],
      {
        margin: { t: 8, r: 8, b: 8, l: 8 },
        scene: {
          xaxis: { title: "x (nm)" },
          yaxis: { title: "y (nm)" },
          zaxis: { title: "z (nm)" },
          aspectmode: "data",
        },
        paper_bgcolor: "#ffffff",
      },
      { responsive: true, displaylogo: false },
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
    input.value = value;
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

  function applyDimer() {
    const diameterNm = numberValue("dimer-diameter-nm");
    const gapNm = numberValue("dimer-gap-nm");
    setParticles([
      { diameter_nm: diameterNm, x_nm: 0, y_nm: 0, z_nm: 0 },
      { diameter_nm: diameterNm, x_nm: diameterNm + gapNm, y_nm: 0, z_nm: 0 },
    ]);
  }

  function applyTrimer() {
    const diameterNm = numberValue("trimer-diameter-nm");
    const centerDistanceNm = numberValue("trimer-center-distance-nm");
    const heightNm = (Math.sqrt(3) * centerDistanceNm) / 2;
    setParticles([
      { diameter_nm: diameterNm, x_nm: 0, y_nm: 0, z_nm: 0 },
      { diameter_nm: diameterNm, x_nm: centerDistanceNm, y_nm: 0, z_nm: 0 },
      { diameter_nm: diameterNm, x_nm: centerDistanceNm / 2, y_nm: heightNm, z_nm: 0 },
    ]);
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

  function initialize() {
    document.getElementById("medium-preset").addEventListener("change", updateMediumInput);
    document.getElementById("apply-dimer").addEventListener("click", applyDimer);
    document.getElementById("apply-trimer").addEventListener("click", applyTrimer);
    document.getElementById("apply-random-cluster").addEventListener("click", () => {
      applyRandomCluster().catch((error) => {
        document.getElementById("geometry-validation").textContent = error.message;
        document.getElementById("geometry-validation").classList.add("has-error");
      });
    });
    document.getElementById("add-particle").addEventListener("click", addParticle);
    updateMediumInput();
    applyDimer();
  }

  return { buildPayload, initialize, refreshGeometry };
})();
