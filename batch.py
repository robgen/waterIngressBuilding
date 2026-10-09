#!/usr/bin/env python3
"""
Batch run of the water ingress simulation over a set of hydrograph files.

For each hydrograph the script runs fragility.run() — config.n_replicates
replicates, one when there is nothing to sample — and records per replicate:
       h_peak_ext        – peak exterior water depth  (m)
       h_peak_int        – peak interior water depth  (m)
       dur_hXXXcm_<tu>  – time (in selected time units) that the
                           interior depth is >= each fixed absolute
                           threshold (e.g. dur_h030cm_min for 0.30 m).
Results go to batch_results.csv; deterministic runs (one replicate) also get a
statistical summary in batch_summary.csv.

Inputs
------
  --depth-dir DIR            every *.csv in DIR (2 or 3 columns: time, depth[, velocity])
  --hydrograph-files PATHS   explicit files or dir/regex patterns
Files are ordered by the numeric suffix in their names.

Building, pathway and run-control flags are shared with cli.py (inputs.py).

Usage
-----
  python3 batch.py \\
      --depth-dir    hydrographs/generated     \\
      --ingress      examples/ex01/ingress.csv \\
      --floor        50                        \\
      --time-units   minutes                   \\
      --dt           1                         \\
      --thresholds   0.10 0.20 0.30 0.50 1.00  \\
      --outdir       batch_results/
"""

import argparse
import csv
import os
import re
import sys

import numpy as np

import engine
import fragility
import inputs
import plot
from loss import load_vulnerability_curve

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


