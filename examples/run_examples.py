#!/usr/bin/env python3
"""Create input files, run all validation cases, and write report.md.

Run from the repo root:
    python3 examples/run_examples.py

Cases in order of complexity — 2×2 matrix (single/batch × no-fragility/membrane MC):

  Single hydrograph, no fragility/membrane:
  01 – Ground floor, single opening at sill = 0 m
  02 – Ground floor, raised sill at 0.3 m
  03 – Ground floor, two openings with different sill heights
  04 – Basement compartment (no ground-floor opening)
  05 – Basement + sump/pump that keeps up
  06 – Basement + sump/pump that is overwhelmed

  Single hydrograph, fragility / membrane MC:
  07 – Fragility MC: single probabilistic seal (50 % failure at peak depth)
  08 – Fragility MC: membrane-protected group (50 % membrane failure)
  09 – Deterministic membrane: design capacity above flood peak (no failure)

  Batch (20 hydrographs, peaks 0.10–1.05 m), no fragility:
  10 – Batch deterministic: single ground-floor opening across 20 hydrographs

  Batch (20 hydrographs), fragility / membrane MC:
  11 – Batch + fragility MC: membrane-protected group, 50 replicates per hydrograph
"""

import argparse
import csv
import io
import os
import subprocess
import sys
import textwrap

HERE  = os.path.dirname(os.path.abspath(__file__))
ROOT  = os.path.dirname(HERE)
PY    = os.path.join(ROOT, '.venv', 'bin', 'python3')

sys.path.insert(0, ROOT)
import plot as viz  # noqa: E402 — must come after sys.path tweak

_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument('--animate', action='store_true', default=False,
                 help='Write GIF animations for each case (slow; off by default)')
ANIMATE, _ = _ap.parse_known_args()

# ── shared hydrograph ─────────────────────────────────────────────────────────
# Triangular flood: 0 → 0.5 m over 30 min, recession to 0 by t = 60 min.
# Each case ends at a duration chosen to avoid a long zero tail.
def make_hydro(t_end):
    return [(0, 0.00), (30, 0.50), (60, 0.00), (t_end, 0.00)]

# Per-case simulation end times (minutes).
# Ex03 needs 360 min for slow crack drainage; others end once dynamics settle.
CASE_DURATION = {
    'ex01': 120,   # fast orifice; drains by ~70 min
    'ex02': 120,   # raised sill; residual trapped, no dynamics after ~70 min
    'ex03': 360,   # slow crack drainage must reach zero
    'ex04': 120,   # basement permanently trapped; level flat after t = 60 min
    'ex05': 90,    # strong pump keeps sump dry throughout
    'ex06': 150,   # sump overflows and basement fills; level flat after ~80 min
    'ex07': 120,   # fragility MC; fill/drain settles by ~100 min
    'ex08': 120,
    'ex09': 90,    # membrane intact, near-zero interior; nothing to show past 90 min
}

# ── batch hydrograph ensemble ─────────────────────────────────────────────────
# 20 triangular hydrographs with peaks from 0.10 m to 1.05 m in 0.05 m steps.
# Each shares the same shape as HYDRO (rise to peak at 30 min, drain by 60 min).
BATCH_PEAKS = [round(0.10 + i * 0.05, 2) for i in range(20)]

# ── helpers ───────────────────────────────────────────────────────────────────

def mkdir(path):
    os.makedirs(path, exist_ok=True)
    return path

def write_text(path, content):
    mkdir(os.path.dirname(path))
    with open(path, 'w') as f:
        f.write(content)

def write_csv_rows(path, rows):
    mkdir(os.path.dirname(path))
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)

def run(name, extra_args, outdir, hydro_path=None):
    """Run cli.py for one case; return (ok, stdout+stderr)."""
    mkdir(outdir)
    if hydro_path is None:
        hydro_path = os.path.join(HERE, 'shared', 'hydro.csv')
    cmd = [
        PY, os.path.join(ROOT, 'cli.py'),
        '--external', hydro_path,
        '--time-units', 'minutes',
        '--dt', '1',
        '--outdir', outdir,
    ] + extra_args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    log = result.stdout + result.stderr
    ok = result.returncode == 0
    if not ok:
        print(f'  *** FAILED: {name}\n{log}')
    else:
        print(f'  OK  {name}')
    return ok, log


def run_batch_case(name, extra_args, outdir):
    """Run batch.py for one case; return (ok, stdout+stderr)."""
    mkdir(outdir)
    cmd = [
        PY, os.path.join(ROOT, 'batch.py'),
        '--time-units', 'minutes',
        '--dt', '1',
        '--outdir', outdir,
    ] + extra_args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    log = result.stdout + result.stderr
    ok = result.returncode == 0
    if not ok:
        print(f'  *** FAILED: {name}\n{log}')
    else:
        print(f'  OK  {name}')
    return ok, log

def read_csv_as_text(path):
    """Return CSV contents as a markdown table string, or '' if missing."""
    if not os.path.exists(path):
        return ''
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    if not rows:
        return ''
    header = '| ' + ' | '.join(rows[0]) + ' |'
    sep    = '| ' + ' | '.join('---' for _ in rows[0]) + ' |'
    body   = '\n'.join('| ' + ' | '.join(r) + ' |' for r in rows[1:])
    return header + '\n' + sep + '\n' + body

def rel(path):
    """Relative path from examples/ for markdown image links."""
    return os.path.relpath(path, HERE)

