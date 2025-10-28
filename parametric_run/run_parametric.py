#!/usr/bin/env python3
"""Run a small parametric sweep for the Flood Ingress Simulation.

Creates a CSV summary of results and (optionally) saves per-case plots.

Defaults are conservative; you can pass comma-separated lists or ranges of the
form start:stop:step for each parameter.

Example:
  python3 parametric_run/run_parametric.py --h_o 0.0,0.15,0.30 --A_o 0.003,0.006,0.009 --DT 1,5

Or with range syntax:
  python3 parametric_run/run_parametric.py --h_o 0:0.5:0.30 --A_o 0.001:0.01:0.0045 --DT 1:10:4

By default the script uses `example_run/example_external_levels.csv` as the
external hydrograph and a single dummy ingress defined by the combination of
parameters (h_o, A_o, coeff=0.6, name='dummy').
"""
import argparse
import csv
import math
import os
import sys
import tempfile
from itertools import product

import pathlib
import sys
# ensure repository root is on sys.path so we can import main and viz
repo_root = pathlib.Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from main import (Building, IngressPathway, Simulation, parse_external_file)
import viz


def parse_list_or_range(s):
    """Parse a string into a list of floats.

    Accepts comma-separated lists (e.g. "0.0,0.25,0.5") or a range in the
    form start:stop:step (inclusive of stop when it fits an integer number of
    steps).
    """
    if s is None:
        return []
    s = str(s).strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid range specification: {s}")
        start, stop, step = map(float, parts)
        if step == 0:
            raise ValueError("step cannot be zero")
        vals = []
        v = start
        # Use a safe loop to avoid fp accumulation issues
        while (step > 0 and v <= stop + 1e-12) or (step < 0 and v >= stop - 1e-12):
            vals.append(round(v, 12))
            v += step
        return vals
    # comma-separated
    items = [p.strip() for p in s.split(",") if p.strip()]
    return [float(x) for x in items]


def run_case(times, levels, h_o, A_o, dt_seconds, floor_area=50.0):
    building = Building(floor_area)
    ingress = [IngressPathway(height=float(h_o), area=float(A_o), coeff=0.6, name='dummy')]
    sim = Simulation(building, ingress, times, levels, dt=dt_seconds)
    times_out, levels_out = sim.run()
    return times_out, levels_out


