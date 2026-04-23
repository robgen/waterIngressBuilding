#!/usr/bin/env python3
"""Timestep sensitivity analysis for Case 05 (basement + sump/pump that keeps up).

Demonstrates that the explicit-Euler sump/pump update oscillates when dt
exceeds the pump drain time of the active sump volume.  Derives the
practical dt guideline:

    dt  ≤  dt_crit  =  A_sump × h_on / Q_pump_peak

Produces:
  examples/ex05/out/dt_sensitivity.png
"""
import copy
import math
import os
import sys

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import plot  # noqa: F401 — sets Agg backend and shared rcParams as side-effect
from engine import Building, IngressPathway, Simulation, sample_with_zero_padding
from pump import SumpPump

# ── Case 05 parameters (must match run_examples.py) ──────────────────────────────
FLOOR_AREA           = 50.0
BASEMENT_AREA        = 30.0
BASEMENT_FLOOR_ELEV  = -2.5
BASEMENT_INGRESS_H   = 0.0
BASEMENT_INGRESS_A   = 0.005
BASEMENT_INGRESS_CD  = 0.5
SUMP_AREA            = 0.5
SUMP_BASE_ELEV       = -2.5
SUMP_OVERFLOW_LEVEL  = 0.8
SUMP_OVERFLOW_COEFF  = 1.8
SUMP_OVERFLOW_EXP    = 1.5
PUMP_ON_LEVEL        = 0.10
PUMP_OFF_LEVEL       = 0.02
PUMP_SHUTOFF_HEAD    = 5.0
PUMP_CURVE_COEFF     = 1000.0
PIPE_LOSS_COEFF      = 0.0
PUMP_AVAIL           = 1.0

# Shared triangular hydrograph (0→0.5 m at 30 min, recession to 0 at 60 min,
# dry tail to 360 min — same as run_examples.py)
_HYDRO_MIN  = [(0, 0.0), (30, 0.5), (60, 0.0), (360, 0.0)]
EXT_TIMES_S = [t * 60.0 for t, _ in _HYDRO_MIN]
EXT_LEVELS  = [h        for _, h in _HYDRO_MIN]

# ── dt sweep ──────────────────────────────────────────────────────────────────
# Ranges from the default 60-s step (unstable) down to 0.5-s reference.
DT_VALUES_S = [60.0, 30.0, 10.0, 5.0, 2.0, 1.0, 0.5]
DT_LABELS   = ['60 s', '30 s', '10 s', '5 s', '2 s', '1 s  (recommended)', '0.5 s  (ref.)']
DT_COLOURS  = ['#c0392b', '#e67e22', '#f39c12', '#d4ac0d', '#2980b9', '#27ae60', '#1abc9c']
DT_LW       = [2.0,       1.8,       1.8,       1.8,       2.0,       2.2,       1.4]
DT_LS       = ['-',       '-',       '-',       '-',       '-',       '-',       '--']

G = 9.81


def _build_sump() -> SumpPump:
    return SumpPump(
        sump_area           = SUMP_AREA,
        sump_base_elevation = SUMP_BASE_ELEV,
        overflow_level      = SUMP_OVERFLOW_LEVEL,
        overflow_coeff      = SUMP_OVERFLOW_COEFF,
        overflow_exponent   = SUMP_OVERFLOW_EXP,
        pump_on_level       = PUMP_ON_LEVEL,
        pump_off_level      = PUMP_OFF_LEVEL,
        pump_shutoff_head   = PUMP_SHUTOFF_HEAD,
        pump_curve_coeff    = PUMP_CURVE_COEFF,
        pipe_loss_coeff     = PIPE_LOSS_COEFF,
        pump_availability   = PUMP_AVAIL,
    )


def run_case(dt_s: float):
    """Run Case 05 at a given dt.  Returns (times_min, h_sump, h_bsmt, h_ext)."""
    b = Building(FLOOR_AREA)
    b.basement_area               = BASEMENT_AREA
    b.z_basement                  = BASEMENT_FLOOR_ELEV
    b.basement_ceiling_elevation  = 0.0          # ground level
    b.h_basement                  = 0.0
    b.basement_ingress = IngressPathway(
        height=BASEMENT_INGRESS_H,
        area=BASEMENT_INGRESS_A,
        coeff=BASEMENT_INGRESS_CD,
        name='perimeter',
        source='outside',
        target='basement',
    )
    b.sump_pump = _build_sump()

    ing = [IngressPathway(height=10.0, area=0.001, coeff=0.6,
                          name='never_reached')]   # no ground-floor path

    sim = Simulation(b, ing, EXT_TIMES_S, EXT_LEVELS, dt=dt_s)
    result = sim.run()
    times_s  = result[0]
    h_bsmt   = result[2]   # basement_levels
    h_sump   = result[3]   # sump_levels
    h_ext    = sample_with_zero_padding(times_s, EXT_TIMES_S, EXT_LEVELS)
    times_min = [t / 60.0 for t in times_s]
    return times_min, h_sump, h_bsmt, h_ext


