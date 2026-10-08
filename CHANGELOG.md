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

- At the time of making the repo public, license changed from **CC0 1.0 Universal** (public-domain dedication) to the **PolyForm Noncommercial License 1.0.0**. The software is now free for non-commercial use (research, teaching, and use by universities, public research bodies, and government institutions); commercial use requires a separate license. `LICENSE` replaced; a `Required Notice:` copyright line is included and must be preserved by anyone redistributing the code.
- `README.md`: added a `## License` section summarising the non-commercial terms and the contact for commercial licensing enquiries.

## [2026-10-08]

### Inputs

- New `--basement-bypass-coeff` flag (`cli.py`, `batch.py`) and "Cd" input in the Streamlit dashboard set the discharge coefficient of the ground↔basement bypass. Default 0.6.
- Previously hardcoded: 0.6 in `cli.py`, 1.0 in `batch.py` and `app.py`. Batch and dashboard runs with a bypass now use 0.6 by default; pass `--basement-bypass-coeff 1.0` to reproduce earlier results.

### Fixes

- Basement perimeter inflow was silently ignored in Monte Carlo runs (`cli.py --n-replicates > 1`, dashboard MC) and in the dashboard single run. Since the unified basement parsing, `Simulation` reads only its ingress list, but these callers still set only `Building.basement_ingress`. `fragility.run` and `app.py` now pass the perimeter (and the ground↔basement bypass, also missing in MC) as pathways.
- Regression and unit tests (`test_regression` ex04/06/07, `test_sump_pump`, `test_diagnostics`) and `examples/make_reference.py` updated the same way; all tests pass. Reference values unchanged.

### Examples

- New Case 05 (basement fills under a long 1.0 m flood): exercises the full-basement (merged compartment) behaviour; see the single engine refactor entry below.
- Former Cases 05–11 renumbered to 06–12 (directories, references, tests, report, schematics). Schematic grid now groups cases into rows of four by building type.

## [2026-10-08] — single engine refactor

### Architecture

- One path to the physics for every mode: `cli.py`, `batch.py` and `app.py` → `fragility.run` → `fragility.run_replicate` → `engine.run` → `Simulation`. A deterministic run is one replicate (nothing is sampled when no element is fragile).
- `engine.run(config, hydro, pathways=(), *, conductance_resolver, progress_callback)` is the only place a `Building` and `Simulation` are assembled (building geometry, sump, ground↔basement bypass). Removed its `basement_pathway` argument: exterior→basement pathways are ordinary pathways with `target='basement'`.
- `fragility.run(config, hydro, paths, membranes)` replaces `run_fragility_montecarlo` (no more `building_factory` / `static_pathways`). `ReplicateRecord` now holds the replicate's `SimResult` (`rec.result`).
- New `fragility.assemble_pathways` / `load_pathways`: the single place where ingress, basement and membrane rows become `(paths, membranes)` (basement targeting, membrane conversion, validation, representative paths). New `parse_pathway_text`; `parse_pathway_file` wraps it.
- New `inputs.py`: model flags shared by `cli.py` and `batch.py` (previously defined twice), plus `config_from_args` / `pathways_from_args`.
- New engine helpers `read_hydrograph`, `hydrograph_from_columns`, `exterior_series`, `TIME_UNIT_SECONDS` replace per-caller copies of hydrograph loading, unit conversion and exterior depth/velocity sampling.
- `batch.run_batch(config, cases, paths, membranes, …)` replaces the old keyword-per-parameter signature and the unused `batch.run`; deterministic and Monte Carlo rows come from the same loop.
- `plot.save_run_result`, `plot.save_run_animation` and `plot.save_run_schematic(config=…, pathways=…)` derive basement/sump/bypass display values from `SimConfig`. The animation no longer recomputes orifice flows; arrows use the engine trace.
- `examples/reference_cases.py` defines the validation cases once for `make_reference.py` and `tests/test_regression.py`.
- Removed: `Building.basement_ingress`, legacy `BasementFragility` hook and basement step resolvers, `parse_membrane_args`, `merge_membrane_source`, `parse_basement_fragility_args`, `report.run_diagnostics`, `engine.parse_ingress_text` / `parse_ingress_file` / `parse_external_text`.

