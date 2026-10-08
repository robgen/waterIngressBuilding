# Model description

This document covers the physical model, governing equations, numerical scheme, and code architecture.

---

## Compartment architecture

The building is represented as a network of up to three well-mixed compartments. Each compartment stores a volume of water and exchanges flow with its neighbours through discrete openings.

```
exterior
   │  ← exterior-to-ground ingress paths (--ingress)
   │  ← exterior-to-basement perimeter opening (--basement-ingress)
   │
ground floor ──── basement ──── sump
               ↑             ↑
          connection     overflow
          (optional)
                              ↓ pump discharge → exterior
```

**Ground floor** — the primary interior compartment. Plan area $S$ (m²), water depth $h_{in}(t)$ measured above the interior ground-floor datum (the reference elevation $z_{ref} = 0$).

**Basement** — optional. Plan area $S_b$ (m²), floor at elevation $z_b < 0$. Water depth $h_b(t)$ measured above $z_b$; absolute water-surface elevation $H_b = z_b + h_b$. A ceiling cap $z_{ceil}$ can be set; water exceeding the cap spills to the ground floor.

**Sump** — optional add-on to the basement sub-system. Plan area $A_s$ (m²), base at elevation $z_s$. When active it intercepts the exterior-to-basement perimeter inflow before it reaches the basement. Excess flow spills over a crest at height $z_s + h_{ov}$ into the basement. A pump extracts water from the sump only.

---

## Symbols and units

| Symbol | Unit | Description |
|--------|------|-------------|
| $t$ | s | Time |
| $h_{in}$ | m | Ground-floor interior water depth |
| $h_b$ | m | Basement water depth above $z_b$ |
| $h_s$ | m | Sump water depth above $z_s$ |
| $H_x$ | m | Absolute water-surface elevation for node $x$ |
| $h_{ext}(t)$ | m | External flood depth (model input) |
| $v_{ext}(t)$ | m/s | External flood velocity (optional input) |
| $S$, $S_b$, $A_s$ | m² | Plan areas of ground floor, basement, sump |
| $z_b$, $z_s$ | m | Floor/base elevations relative to datum |
| $A_i$ | m² | Orifice area of opening $i$ |
| $C_i$ | — | Discharge coefficient of opening $i$ |
| $z_i$ | m | Sill elevation of opening $i$ |
| $g$ | m/s² | Gravitational acceleration (9.81) |
| $Q$ | m³/s | Volumetric flow rate |
| $W$ | m | Flow-facing façade width |
| $\rho$ | kg/m³ | Fluid density (default 1000) |
| $C_D$ | — | Drag coefficient (default 1.0) |

---

## Orifice flow model

Each opening $i$ is modelled as a submerged orifice. Let $H_{src}$ and $H_{tgt}$ be the absolute water-surface elevations on the source and target sides. Flow is permitted only when the opening is submerged — i.e. at least one side is at or above the sill:

$$
\max(H_{src},\ H_{tgt}) \geq z_i
$$

When submerged, the instantaneous flow rate is

$$
Q_i = \mathrm{sign}(\Delta H_i)\; C_i\; A_i\; \sqrt{2g\,|\Delta H_i|}
\qquad \text{where} \quad \Delta H_i = H_{src} - H_{tgt}.
$$

Positive $Q_i$ denotes flow from source to target. The formula handles both inflow and reverse drainage with a single expression.

### Velocity correction

A dynamic-pressure head term is added to the external side of all exterior-facing openings:

$$
\Delta H_{i,\mathrm{eff}} = H_{ext} + \frac{v_{ext}^2}{2g} - H_{tgt}
$$

The submerged test still uses the raw $H_{ext}$ (not the augmented value) because the opening must be physically wetted to pass flow.

Three velocity modes are available (`--velocity-mode`):

| Mode | $v_{ext}(t)$ |
|------|-------------|
| `zero` (default) | $0$ — purely hydrostatic, no hydrodynamic contribution |
| `power_law` | $a \cdot h_{ext}(t)^{b}$ — Manning-style rating curve derived directly from the depth hydrograph; default $a = 1.5$, $b = 0.5$ |
| `file` | linearly interpolated from the third column of the hydrograph file (`--external`) |

---

## Mass balances

### Ground floor

$$
S\;\frac{dh_{in}}{dt} = \sum_{i \in \mathcal{P}_{ext \to gf}} Q_i(t) \;+\; Q_{b \to gf}(t)
$$

