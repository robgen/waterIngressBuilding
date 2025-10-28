# Changelog

All notable changes to this project are documented in this file.

## [2025-10-28]

- Added Streamlit-based web UI: `streamlit_app.py` (replaces legacy Tk GUI).
- Added headless plotting/animation helpers in `viz.py` (Agg backend).
- Exposed user-controlled simulation timestep (`--dt` and Streamlit input).
- Added ingress name support in input format (optional 4th column).
- Implemented ingress-locations plotting and improved labels to reduce overlap.
- Added tests (`tests/test_simulation.py`) and a lightweight runner (`tests/run_tests.py`).
- Added GitHub Actions CI workflow (`.github/workflows/ci.yml`).
- Added documentation under `docs/` with input reference and a technical description.
- Initial refactor and feature additions during interactive session: parsing fixes, GUI refactor, animation support, example inputs in `example_run/`.

- Default time unit changed to minutes (CLI `--time-units`, Streamlit defaults to minutes). Default timestep when omitted is now 1 (in selected units) — i.e. 1 minute by default.
- Added `--temp-output` CLI flag to write outputs to a temporary directory that is removed on exit (useful for tests and smoke runs).
- Streamlit UI: ingress locations plot is shown in the uploader preview (better visual feedback); the app no longer uses deprecated Streamlit parameters and displays animated GIFs inline.
- Streamlit run output now shows only the final simulation result PNG (and optionally the animation) after executing the simulation, reducing UI clutter.