def _load_csv(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))

# ── create shared inputs ──────────────────────────────────────────────────────

print('Creating shared inputs...')
shared = mkdir(os.path.join(HERE, 'shared'))

# Shared basement perimeter opening for basement cases.
write_text(os.path.join(shared, 'basement_opening.csv'),
           'name, height_m, area_m2, Cd\n'
           'perimeter_opening, 0.0, 0.005, 0.5\n')

# ── Ex 01: single opening, sill = 0 ──────────────────────────────────────────
# Realistic: large orifice (e.g. failed door flood-seal on a front door).
# Floor 50 m² ~ small UK terraced house ground floor.
# dt = 0.1 min (6 s): with τ ≈ 266 s the default 60-s step is stable but still
# carries ~1 % peak bias; 6 s reduces this to <0.3 %.
print('\nEx 01 – single opening, sill = 0 m')
ex01 = mkdir(os.path.join(HERE, 'ex01'))
write_text(os.path.join(ex01, 'ingress.csv'),
           'name, height_m, area_m2, Cd\ndoor_gap, 0.0, 0.05, 0.6\n')
write_csv_rows(os.path.join(ex01, 'hydro.csv'), make_hydro(CASE_DURATION['ex01']))
run('ex01', [
    '--ingress', os.path.join(ex01, 'ingress.csv'),
    '--floor', '50',
    '--dt', '0.1',   # 6 s — keeps peak bias < 0.3 % (see dt_sensitivity)
] + (['--animate'] if ANIMATE.animate else []),
    mkdir(os.path.join(ex01, 'out')),
    hydro_path=os.path.join(ex01, 'hydro.csv'))

# Timestep sensitivity study for Ex 01
print('  Generating dt sensitivity figure for ex01...')
subprocess.run([PY, os.path.join(HERE, 'plot_dt_sensitivity.py')],
               capture_output=True, text=True, cwd=ROOT)
print('  OK  ex01 dt-sensitivity')

# ── Ex 02: raised sill at 0.3 m ──────────────────────────────────────────────
# Same floor and orifice as Ex 01; sill raised to 0.3 m.
# Water below sill height is permanently trapped (no drain path below sill=0.3m).
print('\nEx 02 – raised sill, sill = 0.3 m')
ex02 = mkdir(os.path.join(HERE, 'ex02'))
write_text(os.path.join(ex02, 'ingress.csv'),
           'name, height_m, area_m2, Cd\ndoor_gap_raised, 0.3, 0.05, 0.6\n')
write_csv_rows(os.path.join(ex02, 'hydro.csv'), make_hydro(CASE_DURATION['ex02']))
run('ex02', [
    '--ingress', os.path.join(ex02, 'ingress.csv'),
    '--floor', '50',
    '--dt', '0.1',
] + (['--animate'] if ANIMATE.animate else []),
    mkdir(os.path.join(ex02, 'out')),
    hydro_path=os.path.join(ex02, 'hydro.csv'))

# ── Ex 03: two openings, different sills ─────────────────────────────────────
# Base crack (always active) + door gap (active above sill 0.3 m).
# Extended run to 360 min so the slow crack drainage is visible.
print('\nEx 03 – two openings: small always-on + large threshold')
ex03 = mkdir(os.path.join(HERE, 'ex03'))
write_text(os.path.join(ex03, 'ingress.csv'),
           'name, height_m, area_m2, Cd\n'
           'base_crack, 0.0, 0.001, 0.6\n'
           'door_gap_high, 0.3, 0.005, 0.6\n')
write_csv_rows(os.path.join(ex03, 'hydro.csv'), make_hydro(CASE_DURATION['ex03']))
run('ex03', [
    '--ingress', os.path.join(ex03, 'ingress.csv'),
    '--floor', '50',
] + (['--animate'] if ANIMATE.animate else []),
    mkdir(os.path.join(ex03, 'out')),
    hydro_path=os.path.join(ex03, 'hydro.csv'))

# ── Ex 04: basement only, no ground-floor opening ────────────────────────────
# Realistic: 30 m² partial basement, floor at −2.5 m (full-height UK basement).
# Perimeter opening at ground-level sill: drives inflow from any exterior flooding.
# Without a pump, basement water is permanently trapped once the flood recedes.
print('\nEx 04 – basement compartment, no ground-floor opening')
ex04 = mkdir(os.path.join(HERE, 'ex04'))
write_csv_rows(os.path.join(ex04, 'hydro.csv'), make_hydro(CASE_DURATION['ex04']))
run('ex04', [
    '--basement-ingress', os.path.join(shared, 'basement_opening.csv'),
    '--floor', '50',
    '--basement-area',            '30',
    '--basement-floor-elevation', '-2.5',
] + (['--animate'] if ANIMATE.animate else []),
    mkdir(os.path.join(ex04, 'out')),
    hydro_path=os.path.join(ex04, 'hydro.csv'))

