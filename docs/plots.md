# plot.py — figure reference

All figures are produced by `plot.py`.  The module sets the `Agg` backend on
import and applies a shared visual style (grey grid, no top/right spines,
Helvetica/Arial fonts, 150 dpi output).

---

## 1  External hydrograph preview

**Function:** `save_external_preview(times, levels, outpath, time_unit=None)`

A single-panel time-series of the exterior water depth.  Shows the raw data
points and a smooth interpolated line.  Useful for a quick sanity-check of
the uploaded hydrograph before running a simulation.

```python
from engine import parse_external_file
import plot

times, levels = parse_external_file('hydrographs/depth/depth_042.csv',
                                    time_multiplier=60.0)  # minutes → seconds
plot.save_external_preview(times, levels, 'out/external_preview.png',
                          time_unit='minutes')
```

---

## 2  Velocity preview

**Function:** `save_velocity_preview(times, velocities, outpath, time_unit=None, max_safe_v=2.0)`

Time-series of the exterior flow velocity.  A dashed red line marks the
`max_safe_v` threshold (default 2.0 m/s) above which hydrostatic assumptions
break down.

```python
from engine import parse_velocity_file
import plot

vt, vv = parse_velocity_file('hydrographs/velocity/velocity_042.csv',
                              time_multiplier=60.0)
plot.save_velocity_preview(vt, vv, 'out/velocity_preview.png',
                          time_unit='minutes', max_safe_v=2.0)
```

---

## 3  Ingress pathway preview

**Function:** `save_ingress_preview(ingress_list, outpath)`

Horizontal bar chart showing each ingress pathway's effective orifice area
(m²) and sill height (m).  Colour encodes the sill height.  Useful for
reviewing the parsed pathway configuration before running.

```python
from engine import IngressPathway
import plot

paths = [
    IngressPathway(height=0.0, area=0.05,  coeff=0.6, name='door_gap'),
    IngressPathway(height=0.3, area=0.003, coeff=0.6, name='airbrick'),
]
plot.save_ingress_preview(paths, 'out/ingress_preview.png')
```

---

## 4  Ingress location diagram

**Function:** `save_ingress_locations(ingress_list, outpath, building_width=1.0)`

Schematic elevation of the building wall showing each pathway as a coloured
tick at its sill height.  Conveys the vertical distribution of entry points
at a glance.

```python
import plot

plot.save_ingress_locations(paths, 'out/ingress_locations.png',
                           building_width=1.0)
```

---

## 5  Simulation result

**Function:** `save_simulation_result(sim_times, sim_levels, external_levels, outpath, …)`

The primary single-run output figure.  Two or three panels depending on
whether a basement and/or sump are active:

- **Left:** interior (and basement / sump if present) depth time-series
  overlaid with the exterior hydrograph.
- **Right:** ingress flow-rate time-series (m³/s) per pathway.

Key parameters:

| Parameter | Default | Notes |
|---|---|---|
| `ingress_list` | `[]` | Pathway objects — used for the flow panel |
| `basement_levels` | `None` | Include a basement trace |
| `sump_levels` | `None` | Include a sump trace |
| `time_unit` | `'seconds'` | Axis label unit |
| `animate` | `False` | Also calls `generate_animation` |

```python
from engine import Building, IngressPathway, Simulation
import plot

b   = Building(floor_area=50.0)
ing = [IngressPathway(height=0.0, area=0.05, coeff=0.6, name='door_gap')]
t_ext = [0, 1800, 3600, 21600]
h_ext = [0.0, 0.5, 0.0, 0.0]

sim_t, sim_h = Simulation(b, ing, t_ext, h_ext, dt=60).run()
plot.save_simulation_result(sim_t, sim_h, h_ext, 'out/simulation_result.png',
                           ingress_list=ing, time_unit='seconds')
```

---

## 6  GIF animation

**Function:** `generate_animation(sim_times, sim_levels, external_levels, ingress_list, outpath, …)`

Frame-by-frame animated GIF of the interior and exterior water levels rising
and falling.  Each frame shows a schematic cross-section of the building with
the current water surface.  Slow to generate; disabled by default in
`run_examples.py`.

```python
plot.generate_animation(sim_t, sim_h, h_ext, ing,
                       'out/simulation_animation.gif',
                       time_unit='seconds', fps=12)
```

---

## 7  Forces result

**Function:** `save_forces_result(sim_times, forces_rows, outpath, time_unit=None)`

Two-panel figure: hydrostatic force (kN/m) and drag force (kN/m) versus time,
computed from the interior / exterior depth difference and flow velocity.
Generated when `--velocity` data is supplied to the CLI.

```python
from engine import compute_forces
import plot

forces = compute_forces(sim_t, sim_h, h_ext, velocities)
plot.save_forces_result(sim_t, forces, 'out/forces_result.png',
                       time_unit='seconds')
```

