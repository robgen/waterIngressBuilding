#!/usr/bin/env python3
"""Timestep sensitivity analysis for Case 06 (basement + sump/pump that keeps up).

Demonstrates that the explicit-Euler sump/pump update oscillates when dt
is too coarse for the pump, and compares the sweep with the stability limit
used by the engine's warning (SumpPump.max_stable_dt):

    dt  ≤  dt_max  =  0.5 × A_sump × h_on / Q_p,max      (Q_p,max at h_lift = 0)

Produces:
  examples/ex06/out/dt_sensitivity.png
"""
import os
import sys
import warnings

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import plot  # noqa: F401 — sets Agg backend and shared rcParams as side-effect
import engine
import reference_cases as rc
from pump import SumpPump

# ── Case 06 parameters (must match run_examples.py) ──────────────────────────────
FLOOR_AREA           = 50.0
BASEMENT_AREA        = 30.0
BASEMENT_FLOOR_ELEV  = -2.5
BASEMENT_INGRESS_H   = 0.0
BASEMENT_INGRESS_A   = 0.005
BASEMENT_INGRESS_CD  = 0.5
SUMP_AREA            = 0.5
SUMP_BASE_ELEV       = -3.3                     # pit 0.8 m below the basement floor
SUMP_DEPTH           = BASEMENT_FLOOR_ELEV - SUMP_BASE_ELEV
PUMP_ON_LEVEL        = 0.10
PUMP_OFF_LEVEL       = 0.02
PUMP_SHUTOFF_HEAD    = 5.0
PUMP_CURVE_COEFF     = 1000.0
PIPE_LOSS_COEFF      = 0.0
PUMP_AVAIL           = 1.0

# Shared triangular hydrograph (0→0.5 m at 30 min, recession to 0 at 60 min,
# dry tail to 360 min — same as run_examples.py)
HYDRO = rc.hydro([(0, 0.0), (30, 0.5), (60, 0.0), (360, 0.0)])
MODEL = rc.F.assemble_pathways(
    [rc.path('never_reached', 10.0, 0.001)],   # no ground-floor path
    [rc.path('perimeter', BASEMENT_INGRESS_H, BASEMENT_INGRESS_A, BASEMENT_INGRESS_CD)])

# ── dt sweep ──────────────────────────────────────────────────────────────────
# From the default 60-s step down to a reference below the stability limit.
DT_VALUES_S = [60.0, 30.0, 10.0, 5.0, 2.0, 1.0, 0.5, 0.25]
DT_LABELS   = ['60 s', '30 s', '10 s', '5 s', '2 s', '1 s', '0.5 s', '0.25 s  (ref., ≤ dt_max)']
DT_COLOURS  = ['#c0392b', '#e67e22', '#f39c12', '#d4ac0d', '#2980b9', '#27ae60', '#16a085', '#1abc9c']
DT_LW       = [2.0,       1.8,       1.8,       1.8,       2.0,       2.0,       2.0,       1.4]
DT_LS       = ['-',       '-',       '-',       '-',       '-',       '-',       '-',       '--']

G = 9.81


def _build_sump() -> SumpPump:
    return SumpPump(
        sump_area           = SUMP_AREA,
        sump_base_elevation = SUMP_BASE_ELEV,
        pump_on_level       = PUMP_ON_LEVEL,
        pump_off_level      = PUMP_OFF_LEVEL,
        pump_shutoff_head   = PUMP_SHUTOFF_HEAD,
        pump_curve_coeff    = PUMP_CURVE_COEFF,
        pipe_loss_coeff     = PIPE_LOSS_COEFF,
        pump_availability   = PUMP_AVAIL,
    )


