# Model description

This document covers the physical model, governing equations, numerical scheme, and code architecture.

---

## Compartment architecture

The building is represented as a network of up to three well-mixed compartments. Each compartment stores a volume of water and exchanges flow with its neighbours through discrete openings.

```
exterior
   │  ← exterior-to-ground ingress paths (--ingress)
   │  ← exterior-to-basement pathways (--basement-ingress; into the sump if present)
   │
ground floor ──── basement ──── sump pit (below the basement floor)
               ↑             ↑
          bypass         pit opening (drainage) / spill when full
          (optional)
                              ↓ pump discharge → exterior
```

**Elevations** — all elevations (sills, floors, ceilings, sump base) are measured from **external ground level**, $z = 0$; the exterior depth $h_{ext}$ is measured from the same level, so $H_{ext} = h_{ext}$.

**Ground floor** — the primary interior compartment. Plan area $S$ (m²), floor at $z_{floor}$ (`--floor-datum`, default 0), water depth $h_{in}(t)$ above the floor; absolute water-surface elevation $H_{in} = z_{floor} + h_{in}$.

**Basement** — optional. Plan area $S_b$ (m²), floor at elevation $z_b < 0$. Water depth $h_b(t)$ measured above $z_b$; absolute water-surface elevation $H_b = z_b + h_b$. A ceiling cap $z_{ceil}$ can be set; water exceeding the cap spills to the ground floor.

**Sump** — optional pit below the basement floor: plan area $A_s$ (m²), base at elevation $z_s < z_b$, top at the basement floor $z_b$, so its depth is $d_s = z_b - z_s$. Water depth $h_s(t) \le d_s$ above $z_s$. The exterior-to-basement pathways discharge into the pit; basement water drains into it through its opening at the floor; a full pit spills onto the basement floor. The pump draws from the pit only.

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
| $z_{floor}$, $z_b$, $z_s$ | m | Ground-floor, basement-floor and sump-base elevations above external ground |
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

A dynamic-pressure head term is added to the external side of all exterior-facing openings, **only when the exterior water reaches the sill**.  With heads measured above the sill, $h = \max(0,\ H - z_i)$:

$$
\Delta H_{i,\mathrm{eff}} = h_{ext} + \frac{v_{ext}^2}{2g}\,\mathbf{1}[H_{ext} > z_i] - h_{tgt}
$$

Velocity alone never drives flow: with the exterior water below the sill, a dry interior at the sill level receives nothing, and interior water above the sill drains out at the hydrostatic rate whatever the street velocity.  The submerged test also uses the raw $H_{ext}$ because the opening must be physically wetted to pass flow.

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
S_b\;\frac{dh_b}{dt} = Q_{ext \to b}(t) \;+\; Q_{s \to b}(t) \;-\; Q_{b \to s}(t) \;-\; Q_{b \to gf}(t)
$$

where $Q_{ext \to b}$ is inflow through the exterior-to-basement pathways (only when no sump is configured; otherwise it enters the sump), $Q_{s \to b}$ is the spill of a full pit onto the floor and $Q_{b \to s}$ is drainage into the pit.

### Sump pit

$$
A_s\;\frac{dh_s}{dt} = Q_{ext \to b}(t) \;+\; Q_{b \to s}(t) \;-\; Q_{pump}(t) \;-\; Q_{s \to b}(t), \qquad 0 \le h_s \le d_s
$$

- **Drainage** $Q_{b \to s}$: orifice law through the pit opening (sill $z_b$, area `opening_area`, default $A_s$; coefficient `opening_coeff`), driven by the basement water above the floor.  Each step it is capped at the room left in the pit and the water held above it, so the explicit step cannot overshoot.
- **Spill** $Q_{s \to b}$: volume pushed above $d_s$ in a step moves onto the basement floor in the same step.
- The pump cannot remove more than the pit holds in a step.

### Full compartments (merging)

The compartments form a chain, bottom to top: sump pit, basement, ground
floor.  A compartment that is **full and has water in the compartment above**
is part of that compartment and shares its free surface:

- the pit merges with the basement when $h_s = d_s$ and $h_b > 0$;
- the basement merges with the ground floor when $h_b = z_{ceil} - z_b$ and
  $h_{in} > 0$ (a full pit then follows the basement into the merged group).

Within a merged group:

- pathways into a member discharge against the group surface (e.g. with a
  full basement under a flooded ground floor, exterior→basement pathways see
  $H_{in} = h_{in} + z_{floor}$);
- links between members (bypass, pit opening) carry no flow;
- the net inflow of all members, pump included, updates the top member:

