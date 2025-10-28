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
