#!/usr/bin/env python3
"""cli.py — command-line entry point for the water ingress simulation.

This is a thin shim: it parses arguments, builds SimConfig + Hydrograph +
pathway lists, then delegates all computation to engine, fragility, or batch.

Key differences from the old main.py CLI:
  • --sumppump-*     : unified prefix for sump + pump flags (was --sump-* / --pump-*)
  • --basement-ingress PATH : replaces indexed --basement-ingress-* flags
  • --ingress        : unified header-based CSV format only (no legacy positional format)
  • Plotting imported from plot (not viz) internally; viz is still available as alias
"""

import argparse
import csv
import os
import sys
import tempfile

import forces
import engine
import fragility as _frag
import plot as _plot

_MUL = {'seconds': 1.0, 'minutes': 60.0, 'hours': 3600.0}


def _build_argparser():
    p = argparse.ArgumentParser(description='Water Ingress Building Simulation')

    # ── hydrograph ────────────────────────────────────────────────────────────
    p.add_argument('--external', '-e', required=True,
                   help='External depth hydrograph CSV (time, level).')
    p.add_argument('--velocity-mode', default='zero',
                   choices=['zero', 'power_law', 'file'],
                   help="Velocity mode: 'zero' (default), 'power_law' (v=a·h^b), or 'file' (CSV).")
    p.add_argument('--velocity-power-law-a', type=float, default=1.5,
                   help='Power-law coefficient a in v=a·h^b. Default: 1.5.')
    p.add_argument('--velocity-power-law-b', type=float, default=0.5,
                   help='Power-law exponent b in v=a·h^b. Default: 0.5.')

    # ── ingress pathways ──────────────────────────────────────────────────────
    p.add_argument('--ingress', '-i', default=None,
                   help='Ground-floor ingress pathways CSV (unified format). '
                        'Omit for basement-only cases with no ground-floor pathway.')
    p.add_argument('--basement-ingress', default=None,
                   help='Exterior→basement perimeter opening CSV (unified format, '
                        'typically one row).')
    p.add_argument('--membrane', default=None,
                   help='Membrane CSV (unified format; rows with group_id > 0 '
                        'and fragility state columns).')

    # ── building geometry ─────────────────────────────────────────────────────
    p.add_argument('--floor', '-f', type=float, required=True,
                   help='Ground-floor plan area (m²).')

    # ── basement ──────────────────────────────────────────────────────────────
    p.add_argument('--basement-area', type=float, default=0.0,
                   help='Basement plan area (m²). If >0, a basement zone is created.')
    p.add_argument('--basement-floor-elevation', type=float, default=None,
                   help='Basement floor elevation relative to datum (m, negative = below).')
    p.add_argument('--basement-ceiling-elevation', type=float, default=0.0,
                   help='Basement ceiling elevation on the datum (m). Default: 0.')
    p.add_argument('--basement-bypass-height', type=float, default=None,
                   help='Sill of the ground↔basement bypass connection (m).')
    p.add_argument('--basement-bypass-area', type=float, default=0.0,
                   help='Area of the ground↔basement bypass (m²).')

    # ── sump + pump (always used together, --sumppump-* prefix) ──────────────
    p.add_argument('--sumppump-area', type=float, default=0.0,
                   help='Sump plan area (m²). >0 activates the sump+pump module.')
    p.add_argument('--sumppump-base-elevation', type=float, default=None)
    p.add_argument('--sumppump-overflow-level', type=float, default=None)
    p.add_argument('--sumppump-overflow-coeff', type=float, default=1.8)
    p.add_argument('--sumppump-overflow-exponent', type=float, default=1.5)
    p.add_argument('--sumppump-on-level', type=float, default=None)
    p.add_argument('--sumppump-off-level', type=float, default=None)
    p.add_argument('--sumppump-shutoff-head', type=float, default=None)
    p.add_argument('--sumppump-curve-coeff', type=float, default=None)
    p.add_argument('--sumppump-pipe-loss-coeff', type=float, default=0.0)
    p.add_argument('--sumppump-availability', type=float, default=1.0)

    # ── simulation parameters ─────────────────────────────────────────────────
    p.add_argument('--dt', type=float, default=None,
                   help='Simulation timestep (in --time-units). Default: 1 unit.')
    p.add_argument('--time-units', '-u', default='minutes',
                   choices=['seconds', 'minutes', 'hours'])
    p.add_argument('--outdir', '-o', default='.',
                   help='Output directory.')
    p.add_argument('--temp-output', action='store_true',
                   help='Write to a temporary directory removed on exit.')
    p.add_argument('--animate', action='store_true',
                   help='Write a GIF animation (slow).')
    p.add_argument('--verbose', '-v', action='store_true')

    # ── Monte Carlo ───────────────────────────────────────────────────────────
    p.add_argument('--n-replicates', type=int, default=1,
                   help='Number of Monte Carlo replicates. >1 triggers fragility mode.')
    p.add_argument('--random-seed', type=int, default=None)
    p.add_argument('--output-percentiles', nargs='+', type=int,
                   default=[10, 25, 50, 75, 90])

    # ── parameters related to forces ──────────────────────────────────────────
    p.add_argument('--compute-forces', action='store_true')
    p.add_argument('--building-width', type=float, default=10.0)
    p.add_argument('--drag-coeff', type=float, default=1.0)
    p.add_argument('--rho', type=float, default=1000.0)

    return p


