# Fragility framework

This document covers the probabilistic fragility layer: statistical framework, simulation strategy, and calibration guidance.

---

## Overview

Each ingress pathway and membrane can carry a lognormal fragility function that captures uncertainty in its performance at a given flood depth. A Monte Carlo wrapper draws capacity thresholds once per replicate before the time loop; the deterministic solver then uses those thresholds at every timestep to select the active hydraulic state.

The design principles are:

- The deterministic solver is unchanged. All uncertainty is concentrated in a pre-simulation sampling step.
- A single uniform draw per element per replicate governs all state transitions for that element, ensuring monotonic degradation.
- All fragility functions are lognormal, parameterised by depth above the element sill. This is consistent with BS 8511 certification data.
- A deterministic pathway (no state columns) is the zero-fragility degenerate case and behaves identically to the existing solver.

---

## Intensity measure

The intensity measure throughout is **depth above the element sill**:

$$
h = \max(0,\; h_{ext} - z_{sill})
$$

where $z_{sill}$ is the element's sill elevation above the reference datum. This equals the static hydrostatic head on the element and maps directly to what BS 8511 tests measure (Designated Maximum Water Depth, DMWD).

---

## Lognormal fragility functions

Each state transition $k$ is governed by a lognormal exceedance fragility:

$$
P(\text{state} \geq k \mid h) = \Phi\!\left(\frac{\ln h - \ln \eta_k}{\beta_k}\right)
$$

where:
- $\eta_k$ — median capacity: depth above sill at which there is 50 % probability of reaching state $k$
- $\beta_k$ — log-standard deviation, reflecting aleatory uncertainty in product capacity
- $\Phi$ — standard normal CDF

Medians must be strictly increasing: $\eta_1 < \eta_2 < \cdots < \eta_N$.

---

## Single draw and threshold inversion

For each replicate and each element with at least one fragility state, a single uniform random variable is drawn:

$$
u \sim \mathcal{U}(0, 1)
$$

A low $u$ corresponds to a weak specimen; high $u$ to a robust one. The draw is inverted to a capacity threshold for each state:

$$
h^*_k = \eta_k \cdot \exp\!\bigl(\beta_k \cdot \Phi^{-1}(u)\bigr)
$$

This inversion is performed **once per replicate**, before the time loop. A single $u$ across all states of the same element ensures a component cannot reach a worse state without passing through all intermediate states.

---

## State selection during the time loop

At each timestep, for each element with fragility:

1. Compute $h(t) = \max(0,\; h_{ext}(t) - z_{sill})$.
2. Active state = highest $k$ for which $h(t) \geq h^*_k$; state 0 if no threshold is exceeded.
3. Apply the irreversibility latch (see below) if the element is not reversible.
4. Apply $(A_i, C_i)$ for the active state to the orifice formula.

---

## Reversibility and the irreversibility latch

Every fragility-bearing element (ingress path or membrane) carries a mandatory `reversible` flag that controls whether the element can recover from a degraded state during recession.

| `reversible` | Physical archetype | Recession behaviour |
|---|---|---|
| `True` | Flood membrane overtopping; flood skirt; demountable barrier | Returns to base state once depth drops below threshold |
| `False` | Flood door seal failure; airbrick cover failure; service-penetration seal | Remains in highest state reached for the rest of the event |

### Latch logic

When `reversible=False`, a per-element **irreversibility latch** is active:

$$
\tilde{k}(t) = \max\!\bigl(k(t),\; \max_{s \leq t}\, k(s)\bigr)
$$

where $k(t)$ is the instantaneous state derived from the fragility curve and $\tilde{k}(t)$ is the state actually applied to the conductance calculation. Once an irreversible element reaches a degraded state, it stays there even if the external level subsequently drops below the capacity threshold.

The latch resets at the start of each Monte Carlo replicate; it does not persist across events.

### Mapping guidance

| Element | Recommended flag | Reason |
|---|---|---|
| Flood membrane | `reversible=True` | Overtopping-type; restores naturally as flood recedes |
| Flood skirt | `reversible=True` | Overtopping-type; depth-controlled |
| Perimeter barrier | `reversible=True` | Depth-controlled failure |
| Flood door | `reversible=False` | Seal compression failure; requires manual repair |
| Airbrick cover | `reversible=False` | Cover can dislodge and may not reseat |
| Service-penetration seal | `reversible=False` | Hydrostatic pressure failure; remains open |
| Basement perimeter opening | `reversible=False` | Structural breach; irreversible by default |

### CSV format

The `reversible` column must appear after the standard metadata columns and before the first state column:

```
name,height_m,area_m2,Cd,group_id,reversible,state_1_name,...
seal_door,0.0,1e-7,0.6,0,0,failed,...
membrane_1,0.0,1e-6,0.6,1,1,overtopped,...
```

Values: `1` = reversible, `0` = irreversible. The column is **mandatory** for any row that carries at least one state column. Rows without state columns (deterministic paths) may omit it.

---

## Membrane hydraulics

