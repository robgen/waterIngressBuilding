# Known limitations

Deliberate trade-offs and known simplifications in the current implementation. None is a bug; each represents a future extension opportunity.

---

## Physical model

### A. Full orifice area applied regardless of partial submergence

`engine.py` — `IngressPathway.compute_flow`

The orifice formula uses the full area $A$ even when the water surface is only slightly above the sill. For near-threshold events (exterior water within a few centimetres of sill height) the flow is over-estimated; for deep flooding scenarios the error is negligible.

**Possible fix:** two-regime formula — sharp-crested weir for partial submergence, orifice for fully submerged.

---

### B. Simplified quadratic pump curve

`pump.py` — `compute_pump_flow`

The operating point $Q^* = \sqrt{(H_{shut} - H_{lift})/(k_{pump} + k_{pipe})}$ is a two-parameter parabolic approximation. It cannot represent flat-curve (constant-flow) pumps, multi-speed drives, or partial-load behaviour near shut-off.

**Possible fix:** accept a tabulated $(Q, H)$ curve and interpolate the operating point as the intersection with the system curve.

---

### C. `pump_availability` conflates reliability with degraded performance

`pump.py` — `SumpPump`

`pump_availability` ($\eta_p$) multiplies $Q$ directly, representing continuous capacity degradation. For fragility analysis the intended use is Bernoulli failure (the pump either runs or fails completely); the two interpretations produce different risk curves and are not distinguished.

**Possible fix:** add a separate `pump_failure_prob` parameter for binary failure; reserve `pump_availability` for continuous degradation (partial blockage).

---

### D. No ground-floor depth cap

`engine.py` — `Building`

The basement has an explicit ceiling cap (`basement_ceiling_elevation`) but the ground floor has no equivalent. For extreme events or misconfigured inputs, $h_{in}$ can grow without bound.

**Possible fix:** add `ground_ceiling_elevation` and enforce the same cap logic as the basement.

---

### E. Groundwater and soil pressure not modelled

All simulation modules

Perimeter inflow is driven entirely by the surface water level $H_{ext}$. Saturated-soil pressure on basement walls — which can dominate when the water table rises without surface flooding — is not represented.

**Possible fix:** accept a groundwater head time series and add a Darcy-type perimeter leakage term.

---

### F. Forces computed for the ground-floor façade only

`forces.py`

Hydrostatic and drag forces are computed for the ground-floor façade. Basement wall pressure (lateral earth pressure plus hydrostatic component from a flooded basement exterior) is ignored. For buildings with deep basements the ground-floor-only forces can be a significant underestimate.

**Possible fix:** add a basement-wall force calculation using $h_b$, $z_b$, and the perimeter length.

---

### G. Single lumped ground↔basement connection

`engine.py` — `_internal_pathways`

Exterior→basement inflow can be split over any number of pathways (`--basement-ingress` rows), but the ground↔basement connection is a single lumped orifice (`--basement-bypass-*`). Several discrete internal connections at different sills are not modelled.

---

## Numerics

### H. Explicit Euler accuracy and sump oscillation

`engine.py`

The explicit Euler scheme accumulates integration error at coarse $\Delta t$. For sump-enabled runs, a pump that can drain more than the on-level sump volume in a single step causes spurious oscillations. The stability criterion is:

$$
\Delta t \;\leq\; \frac{A_s\,h_{on}}{Q_{pump}}
$$

Setting $\Delta t \leq 0.5\,\Delta t_{crit}$ provides adequate margin. See the timestep sensitivity case studies (ex01, ex06) for quantitative guidance.

---

## Resolved items (summary)

Issues found in earlier reviews and resolved in the current implementation (details in CHANGELOG.md):

| Item | Description | Resolution |
|------|-------------|------------|
| R1 | `Building` state mutated in place — `sim.run()` not idempotent | State snapshotted at construction, reset on each call |
| R2 | `_vel_index` persisted across `run()` calls | Reset on each call |
| R3 | `has_sump` inferred from flow activity | Explicit flag in trace |
| R4 | Animation recomputed flows instead of reading the trace | Arrows use the engine trace |
| R5 | No `SumpPump` parameter validation | `__post_init__` raises on bad inputs |
| R6 | Malformed pathway rows silently skipped | Warning emitted |
| R7 | Legacy `always_open` and positional ingress formats | Removed; header-based pathway CSV only |
| R8 | `VulnerabilityCurve` frozen but held mutable lists | Converted to tuples |
| R9 | Batch file matching by digit concatenation was fragile | Trailing-digit regex |
| R10 | Bypass Cd hardcoded (0.6 in `cli.py`, 1.0 in `batch.py`/`app.py`) | `--basement-bypass-coeff` (default 0.6) |
| R11 | Basement inflow dropped in Monte Carlo and dashboard runs | Single model assembly in `engine.run` for every mode |
| R12 | Full basement kept driving inflow against its ceiling level (indoor level above the flood) | Merging rule (docs/model.md, *Full compartments*) |
| R13 | Sump and basement lumped into one volume; crest measured from the sump base but basement water from the basement floor; weir overflow parameters unused | Sump is a third compartment: a pit whose top is the basement floor, with drainage through its opening and spill when full |
