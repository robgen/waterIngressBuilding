#!/usr/bin/env python3
"""Plotting and animation helpers for headless use (uses Agg backend).

This module sets the Agg backend on import so it is safe to import only
from CLI (not from GUI). Callers that need GUI-backed plotting should not
import this module.
"""
import os
import tempfile

_mpl_config_dir = os.path.join(tempfile.gettempdir(), 'water_ingress_matplotlib')
os.makedirs(_mpl_config_dir, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', _mpl_config_dir)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
from matplotlib import patches
from matplotlib.lines import Line2D

import numpy as np

# ── global visual style ────────────────────────────────────────────────────────
plt.rcParams.update({
    'figure.facecolor':    'white',
    'axes.facecolor':      '#f9fafb',
    'axes.edgecolor':      '#c8cdd2',
    'axes.linewidth':      0.8,
    'axes.grid':           True,
    'axes.grid.axis':      'both',
    'grid.color':          '#e4e8ed',
    'grid.linewidth':      0.55,
    'grid.linestyle':      '-',
    'xtick.color':         '#4a5260',
    'ytick.color':         '#4a5260',
    'xtick.labelcolor':    '#4a5260',
    'ytick.labelcolor':    '#4a5260',
    'xtick.direction':     'out',
    'ytick.direction':     'out',
    'xtick.major.size':    3.5,
    'ytick.major.size':    3.5,
    'xtick.major.width':   0.6,
    'ytick.major.width':   0.6,
    'lines.linewidth':     2.0,
    'lines.solid_capstyle':'round',
    'patch.linewidth':     0.6,
    'font.family':         'sans-serif',
    'font.sans-serif':     ['Helvetica Neue', 'Arial', 'DejaVu Sans'],
    'font.size':           10,
    'axes.titlesize':      11,
    'axes.titleweight':    'bold',
    'axes.titlepad':       8,
    'axes.labelsize':      9.5,
    'axes.labelcolor':     '#2c3140',
    'xtick.labelsize':     8.5,
    'ytick.labelsize':     8.5,
    'legend.fontsize':     8.5,
    'legend.title_fontsize': 8,
    'legend.framealpha':   0.93,
    'legend.edgecolor':    '#d0d5dd',
    'legend.borderpad':    0.5,
    'legend.labelspacing': 0.3,
    'savefig.dpi':         150,
    'savefig.bbox':        'tight',
    'savefig.pad_inches':  0.12,
    'figure.dpi':          110,
    'axes.spines.top':     False,
    'axes.spines.right':   False,
})

# ── canonical colour palette ───────────────────────────────────────────────────
_C = {
    'external':  '#2980b9',
    'indoor':    '#e67e22',
    'basement':  '#27ae60',
    'sump':      '#8e5fbf',
    'perimeter': '#16a5b8',
    'bypass':    '#c49a0a',
    'pump':      '#5e3498',
    'overflow':  '#c0392b',
}

_FILL_ALPHA = {
    'external': 0.10,
    'indoor':   0.18,
    'basement': 0.14,
    'sump':     0.16,
}

# ── shared helpers ─────────────────────────────────────────────────────────────

def _xlabel(time_unit):
    if time_unit:
        return f'Time  ({time_unit})'
    return 'Time'


def _despine(ax, keep=('left', 'bottom')):
    for sp in ('top', 'right', 'left', 'bottom'):
        ax.spines[sp].set_visible(sp in keep)


def _format_m3s(val, _):
    """Compact m³/s formatter that switches to L/s for small values."""
    if abs(val) < 1e-3:
        return f'{val * 1000:.2f} L/s' if abs(val) > 1e-9 else '0'
    return f'{val:.4f}'


def _annotate_peak(ax, times, values, colour, label, x_range,
                   x_frac=0.08, y_frac=0.08, fontsize=8):
    """Draw an arrow + text box at the peak of `values`."""
    if not values or not any(v > 1e-5 for v in values):
        return
    pk_i = int(np.argmax(values))
    pk_t, pk_v = times[pk_i], values[pk_i]
    if pk_v < 1e-4:
        return
    x_off = x_range * x_frac
    y_lo, y_hi = ax.get_ylim()
    y_span = max(y_hi - y_lo, pk_v)
    y_off  = y_span * y_frac
    ax.annotate(
        f'{label}  {pk_v:.3f} m',
        xy=(pk_t, pk_v),
        xytext=(pk_t - x_off, pk_v + y_off),
        fontsize=fontsize,
        color=colour,
        arrowprops=dict(arrowstyle='->', color=colour, lw=1.0,
                        connectionstyle='arc3,rad=-0.15'),
        bbox=dict(boxstyle='round,pad=0.32', fc='white', ec=colour,
                  alpha=0.92, lw=0.9),
        zorder=10,
    )


def _peak_vline(ax, times, values, colour, alpha=0.35, lw=1.2):
    if not values or not any(v > 1e-5 for v in values):
        return
    pk_t = times[int(np.argmax(values))]
    ax.axvline(pk_t, color=colour, lw=lw, ls='--', alpha=alpha, zorder=4)


def _shade_active(ax, times, h_ext, h_in, colour=None):
    """Light fill where h_ext > h_in (actively driving inflow)."""
    arr_ext = np.array(h_ext)
    arr_in  = np.array(h_in)
    c = colour or _C['external']
    ax.fill_between(times, arr_in, arr_ext,
                    where=arr_ext > arr_in,
                    interpolate=True,
                    color=c, alpha=0.07, zorder=1, label='_nolegend_')


# ── external preview ───────────────────────────────────────────────────────────

def save_external_preview(times, levels, outpath, time_unit=None):
    times  = list(times)
    levels = list(levels)
    fig, ax = plt.subplots(figsize=(7, 3.2))

    ax.plot(times, levels, color=_C['external'], lw=2.0, zorder=3)
    ax.fill_between(times, 0, levels,
                    color=_C['external'], alpha=0.15, zorder=2)

    if levels and max(levels) > 1e-4:
        pk_i = int(np.argmax(levels))
        ax.plot(times[pk_i], levels[pk_i], 'o',
                color=_C['external'], ms=6, zorder=5)
        ax.annotate(
            f'peak  {levels[pk_i]:.3f} m',
            xy=(times[pk_i], levels[pk_i]),
            xytext=(0, 10), textcoords='offset points',
            ha='center', fontsize=8.5, color=_C['external'],
            arrowprops=dict(arrowstyle='->', color=_C['external'], lw=0.8),
            bbox=dict(boxstyle='round,pad=0.28', fc='white',
                      ec=_C['external'], alpha=0.90, lw=0.8),
            zorder=6,
        )

    ax.set_xlabel(_xlabel(time_unit))
    ax.set_ylabel('External depth  (m)')
    ax.set_title('External flood hydrograph')
    ax.set_xlim(times[0], times[-1])
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))
    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


# ── velocity preview ───────────────────────────────────────────────────────────

def save_velocity_preview(times, velocities, outpath, time_unit=None,
                           orig_point_times=None, orig_point_vals=None):
    if not times:
        raise ValueError('No velocity times provided')
    times      = list(times)
    velocities = list(velocities)

    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.plot(times, velocities, color='#2ecc71', lw=2.0, zorder=3,
            label='Velocity (sampled)')
    ax.fill_between(times, 0, velocities,
                    color='#2ecc71', alpha=0.14, zorder=2)

    if orig_point_times is not None and orig_point_vals is not None:
        ax.scatter(orig_point_times, orig_point_vals,
                   color='#1a8a4a', marker='D', s=32, zorder=5,
                   label='Input samples', edgecolors='white', linewidths=0.5)

    if velocities and max(velocities) > 1e-4:
        pk_i = int(np.argmax(velocities))
        ax.annotate(
            f'peak  {velocities[pk_i]:.2f} m/s',
            xy=(times[pk_i], velocities[pk_i]),
            xytext=(0, 10), textcoords='offset points',
            ha='center', fontsize=8.5, color='#1a8a4a',
            arrowprops=dict(arrowstyle='->', color='#1a8a4a', lw=0.8),
            bbox=dict(boxstyle='round,pad=0.28', fc='white',
                      ec='#1a8a4a', alpha=0.90, lw=0.8),
            zorder=6,
        )

    ax.set_xlabel(_xlabel(time_unit))
    ax.set_ylabel('Flow velocity  (m/s)')
    ax.set_title('External flow velocity')
    ax.set_xlim(times[0], times[-1])
    ax.set_ylim(bottom=0)
    ax.legend(loc='upper right')
    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


# ── simulation result ──────────────────────────────────────────────────────────

def save_simulation_result(sim_times, sim_levels, external_levels, outpath,
                           time_unit=None, basement_levels=None,
                           velocity_series=None, sump_levels=None,
                           basement_max_depth=None, sump_overflow_level=None):
    """High-quality multi-panel simulation result figure."""
    t   = list(sim_times)
    h_e = list(external_levels)
    h_i = list(sim_levels)
    has_bs   = basement_levels is not None and any(v > 1e-6 for v in basement_levels)
    has_sump = sump_levels is not None and any(v > 1e-6 for v in sump_levels)
    has_vel  = velocity_series is not None

    x_range = (t[-1] - t[0]) if len(t) > 1 else 1.0

    # ── layout ────────────────────────────────────────────────────────────────
    if not (has_bs or has_sump):
        # single-panel
        fig, axes = plt.subplots(1, 1, figsize=(10, 5))
        ax_main = axes
        ax_sub  = None
    else:
        # two panels — upper for gf water, lower for basement/sump
        fig = plt.figure(figsize=(10, 7))
        gs  = gridspec.GridSpec(2, 1, figure=fig,
                                height_ratios=[2.2, 1],
                                hspace=0.10)
        ax_main = fig.add_subplot(gs[0])
        ax_sub  = fig.add_subplot(gs[1], sharex=ax_main)

    # ── top panel: external + indoor ─────────────────────────────────────────
    _peak_vline(ax_main, t, h_e, _C['external'], alpha=0.30, lw=1.0)

    ax_main.fill_between(t, 0, h_e,
                         color=_C['external'], alpha=_FILL_ALPHA['external'],
                         zorder=1)
    ax_main.fill_between(t, 0, h_i,
                         color=_C['indoor'], alpha=_FILL_ALPHA['indoor'],
                         zorder=2)
    _shade_active(ax_main, t, h_e, h_i)

    l_ext, = ax_main.plot(t, h_e, color=_C['external'], lw=2.2, zorder=5,
                          label='External  $h_{out}$')
    l_in,  = ax_main.plot(t, h_i, color=_C['indoor'],   lw=2.2, zorder=6,
                          label='Ground floor  $h_{in}$')

    # peak annotations
    pk_e = max(h_e) if h_e else 0.0
    pk_i = max(h_i) if h_i else 0.0
    _annotate_peak(ax_main, t, h_e, _C['external'], 'h_out peak', x_range,
                   x_frac=0.06, y_frac=0.06)
    if pk_i > 1e-4:
        _annotate_peak(ax_main, t, h_i, _C['indoor'], 'h_in peak', x_range,
                       x_frac=0.06, y_frac=0.12)

    # attenuation callout (only when there is meaningful interior flooding)
    if pk_e > 1e-3 and pk_i > 1e-3:
        attn = (pk_e - pk_i) / pk_e * 100
        ax_main.text(0.98, 0.96,
                     f'Peak attenuation  {attn:.0f} %',
                     transform=ax_main.transAxes,
                     ha='right', va='top', fontsize=8, color='#555',
                     bbox=dict(boxstyle='round,pad=0.32', fc='white',
                               ec='#bbb', alpha=0.88))

    ax_main.set_ylabel('Water depth  (m)')
    ax_main.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f'))
    ax_main.set_ylim(bottom=0)

    legend_handles = [l_ext, l_in]
    if has_bs or has_sump:
        # hide x-tick labels on upper panel when shared
        plt.setp(ax_main.get_xticklabels(), visible=False)
        ax_main.set_xlabel('')
    else:
        ax_main.set_xlabel(_xlabel(time_unit))

    # ── bottom panel: basement / sump ─────────────────────────────────────────
    if ax_sub is not None:
        bs_vals = list(basement_levels) if basement_levels is not None else [0.0] * len(t)
        sp_vals = list(sump_levels)     if sump_levels is not None else None

        if has_bs:
            ax_sub.fill_between(t, 0, bs_vals,
                                color=_C['basement'], alpha=_FILL_ALPHA['basement'],
                                zorder=1)
            if basement_max_depth is not None and basement_max_depth > 0:
                bs_lbl = f'Basement  $h_{{bs}}$  ({basement_max_depth:.3f} m ceil.)'
            else:
                bs_lbl = 'Basement  $h_{bs}$'
            l_bs, = ax_sub.plot(t, bs_vals, color=_C['basement'], lw=2.0,
                                ls='-', zorder=5, label=bs_lbl)
            legend_handles.append(l_bs)
            if max(bs_vals) > 1e-4:
                _annotate_peak(ax_sub, t, bs_vals, _C['basement'],
                               'h_bs peak', x_range, x_frac=0.06, y_frac=0.12)

        if has_sump and sp_vals is not None:
            ax_sub.fill_between(t, 0, sp_vals,
                                color=_C['sump'], alpha=_FILL_ALPHA['sump'],
                                zorder=2)
            l_sp, = ax_sub.plot(t, sp_vals, color=_C['sump'], lw=2.0,
                                ls='-', zorder=6, label='Sump  $h_{sump}$')
            legend_handles.append(l_sp)

        # ── reference lines: sump overflow level & basement ceiling ──────────
        # blended transform: x in axes fraction, y in data coords
        from matplotlib.transforms import blended_transform_factory as _btf
        _tr = _btf(ax_sub.transAxes, ax_sub.transData)

        _y_top = max(
            (max(bs_vals) if has_bs else 0.0),
            (max(sp_vals) if sp_vals is not None and has_sump else 0.0),
            1e-6,
        )

        ref_handles = []

        if sump_overflow_level is not None and sump_overflow_level > 0:
            ax_sub.axhline(sump_overflow_level, color=_C['sump'], lw=1.1,
                           ls='--', alpha=0.60, zorder=3)
            # label on right edge (visible only when line is within current range)
            if sump_overflow_level <= _y_top * 4:
                ax_sub.text(1.01, sump_overflow_level,
                            f'{sump_overflow_level:.3f} m',
                            color=_C['sump'], fontsize=7, va='center',
                            transform=_tr, clip_on=False)
            ref_handles.append(Line2D([], [], color=_C['sump'], lw=1.1, ls='--',
                                      alpha=0.60,
                                      label=f'Sump overflow level  {sump_overflow_level:.3f} m'))

        ax_sub.set_ylabel('Depth  (m)')
        ax_sub.set_xlabel(_xlabel(time_unit))
        ax_sub.set_ylim(bottom=0)
        ax_sub.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f'))

        sub_handles = ([l_bs] if has_bs else []) + \
                      ([l_sp] if has_sump and sp_vals is not None else []) + \
                      ref_handles
        ax_sub.legend(handles=sub_handles, fontsize=8, loc='upper right')

    # ── legend & title ────────────────────────────────────────────────────────
    ax_main.legend(handles=legend_handles, loc='upper left',
                   fontsize=8.5, framealpha=0.93)

    pk_e_str = f'{pk_e:.3f} m' if pk_e > 1e-4 else '—'
    pk_i_str = f'{pk_i:.3f} m' if pk_i > 1e-4 else '—'
    title_parts = [f'$h_{{out}}^{{max}}$ = {pk_e_str}',
                   f'$h_{{in}}^{{max}}$ = {pk_i_str}']
    if has_bs:
        pk_bs = max(bs_vals) if has_bs else 0
        if pk_bs > 1e-4:
            title_parts.append(f'$h_{{bs}}^{{max}}$ = {pk_bs:.3f} m')
    ax_main.set_title(
        'Flood Ingress Simulation  —  ' + '   '.join(title_parts),
        fontsize=11, fontweight='bold', pad=10)

    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