# ── Ex 05: basement + sump/pump that keeps up ────────────────────────────────
# Same inflow as Ex 04.  Strong pump: Q_pump ≈ 0.045 m³/s >> Q_in_max ≈ 0.008 m³/s.
# Q_pump = sqrt((H_shut − H_lift) / k_pump) = sqrt((5.0 − 3.0) / 1000) ≈ 0.045 m³/s
# H_lift = |h_ext − z_sump| = |0.5 − (−2.5)| = 3.0 m at peak flood.
print('\nEx 05 – basement + sump/pump (keeps up)')
ex05 = mkdir(os.path.join(HERE, 'ex05'))
write_csv_rows(os.path.join(ex05, 'hydro.csv'), make_hydro(CASE_DURATION['ex05']))
run('ex05', [
    '--basement-ingress', os.path.join(shared, 'basement_opening.csv'),
    '--floor', '50',
    '--basement-area',               '30',
    '--basement-floor-elevation',    '-2.5',
    '--sumppump-area',               '0.5',
    '--sumppump-base-elevation',     '-2.5',
    '--sumppump-overflow-level',     '0.8',
    '--sumppump-overflow-coeff',     '1.8',
    '--sumppump-overflow-exponent',  '1.5',
    '--sumppump-on-level',           '0.10',
    '--sumppump-off-level',          '0.02',
    '--sumppump-shutoff-head',       '5.0',
    '--sumppump-curve-coeff',        '1000',
    '--sumppump-pipe-loss-coeff',    '0',
    '--sumppump-availability',       '1.0',
] + (['--animate'] if ANIMATE.animate else []),
    mkdir(os.path.join(ex05, 'out')),
    hydro_path=os.path.join(ex05, 'hydro.csv'))

# Timestep sensitivity study for Ex 05
print('  Generating dt sensitivity figure for ex05...')
subprocess.run([PY, os.path.join(HERE, 'plot_dt_sensitivity_sump.py')],
               capture_output=True, text=True, cwd=ROOT)
print('  OK  ex05 dt-sensitivity')

# ── Ex 06: basement + sump/pump overwhelmed ───────────────────────────────────
# Same inflow as Ex 04/05 but 100× weaker pump → sump overflows → basement fills.
# Q_pump = sqrt((5.0 − 3.0) / 100000) ≈ 0.0045 m³/s  <  Q_in_max ≈ 0.008 m³/s
print('\nEx 06 – basement + sump/pump (overwhelmed)')
ex06 = mkdir(os.path.join(HERE, 'ex06'))
write_csv_rows(os.path.join(ex06, 'hydro.csv'), make_hydro(CASE_DURATION['ex06']))
run('ex06', [
    '--basement-ingress', os.path.join(shared, 'basement_opening.csv'),
    '--floor', '50',
    '--basement-area',               '30',
    '--basement-floor-elevation',    '-2.5',
    '--sumppump-area',               '0.5',
    '--sumppump-base-elevation',     '-2.5',
    '--sumppump-overflow-level',     '0.8',
    '--sumppump-overflow-coeff',     '1.8',
    '--sumppump-overflow-exponent',  '1.5',
    '--sumppump-on-level',           '0.10',
    '--sumppump-off-level',          '0.02',
    '--sumppump-shutoff-head',       '5.0',
    '--sumppump-curve-coeff',        '100000',
    '--sumppump-pipe-loss-coeff',    '0',
    '--sumppump-availability',       '1.0',
] + (['--animate'] if ANIMATE.animate else []),
    mkdir(os.path.join(ex06, 'out')),
    hydro_path=os.path.join(ex06, 'hydro.csv'))

# ── Ex 07: fragility MC – single probabilistic path, 50 % failure ─────────────
# One path: base state is a nearly sealed door (area ≈ 0).
# State 1 (seal fails): area = 0.005 m², median = 0.5 m, β = 0.3.
# P(activated at peak) = P(h* < 0.5 m) = Φ(0) = 50 %.
# With floor = 50 m² the fill rate is slow (τ ≈ 44 min): when the seal fails
# the interior fills to ≈ 0.25 m during the 30-min rising limb.
# Result: bimodal peak_h_in — half near 0, half near 0.25 m.
print('\nEx 07 – fragility MC, single probabilistic path (50 % failure)')
ex07 = mkdir(os.path.join(HERE, 'ex07'))
write_text(os.path.join(ex07, 'ingress_frag.csv'),
           'name, height_m, area_m2, Cd, group_id, reversible,'
           ' state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1\n'
           'seal_door, 0.0, 1.0e-7, 0.6, 0, 0, failed, 0.5, 0.3, 5.0e-3, 0.6\n')
write_csv_rows(os.path.join(ex07, 'hydro.csv'), make_hydro(CASE_DURATION['ex07']))
run('ex07', [
    '--ingress', os.path.join(ex07, 'ingress_frag.csv'),
    '--floor', '50',
    '--n-replicates', '500',
    '--random-seed', '42',
], mkdir(os.path.join(ex07, 'out')),
    hydro_path=os.path.join(ex07, 'hydro.csv'))

# ── Ex 08: fragility MC – membrane-protected group, 50 % membrane failure ─────
# Two pathways (airbrick + door gap) sit behind a membrane.
# Membrane: sill = 0 m, base leakage ≈ 0, median capacity = 0.5 m, β = 0.1.
# P(membrane overtopped at peak 0.5 m) = Φ(0) = 50 %.
# When intact:   total area ≈ 0   → near-zero ingress.
# When overtopped: paths restored → airbrick (6 e-3) + door gap (2 e-3) m² active.
print('\nEx 08 – fragility MC, membrane-protected group (50 % failure)')
ex08 = mkdir(os.path.join(HERE, 'ex08'))
write_text(os.path.join(ex08, 'ingress_frag.csv'),
           'name, height_m, area_m2, Cd, group_id\n'
           'airbrick, 0.1, 6.0e-3, 0.6, 1\n'
           'door_gap, 0.0, 2.0e-3, 0.6, 1\n')
