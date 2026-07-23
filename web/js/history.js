window.PlasmonHistoryStore = (() => {
  const storageKey = "plasmon-coupling-simulator.history.v1";
  const maximumEntries = 30;

  function read() {
    try {
      const serialized = window.localStorage.getItem(storageKey);
      if (!serialized) {
        return [];
      }
      const entries = JSON.parse(serialized);
      return Array.isArray(entries) ? entries : [];
    } catch (_error) {
      return [];
    }
  }

  function write(entries) {
    window.localStorage.setItem(storageKey, JSON.stringify(entries.slice(0, maximumEntries)));
  }

  function createEntry(result, downloadMetadata) {
    const timestampUtc = new Date().toISOString();
    const particleCount = result.input.particles.length;
    return {
      id: `${timestampUtc}-${Math.random().toString(36).slice(2, 10)}`,
      timestamp_utc: timestampUtc,
      calculation_mode: result.input.simulation_mode ?? "cda",
      particle_count: particleCount,
      qcm_applied: Boolean(result.qcm_metadata?.qcm_applied),
      smoothing_level: result.smoothing_level,
      experimental_quadrupole_coupling: Boolean(
        result.experimental_quadrupole_metadata?.applied,
      ),
      input: result.input,
      spectrum: result.spectrum,
      qcm_metadata: result.qcm_metadata ?? null,
      experimental_quadrupole_metadata: result.experimental_quadrupole_metadata ?? null,
      download_metadata: downloadMetadata,
    };
  }

  function add(result, downloadMetadata) {
    const entry = createEntry(result, downloadMetadata);
    const entries = [entry, ...read()].slice(0, maximumEntries);
    write(entries);
    return entries;
  }

  function remove(entryId) {
    const entries = read().filter((entry) => entry.id !== entryId);
    write(entries);
    return entries;
  }

  function clear() {
    window.localStorage.removeItem(storageKey);
    return [];
  }

  function metadataCommentLines(metadata) {
    return [
      "# plasmon_coupling_simulator_download_metadata",
      `# result_timestamp_utc=${metadata.result_timestamp_utc}`,
      `# particle_count=${metadata.particle_count}`,
      `# calculation_mode=${metadata.calculation_mode ?? "cda"}`,
      `# qcm_applied=${metadata.qcm_applied}`,
      `# smoothing_level=${metadata.smoothing_level}`,
      `# experimental_quadrupole_coupling=${metadata.experimental_quadrupole_coupling}`,
    ];
  }

  function csvForEntry(entry) {
    const metadata = {
      ...entry.download_metadata,
      calculation_mode: entry.calculation_mode,
    };
    const spectrum = entry.spectrum;
    const rows = [
      ...metadataCommentLines(metadata),
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
          entry.experimental_quadrupole_coupling,
        ].join(","),
      );
    });
    return `${rows.join("\n")}\n`;
  }

  function csvForEntries(entries) {
    const rows = [
      "history_id,result_timestamp_utc,calculation_mode,particle_count,minimum_surface_gap_nm,placement_fingerprint,qcm_applied,smoothing_level,experimental_quadrupole_coupling,wavelength_nm,c_ext_m2,c_sca_m2,c_abs_m2,q_ext,q_sca,q_abs,geometric_cross_section_m2",
    ];
    entries.forEach((entry) => {
      const metadata = entry.download_metadata;
      entry.spectrum.wavelength_nm.forEach((wavelengthNm, index) => {
        rows.push(
          [
            entry.id,
            entry.timestamp_utc,
            entry.calculation_mode,
            entry.particle_count,
            metadata.minimum_surface_gap_nm ?? "not_applicable",
            metadata.placement.fingerprint,
            entry.qcm_applied,
            entry.smoothing_level,
            entry.experimental_quadrupole_coupling,
            wavelengthNm,
            entry.spectrum.c_ext_m2[index],
            entry.spectrum.c_sca_m2[index],
            entry.spectrum.c_abs_m2[index],
            entry.spectrum.q_ext[index],
            entry.spectrum.q_sca[index],
            entry.spectrum.q_abs[index],
            entry.spectrum.geometric_cross_section_m2,
          ].join(","),
        );
      });
    });
    return `${rows.join("\n")}\n`;
  }

  return {
    maximumEntries,
    read,
    add,
    remove,
    clear,
    csvForEntry,
    csvForEntries,
  };
})();
