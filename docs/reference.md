# Input and output reference

---

## Inputs

### Unified pathway CSV format

All pathway inputs — ground-floor ingress, basement perimeter openings, and membranes — share an identical CSV format. One parser (`fragility.parse_pathway_text`) handles all three; routing is determined by which CLI flag the file is passed to.

**Format rules**

- First non-comment row is a **header** with comma-separated column names.
- Lines starting with `#` are comments and are ignored.
- Blank lines are ignored.
- Columns `name`, `height_m`, `area_m2`, `Cd` are required.
- `group_id` is optional (defaults to `0` = ungrouped, no membrane protection).
- `reversible` is required on every row that has fragility state columns (`1` = state follows the current head, e.g. overtopping; `0` = state latches at the worst reached, e.g. a failed seal); it may be left empty on deterministic rows.
- Fragility state columns are optional and repeat in blocks of five per state: `state_name_N`, `median_m_N`, `beta_ln_N`, `area_m2_N`, `Cd_N`.
- Medians must be strictly increasing within a pathway.
- A pathway with `group_id > 0` must not carry its own fragility state columns.

**Column reference**

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `name` | string | yes | Unique identifier |
| `height_m` | float | yes | Sill elevation above external ground (m); with `--floor-datum 0.10` an opening at floor level has `height_m = 0.10` |
| `area_m2` | float | yes | Orifice area in the base (unloaded) state (m²) |
| `Cd` | float | yes | Discharge coefficient in the base state |
| `group_id` | int | no | Membrane group ID; `0` = ungrouped |
| `reversible` | 0/1 | with fragility | Whether a degraded state can recover when the head drops |
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
name,       height_m, area_m2, Cd,  group_id, reversible, state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1
seal_door,  0.0,      1.0e-7,  0.6, 0,        0,          failed,       0.5,        0.3,       5.0e-3,    0.6
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

Two- **or** three-column CSV. Times in simulation time units (default: minutes). Levels in metres above external ground. Linearly interpolated to the simulation grid.

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

Exterior-to-basement pathways (perimeter openings, airbricks into the basement, floor–wall joints). Uses the **same** unified pathway format; every row flows into the basement (into the sump when one is configured). May include fragility states and `group_id`s shared with ground-floor rows, so one membrane can protect both.

Deterministic example:

```csv
name,         height_m, area_m2, Cd
ext_basement, 0.0,      0.005,   0.5
```

With fragility:

```csv
name,         height_m, area_m2, Cd,  group_id, reversible, state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1
ext_basement, 0.0,      1.0e-7,  0.5, 0,        0,          cracked,      0.30,       0.25,      0.005,     0.5
```

---

### Membrane file (`--membrane`)

Uses the **same** unified pathway format. Each row defines one membrane. `group_id` links the membrane to the pathways it protects. Base-state `area_m2` / `Cd` is the membrane's own leakage conductance (typically very small). State columns define the overtopping fragility.

`height_m` is the membrane sill elevation. `median_m_1` is the seal height above that sill (the physical top of the membrane).

```csv
name,           height_m, area_m2, Cd,  group_id, reversible, state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1
front_membrane, 0.0,      1.0e-6,  0.6, 1,        1,          overtopped,   0.5,        0.1,       1.0e-9,    0.6
```

---

### CLI flags

`cli.py` and `batch.py` share every flag below except those marked *cli.py only*
or listed under **Batch only** (definitions in `inputs.py`).

**Pathway files**

| Flag | Description |
|------|-------------|
| `--ingress PATH` | Ground-floor pathways CSV (optional for basement-only cases) |
| `--basement-ingress PATH` | Exterior→basement pathways CSV; every row flows into the basement |
| `--membrane PATH` | Membrane CSV (rows with `group_id > 0` and fragility states) |

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
| `--floor-datum FLOAT` | 0 | Internal floor elevation above external ground (m) |
| `--dt FLOAT` | 1 | Simulation timestep in `--time-units` |
| `--time-units STR` | `minutes` | `seconds`, `minutes`, or `hours` |
| `--outdir PATH` | `.` (cli), `batch_results` (batch) | Output directory |
| `--temp-output` | off | *cli.py only* — write to a temp directory, removed on exit |
| `--animate` | off | *cli.py only* — write a GIF animation (slow) |
| `--verbose` | off | *cli.py only* — print progress to stdout |