# ── forces result ──────────────────────────────────────────────────────────────

def save_forces_result(sim_times, forces_rows, outpath, time_unit=None):
    if not sim_times:
        raise ValueError('No simulation times provided')
    times = list(sim_times)
    F_h   = [r[1] for r in forces_rows]
    F_d   = [r[2] for r in forces_rows]
    F_t   = [r[3] for r in forces_rows]
    M_o   = [r[4] for r in forces_rows]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7),
                                    sharex=True,
                                    gridspec_kw={'height_ratios': [2, 1],
                                                 'hspace': 0.08})

    ax1.fill_between(times, 0, F_t, color='#c0392b', alpha=0.10, zorder=1)
    ax1.plot(times, F_h, lw=2.0, color='#2980b9', label='Hydrostatic  $F_h$', zorder=4)
    ax1.plot(times, F_d, lw=2.0, color='#27ae60', label='Drag  $F_d$', zorder=4)
    ax1.plot(times, F_t, lw=2.4, color='#c0392b', label='Total  $F$', zorder=5)

    # peak total force annotation
    if F_t and max(F_t) > 0:
        pi = int(np.argmax(F_t))
        ax1.annotate(
            f'Peak  {F_t[pi]:,.0f} N',
            xy=(times[pi], F_t[pi]),
            xytext=(10, 8), textcoords='offset points',
            fontsize=8.5, color='#c0392b',
            arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.0),
            bbox=dict(boxstyle='round,pad=0.3', fc='white',
                      ec='#c0392b', alpha=0.92, lw=0.9),
            zorder=8,
        )

    ax1.set_ylabel('Force  (N)')
    ax1.legend(loc='upper left')
    ax1.set_title('Lateral forces on building facade', pad=10)
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    ax2.fill_between(times, 0, M_o, color='#8e5fbf', alpha=0.13, zorder=1)
    ax2.plot(times, M_o, lw=2.0, color='#8e5fbf',
             label='Overturning moment  $M$', zorder=4)
    if M_o and max(M_o) > 0:
        pi = int(np.argmax(M_o))
        ax2.annotate(
            f'Peak  {M_o[pi]:,.0f} Nm',
            xy=(times[pi], M_o[pi]),
            xytext=(10, 6), textcoords='offset points',
            fontsize=8, color='#8e5fbf',
            arrowprops=dict(arrowstyle='->', color='#8e5fbf', lw=0.9),
            bbox=dict(boxstyle='round,pad=0.28', fc='white',
                      ec='#8e5fbf', alpha=0.92, lw=0.9),
            zorder=8,
        )
    ax2.set_ylabel('Moment  (N·m)')
    ax2.set_xlabel(_xlabel(time_unit))
    ax2.legend(loc='upper left')
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


# ── animation ─────────────────────────────────────────────────────────────────