def _build_config(args) -> engine.SimConfig:
    mul = _MUL.get(args.time_units, 60.0)
    dt_sec = (args.dt if args.dt is not None else 1.0) * mul

    from pump import SumpPump
    sumppump = None
    if args.sumppump_area and args.sumppump_area > 0.0:
        required = ['sumppump_base_elevation', 'sumppump_overflow_level',
                    'sumppump_on_level', 'sumppump_off_level',
                    'sumppump_shutoff_head', 'sumppump_curve_coeff']
        missing = [k for k in required if getattr(args, k, None) is None]
        if missing:
            print(f'WARNING: --sumppump-area set but missing: {[k.replace("_", "-") for k in missing]}. Sump disabled.')
        else:
            sumppump = SumpPump(
                sump_area=args.sumppump_area,
                sump_base_elevation=args.sumppump_base_elevation,
                overflow_level=args.sumppump_overflow_level,
                overflow_coeff=args.sumppump_overflow_coeff,
                overflow_exponent=args.sumppump_overflow_exponent,
                pump_on_level=args.sumppump_on_level,
                pump_off_level=args.sumppump_off_level,
                pump_shutoff_head=args.sumppump_shutoff_head,
                pump_curve_coeff=args.sumppump_curve_coeff,
                pipe_loss_coeff=args.sumppump_pipe_loss_coeff,
                pump_availability=args.sumppump_availability,
            )

    return engine.SimConfig(
        floor_area=args.floor,
        dt=dt_sec,
        basement_area=getattr(args, 'basement_area', 0.0) or 0.0,
        basement_floor_elevation=getattr(args, 'basement_floor_elevation', None) or 0.0,
        basement_ceiling_elevation=getattr(args, 'basement_ceiling_elevation', 0.0) or 0.0,
        basement_connection_height=getattr(args, 'basement_bypass_height', None),
        basement_connection_area=getattr(args, 'basement_bypass_area', 0.0) or 0.0,
        sumppump=sumppump,
        n_replicates=args.n_replicates,
        random_seed=args.random_seed,
        output_percentiles=tuple(args.output_percentiles),
        velocity_mode=args.velocity_mode,
        velocity_power_law_a=args.velocity_power_law_a,
        velocity_power_law_b=args.velocity_power_law_b,
        time_units=args.time_units,
        compute_forces=args.compute_forces,
        building_width=args.building_width,
        drag_coeff=args.drag_coeff,
        rho=args.rho,
        animate=args.animate,
        verbose=args.verbose,
    )


def _build_hydro(args, config: engine.SimConfig) -> engine.Hydrograph:
    mul = _MUL.get(config.time_units, 60.0)
    raw_times, levels, inline_vel = engine.parse_combined_file(args.external)
    times_s = [t * mul for t in raw_times]

    v_times_s, velocities = None, None
    if config.velocity_mode == 'file':
        if inline_vel is not None:
            v_times_s = times_s
            velocities = inline_vel
        else:
            raise ValueError(
                '--velocity-mode=file requires a 3-column hydrograph '
                '(time, depth, velocity) but the supplied file has only 2 columns.'
            )

    return engine.Hydrograph(times=times_s, levels=levels,
                             vel_times=v_times_s, velocities=velocities)