A membrane is a perimeter protection element that shields multiple ingress pathways simultaneously. While intact, it replaces the combined conductance of all protected pathways with its own single lumped orifice. When it overtops, the protected pathways are restored to their own parameters.

| Membrane state | Condition | Effect on protected pathways |
|---|---|---|
| Intact (state 0) | $h < h^*_1$ | Representative path carries membrane $(A, C)$; all others suppressed ($10^{-9}$ m²) |
| Overtopped (state 1) | $h \geq h^*_1$ | All protected pathways restored to their own ingress-file parameters |

The representative pathway is the first row in the ingress file sharing the membrane's `group_id`.

Protected pathways must not carry their own fragility states (validated at load time): when the membrane overtops, exposed pathways are treated as deterministic openings.

---

## Basement perimeter opening

The exterior-to-basement perimeter opening supports the same fragility logic as any ingress pathway. It is defined in a separate file (`--basement-ingress`) using the same unified CSV format, and is sampled independently from ground-floor pathways and membranes.

---

## Monte Carlo workflow

For each replicate:

1. Draw $u \sim \mathcal{U}(0,1)$ independently for each probabilistic element (paths, membranes, basement opening).
2. Invert all fragility curves to capacity thresholds $h^*_k$.
3. Run `engine.run()` with a conductance resolver that evaluates thresholds at each timestep.
4. Record: capacity thresholds, $u$ values, peak depths, ingress volumes, active state at peak external depth.

After all replicates:

- Compute percentile distributions (P10, P25, P50, P75, P90) for peak metrics.
- Compute state frequency tables: fraction of replicates in which each element reached each degraded state.
- Compute rank correlations between each element's $u$ and key output metrics.

---

## Calibration guide (BS 8511)

### Equivalent orifice area from leakage rate

The base-state $A_{m²}$ is derived from the certified leakage rate $Q_{leak}$ (m³/s) at DMWD:

$$
A_{equiv} = \frac{Q_{leak}}{C_d \sqrt{2g \cdot \text{DMWD}}}
$$

Use $C_d = 0.6$ as a conventional value for seal-type openings.

### Median capacity from DMWD data

All kitemark observations are survival events (tested up to DMWD without failure). The log-likelihood for estimating $\eta$ with $\beta$ fixed is:

$$
\ell(\eta) = \sum_{i=1}^{n} \ln\!\left[1 - \Phi\!\left(\frac{\ln \text{DMWD}_i - \ln \eta}{\beta}\right)\right]
$$

Fix $\beta$ from the literature (0.30–0.40 for engineered products) and estimate $\eta$ by MLE; or treat $\beta$ as a sensitivity parameter.

### Component-specific guidance

| Component | Standard | Leakage limit | Typical $\beta$ | Degraded state |
|-----------|----------|---------------|-----------------|----------------|
| Flood door | BS 8511-1 | ~1 L/hr/m perimeter at DMWD | 0.30–0.40 | Physical door gap area |
| Airbrick cover | BS 8511-1 | ~500 ml/hr/m perimeter at DMWD | 0.25–0.35 | Open airbrick (~0.006–0.010 m²) |
| Service penetration seal | BS 8511-1 | No standard limit; product-specific | 0.35–0.40 | Annular gap around pipe |
| Flood skirt (building-attached) | BS 8511-1 | Same as airbrick category | 0.05–0.10 (installation height) | — |
| Demountable barrier | BS 8511-2 | ~40 L/hr/m perimeter at DMWD | 0.07–0.12 | — |
| Permanent flood wall/bund | CIRIA C790 | No product standard; design-specific | 0.03–0.07 (settlement) | — |

For membranes (skirts, barriers, bunds), `median_m_1` is the seal height above the membrane sill (the nominal product height). `beta_ln_1` reflects installation height tolerance rather than material scatter.

---

## Summary of assumptions

| Assumption | Justification | Limitation |
|---|---|---|
| Depth above sill as intensity measure | Directly what BS 8511 tests measure | Cannot represent pressure-differential failures |
| Single $u$ per element | One capacity realisation per product; monotonic transitions | Ignores correlation between elements |
| Thresholds fixed before time loop | Efficient; decouples sampling from hydraulics | Transitions are instantaneous; no gradual degradation |
| Lognormal fragility | Standard in component reliability; positive-valued intensity | Limited empirical validation for PFR products specifically |
| $\beta$ fixed from literature | Right-censored kitemark data do not identify $\beta$ jointly with $\eta$ | Epistemic uncertainty in $\beta$ not reflected in ensemble spread |
| Membrane protected paths are deterministic | Avoids ambiguous compound fragility | Exposed paths treated as fully unprotected when membrane overtops |
| Basement and membrane fragilities are independent | Physically correct | Scenarios with a single barrier protecting both levels cannot be represented |
| Irreversibility latch resets between events | Modelled as single-event simulation | Multi-event cumulative damage not represented |
| Per-element reversibility only | Avoids coupling across elements | Scenarios where one failure triggers another (cascade) cannot be modelled |