def generate_animation(sim_times, sim_levels, external_levels, ingress_list, outpath,
                       fps=10, max_frames=200, time_unit=None, basement_levels=None,
                       basement_abs_levels=None, velocity_series=None, sump_levels=None,
                       sump_overflow_level=None, Q_perim_series=None,
                       Q_bypass_series=None):
    n_frames = len(sim_times)
    if n_frames <= 0:
        raise ValueError('No simulation times for animation')
    step         = max(1, n_frames // max_frames)
    frame_indices = list(range(0, n_frames, step))

    building_width = 1.0
    bx = 0.5
    max_ingress_h = max((ing.height for ing in ingress_list), default=0.0)
    max_level     = max(max(external_levels or [0]),
                        max(sim_levels or [0]), max_ingress_h)
    building_height = max(3.0, max_level * 1.4 + 0.5)
    unit_label = ('s' if (time_unit is None or time_unit == 'seconds')
                  else ('min' if time_unit.startswith('min')
                        else ('h' if time_unit.startswith('hour') else time_unit)))

    # Ground↔basement flow series
    if Q_bypass_series is not None:
        Qgb_series = list(Q_bypass_series)
    elif ingress_list and basement_levels is not None:
        abs_basement = basement_abs_levels if basement_abs_levels is not None else basement_levels
        Qgb_series = [0.0] * len(sim_times)
        if abs_basement is not None:
            for i in range(len(sim_times)):
                total = 0.0
                for ing in ingress_list:
                    src = getattr(ing, 'source', 'outside')
                    tgt = getattr(ing, 'target', 'ground')
                    if src == 'ground' and tgt == 'basement':
                        total += ing.compute_flow(sim_levels[i], abs_basement[i])
                    elif src == 'basement' and tgt == 'ground':
                        total -= ing.compute_flow(abs_basement[i], sim_levels[i])
                Qgb_series[i] = total
    else:
        Qgb_series = [0.0] * len(sim_times)

    _dts = ([sim_times[k+1] - sim_times[k] for k in range(len(sim_times) - 1)] + [0.0])
    cum_perim  = [0.0] * len(sim_times)
    cum_bypass = [0.0] * len(sim_times)
    _rp = _rb = 0.0
    for _k in range(len(sim_times)):
        _qp = Q_perim_series[_k] if (Q_perim_series is not None and _k < len(Q_perim_series)) else 0.0
        _qb = max(0.0, Qgb_series[_k])
        _rp += _qp * _dts[_k]
        _rb += _qb * _dts[_k]
        cum_perim[_k]  = _rp
        cum_bypass[_k] = _rb

    # ── layout ────────────────────────────────────────────────────────────────
    # Suppress rcParams grid for the animation (building panel looks cleaner)
    with plt.rc_context({'axes.grid': False, 'axes.facecolor': 'white',
                         'figure.facecolor': 'white'}):
        if basement_levels is None:
            fig = plt.figure(figsize=(12, 5.2))
            gs  = gridspec.GridSpec(1, 2, figure=fig,
                                    width_ratios=[3, 2], wspace=0.42)
            ax_top   = fig.add_subplot(gs[0, 0])
            ax_chart = fig.add_subplot(gs[0, 1])
            ax_b = None
        else:
            fig = plt.figure(figsize=(12, 6.4))
            gs  = gridspec.GridSpec(2, 2, figure=fig,
                                    width_ratios=[3, 2],
                                    height_ratios=[3, 1.1],
                                    wspace=0.42, hspace=0.14)
            ax_top   = fig.add_subplot(gs[0, 0])
            ax_b     = fig.add_subplot(gs[1, 0])
            ax_chart = fig.add_subplot(gs[:, 1])

        # ── building panel ────────────────────────────────────────────────────
        ax_top.set_xlim(-0.5, 4.2)
        ax_top.set_ylim(0, building_height * 1.25)
        ax_top.set_xlabel('Horizontal position', fontsize=8, color='#555')
        ax_top.set_ylabel('Height  (m)', fontsize=8, color='#555')
        ax_top.set_title('Flood Ingress Simulation', fontsize=10,
                         fontweight='bold', color='#1e2433', pad=6)
        ax_top.grid(True, alpha=0.12, lw=0.4, color='#ccc')

        # ground
        ax_top.hlines(0, -0.5, 4.2, colors='#9a7b3e', lw=2.0, zorder=3)
        ax_top.axhspan(-building_height * 0.04, 0,
                       color='#c8a060', alpha=0.22, zorder=2)

        # building walls
        wall_anim = patches.FancyBboxPatch(
            (bx, 0), building_width, building_height,
            boxstyle='square,pad=0',
            lw=1.8, edgecolor='#6a7280', facecolor='#f2ece0', zorder=4)
        ax_top.add_patch(wall_anim)

        # brick lines
        for hy in np.arange(0.25, building_height, 0.25):
            ax_top.hlines(hy, bx, bx + building_width,
                          colors='#d8cfc3', lw=0.28, zorder=5)

        # roof
        rh = building_height * 0.18
        roof_pts = [(bx - 0.06, building_height),
                    (bx + building_width / 2, building_height + rh),
                    (bx + building_width + 0.06, building_height)]
        roof_p = patches.Polygon(roof_pts, closed=True,
                                 facecolor='#7b3600', edgecolor='#5c2900',
                                 lw=1.5, zorder=6)
        ax_top.add_patch(roof_p)

        # ingress markers
        ingress_x = bx + building_width
        items_sorted_anim = sorted(ingress_list, key=lambda ing: ing.height)
        min_lbl_sep = max(0.22, building_height * 0.07)
        label_ys_anim = []
        last_y2 = -999.0
        for ing in items_sorted_anim:
            yl = max(ing.height, last_y2 + min_lbl_sep)
            label_ys_anim.append(yl)
            last_y2 = yl

        for ing, y_lbl in zip(items_sorted_anim, label_ys_anim):
            y = ing.height
            slot_a = patches.FancyBboxPatch(
                (ingress_x - 0.045, y - 0.022), 0.045, 0.045,
                boxstyle='round,pad=0.003',
                facecolor='#c0522a', edgecolor='white', lw=0.4, zorder=7)
            ax_top.add_patch(slot_a)
            if abs(y_lbl - y) > 0.01:
                ax_top.plot([ingress_x + 0.01, ingress_x + 0.09],
                            [y, y_lbl],
                            color='#bbb', lw=0.7, zorder=5)
            ax_top.text(ingress_x + 0.10, y_lbl,
                        getattr(ing, 'name', f'{y:.2f} m'),
                        va='center', fontsize=7, color='#444')

        # interior water patch
        interior_patch = patches.Rectangle(
            (bx + 0.025, 0), building_width - 0.05, 0.0,
            facecolor=_C['indoor'], alpha=0.60, zorder=5)
        ax_top.add_patch(interior_patch)
        interior_lbl = ax_top.text(
            bx + building_width / 2, 0.0, '',
            ha='center', va='bottom', fontsize=9,
            color='#9a3d00', fontweight='bold', zorder=8)

        # exterior water body
        ex_x = 2.25; ex_w = 1.6
        ext_rect = patches.Rectangle(
            (ex_x, 0), ex_w, 0.0,
            facecolor=_C['external'], alpha=0.50, zorder=4)
        ax_top.add_patch(ext_rect)
        ax_top.text(ex_x + ex_w / 2, building_height * 0.96,
                    'External\nwater', ha='center', va='top',
                    fontsize=7.5, color='#1a4d6b', style='italic')
        ext_lbl = ax_top.text(ex_x + ex_w / 2, 0.0, '',
                              ha='center', va='bottom', fontsize=9,
                              color='#1a4d6b', fontweight='bold', zorder=8)

        time_text = ax_top.text(
            bx + 0.04, building_height * 0.93, '',
            fontsize=10, fontweight='bold', color='#1e2433',
            bbox=dict(boxstyle='round,pad=0.30', fc='white',
                      ec='#c0c6cf', alpha=0.85))
        vel_text = ax_top.text(
            ex_x + ex_w / 2, building_height * 0.87, '',
            ha='center', va='center', fontsize=8.5, color='#1e6b41',
            bbox=dict(boxstyle='round,pad=0.20', fc='#e8faf0',
                      ec='#a0d8b3', alpha=0.88))

        ingress_arrows = []

        # ── basement bar panel ────────────────────────────────────────────────
        _bw  = 0.55
        _x_b = 0.20; _x_s = 1.30; _x_end = 2.10
        if ax_b is not None:
            _max_bs = max(basement_levels or [0.0])
            _max_sp = max(sump_levels or [0.0]) if sump_levels is not None else 0.0
            _crest  = sump_overflow_level if sump_overflow_level is not None else 0.0
            _y_max  = max(0.1, _max_bs * 1.3, _max_sp * 1.3, _crest * 1.3) + 0.06
            ax_b.set_xlim(0, _x_end)
            ax_b.set_ylim(0, _y_max)
            ax_b.set_ylabel('Depth  (m)', fontsize=7.5)
            ax_b.grid(True, alpha=0.20, lw=0.4, axis='y')
            ax_b.grid(False, axis='x')
            ax_b.set_xticks([_x_b + _bw / 2, _x_s + _bw / 2])
            ax_b.set_xticklabels(['Basement', 'Sump'], fontsize=8)
            ax_b.tick_params(axis='x', length=0)

            base_perim_patch = patches.Rectangle(
                (_x_b, 0), _bw, 0.0,
                facecolor=_C['basement'], alpha=0.72, hatch='///',
                edgecolor='white', lw=0.4, zorder=3, label='Perimeter inflow')
            ax_b.add_patch(base_perim_patch)
            base_bypass_patch = patches.Rectangle(
                (_x_b, 0), _bw, 0.0,
                facecolor=_C['bypass'], alpha=0.55, hatch='...',
                edgecolor='white', lw=0.4, zorder=3, label='Bypass (gf→bs)')
            ax_b.add_patch(base_bypass_patch)

            if sump_levels is not None:
                sump_bar_patch = patches.Rectangle(
                    (_x_s, 0), _bw, 0.0,
                    facecolor=_C['sump'], alpha=0.80,
                    zorder=3, label='Sump')
                ax_b.add_patch(sump_bar_patch)
                if sump_overflow_level is not None:
                    ax_b.hlines(sump_overflow_level,
                                _x_s - 0.06, _x_s + _bw + 0.06,
                                colors='#c0392b', lw=1.5, ls='--', zorder=5)
                    ax_b.text(_x_s + _bw + 0.08, sump_overflow_level,
                              f'crest\n{sump_overflow_level:.2f} m',
                              va='center', ha='left', fontsize=6.5,
                              color='#c0392b', zorder=6)
            else:
                sump_bar_patch = None

            ax_b.legend(fontsize=6.5, loc='upper right', framealpha=0.80)

        # ── time-series chart ─────────────────────────────────────────────────
        ax_chart.fill_between(sim_times, 0, external_levels,
                              color=_C['external'], alpha=0.08, zorder=1)
        ax_chart.fill_between(sim_times, 0, sim_levels,
                              color=_C['indoor'], alpha=0.14, zorder=2)
        ax_chart.plot(sim_times, external_levels,
                      color=_C['external'], lw=2.0, alpha=0.88,
                      label='External  $h_{out}$', zorder=4)
        ax_chart.plot(sim_times, sim_levels,
                      color=_C['indoor'], lw=2.0, alpha=0.88,
                      label='Ground floor  $h_{in}$', zorder=5)
        if basement_levels is not None:
            bs_lbl = ('Basement: unprotected' if sump_levels is not None
                      else 'Basement  $h_{bs}$')
            ax_chart.plot(sim_times, basement_levels,
                          color=_C['basement'], ls='--', lw=1.6, alpha=0.85,
                          label=bs_lbl, zorder=4)
        if sump_levels is not None:
            ax_chart.plot(sim_times, sump_levels,
                          color=_C['sump'], ls=':', lw=1.6, alpha=0.88,
                          label='Sump  $h_{sump}$', zorder=4)
        ax_chart.legend(fontsize=7, loc='upper left', framealpha=0.92)
        ax_chart.set_xlabel(_xlabel(unit_label), fontsize=9)
        ax_chart.set_ylabel('Water level  (m)', fontsize=9)
        ax_chart.set_title('Water levels', fontsize=10, fontweight='bold', pad=6)
        ax_chart.grid(True, alpha=0.22, lw=0.4)

        cursor_line = ax_chart.axvline(
            sim_times[0], color='#e74c3c', lw=1.6, ls='--', alpha=0.75, zorder=6)

        # ── animation functions ───────────────────────────────────────────────
        def init():
            interior_patch.set_height(0.0)
            ext_rect.set_height(0.0)
            time_text.set_text('')
            interior_lbl.set_text('')
            ext_lbl.set_text('')
            vel_text.set_text('')
            cursor_line.set_xdata([sim_times[0]])
            if ax_b is not None:
                base_perim_patch.set_height(0.0)
                base_bypass_patch.set_height(0.0)
                base_bypass_patch.set_y(0.0)
                if sump_bar_patch is not None:
                    sump_bar_patch.set_height(0.0)
            return []

        def update(frame_i):
            for a in ingress_arrows:
                try:
                    a.remove()
                except Exception:
                    pass
            ingress_arrows.clear()

            i     = frame_indices[frame_i]
            h_in  = sim_levels[i]
            h_out = external_levels[i]
            t_now = sim_times[i]

            interior_patch.set_height(h_in)
            ext_rect.set_height(h_out)

            thr = 0.025 * building_height
            interior_lbl.set_text(f'{h_in:.3f} m' if h_in > thr else '')
            if h_in > thr:
                interior_lbl.set_position((bx + building_width / 2, h_in + 0.01))
            ext_lbl.set_text(f'{h_out:.3f} m' if h_out > thr else '')
            if h_out > thr:
                ext_lbl.set_position((ex_x + ex_w / 2, h_out + 0.01))

            if velocity_series is not None:
                try:
                    vel_text.set_text(f'v = {velocity_series[i]:.2f} m/s')
                except Exception:
                    vel_text.set_text('')

            # basement / sump bars
            if ax_b is not None:
                h_bs = basement_levels[i]
                _cp  = cum_perim[i]; _cb = cum_bypass[i]
                _tot = _cp + _cb
                if _tot > 1e-9:
                    hp = h_bs * (_cp / _tot); hb = h_bs - hp
                elif h_bs > 0:
                    hp = h_bs; hb = 0.0
                else:
                    hp = hb = 0.0
                base_perim_patch.set_height(hp)
                base_bypass_patch.set_y(hp)
                base_bypass_patch.set_height(hb)
                if sump_bar_patch is not None and sump_levels is not None:
                    sump_bar_patch.set_height(sump_levels[i])

            time_text.set_text(f'T = {t_now:.1f} {unit_label}')
            cursor_line.set_xdata([t_now, t_now])

            # flow arrows
            max_area = max((ing.area for ing in ingress_list), default=1.0)
            for ing in ingress_list:
                if not (ing.target == 'ground' or ing.source == 'ground' or
                        (ing.source == 'outside' and ing.target == 'ground')):
                    continue
                Q   = ing.compute_flow(h_out, h_in)
                y   = ing.height
                mag = min(1.0, abs(Q) / max(1e-9, max_area))
                if Q > 0:
                    xa, xb, col = ex_x + 0.05, ingress_x - 0.04, _C['external']
                elif Q < 0:
                    xa, xb, col = ingress_x - 0.04, ex_x + 0.05, _C['indoor']
                else:
                    continue
                arr = ax_top.annotate(
                    '', xy=(xb, y), xytext=(xa, y),
                    arrowprops=dict(arrowstyle='-|>', color=col,
                                   linewidth=1.0 + 3.0 * mag,
                                   shrinkA=0, shrinkB=0))
                ingress_arrows.append(arr)

            # ground↔basement vertical arrows
            if (ax_b is not None and
                    any(abs(q) > 0 for q in Qgb_series)):
                Q_cur = Qgb_series[i] if i < len(Qgb_series) else 0.0
                Q_sc  = max(1e-6, max(abs(q) for q in Qgb_series))
                for ing in ingress_list:
                    src = getattr(ing, 'source', 'outside')
                    tgt = getattr(ing, 'target', 'ground')
                    if not ((src == 'ground' and tgt == 'basement') or
                            (src == 'basement' and tgt == 'ground')):
                        continue
                    y0  = ing.height
                    x0  = ingress_x - 0.08
                    mag = min(1.0, abs(Q_cur) / Q_sc)
                    al  = 0.30 + 0.70 * mag
                    y1  = max(0.0, y0 - 0.3 - 0.7 * mag)
                    col = _C['bypass'] if Q_cur > 0 else _C['basement']
                    arr_v = ax_top.annotate(
                        '', xy=(x0, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle='-|>', color=col,
                                       linewidth=1.0 + 3.5 * mag,
                                       shrinkA=0, shrinkB=0, alpha=al))
                    ingress_arrows.append(arr_v)
                    lbl = ax_top.text(
                        x0 - 0.13, (y0 + y1) / 2.0,
                        f'{Q_cur * 1e3:.2f} L/s',
                        fontsize=7, color='#333', va='center', ha='right',
                        bbox=dict(boxstyle='round,pad=0.12',
                                  fc='white', ec='none'))
                    ingress_arrows.append(lbl)

            return []

        ani = animation.FuncAnimation(
            fig, update, frames=len(frame_indices),
            init_func=init, blit=False)
        try:
            writer = animation.PillowWriter(fps=fps)
            ani.save(outpath, writer=writer, savefig_kwargs={'facecolor': 'white'})
        except Exception:
            writer = animation.FFMpegWriter(fps=fps)
            ani.save(outpath.replace('.gif', '.mp4'), writer=writer)
        finally:
            plt.close(fig)


# ── interpretation dashboard ───────────────────────────────────────────────────

def save_interpretation_dashboard(diag, outpath, time_unit='seconds',
                                  title_suffix=''):
    times    = diag['times']
    n        = len(times)
    has_sump = diag.get('events', {}).get('sump_configured',
               any(q > 0 for q in diag.get('Q_pump', [0])))
    ev       = diag.get('events', {})

    if time_unit == 'minutes':
        t_disp = [t / 60.0 for t in times]; xlabel = 'Time  (min)'
    elif time_unit == 'hours':
        t_disp = [t / 3600.0 for t in times]; xlabel = 'Time  (h)'
    else:
        t_disp = list(times); xlabel = 'Time  (s)'

    n_panels = 5 if has_sump else 4
    fig_h    = 3.6 * n_panels
    fig, axes = plt.subplots(n_panels, 1, figsize=(12, fig_h),
                             constrained_layout=True)
    if n_panels == 1:
        axes = [axes]

    def _shade_pump(ax):
        """Fill pump-on periods with a light purple band (all panels)."""
        if not has_sump:
            return
        pump_state = diag.get('pump_state', [])
        in_on = False; t_on = None
        for k in range(n):
            if k < len(pump_state) and pump_state[k] == 1 and not in_on:
                t_on = t_disp[k]; in_on = True
            elif (k >= len(pump_state) or pump_state[k] == 0) and in_on:
                ax.axvspan(t_on, t_disp[k], alpha=0.08,
                           color=_C['sump'], zorder=0)
                in_on = False
        if in_on:
            ax.axvspan(t_on, t_disp[-1], alpha=0.08,
                       color=_C['sump'], zorder=0)

    def _vline_event(ax, key, colour, label):
        t_ev = ev.get(key)
        if t_ev is None:
            return
        if time_unit == 'minutes':
            t_ev_d = t_ev / 60.0
        elif time_unit == 'hours':
            t_ev_d = t_ev / 3600.0
        else:
            t_ev_d = t_ev
        ax.axvline(t_ev_d, color=colour, lw=1.0, ls=':', alpha=0.60, zorder=3)
        ax.text(t_ev_d, ax.get_ylim()[1] * 0.96, label,
                fontsize=6.5, color=colour, ha='center', va='top', rotation=90)

    # ── Panel 1: water-surface heads ─────────────────────────────────────────
    ax1 = axes[0]
    _shade_pump(ax1)
    ax1.fill_between(t_disp, 0, diag['H_out'],
                     color=_C['external'], alpha=0.08, zorder=1)
    ax1.fill_between(t_disp, 0, diag['h_in'],
                     color=_C['indoor'], alpha=0.14, zorder=2)
    ax1.plot(t_disp, diag['H_out'], color=_C['external'], lw=2.0,
             label='External  $H_{out}$', zorder=4)
    ax1.plot(t_disp, diag['h_in'],  color=_C['indoor'],   lw=2.0,
             label='Ground floor  $h_{in}$', zorder=5)
    if any(v > 1e-6 for v in diag['h_basement']):
        bs_lbl = 'Basement: unprotected' if has_sump else 'Basement  $h_{bs}$'
        ax1.fill_between(t_disp, 0, diag['h_basement'],
                         color=_C['basement'], alpha=0.10, zorder=1)
        ax1.plot(t_disp, diag['h_basement'], color=_C['basement'], lw=1.8,
                 ls='--', label=bs_lbl, zorder=4)
    if has_sump:
        ax1.fill_between(t_disp, 0, diag['h_sump'],
                         color=_C['sump'], alpha=0.12, zorder=2)
        ax1.plot(t_disp, diag['h_sump'], color=_C['sump'], lw=1.8,
                 ls=':', label='Sump  $h_{sump}$', zorder=5)
    ax1.set_xlabel(xlabel); ax1.set_ylabel('Head  (m)')
    title_str = 'Water-surface heads'
    if title_suffix:
        title_str += f'  —  {title_suffix}'
    ax1.set_title(title_str)
    ax1.legend(fontsize=8, loc='upper left')
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f'))

    # ── Panel 2: instantaneous flows ─────────────────────────────────────────
    ax2 = axes[1]
    _shade_pump(ax2)
    ax2.fill_between(t_disp, 0, diag['Q_ext_b'],
                     color=_C['external'], alpha=0.10, zorder=1)
    ax2.plot(t_disp, diag['Q_ext_b'],
             color=_C['external'], lw=1.8, label='Outside → Ground floor', zorder=4)
    ax2.plot(t_disp, diag['Q_b_bs'], color=_C['bypass'], lw=1.6, ls='--',
             label='Ground floor → Basement  (bypass)', zorder=4)
    ax2.plot(t_disp, diag['Q_ext_perimeter'], color=_C['perimeter'], lw=1.8,
             label='Outside → Basement/Sump  (perimeter)', zorder=4)
    if has_sump:
        ax2.plot(t_disp, diag['Q_pump'], color=_C['pump'], lw=1.6, ls='-.',
                 label='Pump discharge', zorder=5)
        ax2.plot(t_disp, diag['Q_sump_overflow'], color=_C['overflow'],
                 lw=1.4, ls=':', label='Sump → Basement overflow', zorder=4)
    ax2.set_xlabel(xlabel); ax2.set_ylabel('Flow rate  (m³/s)')
    ax2.set_title('Instantaneous pathway flows')
    ax2.legend(fontsize=8, loc='upper right')
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x * 1e3:.2f}'))
    ax2.set_ylabel('Flow rate  (L/s)')

    # ── Panel 3: cumulative volumes ───────────────────────────────────────────
    ax3 = axes[2]
    _shade_pump(ax3)
    ax3.fill_between(t_disp, 0, diag['vol_ext_b_cum'],
                     color=_C['external'], alpha=0.10, zorder=1)
    ax3.plot(t_disp, diag['vol_ext_b_cum'],
             color=_C['external'], lw=1.8, label='Outside → Ground floor', zorder=4)
    ax3.plot(t_disp, diag['vol_b_bs_cum'],
             color=_C['bypass'], lw=1.6, ls='--',
             label='Ground floor → Basement  (bypass)', zorder=4)
    ax3.plot(t_disp, diag['vol_perimeter_cum'],
             color=_C['perimeter'], lw=1.8,
             label='Perimeter inflow  (→ basement / sump)', zorder=4)
    if has_sump:
        ax3.plot(t_disp, diag['vol_pump_cum'],
                 color=_C['pump'], lw=1.6, ls='-.',
                 label='Pump discharge', zorder=5)
        ax3.plot(t_disp, diag['vol_sump_overflow_cum'],
                 color=_C['overflow'], lw=1.4, ls=':',
                 label='Sump overflow → Basement', zorder=4)
    ax3.set_xlabel(xlabel); ax3.set_ylabel('Cumulative volume  (m³)')
    ax3.set_title('Cumulative pathway volumes')
    ax3.legend(fontsize=8, loc='upper left')
    ax3.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.4f'))

    # ── Panel 4 (sump): control behaviour ────────────────────────────────────
    if has_sump:
        ax4 = axes[3]
        _shade_pump(ax4)
        ax4.fill_between(t_disp, 0, diag['h_sump'],
                         color=_C['sump'], alpha=0.14, zorder=1)
        ax4.plot(t_disp, diag['h_sump'], color=_C['sump'], lw=2.0,
                 label='Sump depth  $h_s$', zorder=5)
        ax4_r = ax4.twinx()
        ax4_r.spines['right'].set_visible(True)
        ax4_r.spines['right'].set_color('#c8cdd2')
        ax4_r.plot(t_disp, diag['Q_pump'], color=_C['pump'], lw=1.6, ls='-.',
                   label='Pump flow  $Q_p$', zorder=4)
        ax4_r.plot(t_disp, diag['H_lift'], color='#95a5a6', lw=1.2, ls=':',
                   label='Lift head  $H_{lift}$', zorder=3)
        ax4.set_xlabel(xlabel)
        ax4.set_ylabel('Sump depth  (m)', color=_C['sump'])
        ax4_r.set_ylabel('Flow / head  (m³/s  |  m)', color=_C['pump'])
        ax4.set_title('Sump control behaviour')
        # combined legend
        lines1, labels1 = ax4.get_legend_handles_labels()
        lines2, labels2 = ax4_r.get_legend_handles_labels()
        ax4.legend(lines1 + lines2, labels1 + labels2,
                   fontsize=8, loc='upper right')
        panel_idx = 4
    else:
        panel_idx = 3

    # ── Final panel: mass balance + narrative ─────────────────────────────────
    ax5 = axes[panel_idx]
    ax5.axis('off')

    labels_bar = ['Outside → Ground floor', 'Perimeter inflow',
                  'Ground → Basement  (bypass)']
    vals_bar   = [ev.get('vol_ext_b_total', 0.0),
                  ev.get('vol_perimeter_total', 0.0),
                  ev.get('vol_b_bs_total', 0.0)]
    cols_bar   = [_C['external'], _C['perimeter'], _C['bypass']]
    if has_sump:
        labels_bar += ['Pump discharge', 'Sump overflow']
        vals_bar   += [ev.get('vol_pump_total', 0.0),
                       ev.get('vol_sump_overflow_total', 0.0)]
        cols_bar   += [_C['pump'], _C['overflow']]

    ax_bar = ax5.inset_axes([0.01, 0.42, 0.44, 0.54])
    y_pos  = range(len(labels_bar))
    bars   = ax_bar.barh(list(y_pos), vals_bar, color=cols_bar,
                         alpha=0.80, edgecolor='white', linewidth=0.5)
    ax_bar.set_yticks(list(y_pos))
    ax_bar.set_yticklabels(labels_bar, fontsize=7.5)
    ax_bar.set_xlabel('Total volume  (m³)', fontsize=8)
    ax_bar.set_title('Event mass balance', fontsize=9, fontweight='bold')
    ax_bar.tick_params(axis='x', labelsize=7.5)
    ax_bar.bar_label(bars, fmt='%.4f', fontsize=7, padding=3)
    ax_bar.set_xlim(0, (max(vals_bar) * 1.35) if max(vals_bar) > 0 else 1.0)
    ax_bar.grid(True, axis='x', alpha=0.30, lw=0.5)
    ax_bar.grid(False, axis='y')
    ax_bar.spines['top'].set_visible(False)
    ax_bar.spines['right'].set_visible(False)

    try:
        from report import generate_narrative
        bullets = generate_narrative(diag)
    except Exception:
        bullets = []
    bullet_text = ('\n'.join(f'• {b}' for b in bullets)
                   if bullets else '(no summary available)')
    ax5.text(0.52, 0.97, 'Interpretation summary',
             transform=ax5.transAxes,
             fontsize=9.5, fontweight='bold', va='top', color='#1e2433')
    ax5.text(0.52, 0.88, bullet_text,
             transform=ax5.transAxes,
             fontsize=8.5, va='top', color='#2c3140',
             bbox=dict(boxstyle='round,pad=0.5', fc='#f4f6f9',
                       ec='#d0d5dd', alpha=0.95))

    fig.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close(fig)