**Basement**

| Flag | Description |
|------|-------------|
| `--basement-area FLOAT` | Basement plan area (m²) |
| `--basement-floor-elevation FLOAT` | Basement floor elevation above external ground (m, negative = below ground) |
| `--basement-ceiling-elevation FLOAT` | Ceiling elevation above external ground (m), default `--floor-datum`; water above this spills to ground floor |
| `--basement-bypass-height FLOAT` | Sill of the ground-floor ↔ basement bypass connection (m) |
| `--basement-bypass-area FLOAT` | Area of the ground-floor ↔ basement bypass (m²) |
| `--basement-bypass-coeff FLOAT` | Discharge coefficient Cd of the ground-floor ↔ basement bypass (–); default 0.6 |

**Sump and pump** (`--sumppump-*`, always used together)

| Flag | Default | Description |
|------|---------|-------------|
| `--sumppump-area FLOAT` | — | Sump pit plan area (m²); enables the module when > 0 |
| `--sumppump-base-elevation FLOAT` | — | Pit base elevation (m), below `--basement-floor-elevation`; the pit top is at the basement floor, so its depth is floor − base |
| `--sumppump-opening-area FLOAT` | `--sumppump-area` | Area of the pit opening through which basement water drains into the pit (m²) |
| `--sumppump-opening-coeff FLOAT` | 0.6 | Discharge coefficient of the pit opening |
| `--sumppump-on-level FLOAT` | — | Pit depth above its base at which the pump switches on (m) |
| `--sumppump-off-level FLOAT` | — | Pit depth above its base at which the pump switches off (m) |
| `--sumppump-shutoff-head FLOAT` | — | Pump shut-off head $H_{shut}$ (m) |
| `--sumppump-curve-coeff FLOAT` | — | Pump-curve coefficient $k_{pump}$ |
| `--sumppump-pipe-loss-coeff FLOAT` | 0 | Pipe-loss coefficient $k_{pipe}$ |
| `--sumppump-availability FLOAT` | 1.0 | Availability factor $\eta_p$ |

With a pump, `--dt` must not exceed $0.5\,A_{sump}\,h_{on}/Q_{p,max}$ (maximum pump flow at zero lift head); otherwise a `WARNING:` line gives the largest stable step (docs/model.md, *Stability guidance*).

**Monte Carlo**

| Flag | Default | Description |
|------|---------|-------------|
| `--n-replicates INT` | 1 | Number of Monte Carlo replicates (per hydrograph in batch); 1 = a single run, with one sampled draw if the model has fragile elements |
| `--random-seed INT` | — | Optional seed for reproducibility |
| `--output-percentiles INT ...` | 10 25 50 75 90 | Percentiles in `fragility_summary.csv` |

**Forces** (*cli.py only*)

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
| `--hydrograph-files PATH_OR_REGEX ...` | Explicit files or `dir/regex` patterns (instead of `--depth-dir`) |
| `--save-timeseries` | Write `timeseries_NNN.csv` / `.png` per hydrograph (first replicate) |
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
- **Elevations**: metres above external ground level (z = 0), the level from which the exterior depth is measured. Sills, the ground floor (`--floor-datum`), the basement floor and ceiling, the bypass sill and the sump base all use this frame; below-ground elevations are negative (e.g. basement floor at −2.5 m).
- **Interior depths**: `h_in` is measured above the ground floor, `h_basement` above the basement floor, `h_sump` above the sump base.
- **Discharge coefficient**: dimensionless.

---

## Outputs

All outputs are written to `--outdir`. The files produced depend on the run mode.

### Single-run outputs (`cli.py`)

| File | Description |
|------|-------------|
| `schematic.png` | Building cross-section with the pathway table |
| `external_preview.png` | External depth hydrograph |
| `velocity_preview.png` | Exterior velocity on the simulation grid (`--n-replicates 1`) |
| `simulation_result.png` | Water depth in each active compartment vs the exterior (`--n-replicates 1`) |
| `simulation_animation.gif` | Animated cross-section (`--n-replicates 1` with `--animate`) |

