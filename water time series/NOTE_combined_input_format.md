# Note: Combined Depth + Velocity Input Format

**Status:** planned / not yet implemented
**Scope:** data format, CLI, Streamlit app, parsing layer

---

## Motivation

Depth and velocity describe the same flow state at the same instant.
Keeping them in separate files creates pairing risks and diverges from how
real monitoring data is delivered (EA Hydrology API, USGS NWIS, etc.).
A single combined file per event is physically cleaner and simpler to use.

---

## Proposed File Format

Three-column CSV, same comment-header convention as existing files:

```
# time (min), depth (m), velocity (m/s)   ← third column is optional
0,0.00,0.20
15,0.12,0.45
30,0.38,0.91
...
```

Rules:
- **Two-column files** (time, depth) remain valid — velocity falls back to
  the default constant value (`--external-velocity-default` / sidebar input).
- **Three-column files** supply both depth and velocity from the same source.
- Comment lines starting with `#` are ignored, as today.
- Time units follow the global `--time-units` setting (minutes by default).

---

## Required Code Changes

### 1. `main.py` — parser

Add a new function `parse_combined_file(filepath)` (and a matching
`parse_combined_text(text)` for the Streamlit path) that reads the file and
returns `(times, depths, velocities_or_None)`.

Replace the current separate calls to `parse_external_file` +
`parse_velocity_file` with a single call to `parse_combined_file` when the
combined format is detected (i.e. three data columns present).

Detection logic: read the first non-comment data line; if it has three
comma-separated fields, treat as combined; if two, treat as depth-only.

Keep `parse_external_file` and `parse_velocity_file` for backwards
compatibility with existing two-file workflows.

### 2. `main.py` — CLI

Add a new flag:

```
--external-combined <file>
```

that supersedes `--external` + `--external-velocity` when present.
Keep the two legacy flags working unchanged so existing scripts are not broken.

Priority order when multiple flags are supplied:
  1. `--external-combined` (combined file, highest priority)
  2. `--external` + optionally `--external-velocity` (legacy, still supported)

### 3. `streamlit_app.py` — sidebar

Replace the current two separate uploaders:

```
Upload external levels CSV (time, level)
Upload velocity CSV (time, velocity m/s)
```

with a single uploader:

```
Upload hydrograph CSV  (time, depth  —  or  time, depth, velocity)
```

On upload, attempt to parse as combined; if three columns are detected,
populate both depth and velocity; if two columns, populate depth only and
show the velocity default input as before.

Remove the `manual_velocity` checkbox (manual entry of velocity stays
available as a fallback when only two columns are uploaded).

### 4. `water time series/generate.py`

Regenerate the dataset in the combined format:
- One file per case instead of two: `case_001.csv` … `case_100.csv`
  stored directly in `water time series/` (or a subfolder `cases/`).
- Three columns: time (min), depth (m), velocity (m/s).
- Retire the `depth/` and `velocity/` subdirectories.

Update `metadata.csv` column `files` to point to the new single-file paths.

---

## Migration Notes

- Existing `depth_NNN.csv` / `velocity_NNN.csv` pairs remain valid inputs
  via the legacy `--external` + `--external-velocity` flags.
- Documentation in `HYDROGRAPH_GENERATION.md` should be updated to describe
  the combined format and mark the two-file layout as legacy.
- The TECHNICAL.md note on velocity input should be updated accordingly.
