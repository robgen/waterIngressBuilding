#!/usr/bin/env python3
"""Timestep sensitivity analysis for Case 01.

Runs the same single-orifice, ground-floor-only problem with a sweep of
dt values and plots the time-series and peak-convergence, demonstrating
the explicit-Euler instability at large dt.

Produces:
  examples/ex01/out/dt_sensitivity.png
"""
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

# ── problem parameters (Case 01) ──────────────────────────────────────────────
FLOOR_AREA  = 50.0      # m²  — realistic small UK terraced house ground floor
ORIFICE_A   = 0.05      # m²
ORIFICE_CD  = 0.6       # –
SILL_H      = 0.0       # m

# Shared triangular hydrograph matching run_examples.py (flood 0-60 min, dry tail to 120 min)
_HYDRO_MIN = [(0, 0.0), (30, 0.5), (60, 0.0), (120, 0.0)]
EXT_TIMES_S  = [t * 60.0 for t, _ in _HYDRO_MIN]
EXT_LEVELS   = [h        for _, h in _HYDRO_MIN]

# ── dt sweep (seconds) ────────────────────────────────────────────────────────
# From clearly unstable (60 s) down to well-converged reference (1 s)
DT_VALUES_S = [60.0, 30.0, 15.0, 6.0, 1.0]
DT_LABELS   = ['60 s (1 min)', '30 s', '15 s', '6 s (Case 01 fix)', '1 s  (reference)']
DT_COLOURS  = ['#c0392b', '#e67e22', '#f1c40f', '#2980b9', '#27ae60']
DT_LS       = ['-', '-', '-', '-', '--']
DT_LW       = [2.2, 1.8, 1.8, 2.2, 1.4]

G = 9.81


def run_case(dt_s: float):
    """Run the Case 01 problem at a given dt (seconds). Returns (times_min, h_in, h_ext)."""
    b   = Building(FLOOR_AREA)
    ing = [IngressPathway(height=SILL_H, area=ORIFICE_A, coeff=ORIFICE_CD,
                          name='door_gap')]
    sim = Simulation(b, ing, EXT_TIMES_S, EXT_LEVELS, dt=dt_s)
    result = sim.run()
    times_s  = result[0]
    h_in     = result[1]
    h_ext    = sample_with_zero_padding(times_s, EXT_TIMES_S, EXT_LEVELS)
    times_min = [t / 60.0 for t in times_s]
    return times_min, h_in, h_ext


def _analytical_response_time() -> float:
    """Characteristic response time τ = A_floor / (Cd·A·√(2g·H_max)) in seconds."""
    Q_max = ORIFICE_CD * ORIFICE_A * math.sqrt(2 * G * 0.5)
    return FLOOR_AREA * 0.5 / Q_max   # s


