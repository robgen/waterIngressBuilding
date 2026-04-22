# Synthetic Flood Hydrograph Dataset — Technical Documentation

**Dataset:** 100 depth hydrographs + 100 velocity hydrographs
**Generator:** `generate.py` (random seed 42, fully reproducible)
**Format:** CSV, time in minutes, depth in metres, velocity in m/s

---

## 1. Motivation and Scope

Flood ingress simulations require realistic boundary conditions expressed as
time-varying water depth and flow velocity at the external face of a building.
Rather than using a single representative hydrograph, a dataset of 100 cases
spanning the plausible range of UK and European residential flood scenarios
was constructed synthetically.

The generation strategy follows the **"stochastic design hydrograph"**
framework: analytical shapes whose parameters are drawn from probability
distributions calibrated against the published statistical characterisation of
observed flood events. Three flood-type regimes are represented, proportional
to their expected frequency of occurrence in urban/peri-urban settings in
temperate climates.

---

## 2. Flood-Type Classification

The 100 cases are divided into three hydrological regimes following the
typology of Brunner et al. (2017), who classified thousands of observed
European hydrographs by their rise time, recession duration, and shape index:

| Type | Cases | Time to peak *T*_p | Recession ratio *r* | Timestep |
|---|---|---|---|---|
| Flash / urban convective | 40 | 30 – 240 min | 1.2 – 2.0 | 5 min |
| Short-rain | 40 | 4 – 24 h | 1.5 – 3.5 | 15 min |
| Prolonged / fluvial | 20 | 24 – 120 h | 2.0 – 6.0 | 60 min |

The 2:2:1 ratio (flash : short : prolonged) reflects the predominance of
short-duration events in urban and peri-urban settings, where impervious cover
shortens the catchment response time considerably relative to rural basins
(SCS/NRCS, 1972; Boughton & Droop, 2003).

Within each type, *T*_p is drawn from a **log-uniform distribution** over the
stated range. Log-uniform sampling ensures proportional coverage of short and
long events rather than over-representing the long end of the range.

---

## 3. Depth Hydrograph Shape

### 3.1 Rising Limb

The rising limb uses a **gamma-type analytical form** that is zero at *t* = 0,
strictly monotonically increasing, and reaches the peak *h*_peak at *t* = *T*_p
by construction:

$$h(t) = h_\text{peak} \cdot \left(\frac{t}{T_p}\right)^\alpha \cdot \exp\!\left[\alpha\!\left(1 - \frac{t}{T_p}\right)\right], \quad 0 \le t \le T_p$$

**Proof of peak at *T*_p:**

$$\frac{dh}{dt} = h_\text{peak} \cdot \frac{\alpha}{T_p} \cdot \tau^{\alpha-1} \cdot e^{\alpha(1-\tau)} \cdot (1-\tau) = 0 \iff \tau = 1 \; (t = T_p)$$

where τ = *t* / *T*_p. The function is positive and increasing on (0, *T*_p)
for all α > 0. This is functionally equivalent to a normalised **Pearson
Type III (gamma) PDF** used extensively in hydrology for unit hydrograph
derivation (Chow, Maidment & Mays, 1988).

The shape parameter α is drawn from **Uniform(1.5, 4.0)**:

- Low α (≈ 1.5): concave-up rising limb — gradual initial rise, rapid approach
  to peak. Characteristic of catchments with significant initial abstractions.
- High α (≈ 4.0): convex-up rising limb — rapid early rise, less steep near
  peak. Characteristic of flashy impervious catchments.

### 3.2 Recession Limb

The recession follows a **single-store exponential decay** (Maillet, 1905),
which is the classical solution of linear groundwater outflow and is also used
as the standard recession model in HEC-HMS and SWMM:

$$h(t) = h_\text{peak} \cdot \exp\!\bigl[-k\,(t - T_p)\bigr], \quad t > T_p$$

The recession rate *k* is defined implicitly by the **recession ratio** *r*
(recession duration as a multiple of *T*_p), with the convention that *h*
reaches 1 % of *h*_peak at *t* = *T*_p + *r* · *T*_p:

$$k = \frac{\ln 100}{r \cdot T_p}$$

