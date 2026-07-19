window.PlasmonResults = (() => {
  const squareNanometresPerSquareMetre = 1.0e18;
  let latestResult = null;
  let latestDownloadMetadata = null;

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
      timestampToken(timestampUtc),
    ].join("_");
    return { ...conditions, filename_stem: filenameStem };
  }

  function renderWarnings(warnings, qcmApplied) {
    const warningList = document.getElementById("warning-list");
    warningList.replaceChildren();
    const displayWarnings = [...warnings];
    if (qcmApplied) {
      const nearInfraredCaveat = t("warning.nirCdaLimit");
      if (displayWarnings.length > 0) {
        displayWarnings[0] = `${displayWarnings[0]} ${nearInfraredCaveat}`;
      } else {
        displayWarnings.push(nearInfraredCaveat);
      }
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

  function renderResult(result, { preserveDownloadMetadata = false } = {}) {
    latestResult = result;
    if (!preserveDownloadMetadata || !latestDownloadMetadata) {
      latestDownloadMetadata = buildDownloadMetadata(result);
    }
    const spectrum = result.spectrum;
    const toSquareNanometres = (values) =>
      values.map((value) => value * squareNanometresPerSquareMetre);
    const traces = [
      {
        x: spectrum.wavelength_nm,
        y: toSquareNanometres(spectrum.c_ext_m2),
        name: "Cext",
        mode: "lines",
        line: { color: "#1769aa", width: 3 },
      },
      {
        x: spectrum.wavelength_nm,
        y: toSquareNanometres(spectrum.c_sca_m2),
        name: "Csca",
        mode: "lines",
        line: { color: "#15803d", width: 2 },
      },
      {
        x: spectrum.wavelength_nm,
        y: toSquareNanometres(spectrum.c_abs_m2),
        name: "Cabs",
        mode: "lines",
        line: { color: "#b42318", width: 2 },
      },
    ];
    window.Plotly.newPlot(
      "spectrum-plot",
      traces,
      {
        margin: { t: 24, r: 20, b: 58, l: 72 },
        xaxis: { title: t("result.xAxis") },
        yaxis: { title: t("result.yAxis") },
        legend: { orientation: "h", y: 1.12 },
        paper_bgcolor: "#ffffff",
        plot_bgcolor: "#ffffff",
      },
      { responsive: true, displaylogo: false },
    );

    renderQcmNotice(result.qcm_metadata);
    renderWarnings(result.warnings, Boolean(result.qcm_metadata?.qcm_applied));
    document.getElementById("download-csv").disabled = false;
    document.getElementById("download-json").disabled = false;
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
    ];
  }

  function downloadCsv() {
    if (!latestResult || !latestDownloadMetadata) {
      return;
    }
    const spectrum = latestResult.spectrum;
    const rows = [
      ...metadataCommentLines(latestDownloadMetadata),
      "wavelength_nm,c_ext_m2,c_sca_m2,c_abs_m2,q_ext,q_sca,q_abs,geometric_cross_section_m2",
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

  function initialize() {
    document.getElementById("download-csv").addEventListener("click", downloadCsv);
    document.getElementById("download-json").addEventListener("click", downloadJson);
    window.addEventListener("plasmonlanguagechange", () => {
      if (latestResult) {
        renderResult(latestResult, { preserveDownloadMetadata: true });
      }
    });
  }

  return { initialize, renderResult };
})();