---

## 8  Interpretation dashboard

**Function:** `save_interpretation_dashboard(diag, outpath, time_unit='seconds', ingress_list=None)`

A multi-panel diagnostic dashboard combining:

- Interior / exterior depth time-series with annotated peak and duration
- Depth exceedance bars (minutes above 10 cm, 20 cm, …)
- Mass-balance bar chart (volume in vs volume out vs residual)
- Plain-English interpretation bullet points (generated by `report.py`)

`diag` is a `Diagnostics` dataclass returned by `report.diagnostics_from_trace`.

```python
from report import diagnostics_from_trace
import plot

diag = diagnostics_from_trace(sim_t, sim_h, h_ext, ing,
                               time_unit='seconds')
plot.save_interpretation_dashboard(diag, 'out/dashboard.png',
                                  time_unit='seconds', ingress_list=ing)
```

---

## 9  Batch scatter (simple)

**Function:** `save_batch_scatter(h_peak_ext, h_peak_int, outpath)`

Square scatter plot of peak exterior depth vs peak interior depth across all
cases in a batch run.  Uses hexbin density shading when `n > 60`.  A dashed
1:1 line shows the "no attenuation" reference.  Pearson *r* is annotated.
Produced automatically by `batch.py`.

```python
import plot

plot.save_batch_scatter([0.1, 0.2, 0.3, 0.5], [0.09, 0.19, 0.28, 0.45],
                       'out/batch_scatter.png')
```

---

## 10  Loss scatter

**Function:** `save_loss_scatter(h_peak_ext, aggregate_losses, outpath)`

Scatter plot of peak exterior depth vs aggregate flood loss (GBP).  Points
are coloured by depth using a `YlOrRd` gradient.  A running-median trend line
is overlaid when `n > 10`.  Produced by `batch.py` when a vulnerability curve
is supplied.

```python
import plot

plot.save_loss_scatter([0.1, 0.3, 0.5, 0.8], [2000, 8000, 18000, 35000],
                      'out/loss_scatter.png')
```

---

## 11  Batch deterministic (sweep)

**Function:** `save_batch_deterministic(h_ext, h_int, title, outpath)`

Two-panel figure for a deterministic batch run over many hydrographs:

- **Left:** scatter of peak exterior vs peak interior depth with a 1:1
  reference line.
- **Right:** attenuation ratio h\_in / h\_ext vs h\_ext.

Monotonic response and near-unity attenuation (for a large orifice) are
immediately visible.

```python
import plot

h_ext = [0.10, 0.15, 0.20, 0.25, 0.30, 0.50]
h_int = [0.11, 0.16, 0.21, 0.26, 0.31, 0.51]
plot.save_batch_deterministic(h_ext, h_int,
                             'Batch — single opening, 6 hydrographs',
                             'out/batch_result.png')
```

---

## 12  Batch fragility MC (fragility curve)

**Function:** `save_batch_mc_fragility(h_ext_all, h_int_all, title, outpath, membrane_median_m=None)`

Two-panel figure for a batch run with Monte Carlo replicates:

- **Left:** replicate scatter cloud with P10 / P50 / P90 bands.
- **Right:** fragility curve — fraction of replicates with significant ingress
  (h\_in > 5 % of max h\_in) as a function of peak exterior depth.

Pass `membrane_median_m` to draw a vertical reference line at the membrane
design capacity.

```python
import plot

# 20 hydrographs × 50 replicates = 1 000 rows
h_ext_all = [...]   # 1 000 values
h_int_all = [...]   # 1 000 values
plot.save_batch_mc_fragility(h_ext_all, h_int_all,
                            'Batch MC — membrane η = 0.5 m',
                            'out/batch_mc_result.png',
                            membrane_median_m=0.5)
```

---

## 13  Fragility MC result

**Function:** `save_mc_result(peak_h_in, peak_h_ext, state_freq_rows, title, outpath)`

Two-panel figure for a single-hydrograph Monte Carlo run:

- **Left:** scatter of peak interior vs exterior depth, colour-split into
  *intact* (near-zero) and *degraded* replicates, with an empirical CDF
  on the right y-axis.  P25 / P50 / P75 hairlines are drawn on the CDF.
- **Right:** grouped bar chart of element state frequencies (fraction of
  replicates in each state per fragility element or membrane).

`state_freq_rows` is a list of dicts with keys `element`, `state_0_freq`,
`state_1_freq`, … — the format written to `fragility_state_freq.csv` by
`cli.py`.

