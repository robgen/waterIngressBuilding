# Known Limitations

This document records known limitations and design simplifications of the
current implementation.  None is necessarily a bug, but each represents a
deliberate trade-off or a future extension opportunity.

Items are grouped by category.  The original numbered list (from the 2025-04
code review) is preserved at the end for cross-reference.

---

## Physical model

### A. Orifice law applied regardless of partial submergence

**Affected files:** `main.py` (`IngressPathway.compute_flow`)

`compute_flow` always uses the full opening area `A`.  When the water surface
is only slightly above the sill — e.g., external water at 0.32 m through a
vent at 0.30 m — the formula drives flow through the full opening as if it were
completely submerged.  For a wide doorway at sill height 0 this is exact; for
any opening where the water surface is within a few centimetres of the sill the
flow is over-estimated.

**Severity:** Low for deep-flooding scenarios; material for near-threshold
ingress events.

**Future fix:** Replace with a two-regime formula: sharp-crested weir for
`H_source − sill < H_target − sill` (free overflow), orifice for the
fully-submerged regime.

---

### B. Simplified quadratic pump curve

**Affected files:** `pump.py` (`compute_pump_flow`)

The operating point `Q* = sqrt((H_shut − H_lift)/(k_pump + k_pipe))` is a
two-parameter parabolic approximation.  It cannot represent:
- Flat-curve (constant-flow) pumps
- Multi-speed or VFD-controlled pumps
- The partial-load region near shutoff

The pump completely stops when `H_lift ≥ H_shut`; there is no partial-throttle
regime.

**Severity:** Acceptable for residential sump pumps with a single fixed speed.
Inadequate for commercial or industrial installations.

**Future fix:** Accept a tabulated (Q, H) pump curve and interpolate the
operating point as the intersection with the system curve.

---

### C. `pump_availability` conflates reliability with degraded performance

**Affected files:** `pump.py` (`SumpPump`), `main.py` (sump block)

`pump_availability` (η_p) multiplies Q directly: a value of 0.7 means the
pump delivers 70 % of its rated flow at all times.  For a Monte Carlo fragility
pass the intended use is Bernoulli(p) — the pump either operates normally or
fails completely.  The two interpretations (partial degradation vs binary
failure) produce different risk curves and are not distinguished in the API or
documentation.

**Severity:** Low for deterministic runs (leave at 1.0).  Material for any
Monte Carlo use.

**Future fix:** Introduce a separate `pump_failure_prob` parameter for
Bernoulli-style failure, and reserve `pump_availability` for continuous
capacity degradation (e.g., partial blockage).

---

### D. Sump overflow evaluated on the previous step's depth (explicit Euler)

**Affected files:** `main.py` (`Simulation.run`, sump block)

`Q_s_bs = compute_sump_overflow(sp.h_sump, ...)` is called *before*
`sp.h_sump` is updated with the current step's inflow.  The overflow in step n
therefore responds to the depth at step n-1.  The sump can transiently exceed
the overflow crest by one full timestep's worth of inflow before the corrective
overflow takes effect.  This is a standard explicit-Euler artifact and is
already noted as part of limitation 1 (timestep sensitivity); it is stated
explicitly here because the code order makes it non-obvious.

**Severity:** Small for `dt` ≤ 60 s; increases with timestep.

**Future fix:** Compute overflow and depth update simultaneously with a
semi-implicit or iterative scheme.

---

### E. Ground floor has no water depth cap

**Affected files:** `main.py` (`Building.update_water_level`)

`update_water_level(zone='ground')` lets `h_in` grow without bound.  The
basement zone has an explicit ceiling cap (`basement_ceiling_elevation`), but
no equivalent constraint exists for the ground floor.  For extreme events or
misconfigured inputs the simulated ground-floor depth can exceed the physical
building height with no warning.

**Severity:** Low for typical events.  Misleading for sensitivity studies that
push external levels well above observed ranges.

**Future fix:** Add `ground_ceiling_elevation` to `Building` and enforce the
same cap logic as the basement.

---

### F. Groundwater and soil pressure not modelled

**Affected files:** all simulation files

Perimeter inflow is driven entirely by the surface water level `H_out`.
Saturated-soil pressure on basement walls — which can drive significant inflow
even in the absence of surface flooding — is not represented.  The model is
therefore unsuitable for events where the water table is the primary hazard
driver (e.g., prolonged antecedent rainfall without overland flooding).

**Severity:** Structural limitation; inherent to the surface-water-only
formulation.

**Future fix:** Add a separate groundwater head time series as an additional
forcing and compute a Darcy-type perimeter leakage term.

---

### G. Forces computed only for the ground-floor facade; basement omitted

**Affected files:** `forces.py`, `main.py` (`--compute-forces` path)

Hydrostatic and drag forces are computed using `H_out` and `h_in` on the
ground-floor datum, applied to the ground-floor facade width.  Basement wall
pressure (lateral earth pressure plus any hydrostatic component from a high
water table or flooded basement exterior) is ignored.  For buildings with deep
basements the ground-floor-only forces are potentially a significant
underestimate of total lateral loading.

**Severity:** Medium for buildings with basements deeper than ~1.5 m.

**Future fix:** Add a basement-wall force calculation using `h_basement`,
`z_basement`, and the perimeter length as a separate output column.

---

## Numerics and correctness

### H. ~~`Building` state is mutated in place — calling `sim.run()` twice is wrong~~ — **Resolved**

