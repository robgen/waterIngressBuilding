#!/usr/bin/env python3
"""
Batch run wrapper for the water ingress simulation.

Runs one deterministic simulation per hydrograph file in a supplied directory
and aggregates the results.  The randomness in the ensemble comes from the
pre-generated hydrograph files (see hydrographs/generate.py); this
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

See docs/model.md for the planned Monte Carlo / fragility architecture.

Inputs
------
Two directory layouts are supported:

  A) Two separate directories  (current dataset layout)
       depth_dir/     depth_001.csv … depth_100.csv
       velocity_dir/  velocity_001.csv … velocity_100.csv   (optional)
     Files are matched by the numeric suffix in their names.

  B) Single combined-file directory
     Each CSV has three columns: time, depth, velocity.
     Pass --depth-dir pointing to this directory; omit --velocity-dir.

Usage
-----
  python3 batch.py \\
      --depth-dir    "hydrographs/depth"      \\
      --velocity-dir "hydrographs/velocity"   \\
      --ingress      examples/ex01/ingress.csv          \\
      --contents-vulnerability path/to/vulnerability.csv   \\
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
import re
import sys

from loss import load_vulnerability_curve
from engine import (
    Building,
    IngressPathway,
    Simulation,
    SimResult,
    parse_combined_file,
    sample_with_zero_padding,
)
from pump import SumpPump

_MUL = {'seconds': 1.0, 'minutes': 60.0, 'hours': 3600.0}


# ── file discovery ────────────────────────────────────────────────────────────

def _numeric_suffix(filename):
    """Extract the trailing integer from a filename stem (e.g. depth_042.csv → 42).

    Only the rightmost contiguous digit run is used, so filenames that include
    dates or version numbers in earlier positions (e.g. depth_2024_001.csv → 1)
    are handled correctly.
    """
    stem = os.path.splitext(filename)[0]
    m = re.search(r'(\d+)$', stem)
    return int(m.group(1)) if m else 0


def _discover_cases(depth_dir):
    """Return sorted list of (case_id, depth_path) from a directory of CSV files."""
    cases = []
    for fname in sorted(os.listdir(depth_dir)):
        if not fname.endswith('.csv'):
            continue
        cases.append((_numeric_suffix(fname), os.path.join(depth_dir, fname)))
    return sorted(cases, key=lambda x: x[0])


# ── combined-file detection ───────────────────────────────────────────────────

def _parse_depth_file_maybe_combined(filepath):
    """Delegates to engine.parse_combined_file."""
    return parse_combined_file(filepath)


# ── single simulation run ─────────────────────────────────────────────────────

def _run_case(depth_path, ingress_list, floor_area,
              dt_s, mul, velocity_mode='zero', vel_a=1.5, vel_b=0.5,
              basement_area=0.0, basement_floor_elev=None,
              basement_ceiling_elev=0.0,
              basement_ingress=None,
              basement_conn_height=None, basement_conn_area=0.0,
              sump_pump=None):
    """
    Run one simulation and return
    (sim_times_s, sim_levels, sim_basement, sim_sump,
     h_peak_ext, h_peak_int, h_peak_basement, h_peak_sump).

    sim_times_s are in seconds (internal units).  h values in metres.
    sim_basement and sim_sump are None when the respective zones are not active.
    sump_pump is deep-copied per case so mutable state (h_sump, pump_state)
    is reset between runs.
    """
    times_raw, depths, inline_vel = _parse_depth_file_maybe_combined(depth_path)
    times_s = [t * mul for t in times_raw]

    v_times_s, v_vals = None, None
    if velocity_mode == 'file':
        if inline_vel is not None:
            v_times_s = list(times_s)
            v_vals = inline_vel
        else:
            raise ValueError(
                f'velocity_mode=file but {depth_path} has only 2 columns (no inline velocity).'
            )

    building = Building(floor_area)
    if basement_area and basement_area > 0.0:
        building.basement_area = float(basement_area)
        building.h_basement = 0.0
        if basement_floor_elev is not None:
            building.z_basement = float(basement_floor_elev)
        building.basement_ceiling_elevation = float(basement_ceiling_elev)

    # Lumped exterior perimeter opening (spec §16.8)
    if basement_ingress is not None and basement_area > 0.0:
        building.basement_ingress = basement_ingress  # shared read-only object

    # Sump+pump — deep-copy to reset mutable state (h_sump, pump_state) per case
    if sump_pump is not None and basement_area > 0.0:
        building.sump_pump = copy.deepcopy(sump_pump)

    # Ground↔basement bypass connection (goes in ingress list)
    ing = list(ingress_list)
    if basement_area and basement_area > 0.0 and basement_conn_area > 0.0 and basement_conn_height is not None:
        ing.append(IngressPathway(
            height=float(basement_conn_height),
            area=float(basement_conn_area),
            coeff=1.0,
            name='ground-basement-conn',
            source='ground',
            target='basement',
        ))

    sim = Simulation(building, ing, times_s, depths, dt=dt_s,
                     external_vel_times=v_times_s, external_velocities=v_vals,
                     velocity_mode=velocity_mode, vel_a=vel_a, vel_b=vel_b)
    result = sim.run()

    if len(result) == 4:
        sim_times, sim_levels, sim_basement, sim_sump = result
    elif len(result) == 3:
        sim_times, sim_levels, sim_basement = result
        sim_sump = None
    else:
        sim_times, sim_levels = result
        sim_basement = None
        sim_sump = None

    sampled_ext = sample_with_zero_padding(sim_times, times_s, depths)
    h_peak_ext      = max(sampled_ext)   if sampled_ext   else 0.0
    h_peak_int      = max(sim_levels)    if sim_levels    else 0.0
    h_peak_basement = max(sim_basement)  if sim_basement  else 0.0
    h_peak_sump     = max(sim_sump)      if sim_sump      else 0.0
    if velocity_mode == 'file' and v_times_s and v_vals:
        sampled_vel = sample_with_zero_padding(sim_times, v_times_s, v_vals)
        v_peak_ext = max(sampled_vel) if sampled_vel else 0.0
    elif velocity_mode == 'power_law':
        v_peak_ext = vel_a * (h_peak_ext ** vel_b) if h_peak_ext > 0 else 0.0
    else:
        v_peak_ext = 0.0

    total_volume_in = sum(
        (sim_levels[i] - sim_levels[i - 1]) * floor_area
        for i in range(1, len(sim_levels))
        if sim_levels[i] > sim_levels[i - 1]
    )

    return SimResult(
        times=sim_times,
        h_in=sim_levels,
        h_basement=sim_basement or [],
        h_sump=sim_sump or [],
        peak_h_in=h_peak_int,
        peak_h_basement=h_peak_basement,
        peak_h_sump=h_peak_sump,
        peak_h_ext=h_peak_ext,
        v_peak_ext=v_peak_ext,
        total_volume_in=total_volume_in,
    )


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
    key_cols = ['h_peak_ext', 'h_peak_int', 'h_peak_basement']
    if 'h_peak_sump' in results[0]:
        key_cols.append('h_peak_sump')
    key_cols += dur_cols
    for loss_col in ('building_content_loss', 'basement_content_loss', 'aggregate_content_loss'):
        if loss_col in results[0]:
            key_cols.append(loss_col)

    def _summary_round(col, value):
        return round(value, 2 if col.endswith('_loss') else 4)

    rows = []
    for col in key_cols:
        vals = sorted(r[col] for r in results)
        rows.append({
            'metric': col,
            'min':    _summary_round(col, _percentile(vals, 0)),
            'p10':    _summary_round(col, _percentile(vals, 10)),
            'p25':    _summary_round(col, _percentile(vals, 25)),
            'median': _summary_round(col, _percentile(vals, 50)),
            'p75':    _summary_round(col, _percentile(vals, 75)),
            'p90':    _summary_round(col, _percentile(vals, 90)),
            'max':    _summary_round(col, _percentile(vals, 100)),
        })

    summary_path = os.path.join(outdir, 'batch_summary.csv')
    with open(summary_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return summary_path


# ── main batch loop ───────────────────────────────────────────────────────────

_DEFAULT_THRESHOLDS = [round(0.10 * i, 2) for i in range(1, 16)]  # 0.10 … 1.50 m


def run_batch(depth_dir, ingress_list, floor_area,
              time_units, dt, thresholds,
              building_content_vulnerability,
              outdir, verbose=True,
              basement_content_vulnerability=None,
              basement_area=0.0, basement_floor_elev=None,
              basement_ceiling_elev=0.0,
              basement_ingress=None,
              basement_conn_height=None, basement_conn_area=0.0,
              sump_pump=None,
              frag_paths=None, membranes=None,
              n_replicates=1, random_seed=None,
              velocity_mode='zero', vel_a=1.5, vel_b=0.5):
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
    velocity_mode   : 'zero', 'power_law', or 'file' (file requires 3-column CSVs)
    vel_a / vel_b   : power-law coefficients (used when velocity_mode='power_law')
    building_content_vulnerability : optional VulnerabilityCurve mapping h_peak_int
                      (ground-floor peak depth) to building contents loss
    basement_content_vulnerability : optional VulnerabilityCurve mapping h_peak_basement
                      to basement contents loss
    basement_area   : basement floor area (m²); 0 disables basement zone
    basement_floor_elev : basement floor elevation relative to ground-floor datum (m)
    basement_ceiling_elev : basement ceiling elevation on same datum (m)
    basement_conn_height : sill height of ground↔basement connection (m)
    basement_conn_area   : area of ground↔basement connection (m²)
    outdir          : directory for output CSVs
    verbose         : print progress to stdout

    Returns
    -------
    list of result dicts (one per successfully completed case)
    """
    mul  = _MUL.get(time_units, 60.0)
    dt_s = dt * mul
    os.makedirs(outdir, exist_ok=True)

    pairs = _discover_cases(depth_dir)
    if not pairs:
        raise ValueError(f'No CSV files found in: {depth_dir}')

    has_fragile_paths = (frag_paths is not None
                         and any(p.fragility is not None for p in frag_paths))
    use_mc = (has_fragile_paths or bool(membranes)) and n_replicates > 1
    if use_mc:
        import fragility as _frag

    n_total   = len(pairs)
    results   = []
    n_failed  = 0
    tu_abbrev = time_units[:3]

    # Column names encode the threshold value: dur_h030cm_min for 0.30 m
    dur_cols = [f'dur_h{int(round(h*100)):03d}cm_{tu_abbrev}' for h in thresholds]

    if verbose:
        mode_str = f'fragility MC  n={n_replicates}' if use_mc else 'deterministic'
        print(f'Batch run: {n_total} cases  |  {mode_str}  |  '
              f'dt={dt} {time_units}  |  '
              f'thresholds={[round(h, 2) for h in thresholds]} m')

    for idx, (case_id, depth_path) in enumerate(pairs):
        if verbose:
            print(f'  [{idx+1:3d}/{n_total}]  case {case_id:03d}  '
                  f'{os.path.basename(depth_path):<30s}', end='\r', flush=True)
        try:
            times_raw, depths, inline_vel = _parse_depth_file_maybe_combined(depth_path)
            times_s = [t * mul for t in times_raw]

            v_times_s, v_vals = None, None
            if velocity_mode == 'file':
                if inline_vel is not None:
                    v_times_s = list(times_s)
                    v_vals = inline_vel
                else:
                    raise ValueError(
                        f'velocity_mode=file but {os.path.basename(depth_path)} '
                        f'has only 2 columns (no inline velocity).'
                    )

            if use_mc:
                _ba = float(basement_area) if basement_area else 0.0

                def _building_factory(_ba=_ba):
                    from engine import Building
                    b = Building(floor_area)
                    if _ba > 0.0:
                        b.basement_area = _ba
                        if basement_floor_elev is not None:
                            b.z_basement = float(basement_floor_elev)
                        b.basement_ceiling_elevation = float(basement_ceiling_elev)
                        if basement_ingress is not None:
                            b.basement_ingress = basement_ingress
                        if sump_pump is not None:
                            b.sump_pump = copy.deepcopy(sump_pump)
                    return b

                mc = _frag.run_fragility_montecarlo(
                    building_factory   = _building_factory,
                    paths              = frag_paths,
                    membranes          = membranes,
                    basement_fragility = None,
                    external_times     = times_s,
                    external_levels    = depths,
                    n_replicates       = n_replicates,
                    dt                 = dt_s,
                    external_vel_times = v_times_s,
                    external_velocities= v_vals,
                    seed               = random_seed,
                    velocity_mode      = velocity_mode,
                    vel_a              = vel_a,
                    vel_b              = vel_b,
                )
                for rep in mc.replicates:
                    row = {
                        'case_id':         case_id,
                        'replicate':       rep.replicate_id,
                        'depth_file':      os.path.basename(depth_path),
                        'h_peak_ext':      round(rep.peak_h_ext, 4),
                        'h_peak_int':      round(rep.peak_h_in, 4),
                        'h_peak_basement': round(rep.peak_h_basement, 4),
                        'v_peak_ext':      round(rep.v_peak_ext, 4),
                    }
                    if sump_pump is not None:
                        row['h_peak_sump'] = round(rep.peak_h_sump, 4)
                    building_loss = (
                        round(building_content_vulnerability.interpolate_loss(rep.peak_h_in), 2)
                        if building_content_vulnerability is not None else None
                    )
                    basement_loss = (
                        round(basement_content_vulnerability.interpolate_loss(rep.peak_h_basement), 2)
                        if basement_content_vulnerability is not None else None
                    )
                    if building_loss is not None:
                        row['building_content_loss'] = building_loss
                    if basement_loss is not None:
                        row['basement_content_loss'] = basement_loss
                    if building_loss is not None or basement_loss is not None:
                        row['aggregate_content_loss'] = round(
                            (building_loss or 0.0) + (basement_loss or 0.0), 2
                        )
                    rep_durations = _compute_durations(rep.h_in, thresholds, dt_s, mul)
                    for col, dur in zip(dur_cols, rep_durations):
                        row[col] = dur
                    results.append(row)

            else:
                res = _run_case(
                    depth_path, ingress_list,
                    floor_area, dt_s, mul, velocity_mode, vel_a, vel_b,
                    basement_area=basement_area,
                    basement_floor_elev=basement_floor_elev,
                    basement_ceiling_elev=basement_ceiling_elev,
                    basement_ingress=basement_ingress,
                    basement_conn_height=basement_conn_height,
                    basement_conn_area=basement_conn_area,
                    sump_pump=sump_pump,
                )
                durations = _compute_durations(res.h_in, thresholds, dt_s, mul)
                row = {
                    'case_id':         case_id,
                    'depth_file':      os.path.basename(depth_path),
                    'h_peak_ext':      round(res.peak_h_ext, 4),
                    'h_peak_int':      round(res.peak_h_in, 4),
                    'h_peak_basement': round(res.peak_h_basement, 4),
                    'v_peak_ext':      round(res.v_peak_ext, 4),
                }
                if sump_pump is not None:
                    row['h_peak_sump'] = round(res.peak_h_sump, 4)
                building_loss = (
                    round(building_content_vulnerability.interpolate_loss(res.peak_h_in), 2)
                    if building_content_vulnerability is not None else None
                )
                basement_loss = (
                    round(basement_content_vulnerability.interpolate_loss(res.peak_h_basement), 2)
                    if basement_content_vulnerability is not None else None
                )
                if building_loss is not None:
                    row['building_content_loss'] = building_loss
                if basement_loss is not None:
                    row['basement_content_loss'] = basement_loss
                if building_loss is not None or basement_loss is not None:
                    row['aggregate_content_loss'] = round(
                        (building_loss or 0.0) + (basement_loss or 0.0), 2
                    )
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

    import plot as viz

    # ── write batch_results.csv ───────────────────────────────────────────────
    results_path = os.path.join(outdir, 'batch_results.csv')
    with open(results_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    # ── write batch_summary.csv ───────────────────────────────────────────────
    summary_path = _write_summary(results, time_units, outdir) if not use_mc else None

    # ── write batch figures ───────────────────────────────────────────────────
    try:
        _bsmt_d = (abs(float(basement_floor_elev))
                   if basement_area and basement_floor_elev is not None else None)
        _bsmt_pw = [basement_ingress] if basement_ingress is not None else []
        viz.save_run_schematic(
            os.path.join(outdir, 'schematic.png'),
            gf_pathways=ingress_list,
            bsmt_pathways=_bsmt_pw,
            basement_depth=_bsmt_d,
            has_sump=sump_pump is not None,
            has_pump=sump_pump is not None,
            bypass_height=float(basement_conn_height or 0.0),
        )
    except Exception:
        pass

    peak_scatter_path = os.path.join(outdir, 'peak_exterior_vs_peak_interior.png')
    _v_vals = [r.get('v_peak_ext') for r in results]
    viz.save_batch_scatter(
        [r['h_peak_ext'] for r in results],
        [r['h_peak_int'] for r in results],
        peak_scatter_path,
        v_peak=_v_vals if all(v is not None for v in _v_vals) else None,
    )

    if not use_mc and any(r.get('h_peak_basement', 0.0) > 1e-6 for r in results):
        bsmt_scatter_path = os.path.join(outdir, 'peak_exterior_vs_peak_basement.png')
        _v_bsmt = [r.get('v_peak_ext') for r in results]
        viz.save_basement_scatter(
            [r['h_peak_ext']      for r in results],
            [r['h_peak_basement'] for r in results],
            bsmt_scatter_path,
            v_peak=_v_bsmt if all(v is not None for v in _v_bsmt) else None,
        )
        if verbose:
            print(f'  Basement → {bsmt_scatter_path}')

    if verbose:
        print(f'  Results  → {results_path}')
        if summary_path:
            print(f'  Summary  → {summary_path}')
        print(f'  Schematic → {os.path.join(outdir, "schematic.png")}')
        print(f'  Peaks    → {peak_scatter_path}')
        if not use_mc:
            _print_summary_table(results, time_units)

    if not use_mc and 'aggregate_content_loss' in results[0]:
        _v_loss = [r.get('v_peak_ext') for r in results]
        _vp     = _v_loss if all(v is not None for v in _v_loss) else None
        has_basement_loss = any(r.get('basement_content_loss') for r in results)

        if has_basement_loss:
            gf_path   = os.path.join(outdir, 'ground_floor_loss.png')
            bsmt_path = os.path.join(outdir, 'basement_loss.png')
            agg_path  = os.path.join(outdir, 'aggregate_loss.png')
            viz.save_ground_loss_scatter(
                [r['h_peak_int']            for r in results],
                [r['building_content_loss'] for r in results],
                gf_path, v_peak=_vp)
            viz.save_basement_loss_scatter(
                [r['h_peak_basement']       for r in results],
                [r['basement_content_loss'] for r in results],
                bsmt_path, v_peak=_vp)
            viz.save_loss_scatter(
                [r['h_peak_ext']            for r in results],
                [r['aggregate_content_loss'] for r in results],
                agg_path, v_peak=_vp)
            if verbose:
                print(f'  Ground-floor loss → {gf_path}')
                print(f'  Basement loss     → {bsmt_path}')
                print(f'  Aggregate loss    → {agg_path}')
        else:
            loss_path = os.path.join(outdir, 'peak_exterior_vs_aggregate_loss.png')
            viz.save_loss_scatter(
                [r['h_peak_ext']             for r in results],
                [r['aggregate_content_loss'] for r in results],
                loss_path, v_peak=_vp)
            if verbose:
                print(f'  Loss plot → {loss_path}')

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
    for loss_col in ('building_content_loss', 'basement_content_loss', 'aggregate_content_loss'):
        if loss_col in results[0]:
            loss_vals = [r[loss_col] for r in results]
            mn, md, mx = _stats(loss_vals)
            print(f"  {loss_col:<30s}  {mn:8.2f}  {md:8.2f}  {mx:8.2f}")
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
    p.add_argument('--ingress',      required=True,
                   help='Ingress pathways CSV (header-based unified format).')
    p.add_argument('--basement-ingress', default=None,
                   help='Single-row CSV defining the lumped exterior→basement perimeter opening.')
    p.add_argument('--membrane',     default=None,
                   help='Membrane CSV (header-based unified format). Enables fragility MC.')
    p.add_argument('--floor',        type=float, default=50.0,
                   help='Building floor area (m²).')
    p.add_argument('--time-units',   default='minutes',
                   choices=['seconds', 'minutes', 'hours'],
                   help='Time units used in the hydrograph files.')
    p.add_argument('--dt',           type=float, default=1.0,
                   help='Simulation timestep in the selected time units.')
    p.add_argument('--n-replicates', type=int, default=1,
                   help='Monte Carlo replicates per hydrograph (requires --membrane).')
    p.add_argument('--random-seed',  type=int, default=None)
    p.add_argument('--thresholds',   type=float, nargs='+',
                   default=_DEFAULT_THRESHOLDS,
                   metavar='H',
                   help='Absolute interior depth thresholds (m) for exceedance duration.')
    p.add_argument('--velocity-mode', default='zero',
                   choices=['zero', 'power_law', 'file'],
                   help="Velocity mode: 'zero' (default), 'power_law' (v=a·h^b), or 'file' (CSV).")
    p.add_argument('--velocity-power-law-a', type=float, default=1.5,
                   help='Power-law coefficient a in v=a·h^b. Default: 1.5.')
    p.add_argument('--velocity-power-law-b', type=float, default=0.5,
                   help='Power-law exponent b in v=a·h^b. Default: 0.5.')
    p.add_argument('--building-vulnerability', default=None,
                   help='CSV vulnerability curve: peak ground-floor depth → loss.')
    p.add_argument('--basement-vulnerability', default=None,
                   help='CSV vulnerability curve: peak basement depth → loss.')
    p.add_argument('--contents-loss-column', default='mean_repair_loss_GBP',
                   help='Loss column to read from the vulnerability CSVs.')
    p.add_argument('--basement-area', type=float, default=0.0,
                   help='Basement floor area (m²). If >0, a basement zone is created.')
    p.add_argument('--basement-floor-elevation', type=float, default=None,
                   help='Basement floor elevation relative to ground-floor datum (m).')
    p.add_argument('--basement-ceiling-elevation', type=float, default=0.0,
                   help='Basement ceiling elevation on same datum (m).')
    p.add_argument('--basement-bypass-height', type=float, default=None,
                   help='Sill height of ground↔basement connection (m).')
    p.add_argument('--basement-bypass-area', type=float, default=0.0,
                   help='Area of ground↔basement connection (m²).')
    # Sump + pump (unified --sumppump-* prefix, matching cli.py)
    p.add_argument('--sumppump-area', type=float, default=0.0,
                   help='Sump chamber area (m²). If >0 a sump+pump zone is created.')
    p.add_argument('--sumppump-base-elevation',    type=float, default=None)
    p.add_argument('--sumppump-overflow-level',    type=float, default=None)
    p.add_argument('--sumppump-overflow-coeff',    type=float, default=1.8)
    p.add_argument('--sumppump-overflow-exponent', type=float, default=1.5)
    p.add_argument('--sumppump-on-level',          type=float, default=None)
    p.add_argument('--sumppump-off-level',          type=float, default=None)
    p.add_argument('--sumppump-shutoff-head',       type=float, default=None)
    p.add_argument('--sumppump-curve-coeff',        type=float, default=None)
    p.add_argument('--sumppump-pipe-loss-coeff',    type=float, default=0.0)
    p.add_argument('--sumppump-availability',       type=float, default=1.0)
    p.add_argument('--outdir',       default='batch_results',
                   help='Output directory for batch_results.csv and batch_summary.csv.')
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    import fragility as _frag
    frag_paths = _frag.parse_pathway_file(args.ingress)
    ingress_list = [
        IngressPathway(height=p.height_m, area=p.area_m2, coeff=p.Cd, name=p.name)
        for p in frag_paths
    ]
    loss_col = args.contents_loss_column

    building_content_vulnerability = None
    if args.building_vulnerability:
        building_content_vulnerability = load_vulnerability_curve(
            args.building_vulnerability, loss_column=loss_col,
        )

    basement_content_vulnerability = None
    if args.basement_vulnerability:
        basement_content_vulnerability = load_vulnerability_curve(
            args.basement_vulnerability, loss_column=loss_col,
        )

    # Lumped exterior perimeter opening (--basement-ingress PATH)
    basement_ingress = None
    if args.basement_ingress:
        bsmt_paths = _frag.parse_pathway_file(args.basement_ingress)
        if bsmt_paths:
            bp = bsmt_paths[0]
            basement_ingress = IngressPathway(
                height=bp.height_m, area=bp.area_m2, coeff=bp.Cd,
                name=bp.name, source='outside', target='basement')

    # Sump+pump (--sumppump-* flags)
    sump_pump = None
    if args.sumppump_area and args.sumppump_area > 0.0:
        required = ['sumppump_base_elevation', 'sumppump_overflow_level',
                    'sumppump_on_level', 'sumppump_off_level',
                    'sumppump_shutoff_head', 'sumppump_curve_coeff']
        missing = [k for k in required if getattr(args, k, None) is None]
        if missing:
            print(f'WARNING: sump enabled but missing params: {missing}. Sump disabled.')
        else:
            sump_pump = SumpPump(
                sump_area           = float(args.sumppump_area),
                sump_base_elevation = float(args.sumppump_base_elevation),
                overflow_level      = float(args.sumppump_overflow_level),
                overflow_coeff      = float(args.sumppump_overflow_coeff),
                overflow_exponent   = float(args.sumppump_overflow_exponent),
                pump_on_level       = float(args.sumppump_on_level),
                pump_off_level      = float(args.sumppump_off_level),
                pump_shutoff_head   = float(args.sumppump_shutoff_head),
                pump_curve_coeff    = float(args.sumppump_curve_coeff),
                pipe_loss_coeff     = float(args.sumppump_pipe_loss_coeff),
                pump_availability   = float(args.sumppump_availability),
            )

    # Membrane fragility (--membrane PATH)
    membranes = []
    if args.membrane:
        raw = _frag.parse_pathway_file(args.membrane)
        membranes = [_frag.fragile_path_to_membrane(fp)
                     for fp in raw if fp.group_id > 0 and fp.fragility is not None]
        if membranes:
            _frag.assign_representative_paths(frag_paths, membranes)

    run_batch(
        depth_dir                      = args.depth_dir,
        ingress_list                   = ingress_list,
        frag_paths                     = frag_paths,
        membranes                      = membranes,
        n_replicates                   = args.n_replicates,
        random_seed                    = args.random_seed,
        floor_area                     = args.floor,
        time_units                     = args.time_units,
        dt                             = args.dt,
        thresholds                     = args.thresholds,
        velocity_mode                  = args.velocity_mode,
        vel_a                          = args.velocity_power_law_a,
        vel_b                          = args.velocity_power_law_b,
        building_content_vulnerability = building_content_vulnerability,
        basement_content_vulnerability = basement_content_vulnerability,
        basement_area                  = args.basement_area,
        basement_floor_elev            = args.basement_floor_elevation,
        basement_ceiling_elev          = args.basement_ceiling_elevation,
        basement_ingress               = basement_ingress,
        basement_conn_height           = args.basement_bypass_height,
        basement_conn_area             = args.basement_bypass_area,
        sump_pump                      = sump_pump,
        outdir                         = args.outdir,
        verbose                        = True,
    )


if __name__ == '__main__':
    main()


# ── high-level public run() ───────────────────────────────────────────────────

def run(config, hydro_dir: str, pathways: list, *,
        basement_pathway=None,
        thresholds=None,
        building_vulnerability=None,
        basement_vulnerability=None,
        outdir='batch_results',
        verbose=True) -> list:
    """Run the full batch ensemble using SimConfig and a directory of hydrographs.

    Parameters
    ----------
    config                : engine.SimConfig — building geometry and run parameters
    hydro_dir             : path to directory of depth CSV files (2 or 3 columns)
    pathways              : List[IngressPathway] — ingress paths (fixed across all cases)
    basement_pathway      : optional IngressPathway for exterior→basement perimeter
    thresholds            : list of depth thresholds (m) for duration reporting
    building_vulnerability: optional VulnerabilityCurve for ground-floor loss
    basement_vulnerability: optional VulnerabilityCurve for basement loss
    outdir                : output directory for batch CSVs and figures
    verbose               : print progress to stdout

    Returns
    -------
    List of result dicts (one per successfully completed case)
    """
    if thresholds is None:
        thresholds = _DEFAULT_THRESHOLDS

    sump_pump = config.sumppump

    return run_batch(
        depth_dir=hydro_dir,
        ingress_list=pathways,
        floor_area=config.floor_area,
        time_units=config.time_units,
        dt=config.dt / {'seconds': 1.0, 'minutes': 60.0, 'hours': 3600.0}.get(config.time_units, 60.0),
        thresholds=thresholds,
        velocity_mode=config.velocity_mode,
        vel_a=config.velocity_power_law_a,
        vel_b=config.velocity_power_law_b,
        building_content_vulnerability=building_vulnerability,
        basement_content_vulnerability=basement_vulnerability,
        basement_area=config.basement_area,
        basement_floor_elev=config.basement_floor_elevation if config.basement_area > 0 else None,
        basement_ceiling_elev=config.basement_ceiling_elevation,
        basement_ingress=basement_pathway,
        basement_conn_height=config.basement_connection_height,
        basement_conn_area=config.basement_connection_area,
        sump_pump=sump_pump,
        outdir=outdir,
        verbose=verbose,
    )
