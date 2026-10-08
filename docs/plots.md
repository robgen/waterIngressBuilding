# plot.py — figure reference

All figures are produced by `plot.py`.  The module sets the `Agg` backend on
import and applies a shared visual style (grey grid, no top/right spines,
Helvetica/Arial fonts, 150 dpi output).

Single-run figures come in two layers: `save_run_*` functions take the model
objects (`SimConfig`, `Hydrograph`, `SimResult`, pathways) and derive every
argument from them; the lower-level functions they call take plain series.
`cli.py`, `batch.py` and `app.py` use the `save_run_*` layer.

The examples below share this setup (Case 01 of the validation set):

```python
import numpy as np

import engine
import fragility
import plot

config = engine.SimConfig(floor_area=50.0, dt=60.0, time_units='minutes',
                          velocity_mode='power_law')
hydro  = engine.hydrograph_from_columns([0, 30, 60, 120], [0.0, 0.5, 0.0, 0.0],
                                        time_units='minutes')
paths, membranes = fragility.assemble_pathways(
    [fragility.FragilePath('door_gap', height_m=0.0, area_m2=0.05, Cd=0.6)])
result, _ = fragility.run_replicate(config, hydro, paths, membranes,
                                    np.random.default_rng())
```

---

## 1  External hydrograph preview

**Function:** `save_external_preview(times, levels, outpath, time_unit=None)`

Single-panel time series of the exterior water depth with the peak marked.

```python
plot.save_external_preview([t / 60 for t in hydro.times], hydro.levels,
                           'out/external_preview.png', time_unit='minutes')
```

---

## 2  Velocity preview

**Function:** `save_velocity_preview(times, velocities, outpath, time_unit=None, orig_point_times=None, orig_point_vals=None)`

Time series of the exterior flow velocity; `orig_point_*` overlays the raw
input points when the series was interpolated.

```python
h_ext, v_ext = engine.exterior_series(config, hydro, result.times)
plot.save_velocity_preview([t / 60 for t in result.times], v_ext,
                           'out/velocity_preview.png', time_unit='minutes')
```

---

## 3  Run schematic

**Function:** `save_run_schematic(outpath, *, pathways=(), membranes=(), config=None, floor_h=2.5, label='', subtitle='')`

Building cross-section with a zoomed pathway table.  `pathways` are
`FragilePath`s, split by `target` into ground-floor and basement openings;
basement depth, sump and bypass sill are read from `config`.

```python
plot.save_run_schematic('out/schematic.png', pathways=paths,
                        membranes=membranes, config=config, label='Case 01')
```

---

## 4  Simulation result

**Functions:**
`save_run_result(outpath, config, hydro, result)` and the series-level
`save_simulation_result(sim_times, sim_levels, external_levels, outpath, time_unit=None, basement_levels=None, sump_levels=None, basement_max_depth=None, sump_overflow_level=None)`

Water depth in each active compartment against the exterior hydrograph.  A
second panel shows basement (and sump) depth when present, with the ceiling
and sump overflow crest as reference lines.

```python
plot.save_run_result('out/simulation_result.png', config, hydro, result)
```

---

## 5  GIF animation

**Functions:**
`save_run_animation(outpath, config, hydro, result, pathways)` and the
series-level `generate_animation(sim_times, sim_levels, external_levels, pathways, outpath, fps=10, max_frames=200, time_unit=None, basement_levels=None, velocity_series=None, sump_levels=None, sump_overflow_level=None, Q_ext_series=None, Q_perim_series=None, Q_bypass_series=None, bypass_height=None)`

Frame-by-frame cross-section of the building with the rising and falling
water surfaces and a level chart.  Flow arrows come from the engine trace
(`Q_ext_b`, `Q_ext_perimeter`, `Q_b_bs`).  Slow to generate; disabled by
default in `run_examples.py`.

```python
plot.save_run_animation('out/simulation_animation.gif', config, hydro, result, paths)
```

---

## 6  Forces result

**Function:** `save_forces_result(sim_times, forces_rows, outpath, time_unit=None)`