### Fragility (Monte Carlo) outputs (`cli.py --n-replicates N`, N > 1)

| File | Description |
|------|-------------|
| `fragility_replicates.csv` | One row per replicate |
| `fragility_summary.csv` | Percentiles (`--output-percentiles`) of `peak_h_in`, `peak_h_basement`, `total_volume_in` |
| `fragility_state_freq.csv` | Per fragile element / membrane: fraction of replicates in exactly state k (`state_k_freq`, rows sum to 1) |

**`fragility_replicates.csv` columns**

| Column | Description |
|--------|-------------|
| `replicate_id` | Replicate index (0-based) |
| `u_<element>` | Uniform draw for a fragile path, or `u_membrane:<group_id>` |
| `h_star_<k>_<element>` | Sampled capacity threshold for state k (m above sill) |
| `peak_h_in_m` | Peak ground-floor depth (m) |
| `peak_h_basement_m` | Peak basement depth (m), 0 without basement |
| `peak_h_sump_m` | Peak sump depth (m), 0 without sump |
| `peak_h_ext_m` | Peak exterior depth on the simulation grid (m) |
| `total_volume_in_m3` | Sum of ground-floor storage increases (m³) |

### Batch outputs (`batch.py`)

| File | Description |
|------|-------------|
| `batch_results.csv` | One row per hydrograph (per replicate when `--n-replicates` > 1) |
| `batch_summary.csv` | min, p10, p25, median, p75, p90, max of peak depths, durations and losses (one-replicate runs only) |
| `schematic.png` | Building cross-section with the pathway table |
| `peak_exterior_vs_peak_interior.png` | Scatter: peak exterior vs peak interior depth, coloured by peak velocity |
| `peak_exterior_vs_peak_basement.png` | Scatter: peak exterior vs peak basement depth (one-replicate runs with basement water) |
| `ground_floor_loss.png`, `basement_loss.png`, `aggregate_loss.png` | Loss scatters (one-replicate runs with both vulnerability curves) |
| `peak_exterior_vs_aggregate_loss.png` | Loss scatter (one-replicate runs with `--building-vulnerability` only) |
| `timeseries_NNN.csv`, `timeseries_NNN.png` | Per-hydrograph time series and result figure (`--save-timeseries`; first replicate, suffix `_r00` when N > 1) |

**`batch_results.csv` columns**

| Column | Description |
|--------|-------------|
| `case_id` | Numeric suffix of the hydrograph filename |
| `replicate` | Replicate index, only when `--n-replicates` > 1 |
| `depth_file` | Hydrograph filename |
| `h_peak_ext` | Peak exterior depth (m) |
| `h_peak_int` | Peak ground-floor depth (m) |
| `h_peak_basement` | Peak basement depth (m) |
| `v_peak_ext` | Peak exterior velocity (m/s) |
| `h_peak_sump` | Peak sump depth (m), only when sump configured |
| `building_content_loss` | Ground-floor contents loss (GBP), only with `--building-vulnerability` |
| `basement_content_loss` | Basement contents loss (GBP), only with `--basement-vulnerability` |
| `aggregate_content_loss` | Sum of building and basement content losses (GBP) |
| `dur_h<XXX>cm_<tu>` | Time with ground-floor depth ≥ XXX cm, in `--time-units` |

### Force outputs (`cli.py --compute-forces`, `--n-replicates 1`)

| File | Description |
|------|-------------|
| `forces.csv` | Time series of lateral forces and overturning moment |
| `forces_result.png` | Force and moment time series |

**`forces.csv` columns**: `time` (s), `F_hydro_N`, `F_drag_N`, `F_total_N` (positive inward), `M_overturn_Nm` (about external ground), `h_ext_m`, `h_in_m`, `v_m_per_s`, `lever_hydro_m`, `lever_drag_m` (m above external ground; 0 when the force is 0). See docs/model.md, *Lateral forces*.