def _dt_crit(q_pump_peak: float) -> float:
    """Critical timestep: pump drain time for the active sump volume."""
    return SUMP_AREA * PUMP_ON_LEVEL / q_pump_peak


def _q_pump_peak() -> float:
    """Peak pump flow during the flood (at peak flood head, pump ON)."""
    H_lift = abs(0.5 - SUMP_BASE_ELEV)   # external peak 0.5 m above datum
    dH = PUMP_SHUTOFF_HEAD - H_lift
    if dH <= 0:
        return 0.0
    return math.sqrt(dH / PUMP_CURVE_COEFF)


def main():
    outdir = os.path.join(HERE, 'ex05', 'out')
    os.makedirs(outdir, exist_ok=True)

    Q_peak   = _q_pump_peak()
    dt_crit  = _dt_crit(Q_peak)
    print(f'  Q_pump peak ≈ {Q_peak:.4f} m³/s')
    print(f'  dt_crit = A_sump × h_on / Q_pump = {SUMP_AREA} × {PUMP_ON_LEVEL} / {Q_peak:.4f} ≈ {dt_crit:.2f} s')

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
        print(f'  dt={dt_s:5.1f} s  dt/dt_crit={ratio:.2f}  '
              f'peak_h_sump={peak_sp:.4f} m  peak_h_bsmt={peak_bs:.4f} m')

    ref = runs[-1]   # 0.5-s reference

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
                            [t / 60.0 for t in EXT_TIMES_S], EXT_LEVELS)
    ax_ts.fill_between(t_ext_fine, h_ext_fine,
                       alpha=0.07, color='#7f8c8d', zorder=1)
    ax_ts.plot(t_ext_fine, h_ext_fine,
               color='#7f8c8d', lw=1.4, ls='--', zorder=4,
               label='External  $h_{ext}$')

    # sump overflow crest
    ax_ts.axhline(SUMP_OVERFLOW_LEVEL, color='#8e44ad', lw=0.9, ls=':',
                  alpha=0.55, zorder=2, label=f'Sump overflow crest  {SUMP_OVERFLOW_LEVEL} m')

    for r in runs:
        ax_ts.plot(r['t_min'], r['h_sp'],
                   color=r['col'], lw=r['lw'], ls=r['ls'], zorder=3,
                   label=f"Δt = {r['label']}  (peak = {r['peak_sp']:.3f} m)")

    ax_ts.set_xlabel('Time  (min)')
    ax_ts.set_ylabel('Sump depth  $h_{sump}$  (m)')
    ax_ts.set_title('Sump depth time-series — explicit Euler at varying Δt\n'
                    f'Case 05: A_sump = {SUMP_AREA} m²,  '
                    f'h_on = {PUMP_ON_LEVEL} m,  '
                    f'Q_pump_peak ≈ {Q_peak:.3f} m³/s,  '
                    f'dt_crit ≈ {dt_crit:.1f} s')
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
                    label=f'Ref. 0.5 s  ({ref["peak_bs"]*1000:.1f} mm)')
    ax_bsmt.axvline(dt_crit, color='#c0392b', lw=1.2, ls='--', alpha=0.7,
                    label=f'dt_crit ≈ {dt_crit:.1f} s')

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
        'This can trigger a spurious sump overflow.\n\n'
        'Stability criterion:\n\n'
        '   dt  ≤  dt_crit  =  A_sump × h_on / Q_pump\n\n'
        f'Case 05 values:\n'
        f'   A_sump = {SUMP_AREA} m²\n'
        f'   h_on   = {PUMP_ON_LEVEL} m\n'
        f'   Q_pump ≈ {Q_peak:.4f} m³/s  (at peak flood)\n\n'
        f'   →  dt_crit ≈ {dt_crit:.1f} s\n\n'
        'Recommended:  dt ≤ dt_crit / 2  for ≥ 50 %\n'
        'margin.  For Case 05:  dt ≤ 1 s.\n\n'
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
        'Case 05 — Timestep sensitivity: sump/pump oscillation at large Δt',
        fontsize=12, fontweight='bold', color='#1e2433', y=0.96)

    out = os.path.join(outdir, 'dt_sensitivity.png')
    fig.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  Saved {out}')


if __name__ == '__main__':
    main()
