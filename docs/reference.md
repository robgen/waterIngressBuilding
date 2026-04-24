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

Two- **or** three-column CSV. Times in simulation time units (default: minutes). Levels in metres above the reference datum. Linearly interpolated to the simulation grid.

| Columns | Description |
|---------|-------------|
| `time, level` | 2-column format — velocity modes `zero` and `power_law` only |
| `time, level, velocity` | 3-column format — all velocity modes available, including `file` |

**2-column example**

```csv
0,   0.00
15,  0.25
30,  0.50
60,  0.00
360, 0.00
```

**3-column example** (inline velocity)

```csv
0,   0.00, 0.00
15,  0.25, 0.47
30,  0.50, 0.61
60,  0.00, 0.00
360, 0.00, 0.00
```

---

### Velocity mode (`--velocity-mode`)

Three options control how external flood velocity $v_{ext}(t)$ is computed:

| Mode | Requires | Description |
|------|----------|-------------|
| `zero` | 2- or 3-column depth CSV | $v_{ext} = 0$ at all times. No hydrodynamic contribution to ingress or forces. **Default.** |
| `power_law` | 2- or 3-column depth CSV | $v_{ext}(t) = a \cdot h_{ext}(t)^{b}$, derived from the depth hydrograph. Coefficients set with `--velocity-power-law-a` (default 1.5) and `--velocity-power-law-b` (default 0.5). |
| `file` | **3-column depth CSV only** | Velocity time series read from the third column of the depth CSV (`--external`). Raises an error if the file has only 2 columns. |

---

### Ground-floor ingress file (`--ingress`)

Rows represent exterior-to-ground-floor pathways. Uses the unified pathway format. May include membrane-grouped rows and fragility states.

---

### Basement perimeter opening (`--basement-ingress`)

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

**Velocity**

| Flag | Default | Description |
|------|---------|-------------|
| `--velocity-mode STR` | `zero` | `zero`, `power_law`, or `file` |
| `--velocity-power-law-a FLOAT` | 1.5 | Coefficient $a$ in $v = a \cdot h^b$ |
| `--velocity-power-law-b FLOAT` | 0.5 | Exponent $b$ in $v = a \cdot h^b$ |

> **Note:** `--velocity-mode=file` reads velocity from the **3rd column** of `--external`. No separate velocity file is accepted.

**Building geometry**

| Flag | Default | Description |
|------|---------|-------------|
| `--floor FLOAT` | required | Ground-floor plan area (m²) |
| `--dt FLOAT` | 1 | Simulation timestep in `--time-units` |
| `--time-units STR` | `minutes` | `seconds`, `minutes`, or `hours` |
| `--outdir PATH` | `.` | Output directory |
| `--temp-output` | off | Write to a temp directory, removed on exit |
| `--animate` | off | Write a GIF animation (slow) |
| `--verbose` | off | Print progress to stdout |

**Basement**

| Flag | Description |
|------|-------------|
| `--basement-area FLOAT` | Basement plan area (m²) |
| `--basement-floor-elevation FLOAT` | Basement floor elevation relative to datum (m, negative = below datum) |
| `--basement-ceiling-elevation FLOAT` | Optional ceiling elevation cap (m); water above this spills to ground floor |
| `--basement-bypass-height FLOAT` | Sill of the ground-floor ↔ basement bypass connection (m) |
| `--basement-bypass-area FLOAT` | Area of the ground-floor ↔ basement bypass (m²) |

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
| `--depth-dir PATH` | Folder of depth CSV files (one per hydrograph); files may be 2- or 3-column |
| `--building-vulnerability PATH` | CSV mapping ground-floor peak depth to building contents loss |
| `--basement-vulnerability PATH` | CSV mapping basement peak depth to basement contents loss |
| `--contents-loss-column NAME` | Loss column to read from vulnerability CSVs (default `mean_repair_loss_GBP`) |
| `--thresholds FLOAT ...` | Interior depth thresholds (m) for exceedance duration columns |

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
| `peak_exterior_vs_peak_interior.png` | Scatter: peak exterior vs peak interior depth, coloured by peak velocity |
| `peak_exterior_vs_peak_basement.png` | Scatter: peak exterior vs peak basement depth (only when basement active) |
| `peak_exterior_vs_aggregate_loss.png` | Scatter: peak exterior depth vs aggregate loss (only with `--building-vulnerability`) |

**`batch_results.csv` columns**

| Column | Description |
|--------|-------------|
| `case_id` | Numeric case index |
| `depth_file` | Depth hydrograph filename (2- or 3-column) |
| `h_peak_ext` | Peak exterior depth (m) |
| `h_peak_int` | Peak interior ground-floor depth (m) |
| `h_peak_basement` | Peak basement depth (m) |
| `h_peak_sump` | Peak sump depth (m), only when sump configured |
| `v_peak_ext` | Peak exterior velocity (m/s) |
| `dur_h<XXX>cm_<tu>` | Duration above threshold XXX cm, in selected time units |
| `building_content_loss` | Ground-floor contents loss (GBP), only with `--building-vulnerability` |
| `basement_content_loss` | Basement contents loss (GBP), only with `--basement-vulnerability` |
| `aggregate_content_loss` | Sum of building and basement content losses (GBP) |

### Force outputs (only with `--compute-forces`)

| File | Description |
|------|-------------|
| `forces.csv` | Time series of $F_{hydro}$, $F_{drag}$, $F_{total}$, $M_{overturn}$ |
| `forces_result.png` | Time series plot of total lateral force and overturning moment |

**`forces.csv` columns**: `time`, `h_ext`, `F_hydro_kN`, `F_drag_kN`, `F_total_kN`, `M_overturn_kNm`.
