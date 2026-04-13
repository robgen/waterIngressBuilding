# Example input files for Flood Ingress Simulation

This document describes the example input files used by the project and how to format your own inputs.

Files (examples in `example_run/`):

- `example_external_levels.csv` — External water level data. Each line is: `time,level` (both floats). Time units are consistent with the simulation. NOTE: the project default time unit is now minutes and the examples below use minutes.

  Example (times in minutes):

  0,0.0
  1,0.2
  2,0.5

- `example_ingress_paths.txt` — Ingress pathways. Each line is:
  - `height, area, coeff[,name]`

  These pathways represent exterior-to-main-building ingress only.

  Example lines:

  0.0, 0.01, 0.6, wall_crack
  0.3, 0.002, 0.6, airbrick
  0.0, 0.0005, 0.5, service_penetration

Parsing notes

- Lines starting with `#` or blank lines are ignored.
- Non-numeric or malformed lines are skipped.
- For ingress entries, the parser will use a generated name if none is provided.
- Extra columns are intentionally not supported in the public ingress-file format and will raise an error.
- Legacy 5th-column `always_open` values are no longer supported.

Units and conventions

- Times: same units throughout the hydrograph and the simulation timestep. The default unit for the CLI and Streamlit UI is minutes; you can override with the CLI flag `--time-units` (choices: seconds, minutes, hours).
- Areas: square metres (m^2).
- Heights/levels: metres (m).
- Coefficient: empirical discharge coefficient (dimensionless).

Tips

- Provide the external hydrograph at the sampling rate you have; the simulation accepts any hydrograph timestamps and will interpolate the external level to the simulation time grid.
- Choose a simulation timestep (`--dt` or the Streamlit UI field) appropriate to the dynamics you want to capture — smaller dt improves accuracy at the cost of runtime.

## Basement-related inputs

If you use the basement compartment in the simulator (see CLI flags in `main.py`), the following command-line options control basement geometry and its connection to the ground-floor:

- `--basement-area FLOAT` — basement plan area in m^2 (required when enabling a basement). This is used to convert basement volume to depth.
- `--basement-floor-elevation FLOAT` — elevation of the basement floor relative to the internal ground-floor datum (m). Use negative values for floors below the ground-floor level (e.g. `-2.5`).
- `--basement-ingress-height FLOAT` — sill elevation (m, same datum) of the lumped exterior-to-basement opening representing perimeter/below-ground ingress.
- `--basement-ingress-area FLOAT` — area (m^2) of the lumped exterior-to-basement opening.
- `--basement-ingress-coeff FLOAT` — discharge coefficient of the lumped exterior-to-basement opening.
- `--basement-connection-height FLOAT` — sill elevation (m, same datum) of the connection between ground-floor and basement (for example `0.0` for a hatch at ground-floor level).
- `--basement-connection-area FLOAT` — cross-sectional area (m^2) of the vertical/through-connection used to compute flow between ground and basement.
- `--basement-ceiling-elevation FLOAT` — optional ceiling elevation (m, same datum). This caps the maximum basement water surface elevation; overflow beyond this elevation is spilled back to the ground-floor compartment in the current implementation.

Notes and conventions for basements

- All basement elevations and sill heights use the same datum as other ingress pathway sill heights and the internal ground-floor level. The simulator converts depths to absolute elevations internally using `H = z + h`.
- A basement floor below the datum should be given as a negative value (for example `--basement-floor-elevation -2.5`).
- The ingress file remains reserved for exterior-to-main-building pathways. Basement perimeter ingress is configured separately through the lumped `--basement-ingress-*` inputs.
- The lumped exterior-to-basement opening represents perimeter/below-ground inflow to the basement system.
- The submerged test for an opening uses absolute elevations: flow is only computed when the opening is submerged (i.e., when the maximum of the two connected water surfaces exceeds the sill elevation). This means a basement can retain water after external or ground-floor levels fall below the sill height.
- If you do not provide basement options the simulator will run without a basement compartment.
- `--basement-connection-*` remains the bypass between the main building and the basement; it does not pass through the sump.

Example CLI (run from project root):

```bash
python3 main.py --external example_run/example_external_levels.csv \
  --ingress example_run/example_ingress_paths.txt \
  --dt 1.0 --basement-area 40.0 --basement-floor-elevation -2.5 \
  --basement-ingress-height 0.0 --basement-ingress-area 0.003 --basement-ingress-coeff 0.6 \
  --basement-connection-height 0.0 --basement-connection-area 0.001
```

## External velocity-related inputs