Two panels: lateral forces (hydrostatic, drag, total, in N) and overturning
moment (N·m) against time.  `forces_rows` are the rows written to
`forces.csv` by `cli.py --compute-forces`:
`(time, F_hydro, F_drag, F_total, M_overturn, H_net, H_wet, v, lever_hydro, lever_drag)`.

```python
import forces

h_ext, v_ext = engine.exterior_series(config, hydro, result.times)
rows = []
for t, he, hi, v in zip(result.times, h_ext, result.h_in, v_ext):
    H_net, H_wet = max(0.0, he - hi), max(0.0, he)
    f = forces.compute_combined_forces(H_net, H_wet, v, building_width=10.0)
    rows.append((t, f['F_hydro'], f['F_drag'], f['F_total'], f['M_overturn'],
                 H_net, H_wet, v, f['lever_hydro'], f['lever_drag']))
plot.save_forces_result([t / 60 for t in result.times], rows,
                        'out/forces_result.png', time_unit='minutes')
```

---

## 7  Interpretation dashboard

**Function:** `save_interpretation_dashboard(diag, outpath, time_unit='seconds', title_suffix='')`

Stacked panels: depths, instantaneous pathway flows, cumulative pathway
volumes, sump control behaviour (only with a sump), and an event mass-balance
bar chart with the plain-language bullets from `report.generate_narrative`.
`diag` is the dict returned by `report.diagnostics_from_trace`.

```python
from report import diagnostics_from_trace

diag = diagnostics_from_trace(result.trace, config.dt)
plot.save_interpretation_dashboard(diag, 'out/dashboard.png', time_unit='seconds')
```

---

## 8  Batch scatters

All take one value per case (or replicate) and an optional `v_peak` sequence
used for point colour (falls back to peak exterior depth).  Produced by
`batch.py`.

| Function | Axes |
|---|---|
| `save_batch_scatter(h_peak_ext, h_peak_int, outpath, *, v_peak=None)` | peak exterior vs peak ground-floor depth, 1:1 line |
| `save_basement_scatter(h_peak_ext, h_peak_basement, outpath, *, v_peak=None)` | peak exterior vs peak basement depth |
| `save_ground_loss_scatter(h_peak_int, building_losses, outpath, *, v_peak=None)` | peak ground-floor depth vs ground-floor contents loss |
| `save_basement_loss_scatter(h_peak_basement, basement_losses, outpath, *, v_peak=None)` | peak basement depth vs basement contents loss |
| `save_loss_scatter(h_peak_ext, aggregate_losses, outpath, *, v_peak=None)` | peak exterior depth vs aggregate contents loss |

```python
plot.save_batch_scatter([0.1, 0.2, 0.3, 0.5], [0.09, 0.19, 0.28, 0.45],
                        'out/batch_scatter.png')
plot.save_loss_scatter([0.1, 0.3, 0.5, 0.8], [2000, 8000, 18000, 35000],
                       'out/loss_scatter.png')
```

---

## 9  Batch deterministic (sweep)

**Function:** `save_batch_deterministic(h_ext, h_int, title, outpath, *, v_peak=None)`

Two panels for a one-replicate batch over many hydrographs: peak exterior vs
peak interior depth with a 1:1 line, and the attenuation ratio
h\_in / h\_ext vs h\_ext.

```python
plot.save_batch_deterministic([0.10, 0.20, 0.30, 0.50], [0.11, 0.21, 0.31, 0.51],
                              'Batch — single opening', 'out/batch_result.png')
```

---

## 10  Batch fragility MC (fragility curve)

**Function:** `save_batch_mc_fragility(h_ext_all, h_int_all, title, outpath, membrane_median_m=None)`

Two panels for a batch with Monte Carlo replicates: the replicate cloud with
P10 / P50 / P90 bands, and the fragility curve — fraction of replicates with
significant ingress against peak exterior depth.  `membrane_median_m` draws a
reference line at the membrane design capacity.

