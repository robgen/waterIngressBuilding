# Note: Batch Run + Monte Carlo — Architecture Decisions

**Status:** planned / not yet implemented
**Scope:** `batch_run.py`, new `montecarlo.py`, `main.py`, `streamlit_app.py`

---

## Agreed architecture

### One batch function, MC as an extension

There is a single core batch loop.  The Monte Carlo is not a separate concept —
it is the same loop with an extra parameter-sampling step before each simulation.

```
for each hydrograph file:
    [MC only] sample ingress pathway realisations from their uncertainty distributions
    run simulation with (hydrograph, ingress_realisations, building)
    store (sim_times, sim_levels, h_peak_ext, h_peak_int, durations)
```

The batch runs however many files are in the input folder — no fixed N.
The MC runs the same loop, randomising ingress/building parameters per file.

### Time series output — Option 2 (persistent per-case CSVs)

The batch runner saves a per-case time series alongside the summary:

```
outdir/
  batch_results.csv        — one row per case (peaks + durations)
  batch_summary.csv        — percentile statistics
  time_series/
    case_001.csv           — columns: time_<tu>, h_ext, h_int
    case_002.csv
    …
```

This makes the output self-contained: the Streamlit app can load any case
time series without re-running the simulation, and CLI-generated results
remain inspectable in a later app session.

Column format for `time_series/case_NNN.csv`:

```
# time (min), h_ext (m), h_int (m)
0.0, 0.00, 0.00
1.0, 0.12, 0.00
…
```

The time column is in the display units selected at run time (matching `batch_results.csv`).

---

## Streamlit app

### Tab structure

```
st.tabs(['Single run', 'Batch run'])
```

Shared sidebar: ingress pathways, floor area, time units, dt, thresholds.

**Single run tab** — current UI unchanged.

**Batch run tab:**
1. Upload depth CSVs (`accept_multiple_files=True`) + optional velocity CSVs.
2. "Run batch" button → calls `run_batch()`, stores results in `st.session_state`.
3. Scatter plot: h_peak_ext vs h_peak_int (all cases).
4. Case selector (`st.selectbox` over case IDs) → loads `time_series/case_NNN.csv`
   from session state (in-app run) and plots full h_ext + h_int time series.
5. Download buttons: `batch_results.csv`, `batch_summary.csv`, ZIP of time series.

When the user uploads a pre-computed `batch_results.csv` (from a CLI run),
the scatter plot is shown but the case selector is disabled with an info message
("Upload the time_series/ folder to inspect individual cases").  If the user
also uploads time series CSVs, the selector is enabled.

---

## Required code changes

### `batch_run.py`

- `_run_case` already returns `(sim_times, sim_levels, h_peak_ext, h_peak_int)`.
- `run_batch`: add `save_time_series=True` flag.  When True, write
  `outdir/time_series/case_NNN.csv` for each case using the display-unit times.
- Return value: keep as `list[dict]` (summary rows); time series are written
  to disk only.  In-app use stores `sim_times`/`sim_levels` in session state
  directly (avoids disk I/O during app session).

### New `montecarlo.py`

Thin wrapper around `batch_run.run_batch` that adds a sampling step:

```python
def run_montecarlo(depth_dir, ingress_specs, floor_area, time_units, dt,
                   thresholds, default_velocity, outdir, seed=None):
    rng = random.Random(seed)
    pairs = _discover_pairs(depth_dir, velocity_dir=None)
    for case_id, depth_path, vel_path in pairs:
        ingress_list = _sample_ingress(ingress_specs, rng)
        # then run exactly as batch_run._run_case
```

`_sample_ingress(specs, rng)` draws one `IngressPathway` realisation per spec:
- `Cd` ~ Uniform(coeff_lo, coeff_hi)
- `A`  ~ Normal(area_nominal, area_nominal * area_cv), clipped > 0
- `h_sill` ~ Normal(height_nominal, height_sigma)
- If a fragility function is attached: draw state first, override (A, Cd)

Output schema identical to batch run (`mc_results.csv`, `mc_summary.csv`,
`time_series/`).  Additional file: `mc_ingress_samples.csv` (one row per
run per pathway) for sensitivity analysis.

### `IngressSpec` and `FragilityFunction` — `main.py`

```python
@dataclass
class IngressSpec:
    height_nominal: float
    height_sigma:   float = 0.02     # m, 1-sigma installation tolerance
    area_nominal:   float = 0.0      # m²
    area_cv:        float = 0.15     # coefficient of variation
    coeff_lo:       float = 0.4      # Cd uniform lower bound
    coeff_hi:       float = 0.8      # Cd uniform upper bound
    name:           str   = ''
    fragility:      object = None    # FragilityFunction | None

@dataclass
class FragilityFunction:
    states:  list   # e.g. ['open', 'blocked']
    areas:   list   # m² per state
    coeffs:  list   # Cd per state
    medians: list   # h_peak_ext at P=0.5 for each state (log-normal CDF)
    betas:   list   # log-normal dispersion per state

    def sample(self, h_peak_ext, rng):
        """Return (area, coeff) drawn from state probabilities at h_peak_ext."""
```

`IngressPathway` and `parse_ingress_file` remain unchanged.
Add `parse_ingress_spec_file(filepath)` → `list[IngressSpec]` (reads JSON).

### `streamlit_app.py`

- Wrap existing content in `tab_single, tab_batch = st.tabs([...])`.
- Batch tab: multi-file uploader, "Run batch" button, scatter plot, case selector,
  time series plot, download buttons.
- MC mode: add a checkbox "Randomise ingress parameters" in the batch tab.
  When checked, show per-pathway uncertainty inputs (Cd range, area CV) and
  call `run_montecarlo` instead of `run_batch`.

---

## Parameters to randomise (MC mode)

| Parameter | Distribution | Source |
|---|---|---|
| `Cd` per pathway | Uniform(0.4, 0.8) | orifice literature range |
| Area per pathway | Normal(μ, μ·CV), CV≈0.15 | manufacturing tolerance |
| Sill height per pathway | Normal(μ, 0.02 m) | installation tolerance |
| Floor area | Fixed (single building study) | — |

Hydrograph parameters are fixed per file (randomisation already done in
`water time series/generate.py`).  If inline hydrograph synthesis is added
later, parameters can be sampled inside `_sample_hydrograph`.

---

## References

- Merz B et al. (2010) Nat. Hazards Earth Syst. Sci. 10:1–9.
- Kreibich H et al. (2009) NHESS 9:1679–1692.
- Saltelli A et al. (2008) *Global Sensitivity Analysis: The Primer.* Wiley.
