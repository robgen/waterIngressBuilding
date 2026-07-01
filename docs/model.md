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
| `file` | linearly interpolated from a user-supplied time series (`--external-velocity`) |

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

---

## Numerical scheme

The simulator uses a fixed-step explicit Euler scheme. For time step index $n$ (time $t_n = n\,\Delta t$):

1. Interpolate external level $h_{ext}(t_n)$ and velocity $v_{ext}(t_n)$ to the simulation grid.
2. Compute absolute surface elevations for all compartments.
3. Evaluate $Q_i(t_n)$ for every opening using the orifice law above.
4. Evaluate pump and overflow flows.
5. Update compartment volumes: $V_{n+1} = V_n + Q_{net}\,\Delta t$.
6. Convert volumes to depths: $h = V/S$; clip at zero.

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

| Module | Public interface | Upstream imports |
|--------|-----------------|------------------|
| `engine.py` | `engine.run(config, hydro) → SimResult` | `pump`, `forces` |
| `fragility.py` | `fragility.run(config, hydro) → MonteCarloResult` | `engine` |
| `batch.py` | `batch.run(config, hydro_dir) → BatchResult` | `engine`, `fragility`, `loss` |
| `pump.py` | `SumpPump`, `compute_*` helpers | — |
| `loss.py` | `loss.load(path)`, `loss.evaluate(curve, depth)` | — |
| `plot.py` | `plot.simulation()`, `plot.batch()`, `plot.montecarlo()` | — |
| `report.py` | `report.generate(result)`, `report.to_csv(result, path)` | — |
| `forces.py` | `compute_combined_forces()` | — |
| `cli.py` | CLI entry point | all above |
| `app.py` | Streamlit UI | all above |

`engine` is the only module with no upstream project imports. `fragility` and `batch` call `engine.run()` and do not re-implement the physics.

### Key data structures

```
SimConfig
├── floor_area: float              # m²
├── dt: float                      # timestep in time_units
├── time_units: str                # 'seconds' | 'minutes' | 'hours'
├── ingress: List[IngressPath]     # exterior → ground-floor pathways
├── basement: Optional[BasementConfig]
│     ├── area, floor_elev, ceiling_elev
│     ├── opening: IngressPath     # exterior → basement (same type)
│     ├── connection: Optional[IngressPath]   # ground-floor ↔ basement bypass
│     └── sump: Optional[SumpPump]
└── montecarlo: Optional[MonteCarloConfig]
      ├── n_replicates: int
      └── seed: Optional[int]

Hydrograph
├── times: List[float]
├── levels: List[float]
├── vel_times: Optional[List[float]]
└── vel_levels: Optional[List[float]]
```

### Dispatch logic

`cli.py` and `app.py` build a `SimConfig` from user inputs, then call:

- `engine.run(config, hydro)` — if no fragility (`config.montecarlo is None`)
- `fragility.run(config, hydro)` — if `config.montecarlo is not None` and a single hydrograph
- `batch.run(config, hydro_dir)` — if a folder of hydrographs is provided; internally calls `engine.run()` or `fragility.run()` per hydrograph

### Reversibility flag

Every fragility-bearing element (ingress path or membrane) carries a mandatory `reversible: bool` field. When `reversible=False`, the element's active state is latched at the highest state reached during the event; it cannot recover to a lower state even as the flood recedes. The latch is local to each Monte Carlo replicate and resets between replicates. Deterministic paths (no fragility states) do not require this field. See `docs/fragility.md` for the full reversibility mapping guidance.

### Regression contract

All twelve validation case studies in `examples/` have reference peak metrics in `examples/reference/`. `tests/test_regression.py` runs each case and asserts computed metrics match reference values within tolerance (1 % for peak depths, 5 % for volumes). This test must pass before any merge.