# ── batch scatter ──────────────────────────────────────────────────────────────

def save_batch_scatter(h_peak_ext, h_peak_int, outpath, *, v_peak=None):
    h_e = list(h_peak_ext)
    h_i = list(h_peak_int)
    n   = len(h_e)

    fig, ax = plt.subplots(figsize=(6, 5.5))

    lim = max(max(h_e, default=0), max(h_i, default=0)) * 1.08
    lim = max(lim, 0.1)

    c_vals   = list(v_peak) if v_peak is not None else h_e
    cb_label = ('Peak exterior velocity  (m/s)' if v_peak is not None
                else 'Peak exterior depth  (m)')
    sc = ax.scatter(h_e, h_i, s=22, alpha=0.80, zorder=3,
                    c=c_vals, cmap='plasma', edgecolors='white', lw=0.4)
    cb = fig.colorbar(sc, ax=ax, pad=0.02)
    cb.set_label(cb_label, fontsize=8)
    cb.ax.tick_params(labelsize=7.5)

    ax.plot([0, lim], [0, lim], color='#888', lw=1.2, ls='--',
            zorder=2, label='1 : 1  (perfect ingress)')

    # Pearson r annotation
    if n > 2:
        r = float(np.corrcoef(h_e, h_i)[0, 1]) if n > 2 else 0.0
        ax.text(0.97, 0.07, f'Pearson  r = {r:.3f}',
                transform=ax.transAxes, ha='right', va='bottom',
                fontsize=8.5, color='#333',
                bbox=dict(boxstyle='round,pad=0.30', fc='white',
                          ec='#bbb', alpha=0.90))

    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel('Peak exterior depth  $h_{out}^{max}$  (m)')
    ax.set_ylabel('Peak interior depth  $h_{in}^{max}$  (m)')
    ax.set_title(f'Batch run  —  {n} cases', pad=10)
    ax.legend(fontsize=8)
    ax.set_aspect('equal')
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