The simulator accepts an optional external velocity hydrograph to account for hydrodynamic effects on ingress and to support time-series estimates of lateral forces on the flow-facing façade.

- `--external-velocity PATH` — CSV file containing `time,velocity` rows (velocity in m/s). Times use the same time units as the external level hydrograph. If omitted a conservative default velocity is used (see `--external-velocity-default`).
- `--external-velocity-default FLOAT` — default constant velocity (m/s) used when no velocity hydrograph is provided. The project default is 0.2 (m/s).

Units and conventions

- Velocity: metres per second (m/s). The external velocity is assumed orthogonal to the flow-facing building wall for the purpose of drag calculations.
- When a velocity hydrograph is supplied it is linearly interpolated to the simulation time grid and padded with zeros beyond its last timestamp by default (short hydrographs behave as if velocity falls to zero after the last sample).

## Sump and pump inputs

The sump extension adds a third chamber with a pump that removes water from the sump only.

- `--sump-area FLOAT` — sump plan area in m^2. If `>0`, the sump+pump model is enabled.
- `--sump-base-elevation FLOAT` — sump base / pump datum elevation on the shared datum (m).
- `--sump-overflow-level FLOAT` — overflow crest elevation above the sump base (m).
- `--sump-overflow-coeff FLOAT` — overflow coefficient `C_ov`.
- `--sump-overflow-exponent FLOAT` — overflow exponent `m_ov` (default `1.5`).
- `--pump-on-level FLOAT` — sump depth above the sump base at which the pump switches on.
- `--pump-off-level FLOAT` — sump depth above the sump base at which the pump switches off.
- `--pump-shutoff-head FLOAT` — shut-off head `H_shut` for the pump curve.
- `--pump-curve-coeff FLOAT` — pump-curve coefficient `k_pump`.
- `--pipe-loss-coeff FLOAT` — pipe-loss coefficient `k_pipe`.
- `--pump-availability FLOAT` — placeholder availability factor `eta_p` (default `1.0`).

Notes and conventions for sump runs

- In the public CLI and UI, the sump is treated as a basement add-on and should be configured together with a basement.
- The pump lift head is derived internally from the external hydraulic head and `--sump-base-elevation`.
- When a sump is enabled, the lumped exterior-to-basement opening configured by `--basement-ingress-*` is intercepted by the sump first instead of feeding the basement directly.
- The building↔basement bypass configured by `--basement-connection-*` still feeds the basement directly and does not go through the sump.
- The solver uses the same global `--dt` for the sump, pump, and other chambers. Smaller `--dt` values are recommended when pump switching or sump overflow thresholds are important.
- Internal hydraulic substeps are not implemented in this release. They remain a possible future enhancement if sharper threshold handling is needed.

## Force-related inputs

This simulator provides steady hydrostatic and steady drag (hydrodynamic) estimates. It does not model impulsive or wave slam loads. For impulsive/wave impact design and assessment users can apply safety factors or consult standards like FEMA P-55 and ASCE 7 which account for wave impact and sloshing.

- `--building-width FLOAT` — building width (m). This is the horizontal extent of the flow-facing façade used when computing analytical lateral forces (see `docs/TECHNICAL.md`). The term used is "building width" (not "wall width").
- `--drag-coeff FLOAT` — optional drag coefficient C_D (dimensionless). Default conservative value is 1.0.
- `--rho FLOAT` — fluid density in kg/m^3 (default 1000).

## Contents vulnerability inputs

The batch runner can optionally convert each simulated peak interior water depth into a simple aggregate loss estimate by interpolating a vulnerability curve.

- `--contents-vulnerability PATH` — CSV file containing at least `height_m` and a loss column. The default loss column used by `batch_run.py` is `mean_repair_loss_GBP`.
- `--contents-loss-column NAME` — optional column name to interpolate instead of `mean_repair_loss_GBP`.

Behaviour

- The batch run uses the simulated `h_peak_int` for each case, linearly interpolates the vulnerability curve, and writes the result to `aggregate_loss_GBP` in `batch_results.csv`.
- When a vulnerability curve is supplied, the batch runner also writes `peak_exterior_vs_aggregate_loss.png` to the batch output directory.

Example CLI

```bash
python3 batch_run.py \
  --depth-dir "water time series/depth" \
  --velocity-dir "water time series/velocity" \
  --ingress example_run/uk_terraced_house_ingress_paths.txt \
  --contents-vulnerability example_run/uk_contents_vulnerability.csv \
  --outdir batch_results/uk_terraced_house_unprotected_loss
```