def main():
    outdir = os.path.join(HERE, 'ex01', 'out')
    os.makedirs(outdir, exist_ok=True)

    tau = _analytical_response_time()
    print(f'  Characteristic response time τ ≈ {tau:.1f} s  ({tau/60:.2f} min)')

    # ── collect results ───────────────────────────────────────────────────────
    runs = []
    for dt_s, label, col, ls, lw in zip(
            DT_VALUES_S, DT_LABELS, DT_COLOURS, DT_LS, DT_LW):
        t_min, h_in, h_ext = run_case(dt_s)
        peak = max(h_in)
        ratio = dt_s / tau
        runs.append(dict(dt_s=dt_s, label=label, col=col, ls=ls, lw=lw,
                         t_min=t_min, h_in=h_in, h_ext=h_ext,
                         peak=peak, ratio=ratio))
        print(f'  dt={dt_s:5.1f}s  dt/τ={ratio:.3f}  peak_h_in={peak:.4f} m')

    ref_peak = runs[-1]['peak']   # 1-second reference

    # ── figure ────────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 8))
    gs  = gridspec.GridSpec(2, 2, figure=fig,
                            hspace=0.48, wspace=0.38,
                            left=0.07, right=0.97,
                            top=0.90, bottom=0.09)

    # ── (0,:)  time-series panel (spans both columns) ─────────────────────────
    ax_ts = fig.add_subplot(gs[0, :])

    # exterior hydrograph fill
    t_ext_fine = np.linspace(0, 60, 1200)
    h_ext_fine = np.interp(t_ext_fine, [t/60 for t in EXT_TIMES_S], EXT_LEVELS)
    ax_ts.fill_between(t_ext_fine, h_ext_fine,
                       alpha=0.10, color='#7f8c8d', zorder=1)
    ax_ts.plot(t_ext_fine, h_ext_fine,
               color='#7f8c8d', lw=1.6, ls='--', zorder=4, label='External $h_{ext}$')

    for r in runs:
        ax_ts.plot(r['t_min'], r['h_in'],
                   color=r['col'], lw=r['lw'], ls=r['ls'], zorder=3,
                   label=f"Δt = {r['label']}  (peak = {r['peak']:.3f} m)")

    ax_ts.set_xlabel('Time  (min)')
    ax_ts.set_ylabel('Water depth  (m)')
    ax_ts.set_title('Interior depth time-series — explicit Euler at varying Δt\n'
                    f'Case 01: A = {ORIFICE_A} m², $C_d$ = {ORIFICE_CD}, '
                    f'floor = {FLOOR_AREA} m²,  τ ≈ {tau:.0f} s')
    ax_ts.set_xlim(0, 60)
    ax_ts.set_ylim(bottom=0)
    ax_ts.legend(fontsize=8, loc='upper right', ncol=2)

    # stability annotation
    ax_ts.axhline(0.5, color='#7f8c8d', lw=0.8, ls=':', zorder=2)
    ax_ts.text(61, 0.5, '$h_{ext}^{max}$ = 0.5 m',
               va='center', ha='left', fontsize=8, color='#7f8c8d',
               clip_on=False)

    # ── (1,0)  peak h_in vs dt ────────────────────────────────────────────────
    ax_conv = fig.add_subplot(gs[1, 0])
    dt_arr   = np.array([r['dt_s'] for r in runs])
    peak_arr = np.array([r['peak'] for r in runs])
    err_arr  = np.abs(peak_arr - ref_peak)

    for r, e in zip(runs, err_arr):
        ax_conv.scatter(r['dt_s'], r['peak'], s=60, color=r['col'],
                        zorder=5, edgecolors='white', lw=0.8)
    ax_conv.plot(dt_arr, peak_arr, color='#2c3140', lw=1.2, ls='-', zorder=3)
    ax_conv.axhline(ref_peak, color='#27ae60', lw=1.0, ls='--',
                    label=f'Reference ({ref_peak:.4f} m)')
    ax_conv.axhline(0.5, color='#7f8c8d', lw=0.8, ls=':',
                    label='$h_{ext}^{max}$ = 0.5 m')

    # shade instability zone
    tau_min = tau / 60.0
    ax_conv.axvspan(60, 70, color='#c0392b', alpha=0.08, zorder=1)
    ax_conv.text(60, ax_conv.get_ylim()[0] if ax_conv.get_ylim()[0] > 0 else 0.45,
                 'unstable\nzone', ha='right', va='bottom',
                 fontsize=7.5, color='#c0392b', style='italic')

    ax_conv.set_xlabel('Timestep  Δt  (s)')
    ax_conv.set_ylabel('Peak interior depth  (m)')
    ax_conv.set_title('Peak $h_{in}$ vs Δt\n(convergence to reference)')
    ax_conv.legend(fontsize=8)
    ax_conv.set_xlim(0, 65)
    ax_conv.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f'))

    # ── (1,1)  relative error vs dt/τ ────────────────────────────────────────
    ax_err = fig.add_subplot(gs[1, 1])
    ratio_arr = dt_arr / tau
    for r, e, ratio in zip(runs, err_arr, ratio_arr):
        ax_err.scatter(ratio, e * 100, s=60, color=r['col'],
                       zorder=5, edgecolors='white', lw=0.8,
                       label=f"Δt={r['dt_s']:.0f}s")
    ax_err.plot(ratio_arr, err_arr * 100, color='#2c3140', lw=1.2, zorder=3)

    # stability boundary Δt/τ ~ 1
    ax_err.axvline(1.0, color='#c0392b', lw=1.2, ls='--', alpha=0.7,
                   label='Δt / τ = 1  (stability limit)')
    ax_err.axvline(0.1, color='#2980b9', lw=1.0, ls=':', alpha=0.7,
                   label='Δt / τ = 0.1  (Case 01 fix)')

    ax_err.set_xlabel('Normalised timestep  Δt / τ')
    ax_err.set_ylabel('Error in peak depth  |Δ$h_{in}^{max}$|  (%)')
    ax_err.set_title('Relative error vs Δt / τ\n(τ = characteristic response time)')
    ax_err.legend(fontsize=7.5)
    ax_err.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.1f}%'))

    # ── figure title ──────────────────────────────────────────────────────────
    fig.suptitle(
        'Case 01 — Timestep sensitivity: explicit-Euler stability for large orifice',
        fontsize=12, fontweight='bold', color='#1e2433', y=0.97)

    # stability note
    note = (f'τ = A_floor · h_max / Q_max ≈ {tau:.0f} s = {tau/60:.2f} min  '
            f'(characteristic fill time at peak head, 50 m² floor)\n'
            f'With corrected dimensions, Δt = 60 s is stable (Δt/τ = 0.23) but carries ~1 % bias.  '
            f'Fix: Δt = 6 s (Δt/τ ≈ 0.02) reduces peak error to < 0.3 %.')
    fig.text(0.50, 0.945, note,
             ha='center', va='top', fontsize=8.5, color='#444',
             style='italic',
             bbox=dict(boxstyle='round,pad=0.35', fc='#f4f6f9',
                       ec='#d0d5dd', alpha=0.95))

    out = os.path.join(outdir, 'dt_sensitivity.png')
    fig.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  Saved {out}')


if __name__ == '__main__':
    main()
