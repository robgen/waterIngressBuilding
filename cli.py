#!/usr/bin/env python3
"""cli.py — command-line entry point for a single-hydrograph run.

Parses arguments, builds SimConfig + Hydrograph + pathways (inputs.py) and
runs either one replicate (--n-replicates 1) or the Monte Carlo ensemble
(fragility.run), then writes the outputs.
"""

import argparse
import csv
import os
import tempfile

import numpy as np

import engine
import forces
import fragility
import inputs
import plot


def _build_argparser():
    p = argparse.ArgumentParser(description='Water Ingress Building Simulation')
    p.add_argument('--external', '-e', required=True,
                   help='External depth hydrograph CSV (time, level[, velocity]).')
    inputs.add_model_args(p)

    # ── outputs ───────────────────────────────────────────────────────────────
    p.add_argument('--outdir', '-o', default='.',
                   help='Output directory.')
    p.add_argument('--temp-output', action='store_true',
                   help='Write to a temporary directory removed on exit.')
    p.add_argument('--animate', action='store_true',
                   help='Write a GIF animation (slow).')
    p.add_argument('--verbose', '-v', action='store_true')

    # ── parameters related to forces ──────────────────────────────────────────
    p.add_argument('--compute-forces', action='store_true')
    p.add_argument('--building-width', type=float, default=10.0)
    p.add_argument('--drag-coeff', type=float, default=1.0)
    p.add_argument('--rho', type=float, default=1000.0)

    return p


def main(argv=None):
    args = _build_argparser().parse_args(argv)

    outdir = args.outdir
    temp_ctx = None
    if args.temp_output:
        temp_ctx = tempfile.TemporaryDirectory()
        outdir = temp_ctx.name
    else:
        os.makedirs(outdir, exist_ok=True)

    config = inputs.config_from_args(
        args,
        compute_forces=args.compute_forces,
        building_width=args.building_width,
        drag_coeff=args.drag_coeff,
        rho=args.rho,
        animate=args.animate,
        verbose=args.verbose,
    )
    hydro = engine.read_hydrograph(args.external, time_units=config.time_units,
                                   velocity_mode=config.velocity_mode)
    paths, membranes = inputs.pathways_from_args(args)
    mul = engine.TIME_UNIT_SECONDS[config.time_units]

    try:
        plot.save_run_schematic(
            os.path.join(outdir, 'schematic.png'),
            pathways=paths, membranes=membranes, config=config,
            label=os.path.splitext(os.path.basename(args.ingress))[0] if args.ingress else '',
        )
    except Exception as exc:
        if args.verbose:
            print(f'Schematic skipped: {exc}')

    plot.save_external_preview([t / mul for t in hydro.times], hydro.levels,
                               os.path.join(outdir, 'external_preview.png'))

    if config.n_replicates > 1:
        print(f'Running Monte Carlo: {config.n_replicates} replicates …')
        mc = fragility.run(config, hydro, paths, membranes)
        fragility.write_replicates_csv(mc, os.path.join(outdir, 'fragility_replicates.csv'))
        fragility.write_summary_csv(mc,    os.path.join(outdir, 'fragility_summary.csv'))
        fragility.write_state_freq_csv(mc, os.path.join(outdir, 'fragility_state_freq.csv'))
        p50 = mc.percentiles.get('peak_h_in', {}).get('P50', float('nan'))
        print(f'P50 peak interior depth: {p50:.4f} m')
    else:
        print('Running simulation…')
        result, _ = fragility.run_replicate(
            config, hydro, paths, membranes, np.random.default_rng(config.random_seed))
        h_ext, v_ext = engine.exterior_series(config, hydro, result.times)

        try:
            plot.save_velocity_preview([t / mul for t in result.times], v_ext,
                                       os.path.join(outdir, 'velocity_preview.png'),
                                       time_unit=config.time_units)
        except Exception:
            pass

        plot.save_run_result(os.path.join(outdir, 'simulation_result.png'),
                             config, hydro, result)
        print(f'Simulation result saved to {outdir}/simulation_result.png')

        if config.compute_forces:
            _save_forces(result, h_ext, v_ext, config, outdir)

        if config.animate:
            anim_path = os.path.join(outdir, 'simulation_animation.gif')
            try:
                plot.save_run_animation(anim_path, config, hydro, result, paths)
                print(f'Animation saved to {anim_path}')
            except Exception as exc:
                print(f'Animation failed: {exc}')

    print('Done.')
    if temp_ctx:
        temp_ctx.cleanup()


def _save_forces(result, h_ext, v_ext, config, outdir):
    forces_out = []
    for i, t in enumerate(result.times):
        H_net = max(0.0, h_ext[i] - result.h_in[i])
        H_wet = max(0.0, h_ext[i])
        res = forces.compute_combined_forces(
            H_net, H_wet, v_ext[i], config.building_width,
            C_D=config.drag_coeff, rho=config.rho,
        )
        forces_out.append((t, res['F_hydro'], res['F_drag'], res['F_total'],
                           res['M_overturn'], H_net, H_wet, v_ext[i],
                           res['lever_hydro'], res['lever_drag']))
    forces_csv = os.path.join(outdir, 'forces.csv')
    with open(forces_csv, 'w', newline='') as cf:
        w = csv.writer(cf)
        w.writerow(['time', 'F_hydro_N', 'F_drag_N', 'F_total_N', 'M_overturn_Nm',
                    'H_net_m', 'H_wet_m', 'v_m_per_s', 'lever_hydro_m', 'lever_drag_m'])
        for row in forces_out:
            w.writerow(row)
    mul = engine.TIME_UNIT_SECONDS[config.time_units]
    try:
        plot.save_forces_result(
            [t / mul for t in result.times], forces_out,
            os.path.join(outdir, 'forces_result.png'),
            time_unit=config.time_units,
        )
    except Exception as exc:
        print(f'Forces plot skipped: {exc}')


if __name__ == '__main__':
    main()
