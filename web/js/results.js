window.PlasmonResults = (() => {
  const squareNanometresPerSquareMetre = 1.0e18;
  let latestResult = null;

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

  function renderWarnings(warnings) {
    const warningList = document.getElementById("warning-list");
    warningList.replaceChildren();
    warnings.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = warning;
      warningList.append(item);
    });
  }

  function renderResult(result) {
    latestResult = result;
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
        xaxis: { title: "真空波長 (nm)" },
        yaxis: { title: "断面積 (nm²)" },
        legend: { orientation: "h", y: 1.12 },
        paper_bgcolor: "#ffffff",
        plot_bgcolor: "#ffffff",
      },
      { responsive: true, displaylogo: false },
    );

    const qcmNotice = document.getElementById("qcm-notice");
    qcmNotice.hidden = !result.qcm_metadata.qcm_applied;
    renderWarnings(result.warnings);
    document.getElementById("download-csv").disabled = false;
    document.getElementById("download-json").disabled = false;
  }

  function downloadCsv() {
    if (!latestResult) {
      return;
    }
    const spectrum = latestResult.spectrum;
    const rows = ["wavelength_nm,c_ext_m2,c_sca_m2,c_abs_m2"];
    spectrum.wavelength_nm.forEach((wavelengthNm, index) => {
      rows.push(
        [
          wavelengthNm,
          spectrum.c_ext_m2[index],
          spectrum.c_sca_m2[index],
          spectrum.c_abs_m2[index],
        ].join(","),
      );
    });
    downloadBlob("plasmon_spectrum.csv", `${rows.join("\n")}\n`, "text/csv;charset=utf-8");
  }

  function downloadJson() {
    if (!latestResult) {
      return;
    }
    downloadBlob(
      "plasmon_simulation.json",
      `${JSON.stringify(latestResult, null, 2)}\n`,
      "application/json",
    );
  }

  function initialize() {
    document.getElementById("download-csv").addEventListener("click", downloadCsv);
    document.getElementById("download-json").addEventListener("click", downloadJson);
  }

  return { initialize, renderResult };
})();
