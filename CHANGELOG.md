# Changelog

All notable changes to this project are documented in this file.

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


## [2026-04-22] — refactor and documentation reorganisation

### Architecture

- `main.py` split into `engine.py` (`Building`, `IngressPathway`, `Simulation`, `SimConfig`, `Hydrograph`, `SimResult`, `engine.run`) and a thin command-line entry point `cli.py`.
- Renames: `batch_run.py` → `batch.py`, `damage.py` → `loss.py`, `viz.py` → `plot.py`, `diagnostics.py` → `report.py`, `streamlit_app.py` → `app.py`; `case_studies/` → `examples/`.
- `fragility.py` exposes `fragility.run(config, hydro, …) → MonteCarloResult` for the Monte Carlo ensemble.

### Inputs

- Unified header-based pathway CSV for ground-floor ingress, basement openings and membranes (`--ingress`, `--basement-opening`, `--membrane`); fragility state columns are optional extensions. The positional ingress format is no longer accepted.
- Basement opening defined as a CSV file (`--basement-opening`, later `--basement-ingress`) instead of indexed CLI flags.
- Sump and pump flags unified under the `--sumppump-*` prefix.

### Documentation

- `docs/` consolidated into `model.md`, `fragility.md`, `limitations.md`, `reference.md`, `datasets.md` (replacing `TECHNICAL.md`, `KNOWN_LIMITATIONS.md`, `README_INPUTS.md`, `INPUTOUTPUT.md`, `fragility_ingress_spec.md`, `sump_pump_extension_spec.md`, `INTERPRETATION_DASHBOARD_TUTORIAL.md`, `NOTE_montecarlo.md`, `WISHLIST.md`, `hydrographs/HYDROGRAPH_GENERATION.md`).
- `README.md` rewritten: introduction, documentation table, run modes with examples, outputs, roadmap.

### Testing

- `tests/test_regression.py` re-runs the validation cases and compares peak metrics with `examples/reference/exNN.json` (written by `examples/make_reference.py`); tolerances 1 % on peak depths, 5 % on volumes.

## [2026-09-04]

### Licensing

- At the time of making the repo public, license changed from **CC0 1.0 Universal** (public-domain dedication) to the **PolyForm Noncommercial License 1.0.0**. The software is now free for non-commercial use (research, teaching, and use by universities, public research bodies, and government institutions); commercial use requires a separate license. `LICENSE` replaced; a `Required Notice:` copyright line is included and must be preserved by anyone redistributing the code.
- `README.md`: added a `## License` section summarising the non-commercial terms and the contact for commercial licensing enquiries.

## [2026-10-08] — bypass Cd, Monte Carlo basement inflow, Case 05

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

## [2026-10-08] — sump as a third compartment

### Physics

- The sump is a pit below the basement floor with its **top at the basement floor**: depth = `basement_floor_elevation − sump_base_elevation` (must be > 0). It is a compartment of its own (level `h_sump` ≤ depth):
  - exterior→basement pathways discharge into the pit (as before);
  - basement water drains into the pit through its opening (orifice at the basement floor; area `opening_area`, default the whole pit, coefficient `opening_coeff`), capped each step at the room in the pit and the water above it;
  - a full pit spills onto the basement floor in the same step;
  - the pump draws from the pit only, never more than it holds.
- The merging rule now covers the whole chain pit → basement → ground floor: a full compartment with water above it shares that compartment's surface, and a deficit is taken from the members below (basement first, then the pit).
- Previously sump and basement were one lumped volume with the sump crest measured from the sump base but basement water from the basement floor (0.8 m apart in Cases 06–07), and the weir overflow parameters had no effect. Runs without a sump are bit-identical.

### Inputs

- `SumpPump`: removed `overflow_level`, `overflow_coeff`, `overflow_exponent`; added `opening_area` (default `sump_area`) and `opening_coeff` (default 0.6). Removed `pump.compute_sump_overflow`.
- CLI: removed `--sumppump-overflow-level`, `--sumppump-overflow-coeff`, `--sumppump-overflow-exponent`; added `--sumppump-opening-area`, `--sumppump-opening-coeff`. `--sumppump-base-elevation` must be below `--basement-floor-elevation`.
- App: the sump section takes the pit base (default 0.8 m below the basement floor), opening area (0 = whole pit) and Cd instead of the overflow crest, coefficient and exponent.

