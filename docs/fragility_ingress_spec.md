# Probabilistic Fragility Layer for Water Ingress Modelling

## 1. Overview

This document specifies the probabilistic fragility extension to a deterministic water ingress simulation. The fragility layer introduces uncertainty about flood resilience measure performance, propagated through a Monte Carlo ensemble wrapped around the existing deterministic hydraulic solver.

The core design principles are:

- The deterministic solver is unchanged. All uncertainty is concentrated in a pre-simulation sampling step that computes per-element capacity thresholds for each replicate. At every timestep, the solver checks current external depth against those thresholds to select the appropriate conductance.
- A single uniform draw per path or membrane per replicate governs all state transitions for that element. This is equivalent to sampling from the element's capacity distribution and ensures monotonic state transitions.
- All fragility functions are lognormal, expressed as exceedance probabilities conditioned on depth above the element sill. This is directly consistent with BS 8511 certification data.
- The deterministic case is a natural subset: a path with no fragility columns behaves exactly as in the existing solver.
- The membrane (perimeter flood protection element) is the only one-to-many protection case and is handled by a separate optional input file, or by command-line arguments for parametric analyses.
- Physical inputs (ingress paths, membrane) always come from files by default. Command-line arguments act as overrides, primarily for parametric sweeps.

---

## 2. Physical and Statistical Framework

### 2.1 Intensity measure

The intensity measure used throughout is **depth above the element sill**, defined as:

$$h = \max(0,\ h_{\text{ext}} - z_{\text{sill}})$$

where $h_{\text{ext}}$ is the external flood depth at a given timestep and $z_{\text{sill}}$ is the sill elevation of the path or membrane above the same datum. Clipping at zero means the fragility is inactive until floodwater reaches the element.

This quantity is equivalent to the static hydrostatic head acting on the element. It is directly what BS 8511 tests measure and what DMWD (Designated Maximum Water Depth) reports. Expressing fragility in depth above sill makes fragility curves portable across buildings with different sill elevations.

### 2.2 Lognormal fragility functions

Each state transition $k$ is governed by a lognormal exceedance fragility:

$$P(\text{state} \geq k \mid h) = \Phi\left(\frac{\ln h - \ln \eta_k}{\beta_k}\right)$$

where:
- $\eta_k$ is the **median capacity**: the depth above sill at which there is a 50% probability of reaching or exceeding state $k$,
- $\beta_k$ is the **log-standard deviation** (dispersion), reflecting aleatory uncertainty in product capacity,
- $\Phi$ is the standard normal CDF.

Where more than one fragility is defined, medians must be strictly increasing: $\eta_1 < \eta_2 < \ldots < \eta_N$, ensuring monotonic degradation.

### 2.3 Permeability states

Each path or membrane is defined by a base hydraulic state (best performance) and an optional ordered sequence of degraded states. The base state is active when no fragility threshold has been exceeded.

For a path with $N$ fragility curves there are $N+1$ states total:

| State index | Description | Activation condition |
|---|---|---|
| 0 | Base (best performance) | $h < h^*_1$ |
| 1 | Degraded state 1 | $h \geq h^*_1$ |
| $\vdots$ | $\vdots$ | $\vdots$ |
| $N$ | Most degraded state | $h \geq h^*_N$ |

Each state is characterised by its own (`area_m2`, `Cd`) pair used directly as hydraulic parameters at that timestep.

For the standard two-state model (one fragility curve), the base state represents certified performance within the BS 8511 specification, and the single degraded state represents performance outside the specified range, reverting toward the unprotected opening geometry.

### 2.4 Single draw per element and capacity threshold inversion

For each replicate and each element with at least one fragility, a single uniform random variable is drawn:

$$u \sim \mathcal{U}(0, 1)$$

A low $u$ corresponds to a weak specimen — one that transitions to worse states at shallow depth. A high $u$ corresponds to a robust specimen that remains in the base state to greater depth.

The draw is inverted to produce a capacity threshold for each fragility $k$:

$$h^*_k = \eta_k \cdot \exp\!\left(\beta_k \cdot \Phi^{-1}(u)\right)$$

This inversion is performed **once per replicate**, before the time loop. The thresholds are fixed scalars for the duration of that replicate. A single $u$ across all thresholds for the same element ensures a component cannot reach a worse state without passing through all intermediate states.