```python
from fragility import run_fragility_montecarlo, FragilePath, FragilityDefinition, FragilityState
from engine import Building
import plot

paths = [FragilePath(
    name='seal_door', height_m=0.0, area_m2=1e-7, Cd=0.6, group_id=0,
    fragility=FragilityDefinition(states=[
        FragilityState('failed', median_m=0.5, beta_ln=0.3,
                       area_m2=5e-3, Cd=0.6),
    ]),
)]
result = run_fragility_montecarlo(
    building_factory=lambda: Building(50.0),
    paths=paths, membranes=[], basement_fragility=None,
    external_times=[0, 1800, 3600, 21600],
    external_levels=[0.0, 0.5, 0.0, 0.0],
    n_replicates=500, dt=60, seed=42,
)

peak_h_in  = [r.peak_h_in  for r in result.replicates]
peak_h_ext = [r.peak_h_ext for r in result.replicates]

# state_freq_rows can be read from the CSV or built manually:
# [{'element': 'seal_door', 'state_0_freq': '0.50', 'state_1_freq': '0.50'}]
state_freq_rows = []  # omit for no bar chart

plot.save_mc_result(peak_h_in, peak_h_ext, state_freq_rows,
                   'Case 07 — single probabilistic seal (n = 500)',
                   'out/mc_result.png')
```

---

## 14  Building schematic (single panel)

**Function:** `draw_schematic(ax, cfg)`

Draws one building cross-section on an existing `matplotlib.axes.Axes`.
Used inside `save_all_schematics` and in the Streamlit app sidebar.

`cfg` is a dict with the following keys:

| Key | Type | Description |
|---|---|---|
| `label` | str | Title inside the panel (e.g. `'Case 01'`) |
| `subtitle` | str | Subtitle (may contain `\n`) |
| `floor_h` | float | Ground-floor ceiling height (m) |
| `bsmt_d` | float or None | Basement depth below ground (m) |
| `sump` | bool | Draw sump pit |
| `pump` | bool | Draw pump discharge arrow |
| `gf_paths` | list of dict | Ground-floor ingress paths |
| `bsmt_paths` | list of dict | Basement ingress paths |
| `membrane` | dict or None | Flood membrane configuration |

Each path dict: `{'sill': float, 'name': str, 'style': 'det'|'prob'|'behind'}`.

Membrane dict: `{'sill': float, 'capacity': float, 'style': 'prob'|'det'}`.

Nine ready-made configs are available in `plot.SCHEMATIC_CASES`.

```python
import matplotlib.pyplot as plt
import plot

fig, ax = plt.subplots(figsize=(3.5, 3.5))
plot.draw_schematic(ax, plot.SCHEMATIC_CASES[0])  # Case 01
fig.savefig('out/schematic_01.png', dpi=150, bbox_inches='tight')
plt.close(fig)
```

---

## 15  All schematics (3 × 3 grid)

**Function:** `save_all_schematics(outpath, cases=None)`

Draws all nine case-study building schematics in a 3 × 3 grid with a shared
legend.  `cases` defaults to `plot.SCHEMATIC_CASES` (Cases 01–09).

```python
import plot

plot.save_all_schematics('examples/schematics.png')
```

To draw a custom set of cases:

```python
import plot

my_cases = [
    dict(label='No protection', subtitle='sill = 0 m',
         floor_h=2.5, bsmt_d=None, sump=False, pump=False,
         gf_paths=[dict(sill=0.0, name='door gap', style='det')],
         bsmt_paths=[], membrane=None),
    dict(label='Membrane', subtitle='η = 0.4 m (det.)',
         floor_h=2.5, bsmt_d=None, sump=False, pump=False,
         gf_paths=[dict(sill=0.0, name='door gap', style='behind')],
         bsmt_paths=[],
         membrane=dict(sill=0.0, capacity=0.4, style='det')),
]
plot.save_all_schematics('out/my_schematics.png', cases=my_cases)
```

---

## Summary table

| # | Function | Panels | Inputs |
|---|---|---|---|
| 1 | `save_external_preview` | 1 | times, levels |
| 2 | `save_velocity_preview` | 1 | times, velocities |
| 3 | `save_ingress_preview` | 1 | ingress list |
| 4 | `save_ingress_locations` | 1 | ingress list |
| 5 | `save_simulation_result` | 2–3 | sim output + optional basement/sump |
| 6 | `generate_animation` | animated GIF | sim output |
| 7 | `save_forces_result` | 2 | forces rows |
| 8 | `save_interpretation_dashboard` | 5 | Diagnostics dataclass |
| 9 | `save_batch_scatter` | 1 | h_ext, h_int arrays |
| 10 | `save_loss_scatter` | 1 | h_ext, losses arrays |
| 11 | `save_batch_deterministic` | 2 | h_ext, h_int arrays |
| 12 | `save_batch_mc_fragility` | 2 | replicate arrays |
| 13 | `save_mc_result` | 2 | replicate arrays + state freq rows |
| 14 | `draw_schematic` | 1 (on existing axes) | cfg dict |
| 15 | `save_all_schematics` | 3 × 3 grid | list of cfg dicts |
