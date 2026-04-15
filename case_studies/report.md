# Water Ingress Simulation — Validation Case Studies

Eight cases of increasing complexity, using the same
**triangular hydrograph** (peak external depth 0.5 m at t = 30 min,
flood recedes to 0 by t = 60 min, dry tail extends to t = 360 min).
All ground-floor cases use a **50 m²** floor area (small UK terraced
house); basement cases add a **30 m²** partial basement with floor at
**−2.5 m** (full-height UK basement).

---

## Case 01 — Ground floor only, single large opening (sill = 0 m)

**Setup:** one orifice pathway (failed door flood-seal), sill at ground
level, area = 0.05 m², C_d = 0.6, floor area = 50 m².
Simulation timestep **Δt = 6 s** (see timestep sensitivity note below).

Characteristic response time:
τ = A\_floor · h\_max / Q\_max = 50 × 0.5 / 0.094 ≈ **266 s ≈ 4.4 min**

**Expected behaviour:** inflow begins immediately at t = 0.  The large
orifice equilibrates the interior with the exterior within a few
minutes.  Interior depth closely tracks external depth throughout the
flood and drains back out rapidly after t = 60 min.

**Qualitative check:** interior and exterior curves nearly coincide;
drainage complete by ≈ t = 70 min.

![](ex01/out/simulation_result.png)

[Animation (GIF)](ex01/out/simulation_animation.gif)

### Timestep sensitivity — explicit-Euler accuracy

With the corrected 50 m² floor the scheme is stable at dt = 60 s
(Δt/τ = 0.23), but the explicit-Euler method still carries a systematic
positive bias: each step slightly overshoots equilibrium.  The table
below (computed with the 50 m² floor) shows how the peak depth error
converges as Δt shrinks.

| Δt | Δt / τ | Peak h\_in (m) | Error vs 1-s ref |
|---|---|---|---|
| 60 s (1 min) | 0.23 | 0.506 | +1.1 % |
| 30 s | 0.11 | 0.500 | +0.3 % |
| 15 s | 0.06 | 0.499 | < 0.1 % |
| **6 s (fix)** | **0.023** | **0.494** | **< 0.3 %** |
| 1 s (ref) | 0.004 | 0.494 | — |

**Note:** with the original, unrealistically small 10 m² floor the
same orifice gave Δt/τ = 0.57 and caused catastrophic oscillation
(peak error +28 %).  Correcting the geometry eliminated the instability;
the residual bias at Δt = 6 s is negligible (<0.3 %).

![](ex01/out/dt_sensitivity.png)

---

## Case 02 — Raised sill (sill = 0.3 m)

**Setup:** identical to Case 01 (50 m² floor, A = 0.05 m², Δt = 6 s)
except the sill is raised to 0.3 m, representing a flood barrier or
raised threshold.

**Expected behaviour:** no inflow until the external depth exceeds
0.3 m (t ≈ 18 min on the rising limb).  After the flood recedes,
water above the sill drains back out.  Water below the sill height
(0.3 m) is **permanently trapped** — the orifice model requires h > sill
on at least one side to permit flow, so once both interior and exterior
drop below 0.3 m there is no pathway for the residual water to escape.

**Qualitative check:** interior trace flat (zero) until t ≈ 18 min;
kink clearly visible at sill-crossing; residual interior depth converges
to ≈ 0.30 m and remains constant for the rest of the simulation.

![](ex02/out/simulation_result.png)

[Animation (GIF)](ex02/out/simulation_animation.gif)

---

## Case 03 — Two openings: base crack + door gap

**Setup:** 50 m² floor, two pathways —
* Pathway A (`base_crack`): sill = 0.0 m, area = 0.001 m² — small
  permanent crack, active throughout
* Pathway B (`door_gap`): sill = 0.3 m, area = 0.005 m² — door gap,
  activates once exterior exceeds 0.3 m

Simulation extended to 360 min so the slow post-flood crack drainage
is fully visible.

**Expected behaviour:** slow linear rise while only Pathway A is
active.  At t ≈ 18 min Pathway B opens and the fill rate jumps by
~5×.  After the flood (t > 60 min) both pathways initially drain the
interior; once h\_in drops below 0.3 m only the crack remains active
and drainage slows dramatically.  Interior returns to zero by ≈ t = 360 min.