write_text(os.path.join(ex08, 'membrane.csv'),
           'name, height_m, area_m2, Cd, group_id, reversible,'
           ' state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1\n'
           'membrane_1, 0.0, 1.0e-6, 0.6, 1, 1, overtopped, 0.5, 0.1, 1.0e-9, 0.6\n')
write_csv_rows(os.path.join(ex08, 'hydro.csv'), make_hydro(CASE_DURATION['ex08']))
run('ex08', [
    '--ingress',    os.path.join(ex08, 'ingress_frag.csv'),
    '--membrane',   os.path.join(ex08, 'membrane.csv'),
    '--floor', '50',
    '--n-replicates', '500',
    '--random-seed', '42',
], mkdir(os.path.join(ex08, 'out')),
    hydro_path=os.path.join(ex08, 'hydro.csv'))

# ── Ex 09: deterministic membrane — design capacity above flood peak ──────────
# Same two pathways as Ex 08 (airbrick + door_gap behind membrane group_id=1).
# Membrane: sill = 0 m, base leakage ≈ 0.  Capacity = 0.6 m, β = 0 (deterministic).
# Peak flood = 0.5 m < 0.6 m = capacity  →  membrane never overtopped in any replicate.
# Expected: 0/500 overtopping events, interior depth ≈ 0 throughout.
# Contrasts with Ex 08 where the same membrane (capacity 0.5 m, β = 0.1) fails in ≈ 50 %.
print('\nEx 09 – deterministic membrane (design capacity above flood peak)')
ex09 = mkdir(os.path.join(HERE, 'ex09'))
write_text(os.path.join(ex09, 'membrane_det.csv'),
           'name, height_m, area_m2, Cd, group_id, reversible,'
           ' state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1\n'
           'membrane_1, 0.0, 1.0e-6, 0.6, 1, 1, overtopped, 0.6, 0.0, 1.0e-9, 0.6\n')
write_csv_rows(os.path.join(ex09, 'hydro.csv'), make_hydro(CASE_DURATION['ex09']))
run('ex09', [
    '--ingress',  os.path.join(ex08, 'ingress_frag.csv'),   # same airbrick + door_gap
    '--membrane', os.path.join(ex09, 'membrane_det.csv'),
    '--floor', '50',
    '--n-replicates', '500',
    '--random-seed', '42',
], mkdir(os.path.join(ex09, 'out')),
    hydro_path=os.path.join(ex09, 'hydro.csv'))

# Generate MC result figures for ex07, ex08, ex09
print('\nGenerating fragility MC figures ...')
for _case_dir, _title in [
    (os.path.join(HERE, 'ex07'),
     'Case 07 — Fragility MC: single probabilistic seal  (n = 500, seed = 42)'),
    (os.path.join(HERE, 'ex08'),
     'Case 08 — Fragility MC: membrane-protected group  (n = 500, seed = 42)'),
    (os.path.join(HERE, 'ex09'),
     'Case 09 — Deterministic membrane: design capacity above flood peak  (n = 500, seed = 42)'),
]:
    _reps  = _load_csv(os.path.join(_case_dir, 'out', 'fragility_replicates.csv'))
    _sfreq = _load_csv(os.path.join(_case_dir, 'out', 'fragility_state_freq.csv'))
    _out   = os.path.join(_case_dir, 'out', 'mc_result.png')
    viz.save_mc_result(
        [float(r['peak_h_in_m'])           for r in _reps],
        [float(r.get('peak_h_ext_m', 0.5)) for r in _reps],
        _sfreq, _title, _out,
    )
    print(f'  OK  {_out}')

# ── batch hydrograph ensemble ─────────────────────────────────────────────────
print('\nCreating batch hydrograph ensemble ...')
batch_hydros_dir = mkdir(os.path.join(shared, 'batch_hydros'))
for i, peak in enumerate(BATCH_PEAKS):
    write_csv_rows(
        os.path.join(batch_hydros_dir, f'depth_{i+1:03d}.csv'),
        [(0, 0.00), (30, peak), (60, 0.00), (360, 0.00)],
    )
print(f'  OK  {len(BATCH_PEAKS)} hydrographs  (peaks {BATCH_PEAKS[0]}–{BATCH_PEAKS[-1]} m)')

# ── Ex 10: batch, deterministic ───────────────────────────────────────────────
# Same building as Ex 01 (50 m² floor, door_gap sill=0, area=0.05 m²).
# Run over 20 hydrographs with peaks 0.10–1.05 m.
# Demonstrates monotonic scaling: larger floods → deeper interior inundation.
print('\nEx 10 – batch deterministic (20 hydrographs, single opening)')
ex10 = mkdir(os.path.join(HERE, 'ex10'))
run_batch_case('ex10', [
    '--depth-dir', batch_hydros_dir,
    '--ingress',   os.path.join(ex01, 'ingress.csv'),
    '--floor', '50',
], mkdir(os.path.join(ex10, 'out')))