# ── basement scatter ──────────────────────────────────────────────────────────

def save_basement_scatter(h_peak_ext, h_peak_basement, outpath, *, v_peak=None):
    """Scatter of peak exterior depth vs peak basement depth.

    Parameters
    ----------
    h_peak_ext      : sequence of float   Peak exterior depth per case (m).
    h_peak_basement : sequence of float   Peak basement depth per case (m).
    outpath         : str
    v_peak          : sequence of float, optional
        Peak exterior velocity (m/s).  Used for point colour when supplied;
        falls back to colouring by peak exterior depth otherwise.
    """
    h_e = list(h_peak_ext)
    h_b = list(h_peak_basement)
    n   = len(h_e)

    fig, ax = plt.subplots(figsize=(6, 5.5))

    c_vals   = list(v_peak) if v_peak is not None else h_e
    cb_label = ('Peak exterior velocity  (m/s)' if v_peak is not None
                else 'Peak exterior depth  (m)')
    sc = ax.scatter(h_e, h_b, s=22, alpha=0.80, zorder=3,
                    c=c_vals, cmap='plasma', edgecolors='white', lw=0.4)
    cb = fig.colorbar(sc, ax=ax, pad=0.02)
    cb.set_label(cb_label, fontsize=8)
    cb.ax.tick_params(labelsize=7.5)

    if n > 2:
        r = float(np.corrcoef(h_e, h_b)[0, 1])
        ax.text(0.97, 0.07, f'Pearson  r = {r:.3f}',
                transform=ax.transAxes, ha='right', va='bottom',
                fontsize=8.5, color='#333',
                bbox=dict(boxstyle='round,pad=0.30', fc='white',
                          ec='#bbb', alpha=0.90))

    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax.set_ylabel('Peak basement depth  $h_{bsmt}^{max}$  (m)')
    ax.set_title(f'Batch run  —  {n} cases', pad=10)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


# ── loss scatter ───────────────────────────────────────────────────────────────

def _loss_scatter(x_vals, loss_vals, outpath, *, x_label, y_label, title, v_peak=None):
    x    = list(x_vals)
    loss = list(loss_vals)
    n    = len(x)

    fig, ax = plt.subplots(figsize=(7, 5))

    c_vals   = list(v_peak) if v_peak is not None else x
    cb_label = ('Peak exterior velocity  (m/s)' if v_peak is not None
                else x_label)
    sc = ax.scatter(x, loss, s=28, alpha=0.80, zorder=4,
                    c=c_vals, cmap='plasma', edgecolors='white', lw=0.4)
    cb = fig.colorbar(sc, ax=ax, pad=0.02)
    cb.set_label(cb_label, fontsize=8)
    cb.ax.tick_params(labelsize=7.5)

    avg = sum(loss) / n if n > 0 else 0.0
    ax.axhline(avg, color='#c0392b', lw=1.5, ls='--', zorder=2,
               label=f'Mean  GBP {avg:,.0f}')

    if n > 10:
        try:
            order = np.argsort(x)
            x_s   = np.array(x)[order]
            l_s   = np.array(loss)[order]
            bin_w = max(3, n // 12)
            xs, ys = [], []
            for j in range(0, n, max(1, bin_w // 2)):
                sl = slice(j, min(j + bin_w, n))
                xs.append(float(np.mean(x_s[sl])))
                ys.append(float(np.median(l_s[sl])))
            ax.plot(xs, ys, color='#c0392b', lw=2.0, alpha=0.70,
                    label='Running median', zorder=3)
        except Exception:
            pass

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(f'{title}  —  {n} cases', pad=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))
    ax.legend(fontsize=8.5, loc='upper left')
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


def save_loss_scatter(h_peak_ext, aggregate_losses, outpath, *, v_peak=None):
    """Peak exterior depth vs aggregate (combined) content loss."""
    _loss_scatter(h_peak_ext, aggregate_losses, outpath,
                  x_label='Peak exterior depth  $h_{ext}^{max}$  (m)',
                  y_label='Aggregate loss  (GBP)',
                  title='Peak exterior depth vs aggregate loss',
                  v_peak=v_peak)


def save_ground_loss_scatter(h_peak_int, building_losses, outpath, *, v_peak=None):
    """Peak interior (ground-floor) depth vs ground-floor content loss."""
    _loss_scatter(h_peak_int, building_losses, outpath,
                  x_label='Peak interior depth  $h_{in}^{max}$  (m)',
                  y_label='Ground-floor loss  (GBP)',
                  title='Peak interior depth vs ground-floor loss',
                  v_peak=v_peak)


def save_basement_loss_scatter(h_peak_basement, basement_losses, outpath, *, v_peak=None):
    """Peak basement depth vs basement content loss."""
    _loss_scatter(h_peak_basement, basement_losses, outpath,
                  x_label='Peak basement depth  $h_{bsmt}^{max}$  (m)',
                  y_label='Basement loss  (GBP)',
                  title='Peak basement depth vs basement loss',
                  v_peak=v_peak)


# ── fragility Monte Carlo result ───────────────────────────────────────────────

def save_mc_result(peak_h_in, peak_h_ext, state_freq_rows, title, outpath):
    """Scatter + empirical CDF + state-frequency bar chart for a MC run.

    Parameters
    ----------
    peak_h_in : sequence of float
        Peak interior depth per replicate (m).
    peak_h_ext : sequence of float
        Peak exterior depth per replicate (m).
    state_freq_rows : list of dict
        Rows from fragility_state_freq.csv — each dict has keys
        ``element``, ``state_0_freq``, ``state_1_freq``, ...
    title : str
    outpath : str
    """
    import matplotlib as _mpl

    peak_h  = np.asarray(peak_h_in,  dtype=float)
    peak_ex = np.asarray(peak_h_ext, dtype=float)
    n = len(peak_h)

    threshold = float(peak_h.max()) * 0.05 if peak_h.max() > 0 else 0.01
    low_mask  = peak_h < threshold
    high_mask = ~low_mask
    n_low, n_high = int(low_mask.sum()), int(high_mask.sum())

    _BLUE   = '#2980b9'
    _ORANGE = '#e67e22'
    _RED    = '#c0392b'
    PCT_COLOURS = {'P25': '#2980b9', 'P50': '#c0392b', 'P75': '#2980b9'}

    fig = plt.figure(figsize=(14, 6.5))
    fig.patch.set_facecolor('white')
    gs = gridspec.GridSpec(1, 2, figure=fig, width_ratios=[2.8, 1],
                           wspace=0.32, left=0.07, right=0.97,
                           top=0.88, bottom=0.12)

    ax_s = fig.add_subplot(gs[0, 0])

    sc_handles = []
    if n_high > 0 and n_low > 0:
        sc1 = ax_s.scatter(peak_h[low_mask],  peak_ex[low_mask],
                           color=_BLUE,   alpha=0.45, s=22, zorder=3,
                           linewidths=0, label=f'Intact  (n = {n_low})')
        sc2 = ax_s.scatter(peak_h[high_mask], peak_ex[high_mask],
                           color=_ORANGE, alpha=0.55, s=22, zorder=4,
                           linewidths=0, label=f'Degraded  (n = {n_high})')
        sc_handles = [sc1, sc2]
    else:
        sc = ax_s.scatter(peak_h, peak_ex, color=_BLUE, alpha=0.45,
                          s=22, zorder=3, linewidths=0, label=f'n = {n}')
        sc_handles = [sc]

    ax_s.set_xlabel('Peak interior depth  $h_{in}^{max}$  (m)')
    ax_s.set_ylabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax_s.set_xlim(left=0)
    ext_range = float(peak_ex.max() - peak_ex.min())
    if ext_range < 1e-4:
        mid = float(peak_ex.mean())
        ax_s.set_ylim(mid * 0.7, mid * 1.3)
    else:
        ax_s.set_ylim(bottom=0)

    ax_cdf = ax_s.twinx()
    ax_cdf.spines['right'].set_visible(True)
    ax_cdf.spines['right'].set_color('#c8cdd2')
    ax_cdf.spines['right'].set_linewidth(0.8)
    h_sort  = np.sort(peak_h)
    cdf_pct = np.linspace(100.0 / n, 100.0, n)
    ax_cdf.fill_between(h_sort, cdf_pct, step='post', color=_RED, alpha=0.06)
    cdf_line, = ax_cdf.step(h_sort, cdf_pct, color=_RED, lw=1.8,
                             where='post', zorder=5, label='Empirical CDF')
    ax_cdf.set_ylim(0, 108)
    ax_cdf.set_ylabel('Cumulative probability  (%)', color=_RED)
    ax_cdf.tick_params(axis='y', labelcolor=_RED)
    ax_cdf.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.0f}%'))
    ax_cdf.grid(False)
    for pname, pct_val in [('P25', 25), ('P50', 50), ('P75', 75)]:
        pv = float(np.percentile(peak_h, pct_val))
        ax_cdf.plot([pv, pv], [0, pct_val],
                    color=PCT_COLOURS[pname], lw=0.8, ls=':', alpha=0.6)
        ax_cdf.plot([0, pv], [pct_val, pct_val],
                    color=PCT_COLOURS[pname], lw=0.8, ls=':', alpha=0.6)
    ax_s.legend(handles=sc_handles + [cdf_line], fontsize=8, loc='upper right')
    ax_s.set_title('Peak $h_{ext}$ vs peak $h_{in}$ — scatter and empirical CDF')

    ax_sf = fig.add_subplot(gs[0, 1])
    if state_freq_rows:
        state_cols = sorted(
            [k for k in state_freq_rows[0] if k.startswith('state_')],
            key=lambda c: int(c.split('_')[1]))
        elems = [r['element'] for r in state_freq_rows]
        n_el, n_st = len(elems), len(state_cols)
        x  = np.arange(n_el)
        bw = 0.75 / max(n_st, 1)
        blues = _mpl.colormaps.get_cmap('Blues_r')
        for si, col in enumerate(state_cols):
            freqs  = [float(r.get(col, 0) or 0) for r in state_freq_rows]
            colour = blues(0.15 + 0.60 * si / max(n_st - 1, 1))
            b = ax_sf.bar(x + si * bw, freqs, bw, label=f'State {si}',
                          color=colour, edgecolor='white', lw=0.4, zorder=3)
            ax_sf.bar_label(b, fmt='%.2f', fontsize=7, padding=2, color='#333')
        ax_sf.set_xticks(x + bw * (n_st - 1) / 2)
        ax_sf.set_xticklabels(
            [e.replace('membrane:', 'mem:')[:16] for e in elems],
            rotation=30, ha='right', fontsize=7.5)
        ax_sf.set_ylabel('Fraction of replicates')
        ax_sf.set_title('Element state frequencies')
        ax_sf.set_ylim(0, 1.30)
        ax_sf.legend(fontsize=7.5, loc='upper right')
        ax_sf.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f'{x:.0%}'))
        expl = ('Each bar: fraction of replicates\n'
                'in exactly that state.\n\n'
                'State 0  base state (not degraded)\n'
                'State k  degraded to state k\n\n'
                'Bars sum to 100 % per element.')
        ax_sf.text(0.04, 0.60, expl, transform=ax_sf.transAxes,
                   fontsize=7.2, va='top', ha='left', color='#444',
                   bbox=dict(boxstyle='round,pad=0.4', fc='white',
                             ec='#d0d5dd', alpha=0.95))
    else:
        ax_sf.text(0.5, 0.5, 'No state data', transform=ax_sf.transAxes,
                   ha='center', va='center', fontsize=10, color='#888')

    fig.suptitle(title, fontsize=13, fontweight='bold', color='#1e2433', y=0.97)
    if n_low > 0 and n_high > 0:
        split_txt = (f'{n_low}/{n} replicates at near-zero ({100*n_low/n:.1f}%)\n'
                     f'{n_high}/{n} replicates with significant ingress ({100*n_high/n:.1f}%)')
        fig.text(0.42, 0.935, split_txt, ha='center', va='top',
                 fontsize=8.5, color='#444', style='italic',
                 bbox=dict(boxstyle='round,pad=0.35', fc='#f4f6f9',
                           ec='#d0d5dd', alpha=0.95))

    fig.savefig(outpath, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)


# ── batch deterministic ────────────────────────────────────────────────────────

