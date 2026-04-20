# waterIngressBuilding
![CI](https://github.com/robgen/waterIngressBuilding/actions/workflows/ci.yml/badge.svg)

A building exposed to a flood accumulates water through discrete openings in its envelope: door gaps, airbricks, wall cracks, basement perimeter penetrations. This tool models that process using a simplified orifice hydraulic formulation. Each opening is treated as a submerged orifice whose flow rate depends on the head difference between the external flood and the interior. The building is represented as one or two well-mixed compartments — a ground floor and an optional basement — each with its own water balance. A sump-and-pump unit can be added to the basement to represent active drainage.

Beyond deterministic simulation, the tool supports probabilistic analysis of flood resilience measures (FRM) such as flood doors, airbrick covers, and perimeter skirts. Each pathway can be assigned a lognormal fragility function capturing uncertainty in the measure's performance at a given flood depth. A Monte Carlo wrapper samples capacity thresholds before each replicate and reports percentile distributions and state frequencies directly usable in flood risk assessments.

---

## Documentation

| Document | Contents |
|----------|----------|
| [docs/model.md](docs/model.md) | Compartment architecture, orifice model, sump/pump equations, numerical scheme, forces, code architecture |
| [docs/fragility.md](docs/fragility.md) | Probabilistic fragility framework, calibration guide (BS 8511) |
| [docs/reference.md](docs/reference.md) | All input file formats, CLI flags, and output file specifications |
| [docs/limitations.md](docs/limitations.md) | Known limitations and resolved issues |
| [docs/datasets.md](docs/datasets.md) | Synthetic hydrograph dataset documentation |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Supported run modes

| Mode | Entry point | Description |
|------|-------------|-------------|
| Deterministic, single hydrograph | `cli.py` | One flood event; all pathway conductances fixed |
| + basement | `cli.py` | Adds a basement compartment with its own water balance, fed by a separate perimeter opening |
| + sump/pump | `cli.py` | Adds a sump chamber and pump that intercept basement inflow; the pump curve governs when the sump overflows into the basement |
| Fragility (Monte Carlo) | `cli.py` | Samples lognormal pathway capacities and runs N replicates; produces percentile distributions and state frequency tables |
| Batch | `batch.py` | Runs any of the above for every hydrograph in a folder and aggregates results |

Fragility and batch are orthogonal: providing both `--n-replicates` and `--depth-dir` runs full Monte Carlo for every hydrograph in the batch.

---

## Getting started

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py          # web UI
```

---

## Examples

### Mode 1 — Deterministic, single hydrograph

```bash
python3 cli.py \
  --external hydro.csv \
  --ingress  ingress.csv \
  --floor    50 \
  --dt       1 \
  --outdir   out/
```

### Mode 2 — With basement

```bash
python3 cli.py \
  --external                 hydro.csv \
  --ingress                  ingress.csv \
  --basement-opening         basement_opening.csv \
  --basement-area            30 \
  --basement-floor-elevation -2.5 \
  --floor                    50 \
  --outdir                   out/
```

### Mode 3 — With basement and sump/pump

All sump and pump parameters share the `--sumppump-` prefix.

```bash
python3 cli.py \
  --external                  hydro.csv \
  --ingress                   ingress.csv \
  --basement-opening          basement_opening.csv \
  --basement-area             30 \
  --basement-floor-elevation  -2.5 \
  --floor                     50 \
  --sumppump-area             0.5 \
  --sumppump-base-elevation   -2.5 \
  --sumppump-overflow-level   0.8 \
  --sumppump-overflow-coeff   1.8 \
  --sumppump-on-level         0.10 \
  --sumppump-off-level        0.02 \
  --sumppump-shutoff-head     5.0 \
  --sumppump-curve-coeff      1000 \
  --outdir                    out/
```

### Mode 4 — Fragility (Monte Carlo)

Any pathway in `ingress.csv` that contains fragility state columns is treated probabilistically.

```bash
python3 cli.py \
  --external     hydro.csv \
  --ingress      ingress.csv \
  --floor        50 \
  --n-replicates 500 \
  --random-seed  42 \
  --outdir       out/
```

### Mode 5 — Batch

```bash
# Deterministic batch
python3 batch.py \
  --depth-dir  hydrographs/depth \
  --ingress    ingress.csv \
  --floor      50 \
  --outdir     out/

# Batch + fragility
python3 batch.py \
  --depth-dir    hydrographs/depth \
  --ingress      ingress.csv \
  --floor        50 \
  --n-replicates 200 \
  --outdir       out/
```

---

## Outputs

Written to `--outdir`. See [docs/reference.md](docs/reference.md) for full column-level documentation.

| File | Produced by |
|------|-------------|
| `simulation_result.png` | All single-run modes |
| `simulation_animation.gif` | Single-run + `--animate` |
| `batch_results.csv`, `batch_summary.csv` | Batch |
| `fragility_replicates.csv`, `fragility_summary.csv`, `fragility_state_freq.csv` | Fragility |
| `mc_result.png` | Fragility |
| `forces.csv`, `forces_result.png` | `--compute-forces` |

---

## Validation case studies

Twelve cases of increasing complexity, from a single-opening ground-floor model to batch + fragility, are defined in `case_studies/run_cases.py`.

```bash
python3 case_studies/run_cases.py
```

Outputs go to `case_studies/exNN/out/`. Reference metrics for regression testing are in `case_studies/reference/`. See [case_studies/report.md](case_studies/report.md) for documented expectations and results.

---

## Tests

```bash
pytest -q          # recommended
python3 tests/run_tests.py   # without pytest
```

`tests/test_regression.py` reproduces all validation cases and compares peak metrics against reference values in `case_studies/reference/`. Any implementation change that shifts results is caught here (tolerance: 1 % on peak depths, 5 % on volumes).

---

## Roadmap

- **Streamlit batch tab**: `batch.py` produces summary CSVs but the web UI (`app.py`) cannot yet run a batch or inspect individual case time series.
- **Semi-implicit timestepping**: replace explicit Euler with a semi-implicit sump/pump update to allow larger stable timesteps.
- **Multiple compartments**: generalise the compartment graph for multi-storey or split-level buildings.
- **Parametric sweep tool**: dedicated entry point for iterating over `SimConfig` parameter grids (contrast with batch, which iterates over hydrographs).
