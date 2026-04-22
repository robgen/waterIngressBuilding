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


# ── ingress preview (area bar chart) ──────────────────────────────────────────

def save_ingress_preview(ingress_list, outpath):
    if not ingress_list:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, 'No ingress pathways', transform=ax.transAxes,
                ha='center', va='center', fontsize=11, color='#888')
        fig.tight_layout(); fig.savefig(outpath); plt.close(fig)
        return

    items = sorted(ingress_list, key=lambda i: i.area, reverse=True)
    names = [getattr(i, 'name', None) or f'sill {i.height:.2f} m' for i in items]
    areas = [i.area for i in items]
    coeffs = [i.coeff for i in items]

    import matplotlib.cm as cm
    c_lo = min(coeffs); c_hi = max(coeffs)
    if c_lo == c_hi:
        c_lo, c_hi = max(0.0, c_lo - 0.15), c_hi + 0.15
    cmap = matplotlib.colormaps.get_cmap('plasma')
    norm = plt.Normalize(c_lo, c_hi)
    colours = [cmap(norm(c)) for c in coeffs]

    fig_h = max(3.0, 0.45 * len(items) + 1.2)
    fig, ax = plt.subplots(figsize=(8, fig_h))

    bars = ax.barh(range(len(items)), areas, color=colours,
                   edgecolor='white', linewidth=0.6, zorder=3)
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels(names, fontsize=8.5)
    ax.set_xlabel('Opening area  (m²)')
    ax.set_title('Ingress pathway areas')
    ax.invert_yaxis()
    ax.grid(True, axis='x', alpha=0.4)
    ax.grid(False, axis='y')

    for bar, area, item in zip(bars, areas, items):
        ax.text(area + max(areas) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f'{area:.4f} m²   sill {item.height:.2f} m',
                va='center', fontsize=7.5, color='#333')

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, shrink=0.7, pad=0.02)
    cb.set_label('Discharge coefficient  $C_d$', fontsize=8)
    cb.ax.tick_params(labelsize=7.5)

    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


# ── ingress locations (building facade schematic) ─────────────────────────────

