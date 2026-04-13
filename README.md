# waterIngressBuilding
![CI](https://github.com/robgen/waterIngressBuilding/actions/workflows/ci.yml/badge.svg)
Models the ingress of flood water in a building with a simplified hydraulic strategy.

Quick links
- Docs: ./docs/
	- Inputs reference: ./docs/README_INPUTS.md
	- Technical description: ./docs/TECHNICAL.md
	- Changelog: ./CHANGELOG.md

Getting started
1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the classic headless example and create the GIF:

```bash
python3 main.py \
  --external example_run/example_external_levels.csv \
  --ingress example_run/example_ingress_paths.txt \
  --outdir example_run \
  --animate \
  --anim-out simulation_animation.gif
```

This writes the classic example outputs into `example_run/`, including
`simulation_animation.gif`, `simulation_result.png`, and the ingress/external
preview plots.

Note: the project default time unit is minutes. Use `--time-units` to override
(choices: seconds, minutes, hours). If you want a temporary run that doesn't
leave files behind, use `--temp-output` to write outputs to a temporary
directory that is removed when the run completes.

If you are looking at `example_run/run_example.py`, note that it currently
contains several alternative example blocks and a batch-style Example E. The
explicit `main.py` command above is the canonical way to reproduce the classic
single-run GIF example.

4. Run the web UI (Streamlit):

```bash
streamlit run streamlit_app.py
```

Running tests

There is a small test suite under `tests/`. You can run it with pytest or the included lightweight runner:

```bash
# with pytest (recommended)
pytest -q

# or without pytest installed
python3 tests/run_tests.py
```

Notes

- The authoritative simulation and parsers are in `main.py`.
- Headless plotting/animation helpers are in `viz.py` and use the Agg backend.
- The legacy Tk GUI has been retired in favor of `streamlit_app.py`.