### 2.5 Conductance selection during the time loop

At each timestep, for each element with fragility:

$$h(t) = \max(0,\ h_{\text{ext}}(t) - z_{\text{sill}})$$

The active state is the highest $k$ for which $h(t) \geq h^*_k$, or state 0 if no threshold is exceeded:

```
active_state = 0
for k = 1 to N:
    if h(t) >= h*_k:
        active_state = k
use area_m2[active_state], Cd[active_state]
```

### 2.6 Membrane hydraulics

A membrane is a perimeter flood protection element that shields multiple ingress paths simultaneously. While intact, it replaces the combined conductance of all protected paths with its own single equivalent orifice. When it overtops, the protected paths are restored to their own parameters.

The membrane has one fragility curve governing the overtopping transition. The median equals the nominal seal height above the membrane sill; the beta is tight (0.05–0.10) reflecting installation height uncertainty rather than material scatter.

**Membrane state behaviour:**

| Active state | Condition | Effect on protected paths |
|---|---|---|
| Intact (base) | $h < h^*_1$ | Representative path carries membrane (`area_m2`, `Cd`); all other protected paths suppressed ($10^{-9}$ m²) |
| Overtopped | $h \geq h^*_1$ | All protected paths restored to their own parameters from the ingress path file |

The representative path is the first path listed in the membrane's group (lowest row index among paths sharing the membrane's `group_id`).

When the membrane overtops, protected paths that have their own fragility are **not permitted** (see Section 4, validation). Protected paths are always deterministic; their parameters are used as-is when the membrane is overtopped.

---

## 3. Input Files

### 3.1 Ingress path file

One row per ingress path. Base hydraulic parameters are always required. Fragility columns are optional and extend the row to the right for as many degraded states as needed.

**Column specification:**

| Column | Required | Description |
|---|---|---|
| `name` | yes | Unique path identifier |
| `height_m` | yes | Sill elevation above datum (m) |
| `area_m2` | yes | Base-state orifice area (m²) |
| `Cd` | yes | Base-state discharge coefficient (–) |
| `group_id` | yes | Integer group membership. `0` = not part of any membrane group. Non-zero values link paths to a membrane row in the membrane file. Groups may also serve other analytical purposes. |
| `state_name_1` | optional | Label for first degraded state (e.g. `baseline`) |
| `median_m_1` | if state 1 defined | Lognormal median capacity for transition to state 1 (m above sill) |
| `beta_ln_1` | if state 1 defined | Log-standard deviation for transition to state 1 (–) |
| `area_m2_1` | if state 1 defined | Orifice area in degraded state 1 (m²) |
| `Cd_1` | if state 1 defined | Discharge coefficient in degraded state 1 (–) |
| `state_name_2`, `median_m_2`, ... | optional | Additional degraded states, same five-column pattern |

**Rules:**
- `group_id` is mandatory on every row. Use `0` for ungrouped paths.
- Medians must be strictly increasing across states for the same path.
- All five state columns must be present together if any one is specified.
- A path with `group_id != 0` must not define fragility columns (validated at load time; see Section 4).

**Examples:**

```
# name,            height_m, area_m2, Cd,   group_id, state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1

# Deterministic ungrouped paths
wall_crack,        0.00,     5.0e-4,  0.60, 0
unprotected_door,  0.00,     3.0e-2,  0.60, 0

# Flood door: base = certified leakage; state 1 = unprotected opening
flood_door,        0.00,     4.0e-7,  0.60, 0,        baseline,     0.70,       0.35,      3.0e-2,    0.60

# Airbrick cover: base = certified leakage; state 1 = open airbrick
airbrick_1,        0.10,     2.0e-7,  0.60, 0,        baseline,     0.45,       0.30,      8.0e-3,    0.60

# Paths protected by membrane group 1 — no fragility allowed
airbrick_2,        0.10,     8.0e-3,  0.60, 1
airbrick_3,        0.10,     8.0e-3,  0.60, 1
service_pen,       0.05,     3.0e-3,  0.65, 1
```

### 3.2 Membrane file (optional)

One row per membrane. A membrane protects all paths sharing its `group_id`. It has the same hydraulic column structure as an ingress path row, plus a `group_id` column as the join key, plus one fragility definition representing the overtopping transition.