### Behaviour changes

- Results are bit-identical to the previous version for all example outputs and for deterministic and Monte Carlo runs with basement, sump, bypass, velocity and floor datum (full traces compared), except:
  - References ex09, ex10 and ex12 changed: the reference generator never assigned the membrane's representative path, so membrane leakage was not applied. They now match what `cli.py` / `batch.py` produce (e.g. ex09 P50 peak depth 9.0e-5 m instead of 1.5e-7 m).
  - Monte Carlo `peak_h_ext` / `v_peak_ext` are now computed as in deterministic runs (sampled on the simulation grid; power-law velocity was reported as 0 in MC).
  - `cli.py --basement-ingress` now uses every row of the file (previously only the first); `batch.py` already did.
  - `--n-replicates 1` with fragile elements is one sampled replicate in both `cli.py` and `batch.py` (batch previously used the base state).
  - `batch.py`: `--floor` is now required (was 50 by default) and `--ingress` optional; `cli.py` gains `--floor-datum`. Both default `--basement-ceiling-elevation` to `--floor-datum`.
- The ex06 timestep-sensitivity figure now includes basement perimeter inflow (it was silently zero since the unified basement parsing).

### Physics fixes

- Full-basement surcharge: once the basement (and sump) is full to the ceiling and there is water above the ground floor, both act as one compartment. Exterior→basement pathways discharge against the ground-floor level, the bypass carries no flow, the pump draws from the merged volume, and a net outflow larger than the water above the floor is taken from the basement without loss. Previously the full basement kept driving inflow against its fixed ceiling level and pushed the ground floor above the exterior level (Case 05: 1.82 m indoors for a 1.0 m flood, now 0.96 m; strong airbricks with tight above-ground openings under `hydrographs/generated/0212.csv`: 54.9 m indoors for a 1.5 m flood, now 1.50 m). Same rule with and without a sump. Results are unchanged whenever the basement never fills.
- The ground-floor level recorded on a step where the basement overflows now includes that overflow (it was reported, and used for the next step's flows, one step late).
- The pump flow is capped at the water held in the sump and basement, so the recorded `Q_pump` matches what was removed (levels were already clipped at zero).
- New `tests/test_basement_surcharge.py`: indoor level bounded by exterior peak + velocity head (`hydrographs/generated/0212.csv`, strong airbricks, tight openings) and per-step mass balance across entry to and exit from the merged state (basement, basement + bypass, basement + sump).


### Stale code and docs removed

- `docs/datasets.md` rewritten for the dataset `hydrographs/generate.py` actually produces (297-case deterministic grid, 1-min step, `v = 1.5·h^0.5` in a third column, files in `hydrographs/generated/`); it described an earlier random 100-case dataset with separate velocity files, a `main.py` CLI and a non-existent `--external-velocity` flag.
- `docs/plots.md` rewritten from the current `plot.py` signatures (it documented removed functions such as `save_ingress_preview` and `parse_external_file`); every code example in it now runs.
- `docs/reference.md`: output tables and column names match what `cli.py` / `batch.py` write; CSV examples include the mandatory `reversible` column (three of them did not parse); `--basement-ingress` documented as multi-row.
- `docs/limitations.md`, `docs/model.md`, `docs/fragility.md`, `README.md`: references to removed code, flags and paths corrected; the sump overflow weir is documented as not applied (limitation D).
- CI: the smoke test called `main.py` and an `example_run/` folder that no longer exist (and YAML read Python `3.10` as `3.1`); it now runs `cli.py` and `batch.py` on the example inputs. Removed `tests/run_tests.py` (ran one test file; pytest is a requirement).
- `plot.save_simulation_result`: removed the `velocity_series` argument, which was accepted but never drawn. Removed unused locals and imports.