def run_case(dt_s: float):
    """Run Case 06 at a given dt.  Returns (times_min, h_sump, h_bsmt, h_ext)."""
    cfg = engine.SimConfig(
        floor_area=FLOOR_AREA, dt=dt_s,
        basement_area=BASEMENT_AREA,
        basement_floor_elevation=BASEMENT_FLOOR_ELEV,
        basement_ceiling_elevation=0.0,          # ground level
        sumppump=_build_sump(),
    )
    r = rc.run_one(cfg, HYDRO, MODEL)
    h_ext, _ = engine.exterior_series(cfg, HYDRO, r.times)
    times_min = [t / 60.0 for t in r.times]
    return times_min, r.h_sump, r.h_basement, h_ext


def main():
    outdir = os.path.join(HERE, 'ex06', 'out')
    os.makedirs(outdir, exist_ok=True)
    # The sweep runs steps above the limit on purpose.
    warnings.simplefilter('ignore', engine.PumpStepWarning)

    sump = _build_sump()
    Q_max   = sump.max_pump_flow()
    dt_crit = sump.max_stable_dt()
    print(f'  Q_p,max (h_lift = 0) = {Q_max:.4f} m³/s')
    print(f'  dt_max = 0.5 × A_sump × h_on / Q_p,max = 0.5 × {SUMP_AREA} × {PUMP_ON_LEVEL} / {Q_max:.4f} ≈ {dt_crit:.3f} s')

    # ── collect results ───────────────────────────────────────────────────────
    runs = []
    for dt_s, label, col, lw, ls in zip(
            DT_VALUES_S, DT_LABELS, DT_COLOURS, DT_LW, DT_LS):
        t_min, h_sp, h_bs, h_ext = run_case(dt_s)
        peak_sp  = max(h_sp)
        peak_bs  = max(h_bs)
        ratio    = dt_s / dt_crit
        runs.append(dict(dt_s=dt_s, label=label, col=col, lw=lw, ls=ls,
                         t_min=t_min, h_sp=h_sp, h_bs=h_bs, h_ext=h_ext,
                         peak_sp=peak_sp, peak_bs=peak_bs, ratio=ratio))
        print(f'  dt={dt_s:5g} s  dt/dt_max={ratio:.2f}  '
              f'peak_h_sump={peak_sp:.4f} m  peak_h_bsmt={peak_bs:.4f} m')

    ref = runs[-1]   # 0.25-s reference

    # ── figure ────────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 9))
    gs  = gridspec.GridSpec(2, 2, figure=fig,
                            hspace=0.50, wspace=0.38,
                            left=0.07, right=0.97,
                            top=0.88, bottom=0.09)

    # ── (0,:)  h_sump time-series ─────────────────────────────────────────────
    ax_ts = fig.add_subplot(gs[0, :])

    # exterior hydrograph (background)
    t_ext_fine  = np.linspace(0, 120, 1440)
    h_ext_fine  = np.interp(t_ext_fine,
                            [t / 60.0 for t in HYDRO.times], HYDRO.levels)
    ax_ts.fill_between(t_ext_fine, h_ext_fine,
                       alpha=0.07, color='#7f8c8d', zorder=1)
    ax_ts.plot(t_ext_fine, h_ext_fine,
               color='#7f8c8d', lw=1.4, ls='--', zorder=4,
               label='External  $h_{ext}$')

    # sump top (basement floor)
    ax_ts.axhline(SUMP_DEPTH, color='#8e44ad', lw=0.9, ls=':',
                  alpha=0.55, zorder=2, label=f'Sump top (basement floor)  {SUMP_DEPTH:.1f} m')

    for r in runs:
        ax_ts.plot(r['t_min'], r['h_sp'],
                   color=r['col'], lw=r['lw'], ls=r['ls'], zorder=3,
                   label=f"Δt = {r['label']}  (peak = {r['peak_sp']:.3f} m)")

    ax_ts.set_xlabel('Time  (min)')
    ax_ts.set_ylabel('Sump depth  $h_{sump}$  (m)')
    ax_ts.set_title('Sump depth time-series — explicit Euler at varying Δt\n'
                    f'Case 06: A_sump = {SUMP_AREA} m²,  '
                    f'h_on = {PUMP_ON_LEVEL} m,  '
                    f'Q_p,max ≈ {Q_max:.4f} m³/s,  '
                    f'dt_max ≈ {dt_crit:.3f} s')
    ax_ts.set_xlim(0, 120)
    ax_ts.set_ylim(bottom=0)
    ax_ts.legend(fontsize=8, loc='upper right', ncol=2)

    # ── (1,0)  peak h_bsmt vs dt ──────────────────────────────────────────────
    ax_bsmt = fig.add_subplot(gs[1, 0])
    dt_arr  = np.array([r['dt_s'] for r in runs])
    pb_arr  = np.array([r['peak_bs'] for r in runs])

    for r in runs:
        ax_bsmt.scatter(r['dt_s'], r['peak_bs'] * 1000,
                        s=70, color=r['col'], zorder=5,
                        edgecolors='white', lw=0.8)
    ax_bsmt.plot(dt_arr, pb_arr * 1000,
                 color='#2c3140', lw=1.2, ls='-', zorder=3)
    ax_bsmt.axhline(ref['peak_bs'] * 1000, color='#1abc9c', lw=1.0, ls='--',
                    label=f'Ref. 0.25 s  ({ref["peak_bs"]*1000:.1f} mm)')
    ax_bsmt.axvline(dt_crit, color='#c0392b', lw=1.2, ls='--', alpha=0.7,
                    label=f'dt_max ≈ {dt_crit:.3f} s')

    ax_bsmt.set_xlabel('Timestep  Δt  (s)')
    ax_bsmt.set_ylabel('Peak basement depth  (mm)')
    ax_bsmt.set_title('Peak $h_{bsmt}$ vs Δt\n(should be ≈ 0 when pump keeps up)')
    ax_bsmt.legend(fontsize=8)
    ax_bsmt.set_xlim(left=0)
    ax_bsmt.set_ylim(bottom=0)
    ax_bsmt.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))

    # ── (1,1)  guidance text panel ────────────────────────────────────────────
    ax_guide = fig.add_subplot(gs[1, 1])
    ax_guide.axis('off')

    guidance = (
        'Timestep guideline for sump/pump systems\n'
        '─────────────────────────────────────────\n\n'
        'The explicit-Euler update drains the sump\n'
        'by  ΔV = Q_pump × dt  each step.\n\n'
        'If  ΔV > A_sump × h_on,  the sump is emptied\n'
        'in one step, causing the level to oscillate\n'
        'between h_on and 0 at every other timestep.\n'
        'This can make the pit spill spuriously.\n\n'
        'Stability limit (one step drains at most half\n'
        'the switch-on volume at the maximum rate):\n\n'
        '   dt  ≤  0.5 × A_sump × h_on / Q_p,max\n\n'
        f'Case 06 values:\n'
        f'   A_sump  = {SUMP_AREA} m²\n'
        f'   h_on    = {PUMP_ON_LEVEL} m\n'
        f'   Q_p,max ≈ {Q_max:.4f} m³/s  (h_lift = 0)\n\n'
        f'   →  dt_max ≈ {dt_crit:.3f} s\n\n'
        'The model warns when the step is larger.\n\n'
        'Note: where no sump is configured, the\n'
        'tighter basement fill timescale governs\n'
        '(τ_bsmt = A_bsmt × Δz / Q_in).'
    )
    ax_guide.text(0.04, 0.97, guidance,
                  transform=ax_guide.transAxes,
                  va='top', ha='left', fontsize=8.5,
                  fontfamily='monospace',
                  bbox=dict(boxstyle='round,pad=0.6', fc='#f4f6f9',
                            ec='#d0d5dd', alpha=0.97))

    # ── figure title ──────────────────────────────────────────────────────────
    fig.suptitle(
        'Case 06 — Timestep sensitivity: sump/pump oscillation at large Δt',
        fontsize=12, fontweight='bold', color='#1e2433', y=0.96)

    out = os.path.join(outdir, 'dt_sensitivity.png')
    fig.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  Saved {out}')


if __name__ == '__main__':
    main()