$$
S_{gf}\;\frac{dh_{in}}{dt} = \sum_{i \in \mathcal{P}_{ext \to gf}} Q_i \;+\; \sum_{j \in \mathcal{P}_{ext \to b}} Q_j(H_{ext}, H_{in}) \;-\; Q_{pump}
\qquad \text{(all three merged)}
$$

The lower members stay full.  If a step's net outflow exceeds the water in
the top member, the remainder is taken from the members below (basement
first, then the pit), which then continue as separate compartments.  Without
this rule a full compartment would keep driving inflow against its fixed top
level and push the compartment above higher than the exterior level.

---

## Sump and pump

### Pump curve

The pump operates when $h_s \geq h_{on}$ and switches off when $h_s \leq h_{off}$. The operating flow rate uses a two-parameter quadratic approximation:

$$
Q_{pump} = \sqrt{\frac{H_{shut} - H_{lift}}{k_{pump} + k_{pipe}}}
$$

where $H_{lift} = H_{ext} - z_s$ is the lift head (reduces pump capacity as the flood rises) and $H_{shut}$ is the pump shut-off head. The pump produces zero flow when $H_{lift} \geq H_{shut}$.


---

## Numerical scheme

The simulator uses a fixed-step explicit Euler scheme. For time step index $n$ (time $t_n = n\,\Delta t$):

1. Interpolate external level $h_{ext}(t_n)$ and velocity $v_{ext}(t_n)$ to the simulation grid.
2. Compute absolute surface elevations for all compartments.
3. Evaluate $Q_i(t_n)$ for every opening using the orifice law above.
4. Evaluate pump flow and pit drainage.
5. Update compartment volumes: $V_{n+1} = V_n + Q_{net}\,\Delta t$.
6. Convert volumes to depths: $h = V/S$; clip at zero; move volume above a compartment's capacity to the compartment above (pit → basement → ground floor).  The pump never removes more water than the pit holds in that step.

### Stability guidance

The explicit Euler scheme has no CFL condition tied to wave propagation, but small errors accumulate for coarse $\Delta t$.

When a sump and pump are included, the scheme is only conditionally stable: the pump can empty the pit faster than a coarse step can resolve, and the level then oscillates between the switch-on level and empty, which can make the pit spill spuriously.  The step must satisfy

$$
\Delta t \;\leq\; \Delta t_{max} = \frac{0.5\,A_s\,h_{on}}{Q_{p,max}},
\qquad
Q_{p,max} = \eta_p\,\sqrt{\frac{H_{shut}}{k_{pump} + k_{pipe}}}
$$

so that a single step drains no more than half of the switch-on storage volume $A_s h_{on}$ at the maximum pumping rate ($Q_{p,max}$: the pump curve at $H_{lift} = 0$).  The model does not change the step: `engine.run` issues a `PumpStepWarning` stating $\Delta t_{max}$ when the configured step is larger (printed as a `WARNING:` line by `cli.py` and `batch.py`, shown in the Results tab of the app).

---

## Lateral forces

When `--compute-forces` is enabled, `cli.py` computes per-step closed-form estimates of the hydrostatic and hydrodynamic lateral forces on the flow-facing façade of width $W$ (`forces.py`).  Forces are positive inward; moments are taken about external ground level.  Basement wall forces are not included.

### Hydrostatic force

Exterior water presses on the wall from external ground up to $h_{ext}$; interior water presses back from the floor ($z_{floor}$) up to $z_{floor} + h_{in}$.  Integrating both hydrostatic distributions:

$$
F_{hydro} = \tfrac{1}{2}\,\rho\,g\,W\,\bigl(h_{ext}^2 - h_{in}^2\bigr)
\qquad
M_{hydro} = \tfrac{1}{2}\,\rho\,g\,W\,\Bigl[\frac{h_{ext}^3}{3} - h_{in}^2\Bigl(z_{floor} + \frac{h_{in}}{3}\Bigr)\Bigr]
$$

$F_{hydro}$ is negative when the interior water pushes outward (e.g. after the flood recedes).  With a dry interior it reduces to $\tfrac{1}{2}\rho g W h_{ext}^2$ acting at $h_{ext}/3$.

### Hydrodynamic (drag) force

$$
F_{drag} = \tfrac{1}{2}\,\rho\,C_D\,v_{ext}^2\,W\,h_{ext}
$$

acting at $h_{ext}/2$.

### Combined force and overturning moment

$$
F_{total} = F_{hydro} + F_{drag}
\qquad
M_{overturn} = M_{hydro} \;+\; F_{drag}\,\frac{h_{ext}}{2}
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