def save_ingress_locations(ingress_list, outpath, building_width=1.0):
    if not ingress_list:
        raise ValueError('No ingress points provided')

    import matplotlib.cm as cm

    items_sorted = sorted(ingress_list, key=lambda ig: ig.height)
    MAX_H = max((ing.height for ing in ingress_list), default=1.0)

    # spread labels vertically so they never overlap
    MIN_SEP = 0.30
    label_ys, last_y = [], -999.0
    for ing in items_sorted:
        y_lbl = max(ing.height, last_y + MIN_SEP)
        label_ys.append(y_lbl)
        last_y = y_lbl

    max_label_y   = max(label_ys) if label_ys else 0.0
    building_h    = max(3.0, MAX_H * 1.35 + 0.3, max_label_y + 0.4)
    y_top         = building_h * 1.22
    y_bot         = -0.3
    fig_h         = max(5.5, min(14.0, (y_top - y_bot) * 1.6))
    fig, ax       = plt.subplots(figsize=(9, fig_h))

    bx  = 0.55
    bw  = 1.0
    igx = bx + bw          # where ingress markers sit (wall surface)
    lx0 = igx + 0.38       # left edge of label column
    xR  = lx0 + 3.6        # right edge of the axes

    ax.set_xlim(bx - 0.65, xR)
    ax.set_ylim(y_bot, y_top)
    ax.set_aspect('auto')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    # ── ground ────────────────────────────────────────────────────────────────
    ax.axhspan(y_bot, 0.0, color='#d5b97b', alpha=0.28, zorder=0)
    ax.hlines(0.0, bx - 0.65, xR, colors='#9a7b3e', lw=1.8, zorder=1)
    ax.fill_between([bx - 0.65, xR], y_bot, 0.0,
                    color='#c4a05a', alpha=0.10, zorder=0)

    # ── building walls ────────────────────────────────────────────────────────
    wall = patches.FancyBboxPatch(
        (bx, 0), bw, building_h,
        boxstyle='square,pad=0', linewidth=1.5,
        edgecolor='#6a7280', facecolor='#f3ede2', zorder=2)
    ax.add_patch(wall)

    # subtle brick texture: horizontal mortar lines every 0.25 m
    for hy in np.arange(0.25, building_h, 0.25):
        ax.hlines(hy, bx, bx + bw, colors='#d8cfc3', lw=0.35, zorder=3)

    # ── roof ─────────────────────────────────────────────────────────────────
    rh = building_h * 0.17
    roof = patches.Polygon(
        [(bx - 0.08, building_h),
         (bx + bw / 2, building_h + rh),
         (bx + bw + 0.08, building_h)],
        closed=True, facecolor='#7b3600', edgecolor='#5c2900', lw=1.3, zorder=4)
    ax.add_patch(roof)
    # ridge cap
    ax.plot([bx + bw / 2 - 0.02, bx + bw / 2 + 0.02],
            [building_h + rh, building_h + rh],
            color='#4a1e00', lw=2.0, zorder=5)

    # ── manual y-axis (left of building) ─────────────────────────────────────
    tick_step = 0.5 if building_h <= 4.0 else 1.0
    tick_val  = 0.0
    while tick_val <= building_h + 0.01:
        ax.hlines(tick_val, bx - 0.22, bx - 0.08,
                  colors='#8a8f9b', lw=0.8, zorder=5)
        ax.text(bx - 0.26, tick_val, f'{tick_val:.1f}',
                ha='right', va='center', fontsize=7.5, color='#555')
        tick_val = round(tick_val + tick_step, 6)
    ax.text(bx - 0.48, building_h / 2,
            'Height above\nground floor  (m)',
            ha='center', va='center', fontsize=8, color='#555', rotation=90)

    # ── colour + size maps ────────────────────────────────────────────────────
    coeffs = [ing.coeff for ing in ingress_list]
    c_lo, c_hi = min(coeffs), max(coeffs)
    if c_lo == c_hi:
        c_lo, c_hi = max(0.0, c_lo - 0.15), c_hi + 0.15
    cmap = matplotlib.colormaps.get_cmap('plasma')
    norm = plt.Normalize(c_lo, c_hi)

    areas = [ing.area for ing in ingress_list]
    a_lo, a_hi = min(areas), max(areas)

    def _ms(a):
        if a_hi == a_lo:
            return 90
        return 30 + 160 * (a - a_lo) / (a_hi - a_lo)

    # ── draw pathways ─────────────────────────────────────────────────────────
    for ing, y_lbl in zip(items_sorted, label_ys):
        y     = ing.height
        col   = cmap(norm(ing.coeff))

        # wall slot
        slot = patches.FancyBboxPatch(
            (igx - 0.055, y - 0.022), 0.055, 0.045,
            boxstyle='round,pad=0.005',
            facecolor=col, edgecolor='white', lw=0.5, zorder=6)
        ax.add_patch(slot)

        # circle at slot exit
        ax.scatter([igx + 0.012], [y], s=_ms(ing.area),
                   color=col, edgecolors='white', lw=0.8, zorder=7,
                   clip_on=False)

        # connector
        con_style = 'arc3,rad=0.15' if abs(y_lbl - y) > 0.05 else 'arc3,rad=0'
        ax.annotate('',
                    xy=(lx0 - 0.04, y_lbl),
                    xytext=(igx + 0.06, y),
                    arrowprops=dict(arrowstyle='-', color='#cccccc',
                                   connectionstyle=con_style,
                                   linestyle='dashed', lw=0.9))

        # label
        safe = ing.name.replace('_', r'\_') if hasattr(ing, 'name') and ing.name else '?'
        lbl  = (f'$\\bf{{{safe}}}$'
                f'\n  $A = {ing.area:.5f}$ m²   '
                f'$C_d = {ing.coeff:.2f}$   '
                f'sill = {ing.height:.3f} m')
        ax.text(lx0, y_lbl, lbl, va='center', ha='left', fontsize=8,
                color='#1e2433', linespacing=1.55,
                bbox=dict(boxstyle='round,pad=0.38', fc='white',
                          ec=col, lw=1.1, alpha=0.96))

    # ── total area annotation ──────────────────────────────────────────────────
    total_A = sum(areas)
    ax.text(bx + bw / 2, -0.18,
            f'n = {len(ingress_list)} pathways   '
            f'$\\Sigma A = {total_A:.5f}$ m²',
            ha='center', va='top', fontsize=8, color='#444',
            style='italic')

    # ── colourbar ─────────────────────────────────────────────────────────────
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.016, pad=0.01, aspect=32,
                        location='right')
    cbar.set_label('Discharge coefficient  $C_d$', fontsize=8)
    cbar.ax.tick_params(labelsize=7.5)

    # ── area size legend ──────────────────────────────────────────────────────
    if a_hi > a_lo:
        sz_vals = [a_lo, (a_lo + a_hi) / 2, a_hi]
        handles = [plt.scatter([], [], s=_ms(a), color='#a0a0a0',
                               edgecolors='white', lw=0.7,
                               label=f'{a:.5f} m²')
                   for a in sz_vals]
        ax.legend(handles=handles, title='Opening area',
                  title_fontsize=7.5, fontsize=7.5,
                  loc='upper left', framealpha=0.93,
                  edgecolor='#ccc', handletextpad=0.5)

    ax.set_title('Ingress pathways — building facade',
                 fontsize=12, fontweight='bold', pad=10,
                 color='#1e2433')

    fig.savefig(outpath, dpi=150, bbox_inches='tight')
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
                         'figure.facecolor': '#f0f4f8'}):
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
            ani.save(outpath, writer=writer)
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

