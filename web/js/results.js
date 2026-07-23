window.PlasmonResults = (() => {
  const squareNanometresPerSquareMetre = 1.0e18;
  const SMOOTHING_COEFFS = Object.freeze({
    low: [-0.08571429, 0.34285714, 0.48571429, 0.34285714, -0.08571429],
    medium: [-0.09090909, 0.06060606, 0.16883117, 0.23376623, 0.25541126, 0.23376623, 0.16883117, 0.06060606, -0.09090909],
    high: [-0.07058824, -0.01176471, 0.03800905, 0.07873303, 0.11040724, 0.13303167, 0.14660633, 0.15113122, 0.14660633, 0.13303167, 0.11040724, 0.07873303, 0.03800905, -0.01176471, -0.07058824],
    very_high: [0.0447205, -0.02484472, -0.05001635, -0.04315136, -0.01515297, 0.02452935, 0.06789993, 0.10841682, 0.14099187, 0.16199065, 0.16923254, 0.16199065, 0.14099187, 0.10841682, 0.06789993, 0.02452935, -0.01515297, -0.04315136, -0.05001635, -0.02484472, 0.0447205],
    extreme: [0.03812317, 0, -0.02275255, -0.0328648, -0.0328648, -0.02507837, -0.01162908, 0.00556174, 0.024775, 0.04449388, 0.06340378, 0.08039236, 0.0945495, 0.10516736, 0.11174032, 0.11396501, 0.11174032, 0.10516736, 0.0945495, 0.08039236, 0.06340378, 0.04449388, 0.024775, 0.00556174, -0.01162908, -0.02507837, -0.0328648, -0.0328648, -0.02275255, 0, 0.03812317],
  });
  let latestResult = null;
  let latestDownloadMetadata = null;
  let selectedHistoryIds = new Set();
  let comparisonActive = false;
  let comparisonError = null;
  let detailHistoryEntry = null;

  function t(key, parameters) {
    return window.PlasmonI18n.t(key, parameters);
  }

  function downloadBlob(filename, content, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function formatNumber(value, digits = 1) {
    return Number.isFinite(value) ? Number(value.toFixed(digits)) : null;
  }

  function formatFileNumber(value) {
    if (!Number.isFinite(value)) {
      return "na";
    }
    return String(formatNumber(value)).replace("-", "m").replace(".", "p");
  }

  function timestampToken(timestampUtc) {
    return timestampUtc.replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  }

  function layoutFingerprint(particles) {
    const source = JSON.stringify(
      particles.map((particle) => [
        formatNumber(particle.diameter_nm, 6),
        formatNumber(particle.x_nm, 6),
        formatNumber(particle.y_nm, 6),
        formatNumber(particle.z_nm, 6),
      ]),
    );
    let hash = 2166136261;
    for (let index = 0; index < source.length; index += 1) {
      hash ^= source.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  function layoutType(particleCount) {
    if (particleCount === 1) {
      return "single";
    }
    if (particleCount === 2) {
      return "dimer";
    }
    if (particleCount === 3) {
      return "three-particle";
    }
    return "cluster";
  }

  function minimumSurfaceGapNm(particles) {
    if (particles.length < 2) {
      return null;
    }
    let minimumGap = Number.POSITIVE_INFINITY;
    for (let left = 0; left < particles.length; left += 1) {
      for (let right = left + 1; right < particles.length; right += 1) {
        const first = particles[left];
        const second = particles[right];
        const centerDistance = Math.hypot(
          first.x_nm - second.x_nm,
          first.y_nm - second.y_nm,
          first.z_nm - second.z_nm,
        );
        minimumGap = Math.min(
          minimumGap,
          centerDistance - (first.diameter_nm + second.diameter_nm) / 2.0,
        );
      }
    }
    return formatNumber(minimumGap, 6);
  }

  function diameterSummary(particles) {
    const values = particles.map((particle) => formatFileNumber(particle.diameter_nm));
    if (new Set(values).size === 1) {
      return `${values[0]}x${particles.length}`;
    }
    if (values.length <= 4) {
      return values.join("-");
    }
    const numericValues = particles.map((particle) => particle.diameter_nm);
    return `${formatFileNumber(Math.min(...numericValues))}-${formatFileNumber(Math.max(...numericValues))}`;
  }

  function placementFileToken(particles, placement) {
    const coordinateToken = (particle) =>
      `x${formatFileNumber(particle.x_nm)}y${formatFileNumber(particle.y_nm)}z${formatFileNumber(particle.z_nm)}`;
    if (particles.length <= 3) {
      return `pos-${particles.map(coordinateToken).join("_")}-h${placement.fingerprint}`;
    }
    const bounds = ["x_nm", "y_nm", "z_nm"].map((axis) => {
      const values = particles.map((particle) => particle[axis]);
      return `${axis.slice(0, 1)}${formatFileNumber(Math.min(...values))}-${formatFileNumber(Math.max(...values))}`;
    });
    return `bbox-${bounds.join("_")}-h${placement.fingerprint}`;
  }

  function buildDownloadMetadata(result) {
    const timestampUtc = new Date().toISOString();
    const particles = result.input.particles;
    const spectrum = result.input.spectrum;
    const minimumGapNm = minimumSurfaceGapNm(particles);
    const qcmApplied = Boolean(result.qcm_metadata?.qcm_applied);
    const experimentalQuadrupoleApplied = Boolean(
      result.experimental_quadrupole_metadata?.applied,
    );
    const placement = {
      type: layoutType(particles.length),
      fingerprint: layoutFingerprint(particles),
      coordinate_unit: "nm",
      particles: particles.map((particle, index) => ({
        index: index + 1,
        diameter_nm: formatNumber(particle.diameter_nm, 6),
        x_nm: formatNumber(particle.x_nm, 6),
        y_nm: formatNumber(particle.y_nm, 6),
        z_nm: formatNumber(particle.z_nm, 6),
      })),
    };
    const conditions = {
      particle_count: particles.length,
      diameters_nm: particles.map((particle) => formatNumber(particle.diameter_nm, 6)),
      placement,
      minimum_surface_gap_nm: minimumGapNm,
      wavelength_range_nm: {
        start: spectrum.start_wavelength_nm,
        end: spectrum.end_wavelength_nm,
        step: spectrum.step_nm,
      },
      qcm_applied: qcmApplied,
      smoothing_level: result.smoothing_level,
      experimental_quadrupole_coupling: experimentalQuadrupoleApplied,
      experimental_quadrupole_metadata: result.experimental_quadrupole_metadata ?? null,
      result_timestamp_utc: timestampUtc,
    };
    const filenameStem = [
      "plasmon",
      `n${conditions.particle_count}`,
      `d${diameterSummary(particles)}nm`,
      `layout-${placement.type}-${placementFileToken(particles, placement)}`,
      `gap${minimumGapNm === null ? "na" : formatFileNumber(minimumGapNm)}nm`,
      `wl${formatFileNumber(spectrum.start_wavelength_nm)}-${formatFileNumber(spectrum.end_wavelength_nm)}s${formatFileNumber(spectrum.step_nm)}nm`,
      `qcm-${qcmApplied ? "on" : "off"}`,
      `ed-eq-${experimentalQuadrupoleApplied ? "on" : "off"}`,
      timestampToken(timestampUtc),
    ].join("_");
    return { ...conditions, filename_stem: filenameStem };
  }

  const warningTranslationKeyByCode = Object.freeze({
    cda_gap_limitation: "warning.cdaGapLimitation",
    experimental_quadrupole_coupling: "warning.experimentalQuadrupoleCoupling",
    qcm_applied: "warning.qcmApplied",
    qcm_classical_limit: "warning.qcmClassicalLimit",
    qcm_validation_override: "warning.qcmValidationOverride",
  });

  function warningText(warning) {
    const parameters = warning?.parameters ?? {};
    const translationKey = warningTranslationKeyByCode[warning?.code];
    if (!translationKey) {
      return t("warning.unknown");
    }
    return t(translationKey, {
      minimumGapNm: formatNumber(Number(parameters.minimum_gap_nm), 3),
      layerCount: parameters.layer_count,
      bridgeCount: parameters.bridge_count,
      classicalLimitPairCount: parameters.classical_limit_pair_count,
      pairCount: parameters.pair_count,
    });
  }

  function renderWarnings(warnings, qcmApplied) {
    const warningList = document.getElementById("warning-list");
    warningList.replaceChildren();
    const displayWarnings = (warnings ?? []).map(warningText);
    if (qcmApplied) {
      displayWarnings.push(t("warning.nirCdaLimit"));
    }
    displayWarnings.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = warning;
      warningList.append(item);
    });
  }

  function setQcmDetail(id, value) {
    document.getElementById(id).textContent = value ?? t("result.missing");
  }

  function renderQcmNotice(metadata) {
    const qcmNotice = document.getElementById("qcm-notice");
    const applied = Boolean(metadata?.qcm_applied);
    qcmNotice.hidden = !applied;
    if (!applied) {
      return;
    }
    qcmNotice.open = false;
    setQcmDetail("qcm-detail-status", metadata.qcm_parameter_status);
    setQcmDetail("qcm-detail-source", metadata.qcm_parameter_source);
    setQcmDetail("qcm-detail-figure", metadata.qcm_figure);
    setQcmDetail("qcm-detail-curve", metadata.qcm_curve);
    setQcmDetail("qcm-detail-uncertainty", metadata.qcm_reading_uncertainty);
    setQcmDetail("qcm-detail-calibration", metadata.qcm_calibration_points);
    setQcmDetail("qcm-detail-interpolation", metadata.qcm_interpolation);
  }

  function savgolFilter(y, coeffs) {
    if (!Array.isArray(coeffs) || coeffs.length % 2 === 0 || y.length < coeffs.length) {
      return y;
    }
    const half = Math.floor(coeffs.length / 2);
    const padded = [
      ...y.slice(1, half + 1).reverse(),
      ...y,
      ...y.slice(-half - 1, -1).reverse(),
    ];
    const result = new Float64Array(y.length);
    for (let index = 0; index < y.length; index += 1) {
      let sum = 0;
      for (let coeffIndex = 0; coeffIndex < coeffs.length; coeffIndex += 1) {
        sum += coeffs[coeffIndex] * padded[index + coeffIndex];
      }
      result[index] = sum;
    }
    return result;
  }

  function smoothingControl() {
    return document.getElementById("result-smoothing") ?? document.getElementById("smoothing-toggle");
  }

  function syncLegacySmoothingControl(level) {
    const legacyControl = document.getElementById("smoothing-toggle");
    if (legacyControl) {
      legacyControl.value = level;
    }
  }

  function smoothingLevel() {
    const control = document.getElementById("result-smoothing");
    const legacyControl = document.getElementById("smoothing-toggle");
    if (control) {
      return control.value;
    }
    return legacyControl?.value ?? "medium";
  }

  function spectrumForDisplay(spectrum) {
    const rawExt = spectrum.raw_c_ext_m2 ?? spectrum.c_ext_m2;
    const rawSca = spectrum.raw_c_sca_m2 ?? spectrum.c_sca_m2;
    const level = smoothingLevel();
    if (level === "off") {
      const rawAbs = spectrum.raw_c_abs_m2 ?? spectrum.c_abs_m2;
      return { ...spectrum, c_ext_m2: rawExt, c_sca_m2: rawSca, c_abs_m2: rawAbs };
    }
    const coeffs = SMOOTHING_COEFFS[level];
    const smoothedExt = savgolFilter(rawExt, coeffs);
    const smoothedSca = savgolFilter(rawSca, coeffs);
    const smoothedAbs = smoothedExt.map((value, index) => value - smoothedSca[index]);
    return { ...spectrum, c_ext_m2: smoothedExt, c_sca_m2: smoothedSca, c_abs_m2: smoothedAbs };
  }

  function plotSpectrum(traces, layout, config, { preferReact = true } = {}) {
    if (preferReact && typeof window.Plotly.react === "function") {
      window.Plotly.react("spectrum-plot", traces, layout, config);
      return;
    }
    window.Plotly.newPlot("spectrum-plot", traces, layout, config);
  }

  function preservedAxisRanges() {
    const plotDiv = document.getElementById("spectrum-plot");
    const xRange = plotDiv?.layout?.xaxis?.range;
    const yRange = plotDiv?.layout?.yaxis?.range;
    const layout = {};
    if (Array.isArray(xRange)) {
      layout.xaxis = { range: [...xRange] };
    }
    if (Array.isArray(yRange)) {
      layout.yaxis = { range: [...yRange] };
    }
    return layout;
  }

  function renderResult(result, { preserveDownloadMetadata = false, resetZoom = false } = {}) {
    comparisonActive = false;
    clearComparisonError();
    latestResult = result;
    if (!preserveDownloadMetadata || !latestDownloadMetadata) {
      latestDownloadMetadata = buildDownloadMetadata(result);
    }
    const spectrum = spectrumForDisplay(result.spectrum);
    const toSquareNanometres = (values) =>
      values.map((value) => value * squareNanometresPerSquareMetre);
    const traces = [
      {
        x: spectrum.wavelength_nm,
        y: toSquareNanometres(spectrum.c_ext_m2),
        name: t("result.cExt"),
        mode: "lines",
        line: { color: "#1769aa", width: 3 },
      },
      {
        x: spectrum.wavelength_nm,
        y: toSquareNanometres(spectrum.c_sca_m2),
        name: t("result.cSca"),
        mode: "lines",
        line: { color: "#15803d", width: 2 },
      },
      {
        x: spectrum.wavelength_nm,
        y: toSquareNanometres(spectrum.c_abs_m2),
        name: t("result.cAbs"),
        mode: "lines",
        line: { color: "#b42318", width: 2 },
      },
    ];
    const layout = {
      margin: { t: 24, r: 20, b: 58, l: 72 },
      xaxis: { title: t("result.xAxis") },
      yaxis: { title: t("result.yAxis") },
      legend: { orientation: "h", y: 1.12 },
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      uirevision: "spectrum-plot",
    };
    if (!resetZoom) {
      const axisRanges = preservedAxisRanges();
      if (axisRanges.xaxis) {
        layout.xaxis = { ...layout.xaxis, ...axisRanges.xaxis };
      }
      if (axisRanges.yaxis) {
        layout.yaxis = { ...layout.yaxis, ...axisRanges.yaxis };
      }
    }
    const config = { responsive: true, displaylogo: false };
    plotSpectrum(traces, layout, config, { preferReact: !resetZoom });

    renderQcmNotice(result.qcm_metadata);
    renderWarnings(result.warnings, Boolean(result.qcm_metadata?.qcm_applied));
    document.getElementById("result-smoothing-control").hidden = false;
    document.getElementById("download-csv").disabled = false;
    document.getElementById("download-json").disabled = false;
  }

  function completeResult(result) {
    latestResult = result;
    latestDownloadMetadata = buildDownloadMetadata(result);
    const entries = window.PlasmonHistoryStore.add(result, latestDownloadMetadata);
    renderResult(result, { preserveDownloadMetadata: true, resetZoom: true });
    renderHistory(entries);
  }

  function metadataCommentLines(metadata) {
    return [
      "# plasmon_coupling_simulator_download_metadata",
      `# result_timestamp_utc=${metadata.result_timestamp_utc}`,
      `# particle_count=${metadata.particle_count}`,
      `# diameters_nm=${metadata.diameters_nm.join(";")}`,
      `# placement_type=${metadata.placement.type}`,
      `# placement_fingerprint=${metadata.placement.fingerprint}`,
      `# particle_positions_nm=${JSON.stringify(metadata.placement.particles)}`,
      `# minimum_surface_gap_nm=${metadata.minimum_surface_gap_nm ?? "not_applicable"}`,
      `# wavelength_range_nm=${metadata.wavelength_range_nm.start},${metadata.wavelength_range_nm.end},step=${metadata.wavelength_range_nm.step}`,
      `# qcm_applied=${metadata.qcm_applied}`,
      `# smoothing_level=${metadata.smoothing_level}`,
      `# experimental_quadrupole_coupling=${metadata.experimental_quadrupole_coupling}`,
      `# experimental_quadrupole_model=${metadata.experimental_quadrupole_metadata?.model ?? "not_applied"}`,
    ];
  }

  function downloadCsv() {
    if (!latestResult || !latestDownloadMetadata) {
      return;
    }
    const spectrum = latestResult.spectrum;
    const rows = [
      ...metadataCommentLines(latestDownloadMetadata),
      "wavelength_nm,c_ext_m2,c_sca_m2,c_abs_m2,q_ext,q_sca,q_abs,geometric_cross_section_m2,experimental_quadrupole_coupling",
    ];
    spectrum.wavelength_nm.forEach((wavelengthNm, index) => {
      rows.push(
        [
          wavelengthNm,
          spectrum.c_ext_m2[index],
          spectrum.c_sca_m2[index],
          spectrum.c_abs_m2[index],
          spectrum.q_ext[index],
          spectrum.q_sca[index],
          spectrum.q_abs[index],
          spectrum.geometric_cross_section_m2,
          latestDownloadMetadata.experimental_quadrupole_coupling,
        ].join(","),
      );
    });
    downloadBlob(
      `${latestDownloadMetadata.filename_stem}.csv`,
      `${rows.join("\n")}\n`,
      "text/csv;charset=utf-8",
    );
  }

  function downloadJson() {
    if (!latestResult || !latestDownloadMetadata) {
      return;
    }
    const resultWithDownloadMetadata = {
      ...latestResult,
      download_metadata: latestDownloadMetadata,
    };
    downloadBlob(
      `${latestDownloadMetadata.filename_stem}.json`,
      `${JSON.stringify(resultWithDownloadMetadata, null, 2)}\n`,
      "application/json",
    );
  }

  function historyEntryLabel(entry) {
    const timestamp = new Date(entry.timestamp_utc).toLocaleString();
    const modeKey = entry.calculation_mode === "exact_mie"
      ? "history.modeExactMie"
      : "history.modeCda";
    return t("history.entry", {
      timestamp,
      particleCount: entry.particle_count,
      mode: t(modeKey),
      stepNm: entry.input?.spectrum?.step_nm ?? t("result.missing"),
      qcm: entry.qcm_applied ? t("history.qcmOn") : t("history.qcmOff"),
      quadrupole: entry.experimental_quadrupole_coupling
        ? t("history.quadrupoleOn")
        : t("history.quadrupoleOff"),
    });
  }

  function displayedParticleValue(value) {
    const rounded = formatNumber(Number(value), 1);
    return rounded === null ? t("result.missing") : String(rounded);
  }

  function particlesForHistoryEntry(entry) {
    return Array.isArray(entry?.input?.particles) ? entry.input.particles : [];
  }

  function particleText(particle, index, translationKey) {
    return t(translationKey, {
      index: index + 1,
      diameterNm: displayedParticleValue(particle.diameter_nm),
      xNm: displayedParticleValue(particle.x_nm),
      yNm: displayedParticleValue(particle.y_nm),
      zNm: displayedParticleValue(particle.z_nm),
    });
  }

  function historyParticleSummary(entry) {
    const particles = particlesForHistoryEntry(entry);
    const maximumShownParticles = 3;
    const summary = particles
      .slice(0, maximumShownParticles)
      .map((particle, index) => particleText(particle, index, "history.particleCompact"));
    const remainingCount = particles.length - summary.length;
    if (remainingCount > 0) {
      summary.push(t("history.additionalParticles", { count: remainingCount }));
    }
    return summary.join(" / ") || t("result.missing");
  }

  function renderHistoryDetails(entry) {
    const summary = document.getElementById("history-detail-summary");
    const list = document.getElementById("history-detail-particles");
    if (!summary || !list) {
      return;
    }
    summary.textContent = historyEntryLabel(entry);
    list.replaceChildren();
    particlesForHistoryEntry(entry).forEach((particle, index) => {
      const item = document.createElement("li");
      item.textContent = particleText(particle, index, "history.particleDetail");
      list.append(item);
    });
  }

  function showHistoryDetails(entry) {
    const dialog = document.getElementById("history-detail-dialog");
    if (!dialog) {
      return;
    }
    detailHistoryEntry = entry;
    renderHistoryDetails(entry);
    if (dialog.open) {
      return;
    }
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }

  function closeHistoryDetails() {
    const dialog = document.getElementById("history-detail-dialog");
    if (!dialog) {
      return;
    }
    if (typeof dialog.close === "function" && dialog.open) {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
      detailHistoryEntry = null;
    }
  }

  function historyFilename(entry, extension) {
    return `${entry.download_metadata.filename_stem}_history.${extension}`;
  }

  function renderHistory(entries = window.PlasmonHistoryStore.read()) {
    const list = document.getElementById("history-list");
    if (!list) {
      return;
    }
    selectedHistoryIds = new Set(
      [...selectedHistoryIds].filter((entryId) =>
        entries.some((entry) => entry.id === entryId),
      ),
    );
    list.replaceChildren();
    if (entries.length === 0) {
      const empty = document.createElement("p");
      empty.className = "history-empty";
      empty.textContent = t("history.empty");
      list.append(empty);
    }
    entries.forEach((entry) => {
      const row = document.createElement("div");
      row.className = "history-entry";
      const select = document.createElement("input");
      select.type = "checkbox";
      select.checked = selectedHistoryIds.has(entry.id);
      select.setAttribute("aria-label", t("history.select"));
      select.addEventListener("change", () => {
        if (select.checked) {
          selectedHistoryIds.add(entry.id);
        } else {
          selectedHistoryIds.delete(entry.id);
        }
        updateHistoryControls(entries);
        if (comparisonActive) {
          if (selectedHistoryIds.size >= 2) {
            compareSelectedHistory();
          } else if (latestResult) {
            renderResult(latestResult, { preserveDownloadMetadata: true });
          }
        }
      });
      const information = document.createElement("div");
      information.className = "history-entry-info";
      const label = document.createElement("span");
      label.className = "history-entry-label";
      label.textContent = historyEntryLabel(entry);
      const particleSummary = document.createElement("span");
      particleSummary.className = "history-entry-particle-summary";
      particleSummary.textContent = historyParticleSummary(entry);
      information.append(label, particleSummary);
      const details = document.createElement("button");
      details.type = "button";
      details.className = "button-secondary history-entry-action history-detail-button";
      details.textContent = t("history.details");
      details.addEventListener("click", () => showHistoryDetails(entry));
      const download = document.createElement("button");
      download.type = "button";
      download.className = "button-secondary history-entry-action";
      download.textContent = t("history.downloadCsv");
      download.addEventListener("click", () => {
        downloadBlob(
          historyFilename(entry, "csv"),
          window.PlasmonHistoryStore.csvForEntry(entry),
          "text/csv;charset=utf-8",
        );
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "button-secondary history-entry-action";
      remove.textContent = t("history.delete");
      remove.addEventListener("click", () => {
        window.PlasmonHistoryStore.remove(entry.id);
        selectedHistoryIds.delete(entry.id);
        if (comparisonActive && selectedHistoryIds.size < 2 && latestResult) {
          renderResult(latestResult, { preserveDownloadMetadata: true });
        }
        renderHistory();
      });
      row.append(select, information, details, download, remove);
      list.append(row);
    });
    updateHistoryControls(entries);
  }

  function updateHistoryControls(entries = window.PlasmonHistoryStore.read()) {
    const compare = document.getElementById("history-compare");
    const selectAll = document.getElementById("history-select-all");
    const deselectAll = document.getElementById("history-deselect-all");
    const exportAll = document.getElementById("history-download-all");
    const clear = document.getElementById("history-clear");
    if (!compare || !selectAll || !deselectAll || !exportAll || !clear) {
      return;
    }
    compare.disabled = selectedHistoryIds.size < 2;
    selectAll.disabled = entries.length === 0;
    deselectAll.disabled = entries.length === 0;
    exportAll.disabled = entries.length === 0;
    clear.disabled = entries.length === 0;
  }

  function selectAllHistory() {
    const entries = window.PlasmonHistoryStore.read();
    selectedHistoryIds = new Set(entries.map((entry) => entry.id));
    renderHistory(entries);
    updateHistoryControls(entries);
  }

  function deselectAllHistory() {
    selectedHistoryIds = new Set();
    const wasComparisonActive = comparisonActive;
    comparisonActive = false;
    if (wasComparisonActive && latestResult) {
      renderResult(latestResult, { preserveDownloadMetadata: true });
    }
    renderHistory();
    updateHistoryControls();
  }

  const comparisonQuantityTranslationKey = Object.freeze({
    c_ext: "result.cExt",
    c_sca: "result.cSca",
    c_abs: "result.cAbs",
  });

  function comparisonControls() {
    const quantity = document.getElementById("history-compare-quantity");
    const normalizationMode = document.getElementById("history-normalization-mode");
    const referenceWavelength = document.getElementById("history-reference-wavelength-nm");
    if (!quantity || !normalizationMode || !referenceWavelength) {
      return null;
    }
    return {
      quantity: quantity.value,
      normalization: {
        mode: normalizationMode.value,
        referenceWavelengthNm: Number(referenceWavelength.value),
      },
    };
  }

  function updateComparisonSettingsVisibility() {
    const normalizationMode = document.getElementById("history-normalization-mode");
    const referenceContainer = document.getElementById(
      "history-reference-wavelength-container",
    );
    const referenceWavelength = document.getElementById("history-reference-wavelength-nm");
    if (!normalizationMode || !referenceContainer || !referenceWavelength) {
      return;
    }
    const requiresReference = normalizationMode.value === "reference";
    referenceContainer.hidden = !requiresReference;
    referenceWavelength.disabled = !requiresReference;
  }

  function comparisonErrorText(error) {
    const wavelengthNm = displayedParticleValue(Number(error?.parameters?.wavelengthNm));
    if (error?.code === "invalid_reference_wavelength") {
      return t("history.referenceWavelengthRequired");
    }
    if (error?.code === "reference_wavelength_out_of_range") {
      return t("history.referenceOutOfRange", { wavelengthNm });
    }
    if (error?.code === "normalization_zero") {
      return t("history.normalizationZero");
    }
    return t("api.simulateFailed");
  }

  function renderComparisonError() {
    const target = document.getElementById("history-comparison-error");
    if (!target) {
      return;
    }
    target.hidden = comparisonError === null;
    target.textContent = comparisonError === null ? "" : comparisonErrorText(comparisonError);
  }

  function clearComparisonError() {
    comparisonError = null;
    renderComparisonError();
  }

  function showComparisonError(error) {
    comparisonError = error;
    renderComparisonError();
  }

  function refreshActiveComparison() {
    if (comparisonActive && selectedHistoryIds.size >= 2) {
      compareSelectedHistory();
    }
  }

  function comparisonYAxisTitle(quantity, normalizationMode) {
    if (normalizationMode === "absolute") {
      return t("result.yAxis");
    }
    return t("history.normalizedYAxis", {
      quantity: t(comparisonQuantityTranslationKey[quantity]),
    });
  }

  function compareSelectedHistory() {
    const entries = window.PlasmonHistoryStore.read().filter((entry) =>
      selectedHistoryIds.has(entry.id),
    );
    if (entries.length < 2) {
      return;
    }
    const controls = comparisonControls();
    if (!controls) {
      return;
    }
    let series;
    try {
      series = window.PlasmonHistoryComparison.buildSeries(
        entries,
        controls.quantity,
        controls.normalization,
        { useSmoothed: smoothingLevel() !== "off" },
      );
    } catch (error) {
      showComparisonError(error);
      return;
    }
    clearComparisonError();
    comparisonActive = true;
    const colours = ["#1769aa", "#b42318", "#15803d", "#7c3aed", "#d97706", "#0f766e"];
    const traces = series.map((item, index) => ({
      x: item.wavelengthsNm,
      y: item.values,
      name: historyEntryLabel(item.entry),
      mode: "lines",
      line: { color: colours[index % colours.length], width: 2 },
    }));
    plotSpectrum(
      traces,
      {
        margin: { t: 24, r: 20, b: 58, l: 72 },
        xaxis: { title: t("result.xAxis") },
        yaxis: { title: comparisonYAxisTitle(controls.quantity, controls.normalization.mode) },
        legend: { orientation: "h", y: 1.12 },
        paper_bgcolor: "#ffffff",
        plot_bgcolor: "#ffffff",
        uirevision: "spectrum-plot",
      },
      { responsive: true, displaylogo: false },
      { preferReact: true },
    );
  }

  function downloadAllHistory() {
    const entries = window.PlasmonHistoryStore.read();
    if (entries.length === 0) {
      return;
    }
    downloadBlob(
      "plasmon_history.csv",
      `${window.PlasmonHistoryStore.csvForEntries(entries)}\n`,
      "text/csv;charset=utf-8",
    );
  }

  function initialize() {
    document.getElementById("download-csv").addEventListener("click", downloadCsv);
    document.getElementById("download-json").addEventListener("click", downloadJson);
    const modernSmoothingControl = document.getElementById("result-smoothing");
    const legacySmoothingControl = document.getElementById("smoothing-toggle");
    const simulationForm = document.getElementById("simulation-form");
    if (simulationForm) {
      simulationForm.addEventListener(
        "submit",
        () => {
          if (modernSmoothingControl && legacySmoothingControl) {
            modernSmoothingControl.value = legacySmoothingControl.value;
          }
        },
        true,
      );
    }
    modernSmoothingControl?.addEventListener("change", () => {
      syncLegacySmoothingControl(modernSmoothingControl.value);
      if (comparisonActive && selectedHistoryIds.size >= 2) {
        compareSelectedHistory();
      } else if (latestResult) {
        renderResult(latestResult, { preserveDownloadMetadata: true });
      }
    });
    legacySmoothingControl?.addEventListener("change", () => {
      if (modernSmoothingControl) {
        modernSmoothingControl.value = legacySmoothingControl.value;
      }
      if (comparisonActive && selectedHistoryIds.size >= 2) {
        compareSelectedHistory();
      } else if (latestResult) {
        renderResult(latestResult, { preserveDownloadMetadata: true });
      }
    });
    syncLegacySmoothingControl(smoothingLevel());
    document.getElementById("history-compare").addEventListener("click", compareSelectedHistory);
    document.getElementById("history-select-all").addEventListener("click", selectAllHistory);
    document.getElementById("history-deselect-all").addEventListener("click", deselectAllHistory);
    document.getElementById("history-compare-quantity").addEventListener("change", refreshActiveComparison);
    document.getElementById("history-normalization-mode").addEventListener("change", () => {
      updateComparisonSettingsVisibility();
      const referenceWavelength = document.getElementById("history-reference-wavelength-nm");
      if (referenceWavelength.value.trim() !== "" || referenceWavelength.disabled) {
        refreshActiveComparison();
      }
    });
    document
      .getElementById("history-reference-wavelength-nm")
      .addEventListener("change", refreshActiveComparison);
    document.getElementById("history-download-all").addEventListener("click", downloadAllHistory);
    document.getElementById("history-clear").addEventListener("click", () => {
      if (!window.confirm(t("history.clearConfirm"))) {
        return;
      }
      window.PlasmonHistoryStore.clear();
      selectedHistoryIds = new Set();
      comparisonActive = false;
      clearComparisonError();
      if (latestResult) {
        renderResult(latestResult, { preserveDownloadMetadata: true });
      }
      renderHistory();
    });
    document.getElementById("history-detail-close").addEventListener("click", closeHistoryDetails);
    document.getElementById("history-detail-dialog").addEventListener("close", () => {
      detailHistoryEntry = null;
    });
    updateComparisonSettingsVisibility();
    renderHistory();
    window.addEventListener("plasmonlanguagechange", () => {
      const shouldRenderComparison = comparisonActive && selectedHistoryIds.size >= 2;
      if (latestResult && !shouldRenderComparison) {
        renderResult(latestResult, {
          preserveDownloadMetadata: true,
        });
      }
      renderHistory();
      if (detailHistoryEntry) {
        renderHistoryDetails(detailHistoryEntry);
      }
      if (shouldRenderComparison) {
        compareSelectedHistory();
      } else {
        renderComparisonError();
      }
    });
  }

  return { completeResult, initialize, renderResult };
})();