Multiple membranes are supported (one row each, distinct `group_id` values).

**Column specification:**

| Column | Required | Description |
|---|---|---|
| `group_id` | yes | Integer matching the `group_id` of protected paths in the ingress file |
| `height_m` | yes | Membrane sill elevation above datum (m). Intensity is computed as $h = \max(0, h_{\text{ext}} - \text{height\_m})$ |
| `area_m2` | yes | Base-state equivalent leakage area of the membrane (m²). Represents entire perimeter leakage as a single lumped orifice |
| `Cd` | yes | Base-state discharge coefficient (–) |
| `state_name_1` | yes | Label for the overtopping state (e.g. `overtopped`) |
| `median_m_1` | yes | Seal height above membrane sill (m). Typically equals the nominal product height. Intensity at overtopping = depth above sill reaching this value |
| `beta_ln_1` | yes | Log-standard deviation for overtopping (–). Use 0.05–0.10 for installation height uncertainty |
| `state_name_2`, `median_m_2`, `beta_ln_2`, `area_m2_2`, `Cd_2` | optional | Second degraded state if intermediate permeability data are available |

**Note on `height_m` vs `median_m_1`:** `height_m` is the elevation of the membrane base (sill) above datum — the same convention as all ingress paths. `median_m_1` is the seal height of the membrane above its own sill, i.e. the height of the top of the membrane above its base. For a membrane sitting on flat ground (`height_m = 0`) with a 600 mm seal, `median_m_1 = 0.60`.

**Example:**

```
# group_id, height_m, area_m2, Cd,   state_name_1, median_m_1, beta_ln_1
1,          0.00,     1.0e-5,  0.60, overtopped,   0.60,       0.07
```

### 3.3 Command-line arguments (override mode)

Command-line arguments act as overrides for parametric analyses — primarily for sweeping membrane or basement parameters across multiple runs without creating a separate file per combination.

**Override precedence:**
- If a membrane file is provided and no membrane arguments are given: use the file.
- If membrane arguments are given and no membrane file exists: construct a single-membrane definition from the arguments.
- If both file and arguments are provided: arguments override the file. A warning is logged.
- If neither is provided: no membrane in this run.

**Membrane arguments** mirror the membrane file columns:

```
--membrane-group    INT     group_id of protected paths
--membrane-height   FLOAT   height_m (sill elevation, m)
--membrane-area     FLOAT   base-state area_m2 (m²)
--membrane-Cd       FLOAT   base-state Cd (–)
--membrane-median   FLOAT   median_m_1 (seal height above sill, m)
--membrane-beta     FLOAT   beta_ln_1 (–)
```

**Example parametric sweep over membrane seal height:**

```bash
for h in 0.3 0.4 0.5 0.6 0.7 0.8 0.9; do
    python run.py --ingress paths.csv \
                  --membrane-group 1 \
                  --membrane-height 0.0 \
                  --membrane-area 1e-5 \
                  --membrane-Cd 0.6 \
                  --membrane-median $h \
                  --membrane-beta 0.07
done
```

The same override logic applies to the basement argument following the existing code pattern.

---

## 4. Simulation Strategy: Step-by-Step

### Step 1 — Load ingress paths

Parse the ingress path file. For each path store base parameters and any fragility state definitions. Separate into:
- **Deterministic** (`group_id = 0`, no state columns): `area_m2` and `Cd` fixed throughout.
- **Probabilistic** (`group_id = 0`, state columns present): capacity thresholds sampled each replicate.
- **Membrane-protected** (`group_id != 0`, no state columns): parameters restored when membrane overtops.

### Step 2 — Load membrane (if provided)

Parse the membrane file or construct from arguments per override precedence rules. For each membrane, store base parameters, `group_id`, and fragility definition. Identify the representative path as the first (lowest row index) path in the ingress file sharing the membrane's `group_id`.

### Step 3 — Validate

- **Fragility–membrane conflict**: for every path with `group_id != 0`, check that no fragility columns are populated. If any are found, raise an error naming the offending path and halt. The user must either remove the fragility from the path or remove the path from the membrane group.
- **Monotonic medians**: for every probabilistic path and every membrane, verify medians are strictly increasing across states.
- **Complete state definitions**: verify all five state columns are present together for each defined state.

### Step 4 — For each Monte Carlo replicate: sample capacity thresholds