def save_batch_deterministic(h_ext, h_int, title, outpath, *, v_peak=None):
    """Scatter h_ext vs h_int + attenuation ratio for a deterministic batch run.

    Parameters
    ----------
    h_ext  : sequence of float   Peak exterior depths (m).
    h_int  : sequence of float   Peak interior depths (m).
    title  : str
    outpath: str
    v_peak : sequence of float, optional
        Peak exterior velocity (m/s) per case.  When supplied, points are
        coloured by velocity; otherwise coloured by peak exterior depth.
    """
    _ORANGE = '#e67e22'
    _GREY   = '#7f8c8d'

    h_e = np.asarray(h_ext, dtype=float)
    h_i = np.asarray(h_int, dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.patch.set_facecolor('white')

    ax = axes[0]
    lim = max(h_e.max(), h_i.max()) * 1.08
    c_vals   = np.asarray(v_peak, dtype=float) if v_peak is not None else h_e
    cb_label = ('Peak exterior velocity  (m/s)' if v_peak is not None
                else 'Peak exterior depth  (m)')
    sc0 = ax.scatter(h_e, h_i, s=55, alpha=0.85, zorder=4,
                     c=c_vals, cmap='plasma', edgecolors='white', lw=0.5)
    cb0 = fig.colorbar(sc0, ax=ax, pad=0.02)
    cb0.set_label(cb_label, fontsize=8)
    cb0.ax.tick_params(labelsize=7.5)
    ax.plot([0, lim], [0, lim], color=_GREY, lw=1.0, ls='--', alpha=0.5,
            label='$h_{in}$ = $h_{ext}$  (no attenuation)')
    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax.set_ylabel('Peak interior depth  $h_{in}^{max}$  (m)')
    ax.set_title('Peak $h_{ext}$ vs peak $h_{in}$')
    ax.legend(fontsize=8)

    ax2 = axes[1]
    ratio = np.where(h_e > 1e-6, h_i / h_e, np.nan)
    ax2.scatter(h_e, ratio, color=_ORANGE, alpha=0.7, s=55, zorder=4,
                edgecolors='white', lw=0.5)
    ax2.axhline(1.0, color=_GREY, lw=1.0, ls='--', alpha=0.5)
    ax2.set_xlim(0)
    ax2.set_ylim(0, min(1.5, float(np.nanmax(ratio)) * 1.15))
    ax2.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax2.set_ylabel('Attenuation ratio  $h_{in} / h_{ext}$')
    ax2.set_title('Interior / exterior attenuation ratio')
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.2f}'))

    fig.suptitle(title, fontsize=12, fontweight='bold', color='#1e2433', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(outpath, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)


# ── batch fragility MC ─────────────────────────────────────────────────────────

def save_batch_mc_fragility(h_ext_all, h_int_all, title, outpath,
                             membrane_median_m=None):
    """Replicate scatter + P10/P50/P90 bands + fragility curve.

    Parameters
    ----------
    h_ext_all : sequence of float   Peak exterior depth per replicate (m).
    h_int_all : sequence of float   Peak interior depth per replicate (m).
    title : str
    outpath : str
    membrane_median_m : float, optional
        If given, draws a vertical reference line at this depth on the
        fragility curve panel.
    """
    from collections import defaultdict

    _BLUE   = '#2980b9'
    _ORANGE = '#e67e22'
    _RED    = '#c0392b'
    _GREY   = '#7f8c8d'

    h_e = np.asarray(h_ext_all, dtype=float)
    h_i = np.asarray(h_int_all, dtype=float)

    by_level = defaultdict(list)
    for he, hi in zip(h_e, h_i):
        by_level[round(float(he), 4)].append(float(hi))

    levels  = np.array(sorted(by_level))
    p10_arr = np.array([np.percentile(by_level[lv], 10) for lv in levels])
    p50_arr = np.array([np.percentile(by_level[lv], 50) for lv in levels])
    p90_arr = np.array([np.percentile(by_level[lv], 90) for lv in levels])
    threshold = float(h_i.max()) * 0.05 if h_i.max() > 0 else 0.01
    p_fail  = np.array([np.mean(np.array(by_level[lv]) > threshold)
                        for lv in levels])

    fig = plt.figure(figsize=(14, 5.5))
    fig.patch.set_facecolor('white')
    gs = gridspec.GridSpec(1, 2, figure=fig, wspace=0.34,
                           left=0.07, right=0.97, top=0.88, bottom=0.12)

    ax_s = fig.add_subplot(gs[0, 0])
    sc_s = ax_s.scatter(h_e, h_i, alpha=0.30, s=14, zorder=2, linewidths=0,
                        c=h_e, cmap='plasma')
    cb_s = fig.colorbar(sc_s, ax=ax_s, pad=0.02)
    cb_s.set_label('Peak exterior depth  (m)', fontsize=8)
    cb_s.ax.tick_params(labelsize=7.5)
    ax_s.fill_between(levels, p10_arr, p90_arr, alpha=0.20, color=_ORANGE)
    ax_s.plot(levels, p10_arr, color=_ORANGE, lw=1.0, ls='--', alpha=0.8,
              label='P10 / P90')
    ax_s.plot(levels, p90_arr, color=_ORANGE, lw=1.0, ls='--', alpha=0.8)
    ax_s.plot(levels, p50_arr, color=_RED, lw=2.0, ls='-', zorder=5,
              label='P50 (median)')
    ax_s.set_xlim(0); ax_s.set_ylim(bottom=0)
    ax_s.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax_s.set_ylabel('Peak interior depth  $h_{in}^{max}$  (m)')
    ax_s.set_title('Replicate scatter + P10 / P50 / P90 bands')
    ax_s.legend(fontsize=8, loc='upper left', handles=[
        plt.Line2D([0], [0], color=_ORANGE, lw=1.0, ls='--', label='P10 / P90'),
        plt.Line2D([0], [0], color=_RED,    lw=2.0, ls='-',  label='P50 (median)'),
    ])

    ax_f = fig.add_subplot(gs[0, 1])
    ax_f.fill_between(levels, p_fail * 100, alpha=0.15, color=_RED, step='mid')
    ax_f.step(levels, p_fail * 100, color=_RED, lw=2.0, where='mid',
              label='Failure probability')
    ax_f.set_xlim(0); ax_f.set_ylim(0, 108)
    ax_f.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax_f.set_ylabel('P(significant ingress)  (%)')
    ax_f.set_title('Fragility curve\n'
                   r'(fraction of replicates with $h_{in} > 5\%\,h_{in}^{max}$)')
    ax_f.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.0f}%'))
    if membrane_median_m is not None:
        ax_f.axvline(membrane_median_m, color=_GREY, lw=0.9, ls=':', alpha=0.6,
                     label=f'Membrane median  {membrane_median_m} m')
    ax_f.legend(fontsize=8, loc='upper left')

    n_hydros = len(levels)
    n_reps   = len(h_e) // n_hydros if n_hydros else 0
    fig.suptitle(f'{title}\n'
                 f'({n_hydros} hydrographs × {n_reps} replicates = {len(h_e)} total)',
                 fontsize=12, fontweight='bold', color='#1e2433', y=0.99)

    fig.savefig(outpath, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)


# ── building schematics ────────────────────────────────────────────────────────

import matplotlib.patches as _mpatches  # noqa: E402 — late import avoids circular

_SCH_BLACK    = '#1c2027'
_SCH_RED      = '#c0392b'
_SCH_BLUE     = '#2980b9'
_SCH_EARTH_FC = '#c8b89a'
_SCH_EARTH_EC = '#a09070'
_SCH_INT_GF   = '#f5f6f7'
_SCH_INT_BS   = '#edf0f2'

_SCH_W       = 1.0
_SCH_EXT_W   = 0.45
_SCH_LW_WALL = 1.8
_SCH_LW_THIN = 0.9
_SCH_TICK    = 0.13
_SCH_SUMP_W  = 0.22
_SCH_SUMP_D  = 0.28

SCHEMATIC_CASES = [
    dict(label='Case 01', subtitle='Single opening\nsill = 0 m',
         floor_h=2.5, bsmt_d=None, sump=False, pump=False,
         gf_paths=[dict(sill=0.0, name='door gap', style='det')],
         bsmt_paths=[], membrane=None),
    dict(label='Case 02', subtitle='Raised sill\nsill = 0.3 m',
         floor_h=2.5, bsmt_d=None, sump=False, pump=False,
         gf_paths=[dict(sill=0.3, name='door gap', style='det')],
         bsmt_paths=[], membrane=None),
    dict(label='Case 03', subtitle='Two openings\nsills 0 m and 0.3 m',
         floor_h=2.5, bsmt_d=None, sump=False, pump=False,
         gf_paths=[dict(sill=0.0, name='crack', style='det'),
                   dict(sill=0.3, name='door gap', style='det')],
         bsmt_paths=[], membrane=None),
    dict(label='Case 04', subtitle='Basement\n(no pump)',
         floor_h=2.5, bsmt_d=2.5, sump=False, pump=False,
         gf_paths=[],
         bsmt_paths=[dict(sill=0.0, name='bsmt crack', style='det')],
         membrane=None),
    dict(label='Case 05', subtitle='Basement + pump\n(keeps up)',
         floor_h=2.5, bsmt_d=2.5, sump=True, pump=True,
         gf_paths=[],
         bsmt_paths=[dict(sill=0.0, name='bsmt crack', style='det')],
         membrane=None),
    dict(label='Case 06', subtitle='Basement + pump\n(overwhelmed)',
         floor_h=2.5, bsmt_d=2.5, sump=True, pump=True,
         gf_paths=[],
         bsmt_paths=[dict(sill=0.0, name='bsmt crack', style='det')],
         membrane=None),
    dict(label='Case 07', subtitle='Probabilistic seal\n(MC fragility)',
         floor_h=2.5, bsmt_d=None, sump=False, pump=False,
         gf_paths=[dict(sill=0.0, name='seal door', style='prob')],
         bsmt_paths=[], membrane=None),
    dict(label='Case 08', subtitle='Membrane group\n(probabilistic)',
         floor_h=2.5, bsmt_d=None, sump=False, pump=False,
         gf_paths=[dict(sill=0.0, name='door gap', style='behind'),
                   dict(sill=0.1, name='airbrick', style='behind')],
         bsmt_paths=[],
         membrane=dict(sill=0.0, capacity=0.5, style='prob')),
    dict(label='Case 09', subtitle='Membrane\n(deterministic)',
         floor_h=2.5, bsmt_d=None, sump=False, pump=False,
         gf_paths=[dict(sill=0.0, name='door gap', style='behind'),
                   dict(sill=0.1, name='airbrick', style='behind')],
         bsmt_paths=[],
         membrane=dict(sill=0.0, capacity=0.6, style='det')),
]