def _build_pathways(args):
    """Parse --ingress, --basement-ingress, --membrane and return (paths, membranes, basement_pathway)."""
    paths = _frag.parse_pathway_file(args.ingress) if args.ingress else []
    _frag.validate_fragility_inputs(paths, [])

    basement_pathway = None
    if args.basement_ingress:
        bsmt_paths = _frag.parse_pathway_file(args.basement_ingress)
        if bsmt_paths:
            bp = bsmt_paths[0]
            basement_pathway = engine.IngressPathway(
                height=bp.height_m, area=bp.area_m2, coeff=bp.Cd,
                name=bp.name, source='outside', target='basement',
            )

    membranes = []
    if args.membrane:
        raw = _frag.parse_pathway_file(args.membrane)
        membranes = [_frag.fragile_path_to_membrane(fp) for fp in raw
                     if fp.group_id > 0 and fp.fragility is not None]
        if membranes:
            _frag.assign_representative_paths(paths, membranes)

    return paths, membranes, basement_pathway


def main(argv=None):
    parser = _build_argparser()
    args = parser.parse_args(argv)

    outdir = args.outdir
    temp_ctx = None
    if args.temp_output:
        temp_ctx = tempfile.TemporaryDirectory()
        outdir = temp_ctx.name
    else:
        os.makedirs(outdir, exist_ok=True)

    mul = _MUL.get(args.time_units, 60.0)
    config = _build_config(args)
    hydro = _build_hydro(args, config)
    paths, membranes, basement_pathway = _build_pathways(args)

    # Building schematic (replaces ingress_preview + ingress_locations)
    try:
        bsmt_d = (abs(config.basement_floor_elevation)
                  if config.basement_area > 0 else None)
        _bsmt_paths_sch = [basement_pathway] if basement_pathway is not None else []
        _plot.save_run_schematic(
            os.path.join(outdir, 'schematic.png'),
            gf_pathways=paths,
            bsmt_pathways=_bsmt_paths_sch,
            membranes=membranes,
            basement_depth=bsmt_d,
            has_sump=config.sumppump is not None,
            has_pump=config.sumppump is not None,
            bypass_height=float(config.basement_connection_height or 0.0),
            label=os.path.splitext(os.path.basename(args.ingress))[0] if args.ingress else '',
        )
    except Exception as exc:
        if args.verbose:
            print(f'Schematic skipped: {exc}')

    # Plots that don't depend on simulation results
    orig_times = [t / mul for t in hydro.times]
    _plot.save_external_preview(orig_times, hydro.levels, os.path.join(outdir, 'external_preview.png'))

    # ── Monte Carlo path ──────────────────────────────────────────────────────
    if config.n_replicates > 1:
        print(f'Running Monte Carlo: {config.n_replicates} replicates …')
        mc = _frag.run(config, hydro, paths, membranes=membranes, basement_pathway=basement_pathway)
        _frag.write_replicates_csv(mc, os.path.join(outdir, 'fragility_replicates.csv'))
        _frag.write_summary_csv(mc,    os.path.join(outdir, 'fragility_summary.csv'))
        _frag.write_state_freq_csv(mc, os.path.join(outdir, 'fragility_state_freq.csv'))
        p50 = mc.percentiles.get('peak_h_in', {}).get('P50', float('nan'))
        print(f'P50 peak interior depth: {p50:.4f} m')
        print('Done.')
        if temp_ctx:
            temp_ctx.cleanup()
        return

    # ── Deterministic path ────────────────────────────────────────────────────
    # Build conductance resolver for any fragility paths (resolves to base state)
    has_fragility = any(p.fragility is not None for p in paths) or bool(membranes)
    if has_fragility:
        from fragility import sample_all_thresholds, make_conductance_resolver, make_basement_step_resolver
        import numpy as np
        # Single deterministic draw at u=0.5 (median state) for display
        rng = np.random.default_rng(config.random_seed)
        sampled = sample_all_thresholds(paths, membranes, None, rng)
        resolver = make_conductance_resolver(paths, membranes, sampled)
        deterministic_paths = []
        conductance_resolver = resolver
    else:
        conductance_resolver = None
        deterministic_paths = [
            engine.IngressPathway(height=p.height_m, area=p.area_m2, coeff=p.Cd, name=p.name)
            for p in paths
        ]

    print('Running simulation…')
    result = engine.run(config, hydro, deterministic_paths,
                        basement_pathway=basement_pathway,
                        conductance_resolver=conductance_resolver)

    sim_times_display = [t / mul for t in result.times]
    sampled_ext = engine.sample_with_zero_padding(result.times, hydro.times, hydro.levels)
    if config.velocity_mode == 'file' and hydro.vel_times and hydro.velocities:
        sampled_vel = engine.sample_with_zero_padding(result.times, hydro.vel_times, hydro.velocities)
    elif config.velocity_mode == 'power_law':
        sampled_vel = [config.velocity_power_law_a * (max(0.0, h) ** config.velocity_power_law_b)
                       for h in sampled_ext]
    else:
        sampled_vel = [0.0] * len(result.times)

    # velocity preview
    try:
        _plot.save_velocity_preview(sim_times_display, sampled_vel,
                                    os.path.join(outdir, 'velocity_preview.png'),
                                    time_unit=config.time_units)
    except Exception:
        pass

    bsmt_max = (max(0.0, config.basement_ceiling_elevation - config.basement_floor_elevation)
                if config.basement_area > 0 else None)
    sump_ov = config.sumppump.overflow_level if config.sumppump else None

    sim_basement = result.h_basement if result.h_basement else None
    sim_sump = result.h_sump if result.h_sump else None

    _plot.save_simulation_result(
        sim_times_display, result.h_in, sampled_ext,
        os.path.join(outdir, 'simulation_result.png'),
        time_unit=config.time_units,
        basement_levels=sim_basement,
        velocity_series=sampled_vel,
        sump_levels=sim_sump,
        basement_max_depth=bsmt_max,
        sump_overflow_level=sump_ov,
    )
    print(f"Simulation result saved to {outdir}/simulation_result.png")

    if config.compute_forces:
        _save_forces(result, sampled_ext, sampled_vel, config, mul, outdir)

    if config.animate:
        _anim_paths = [
            engine.IngressPathway(height=p.height_m, area=p.area_m2, coeff=p.Cd, name=p.name)
            for p in paths
        ]
        _save_animation(result, _anim_paths, sampled_ext, sampled_vel,
                        config, mul, outdir)

    print('Done.')
    if temp_ctx:
        temp_ctx.cleanup()


