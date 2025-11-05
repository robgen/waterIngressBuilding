# Example input files for Flood Ingress Simulation

This document describes the example input files used by the project and how to format your own inputs.

Files (examples in `example_run/`):

- `example_external_levels.csv` — External water level data. Each line is: `time,level` (both floats). Time units are consistent with the simulation. NOTE: the project default time unit is now minutes and the examples below use minutes.

  Example (times in minutes):

  0,0.0
  1,0.2
  2,0.5

- `example_ingress_paths.txt` — Ingress pathways. Each line is: `height, area, coeff[,name]` (comma-separated). The optional fourth column is a textual name for the ingress.

  Example lines:

  0.0, 0.01, 0.6, wall_crack
  0.3, 0.002, 0.6, airbrick

Parsing notes

- Lines starting with `#` or blank lines are ignored.
- Non-numeric or malformed lines are skipped.
- For ingress entries, the parser will use a generated name if none is provided.

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
- `--basement-connection-height FLOAT` — sill elevation (m, same datum) of the connection between ground-floor and basement (for example `0.0` for a hatch at ground-floor level).
- `--basement-connection-area FLOAT` — cross-sectional area (m^2) of the vertical/through-connection used to compute flow between ground and basement.
- `--basement-ceiling-elevation FLOAT` — optional ceiling elevation (m, same datum). This caps the maximum basement water surface elevation; overflow beyond this elevation is spilled back to the ground-floor compartment in the current implementation.

Notes and conventions for basements

- All basement elevations and sill heights use the same datum as other ingress pathway sill heights and the internal ground-floor level. The simulator converts depths to absolute elevations internally using `H = z + h`.
- A basement floor below the datum should be given as a negative value (for example `--basement-floor-elevation -2.5`).
- The submerged test for an opening uses absolute elevations: flow is only computed when the opening is submerged (i.e., when the maximum of the two connected water surfaces exceeds the sill elevation). This means a basement can retain water after external or ground-floor levels fall below the sill height.
- If you do not provide basement options the simulator will run without a basement compartment.

Example CLI (run from project root):

```bash
python3 main.py --external example_run/example_external_levels.csv \
  --ingress example_run/example_ingress_paths.txt \
  --dt 1.0 --basement-area 40.0 --basement-floor-elevation -2.5 \
  --basement-connection-height 0.0 --basement-connection-area 0.001
```