def draw_schematic(ax, cfg):
    """Draw one building cross-section schematic on *ax*.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to draw on (axis is turned off inside this function).
    cfg : dict
        Case configuration dict.  Required keys: ``label``, ``subtitle``,
        ``floor_h``, ``gf_paths``, ``bsmt_paths``.  Optional: ``bsmt_d``,
        ``sump``, ``pump``, ``membrane``.  See ``SCHEMATIC_CASES`` for
        worked examples.
    """
    floor_h       = cfg['floor_h']
    bsmt_d        = cfg.get('bsmt_d') or 0.0
    has_sump      = cfg.get('sump', False) and bsmt_d > 0
    has_pump      = cfg.get('pump', False) and bsmt_d > 0
    membrane      = cfg.get('membrane')
    bypass_height = cfg.get('bypass_height', 0.0) or 0.0

    y_gnd  = 0.0
    y_top  = floor_h
    y_bsmt = -bsmt_d
    y_sump = y_bsmt - _SCH_SUMP_D
    # when bypass_height > 0 the GF slab sits at that elevation above datum
    y_slab = bypass_height if (bsmt_d > 0 and bypass_height > 0) else y_gnd
    # GF is drawn solid only up to y_clip_gf; dotted above (break indicator)
    y_clip_gf = float(cfg.get('y_clip_gf') or floor_h)

    x_lo = -(_SCH_EXT_W + 0.15)
    x_hi = _SCH_W + _SCH_EXT_W + 0.40
    y_lo = (y_sump - 0.20) if has_sump else ((y_bsmt - 0.20) if bsmt_d else -0.35)
    y_hi = y_top + 0.30

    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.axis('off')

    soil_bot = y_lo
    for x0f, wf in [(-_SCH_EXT_W, _SCH_EXT_W), (_SCH_W, _SCH_EXT_W)]:
        ax.add_patch(_mpatches.Rectangle(
            (x0f, soil_bot), wf, y_gnd - soil_bot,
            fc=_SCH_EARTH_FC, ec=_SCH_EARTH_EC, lw=0.35, hatch='//////', zorder=1))
    ax.plot([-(_SCH_EXT_W + 0.10), _SCH_W + _SCH_EXT_W + 0.10],
            [y_gnd, y_gnd], color=_SCH_BLACK, lw=_SCH_LW_THIN, zorder=4)

    y_fill_top = min(y_clip_gf, y_top)
    ax.add_patch(_mpatches.Rectangle(
        (0, y_slab), _SCH_W, y_fill_top - y_slab, fc=_SCH_INT_GF, ec='none', zorder=2))
    if bsmt_d > 0:
        ax.add_patch(_mpatches.Rectangle(
            (0, y_bsmt), _SCH_W, bsmt_d + y_slab, fc=_SCH_INT_BS, ec='none', zorder=2))

    wall_bot = y_bsmt if bsmt_d > 0 else y_gnd
    for xw in (0.0, _SCH_W):
        ax.plot([xw, xw], [wall_bot, y_clip_gf],
                color=_SCH_BLACK, lw=_SCH_LW_WALL, zorder=5)
        if y_clip_gf < y_top:
            ax.plot([xw, xw], [y_clip_gf, y_top],
                    color=_SCH_BLACK, lw=_SCH_LW_WALL * 0.7,
                    ls=(0, (3, 2)), zorder=5)
            # break marks
            for dx in (-0.03, 0.03):
                ax.plot([xw + dx, xw - dx],
                        [y_clip_gf - 0.04, y_clip_gf + 0.04],
                        color=_SCH_BLACK, lw=0.8, zorder=6)
    ax.plot([0, _SCH_W], [y_top, y_top],    color=_SCH_BLACK, lw=_SCH_LW_WALL, zorder=5)
    ax.plot([0, _SCH_W], [wall_bot, wall_bot], color=_SCH_BLACK, lw=_SCH_LW_WALL, zorder=5)
    if bsmt_d > 0:
        ax.plot([0, _SCH_W], [y_slab, y_slab],
                color=_SCH_BLACK, lw=_SCH_LW_THIN, ls=(0, (4, 3)), alpha=0.55, zorder=4)

    sump_cx = _SCH_W * 0.75
    sump_cy = y_bsmt
    if has_sump:
        sx0 = _SCH_W - 0.08 - _SCH_SUMP_W
        sx1 = _SCH_W - 0.08
        sy_top, sy_bot = y_bsmt, y_sump
        ax.add_patch(_mpatches.Rectangle(
            (sx0, sy_bot), _SCH_SUMP_W, _SCH_SUMP_D,
            fc='white', ec='none', zorder=3))
        ax.plot([0, sx0],   [sy_top, sy_top], color=_SCH_BLACK, lw=_SCH_LW_WALL, zorder=6)
        ax.plot([sx0, sx0], [sy_top, sy_bot], color=_SCH_BLACK, lw=_SCH_LW_WALL, zorder=6)
        ax.plot([sx0, sx1], [sy_bot, sy_bot], color=_SCH_BLACK, lw=_SCH_LW_WALL, zorder=6)
        ax.plot([sx1, sx1], [sy_bot, sy_top], color=_SCH_BLACK, lw=_SCH_LW_WALL, zorder=6)
        ax.plot([sx1, _SCH_W], [sy_top, sy_top], color=_SCH_BLACK, lw=_SCH_LW_WALL, zorder=6)
        sump_cx = (sx0 + sx1) / 2
        sump_cy = (sy_top + sy_bot) / 2

    if has_pump:
        arrow_y = sump_cy
        x_tip = _SCH_W + _SCH_EXT_W - 0.05
        ax.plot([sump_cx, x_tip], [arrow_y, arrow_y],
                color=_SCH_BLUE, lw=1.6, ls=(0, (4, 2.5)),
                solid_capstyle='butt', zorder=6)
        ax.annotate('', xy=(x_tip, arrow_y), xytext=(x_tip - 0.001, arrow_y),
                    arrowprops=dict(arrowstyle='-|>', color=_SCH_BLUE,
                                   lw=1.6, mutation_scale=11), zorder=7)
        ax.text(x_tip + 0.04, arrow_y + 0.07, r'$Q_p$',
                color=_SCH_BLUE, fontsize=6.5, ha='left', va='bottom', zorder=7)

    def _path(sill_y, style, name):
        if style == 'det':
            ax.plot([-_SCH_TICK, _SCH_TICK], [sill_y, sill_y],
                    color=_SCH_RED, lw=2.4, solid_capstyle='round', zorder=8)
            ax.text(-_SCH_TICK - 0.05, sill_y, name,
                    ha='right', va='center', fontsize=6.0, color=_SCH_RED)
        elif style == 'prob':
            bh = 0.13
            ax.add_patch(_mpatches.FancyBboxPatch(
                (-0.045, sill_y - bh), 0.09, 2 * bh,
                boxstyle='round,pad=0.01',
                fc=_SCH_BLUE, ec=_SCH_BLUE, lw=0.5, alpha=0.80, zorder=8))
            ax.plot([-_SCH_TICK, _SCH_TICK], [sill_y, sill_y],
                    color=_SCH_RED, lw=1.0, ls='--', alpha=0.45, zorder=7)
            ax.text(-_SCH_TICK - 0.05, sill_y, name,
                    ha='right', va='center', fontsize=6.0, color=_SCH_BLUE)
        elif style == 'behind':
            ax.plot([-_SCH_TICK * 0.55, _SCH_TICK * 0.55], [sill_y, sill_y],
                    color=_SCH_RED, lw=1.4, alpha=0.32,
                    solid_capstyle='round', zorder=7)
            ax.text(-_SCH_TICK * 0.55 - 0.05, sill_y, name,
                    ha='right', va='center', fontsize=5.5,
                    color=_SCH_RED, alpha=0.38)

    for p in cfg.get('gf_paths', []):
        _path(p['sill'], p['style'], p.get('name', ''))
    for p in cfg.get('bsmt_paths', []):
        _path(p['sill'], p['style'], p.get('name', ''))

    if membrane is not None:
        y_m  = membrane.get('sill', 0.0)
        cap  = membrane.get('capacity', 0.5)
        ls_m = (0, (5, 3)) if membrane.get('style') == 'prob' else '-'
        x_m0 = -(_SCH_EXT_W - 0.05)
        ax.plot([x_m0, 0.0], [y_m, y_m],
                color=_SCH_BLUE, lw=2.2, ls=ls_m,
                solid_capstyle='butt', zorder=8)
        x_cap = x_m0 + 0.06
        ax.plot([x_cap, x_cap], [y_m, y_m + cap],
                color=_SCH_BLUE, lw=0.9, ls=':', alpha=0.65, zorder=7)
        ax.plot([x_cap - 0.04, x_cap + 0.04], [y_m + cap, y_m + cap],
                color=_SCH_BLUE, lw=0.9, alpha=0.65, zorder=7)
        prob_tag = ' (prob.)' if membrane.get('style') == 'prob' else ''
        ax.text(x_m0 - 0.03, y_m + cap / 2,
                f'membrane\n{cap:.1f} m{prob_tag}',
                ha='right', va='center', fontsize=5.5, color=_SCH_BLUE,
                style='italic' if membrane.get('style') == 'prob' else 'normal',
                zorder=8)

    ax.text(0.05, y_top - 0.12, cfg['label'],
            ha='left', va='top', fontsize=7.5, fontweight='bold',
            color='#1e2433', zorder=9)
    ax.text(0.05, y_top - 0.32, cfg['subtitle'],
            ha='left', va='top', fontsize=6.2, color='#3a4254',
            linespacing=1.35, zorder=9)
    ax.text(-(_SCH_EXT_W / 2), y_hi - 0.05, 'exterior',
            ha='center', va='top', fontsize=5.5, color='#888', style='italic')
    ax.plot([_SCH_W + 0.04, _SCH_W + 0.10], [y_gnd, y_gnd],
            color='#aaa', lw=0.7, zorder=4)
    ax.text(_SCH_W + 0.13, y_gnd, '0 m',
            ha='left', va='center', fontsize=5.0, color='#999')


