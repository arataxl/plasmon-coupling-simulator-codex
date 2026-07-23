window.PlasmonHistoryComparison = (() => {
  const squareNanometresPerSquareMetre = 1.0e18;
  const spectrumFieldByQuantity = Object.freeze({
    c_ext: "c_ext_m2",
    c_sca: "c_sca_m2",
    c_abs: "c_abs_m2",
  });

  class HistoryComparisonError extends Error {
    constructor(code, parameters = {}) {
      super(code);
      this.code = code;
      this.parameters = parameters;
    }
  }

  function finiteSeries(entry, quantity, { useSmoothed = true } = {}) {
    const field = spectrumFieldByQuantity[quantity];
    const spectrum = entry?.spectrum;
    const wavelengthsNm = spectrum?.wavelength_nm;
    const rawField = `raw_${field}`;
    const valuesM2 = !useSmoothed && Array.isArray(spectrum?.[rawField])
      ? spectrum[rawField]
      : spectrum?.[field];
    if (
      !field ||
      !Array.isArray(wavelengthsNm) ||
      !Array.isArray(valuesM2) ||
      wavelengthsNm.length === 0 ||
      wavelengthsNm.length !== valuesM2.length
    ) {
      throw new HistoryComparisonError("invalid_spectrum");
    }
    if (
      !wavelengthsNm.every(Number.isFinite) ||
      !valuesM2.every(Number.isFinite) ||
      wavelengthsNm.some((wavelengthNm, index) =>
        index > 0 && wavelengthNm <= wavelengthsNm[index - 1]
      )
    ) {
      throw new HistoryComparisonError("invalid_spectrum");
    }
    return { wavelengthsNm, valuesM2 };
  }

  function peakTopNormalised(values) {
    const peak = Math.max(...values);
    if (!Number.isFinite(peak) || peak === 0) {
      throw new HistoryComparisonError("normalization_zero");
    }
    return values.map((value) => value / peak);
  }

  function valueAtWavelength(wavelengthsNm, values, referenceWavelengthNm) {
    if (!Number.isFinite(referenceWavelengthNm)) {
      throw new HistoryComparisonError("invalid_reference_wavelength");
    }
    const first = wavelengthsNm[0];
    const last = wavelengthsNm[wavelengthsNm.length - 1];
    if (referenceWavelengthNm < first || referenceWavelengthNm > last) {
      throw new HistoryComparisonError("reference_wavelength_out_of_range", {
        wavelengthNm: referenceWavelengthNm,
      });
    }
    for (let index = 0; index < wavelengthsNm.length; index += 1) {
      if (wavelengthsNm[index] === referenceWavelengthNm) {
        return values[index];
      }
      if (wavelengthsNm[index] > referenceWavelengthNm) {
        const lowerWavelengthNm = wavelengthsNm[index - 1];
        const upperWavelengthNm = wavelengthsNm[index];
        const fraction =
          (referenceWavelengthNm - lowerWavelengthNm) /
          (upperWavelengthNm - lowerWavelengthNm);
        return values[index - 1] + fraction * (values[index] - values[index - 1]);
      }
    }
    return values[values.length - 1];
  }

  function referenceNormalised(wavelengthsNm, values, referenceWavelengthNm) {
    const referenceValue = valueAtWavelength(wavelengthsNm, values, referenceWavelengthNm);
    if (!Number.isFinite(referenceValue) || referenceValue === 0) {
      throw new HistoryComparisonError("normalization_zero", {
        wavelengthNm: referenceWavelengthNm,
      });
    }
    return values.map((value) => value / referenceValue);
  }

  function buildSeries(entries, quantity, normalization, options = {}) {
    const mode = normalization?.mode ?? "absolute";
    if (!Object.hasOwn(spectrumFieldByQuantity, quantity)) {
      throw new HistoryComparisonError("invalid_quantity");
    }
    if (!Array.isArray(entries) || entries.length === 0) {
      throw new HistoryComparisonError("invalid_spectrum");
    }
    return entries.map((entry) => {
      const { wavelengthsNm, valuesM2 } = finiteSeries(entry, quantity, options);
      let values;
      if (mode === "absolute") {
        values = valuesM2.map((value) => value * squareNanometresPerSquareMetre);
      } else if (mode === "peak") {
        values = peakTopNormalised(valuesM2);
      } else if (mode === "reference") {
        values = referenceNormalised(
          wavelengthsNm,
          valuesM2,
          Number(normalization?.referenceWavelengthNm),
        );
      } else {
        throw new HistoryComparisonError("invalid_normalization_mode");
      }
      return { entry, wavelengthsNm, values };
    });
  }

  return {
    HistoryComparisonError,
    buildSeries,
    peakTopNormalised,
    referenceNormalised,
    valueAtWavelength,
  };
})();
