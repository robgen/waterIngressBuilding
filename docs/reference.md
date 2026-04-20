# Input and output reference

---

## Inputs

### Unified pathway CSV format

All pathway inputs — ground-floor ingress, basement perimeter opening, and membranes — share an identical CSV format. One parser handles all three; routing is determined by which CLI flag the file is passed to.

**Format rules**

- First non-comment row is a **header** with comma-separated column names.
- Lines starting with `#` are comments and are ignored.
- Blank lines are ignored.
- Columns `name`, `height_m`, `area_m2`, `Cd` are required.
- `group_id` is optional (defaults to `0` = ungrouped, no membrane protection).
- Fragility state columns are optional and repeat in blocks of five per state: `state_name_N`, `median_m_N`, `beta_ln_N`, `area_m2_N`, `Cd_N`.
- Medians must be strictly increasing within a pathway.
- A pathway with `group_id > 0` must not carry its own fragility state columns.

**Column reference**

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `name` | string | yes | Unique identifier |
| `height_m` | float | yes | Sill elevation relative to the interior ground-floor datum (m) |
| `area_m2` | float | yes | Orifice area in the base (unloaded) state (m²) |
| `Cd` | float | yes | Discharge coefficient in the base state |
| `group_id` | int | no | Membrane group ID; `0` = ungrouped |
| `state_name_N` | string | no | Label for fragility state N |
| `median_m_N` | float | no | Lognormal median capacity for state N (m above sill) |
| `beta_ln_N` | float | no | Log-standard deviation for state N |
| `area_m2_N` | float | no | Orifice area when state N is active (m²) |
| `Cd_N` | float | no | Discharge coefficient when state N is active |

**Deterministic pathway**

```csv
name,       height_m, area_m2, Cd
door_gap,   0.0,      0.05,    0.6
airbrick,   0.1,      0.006,   0.6
wall_crack, 0.0,      0.001,   0.6
```

**Pathway with one fragility state**

The base-state area represents the sealed or best-performance conductance. State 1 is the degraded conductance, activated when the sampled capacity threshold is exceeded.

```csv
name,       height_m, area_m2, Cd,  group_id, state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1
seal_door,  0.0,      1.0e-7,  0.6, 0,        failed,       0.5,        0.3,       5.0e-3,    0.6
wall_crack, 0.0,      0.001,   0.6
```

**Membrane-protected group**

Pathways with `group_id > 0` are shielded by a membrane; their conductances are suppressed while the membrane is intact.

```csv
name,     height_m, area_m2, Cd,  group_id
airbrick, 0.1,      6.0e-3,  0.6, 1
door_gap, 0.0,      2.0e-3,  0.6, 1
```

---

### External hydrograph (`--external`)

Two-column CSV: `time` and `level`. Times in simulation time units (default: minutes). Levels in metres above the reference datum. Linearly interpolated to the simulation grid.

```csv
0,   0.00
15,  0.25
30,  0.50
60,  0.00
360, 0.00
```

---

### External velocity hydrograph (`--external-velocity`)

Optional two-column CSV: `time` and `velocity` (m/s). Same time units as the level hydrograph. If omitted, a conservative constant default velocity is used (`--external-velocity-default`, default 0.2 m/s).

```csv
0,   0.0
15,  0.3
30,  0.5
60,  0.0
```

---

### Ground-floor ingress file (`--ingress`)

Rows represent exterior-to-ground-floor pathways. Uses the unified pathway format. May include membrane-grouped rows and fragility states.

---

### Basement perimeter opening (`--basement-opening`)

Represents the lumped exterior-to-basement perimeter opening. Uses the **same** unified pathway format. Typically a single-row file. May include fragility states.

Deterministic example:

```csv
name,         height_m, area_m2, Cd
ext_basement, 0.0,      0.005,   0.5
```

With fragility:

```csv
name,         height_m, area_m2, Cd,  group_id, state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1
ext_basement, 0.0,      1.0e-7,  0.5, 0,        cracked,      0.30,       0.25,      0.005,     0.5
```

---

### Membrane file (`--membrane`)

Uses the **same** unified pathway format. Each row defines one membrane. `group_id` links the membrane to the pathways it protects. Base-state `area_m2` / `Cd` is the membrane's own leakage conductance (typically very small). State columns define the overtopping fragility.

`height_m` is the membrane sill elevation. `median_m_1` is the seal height above that sill (the physical top of the membrane).

```csv
name,           height_m, area_m2, Cd,  group_id, state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1
front_membrane, 0.0,      1.0e-6,  0.6, 1,        overtopped,   0.5,        0.1,       1.0e-9,    0.6
```

---

### CLI flags

**Building geometry**

| Flag | Default | Description |
|------|---------|-------------|
| `--floor FLOAT` | required | Ground-floor plan area (m²) |
| `--dt FLOAT` | 1 | Simulation timestep in `time_units` |
| `--time-units STR` | `minutes` | `seconds`, `minutes`, or `hours` |
| `--outdir PATH` | required | Output directory |
| `--animate` | off | Write a GIF animation |

**Basement**

| Flag | Description |
|------|-------------|
| `--basement-area FLOAT` | Basement plan area (m²) |
| `--basement-floor-elevation FLOAT` | Basement floor elevation relative to datum (m, negative = below datum) |
| `--basement-ceiling-elevation FLOAT` | Optional ceiling elevation cap (m); water above this spills to ground floor |
| `--basement-connection-height FLOAT` | Sill of the ground-floor ↔ basement bypass connection (m) |
| `--basement-connection-area FLOAT` | Area of the ground-floor ↔ basement bypass (m²) |

**Sump and pump** (`--sumppump-*`, always used together)

