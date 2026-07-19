window.PlasmonInputForm = (() => {
  const mediumPresets = {
    water: { name: "water", refractiveIndex: 1.33 },
    ethanol: { name: "ethanol", refractiveIndex: 1.361 },
  };

  function numberValue(id) {
    return Number(document.getElementById(id).value);
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

  function buildPayload() {
    const particleCount = numberValue("particle-count");
    const diameterNm = numberValue("diameter-nm");
    const gapNm = numberValue("gap-nm");
    const mediumPreset = document.getElementById("medium-preset").value;
    const polarizationChoice = document.getElementById("polarization").value;
    const startWavelengthNm = numberValue("start-wavelength-nm");
    const polarization = polarizationChoice === "x" ? [1, 0, 0] : [0, 1, 0];
    const particles = Array.from({ length: particleCount }, (_, index) => ({
      diameter_nm: diameterNm,
      x_nm: index * (diameterNm + gapNm),
      y_nm: 0,
      z_nm: 0,
    }));

    return {
      material: "Au",
      particles,
      medium: {
        name: mediumPreset === "custom" ? "custom" : mediumPresets[mediumPreset].name,
        refractive_index: numberValue("medium-refractive-index"),
      },
      light_source: {
        wavelength_nm: startWavelengthNm,
        propagation_direction: [0, 0, 1],
        polarization,
      },
      spectrum: {
        start_wavelength_nm: startWavelengthNm,
        end_wavelength_nm: numberValue("end-wavelength-nm"),
        step_nm: numberValue("wavelength-step-nm"),
      },
    };
  }

  function initialize() {
    document
      .getElementById("medium-preset")
      .addEventListener("change", updateMediumInput);
    updateMediumInput();
  }

  return { buildPayload, initialize };
})();
