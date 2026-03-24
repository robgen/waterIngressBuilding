#!/usr/bin/env python3
"""
Batch run wrapper for the water ingress simulation.

Runs one deterministic simulation per hydrograph file in a supplied directory
and aggregates the results.  The randomness in the ensemble comes from the
pre-generated hydrograph files (see water time series/generate.py); this
script itself performs no parameter sampling.

For each case the script:
  1. Runs one full simulation with the external depth (and optionally velocity)
     time series for that case.
  2. Extracts:
       h_peak_ext        – peak exterior water depth  (m)
       h_peak_int        – peak interior water depth  (m)
       dur_hXXXcm_<tu>  – time (in selected time units) that the
                           interior depth is >= each fixed absolute
                           threshold (e.g. dur_h030cm_min for 0.30 m).
                           Returns 0 when the threshold is not reached.
  3. Writes results to batch_results.csv and a statistical summary to
     batch_summary.csv in the specified output directory.

See docs/NOTE_montecarlo.md for the planned true Monte Carlo implementation
that will sample building and ingress parameters from distributions at runtime.

Inputs
------
Two directory layouts are supported:

  A) Two separate directories  (current dataset layout)
       depth_dir/     depth_001.csv … depth_100.csv
       velocity_dir/  velocity_001.csv … velocity_100.csv   (optional)
     Files are matched by the numeric suffix in their names.

  B) Single combined-file directory  (future layout, see
     water time series/NOTE_combined_input_format.md)
     Each CSV has three columns: time, depth, velocity.
     Pass --depth-dir pointing to this directory; omit --velocity-dir.

Usage
-----
  python3 batch_run.py \\
      --depth-dir    "water time series/depth"      \\
      --velocity-dir "water time series/velocity"   \\
      --ingress      example_run/example_ingress_paths.txt \\
      --floor        50                              \\
      --time-units   minutes                         \\
      --dt           1                               \\
      --thresholds   0.10 0.20 0.30 0.50 1.00 1.50   \\
      --outdir       batch_results/
"""

import argparse
import copy
import csv
import math
import os
import sys

from main import (
    Building,
    IngressPathway,
    Simulation,
    parse_external_file,
    parse_ingress_file,
    parse_velocity_file,
    sample_with_zero_padding,
)

_MUL = {'seconds': 1.0, 'minutes': 60.0, 'hours': 3600.0}


# ── file discovery ────────────────────────────────────────────────────────────

def _numeric_suffix(filename):
    """Extract the leading integer from the numeric part of a filename stem."""
    stem = os.path.splitext(filename)[0]
    digits = ''.join(c for c in stem if c.isdigit())
    return int(digits) if digits else 0


def _discover_pairs(depth_dir, velocity_dir):
    """
    Return sorted list of (case_id, depth_path, velocity_path_or_None).

    For layout A the velocity file is matched by identical numeric suffix.
    For layout B (combined files) velocity_dir is None and the third column
    of each depth file is used if present.
    """
    pairs = []
    for fname in sorted(os.listdir(depth_dir)):
        if not fname.endswith('.csv'):
            continue
        case_id = _numeric_suffix(fname)
        depth_path = os.path.join(depth_dir, fname)
        vel_path = None
        if velocity_dir:
            digits = ''.join(c for c in os.path.splitext(fname)[0] if c.isdigit())
            for vname in os.listdir(velocity_dir):
                if vname.endswith('.csv'):
                    vdigits = ''.join(c for c in os.path.splitext(vname)[0] if c.isdigit())
                    if vdigits == digits:
                        vel_path = os.path.join(velocity_dir, vname)
                        break
        pairs.append((case_id, depth_path, vel_path))
    return sorted(pairs, key=lambda x: x[0])


# ── combined-file detection ───────────────────────────────────────────────────

def _parse_depth_file_maybe_combined(filepath):
    """
    Parse a depth file that may be two-column (time, depth) or three-column
    (time, depth, velocity).  Returns (times, depths, velocities_or_None).
    """
    times, depths, velocities = [], [], []
    has_velocity = None
    with open(filepath) as f:
        for raw in f:
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 2:
                continue
            if has_velocity is None:
                has_velocity = len(parts) >= 3
            times.append(float(parts[0]))
            depths.append(float(parts[1]))
            if has_velocity:
                velocities.append(float(parts[2]) if len(parts) >= 3 else 0.0)
    if not times:
        raise ValueError(f'No data found in {filepath}')
    return times, depths, velocities if has_velocity else None


# ── single simulation run ─────────────────────────────────────────────────────