For each probabilistic path and each membrane, draw $u \sim \mathcal{U}(0,1)$ independently and invert all fragility curves:

$$h^*_k = \eta_k \cdot \exp\!\left(\beta_k \cdot \Phi^{-1}(u)\right) \quad k = 1, \ldots, N$$

Store thresholds as fixed scalars for this replicate. Deterministic paths require no sampling.

### Step 5 — Run the deterministic time loop

At each timestep $t$:

**For each probabilistic path:**
1. Compute $h(t) = \max(0,\ h_{\text{ext}}(t) - \text{height\_m})$.
2. Identify active state: highest $k$ with $h(t) \geq h^*_k$, else state 0.
3. Pass active state (`area_m2`, `Cd`) to solver.

**For each membrane:**
1. Compute $h(t) = \max(0,\ h_{\text{ext}}(t) - \text{height\_m})$.
2. Identify active state using same threshold comparison.
3. If intact (state 0): representative path carries membrane base (`area_m2`, `Cd`); all other group paths suppressed ($10^{-9}$ m²).
4. If overtopped (state 1): all group paths restored to their own ingress file parameters; membrane orifice suppressed ($10^{-9}$ m²).
5. If second state defined and active: same as overtopped, plus representative path additionally carries second-state (`area_m2_2`, `Cd_2`).

**For deterministic paths:** pass fixed `area_m2` and `Cd` unchanged.

### Step 6 — Record outputs

Per replicate: all solver outputs (peak interior depth, flood duration above thresholds, total ingress volume), sampled $u$ values, capacity thresholds $h^*_k$, and active state at peak external depth for each element.

### Step 7 — Repeat and aggregate

Repeat Steps 4–6 for $N_{\text{rep}}$ replicates. Compute:
- Percentile distributions of output metrics (P10, P50, P90, etc.).
- State frequency tables: fraction of replicates in which each element reached each state.
- Rank correlation between each element's $u$ draw and key output metrics.

---

## 5. Calibration

All calibration is external to the input files. The input files contain hydraulic parameters only (`area_m2`, `Cd`, `median_m`, `beta_ln`). The workflow below derives those values from available data sources for each component type.

### 5.1 General calibration procedure

**Converting leakage rate to equivalent orifice area:**

The base-state `area_m2` is derived from the certified leakage rate $Q_{\text{leak}}$ (m³/s) at DMWD:

$$A_{\text{equiv}} = \frac{Q_{\text{leak}}}{C_d \sqrt{2g \cdot \text{DMWD}}}$$

Use $C_d = 0.6$ as a conventional value for a seal or gap-type path. Apply this formula to the BS 8511 maximum permitted leakage rate for the product type to obtain the upper bound on the base-state equivalent area for a product that just passes certification.

**Estimating the median capacity from DMWD data:**

Every kitemark observation is a survival event. The log-likelihood for estimating $\eta$ with $\beta$ fixed is:

$$\ell(\eta) = \sum_{i=1}^{n} \ln\left[1 - \Phi\left(\frac{\ln \text{DMWD}_i - \ln \eta}{\beta}\right)\right]$$

Maximise over $\eta$. With all observations right-censored, $\eta$ and $\beta$ are not jointly identifiable — fix $\beta$ from the literature (0.30–0.40 for engineered PFR products) and estimate $\eta$ by MLE, or treat $\beta$ as a sensitivity parameter.

**Degraded-state area:**

The degraded (baseline) state represents the unprotected opening geometry. This comes from a building survey: the physical aperture dimensions of the door, window, or vent opening before any flood protection was installed. Use the survey-measured area and $C_d = 0.6$.

### 5.2 Flood door and flood window

**Applicable standard:** BS 8511-1:2019+A1:2021 (building aperture products).

**BS 8511 leakage limit:** approximately 1 L/hr per metre of perimeter at DMWD for flood doors. Convert total perimeter leakage at rated head to $A_{\text{equiv}}$ using the formula above.

**Example:** door with 3 m perimeter, DMWD = 0.6 m, leakage limit = 1 L/hr/m → $Q = 3$ L/hr $= 8.3 \times 10^{-7}$ m³/s:
$$A_{\text{equiv}} = \frac{8.3 \times 10^{-7}}{0.6 \times \sqrt{2 \times 9.81 \times 0.6}} \approx 4 \times 10^{-7} \text{ m}^2$$

