# Fragility Example

This example demonstrates three fragility-enabled component patterns:

- `flood_door`: a one-state probabilistic ingress path
- `garage_door`: a two-state probabilistic ingress path
- `group_id = 1`: a membrane-protected set of deterministic paths

Files:

- `example_fragility_ingress_paths.csv`
- `example_fragility_membrane.csv`
- `example_external_levels.csv`

Suggested run:

```bash
python3 main.py \
  --external example_run/example_external_levels.csv \
  --ingress example_run/example_fragility_ingress_paths.csv \
  --membrane-file example_run/example_fragility_membrane.csv \
  --ingress-format fragility \
  --n-replicates 100 \
  --random-seed 42 \
  --outdir example_run/fragility_example_output
```

Notes:

- The fragility path is only activated in the CLI when `--n-replicates` is greater than `1`.
- Basement fragility is configured through CLI arguments, not through the ingress CSV.