def _run_case(depth_path, vel_path, ingress_list, floor_area,
              dt_s, mul, default_velocity):
    """
    Run one simulation and return (sim_times_s, sim_levels, h_peak_ext, h_peak_int).

    sim_times_s are in seconds (internal units).  h values in metres.
    """
    times_raw, depths, inline_vel = _parse_depth_file_maybe_combined(depth_path)
    times_s = [t * mul for t in times_raw]

    # velocity source priority: explicit file > inline third column > default constant
    if vel_path:
        v_times_raw, v_vals = parse_velocity_file(vel_path)
        v_times_s = [t * mul for t in v_times_raw]
    elif inline_vel is not None:
        v_times_s = list(times_s)
        v_vals = inline_vel
    else:
        v_times_s = list(times_s)
        v_vals = [float(default_velocity)] * len(times_s)

    building = Building(floor_area)
    sim = Simulation(
        building,
        ingress_list,          # stateless — safe to share across runs
        times_s,
        depths,
        dt=dt_s,
        external_vel_times=v_times_s,
        external_velocities=v_vals,
    )
    result = sim.run()
    sim_times = result[0]
    sim_levels = result[1]

    sampled_ext = sample_with_zero_padding(sim_times, times_s, depths)
    h_peak_ext = max(sampled_ext) if sampled_ext else 0.0
    h_peak_int = max(sim_levels) if sim_levels else 0.0

    return sim_times, sim_levels, h_peak_ext, h_peak_int


# ── duration calculation ──────────────────────────────────────────────────────

def _compute_durations(sim_levels, thresholds, dt_s, mul):
    """
    Return durations_display_units for each fixed absolute threshold (m).

    Duration at h_star = total time interior depth >= h_star.
    Returns 0.0 for any threshold above the peak interior depth.
    Uses the fixed simulation dt (dt_s seconds) for all steps.
    """
    durations = []
    for h_star in thresholds:
        n_steps_above = sum(1 for h in sim_levels if h >= h_star)
        dur_display = (n_steps_above * dt_s) / mul
        durations.append(round(dur_display, 3))
    return durations


# ── summary statistics ────────────────────────────────────────────────────────

