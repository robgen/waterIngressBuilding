# Known limitations

Deliberate trade-offs and known simplifications in the current implementation. None is a bug; each represents a future extension opportunity.

---

## Physical model

### A. Full orifice area applied regardless of partial submergence

`engine.py` — `IngressPath.compute_flow`

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

### D. Sump overflow evaluated on the previous step's depth

`engine.py` — sump update block

Overflow $Q_{s \to b}$ is computed before $h_s$ is updated with the current step's inflow (explicit Euler artifact). The sump can transiently exceed the overflow crest by one full step's worth of inflow before the corrective overflow takes effect.

**Possible fix:** semi-implicit or iterative sump update.

---

### E. No ground-floor depth cap

`engine.py` — `Building`

The basement has an explicit ceiling cap (`basement_ceiling_elevation`) but the ground floor has no equivalent. For extreme events or misconfigured inputs, $h_{in}$ can grow without bound.

**Possible fix:** add `ground_ceiling_elevation` and enforce the same cap logic as the basement.

---

### F. Groundwater and soil pressure not modelled

All simulation modules

Perimeter inflow is driven entirely by the surface water level $H_{ext}$. Saturated-soil pressure on basement walls — which can dominate when the water table rises without surface flooding — is not represented.

**Possible fix:** accept a groundwater head time series and add a Darcy-type perimeter leakage term.

---

### G. Forces computed for the ground-floor façade only

`forces.py`

Hydrostatic and drag forces are computed for the ground-floor façade. Basement wall pressure (lateral earth pressure plus hydrostatic component from a flooded basement exterior) is ignored. For buildings with deep basements the ground-floor-only forces can be a significant underestimate.

**Possible fix:** add a basement-wall force calculation using $h_b$, $z_b$, and the perimeter length.

---

### H. Bypass connection coefficient hardcoded

`engine.py` — ground↔basement bypass

The discharge coefficient for the ground-floor ↔ basement connection is hardcoded to 1.0. There is no CLI flag to override it.

**Possible fix:** expose `--basement-connection-coeff` as a CLI argument.

---

### I. Lumped single perimeter opening and bypass

All simulation modules

The model represents the full basement perimeter inflow as a single lumped orifice and the ground↔basement path as a single lumped connection. Spatial variation in perimeter leakage and multiple discrete connections are not modelled.

---

## Numerics

### J. Explicit Euler accuracy and sump oscillation

`engine.py`

The explicit Euler scheme accumulates integration error at coarse $\Delta t$. For sump-enabled runs, a pump that can drain more than the on-level sump volume in a single step causes spurious oscillations. The stability criterion is:

$$
\Delta t \;\leq\; \frac{A_s\,h_{on}}{Q_{pump}}
$$

Setting $\Delta t \leq 0.5\,\Delta t_{crit}$ provides adequate margin. See the timestep sensitivity case studies (ex01, ex05) for quantitative guidance.

---

## Resolved items (summary)

The following issues were identified in earlier code reviews and are resolved in the current implementation:

| Item | Description | Status |
|------|-------------|--------|
| H | `Building` state mutated in place — `sim.run()` not idempotent | Resolved — state snapshotted at construction, reset on each call |
| I | `_vel_index` persisted across `run()` calls | Resolved |
| J | `has_sump` inferred from flow activity | Resolved — explicit flag in trace |
| K | Animation recomputed bypass flow instead of reading trace | Resolved |
| L | No `SumpPump` parameter validation | Resolved — `__post_init__` raises on bad inputs |
| M | `parse_ingress_text` passed raw strings to constructor | Resolved |
| N | Malformed ingress lines silently skipped | Resolved — warning emitted |
| O | `import math` inside `run()` | Resolved |
| P | `sample_external` closure duplicated canonical sampler | Resolved |
| Q | Legacy `always_open` ingress flag | Resolved — removed |
| R | `VulnerabilityCurve` frozen but held mutable lists | Resolved — converted to tuples |
| S | Batch file matching by digit concatenation was fragile | Resolved — uses trailing-digit regex |