**Median capacity:** MLE on kitemark dataset for flood doors (approximately 15–30 products, DMWDs ranging 300–900 mm, clustering near 600 mm). Fix $\beta = 0.35$.

**Degraded state:** physical door gap geometry from building survey, typically 0.01–0.05 m².

**Approximate dataset size:** 15–30 certified products under BS 8511.

### 5.3 Airbrick cover

**Applicable standard:** BS 8511-1:2019+A1:2021 (building aperture products — airbrick/air vent category).

**BS 8511 leakage limit:** 500 ml/hr per metre of opening perimeter at DMWD. Convert to $A_{\text{equiv}}$ at rated head.

**Median capacity:** MLE on kitemark dataset for airbrick covers (approximately 5–10 products, DMWDs in the 300–600 mm range). Fix $\beta = 0.30$. Dataset is small; treat $\beta$ as a sensitivity parameter and report results for $\beta \in [0.25, 0.40]$.

**Degraded state:** open airbrick area, typically 0.006–0.010 m² for a standard single clay airbrick (215 mm × 65 mm face with approximately 40–50% open area).

**Note:** passive airbricks (floating valve type) have an additional failure mode — valve fails to seat due to debris or fouling. This is not represented by a separate fragility state but increases the effective dispersion $\beta$. If evidence of non-deployment is available from field surveys, increase $\beta$ accordingly.

**Approximate dataset size:** 5–10 certified products.

### 5.4 Service penetration seal

**Applicable standard:** BS 8511-1 (building aperture products). Coverage of service penetrations is less explicit than for doors and airbricks; some products may be certified under bespoke test arrangements.

**Leakage limit:** no single standard limit; depends on seal type and penetration geometry. Use measured leakage from any available test data. In the absence of test data, treat the base-state area as a calibration parameter bounded by the physical gap area around the pipe or cable.

**Median capacity:** limited kitemark data. Use $\eta$ from a conservative assumption (e.g. DMWD of the best available certified seal product) and $\beta = 0.35$–$0.40$ to reflect greater uncertainty.

**Degraded state:** annular gap area around the unprotected penetration. Estimate from pipe/duct nominal diameter and wall sleeve internal diameter.

**Note:** service penetrations are highly variable in geometry; a single fragility curve may not adequately represent the full population. Where penetrations are a dominant ingress pathway, a building-specific survey and seal-specific test data are preferable to generic calibration.

### 5.5 Flood skirt (membrane, building-attached)

**Applicable standard:** BS 8511-1:2019+A1:2021 (building skirt and wall sealant systems).

**Physical description:** a flexible rubber or polymer skirt fixed to the base of an external wall, sealing low-level openings (airbricks, cable entries, shallow thresholds) behind it. The protected openings are in hydraulic series with the skirt; while intact, the skirt is the controlling element.

**Base-state area:** the skirt perimeter leakage as a single lumped equivalent orifice. Calibrate from BS 8511 certified leakage rate for skirt/sealant products (approximately 500 ml/hr/m of perimeter, same category as airbrick covers under Part 1). The skirt may cover several metres of wall, so total leakage is higher than for a single airbrick; the equivalent area scales accordingly.

**Overtopping fragility:**
- `median_m_1` = nominal skirt seal height (the physical height of the top of the skirt above its base, measured from installation records or product specification).
- `beta_ln_1` = 0.05–0.10, reflecting installation height tolerance (typically ±20–40 mm for a well-installed skirt).

**No second degraded state** unless intermediate permeability data from tests at depths between zero and DMWD are available. The dominant and well-evidenced failure mode is overtopping. Structural seal failure under hydrostatic loading is a secondary mode with no published fragility data for BS 8511-type skirts.

**Approximate dataset size:** 5–10 certified products under BS 8511 skirt/sealant category.

### 5.6 Demountable or temporary perimeter barrier (membrane)

**Applicable standard:** BS 8511-2:2019+A1:2021 (perimeter barrier systems — temporary and demountable).

**Physical description:** aluminium or steel panels slotted into permanent tracks or stacked as stop-logs across doorways, access routes, or building frontages. Protects all openings on the shielded side of the building, including doors, windows at low level, drainage gullies, and airbricks.