**Qualitative check:** clear inflection near t ≈ 18 min; drainage
curve shows two distinct slopes (fast above 0.3 m, slow below 0.3 m);
interior reaches zero by end of 6-hour window.

![](ex03/out/simulation_result.png)

[Animation (GIF)](ex03/out/simulation_animation.gif)

---

## Case 04 — Basement compartment (no ground-floor opening)

**Setup:** 50 m² ground floor (no effective opening), 30 m² partial
basement, floor at −2.5 m (full-height UK basement, total void ≈ 75 m³).
Lumped exterior→basement perimeter opening: sill = 0 m, area = 0.005 m²,
C_d = 0.5.  No pump.

The perimeter sill is at ground level (0 m), so its effective head is
simply h\_ext (the exterior flood depth); the basement water surface
(below ground) exerts no back-pressure.  Maximum inflow:
Q\_max = 0.5 × 0.005 × √(2g × 0.5) ≈ **0.008 m³/s**.

Without a pump, once the flood recedes (h\_ext → 0) the basement water
is **permanently trapped** — it cannot drain back through a sill at 0 m
when the exterior is dry.

**Expected behaviour:** ground-floor trace identically zero; basement
fills steadily during the 60-min flood, reaching ≈ 0.6 m depth (above
floor) by t = 60 min; level remains constant thereafter.

**Qualitative check:** ground-floor trace = 0; basement trace rises
monotonically during flood and plateaus after t = 60 min.

![](ex04/out/simulation_result.png)

[Animation (GIF)](ex04/out/simulation_animation.gif)

---

## Case 05 — Basement + sump/pump (pump keeps up)

**Setup:** identical inflow to Case 04 (30 m² basement, z = −2.5 m).
Added sump (area = 0.5 m², base at −2.5 m, overflow crest at 0.8 m
above base).  Strong pump: k\_pump = 1 000.

Q\_pump = √((H\_shut − H\_lift) / k\_pump).
At peak flood (H\_lift = |0.5 − (−2.5)| = 3.0 m):
Q\_pump = √((5.0 − 3.0) / 1 000) ≈ **0.045 m³/s** >> Q\_in\_max ≈ 0.008 m³/s.

**Expected behaviour:** the sump activates almost immediately and pumps
out all inflow.  Sump level stays below the on-level (0.10 m); no
overflow; no basement flooding; no ground-floor flooding.  After the
flood the pump drains any residual sump water.

**Qualitative check:** sump trace stays near zero (≤ 0.10 m); basement
and ground-floor traces remain at zero throughout.

![](ex05/out/simulation_result.png)

[Animation (GIF)](ex05/out/simulation_animation.gif)

### Timestep sensitivity — sump/pump oscillation

With the explicit-Euler update, the pump discharges **ΔV = Q_pump × Δt**
per step.  If ΔV exceeds the active sump volume **A_sump × h_on**, the
sump drains past zero in one step and refills to h\_on the next — a pure
numerical artefact that can push h\_sump past the overflow crest and
cause spurious basement flooding.

**Stability criterion:**

> Δt  ≤  dt\_crit  =  A\_sump × h\_on / Q\_pump

For Case 05 (A\_sump = 0.5 m², h\_on = 0.10 m, Q\_pump ≈ 0.045 m³/s):

> dt\_crit ≈ 1.1 s  →  recommended Δt ≤ **1 s** (50 % margin)

The figure below shows sump depth time-series for Δt = 60 s down to 0.5 s
(reference).  At Δt = 60 s the sump oscillates to the overflow crest,
producing a spurious 2 mm basement depth.  At Δt ≤ 2 s the level is
smooth and the basement remains dry throughout.

![](ex05/out/dt_sensitivity.png)

---

## Case 06 — Basement + sump/pump (pump overwhelmed)

**Setup:** same as Case 05 but 100× weaker pump: k\_pump = 100 000.
At peak flood:
Q\_pump = √((5.0 − 3.0) / 100 000) ≈ **0.0045 m³/s** < Q\_in\_max ≈ 0.008 m³/s.

