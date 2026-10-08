# Synthetic Flood Hydrograph Dataset

**Location:** `hydrographs/generated/0001.csv` … `0297.csv`, case list in `hydrographs/metadata.csv`
**Generator:** `hydrographs/generate.py` — deterministic parameter sweep (no random sampling)
**Format:** 3-column CSV — time (min), depth (m), velocity (m/s)

---

## 1. Purpose

Ingress simulations need time-varying exterior water depth (and optionally
velocity) at the building face.  Instead of one representative event, the
dataset sweeps the parameters that control hydrograph shape — peak depth,
time to peak, rising-limb shape and recession length — on a regular grid, so
batch runs (`batch.py --depth-dir hydrographs/generated`) cover the whole
parameter space and results can be read as response surfaces.

---

## 2. Parameter Grid

The case list is the Cartesian product of four grids (constants at the top of
`generate.py`):

| Parameter | Symbol | Values | Count |
|---|---|---|---|
| Peak depth | *h*_peak | 0.01, 0.15, 0.30, 0.45, 0.60, 0.90, 1.20, 1.50, 1.80, 2.10, 2.40 m | 11 |
| Time to peak | *T*_p | 60, 480, 960 min | 3 |
| Rising-limb shape | α | 1.5, 2.5, 4.0 | 3 |
| Recession ratio | *r* = *T*_rec / *T*_p | 1.5, 2.5, 4.0 | 3 |

11 × 3 × 3 × 3 = **297 cases**.  Cases are numbered in product order with
*h*_peak varying slowest and *r* fastest: case 1 is
(0.01 m, 60 min, 1.5, 1.5), case 2 is (0.01 m, 60 min, 1.5, 2.5), …,
case 297 is (2.40 m, 960 min, 4.0, 4.0).  `metadata.csv` lists
`case, h_peak, t_peak, alpha, recession_ratio, n_steps` for every case.

All cases use a fixed timestep of **1 min**.

---

## 3. Depth Hydrograph Shape

### 3.1 Rising Limb

The rising limb uses a **gamma-type analytical form** that is zero at *t* = 0,
strictly increasing, and reaches *h*_peak at *t* = *T*_p by construction:

$$h(t) = h_\text{peak} \cdot \left(\frac{t}{T_p}\right)^\alpha \cdot \exp\!\left[\alpha\!\left(1 - \frac{t}{T_p}\right)\right], \quad 0 \le t \le T_p$$

With τ = *t* / *T*_p,

$$\frac{dh}{dt} = h_\text{peak} \cdot \frac{\alpha}{T_p} \cdot \tau^{\alpha-1} \cdot e^{\alpha(1-\tau)} \cdot (1-\tau) = 0 \iff \tau = 1 \; (t = T_p)$$

This is a normalised **Pearson Type III (gamma)** shape, as used for unit
hydrograph derivation (Chow, Maidment & Mays, 1988).  Larger α gives a
slower start and a steeper approach to the peak.

### 3.2 Recession Limb

The recession is a **single-store exponential decay** (Maillet, 1905):

$$h(t) = h_\text{peak} \cdot \exp\!\bigl[-k\,(t - T_p)\bigr], \quad t > T_p$$

with *k* chosen so that *h* falls to 1 % of *h*_peak after the recession
duration *T*_rec = *r* · *T*_p:

$$k = \frac{\ln 100}{r \cdot T_p}$$

### 3.3 Series Length

Each series runs from *t* = 0 to *T*_p + *T*_rec + 3 min in 1-min steps;
depths are rounded to 0.1 mm.  A final point at depth 0 is appended 5 min
after the last step so that every event ends dry.

---

## 4. Velocity

Velocity is derived from depth at every timestep with a fixed power law (no
independent shaping or time lead):

$$v(t) = a \cdot h(t)^{b}, \qquad a = 1.5\ \text{m}^{1-b}/\text{s},\; b = 0.5$$

(`VEL_A`, `VEL_B` in `generate.py`).  The third column is used by the
simulation only with `--velocity-mode file`; with `--velocity-mode power_law`
the simulation computes the same relation itself from
`--velocity-power-law-a/-b` (defaults 1.5 and 0.5).

---

## 5. Limitations

1. **Single-peak events only.**  Compound events (multiple peaks, rainfall
   bursts separated by dry periods) are not represented.
2. **Grid, not a probability sample.**  Cases are equally weighted points of
   a sweep; they carry no information on how frequent each event is.  Any
   probabilistic use needs weights from a hazard model.
3. **Velocity is a deterministic function of depth.**  Backwater, tidal and
   unsteady-flow effects (e.g. velocity leading depth in flash floods) are
   not represented.
4. **No spatial variability.**  Each case is a single time series assumed
   uniform over the façade, consistent with the zero-dimensional ingress
   model it drives.

---

## 6. Usage

### 6.1 File Format

```
# case 0212  h_peak=1.50 m  t_peak=960 min  alpha=2.5  rec_ratio=2.5
# time (min), depth (m), velocity (m/s)
0.0,0.0,0.0
1.0,0.0,0.0
...
```

Time is in **minutes**, depth in **metres above external ground level**
(*h*_out in the simulation model), velocity in **m/s**.  Lines starting with
`#` are ignored by the parser.

### 6.2 Single Case

```bash
python3 cli.py \
  --external hydrographs/generated/0212.csv \
  --ingress  path/to/ingress.csv \
  --floor 50 --dt 1 --time-units minutes \
  --velocity-mode file \
  --outdir results/case_0212
```

### 6.3 All Cases

```bash
python3 batch.py \
  --depth-dir hydrographs/generated \
  --ingress   path/to/ingress.csv \
  --floor 50 --dt 1 --time-units minutes \
  --velocity-mode file \
  --outdir results/batch
```

A subset can be selected with `--hydrograph-files`, e.g.
`--hydrograph-files "hydrographs/generated/02[0-9][0-9]\.csv"`.

### 6.4 Streamlit App

Upload any `NNNN.csv` as the hydrograph, set *Time unit = minutes* and a
timestep of 1 min, and choose velocity mode *File* to use the third column.
`metadata.csv` helps pick representative or extreme cases.

### 6.5 Regenerating the Dataset

```bash
python3 hydrographs/generate.py
```

This rewrites all case files in `hydrographs/generated/` and `metadata.csv`.
Edit the grids or `VEL_A`/`VEL_B` at the top of `generate.py` to change
coverage, resolution or the velocity law.

---

## 7. References

- Chow, V.T., Maidment, D.R. & Mays, L.W. (1988). *Applied Hydrology*.
  McGraw-Hill, New York.
- Maillet, E. (1905). *Essais d'hydraulique souterraine et fluviale*.
  Hermann, Paris.