```python
config_mc = engine.SimConfig(floor_area=50.0, dt=60.0, n_replicates=50, random_seed=42)
mc_paths, mc_membranes = fragility.assemble_pathways(
    [fragility.FragilePath('airbrick', 0.1, 6e-3, 0.6, group_id=1),
     fragility.FragilePath('door_gap', 0.0, 2e-3, 0.6, group_id=1)],
    [],
    [fragility.FragilePath('membrane', 0.0, 1e-6, 0.6, group_id=1, reversible=True,
                           fragility=fragility.FragilityDefinition([
                               fragility.FragilityState('overtopped', 0.5, 0.1, 1e-9, 0.6)]))])
h_ext_all, h_int_all = [], []
for peak in (0.3, 0.5, 0.7):
    hyd = engine.hydrograph_from_columns([0, 30, 60, 120], [0.0, peak, 0.0, 0.0],
                                         time_units='minutes')
    for rec in fragility.run(config_mc, hyd, mc_paths, mc_membranes).replicates:
        h_ext_all.append(rec.result.peak_h_ext)
        h_int_all.append(rec.result.peak_h_in)
plot.save_batch_mc_fragility(h_ext_all, h_int_all, 'Batch MC — membrane η = 0.5 m',
                             'out/batch_mc_result.png', membrane_median_m=0.5)
```

---

## 11  Fragility MC result

**Function:** `save_mc_result(peak_h_in, peak_h_ext, state_freq_rows, title, outpath)`

- **Left:** scatter of peak interior depth per replicate, separating
  *intact* (near-zero) and *degraded* replicates, with an empirical CDF on
  the right y-axis and P25 / P50 / P75 hairlines.
- **Right:** grouped bar chart of element state frequencies.

`state_freq_rows` are the rows of `fragility_state_freq.csv` (dicts with
`element`, `state_0_freq`, `state_1_freq`, …); pass `[]` to omit the bars.
Used by `examples/run_examples.py`.

```python
mc = fragility.run(config_mc, hydro, mc_paths, mc_membranes)
plot.save_mc_result([r.result.peak_h_in for r in mc.replicates],
                    [r.result.peak_h_ext for r in mc.replicates],
                    [], 'Membrane group (n = 50)', 'out/mc_result.png')
```

---

## 12  Building schematic (single panel)

**Function:** `draw_schematic(ax, cfg)`

Draws one building cross-section on an existing `matplotlib.axes.Axes`.
Used by `save_all_schematics` and `save_run_schematic`.

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
| `bypass_height` | float, optional | Ground-floor slab / bypass sill elevation (m) |

Each path dict: `{'sill': float, 'name': str, 'style': 'det'|'prob'|'behind'}`.
Membrane dict: `{'sill': float, 'capacity': float, 'style': 'prob'|'det'}`.

Ready-made configs for the single-hydrograph validation cases (01–10) are in
`plot.SCHEMATIC_CASES`.

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(3.5, 3.5))
plot.draw_schematic(ax, plot.SCHEMATIC_CASES[0])  # Case 01
fig.savefig('out/schematic_01.png', dpi=150, bbox_inches='tight')
plt.close(fig)
```

---

## 13  All schematics (grid)

**Function:** `save_all_schematics(outpath, cases=None)`

Draws case schematics in rows of four, one row per run of consecutive cases
with the same building type (ground floor only / with basement), with a
shared legend.  `cases` defaults to `plot.SCHEMATIC_CASES`.

```python
plot.save_all_schematics('out/schematics.png')

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

| # | Function | Output | Inputs |
|---|---|---|---|
| 1 | `save_external_preview` | 1 panel | times, levels |
| 2 | `save_velocity_preview` | 1 panel | times, velocities |
| 3 | `save_run_schematic` | cross-section + pathway table | pathways, membranes, config |
| 4 | `save_run_result` / `save_simulation_result` | 1–2 panels | run objects / series |
| 5 | `save_run_animation` / `generate_animation` | animated GIF | run objects / series + trace flows |
| 6 | `save_forces_result` | 2 panels | forces rows |
| 7 | `save_interpretation_dashboard` | 4–5 panels | diagnostics dict |
| 8 | `save_*_scatter` | 1 panel | per-case arrays |
| 9 | `save_batch_deterministic` | 2 panels | per-case arrays |
| 10 | `save_batch_mc_fragility` | 2 panels | per-replicate arrays |
| 11 | `save_mc_result` | 2 panels | per-replicate arrays + state freq rows |
| 12 | `draw_schematic` | 1 panel on existing axes | cfg dict |
| 13 | `save_all_schematics` | grid | list of cfg dicts |