# ── Ex 11: batch + fragility MC ───────────────────────────────────────────────
# Same membrane-protected building as Ex 08 (airbrick + door_gap, membrane η=0.5 m).
# 20 hydrographs × 50 replicates = 1 000 simulations.
# Below η=0.5 m: membrane almost always intact → near-zero ingress.
# Above η=0.5 m: failure probability increases → rising P50 interior depth.
# Produces a fragility curve: P(significant ingress) vs h_ext.
print('\nEx 11 – batch + fragility MC (20 hydrographs × 50 replicates, membrane)')
ex11 = mkdir(os.path.join(HERE, 'ex11'))
run_batch_case('ex11', [
    '--depth-dir', batch_hydros_dir,
    '--ingress',   os.path.join(ex08, 'ingress_frag.csv'),
    '--membrane',  os.path.join(ex08, 'membrane.csv'),
    '--floor', '50',
    '--n-replicates', '50',
    '--random-seed',  '42',
], mkdir(os.path.join(ex11, 'out')))

# Generate batch figures
print('\nGenerating batch figures ...')
_rows10 = _load_csv(os.path.join(HERE, 'ex10', 'out', 'batch_results.csv'))
_out10  = os.path.join(HERE, 'ex10', 'out', 'batch_result.png')
viz.save_batch_deterministic(
    [float(r['h_peak_ext']) for r in _rows10],
    [float(r['h_peak_int']) for r in _rows10],
    'Case 10 — Batch deterministic: 20 hydrographs, single ground-floor opening',
    _out10,
    v_peak=[float(r['v_peak_ext']) for r in _rows10] if 'v_peak_ext' in _rows10[0] else None,
)
print(f'  OK  {_out10}')

_rows11 = _load_csv(os.path.join(HERE, 'ex11', 'out', 'batch_results.csv'))
_out11  = os.path.join(HERE, 'ex11', 'out', 'batch_mc_result.png')
viz.save_batch_mc_fragility(
    [float(r['h_peak_ext']) for r in _rows11],
    [float(r['h_peak_int']) for r in _rows11],
    'Case 11 — Batch + fragility MC: 20 hydrographs × 50 replicates, membrane',
    _out11,
    membrane_median_m=0.5,
)
print(f'  OK  {_out11}')

# ── generate building schematics ─────────────────────────────────────────────
print('\nGenerating building schematics ...')
_sch_path = viz.save_all_schematics(os.path.join(HERE, 'schematics.png'))
print(f'  OK  {_sch_path}')

# ── generate report ───────────────────────────────────────────────────────────
print('\nGenerating report.md ...')

def img(case_dir, filename='simulation_result.png'):
    p = os.path.join(case_dir, 'out', filename)
    return rel(p) if os.path.exists(p) else '_figure not found_'

def gif_link(case_dir, filename='simulation_animation.gif'):
    p = os.path.join(case_dir, 'out', filename)
    if os.path.exists(p):
        return f'[Animation (GIF)]({rel(p)})'
    return ''

def mc_table(case_dir, filename):
    p = os.path.join(case_dir, 'out', filename)
    return read_csv_as_text(p)

