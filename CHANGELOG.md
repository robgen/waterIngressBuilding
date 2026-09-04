# Changelog

All notable changes to this project are documented in this file.

## [planned — major refactor]

### Documentation reorganisation

- `docs/` consolidated from eight files to five: `model.md`, `fragility.md`, `limitations.md`, `reference.md`, `datasets.md`.
- `docs/model.md`: complete rewrite of `TECHNICAL.md`; absorbs `sump_pump_extension_spec.md` and the Streamlit dashboard section; adds code architecture and regression contract.
- `docs/fragility.md`: clean rewrite of `fragility_ingress_spec.md`; retains physics and calibration sections; removes stale input format descriptions.
- `docs/limitations.md`: cleaned up `KNOWN_LIMITATIONS.md`; resolved items condensed to a summary table.
- `docs/reference.md`: replaces `README_INPUTS.md` and `INPUTOUTPUT.md`; covers all inputs, CLI flags, and output files in one place.
- `docs/datasets.md`: replaces `hydrographs/HYDROGRAPH_GENERATION.md`.
- Deleted: `NOTE_montecarlo.md`, `WISHLIST.md`, `INTERPRETATION_DASHBOARD_TUTORIAL.md`, `sump_pump_extension_spec.md`, `fragility_ingress_spec.md`, `README_INPUTS.md`, `INPUTOUTPUT.md`, `hydrographs/NOTE_combined_input_format.md`, `example_run/example_fragility_README.md`.
- `README.md` rewritten: conceptual intro, documentation table, run-mode table, examples for all five modes, outputs summary, roadmap.
- `.gitignore` updated: simulation outputs from `example_run/`, `parametric_run/` excluded.
- Naming convention: all docs files lowercase; only `README.md`, `CHANGELOG.md`, `LICENSE` retain uppercase (conventional).

### Architecture

- New module `engine.py`: canonical single-simulation runner, extracted from `main.py`. Owns `Building`, `IngressPath`, `SimConfig`, `Hydrograph`, `SimResult`, and `engine.run(config, hydro) → SimResult`.
- `fragility.py` refactored: now a Monte Carlo wrapper that calls `engine.run()` once per replicate. Exposes `fragility.run(config, hydro) → MonteCarloResult`.
- `batch.py` (renamed from `batch_run.py`): now a thin iterator — discovers hydrograph files, calls `engine.run()` or `fragility.run()` per file, aggregates results. Exposes `batch.run(config, hydro_dir) → BatchResult`. No longer re-implements building configuration.
- Batch + fragility now composable: `batch.run()` runs full Monte Carlo for each hydrograph when `config.montecarlo` is set.
- `damage.py` → `loss.py`: more expressive name for vulnerability/loss curve logic.
- `viz.py` → `plot.py`: more expressive name; methods renamed `plot.simulation()`, `plot.batch()`, `plot.montecarlo()`.
- `diagnostics.py` → `report.py`: more expressive name; methods renamed `report.generate()`, `report.to_csv()`.
- `streamlit_app.py` → `app.py`.
- `main.py` → `cli.py`: now a thin shim only; all simulation logic moved to `engine`, `fragility`, `batch`.

### Inputs

- Unified pathway CSV format: a single header-based CSV format is used for all pathway inputs (ground-floor ingress, basement perimeter opening, membranes). One parser handles all three; routing is determined by CLI flag (`--ingress`, `--basement-ingress`, `--membrane`).
- Fragility state columns are optional extensions to the base pathway columns; omitting them gives a deterministic pathway. No separate "fragility format" is needed.
- Basement perimeter opening (`--basement-ingress`): previously configured via indexed CLI args (`--basement-ingress-*`, `--basement-state-name-1`, …). Now specified as a single-row CSV file using the same format as the ingress file.
- Sump and pump flags unified under `--sumppump-*` prefix (previously split between `--sump-*` and `--pump-*`). The two components are always configured together; the prefix reflects this.
- No backward compatibility with old ingress file formats. Existing input files must be updated to the header-based format.

### Testing

- `tests/test_regression.py`: new regression test suite that runs all nine validation case studies programmatically and compares peak metrics against reference values in `case_studies/reference/`.
- Reference metric JSON files stored in `case_studies/reference/exNN.json` (generated once and committed). Tolerances: 1 % for peak depths, 5 % for volumes.
- Three new case studies added: ex10 (basement + fragility), ex11 (batch deterministic), ex12 (batch + fragility).

## [2025-10-28]

- Added Streamlit-based web UI: `streamlit_app.py` (replaces legacy Tk GUI).
- Added headless plotting/animation helpers in `viz.py` (Agg backend).
- Exposed user-controlled simulation timestep (`--dt` and Streamlit input).
- Added ingress name support in input format (optional 4th column).
- Implemented ingress-locations plotting and improved labels to reduce overlap.
- Added tests (`tests/test_simulation.py`) and a lightweight runner (`tests/run_tests.py`).
- Added GitHub Actions CI workflow (`.github/workflows/ci.yml`).
- Added documentation under `docs/` with input reference and a technical description.
- Initial refactor and feature additions during interactive session: parsing fixes, GUI refactor, animation support, example inputs in `example_run/`.
- Default time unit changed to minutes (CLI `--time-units`, Streamlit defaults to minutes). Default timestep when omitted is now 1 (in selected units) — i.e. 1 minute by default.
- Added `--temp-output` CLI flag to write outputs to a temporary directory that is removed on exit (useful for tests and smoke runs).
- Streamlit UI: ingress locations plot is shown in the uploader preview (better visual feedback); the app no longer uses deprecated Streamlit parameters and displays animated GIFs inline.
- Streamlit run output now shows only the final simulation result PNG (and optionally the animation) after executing the simulation, reducing UI clutter.

## [2025-11-06]

- Added analytical hydrostatic and hydrodynamic lateral force calculations and overturning moment outputs (closed-form formulas only). Implemented in `forces.py`.
- Added CLI flags: `--compute-forces`, `--building-width`, `--drag-coeff`, and `--rho` to enable force time-series computation and adjust parameters.
- Added plotting helper `viz.save_forces_result` and `forces.csv`/`forces_result.png` outputs when `--compute-forces` is used.
- Velocity handling: external velocity hydrograph remains supported; forces use sampled/padded velocity series (assumed orthogonal to flow-facing façade).
- Added unit tests for force formulas (`tests/test_forces.py`) and example runner that demonstrates force outputs.


## [2026-09-04]

### Licensing

- License changed from **CC0 1.0 Universal** (public-domain dedication) to the **PolyForm Noncommercial License 1.0.0**. The software is now free for non-commercial use (research, teaching, and use by universities, public research bodies, and government institutions); commercial use requires a separate license. `LICENSE` replaced; a `Required Notice:` copyright line is included and must be preserved by anyone redistributing the code.
- `README.md`: added a `## License` section summarising the non-commercial terms and the contact for commercial licensing enquiries.