where $\mathcal{P}_{ext \to gf}$ is the set of exterior-to-ground-floor pathways defined in `--ingress` and $Q_{b \to gf}$ is the bypass connection flow (positive when basement overflows into ground floor).

### Basement

$$
S_b\;\frac{dh_b}{dt} = Q_{ext \to b}(t) \;+\; Q_{s \to b}(t) \;-\; Q_{b \to gf}(t)
$$

where $Q_{ext \to b}$ is inflow through the exterior-to-basement perimeter opening and $Q_{s \to b}$ is sump overflow into the basement. When no sump is configured, $Q_{ext \to b}$ acts directly on the basement; when a sump is configured, $Q_{ext \to b}$ is intercepted by the sump.

### Sump

$$
A_s\;\frac{dh_s}{dt} = Q_{ext \to b}(t) \;-\; Q_{pump}(t) \;-\; Q_{s \to b}(t)
$$

### Full basement (merged compartment)

When the basement (and sump, if present) is full to the ceiling and there is
water above the ground floor ($h_b = z_{ceil} - z_b$ and $h_{in} > 0$), the
two compartments behave as one, with free surface at the ground-floor level
$H_{in} = h_{in} + z_{floor}$:

- every exterior→basement pathway discharges against $H_{in}$ instead of the
  basement level, and its volume enters the ground-floor balance;
- the ground↔basement bypass is internal and carries no flow;
- the pump (if any) draws from the merged volume:

$$
S_{gf}\;\frac{dh_{in}}{dt} = \sum_{i \in \mathcal{P}_{ext \to gf}} Q_i \;+\; \sum_{j \in \mathcal{P}_{ext \to b}} Q_j(H_{ext}, H_{in}) \;-\; Q_{pump}
$$

The lower compartment stays full while merged.  If a step's net outflow
exceeds the water above the floor, the remainder is taken from the basement
(and sump), which then continues as a separate compartment just below the
ceiling.  Without this rule the full basement would keep driving perimeter
inflow against the fixed ceiling level and push the ground floor above the
exterior level.

---

## Sump and pump

### Pump curve

The pump operates when $h_s \geq h_{on}$ and switches off when $h_s \leq h_{off}$. The operating flow rate uses a two-parameter quadratic approximation:

$$
Q_{pump} = \sqrt{\frac{H_{shut} - H_{lift}}{k_{pump} + k_{pipe}}}
$$

where $H_{lift} = H_{ext} - z_s$ is the lift head (reduces pump capacity as the flood rises) and $H_{shut}$ is the pump shut-off head. The pump produces zero flow when $H_{lift} \geq H_{shut}$.

### Sump overflow

Overflow from sump to basement occurs when $h_s > h_{ov}$ (the overflow crest height above $z_s$). The overflow rate follows a weir-type formula:

$$
Q_{s \to b} = C_{ov}\;\bigl(h_s - h_{ov}\bigr)^{m_{ov}}
$$

with empirical coefficients $C_{ov}$ and $m_{ov}$ (default exponent 1.5).

> **Not applied in the current engine.** The sump and basement share one
> stored volume and the sump spills instantly above the crest; $C_{ov}$ and
> $m_{ov}$ have no effect (see docs/limitations.md, item D).

---

## Numerical scheme

The simulator uses a fixed-step explicit Euler scheme. For time step index $n$ (time $t_n = n\,\Delta t$):

1. Interpolate external level $h_{ext}(t_n)$ and velocity $v_{ext}(t_n)$ to the simulation grid.
2. Compute absolute surface elevations for all compartments.
3. Evaluate $Q_i(t_n)$ for every opening using the orifice law above.
4. Evaluate pump and overflow flows.
5. Update compartment volumes: $V_{n+1} = V_n + Q_{net}\,\Delta t$.
6. Convert volumes to depths: $h = V/S$; clip at zero.  The pump never removes more water than the sump and basement hold in that step.

### Stability guidance

The explicit Euler scheme has no CFL condition tied to wave propagation, but small errors accumulate for coarse $\Delta t$.

For sump-enabled runs, numerical oscillation occurs when the pump can drain more than the sump's on-level volume in a single step:

$$
\Delta t \;\leq\; \Delta t_{crit} = \frac{A_s\,h_{on}}{Q_{pump}}
$$

Setting $\Delta t \leq 0.5\,\Delta t_{crit}$ (50 % safety margin) avoids spurious overflow events.

---

## Lateral forces

