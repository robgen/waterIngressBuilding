# To be implemented

## 1. Combined depth + velocity input format

Apply NOTE_combined_input_format.md across main.py, streamlit_app.py, and
water time series/generate.py.  Then remove that note file.

## 2. Batch run in Streamlit + per-case time series

`batch_run.py` saves only summary CSVs; the Streamlit app cannot yet run the
batch or inspect individual case time series.

**Decisions made (see docs/NOTE_montecarlo.md for full spec):**
- Option 2: `run_batch` writes `outdir/time_series/case_NNN.csv` (time, h_ext, h_int)
- App uses `st.tabs(['Single run', 'Batch run'])`; shared sidebar for building config
- In-app batch run: time series cached in `st.session_state` (no disk I/O during session)
- Uploaded pre-computed results: scatter plot shown; case selector enabled only if
  time series CSVs are also uploaded
- Download: `batch_results.csv`, `batch_summary.csv`, ZIP of time series

**Code changes needed:**
- `batch_run.py`: add `save_time_series=True` flag and `time_series/` writer
- `streamlit_app.py`: tabs, multi-file upload, "Run batch" button, case selector,
  time series plot, download buttons

## 3. True Monte Carlo simulation

MC is an extension of the batch loop — same function, but samples ingress/building
parameters from probability distributions for each hydrograph file.

**Decisions made (see docs/NOTE_montecarlo.md for full spec):**
- New `montecarlo.py` wraps `batch_run` with a `_sample_ingress(specs, rng)` step
- Parameters randomised per run: Cd (Uniform), area (Normal), sill height (Normal)
- Hydrograph parameters fixed per file (already randomised in generate.py)
- `IngressSpec` + `FragilityFunction` dataclasses added to `main.py`
- Input spec: JSON file (`ingress_specs.json`) replacing the plain ingress text file
- Output identical to batch run; adds `mc_ingress_samples.csv` for sensitivity analysis
- App: "Randomise ingress parameters" checkbox in the batch tab triggers MC mode

## 4. Fragility functions on ingress pathways

Each ingress point can have a fragility function: P(state | h_peak_ext), where
each state maps to a (area, Cd) pair.  One-to-many mapping: one fragility
function (e.g. flood skirt) can govern multiple ingress points.

Covered in `FragilityFunction` class spec in docs/NOTE_montecarlo.md.

## 5. Check if parametric_run and batch_run overlap

Check if one between parametric_run and batch_run can be removed or merged.