This ensures continuity at the peak (*h*(*T*_p) = *h*_peak from both sides)
and a smooth, physically plausible recession tail.

The recession ratio *r* is drawn from a **Uniform** distribution whose bounds
depend on flood type (see Table in Section 2), consistent with the rise/
recession ratios reported by Brunner et al. (2017) and the SCS dimensionless
unit hydrograph (NRCS, 2007), which prescribes *r* ≈ 1.67 for a standard
mixed catchment (Peak Rate Factor 484).

### 3.3 Peak Depth Distribution

Peak depths *h*_peak are drawn from a **log-normal distribution**:

$$\ln h_\text{peak} \sim \mathcal{N}(\mu_{\ln}, \sigma_{\ln}^2)$$

with **median = 0.50 m** (i.e. μ_ln = ln 0.5 ≈ −0.693) and **σ_ln = 0.75**,
giving the following approximate percentiles:

| Percentile | *h*_peak (m) | Context |
|---|---|---|
| 10th | 0.11 | Below doorstep level for many properties |
| 25th | 0.21 | Surface water ponding |
| 50th | 0.50 | Moderate ground-floor flooding |
| 75th | 1.07 | Significant inundation |
| 90th | 1.81 | Severe; contents and structure affected |

Samples are hard-clipped to [0.05, 2.50] m. The chosen distribution is
consistent with:

- The Environment Agency's Surface Water Flood risk map depth thresholds
  (0.2, 0.3, 0.6, 0.9, 1.2 m);
- The FLEMOflash damage model calibration range (Kellermann et al., 2020),
  where significant structural damage begins at approximately 0.28 m and
  total loss is associated with depths above ~2.3 m;
- The empirical depth distribution reported for UK insurance claims after the
  summer 2007 floods, where the majority of residential claims involved
  interior depths in the 0.2–1.0 m range (Chatterton et al., 2010).

---

## 4. Velocity Hydrograph

### 4.1 Peak Velocity Estimation

Flood velocity is not simulated independently; instead, the peak velocity is
estimated from the peak depth via a **Manning-type power law with stochastic
coefficients**, following the approach of Kreibich et al. (2009):

$$V_\text{peak} = C \cdot h_\text{peak}^\beta$$

where:

- **C ~ Uniform(0.30, 1.50)** — effective conveyance coefficient (m^(1−β)/s).
  This subsumes channel geometry, slope, and Manning roughness *n*. For a wide
  rectangular channel, *C* = *S*^0.5 / (*n* · *R*^(2/3−β)), where *R* is
  hydraulic radius and *S* is bed slope.
- **β ~ Uniform(0.40, 0.70)** — depth exponent. Manning's equation yields
  β = 2/3 ≈ 0.667 for a wide channel; lower values (0.4–0.5) reflect
  overland / street flow where momentum losses are more complex.

Samples are clipped to [0.05, 5.0] m/s. The upper bound of 5 m/s is
consistent with the maximum velocities reported in extreme flash floods such
as Boscastle 2004 (> 4 m/s in the valley channel; Roca & Davison, 2010).
The human stability threshold of *v* · *d* < 0.6 m²/s (adults) from DEFRA
FD2320/FD2321 is not enforced as a hard constraint, since the dataset is
intended to represent the full hazard range, not only human-safe conditions.

### 4.2 Velocity Hydrograph Shape

The velocity time series uses the **same gamma + exponential analytical form**
as the depth hydrograph, but with independently sampled shape parameters
(α_v, *r*_v) and a **temporal lead** relative to the depth peak:

$$t_{V_\text{peak}} = T_p \cdot (1 - \lambda), \quad \lambda \sim \text{Uniform}(0.00,\, 0.20)$$

The lead ratio λ reflects the physical observation that in unsteady open-
channel flow the velocity wave (kinematic wave) can arrive slightly before
the depth wave (dynamic wave), particularly in flash floods with steep water
surface gradients. The lead is bounded to 20 % of *T*_p, consistent with
kinematic wave theory for Froude numbers < 1 (Lighthill & Whitham, 1955).

The recession of velocity is tied to the depth recession ratio with a ±20 %
multiplicative scatter: *r*_v = *r* · Uniform(0.8, 1.2), preserving the
physical correlation between depth and velocity recession while introducing
realistic variability.

---