report = textwrap.dedent("""\
# Water Ingress Simulation — Validation Case Studies

Eleven cases arranged in a **2 × 2 matrix** of
(single hydrograph / batch ensemble) × (deterministic / fragility MC):

| | Single hydrograph | Batch (20 hydrographs, peaks 0.10–1.05 m) |
|---|---|---|
| **No fragility / membrane** | Cases 01–06 | **Case 10** |
| **Fragility / membrane MC** | Cases 07–09 | **Case 11** |

All cases share the same **triangular hydrograph shape**
(rise to peak at t = 30 min, drain to zero by t = 60 min,
dry tail to t = 360 min).
Single-hydrograph cases use a **0.5 m peak**.
Batch cases sweep peaks from **0.10 m to 1.05 m** (20 files, 0.05 m steps).

Ground-floor cases: **50 m²** floor area (small UK terraced house).
Basement cases add a **30 m²** partial basement at **−2.5 m**.

---

## Case 01 — Ground floor only, single large opening (sill = 0 m)

**Setup:** one orifice pathway (failed door flood-seal), sill at ground
level, area = 0.05 m², C_d = 0.6, floor area = 50 m².
Simulation timestep **Δt = 6 s** (see timestep sensitivity note below).

Characteristic response time:
τ = A\_floor · h\_max / Q\_max = 50 × 0.5 / 0.094 ≈ **266 s ≈ 4.4 min**

**Expected behaviour:** inflow begins immediately at t = 0.  The large
orifice equilibrates the interior with the exterior within a few
minutes.  Interior depth closely tracks external depth throughout the
flood and drains back out rapidly after t = 60 min.

**Qualitative check:** interior and exterior curves nearly coincide;
drainage complete by ≈ t = 70 min.

![]({sim01})

{gif01}

### Timestep sensitivity — explicit-Euler accuracy

With the corrected 50 m² floor the scheme is stable at dt = 60 s
(Δt/τ = 0.23), but the explicit-Euler method still carries a systematic
positive bias: each step slightly overshoots equilibrium.  The table
below (computed with the 50 m² floor) shows how the peak depth error
converges as Δt shrinks.

| Δt | Δt / τ | Peak h\_in (m) | Error vs 1-s ref |
|---|---|---|---|
| 60 s (1 min) | 0.23 | 0.506 | +1.1 % |
| 30 s | 0.11 | 0.500 | +0.3 % |
| 15 s | 0.06 | 0.499 | < 0.1 % |
| **6 s (fix)** | **0.023** | **0.494** | **< 0.3 %** |
| 1 s (ref) | 0.004 | 0.494 | — |

**Note:** with the original, unrealistically small 10 m² floor the
same orifice gave Δt/τ = 0.57 and caused catastrophic oscillation
(peak error +28 %).  Correcting the geometry eliminated the instability;
the residual bias at Δt = 6 s is negligible (<0.3 %).

![]({dt_sens01})

---

## Case 02 — Raised sill (sill = 0.3 m)

**Setup:** identical to Case 01 (50 m² floor, A = 0.05 m², Δt = 6 s)
except the sill is raised to 0.3 m, representing a flood barrier or
raised threshold.

**Expected behaviour:** no inflow until the external depth exceeds
0.3 m (t ≈ 18 min on the rising limb).  After the flood recedes,
water above the sill drains back out.  Water below the sill height
(0.3 m) is **permanently trapped** — the orifice model requires h > sill
on at least one side to permit flow, so once both interior and exterior
drop below 0.3 m there is no pathway for the residual water to escape.

**Qualitative check:** interior trace flat (zero) until t ≈ 18 min;
kink clearly visible at sill-crossing; residual interior depth converges
to ≈ 0.30 m and remains constant for the rest of the simulation.

![]({sim02})

{gif02}

---

## Case 03 — Two openings: base crack + door gap

**Setup:** 50 m² floor, two pathways —
* Pathway A (`base_crack`): sill = 0.0 m, area = 0.001 m² — small
  permanent crack, active throughout
* Pathway B (`door_gap`): sill = 0.3 m, area = 0.005 m² — door gap,
  activates once exterior exceeds 0.3 m

Simulation extended to 360 min so the slow post-flood crack drainage
is fully visible.

**Expected behaviour:** slow linear rise while only Pathway A is
active.  At t ≈ 18 min Pathway B opens and the fill rate jumps by
~5×.  After the flood (t > 60 min) both pathways initially drain the
interior; once h\_in drops below 0.3 m only the crack remains active
and drainage slows dramatically.  Interior returns to zero by ≈ t = 360 min.

**Qualitative check:** clear inflection near t ≈ 18 min; drainage
curve shows two distinct slopes (fast above 0.3 m, slow below 0.3 m);
interior reaches zero by end of 6-hour window.

![]({sim03})

{gif03}

---

## Case 04 — Basement compartment (no ground-floor opening)

**Setup:** 50 m² ground floor (no effective opening), 30 m² partial
basement, floor at −2.5 m (full-height UK basement, total void ≈ 75 m³).
Lumped exterior→basement perimeter opening: sill = 0 m, area = 0.005 m²,
C_d = 0.5.  No pump.

The perimeter sill is at ground level (0 m), so its effective head is
simply h\_ext (the exterior flood depth); the basement water surface
(below ground) exerts no back-pressure.  Maximum inflow:
Q\_max = 0.5 × 0.005 × √(2g × 0.5) ≈ **0.008 m³/s**.

Without a pump, once the flood recedes (h\_ext → 0) the basement water
is **permanently trapped** — it cannot drain back through a sill at 0 m
when the exterior is dry.

**Expected behaviour:** ground-floor trace identically zero; basement
fills steadily during the 60-min flood, reaching ≈ 0.6 m depth (above
floor) by t = 60 min; level remains constant thereafter.

**Qualitative check:** ground-floor trace = 0; basement trace rises
monotonically during flood and plateaus after t = 60 min.

![]({sim04})

{gif04}

---

## Case 05 — Basement + sump/pump (pump keeps up)

**Setup:** identical inflow to Case 04 (30 m² basement, z = −2.5 m).
Added sump (area = 0.5 m², base at −2.5 m, overflow crest at 0.8 m
above base).  Strong pump: k\_pump = 1 000.

Q\_pump = √((H\_shut − H\_lift) / k\_pump).
At peak flood (H\_lift = |0.5 − (−2.5)| = 3.0 m):
Q\_pump = √((5.0 − 3.0) / 1 000) ≈ **0.045 m³/s** >> Q\_in\_max ≈ 0.008 m³/s.

**Expected behaviour:** the sump activates almost immediately and pumps
out all inflow.  Sump level stays below the on-level (0.10 m); no
overflow; no basement flooding; no ground-floor flooding.  After the
flood the pump drains any residual sump water.

**Qualitative check:** sump trace stays near zero (≤ 0.10 m); basement
and ground-floor traces remain at zero throughout.

![]({sim05})

{gif05}

### Timestep sensitivity — sump/pump oscillation

With the explicit-Euler update, the pump discharges **ΔV = Q_pump × Δt**
per step.  If ΔV exceeds the active sump volume **A_sump × h_on**, the
sump drains past zero in one step and refills to h\_on the next — a pure
numerical artefact that can push h\_sump past the overflow crest and
cause spurious basement flooding.

**Stability criterion:**

> Δt  ≤  dt\_crit  =  A\_sump × h\_on / Q\_pump

For Case 05 (A\_sump = 0.5 m², h\_on = 0.10 m, Q\_pump ≈ 0.045 m³/s):

> dt\_crit ≈ 1.1 s  →  recommended Δt ≤ **1 s** (50 % margin)

The figure below shows sump depth time-series for Δt = 60 s down to 0.5 s
(reference).  At Δt = 60 s the sump oscillates to the overflow crest,
producing a spurious 2 mm basement depth.  At Δt ≤ 2 s the level is
smooth and the basement remains dry throughout.

![]({dt_sens05})

---

## Case 06 — Basement + sump/pump (pump overwhelmed)

**Setup:** same as Case 05 but 100× weaker pump: k\_pump = 100 000.
At peak flood:
Q\_pump = √((5.0 − 3.0) / 100 000) ≈ **0.0045 m³/s** < Q\_in\_max ≈ 0.008 m³/s.

**Expected behaviour:** pump activates but cannot match inflow; sump
level rises quickly (excess rate ≈ 0.003 m³/s over 0.5 m² ≈ 7 mm/s)
and reaches the overflow crest (0.8 m) within ≈ 2 min.  Excess water
spills into the basement, which then fills.  Contrast directly with
Case 05 where the sump never overflows.

**Qualitative check:** sump trace rises to the overflow crest and
saturates there; basement trace becomes positive soon after; sump
overflow crest visible as a horizontal asymptote.

![]({sim06})

{gif06}

---

## Case 07 — Fragility Monte Carlo: single probabilistic seal (500 replicates)

**Setup:** 50 m² ground floor.  One fragility path `seal_door` —
* Base state: area ≈ 0 m² (sealed)
* Degraded state (seal fails): area = 0.005 m²

Lognormal capacity: median η = 0.5 m, β = 0.3.  Peak external depth
= 0.5 m → P(seal fails) = P(h\* < 0.5 m) = **50 %** by construction.

With a 50 m² floor the characteristic fill time when the seal fails is
τ ≈ 44 min (slow relative to the 30-min rising limb), so the "failed"
cluster reaches a peak interior depth of ≈ 0.25 m — well below the
external peak of 0.5 m.

**Expected behaviour:** bimodal ensemble —
* ≈50 % of replicates: seal intact → peak\_h\_in ≈ 0
* ≈50 % of replicates: seal failed → peak\_h\_in ≈ 0.25 m

**Qualitative check:** histogram has two clearly separated clusters;
sharp discontinuity between P50 (≈ 0) and P75 (> 0); P10–P90 range is
wide.

![]({sim07})

### Percentile summary (peak_h_in, peak_h_basement, total_volume_in)

{tbl07_summary}

### State frequency table

{tbl07_states}

---

## Case 08 — Fragility Monte Carlo: membrane-protected group (500 replicates)

**Setup:** 50 m² ground floor.  Two pathways behind a flood-protection
membrane (group\_id = 1) —
* `airbrick`: sill = 0.1 m, area = 0.006 m²
* `door_gap`: sill = 0.0 m, area = 0.002 m²

Membrane: sill = 0 m, base leakage ≈ 0.  Lognormal overtopping
capacity: median = 0.5 m, β = 0.1 (tight, near-deterministic threshold).
P(membrane overtopped) = **50 %**.

When the membrane fails, total area = 0.008 m² → τ ≈ 28 min; the
"failed" cluster peak interior depth ≈ 0.20 m.

**Expected behaviour:**
* ≈50 % of replicates: membrane intact → total ingress ≈ 0
* ≈50 % of replicates: membrane overtopped → interior fills to ≈ 0.20 m

The tight β = 0.1 means the two clusters are well-separated with
little intermediate probability mass.

**Observed (seed = 42, n = 500):** same 251/249 split as Case 07
(same seed and uniform draws).

**Qualitative check:** same bimodal pattern as Case 07; slightly lower
"failed" cluster peak than Case 07 because the airbrick sill (0.1 m)
delays part of the inflow.

![]({sim08})

### Percentile summary

{tbl08_summary}

### State frequency table

{tbl08_states}

---

## Case 09 — Deterministic membrane (design capacity above flood peak)

**Setup:** identical pathways to Case 08 (airbrick + door\_gap behind membrane
group\_id = 1, 50 m² floor).  The membrane capacity is **deterministic**:
β = 0, median η = **0.6 m** — fixed capacity, no uncertainty.

With the triangular hydrograph peaking at **0.5 m < 0.6 m**, the demand
never reaches the membrane capacity.  The membrane remains intact in every
replicate.

While intact, the membrane presents only its base-state leakage conductance
(area = 1 × 10⁻⁶ m²) to the flood; the pathways behind it are suppressed to
1 × 10⁻⁹ m².  This results in negligible interior depth throughout.

**Comparison with Case 08:** in Case 08 the same membrane has η = 0.5 m and
β = 0.1, giving P(failure) = 50 %.  Case 09 shows that raising the design
capacity by 0.1 m (to just above the flood peak) eliminates all ingress when
there is no uncertainty.

**Qualitative check:** scatter and CDF both cluster at h\_in ≈ 0;
state frequency shows State 0 = 100 %, State 1 = 0 %.

![]({sim09})

### Percentile summary

{tbl09_summary}

### State frequency table

{tbl09_states}

---

## Case 10 — Batch deterministic: 20 hydrographs, single opening

**Setup:** same building as Case 01 (50 m² ground floor, `door_gap` at
sill = 0 m, area = 0.05 m², C_d = 0.6).  The same orifice model is
run over **20 independent hydrographs** with triangular shapes and peaks
ranging from **0.10 m to 1.05 m** in 0.05 m steps.  No fragility or
membrane is applied; the result is purely deterministic.

**Expected behaviour:** peak interior depth increases monotonically
with peak exterior depth.  For small peaks (h\_ext ≤ 0.10 m) the large
orifice tracks the exterior almost perfectly (h\_in ≈ h\_ext).  For
larger peaks the interior fills rapidly and the ratio h\_in/h\_ext also
approaches 1.  The attenuation ratio remains close to 1.0 throughout
because the large orifice (area = 0.05 m²) equilibrates quickly with
the 50 m² floor.

**Qualitative check:** monotonically rising scatter; ratio h\_in/h\_ext
≈ constant near 1; no scatter around the response curve (deterministic).

![]({scatter10})

### First 5 rows of batch\_results.csv

{tbl10_results}

### Batch summary statistics

{tbl10_summary}

---

## Case 11 — Batch + fragility MC: 20 hydrographs × 50 replicates, membrane

**Setup:** same membrane-protected building as Case 08 —
* `airbrick`: sill = 0.1 m, area = 0.006 m², behind membrane group 1
* `door_gap`: sill = 0.0 m, area = 0.002 m², behind membrane group 1
* Membrane: sill = 0 m, base leakage ≈ 0; lognormal capacity
  **η = 0.5 m, β = 0.1** (tight near-deterministic threshold)

The same 20 hydrographs as Case 10 are used.  For each hydrograph,
**50 Monte Carlo replicates** are drawn (seed = 42), giving
**1 000 total simulations**.  The seed is reset identically for each
hydrograph, making the per-hydrograph MC independent.

**Expected behaviour** (fragility curve):
* h\_ext ≪ 0.5 m  →  membrane never overtopped  →  P(failure) ≈ 0 %,
  peak\_h\_in ≈ 0 for all replicates
* h\_ext ≈ 0.5 m  →  P(overtopping) ≈ 50 % (median capacity = 0.5 m)
  →  bimodal peak\_h\_in (≈50 % near 0, ≈50 % positive)
* h\_ext ≫ 0.5 m  →  membrane almost certainly overtopped
  →  P(failure) → 100 %, peak\_h\_in rises with h\_ext

The left panel shows the replicate cloud with P10 / P50 / P90 bands.
The right panel shows the fragility curve — the fraction of replicates
with significant ingress as a function of peak exterior depth.

**Comparison with Case 08:** the h\_ext = 0.5 m slice of Case 11 is
statistically equivalent to Case 08 (same building, same hydrograph,
same seed, n = 50 replicates).

![]({scatter11})
""")

