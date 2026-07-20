# Third-Party Notices

This document records third-party software, data, and scholarly references
used by this repository. It is a notice document and does not replace the
licenses or terms of the respective rights holders.

## Plotly.js

This repository bundles Plotly.js 2.24.1 locally at
`web/vendor/plotly-2.24.1.min.js` for offline graph rendering. Plotly.js is
licensed under the MIT License. The bundled file identifies its version,
copyright holder, and MIT license in its opening comment (lines 1--5), and
also refers to `plotly.min.js.LICENSE.txt` for license information.

## Optical constants and scholarly references

The Au optical-constants dataset and the scholarly references in this
repository remain the property of their original authors and rights holders.
The dataset provenance and applicable usage notes are recorded in
`data/optical_constants/metadata.yaml`; the bibliographic sources, including
Johnson and Christy (1972), are recorded in `docs/references.md`.

## Provisional QCM distance-dependent table

`data/qcm/gamma_g_au_digitized.csv` is a provisional, manually digitized
reference table derived from the Au jellium blue solid curve in Esteban et al.
(2012), *Nature Communications* 3, 825, Fig. 2d. It is not an
author-provided numerical table, fit, or quantitatively validated primary
dataset. Its source, reading uncertainty, absent calibration-point record, and
interpolation policy are retained in `data/qcm/metadata.yaml` and
`docs/quantum_corrected_model_integration.md`.

## Research-paper PDFs

Research-paper PDFs are not distributed or bundled with this repository. In
particular, the local Faraday Discussions PDF is excluded by `.gitignore`.
`docs/Faraday_Discussion_178_151-183_2015.md` retains only a bibliographic
record and project-specific notes.

## License scope

The repository's [MIT License](LICENSE) applies only to original source code
and documentation created by this repository's copyright holder. It does not
grant, relicense, or otherwise alter rights in third-party software, datasets,
research papers, digitized reference values, trademarks, or other third-party
materials.