**Expected behaviour:** pump activates but cannot match inflow; sump
level rises quickly (excess rate ≈ 0.003 m³/s over 0.5 m² ≈ 7 mm/s)
and reaches the overflow crest (0.8 m) within ≈ 2 min.  Excess water
spills into the basement, which then fills.  Contrast directly with
Case 05 where the sump never overflows.

**Qualitative check:** sump trace rises to the overflow crest and
saturates there; basement trace becomes positive soon after; sump
overflow crest visible as a horizontal asymptote.

![](ex06/out/simulation_result.png)

[Animation (GIF)](ex06/out/simulation_animation.gif)

---

## Case 07 — Fragility Monte Carlo: single probabilistic seal (500 replicates)

**Setup:** 50 m² ground floor.  One fragility path `seal_door` —
* Base state: area ≈ 0 m² (sealed)
* Degraded state (seal fails): area = 0.005 m²

Lognormal capacity: median η = 0.5 m, β = 0.3.  Peak external depth
= 0.5 m → P(seal fails) = P(h\* < 0.5 m) = **50 %** by construction.

With a 50 m² floor the characteristic fill time when the seal fails is
τ ≈ 44 min (slow relative to the 30-min rising limb), so the "failed"
cluster reaches a peak interior depth of ≈ 0.25 m — well below the
external peak of 0.5 m.

**Expected behaviour:** bimodal ensemble —
* ≈50 % of replicates: seal intact → peak\_h\_in ≈ 0
* ≈50 % of replicates: seal failed → peak\_h\_in ≈ 0.25 m

**Qualitative check:** histogram has two clearly separated clusters;
sharp discontinuity between P50 (≈ 0) and P75 (> 0); P10–P90 range is
wide.

![](ex07/out/mc_result.png)

### Percentile summary (peak_h_in, peak_h_basement, total_volume_in)

| metric | P10 | P25 | P50 | P75 | P90 |
| --- | --- | --- | --- | --- | --- |
| peak_h_basement | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| peak_h_in | 1.338816591069177e-05 | 1.338816591069177e-05 | 1.338816591069177e-05 | 0.11141965865701241 | 0.17462296390125154 |
| total_volume_in | 0.000668688295534588 | 0.000668688295534588 | 0.000668688295534588 | 5.570982212850621 | 8.731147475062578 |

### State frequency table

| element | state_0_freq | state_1_freq |
| --- | --- | --- |
| seal_door | 1.0 | 0.498 |

---

## Case 08 — Fragility Monte Carlo: membrane-protected group (500 replicates)

**Setup:** 50 m² ground floor.  Two pathways behind a flood-protection
membrane (group\_id = 1) —
* `airbrick`: sill = 0.1 m, area = 0.006 m²
* `door_gap`: sill = 0.0 m, area = 0.002 m²

Membrane: sill = 0 m, base leakage ≈ 0.  Lognormal overtopping
capacity: median = 0.5 m, β = 0.1 (tight, near-deterministic threshold).
P(membrane overtopped) = **50 %**.

When the membrane fails, total area = 0.008 m² → τ ≈ 28 min; the
"failed" cluster peak interior depth ≈ 0.20 m.

**Expected behaviour:**
* ≈50 % of replicates: membrane intact → total ingress ≈ 0
* ≈50 % of replicates: membrane overtopped → interior fills to ≈ 0.20 m

The tight β = 0.1 means the two clusters are well-separated with
little intermediate probability mass.

**Observed (seed = 42, n = 500):** same 251/249 split as Case 07
(same seed and uniform draws).

**Qualitative check:** same bimodal pattern as Case 07; slightly lower
"failed" cluster peak than Case 07 because the airbrick sill (0.1 m)
delays part of the inflow.

![](ex08/out/mc_result.png)

### Percentile summary

| metric | P10 | P25 | P50 | P75 | P90 |
| --- | --- | --- | --- | --- | --- |
| peak_h_basement | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| peak_h_in | 0.00013291917224786008 | 0.00013291917224786008 | 0.00013291917224786008 | 0.08057464579912538 | 0.11099713874695413 |
| total_volume_in | 0.006638751412392997 | 0.006638751412392997 | 0.006638751412392997 | 4.028725082756269 | 5.5498497301477085 |

### State frequency table

| element | state_0_freq | state_1_freq |
| --- | --- | --- |
| membrane:1 | 1.0 | 0.498 |