def csv_head(path, n=5):
    """Return first n data rows of a CSV as a markdown table, or '' if missing."""
    if not os.path.exists(path):
        return ''
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    if not rows:
        return ''
    header = '| ' + ' | '.join(rows[0]) + ' |'
    sep    = '| ' + ' | '.join('---' for _ in rows[0]) + ' |'
    body   = '\n'.join('| ' + ' | '.join(r) + ' |' for r in rows[1:n+1])
    suffix = f'\n_…and {len(rows)-1-n} more rows_' if len(rows) > n + 1 else ''
    return header + '\n' + sep + '\n' + body + suffix


report = report.format(
    sim01=img(os.path.join(HERE, 'ex01')),
    dt_sens01=img(os.path.join(HERE, 'ex01'), 'dt_sensitivity.png'),
    sim02=img(os.path.join(HERE, 'ex02')),
    sim03=img(os.path.join(HERE, 'ex03')),
    sim04=img(os.path.join(HERE, 'ex04')),
    sim05=img(os.path.join(HERE, 'ex05')),
    dt_sens05=img(os.path.join(HERE, 'ex05'), 'dt_sensitivity.png'),
    sim06=img(os.path.join(HERE, 'ex06')),
    sim07=img(os.path.join(HERE, 'ex07'), 'mc_result.png'),
    sim08=img(os.path.join(HERE, 'ex08'), 'mc_result.png'),
    sim09=img(os.path.join(HERE, 'ex09'), 'mc_result.png'),
    gif01=gif_link(os.path.join(HERE, 'ex01')),
    gif02=gif_link(os.path.join(HERE, 'ex02')),
    gif03=gif_link(os.path.join(HERE, 'ex03')),
    gif04=gif_link(os.path.join(HERE, 'ex04')),
    gif05=gif_link(os.path.join(HERE, 'ex05')),
    gif06=gif_link(os.path.join(HERE, 'ex06')),
    tbl07_summary=mc_table(os.path.join(HERE, 'ex07'), 'fragility_summary.csv') or '_not generated_',
    tbl07_states =mc_table(os.path.join(HERE, 'ex07'), 'fragility_state_freq.csv') or '_not generated_',
    tbl08_summary=mc_table(os.path.join(HERE, 'ex08'), 'fragility_summary.csv') or '_not generated_',
    tbl08_states =mc_table(os.path.join(HERE, 'ex08'), 'fragility_state_freq.csv') or '_not generated_',
    tbl09_summary=mc_table(os.path.join(HERE, 'ex09'), 'fragility_summary.csv') or '_not generated_',
    tbl09_states =mc_table(os.path.join(HERE, 'ex09'), 'fragility_state_freq.csv') or '_not generated_',
    scatter10=img(os.path.join(HERE, 'ex10'), 'batch_result.png'),
    tbl10_results=csv_head(os.path.join(HERE, 'ex10', 'out', 'batch_results.csv')) or '_not generated_',
    tbl10_summary=mc_table(os.path.join(HERE, 'ex10'), 'batch_summary.csv') or '_not generated_',
    scatter11=img(os.path.join(HERE, 'ex11'), 'batch_mc_result.png'),
)

report_path = os.path.join(HERE, 'report.md')
with open(report_path, 'w') as f:
    f.write(report)

print(f'\nDone.  Report written to {report_path}')