def save_all_schematics(outpath, cases=None):
    """Draw all case-study schematics in a 3 × 3 grid and save to *outpath*.

    Parameters
    ----------
    outpath : str
        Destination path for the PNG.
    cases : list of dict, optional
        Case configs to draw.  Defaults to ``SCHEMATIC_CASES`` (Cases 01–09).
    """
    if cases is None:
        cases = SCHEMATIC_CASES

    plt.rcParams.update({'font.family': 'sans-serif',
                         'font.sans-serif': ['Helvetica Neue', 'Arial',
                                             'DejaVu Sans']})
    fig, axes = plt.subplots(
        3, 3, figsize=(13, 13),
        gridspec_kw={'height_ratios': [1.0, 1.9, 1.0],
                     'hspace': 0.14, 'wspace': 0.10})
    fig.patch.set_facecolor('white')

    for ax, cfg in zip(axes.flat, cases):
        draw_schematic(ax, cfg)

    legend_items = [
        _mpatches.Patch(fc=_SCH_RED,  ec=_SCH_RED,  lw=0,
                        label='Deterministic ingress path (red tick)'),
        _mpatches.Patch(fc=_SCH_BLUE, ec=_SCH_BLUE, lw=0,
                        label='Probabilistic seal — fragility element (blue bar)'),
        _mpatches.Patch(fc='none', ec=_SCH_BLUE, lw=0,
                        label='Protected path (faint tick — behind membrane)'),
        Line2D([0], [0], color=_SCH_BLUE, lw=2, ls=(0, (5, 3)),
               label='Probabilistic membrane (blue dashed)'),
        Line2D([0], [0], color=_SCH_BLUE, lw=2, ls='-',
               label='Deterministic membrane (blue solid)'),
        Line2D([0], [0], color=_SCH_BLUE, lw=1.6, ls=(0, (4, 2.5)),
               marker='>', markersize=5, markevery=[-1],
               label='Pump discharge (dashed arrow)'),
    ]
    fig.legend(handles=legend_items, loc='lower center', ncol=3,
               fontsize=7.5, framealpha=0.95, edgecolor='#d0d5dd',
               bbox_to_anchor=(0.5, 0.01))
    fig.suptitle('Case study building schematics — cross-section',
                 fontsize=13, fontweight='bold', color='#1e2433', y=0.995)

    fig.savefig(outpath, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return outpath


def save_run_schematic(outpath, *,
                       gf_pathways=(),
                       bsmt_pathways=(),
                       membranes=(),
                       basement_depth=None,
                       has_sump=False,
                       has_pump=False,
                       floor_h=2.5,
                       bypass_height=0.0,
                       label='',
                       subtitle=''):
    """Save a single building cross-section schematic with embedded pathway table.

    Replaces the separate ingress_preview and ingress_locations plots.

    Parameters
    ----------
    outpath         : str   Destination PNG path.
    gf_pathways     : iterable of FragilePath or IngressPathway
    bsmt_pathways   : iterable of FragilePath or IngressPathway
    membranes       : iterable of Membrane
    basement_depth  : float or None  Absolute basement depth below datum (m).
    has_sump        : bool
    has_pump        : bool
    floor_h         : float  Floor-to-ceiling height for display (m).
    label           : str
    subtitle        : str
    """
    def _sill(p):
        v = getattr(p, 'height_m', None)
        return v if v is not None else float(getattr(p, 'height', 0.0))

    def _area(p):
        # prefer fragility state area (the opened area) when available
        frag = getattr(p, 'fragility', None)
        if frag is not None:
            states = getattr(frag, 'states', [])
            if states:
                st_a = getattr(states[0], 'area_m2', None)
                if st_a is not None and st_a > 0:
                    return float(st_a)
        v = getattr(p, 'area_m2', None)
        return v if v is not None else float(getattr(p, 'area', 0.0))

    def _cd(p):
        v = getattr(p, 'Cd', None)
        return v if v is not None else float(getattr(p, 'coeff', 0.6))

    def _style(p):
        if getattr(p, 'group_id', 0):
            return 'behind'
        if getattr(p, 'fragility', None) is not None:
            return 'prob'
        return 'det'

    def _path_dict(p):
        return {'sill': _sill(p), 'name': getattr(p, 'name', ''), 'style': _style(p)}

    mem_cfg = None
    for m in membranes:
        states = m.fragility.states if m.fragility else []
        if states:
            cap   = states[0].median_m
            style = 'prob' if states[0].beta_ln > 0 else 'det'
        else:
            cap, style = _sill(m), 'det'
        mem_cfg = {'sill': _sill(m), 'capacity': cap, 'style': style}
        break

    y_visible_hi = floor_h + 0.3
    y_visible_lo = -(basement_depth or 0.0) - 0.25

    def _in_view(pd):
        return y_visible_lo <= pd['sill'] <= y_visible_hi

    import math as _math

    # ── fragility uncertainty range helper ────────────────────────────────────
    def _frag_range(p):
        frag = getattr(p, 'fragility', None)
        if frag is None:
            return None
        states = getattr(frag, 'states', [])
        if not states:
            return None
        s = states[0]
        beta = getattr(s, 'beta_ln', 0.0)
        med  = getattr(s, 'median_m', _sill(p))
        if beta <= 0:
            return None
        return (med * _math.exp(-beta), med * _math.exp(beta))

    # ── collect all_pw with fragility range ───────────────────────────────────
    all_pw = []
    for p in gf_pathways:
        pd = _path_dict(p)
        if _in_view(pd):
            all_pw.append({'name': getattr(p, 'name', ''), 'sill': _sill(p),
                           'area': _area(p), 'cd': _cd(p),
                           'style': _style(p), 'is_bsmt': False,
                           'frag_range': _frag_range(p)})
    for p in bsmt_pathways:
        pd = _path_dict(p)
        if _in_view(pd):
            all_pw.append({'name': getattr(p, 'name', ''), 'sill': _sill(p),
                           'area': _area(p), 'cd': _cd(p),
                           'style': 'det', 'is_bsmt': True,
                           'frag_range': None})

    bsmt_d  = float(basement_depth or 0.0)
    y_slab  = float(bypass_height or 0.0) if bsmt_d > 0 else 0.0

    # ── zoom y-range: all sill heights + fragility ranges + bypass slab ─────
    all_sills = [pw['sill'] for pw in all_pw]
    if bsmt_d > 0:
        all_sills.append(y_slab)
    # include fragility range extents so uncertainty bars are always visible
    for pw in all_pw:
        fr = pw.get('frag_range')
        if fr:
            all_sills.extend(fr)
    _zm = 0.20
    if all_sills:
        zoom_ylo = min(all_sills) - _zm
        zoom_yhi = max(all_sills) + _zm
    else:
        zoom_ylo, zoom_yhi = -0.15, 0.35

    # ── GF clip height ────────────────────────────────────────────────────────
    gf_sills = [pw['sill'] for pw in all_pw if not pw['is_bsmt']]
    y_clip_gf = float(floor_h)
    if gf_sills:
        y_clip_gf = min(float(floor_h), max(gf_sills) + 0.55)
    y_clip_gf = max(y_clip_gf, zoom_yhi + 0.25, 0.4)
    y_clip_gf = min(y_clip_gf, float(floor_h))

    cfg = {
        'label':         label,
        'subtitle':      subtitle,
        'floor_h':       floor_h,
        'bsmt_d':        basement_depth,
        'sump':          has_sump,
        'pump':          has_pump,
        'gf_paths':      [],
        'bsmt_paths':    [],
        'membrane':      mem_cfg,
        'bypass_height': y_slab,
        'y_clip_gf':     y_clip_gf,
    }

    # ── figure: single schematic axes ─────────────────────────────────────────
    total_h = float(floor_h) + bsmt_d
    sch_h   = max(4.5, 1.5 * total_h)
    fig, ax_sch = plt.subplots(figsize=(8.5, sch_h), facecolor='white')
    fig.patch.set_facecolor('white')

    draw_schematic(ax_sch, cfg)

    # ── colormap shared across all pathways ───────────────────────────────────
    cds  = [pw['cd'] for pw in all_pw] if all_pw else [0.6]
    c_lo, c_hi = min(cds), max(cds)
    if c_lo == c_hi:
        c_lo, c_hi = max(0.0, c_lo - 0.15), c_hi + 0.15
    _cmap_pw = matplotlib.colormaps.get_cmap('plasma')
    _norm_pw = plt.Normalize(c_lo, c_hi)

    areas = [pw['area'] for pw in all_pw] if all_pw else [0.001]
    a_lo, a_hi = min(areas), max(areas)

    def _ms(a):
        if a_hi == a_lo:
            return 60
        return 25 + 110 * (a - a_lo) / (a_hi - a_lo)

    # ── inset zoom axes: position inside building above clip line ─────────────
    xlo_ax, xhi_ax = ax_sch.get_xlim()
    ylo_ax, yhi_ax = ax_sch.get_ylim()
    xr = xhi_ax - xlo_ax
    yr = yhi_ax - ylo_ax

    # inset occupies the building interior space above the clip
    _pad = 0.04
    ins_xd0 = 0.05
    ins_xd1 = _SCH_W - 0.05
    ins_yd0 = y_clip_gf + _pad
    ins_yd1 = yhi_ax - _pad

    ins_x0 = (ins_xd0 - xlo_ax) / xr
    ins_y0 = (ins_yd0 - ylo_ax) / yr
    ins_w  = (ins_xd1 - ins_xd0) / xr
    ins_h  = (ins_yd1 - ins_yd0) / yr

    # ensure minimum inset size; fall back to right-side placement
    if ins_h < 0.12 or ins_w < 0.15:
        ins_x0, ins_y0, ins_w, ins_h = 0.54, 0.55, 0.40, 0.38

    axins = ax_sch.inset_axes([ins_x0, ins_y0, ins_w, ins_h])

    # zoom x: the wall strip (exterior to small interior depth)
    zoom_xlo = -_SCH_EXT_W - 0.02
    zoom_xhi =  0.18
    axins.set_xlim(zoom_xlo, zoom_xhi)
    axins.set_ylim(zoom_ylo, zoom_yhi)

    axins.set_facecolor('#f8f9fa')
    for sp in axins.spines.values():
        sp.set_edgecolor('#bbb')
        sp.set_linewidth(0.6)
    axins.tick_params(left=True, labelleft=True, bottom=False, labelbottom=False,
                      labelsize=5.5, length=2, width=0.5, color='#999')
    axins.set_ylabel('elevation (m)', fontsize=5.5, color='#666', labelpad=3)
    axins.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.2f}'))

    # wall line in inset
    axins.plot([0, 0], [zoom_ylo - 0.05, zoom_yhi + 0.05],
               color=_SCH_BLACK, lw=1.2, zorder=5, clip_on=False)
    # ground datum
    if zoom_ylo < 0 < zoom_yhi:
        axins.axhline(0.0, color='#888', lw=0.6, ls='-', alpha=0.6, zorder=3)
        axins.text(zoom_xhi - 0.01, 0.005, '±0 m', fontsize=4.5,
                   color='#999', ha='right', va='bottom')
    # bypass slab marker in inset (always at y_slab when basement present)
    if bsmt_d > 0 and zoom_ylo <= y_slab <= zoom_yhi:
        axins.plot([zoom_xlo, zoom_xhi], [y_slab, y_slab],
                   color=_SCH_BLACK, lw=0.8, ls=(0, (4, 3)), alpha=0.5, zorder=3)
        slab_lbl = f'GF slab  ({y_slab:+.2f} m)' if abs(y_slab) > 0.005 else 'GF slab  (±0 m)'
        axins.text(0.02, y_slab + 0.01, slab_lbl, fontsize=4.5,
                   color='#777', va='bottom')

    # ── draw pathways in inset ────────────────────────────────────────────────
    all_pw_sorted = sorted(all_pw, key=lambda x: x['sill'])

    for pw in all_pw_sorted:
        y   = pw['sill']
        col = _cmap_pw(_norm_pw(pw['cd']))
        is_frag = pw['style'] == 'prob'

        # coloured slot on external wall face
        slot_lw = 1.4 if is_frag else 0.4
        slot_ec = col  if is_frag else 'white'
        slot_ls = '--' if is_frag else 'solid'
        axins.add_patch(_mpatches.FancyBboxPatch(
            (-0.038, y - 0.022), 0.038, 0.044,
            boxstyle='round,pad=0.003',
            facecolor=col, edgecolor=slot_ec, lw=slot_lw,
            linestyle=slot_ls, zorder=8))

        # fragility uncertainty bar (option B)
        fr = pw.get('frag_range')
        if is_frag and fr:
            xb = -0.019
            axins.plot([xb, xb], [fr[0], fr[1]],
                       color=col, lw=1.8, solid_capstyle='round', alpha=0.75, zorder=9)
            for yb in fr:
                axins.plot([xb - 0.012, xb + 0.012], [yb, yb],
                           color=col, lw=1.0, alpha=0.75, zorder=9)

        # area circle on interior face
        axins.scatter([0.035], [y], s=_ms(pw['area']),
                      color=col, edgecolors='white', lw=0.5, zorder=9)

        # callout label (exterior side, clip_on=False)
        tag = '~' if is_frag else ('(B) ' if pw['is_bsmt'] else '')
        safe = pw['name'].replace('_', '-')
        lbl  = (f"{tag}$\\bf{{{safe}}}$\n"
                f"  sill={y:.3f} m   $A={pw['area']:.4f}$ m²   $C_d={pw['cd']:.2f}$")
        axins.text(-0.055, y, lbl, va='center', ha='right',
                   fontsize=5.5, color='#1e2433', linespacing=1.35,
                   bbox=dict(boxstyle='round,pad=0.25', fc='white',
                             ec=col, lw=0.9, alpha=0.95),
                   clip_on=False, zorder=10)

    # indicate_inset_zoom: connect inset to zoom region in main axes
    ax_sch.indicate_inset_zoom(axins, edgecolor='#999', alpha=0.6, lw=0.8)

    # footnote: total area
    if all_pw:
        ax_sch.text(
            _SCH_W / 2, ylo_ax + 0.05,
            f'n = {len(all_pw)}   $\\Sigma A = {sum(areas):.4f}$ m²',
            ha='center', va='bottom', fontsize=6.5, color='#555',
            style='italic', clip_on=False)

    # Cd colorbar
    _sm = plt.cm.ScalarMappable(cmap=_cmap_pw, norm=_norm_pw)
    _sm.set_array([])
    _cb = fig.colorbar(_sm, ax=ax_sch, fraction=0.018, pad=0.01,
                       aspect=25, location='right', shrink=0.55)
    _cb.set_label('Discharge coefficient  $C_d$', fontsize=7)
    _cb.ax.tick_params(labelsize=6.5)

    # ── dimension annotations ─────────────────────────────────────────────────
    x_dim = _SCH_W + _SCH_EXT_W + 0.15

    def _dim_line(y_bot, y_top_d, label_str, side_label=''):
        ax_sch.plot([x_dim - 0.04, x_dim + 0.04], [y_bot, y_bot],
                    color='#888', lw=0.7, clip_on=False, zorder=10)
        ax_sch.plot([x_dim - 0.04, x_dim + 0.04], [y_top_d, y_top_d],
                    color='#888', lw=0.7, clip_on=False, zorder=10)
        ax_sch.annotate('', xy=(x_dim, y_top_d), xytext=(x_dim, y_bot),
                        arrowprops=dict(arrowstyle='<->', color='#666',
                                       lw=0.9, mutation_scale=8),
                        clip_on=False, zorder=10)
        mid = (y_bot + y_top_d) / 2
        ax_sch.text(x_dim + 0.10, mid, label_str,
                    ha='left', va='center', fontsize=6.5, color='#444',
                    clip_on=False, zorder=10)
        if side_label:
            ax_sch.text(x_dim + 0.10, mid - 0.22, side_label,
                        ha='left', va='center', fontsize=5.2, color='#888',
                        clip_on=False, zorder=10)

    _dim_line(0.0, floor_h, f'{floor_h:.1f} m', 'floor ht.')
    if basement_depth:
        _dim_line(-basement_depth, 0.0, f'{basement_depth:.1f} m', 'bsmt. depth')

    xlo2, xhi2 = ax_sch.get_xlim()
    ax_sch.set_xlim(xlo2, max(xhi2, x_dim + 0.65))

    fig.savefig(outpath, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return outpath