When `--compute-forces` is enabled, the simulator computes per-step closed-form estimates of hydrostatic and hydrodynamic lateral forces on the flow-facing façade. Basement wall forces are not included.

### Hydrostatic force

$$
F_{hydro} = \tfrac{1}{2}\,\rho\,g\,H^2\,W
$$

Acts at $H/3$ above the base, where $H = h_{ext}(t)$ is the external wetted height.

### Hydrodynamic (drag) force

$$
F_{drag} = \tfrac{1}{2}\,\rho\,C_D\,v_{ext}^2\,W\,H
$$

Acts at $H/2$ above the base.

### Combined force and overturning moment

$$
F_{total} = F_{hydro} + F_{drag}
\qquad
M_{overturn} = F_{hydro}\,\frac{H}{3} \;+\; F_{drag}\,\frac{H}{2}
$$

---

## Code architecture

### Modules

| Module | Responsibility | Public interface |
|--------|----------------|------------------|
| `engine.py` | Physics and model assembly; the only place a `Building` and `Simulation` are built | `engine.run(config, hydro, pathways, *, conductance_resolver, progress_callback) → SimResult`, `read_hydrograph`, `hydrograph_from_columns`, `exterior_series` |
| `fragility.py` | Pathway parsing/assembly, threshold sampling, conductance resolver, Monte Carlo loop | `parse_pathway_text/file`, `assemble_pathways`, `load_pathways`, `run_replicate(config, hydro, paths, membranes, rng) → (SimResult, SampledThresholds)`, `run(config, hydro, paths, membranes) → MonteCarloResult` |
| `inputs.py` | Command-line model flags shared by `cli.py` and `batch.py` | `add_model_args`, `config_from_args`, `pathways_from_args` |
| `batch.py` | Loop over hydrograph files, tabulate and summarise | `run_batch(config, cases, paths, membranes, …)` |
| `pump.py` | Sump/pump hydraulics | `SumpPump`, `compute_*` helpers |
| `loss.py` | Vulnerability curves | `load_vulnerability_curve`, `VulnerabilityCurve` |
| `plot.py` | Figures | `save_run_result`, `save_run_animation`, `save_run_schematic`, batch/MC plots |
| `report.py` | Diagnostics from the engine trace | `diagnostics_from_trace(result.trace, config.dt)` |
| `forces.py` | Hydrostatic and drag forces | `compute_combined_forces()` |
| `cli.py` | Single-hydrograph CLI | — |
| `app.py` | Streamlit UI | — |

Call chain — every mode reaches the physics through the same path:

```
cli.py ──────┐
app.py ──────┼──► fragility.run ──► fragility.run_replicate ──► engine.run ──► Simulation
batch.py ────┘    (n replicates)    (sample thresholds,          (Building,
  (per hydrograph)                   build resolver)              bypass, sump)
```

A deterministic run is one replicate: with no fragile elements nothing is
sampled and the resolver returns the base-state pathways.

### Key data structures

```
SimConfig                          # building geometry + run control (engine.py)
├── floor_area, floor_datum
├── dt (s), time_units
├── basement_area, basement_floor_elevation, basement_ceiling_elevation
├── basement_connection_height / _area / _coeff   # ground↔basement bypass
├── sumppump: Optional[SumpPump]
├── n_replicates, random_seed, output_percentiles
└── velocity_mode, velocity_power_law_a / _b

Hydrograph                         # times in seconds
├── times, levels
└── vel_times, velocities          # velocity_mode='file' only

FragilePath                        # every pathway (fragility.py)
├── name, height_m, area_m2, Cd
├── group_id                       # > 0 → protected by that membrane
├── fragility, reversible          # probabilistic paths
└── target: 'ground' | 'basement'  # exterior → which compartment
```

### Reversibility flag

Every fragility-bearing element (ingress path or membrane) carries a mandatory `reversible: bool` field. When `reversible=False`, the element's active state is latched at the highest state reached during the event; it cannot recover to a lower state even as the flood recedes. The latch is local to each Monte Carlo replicate and resets between replicates. Deterministic paths (no fragility states) do not require this field. See `docs/fragility.md` for the full reversibility mapping guidance.

### Regression contract

All twelve validation case studies in `examples/` have reference peak metrics in `examples/reference/`. `tests/test_regression.py` runs each case and asserts computed metrics match reference values within tolerance (1 % for peak depths, 5 % for volumes). This test must pass before any merge.
