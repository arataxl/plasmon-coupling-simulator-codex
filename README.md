# Plasmonic Coupling Simulator

Japanese version: [README-JP.md](README-JP.md)

Plasmonic Coupling Simulator is a local web application for researchers and students who want to explore optical trends in assemblies of gold (Au) nanospheres. It calculates extinction, scattering, and absorption spectra with the Coupled Dipole Approximation (CDA) and a limited Quantum Corrected Model (QCM) path for sub-nanometre gaps.

It is a condition-exploration tool, not a quantitative reproducer of experiments and not a replacement for BEM, DDA, FDTD, or TDDFT.

## What the MVP provides

- Au nanospheres only: 1–20 particles, each with an independently editable diameter and 3D centre coordinate.
- Complete single-sphere Mie calculations as a reference, and FCDA-based multi-particle CDA with a retarded dyadic Green tensor.
- Extinction (`C_ext`), scattering (`C_sca`), absorption (`C_abs`), and their efficiencies (`Q_ext`, `Q_sca`, `Q_abs`) as spectra.
- A static local web UI with English as the initial language and a Japanese toggle, a 3D geometry preview, dimer/equilateral-trimer/random-cluster presets, SSE progress updates, and cooperative cancellation.
- Browser-side CSV/JSON downloads that include calculation conditions and do not save results on the server. Exported JSON can be validated and used for the same calculation again.

The detailed MVP boundary and acceptance criteria are in [docs/SPEC.md](docs/SPEC.md).

## Physical scope and limitations

All core calculations use SI units. The UI, API, and CSV/JSON boundaries convert to and from nm where needed. The supported MVP model is limited to spherical Au particles with diameters from 2 to 100 nm in a homogeneous, isotropic, non-absorbing medium, over an initial wavelength range of 200–1500 nm.

| Condition | Application behaviour | Interpretation |
| --- | --- | --- |
| Surface gap `< 0.5 nm` | Blocked by both UI and API; values are not silently rounded. | Outside the model: contact and charge-transfer-plasmon regimes are not represented. |
| `0.5 <= gap < 1.0 nm` | QCM is selected automatically and cannot be disabled through the UI/API. | Reference result using a provisional digitized Au curve from Esteban et al. (2012), Fig. 2d. Provenance is retained in JSON and the result UI. |
| `1.0 <= gap <= 5.0 nm` | Classical CDA is used and a CDA dipole-approximation warning is shown. | Use for trend exploration or semi-quantitative comparison. |
| Diameter `<= 40 nm` and `gap > 5 nm` | Preferred CDA exploration region. | Experimental quantitative agreement is still not guaranteed. |
| Diameter `40–100 nm` | Higher-order multipoles may matter; the MVP has no diameter-triggered automatic warning. | Treat as qualitative or semi-quantitative; compare with BEM/DDA/FDTD where needed. |

The QCM distance-dependent `gamma_g` values are a versioned, manually digitized reference table for the Au jellium blue solid curve in Esteban et al. (2012), Fig. 2d. Interpolation is shape-preserving PCHIP in `log(gamma_g)`. The table is provisional, has an estimated 5–10% reading uncertainty, and is not extrapolated. Above its 5.439 Å upper separation, QCM-selected pairs use the classical limit and the result reports that status explicitly. The MVP's four-layer QCM construction is a volume-equivalent auxiliary bridge-dipole reduction, not a reproduction of the paper's BEM/FEM model.

The near-infrared response can be underestimated because CDA omits higher-order multipole coupling. BEM, DDA, or FDTD can therefore yield different results.

Kreibig size correction remains an internal physics-core hook and is off by default. It is not exposed through the MVP UI or API because compatible primary-source parameters for the Johnson and Christy bulk `n + ik` model have not been established. The Au jellium Drude values used in the QCM context are not reused for that correction.

For the authoritative physical assumptions and QCM integration details, see [docs/physics_assumptions.md](docs/physics_assumptions.md) and [docs/quantum_corrected_model_integration.md](docs/quantum_corrected_model_integration.md).

## Architecture

- `src/physics/`: Mie reference calculations, FCDA polarizability, Green tensor, CDA solver, and QCM support.
- `src/api/` and `src/services/`: FastAPI routes, structured errors/warnings, calculation orchestration, SSE jobs, and cancellation.
- `web/`: static HTML/CSS/JavaScript and a bundled Plotly.js 2.24.1 asset.
- `src/io/` and `src/schemas/`: unit conversions, versioned QCM-table loading, reproducible JSON/CSV handling, and Pydantic contracts.

The application listens only on `127.0.0.1`. After the first setup, starting, calculating, visualising, and downloading work offline. Plotly.js is bundled and verified against its expected SHA-256 during setup if the asset is missing.

## Setup and run (Windows)

The project uses Python 3.12 through the Windows Python Launcher.

```powershell
setup_windows.bat
run_app.bat
```

`setup_windows.bat` creates `.venv`, installs the approved dependencies, and verifies the bundled Plotly.js asset. Then open <http://127.0.0.1:8000/>. `run_app.bat` binds only to `127.0.0.1`.

Run validation and lint checks with:

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check src tests
```

## API and exports

- `POST /simulate` returns a completed result. Its spectrum grid is capped at 301 points.
- `POST /simulate/jobs`, `GET /simulate/stream/{job_id}`, and `POST /simulate/jobs/{job_id}/cancel` provide SSE progress and cooperative cancellation. Partial spectra are neither returned nor saved after cancellation.
- Results carry language-independent warning/error codes and numeric parameters; the UI translates them into the selected language.
- CSV includes wavelength, cross sections, efficiencies, and the aggregate geometric cross section. JSON includes inputs, results, provenance, and QCM metadata when applicable.

## Validation

The test suite covers complete Mie reference calculations, the isolated CDA limit, dimer coupling, QCM safety and integration, multi-particle stability, and I/O reproducibility. The formal tests and thresholds are defined in [docs/validation_plan.md](docs/validation_plan.md).

## Human–Codex collaboration record

This project used an iterative human-review and Codex-implementation cycle. AI output was not treated as evidence for physics, experimental values, or literature claims.

| Human discovery or decision | Codex implementation work |
| --- | --- |
| Browser testing revealed that highly precise preset coordinates could prevent a spectrum calculation after they were inserted into numeric form controls. | Implemented display-time coordinate rounding with post-rounding gap validation, plus regression tests. |
| Human review identified that fixed-pixel 3D markers did not show physical particle size under zoom. | Replaced them with real-diameter `mesh3d` sphere geometry, labels, equal-axis scaling, and rendering safeguards. |
| Audit review found that the QCM range and the 1–5 nm classical-CDA warning were described inconsistently. | Separated structured QCM and CDA warning codes, translated them in both UI languages, added boundary tests, and synchronized the documentation. |

Humans retained responsibility for identifying issues in real browser use, choosing the product and physics scope, approving physical assumptions, and reviewing completed behaviour. Codex implemented the approved changes, maintained tests and documentation, and reported verification results.

## References and project documents

- [docs/SPEC.md](docs/SPEC.md): MVP scope, priorities, acceptance criteria, and deadline
- [docs/physics_assumptions.md](docs/physics_assumptions.md): physical assumptions and valid range
- [docs/quantum_corrected_model_integration.md](docs/quantum_corrected_model_integration.md): QCM integration and provisional digitized-table policy
- [docs/validation_plan.md](docs/validation_plan.md): Validation Tests 1–6
- [docs/references.md](docs/references.md): cited literature
- [LICENSE](LICENSE): MIT License for original repository source code and documentation
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): third-party software, data, and scholarly-material notices