**BS 8511-2 leakage limit:** approximately 40 L/hr per metre of barrier perimeter at DMWD (higher than building aperture products, reflecting that rain falls on both sides during a flood event and that track-to-panel seals are less tight than door seals).

**Base-state area:** convert 40 L/hr/m at rated head to $A_{\text{equiv}}$ using the standard formula. For a 3 m wide barrier at DMWD = 0.6 m: total leakage = 120 L/hr $= 3.33 \times 10^{-5}$ m³/s:
$$A_{\text{equiv}} = \frac{3.33 \times 10^{-5}}{0.6 \times \sqrt{2 \times 9.81 \times 0.6}} \approx 1.6 \times 10^{-5} \text{ m}^2$$

**Overtopping fragility:**
- `median_m_1` = nominal barrier height above its sill.
- `beta_ln_1` = 0.07–0.12. Slightly higher than for a fixed skirt, reflecting that demountable barriers are assembled on-site and panel alignment and seal compression are more variable than a factory-fitted skirt.

**Median capacity for leakage fragility** (if a second state is defined when data are available): MLE from BS 8511-2 DMWD dataset. Dataset is larger and more spread than Part 1 (10–20 products, DMWDs from 300 mm to over 3000 mm), making joint estimation of $\eta$ more tractable if $\beta$ is fixed.

### 5.7 Permanent flood wall or bund (membrane)

**Applicable standard:** no BS 8511 product certification — permanent walls and bunds are civil structures, not tested products. Guidance from CIRIA C790 and FEMA Technical Bulletins applies.

**Physical description:** a masonry, concrete, or earth bund encircling a property or protecting a building face. Protects all openings on the landward side.

**Base-state area:** the dominant leakage path through a flood wall is typically through construction joints, gate seals, or service crossings, not through the wall fabric itself. Estimate equivalent leakage area from the wall design — seal specifications for any gates or crossings should provide leakage rates. In the absence of specific data, treat base-state area as a calibration parameter with high uncertainty.

**Overtopping fragility:**
- `median_m_1` = design crest height above sill.
- `beta_ln_1` = 0.03–0.07. Permanent structures have tighter construction tolerances than deployable products; height uncertainty is dominated by differential settlement over time (typically a few tens of millimetres).

**No product dataset.** Calibration relies on design drawings and, for existing structures, survey measurements of actual crest levels. Treat $\eta$ as the surveyed crest height and $\beta$ as a sensitivity parameter.

---

## 6. Summary of Modelling Assumptions and Limitations

| Assumption | Justification | Known limitation |
|---|---|---|
| External depth as intensity measure | BS 8511 tests use external static head; DMWD maps directly to this quantity | Cannot represent pressure-differential driven failures (e.g. slow-draining basements) |
| Single $u$ draw per element | One capacity realisation per product; ensures monotonic state transitions | Ignores correlation between elements (shared installation quality); may underestimate compound failure probability |
| Capacity thresholds fixed before time loop | Efficient; decouples sampling from hydraulics | State transitions are instantaneous at threshold depth; does not model gradual degradation within an event |
| Lognormal fragility throughout | Standard in component reliability; positive-valued intensity; consistent with right-censored MLE | Limited empirical validation of lognormal form for PFR products specifically |
| Overtopping as tight-$\beta$ lognormal | Preserves unified framework; equivalent to normally distributed installation height for small $\beta$ | Negligible overestimation of overtopping probability below nominal height for $\beta < 0.10$ |
| $\beta$ fixed from literature | Necessary: all kitemark observations are right-censored; $\beta$ not identifiable from survival data alone | Epistemic uncertainty in $\beta$ not reflected in ensemble spread; treat as sensitivity parameter |
| Membrane representative-path convention | Avoids solver modification; suppressed paths use $10^{-9}$ m² to avoid numerical issues | Physical coupling between membrane leakage and sub-floor drainage not modelled; membrane treated as single lumped orifice |
| Membrane-protected paths must be deterministic | Avoids ambiguous compound fragility logic | When membrane overtops, exposed paths are treated as fully unprotected deterministic openings; their own uncertainty is ignored |
| File-as-default, argument-as-override | Arguments are overrides for parametric sweeps; physical inputs live in files for reproducibility | Both ingestion paths must produce identical internal objects; argument parsing must be kept in sync with file column definitions |