def _discover_cases_from_files(patterns):
    """Return sorted list of (case_id, depth_path) from explicit paths or regex patterns.

    Each entry in *patterns* is either:
      - A literal file path (must exist) → used directly.
      - A string like "dir/regex" where *dir* is a real directory and *regex* is
        matched with re.search() against filenames in that directory.

    Duplicates are silently ignored; results are sorted by numeric suffix.
    """
    cases = []
    seen = set()
    for pattern in patterns:
        if os.path.isfile(pattern):
            path = os.path.abspath(pattern)
            if path not in seen:
                seen.add(path)
                cases.append((_numeric_suffix(os.path.basename(path)), path))
        else:
            dir_part = os.path.dirname(pattern) or '.'
            pat_part = os.path.basename(pattern)
            if not os.path.isdir(dir_part):
                raise ValueError(
                    f'--hydrograph-files: directory not found: {dir_part!r} '
                    f'(from pattern {pattern!r})'
                )
            rx = re.compile(pat_part)
            for fname in sorted(os.listdir(dir_part)):
                if not fname.endswith('.csv'):
                    continue
                if rx.search(fname):
                    path = os.path.abspath(os.path.join(dir_part, fname))
                    if path not in seen:
                        seen.add(path)
                        cases.append((_numeric_suffix(fname), path))
    return sorted(cases, key=lambda x: x[0])

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
        vals = [r[col] for r in results]
        rows.append({
            'metric': col,
            'min':    _summary_round(col, float(np.percentile(vals, 0))),
            'p10':    _summary_round(col, float(np.percentile(vals, 10))),
            'p25':    _summary_round(col, float(np.percentile(vals, 25))),
            'median': _summary_round(col, float(np.percentile(vals, 50))),
            'p75':    _summary_round(col, float(np.percentile(vals, 75))),
            'p90':    _summary_round(col, float(np.percentile(vals, 90))),
            'max':    _summary_round(col, float(np.percentile(vals, 100))),
        })

    summary_path = os.path.join(outdir, 'batch_summary.csv')
    with open(summary_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return summary_path


# ── time-series export ───────────────────────────────────────────────────────

def _write_timeseries_csv(path, sim_times, h_in, h_ext,
                          h_basement, h_sump, mul, time_units):
    """Write a time-series CSV: time, h_ext, h_int, [h_basement], [h_sump]."""
    has_bsm = bool(h_basement) and any(v > 1e-9 for v in h_basement)
    has_smp = bool(h_sump)     and any(v > 1e-9 for v in h_sump)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        header = [f'time_{time_units}', 'h_ext_m', 'h_int_m']
        if has_bsm:
            header.append('h_basement_m')
        if has_smp:
            header.append('h_sump_m')
        w.writerow(header)
        for i, (t, hi, he) in enumerate(zip(sim_times, h_in, h_ext)):
            row = [round(t / mul, 3), round(he, 4), round(hi, 4)]
            if has_bsm:
                row.append(round(h_basement[i] if i < len(h_basement) else 0.0, 4))
            if has_smp:
                row.append(round(h_sump[i]     if i < len(h_sump)     else 0.0, 4))
            w.writerow(row)

def _result_row(case_id, depth_file, rec, n_replicates, thresholds, dur_cols,
                config, building_vuln, basement_vuln):
    """One batch_results.csv row for one replicate."""
    res = rec.result
    row = {'case_id': case_id}
    if n_replicates > 1:
        row['replicate'] = rec.replicate_id
    row.update({
        'depth_file':      depth_file,
        'h_peak_ext':      round(res.peak_h_ext, 4),
        'h_peak_int':      round(res.peak_h_in, 4),
        'h_peak_basement': round(res.peak_h_basement, 4),
        'v_peak_ext':      round(res.v_peak_ext, 4),
    })
    if config.sumppump is not None:
        row['h_peak_sump'] = round(res.peak_h_sump, 4)
    building_loss = (round(building_vuln.interpolate_loss(res.peak_h_in), 2)
                     if building_vuln is not None else None)
    basement_loss = (round(basement_vuln.interpolate_loss(res.peak_h_basement), 2)
                     if basement_vuln is not None else None)
    if building_loss is not None:
        row['building_content_loss'] = building_loss
    if basement_loss is not None:
        row['basement_content_loss'] = basement_loss
    if building_loss is not None or basement_loss is not None:
        row['aggregate_content_loss'] = round(
            (building_loss or 0.0) + (basement_loss or 0.0), 2)
    mul = engine.TIME_UNIT_SECONDS[config.time_units]
    for col, dur in zip(dur_cols, _compute_durations(res.h_in, thresholds, config.dt, mul)):
        row[col] = dur
    return row


# ── main batch loop ───────────────────────────────────────────────────────────

_DEFAULT_THRESHOLDS = [round(0.10 * i, 2) for i in range(1, 16)]  # 0.10 … 1.50 m


def run_batch(config, cases, paths, membranes=(), *, thresholds=None,
              building_content_vulnerability=None,
              basement_content_vulnerability=None,
              outdir='batch_results', save_timeseries=False, verbose=True):
    """Run every hydrograph in `cases` and write the batch outputs.

    Parameters
    ----------
    config    : engine.SimConfig (n_replicates > 1 → Monte Carlo per hydrograph)
    cases     : list of (case_id, hydrograph_path)
    paths     : List[FragilePath] — all pathways (ground floor and basement)
    membranes : List[Membrane]
    thresholds: absolute interior depth thresholds (m) for exceedance duration
    building_content_vulnerability / basement_content_vulnerability :
                optional VulnerabilityCurve for ground-floor / basement loss
    outdir    : directory for output CSVs and figures

    Returns
    -------
    list of result dicts (one per replicate per successfully completed case)
    """
    if thresholds is None:
        thresholds = _DEFAULT_THRESHOLDS
    os.makedirs(outdir, exist_ok=True)
    membranes = list(membranes)

    use_mc    = config.n_replicates > 1
    mul       = engine.TIME_UNIT_SECONDS[config.time_units]
    n_total   = len(cases)
    results   = []
    n_failed  = 0
    tu_abbrev = config.time_units[:3]

    # Column names encode the threshold value: dur_h030cm_min for 0.30 m
    dur_cols = [f'dur_h{int(round(h*100)):03d}cm_{tu_abbrev}' for h in thresholds]

    if verbose:
        mode_str = f'fragility MC  n={config.n_replicates}' if use_mc else 'deterministic'
        print(f'Batch run: {n_total} cases  |  {mode_str}  |  '
              f'dt={config.dt / mul} {config.time_units}  |  '
              f'thresholds={[round(h, 2) for h in thresholds]} m')

    for idx, (case_id, depth_path) in enumerate(cases):
        if verbose:
            print(f'  [{idx+1:3d}/{n_total}]  case {case_id:03d}  '
                  f'{os.path.basename(depth_path):<30s}', end='\r', flush=True)
        try:
            hydro = engine.read_hydrograph(depth_path, time_units=config.time_units,
                                           velocity_mode=config.velocity_mode)
            mc = fragility.run(config, hydro, paths, membranes)
            for rec in mc.replicates:
                results.append(_result_row(
                    case_id, os.path.basename(depth_path), rec, config.n_replicates,
                    thresholds, dur_cols, config,
                    building_content_vulnerability, basement_content_vulnerability))

            if save_timeseries:
                rec = mc.replicates[0]
                rep_tag = '' if not use_mc else f'_r{rec.replicate_id:02d}'
                ts_path = os.path.join(outdir, f'timeseries_{case_id:03d}{rep_tag}.csv')
                h_ext, _ = engine.exterior_series(config, hydro, rec.result.times)
                _write_timeseries_csv(ts_path, rec.result.times, rec.result.h_in, h_ext,
                                      rec.result.h_basement, rec.result.h_sump,
                                      mul, config.time_units)
                plot.save_run_result(ts_path.replace('.csv', '.png'),
                                     config, hydro, rec.result)

        except Exception as exc:
            n_failed += 1
            if verbose:
                print(f'\n  WARNING case {case_id} skipped: {exc}')

    if verbose:
        print(f'\n  Completed: {n_total - n_failed}/{n_total}'
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
    summary_path = _write_summary(results, config.time_units, outdir) if not use_mc else None

    # ── write batch figures ───────────────────────────────────────────────────
    try:
        plot.save_run_schematic(os.path.join(outdir, 'schematic.png'),
                                pathways=paths, membranes=membranes, config=config)
    except Exception:
        pass

    peak_scatter_path = os.path.join(outdir, 'peak_exterior_vs_peak_interior.png')
    _v_vals = [r.get('v_peak_ext') for r in results]
    plot.save_batch_scatter(
        [r['h_peak_ext'] for r in results],
        [r['h_peak_int'] for r in results],
        peak_scatter_path,
        v_peak=_v_vals if all(v is not None for v in _v_vals) else None,
    )

    if not use_mc and any(r.get('h_peak_basement', 0.0) > 1e-6 for r in results):
        bsmt_scatter_path = os.path.join(outdir, 'peak_exterior_vs_peak_basement.png')
        _v_bsmt = [r.get('v_peak_ext') for r in results]
        plot.save_basement_scatter(
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
            _print_summary_table(results)

    if not use_mc and 'aggregate_content_loss' in results[0]:
        _v_loss = [r.get('v_peak_ext') for r in results]
        _vp     = _v_loss if all(v is not None for v in _v_loss) else None
        has_basement_loss = any(r.get('basement_content_loss') for r in results)

        if has_basement_loss:
            gf_path   = os.path.join(outdir, 'ground_floor_loss.png')
            bsmt_path = os.path.join(outdir, 'basement_loss.png')
            agg_path  = os.path.join(outdir, 'aggregate_loss.png')
            plot.save_ground_loss_scatter(
                [r['h_peak_int']            for r in results],
                [r['building_content_loss'] for r in results],
                gf_path, v_peak=_vp)
            plot.save_basement_loss_scatter(
                [r['h_peak_basement']       for r in results],
                [r['basement_content_loss'] for r in results],
                bsmt_path, v_peak=_vp)
            plot.save_loss_scatter(
                [r['h_peak_ext']            for r in results],
                [r['aggregate_content_loss'] for r in results],
                agg_path, v_peak=_vp)
            if verbose:
                print(f'  Ground-floor loss → {gf_path}')
                print(f'  Basement loss     → {bsmt_path}')
                print(f'  Aggregate loss    → {agg_path}')
        else:
            loss_path = os.path.join(outdir, 'peak_exterior_vs_aggregate_loss.png')
            plot.save_loss_scatter(
                [r['h_peak_ext']             for r in results],
                [r['aggregate_content_loss'] for r in results],
                loss_path, v_peak=_vp)
            if verbose:
                print(f'  Loss plot → {loss_path}')

    return results


def _print_summary_table(results):
    """Print a short summary table to stdout."""
    def _stats(vals):
        return min(vals), float(np.percentile(vals, 50)), max(vals)

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
        description='Batch run of the water ingress simulation over a set of '
                    'hydrograph files.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    input_group = p.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--depth-dir',
                   help='Directory containing hydrograph CSV files.')
    input_group.add_argument('--hydrograph-files', nargs='+', metavar='PATH_OR_REGEX',
                   help='One or more explicit file paths or regex patterns '
                        '(e.g. "hydrographs/0083.csv" or "hydrographs/008[0-9]\\.csv"). '
                        'Mutually exclusive with --depth-dir.')
    inputs.add_model_args(p)
    p.add_argument('--thresholds',   type=float, nargs='+',
                   default=_DEFAULT_THRESHOLDS,
                   metavar='H',
                   help='Absolute interior depth thresholds (m) for exceedance duration.')
    p.add_argument('--building-vulnerability', default=None,
                   help='CSV vulnerability curve: peak ground-floor depth → loss.')
    p.add_argument('--basement-vulnerability', default=None,
                   help='CSV vulnerability curve: peak basement depth → loss.')
    p.add_argument('--contents-loss-column', default='mean_repair_loss_GBP',
                   help='Loss column to read from the vulnerability CSVs.')
    p.add_argument('--outdir',       default='batch_results',
                   help='Output directory for batch_results.csv and batch_summary.csv.')
    p.add_argument('--save-timeseries', action='store_true', default=False,
                   help='Write time-series CSV and plot for each hydrograph '
                        '(timeseries_NNN.csv / .png).  Intended for single-event runs.')
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    config = inputs.config_from_args(args)
    paths, membranes = inputs.pathways_from_args(args)

    if args.hydrograph_files:
        cases = _discover_cases_from_files(args.hydrograph_files)
        if not cases:
            raise ValueError(f'No CSV files matched by --hydrograph-files: {args.hydrograph_files}')
    else:
        cases = _discover_cases(args.depth_dir)
        if not cases:
            raise ValueError(f'No CSV files found in: {args.depth_dir}')

    def _vuln(path):
        return (load_vulnerability_curve(path, loss_column=args.contents_loss_column)
                if path else None)

    run_batch(
        config, cases, paths, membranes,
        thresholds=args.thresholds,
        building_content_vulnerability=_vuln(args.building_vulnerability),
        basement_content_vulnerability=_vuln(args.basement_vulnerability),
        outdir=args.outdir,
        save_timeseries=args.save_timeseries,
        verbose=True,
    )


if __name__ == '__main__':
    main()