def main(argv=None):
    parser = argparse.ArgumentParser(description='Parametric sweep for flood ingress')
    parser.add_argument('--external', default='example_run/example_external_levels.csv', help='External hydrograph CSV (time,level)')
    parser.add_argument('--h_o', default='0.0,0.25,0.5', help='Orifice height list or range (start:stop:step)')
    parser.add_argument('--A_o', default='0.001,0.005,0.01', help='Orifice area list or range')
    parser.add_argument('--DT', default='1,5,10', help='Simulation timestep(s) (in time-units)')
    parser.add_argument('--time-units', choices=['seconds', 'minutes', 'hours'], default='minutes', help='Units of the hydrograph and DT (default: minutes)')
    # default outdir placed under the parametric_run folder so outputs are
    # colocated with this script (user preference)
    parser.add_argument('--outdir', default='parametric_run/parametric_out', help='Output directory to save CSV and plots')
    parser.add_argument('--no-plots', action='store_true', help='Do not save per-case PNG plots')
    parser.add_argument('--temp-output', action='store_true', help='Write outputs to temporary directory and remove on exit')
    args = parser.parse_args(argv)

    # read external hydrograph
    times, levels = parse_external_file(args.external)

    # convert times to seconds internally
    mul = 1.0
    if args.time_units.startswith('min'):
        mul = 60.0
    elif args.time_units.startswith('hour'):
        mul = 3600.0
    times_sec = [t * mul for t in times]

    h_list = parse_list_or_range(args.h_o)
    A_list = parse_list_or_range(args.A_o)
    DT_list = parse_list_or_range(args.DT)

    if not h_list or not A_list or not DT_list:
        print('Empty parameter list; nothing to run')
        return 1

    # prepare output dir
    outdir = args.outdir
    temp_ctx = None
    if args.temp_output:
        temp_ctx = tempfile.TemporaryDirectory()
        outdir = temp_ctx.name
        print(f'Writing outputs to temporary directory: {outdir}')
    else:
        os.makedirs(outdir, exist_ok=True)

    csv_path = os.path.join(outdir, 'parametric_summary.csv')
    cases = []
    with open(csv_path, 'w', newline='') as cf:
        writer = csv.writer(cf)
        writer.writerow(['h_o', 'A_o', 'DT', 'final_h_in', 'max_h_in', 'n_steps', 'last_time'])

        for h_o, A_o, DT in product(h_list, A_list, DT_list):
            dt_seconds = float(DT) * mul
            print(f'Running h_o={h_o}, A_o={A_o}, DT={DT} (dt_seconds={dt_seconds})')
            sim_times, sim_levels = run_case(times_sec, levels, h_o, A_o, dt_seconds)
            final = sim_levels[-1] if sim_levels else 0.0
            peak = max(sim_levels) if sim_levels else 0.0
            n_steps = len(sim_times)
            last_time = sim_times[-1] if sim_times else 0.0
            writer.writerow([h_o, A_o, DT, final, peak, n_steps, last_time])

            # save full time-series CSV and (optionally) a styled plot for this case
            try:
                # display times in original units for plotting
                sim_times_display = [t / mul for t in sim_times]

                # resample external to simulation times (linear interpolation)
                sampled_external = []
                j = 0
                for t in sim_times:
                    while j < len(times_sec) - 1 and t >= times_sec[j+1]:
                        j += 1
                    if j < len(times_sec) - 1:
                        t1, h1 = times_sec[j], levels[j]
                        t2, h2 = times_sec[j+1], levels[j+1]
                        if t2 != t1:
                            frac = (t - t1) / (t2 - t1)
                            sampled_external.append(h1 + frac * (h2 - h1))
                        else:
                            sampled_external.append(h1)
                    else:
                        sampled_external.append(levels[-1])

                # save CSV of full time series for this case
                fname_base = f'sim_ho{h_o:.3f}_Ao{A_o:.6f}_dt{DT:.3f}'.replace(' ', '')
                csv_name = f'{fname_base}.csv'
                csv_path_case = os.path.join(outdir, csv_name)
                with open(csv_path_case, 'w', newline='') as tf:
                    w = csv.writer(tf)
                    w.writerow(['time', 'external_level', 'interior_level'])
                    for t_disp, h_out, h_in in zip(sim_times_display, sampled_external, sim_levels):
                        w.writerow([t_disp, h_out, h_in])

                # store case results for an aggregate overlay plot later
                cases.append({
                    'h_o': float(h_o),
                    'A_o': float(A_o),
                    'DT': float(DT),
                    'sim_times': sim_times_display,
                    'external': sampled_external,
                    'interior': sim_levels,
                    'csv': csv_path_case,
                    'png': os.path.join(outdir, f'{fname_base}.png') if not args.no_plots else None,
                })

                if not args.no_plots:
                    # determine style mapping: area -> greyscale (larger area -> darker),
                    # height -> linewidth, DT -> dash pattern
                    def normalize(v, vmin, vmax):
                        if vmax <= vmin:
                            return 0.5
                        return (v - vmin) / (vmax - vmin)

                    a_min, a_max = min(A_list), max(A_list)
                    h_min, h_max = min(h_list), max(h_list)
                    dt_min, dt_max = min(DT_list), max(DT_list)

                    a_norm = normalize(float(A_o), a_min, a_max)
                    h_norm = normalize(float(h_o), h_min, h_max)
                    dt_norm = normalize(float(DT), dt_min, dt_max)

                    # grayscale: 0=black, 1=white. Make larger area darker -> smaller value
                    shade = 0.9 - 0.7 * a_norm  # range ~0.9..0.2
                    color = str(max(0.0, min(1.0, shade)))

                    # linewidth mapping (height)
                    lw = 0.8 + 3.5 * h_norm

                    # dash patterns pool
                    dash_pool = [[], [6, 2], [4, 4], [2, 2], [10, 3, 2, 3]]
                    dash_idx = int(round(dt_norm * (len(dash_pool) - 1)))
                    dash_pattern = dash_pool[dash_idx]

                    # create plot
                    import matplotlib
                    matplotlib.use('Agg')
                    import matplotlib.pyplot as plt

                    fig, ax = plt.subplots(figsize=(8, 5))
                    ax.plot(sim_times_display, sampled_external, color='0.6', label='External Level (h_out)')

                    line_in, = ax.plot(sim_times_display, sim_levels, color=color, linewidth=lw, label='Indoor Level (h_in)')
                    if dash_pattern:
                        line_in.set_dashes(dash_pattern)

                    ax.set_xlabel(f'Time ({args.time_units})')
                    ax.set_ylabel('Water level (m)')
                    ax.set_title(f'h_o={h_o}, A_o={A_o}, DT={DT}')
                    ax.legend()
                    fig.tight_layout()

                    outpath = os.path.join(outdir, f'{fname_base}.png')
                    fig.savefig(outpath)
                    plt.close(fig)
            except Exception as e:
                print(f'Failed to save outputs for case {h_o},{A_o},{DT}: {e}')

    # After all cases, create an aggregate overlay plot with all interior traces
    try:
        if cases:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(10, 6))
            # plot original external hydrograph (in original units)
            # convert original times to display units
            times_display_orig = [t / mul for t in times]
            ax.plot(times_display_orig, levels, color='0.4', linewidth=1.2, label='External (orig)')

            # reuse normalization bounds
            a_min, a_max = min(A_list), max(A_list)
            h_min, h_max = min(h_list), max(h_list)
            dt_min, dt_max = min(DT_list), max(DT_list)

            def normalize(v, vmin, vmax):
                if vmax <= vmin:
                    return 0.5
                return (v - vmin) / (vmax - vmin)

            dash_pool = [[], [6, 2], [4, 4], [2, 2], [10, 3, 2, 3]]

            for c in cases:
                a_norm = normalize(c['A_o'], a_min, a_max)
                h_norm = normalize(c['h_o'], h_min, h_max)
                dt_norm = normalize(c['DT'], dt_min, dt_max)

                shade = 0.9 - 0.7 * a_norm
                color = str(max(0.0, min(1.0, shade)))
                lw = 0.8 + 3.5 * h_norm
                dash_idx = int(round(dt_norm * (len(dash_pool) - 1)))
                dash_pattern = dash_pool[dash_idx]

                label = f"h={c['h_o']}, A={c['A_o']}, DT={c['DT']}"
                line, = ax.plot(c['sim_times'], c['interior'], color=color, linewidth=lw, label=label)
                if dash_pattern:
                    line.set_dashes(dash_pattern)

            ax.set_xlabel(f'Time ({args.time_units})')
            ax.set_ylabel('Water level (m)')
            ax.set_title('Parametric sweep: interior levels overlay')
            # show legend (may be large)
            ax.legend(fontsize='small', ncol=1)
            fig.tight_layout()
            agg_path = os.path.join(outdir, 'aggregate_overlay.png')
            fig.savefig(agg_path)
            plt.close(fig)
            print(f'Aggregate overlay plot saved to: {agg_path}')
    except Exception as e:
        print(f'Failed to create aggregate overlay plot: {e}')

    print(f'Parametric summary written to: {csv_path}')
    if temp_ctx is not None:
        try:
            temp_ctx.cleanup()
            print('(Temporary outputs removed)')
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