def save_batch_scatter(h_peak_ext, h_peak_int, outpath):
    h_e = list(h_peak_ext)
    h_i = list(h_peak_int)
    n   = len(h_e)

    fig, ax = plt.subplots(figsize=(6, 5.5))

    lim = max(max(h_e, default=0), max(h_i, default=0)) * 1.08
    lim = max(lim, 0.1)

    # hexbin for density when many points, scatter otherwise
    if n > 60:
        hb = ax.hexbin(h_e, h_i, gridsize=20, cmap='Blues',
                       mincnt=1, linewidths=0.3, zorder=3)
        cb = fig.colorbar(hb, ax=ax, pad=0.02)
        cb.set_label('Count', fontsize=8)
        cb.ax.tick_params(labelsize=7.5)
    else:
        ax.scatter(h_e, h_i, s=22, alpha=0.75,
                   color=_C['external'], edgecolors='white', lw=0.4, zorder=3)

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


# ── loss scatter ───────────────────────────────────────────────────────────────

def save_loss_scatter(h_peak_ext, aggregate_losses, outpath):
    h_e  = list(h_peak_ext)
    loss = list(aggregate_losses)
    n    = len(h_e)

    fig, ax = plt.subplots(figsize=(7, 5))

    # colour dots by depth using a gradient
    sc = ax.scatter(h_e, loss, s=28, alpha=0.80, zorder=4,
                    c=h_e, cmap='YlOrRd', edgecolors='white', lw=0.4)
    cb = fig.colorbar(sc, ax=ax, pad=0.02)
    cb.set_label('Peak exterior depth  (m)', fontsize=8)
    cb.ax.tick_params(labelsize=7.5)

    avg = sum(loss) / n if n > 0 else 0.0
    ax.axhline(avg, color='#c0392b', lw=1.5, ls='--', zorder=2,
               label=f'Mean  GBP {avg:,.0f}')

    # non-parametric smoothed trend (running median in depth bins)
    if n > 10:
        try:
            order = np.argsort(h_e)
            h_s   = np.array(h_e)[order]
            l_s   = np.array(loss)[order]
            bin_w = max(3, n // 12)
            xs, ys = [], []
            for j in range(0, n, max(1, bin_w // 2)):
                sl = slice(j, min(j + bin_w, n))
                xs.append(float(np.mean(h_s[sl])))
                ys.append(float(np.median(l_s[sl])))
            ax.plot(xs, ys, color='#c0392b', lw=2.0, alpha=0.70,
                    label='Running median', zorder=3)
        except Exception:
            pass

    ax.set_xlabel('Peak exterior depth  $h_{out}^{max}$  (m)')
    ax.set_ylabel('Aggregate loss  (GBP)')
    ax.set_title(f'Peak exterior depth vs aggregate loss  —  {n} cases', pad=10)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.legend(fontsize=8.5, loc='upper left')

    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