`Simulation.__init__` now snapshots `h_in`, `h_basement`, `h_sump`, and
`pump_state` at construction time.  `run()` resets all four values at the top
of every call, making it fully idempotent.  Verified: two consecutive calls on
the same instance produce bit-for-bit identical results.

---

### I. ~~`_vel_index` persists across `run()` calls~~ — **Resolved**

`self._vel_index` is now reset to 0 at the top of `run()`, eliminating the
stale-index bug on repeated calls.

---

### J. ~~`has_sump` inferred from flow activity rather than configuration~~ — **Resolved**

`Simulation.run()` writes `_trace['sump_configured'] = sp is not None`.
`diagnostics_from_trace` reads this flag directly (with a fallback to the
old flow-activity heuristic for traces from older code).  The flag is also
propagated into `diag['events']['sump_configured']` so `viz.py` can read it.

---

### K. ~~Animation re-computes ground↔basement flow rather than reading the trace~~ — **Resolved**

`generate_animation` now accepts a `Q_bypass_series` kwarg.  When supplied
(from `sim._last_trace['Q_b_bs']`), it is used directly; the fallback
re-computation loop is still present for callers that do not have trace data.
Both `main.py` and `streamlit_app.py` now pass `Q_bypass_series`.

---

### L. ~~No input validation on `SumpPump` parameters~~ — **Resolved**

`SumpPump.__post_init__` now raises `ValueError` for:
- `sump_area ≤ 0`
- `pump_off_level ≥ pump_on_level` (inverted hysteresis)
- `overflow_level < 0`

And emits `warnings.warn` for:
- `pump_shutoff_head ≤ 0` (pump always returns zero)
- `pump_on_level > overflow_level` (pump only activates after overflow)

---

## API and code quality

### M. ~~`parse_ingress_text` passes raw strings to `IngressPathway`~~ — **Resolved**

Both `parse_ingress_file` and `parse_ingress_text` now convert columns to
`float` explicitly before constructing the object.  `parse_ingress_text`
reports the offending line number in the `warnings.warn` message.

---

### N. ~~Malformed lines in ingress files are silently skipped~~ — **Resolved**

Both `parse_ingress_file` and `batch_run._parse_depth_file_maybe_combined`
count skipped lines and emit `warnings.warn(f"{n} malformed line(s) skipped
in {filepath}")` when any are discarded.

---

### O. ~~`import math` inside `Simulation.run()`~~ — **Resolved**

The stray `import math as _math` inside `run()` has been removed; the
module-level `math` import is used throughout.

---

### P. ~~`sample_external` duplicated inside `main()` with different semantics~~ — **Resolved**

The local `sample_external` closure has been deleted.  All sampling in
`main()` now uses the canonical `sample_with_zero_padding`, which pads with
0.0 beyond the hydrograph end (water has receded).

---

### Q. ~~Hidden `always_open` ingress flag expanded the public file format~~ — **Resolved**

The legacy `always_open` flag has been removed from `IngressPathway`,
`parse_ingress_file`, and `parse_ingress_text`.  Public ingress inputs are now
back to `height, area, coeff[,name]` only, matching the documented submerged-
opening behaviour used by the example models.

---

### R. ~~`VulnerabilityCurve` has mutable list fields under `frozen=True`~~ — **Resolved**

`VulnerabilityCurve.__post_init__` now converts `heights_m` and `losses` to
`tuple` via `object.__setattr__`.  The field type annotations are updated to
`tuple`.  Mutation (`curve.heights_m.append(...)`) now raises `AttributeError`.

---

### S. ~~Batch file matching by digit concatenation is fragile~~ — **Resolved**

`_numeric_suffix` now uses `re.search(r'(\d+)$', stem)` — only the trailing
digit run.  `_discover_pairs` matches depth and velocity files by
`_numeric_suffix(name) == suffix`, handling filenames with dates or version
numbers in earlier positions correctly.

---

## Cross-reference: original numbered list (2025-04 review)

| # | Title | Status |
|---|---|---|
| 1 | Timestep sensitivity of sump/pump dynamics | Open (see also D) |
| 2 | Pump lift-head is a conservative first-order approximation | Open |
| 3 | Basement overflow to ground floor is a hard volume cap | Open |
| 4 | Diagnostics duplicated the solver loop | **Resolved** — `diagnostics.py` now reads `sim._last_trace` |
| 5 | Silent pass-through of unrecognised source/target pairs | Open |
| 6 | Bypass connection coefficient hardcoded to 1.0 | Open |
| 7 | Lumped model: single perimeter opening, bypass, and sump | Open |
| 8 | No physical validation or calibration | Open |

## Cross-reference: extended list (2025-04 code review, H–S)

| # | Title | Status |
|---|---|---|
| H | `run()` mutated `Building` in place — not idempotent | **Resolved** |
| I | `_vel_index` persisted across `run()` calls | **Resolved** |
| J | `has_sump` inferred from flow activity | **Resolved** |
| K | Animation re-computed bypass flow instead of reading trace | **Resolved** |
| L | No `SumpPump` parameter validation | **Resolved** |
| M | `parse_ingress_text` passed raw strings to constructor | **Resolved** |
| N | Malformed lines skipped silently | **Resolved** |
| O | `import math` inside `run()` | **Resolved** |
| P | `sample_external` closure duplicated `sample_with_zero_padding` | **Resolved** |
| Q | Hidden `always_open` ingress flag expanded the file format | **Resolved** — removed from code and public inputs |
| R | `VulnerabilityCurve` frozen but held mutable lists | **Resolved** |
| S | Batch file matching by digit concatenation was fragile | **Resolved** |