| Flag | Default | Description |
|------|---------|-------------|
| `--sumppump-area FLOAT` | — | Sump plan area (m²); enables the module when > 0 |
| `--sumppump-base-elevation FLOAT` | — | Sump base / pump datum elevation (m) |
| `--sumppump-overflow-level FLOAT` | — | Overflow crest height above sump base (m) |
| `--sumppump-overflow-coeff FLOAT` | — | Overflow coefficient $C_{ov}$ |
| `--sumppump-overflow-exponent FLOAT` | 1.5 | Overflow exponent $m_{ov}$ |
| `--sumppump-on-level FLOAT` | — | Sump depth above base at which pump switches on (m) |
| `--sumppump-off-level FLOAT` | — | Sump depth above base at which pump switches off (m) |
| `--sumppump-shutoff-head FLOAT` | — | Pump shut-off head $H_{shut}$ (m) |
| `--sumppump-curve-coeff FLOAT` | — | Pump-curve coefficient $k_{pump}$ |
| `--sumppump-pipe-loss-coeff FLOAT` | 0 | Pipe-loss coefficient $k_{pipe}$ |
| `--sumppump-availability FLOAT` | 1.0 | Availability factor $\eta_p$ |

**Monte Carlo**

| Flag | Default | Description |
|------|---------|-------------|
| `--n-replicates INT` | 1 | Number of Monte Carlo replicates; > 1 triggers fragility mode |
| `--random-seed INT` | — | Optional seed for reproducibility |

**Forces**

| Flag | Default | Description |
|------|---------|-------------|
| `--compute-forces` | off | Enable lateral force time series |
| `--building-width FLOAT` | — | Flow-facing façade width (m) |
| `--drag-coeff FLOAT` | 1.0 | Drag coefficient $C_D$ |
| `--rho FLOAT` | 1000 | Fluid density (kg/m³) |

**Batch only**

| Flag | Description |
|------|-------------|
| `--depth-dir PATH` | Folder of depth CSV files (one per hydrograph) |
| `--velocity-dir PATH` | Optional matching folder of velocity CSV files |
| `--contents-vulnerability PATH` | CSV with `height_m` and a loss column |
| `--contents-loss-column NAME` | Loss column name (default `mean_repair_loss_GBP`) |

---

### Units and conventions

- **Time**: minutes by default; override with `--time-units`.
- **Length / depth**: metres (m).
- **Area**: m².
- **Velocity**: m/s.
- **Elevations**: metres relative to the interior ground-floor datum. Use negative values for below-datum elevations (e.g. basement floor at −2.5 m).
- **Discharge coefficient**: dimensionless.

---

## Outputs

All outputs are written to `--outdir`. The files produced depend on the run mode.

### Single-run outputs (all non-batch modes)

| File | Description |
|------|-------------|
| `simulation_result.png` | Time series of water depth in each active compartment |
| `simulation_animation.gif` | Animated cross-section schematic (only with `--animate`) |
| `external_preview.png` | External hydrograph (and velocity, if provided) |
| `ingress_preview.png` | Pathway sill heights and areas |
| `ingress_locations.png` | Pathway positions on the building envelope |

### Fragility (Monte Carlo) outputs

| File | Description |
|------|-------------|
| `fragility_replicates.csv` | One row per replicate: $u$ values, capacity thresholds, peak depths, total volume |
| `fragility_summary.csv` | Percentile statistics (P10, P25, P50, P75, P90) for peak depths and volume |
| `fragility_state_freq.csv` | Fraction of replicates reaching each degraded state per pathway |
| `mc_result.png` | Scatter and CDF plots of peak interior and basement depth |

**`fragility_replicates.csv` columns**

| Column | Description |
|--------|-------------|
| `replicate` | Replicate index (0-based) |
| `u_<name>` | Uniform draw for pathway `<name>` |
| `threshold_<name>_k` | Sampled capacity threshold for state k of pathway `<name>` (m above sill) |
| `peak_h_in` | Peak interior ground-floor depth (m) |
| `peak_h_basement` | Peak basement depth (m), if basement configured |
| `total_volume_in` | Total ingress volume to ground floor (m³) |

### Batch outputs

| File | Description |
|------|-------------|
| `batch_results.csv` | One row per hydrograph: peak depths, durations, loss estimate |
| `batch_summary.csv` | Percentile statistics (P10, P50, P90) across the ensemble |
| `peak_exterior_vs_interior.png` | Scatter: peak external vs peak interior depth |
| `peak_exterior_vs_aggregate_loss.png` | Scatter: peak external depth vs loss (only with `--contents-vulnerability`) |

**`batch_results.csv` columns**

| Column | Description |
|--------|-------------|
| `case` | Hydrograph file name (without extension) |
| `peak_h_ext` | Peak external depth (m) |
| `peak_h_in` | Peak interior ground-floor depth (m) |
| `peak_h_basement` | Peak basement depth (m), if basement configured |
| `dur_h<XXX>cm_<tu>` | Duration above threshold XXX cm, in time units |
| `aggregate_loss_GBP` | Interpolated loss from vulnerability curve, if provided |

With `--n-replicates > 1`, depth columns become percentile sets (e.g. `peak_h_in_p50`).

### Force outputs (only with `--compute-forces`)

| File | Description |
|------|-------------|
| `forces.csv` | Time series of $F_{hydro}$, $F_{drag}$, $F_{total}$, $M_{overturn}$ |
| `forces_result.png` | Time series plot of total lateral force and overturning moment |

**`forces.csv` columns**: `time`, `h_ext`, `F_hydro_kN`, `F_drag_kN`, `F_total_kN`, `M_overturn_kNm`.