def _save_forces(result, sampled_ext, sampled_vel, config, mul, outdir):
    forces_out = []
    for i, t in enumerate(result.times):
        h_out_i = sampled_ext[i]
        h_in_i = result.h_in[i]
        v_i = sampled_vel[i] if i < len(sampled_vel) else 0.0
        H_net = max(0.0, h_out_i - h_in_i)
        H_wet = max(0.0, h_out_i)
        res = forces.compute_combined_forces(
            H_net, H_wet, v_i, config.building_width,
            C_D=config.drag_coeff, rho=config.rho,
        )
        forces_out.append((t, res['F_hydro'], res['F_drag'], res['F_total'],
                           res['M_overturn'], H_net, H_wet, v_i,
                           res['lever_hydro'], res['lever_drag']))
    forces_csv = os.path.join(outdir, 'forces.csv')
    with open(forces_csv, 'w', newline='') as cf:
        w = csv.writer(cf)
        w.writerow(['time', 'F_hydro_N', 'F_drag_N', 'F_total_N', 'M_overturn_Nm',
                    'H_net_m', 'H_wet_m', 'v_m_per_s', 'lever_hydro_m', 'lever_drag_m'])
        for row in forces_out:
            w.writerow(row)
    try:
        _plot.save_forces_result(
            [t / mul for t in result.times], forces_out,
            os.path.join(outdir, 'forces_result.png'),
            time_unit=config.time_units,
        )
    except Exception as exc:
        print(f'Forces plot skipped: {exc}')


def _save_animation(result, ingress_list, sampled_ext, sampled_vel, config, mul, outdir):
    anim_path = os.path.join(outdir, 'simulation_animation.gif')
    sim_times_display = [t / mul for t in result.times]
    sim_basement_abs = (
        [config.basement_floor_elevation + hb for hb in result.h_basement]
        if result.h_basement else None
    )
    try:
        _plot.generate_animation(
            sim_times_display, result.h_in, sampled_ext,
            ingress_list, anim_path,
            time_unit=config.time_units,
            basement_levels=result.h_basement or None,
            basement_abs_levels=sim_basement_abs,
            velocity_series=sampled_vel,
            sump_levels=result.h_sump or None,
            sump_overflow_level=config.sumppump.overflow_level if config.sumppump else None,
            Q_perim_series=result.trace.get('Q_ext_perimeter'),
            Q_bypass_series=result.trace.get('Q_b_bs'),
        )
        print(f'Animation saved to {anim_path}')
    except Exception as exc:
        print(f'Animation failed: {exc}')


if __name__ == '__main__':
    main()