### Outputs

- Trace: `Q_sump_overflow` is the pit spilling onto the basement floor (it was always zero); new `Q_b_sump` is basement water draining into the pit. Diagnostics and the dashboard label them "sump spill".
- Plots: the sump reference line is the pit top (basement floor); `sump_overflow_level` arguments renamed `sump_depth`.

### Examples

- Cases 06–07: pit base moved from −2.5 m to −3.3 m (0.8 m pit below the −2.5 m basement floor); lift head at peak flood 3.8 m instead of 3.0 m. Case 06: peak sump 0.80 m, basement 0.002 m (60 s timestep artefact, unchanged in size). Case 07: the pit fills at 12 min and the basement peaks at 0.21 m (was 0.12 m); after the flood the pump drains the basement back through the pit and empties both (the basement water previously stayed). References, report text and the timestep-sensitivity figure updated (dt_crit 1.4 s).

## [2026-10-09] — velocity head only at a wetted opening

- `IngressPathway.compute_flow` added the velocity head v²/2g even when the exterior water was below the sill. Two consequences, on `main` and `refactor`, with and without a pump, whenever the velocity is nonzero (`file` or `power_law`):
  - an opening whose sill equals the floor datum let water in from velocity alone when the floor was dry (target level exactly at the sill): in the 0.01 m-peak events the ground floor gained ≈ v²/2g ≈ 1.3 mm;
  - interior water above a sill could not drain, or was pushed further in, while a flowing street stayed below the sill.
- The velocity head is now added only when the source water is above the sill. Zero-velocity runs (all validation examples) are unchanged.
- Tests in `tests/test_velocity.py`: no inflow from velocity alone, unobstructed drainage below the sill, velocity head still applied once the sill is reached, and a dry floor for `hydrographs/generated/0001.csv` against an opening at the floor datum in every velocity mode.

## [2026-10-09] — lateral forces, documentation and cleanup

### Physics

- Hydrostatic façade force: with water on both sides the net pressure is constant below the interior surface, so the force is ½ρgW(h_ext² − h_in²), not ½ρgW(h_ext − h_in)² (which under-estimated it whenever the interior was wet, e.g. by 9× for 0.5 m outside / 0.4 m inside). The interior water now acts from the floor (`--floor-datum`) and the exterior from external ground, so the moment uses each side's own lever arm. The force is negative when the interior water pushes outward.
- `forces.compute_hydrostatic_force(h_ext, h_in, width, floor_datum)` and `compute_drag_force(h_ext, v, width)` return (force, moment); `compute_combined_forces(h_ext, h_in, v, width, floor_datum=…)`. `forces.csv` columns `H_net_m`, `H_wet_m` replaced by `h_ext_m`, `h_in_m`.

### Documentation

- Elevations documented as they are used: measured from external ground (z = 0), with the ground floor at `--floor-datum` (`model.md`, `reference.md`, `fragility.md`; they described an interior-floor datum).
- `model.md` lateral-force section, `reference.md` forces columns and the `plots.md` forces example match `forces.py`; `fragility.md` documents the membrane's second state.
- Removed references to deleted specification documents from `pump.py`, `report.py`, `fragility.py` and the sump tests; `plot.py` and `SimConfig.time_units` descriptions corrected.
- `examples/report.md`: Case 01 timestep table and Case 08–09 replicate figures are computed when the report is generated; Case 03, 08 and 09 explanations match the results; no comparisons with earlier model versions. The Case 01 timestep figure describes convergence (all steps are stable) instead of an instability zone.
- CHANGELOG: the "planned" refactor section rewritten as the dated 2026-04-22 entry and put in order.

### Removed

- Unused code: `plot._despine`, `plot._format_m3s`, the dashboard's `_vline_event`, `Simulation.run(verbose)`, the `membranes` argument of `fragility.validate_fragility_inputs`, the `fragility.sample_thresholds` wrapper (use `FragilityDefinition.sample_thresholds`); `batch.py` uses `numpy.percentile` (same values).
- Outdated example images: `ingress_preview.png`, `ingress_locations.png`, `ingress_paths.png` (no longer produced) and the `simulation_animation.gif` files (made with earlier model versions; regenerate with `python3 examples/run_examples.py --animate`).