def _percentile(sorted_vals, p):
    """Linear interpolation percentile on a pre-sorted list."""
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    idx = (p / 100.0) * (n - 1)
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    return sorted_vals[lo] + (idx - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _write_summary(results, time_units, outdir):
    """Write batch_summary.csv with percentile statistics for key columns."""
    tu = time_units[:3]
    dur_cols = [c for c in results[0].keys() if c.startswith('dur_h') and c.endswith(tu)]
    key_cols = ['h_peak_ext', 'h_peak_int'] + dur_cols

    rows = []
    for col in key_cols:
        vals = sorted(r[col] for r in results)
        rows.append({
            'metric': col,
            'min':    round(_percentile(vals, 0),   4),
            'p10':    round(_percentile(vals, 10),  4),
            'p25':    round(_percentile(vals, 25),  4),
            'median': round(_percentile(vals, 50),  4),
            'p75':    round(_percentile(vals, 75),  4),
            'p90':    round(_percentile(vals, 90),  4),
            'max':    round(_percentile(vals, 100), 4),
        })

    summary_path = os.path.join(outdir, 'batch_summary.csv')
    with open(summary_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return summary_path


# ── main batch loop ───────────────────────────────────────────────────────────

_DEFAULT_THRESHOLDS = [round(0.10 * i, 2) for i in range(1, 16)]  # 0.10 … 1.50 m


def run_batch(depth_dir, velocity_dir, ingress_list, floor_area,
              time_units, dt, thresholds, default_velocity,
              outdir, verbose=True):
    """
    Run the full batch ensemble and write results.

    Each case is a single deterministic simulation driven by one pre-generated
    hydrograph file.  For true Monte Carlo (sampling ingress and building
    parameters from distributions), see docs/NOTE_montecarlo.md.

    Parameters
    ----------
    depth_dir       : directory containing depth CSV files
    velocity_dir    : directory with matching velocity CSVs, or None
    ingress_list    : list of IngressPathway objects (shared, stateless)
    floor_area      : building floor area (m²)
    time_units      : 'seconds' | 'minutes' | 'hours'
    dt              : simulation timestep in the selected time units
    thresholds      : list of absolute interior depth thresholds (m) at which
                      exceedance duration is reported (e.g. [0.10, 0.30, 1.00])
    default_velocity: fallback velocity (m/s) when no velocity data available
    outdir          : directory for output CSVs
    verbose         : print progress to stdout

    Returns
    -------
    list of result dicts (one per successfully completed case)
    """
    mul  = _MUL.get(time_units, 60.0)
    dt_s = dt * mul
    os.makedirs(outdir, exist_ok=True)

    pairs = _discover_pairs(depth_dir, velocity_dir)
    if not pairs:
        raise ValueError(f'No CSV files found in: {depth_dir}')

    n_total   = len(pairs)
    results   = []
    n_failed  = 0
    tu_abbrev = time_units[:3]

    # Column names encode the threshold value: dur_h030cm_min for 0.30 m
    dur_cols = [f'dur_h{int(round(h*100)):03d}cm_{tu_abbrev}' for h in thresholds]

    if verbose:
        print(f'Batch run: {n_total} cases  |  '
              f'dt={dt} {time_units}  |  '
              f'thresholds={[round(h, 2) for h in thresholds]} m')

    for idx, (case_id, depth_path, vel_path) in enumerate(pairs):
        if verbose:
            print(f'  [{idx+1:3d}/{n_total}]  case {case_id:03d}  '
                  f'{os.path.basename(depth_path):<30s}', end='\r', flush=True)
        try:
            sim_times, sim_levels, h_peak_ext, h_peak_int = _run_case(
                depth_path, vel_path, ingress_list,
                floor_area, dt_s, mul, default_velocity,
            )
            durations = _compute_durations(sim_levels, thresholds, dt_s, mul)
            row = {
                'case_id':       case_id,
                'depth_file':    os.path.basename(depth_path),
                'velocity_file': os.path.basename(vel_path) if vel_path else '',
                'h_peak_ext':    round(h_peak_ext, 4),
                'h_peak_int':    round(h_peak_int, 4),
            }
            for col, dur in zip(dur_cols, durations):
                row[col] = dur
            results.append(row)

        except Exception as exc:
            n_failed += 1
            if verbose:
                print(f'\n  WARNING case {case_id} skipped: {exc}')

    if verbose:
        print(f'\n  Completed: {len(results)}/{n_total}'
              + (f'  ({n_failed} failed)' if n_failed else ''))

    if not results:
        print('No results produced.', file=sys.stderr)
        return results

    # ── write batch_results.csv ───────────────────────────────────────────────
    results_path = os.path.join(outdir, 'batch_results.csv')
    with open(results_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    # ── write batch_summary.csv ───────────────────────────────────────────────
    summary_path = _write_summary(results, time_units, outdir)

    if verbose:
        print(f'  Results  → {results_path}')
        print(f'  Summary  → {summary_path}')
        _print_summary_table(results, time_units)

    return results


def _print_summary_table(results, time_units):
    """Print a short summary table to stdout."""
    tu = time_units[:3]

    def _stats(vals):
        s = sorted(vals)
        med = _percentile(s, 50)
        return min(s), med, max(s)

    h_ext  = [r['h_peak_ext'] for r in results]
    h_int  = [r['h_peak_int'] for r in results]
    ratio  = [r['h_peak_int'] / r['h_peak_ext']
               for r in results if r['h_peak_ext'] > 1e-6]

    print()
    print(f"  {'Metric':<30s}  {'Min':>8s}  {'Median':>8s}  {'Max':>8s}")
    print('  ' + '-' * 58)
    for label, vals in [
        ('h_peak_ext (m)',      h_ext),
        ('h_peak_int (m)',      h_int),
        ('h_int / h_ext ratio', ratio),
    ]:
        mn, md, mx = _stats(vals)
        print(f"  {label:<30s}  {mn:8.3f}  {md:8.3f}  {mx:8.3f}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description='Batch run of the water ingress simulation over an ensemble '
                    'of pre-generated flood hydrographs. '
                    'For true Monte Carlo see docs/NOTE_montecarlo.md.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument('--depth-dir',    required=True,
                   help='Directory containing depth CSV files.')
    p.add_argument('--velocity-dir', default=None,
                   help='Directory containing matching velocity CSV files. '
                        'Omit to use inline velocity (3rd column) or default constant.')
    p.add_argument('--ingress',      required=True,
                   help='Ingress pathways file (height,area,coeff[,name]).')
    p.add_argument('--floor',        type=float, default=50.0,
                   help='Building floor area (m²).')
    p.add_argument('--time-units',   default='minutes',
                   choices=['seconds', 'minutes', 'hours'],
                   help='Time units used in the hydrograph files.')
    p.add_argument('--dt',           type=float, default=1.0,
                   help='Simulation timestep in the selected time units.')
    p.add_argument('--thresholds',   type=float, nargs='+',
                   default=_DEFAULT_THRESHOLDS,
                   metavar='H',
                   help='Absolute interior depth thresholds (m) at which '
                        'exceedance duration is reported. '
                        'Default: 0.10 0.20 … 1.50 m.')
    p.add_argument('--default-velocity', type=float, default=0.2,
                   help='Fallback velocity (m/s) when no velocity data are available.')
    p.add_argument('--outdir',       default='batch_results',
                   help='Output directory for batch_results.csv and batch_summary.csv.')
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    ingress_list = parse_ingress_file(args.ingress)
    run_batch(
        depth_dir        = args.depth_dir,
        velocity_dir     = args.velocity_dir,
        ingress_list     = ingress_list,
        floor_area       = args.floor,
        time_units       = args.time_units,
        dt               = args.dt,
        thresholds       = args.thresholds,
        default_velocity = args.default_velocity,
        outdir           = args.outdir,
        verbose          = True,
    )


if __name__ == '__main__':
    main()