## 5. Reproducibility and Random Seed

All stochastic sampling uses Python's `random` module (Mersenne Twister) and,
when available, NumPy's `numpy.random`, both initialised with **seed = 42**.
Regenerating the dataset by running `generate.py` from the same Python
environment will produce bit-identical output. The complete parameter set for
each case is stored in `metadata.csv` alongside the hydrograph files.

---

## 6. Dataset Statistics (realised sample)

After generation, the 100 cases exhibit the following summary statistics:

| Variable | Min | Median | Max | Notes |
|---|---|---|---|---|
| *h*_peak (m) | 0.07 | 0.46 | 2.01 | Log-normal, clipped [0.05, 2.50] |
| *V*_peak (m/s) | 0.14 | 0.59 | 2.30 | Manning-type, clipped [0.05, 5.00] |
| *T*_p (min) | 34 | 460 | 6 230 | Log-uniform per type |
| Event duration (min) | 125 | 1 530 | 50 640 | *T*_p + *r*·*T*_p + tail |
| Timestep dt (min) | 5 | 15 | 60 | Fixed per flood type |

---

## 7. Limitations

1. **Compound events** (multiple peaks, rainfall bursts separated by dry
   periods) are not represented. The dataset consists exclusively of
   single-peak hydrographs.

2. **Backwater and tidal effects** are not modelled. Velocities are derived
   from depth via a quasi-steady Manning approximation; hydrodynamic effects
   (e.g. velocity surging ahead of depth in steep channels) are represented
   only approximately via the lead-ratio parameter.

3. **Spatial variability** is absent. Each case provides a single time series
   assumed uniform over the building facade, consistent with the zero-
   dimensional ingress model it is intended to drive.

4. **Negative correlation between *T*_p and *h*_peak** within flood types is
   not enforced. In reality, short flash floods can produce extreme depths in
   confined areas (e.g. Boscastle), while prolonged fluvial events may
   accumulate comparable depths over a longer duration. The dataset samples
   these parameters independently.

---

## 8. Usage

### 8.1 File Format

All files follow the same two-column CSV format used by the water ingress
simulation engine, with `#`-prefixed comment lines at the top:

```
# Synthetic flood depth hydrograph — case 007
# type=flash  T_peak=87.4 min  h_peak=0.312 m  alpha=2.851  recession_ratio=1.743
# time (min), depth (m)
0.0,0.0
5.0,0.0012
10.0,0.0089
...
```

Time is always in **minutes**. Depth is in **metres above external ground
level** (equivalent to *h_out* in the simulation model). Velocity is in
**m/s**.

### 8.2 Running a Single Case via CLI

```bash
python3 main.py \
  --external "hydrographs/depth/depth_042.csv" \
  --ingress  path/to/ingress.csv \
  --external-velocity "hydrographs/velocity/velocity_042.csv" \
  --floor 50 --dt 1 --time-units minutes \
  --outdir results/case_042
```

### 8.3 Batch Run (all 100 cases)

```bash
for i in $(seq -w 1 100); do
  python3 main.py \
    --external  "hydrographs/depth/depth_${i}.csv" \
    --ingress   path/to/ingress.csv \
    --external-velocity "hydrographs/velocity/velocity_${i}.csv" \
    --floor 50 --dt 1 --time-units minutes \
    --outdir "results/case_${i}"
done
```

### 8.4 Using the Streamlit App

Upload any `depth_NNN.csv` as the **external levels** file and the
corresponding `velocity_NNN.csv` as the **velocity** file. Select
*Time units = minutes* and *Timestep = 1 min* (or coarser for long-duration
cases). Case metadata (flood type, peak depth, peak velocity) is available in
`metadata.csv` to help select representative or extreme cases for interactive
exploration.

### 8.5 Regenerating the Dataset

```bash
cd "hydrographs"
python3 generate.py
```

This overwrites all 200 CSV files and `metadata.csv` deterministically
(seed = 42). Modifying the seed or the parameter bounds in `generate.py`
produces a different ensemble while preserving the same physical methodology.

---

## 9. References

**Hydrograph shape and flood type classification**

- Brunner, M.I., Sikorska, A.E., Furrer, R. & Favre, A.-C. (2017). Uncertainty
  assessment of synthetic design hydrographs for gauged and ungauged catchments.
  *Water Resources Research*, 53(5), 3427–3446.
  https://doi.org/10.1002/2016WR019535

- Chow, V.T., Maidment, D.R. & Mays, L.W. (1988). *Applied Hydrology*.
  McGraw-Hill, New York.

- NRCS (2007). *Part 630 Hydrology — Chapter 16: Hydrographs*.
  National Engineering Handbook. US Department of Agriculture, Natural
  Resources Conservation Service.
  https://directives.sc.egov.usda.gov/OpenNonWebContent.aspx?content=17752.wba

- SCS (1972). *National Engineering Handbook, Section 4: Hydrology*.
  US Soil Conservation Service, Washington DC.

**Peak depth statistics and residential flood damage**

- Chatterton, J., Clarke, C., Dent, J., Hardman, M., Hick, E., Kelly, D.,
  Moncrieff, C., Moore, K., Dawks, S., Padin, M. & Zsamboky, M. (2010).
  *The costs of the summer 2007 floods in England*. Environment Agency
  Science Report SC070039.

- Environment Agency (2013–present). *Risk of Flooding from Surface Water*
  (RoFSW) national mapping, depth thresholds 0.2 / 0.3 / 0.6 / 0.9 / 1.2 m.
  https://check-long-term-flood-risk.service.gov.uk

- Kellermann, P., Schöbel, A., Kundela, G. & Thieken, A.H. (2020).
  Estimating flood damage to railway infrastructure — the case of the
  floodpro model. *Natural Hazards and Earth System Sciences*, republished as
  part of the FLEMOflash framework.

**Velocity and hazard thresholds**

- DEFRA / Environment Agency (2003). *Flood Risks to People — Phase 1*.
  Research Report FD2317. Department for Environment, Food & Rural Affairs,
  London.

- DEFRA / Environment Agency (2006). *Flood Risks to People — Phase 2: The
  Flood Risks to People Methodology*. Research Report FD2321/TR2.
  https://assets.publishing.service.gov.uk/media/602d04a98fa8f5037d371a08/FLOOD_HAZARD_RATINGS_AND_THRESHOLDS_explanatory_note.pdf

- Kreibich, H., Piroth, K., Seifert, I., Maiwald, H., Kunert, U., Schwarz, J.,
  Merz, B. & Thieken, A.H. (2009). Is flow velocity a significant parameter
  in flood damage modelling? *Natural Hazards and Earth System Sciences*,
  9(5), 1679–1692. https://doi.org/10.5194/nhess-9-1679-2009

- Roca, M. & Davison, M. (2010). Two dimensional model analysis of flash-flood
  processes: application to the Boscastle event. *Journal of Flood Risk
  Management*, 3(1), 63–71. https://doi.org/10.1111/j.1753-318X.2009.01052.x

**Kinematic wave theory (velocity lead)**

- Lighthill, M.J. & Whitham, G.B. (1955). On kinematic waves. I: Flood
  movement in long rivers. *Proceedings of the Royal Society of London A*,
  229(1178), 281–316. https://doi.org/10.1098/rspa.1955.0088

**Recession curve model**

- Maillet, E. (1905). *Essais d'hydraulique souterraine et fluviale*.
  Hermann, Paris.

**Manning's equation and open-channel flow**

- Chaudhry, M.H. (2008). *Open-Channel Hydraulics* (2nd ed.). Springer,
  New York. https://doi.org/10.1007/978-0-387-68648-6

**Data availability (open sources consulted for calibration)**

- Environment Agency Hydrology API — historical stage and flow data for
  England at 15-minute resolution.
  https://environment.data.gov.uk/hydrology/doc/reference

- NRFA (National River Flow Archive) — daily and sub-daily flow data for
  the UK, operated by the UK Centre for Ecology & Hydrology.
  https://nrfa.ceh.ac.uk

- USGS National Water Information System — instantaneous gage height and
  discharge for US stream gauges.
  https://waterservices.usgs.gov/docs/instantaneous-values/

- Copernicus Flash Flood Benchmark Dataset (Argens 2010, Alpes-Maritimes
  2015, Aude 2018), contributed by INRAE.
  https://doi.org/10.57745/IXXNAY
