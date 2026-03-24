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
from matplotlib import patches
from matplotlib.ticker import FuncFormatter


def save_external_preview(times, levels, outpath, time_unit=None):
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(times, levels, marker='o')
    ax.set_title('External level (preview)')
    xlabel = 'Time'
    if time_unit:
        xlabel = f'Time ({time_unit})'
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Level (m)')
    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


def save_velocity_preview(times, velocities, outpath, time_unit=None, orig_point_times=None, orig_point_vals=None):
    """Save a small preview plot of the external velocity hydrograph.

    If times is empty this function will raise ValueError.
    """
    if not times:
        raise ValueError('No velocity times provided')
    fig, ax = plt.subplots(figsize=(6, 3))
    # plot the (possibly sampled) series as a line
    ax.plot(times, velocities, marker='o', color='tab:green', label='Velocity (sampled/padded)')
    # if original sparse points provided, overplot them as distinct markers
    if orig_point_times is not None and orig_point_vals is not None:
        ax.scatter(orig_point_times, orig_point_vals, color='black', marker='x', label='Original samples')
    ax.set_title('External velocity (preview)')
    xlabel = 'Time'
    if time_unit:
        xlabel = f'Time ({time_unit})'
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Velocity (m/s)')
    fig.tight_layout()
    ax.legend()
    fig.savefig(outpath)
    plt.close(fig)


def save_ingress_preview(ingress_list, outpath):
    names = [i.name if getattr(i, 'name', None) else str(i.height) for i in ingress_list]
    areas = [i.area for i in ingress_list]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(names, areas)
    ax.set_title('Ingress areas (preview)')
    ax.set_xlabel('Ingress')
    ax.set_ylabel('Area (m^2)')
    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


def save_ingress_locations(ingress_list, outpath, building_width=1.0):
    """Save a schematic of ingress pathways on a building facade.

    Markers are sized proportionally to area and coloured by discharge
    coefficient. Labels are spread vertically to avoid overlap and connected
    to their markers by dashed lines.
    """
    if not ingress_list:
        raise ValueError('No ingress points provided')

    import matplotlib.cm as cm

    max_h = max((ing.height for ing in ingress_list), default=1.0)

    # ── compute label spread first so building height can accommodate them ───
    items_sorted = sorted(ingress_list, key=lambda ig: ig.height)
    MIN_SEP = 0.28          # fixed minimum vertical gap between labels (m)
    label_ys, last_y = [], -999.0
    for ing in items_sorted:
        y_lbl = max(ing.height, last_y + MIN_SEP)
        label_ys.append(y_lbl)
        last_y = y_lbl

    max_label_y = max(label_ys) if label_ys else 0.0
    building_height = max(3.0, max_h * 1.35 + 0.3, max_label_y + 0.4)

    # figure height derived from data range, not entry count
    y_top = building_height * 1.22   # room for roof + legend
    y_bot = -0.25
    fig_h = max(5.0, min(14.0, (y_top - y_bot) * 1.55))
    fig, ax = plt.subplots(figsize=(8, fig_h))

    # ── coordinate system ────────────────────────────────────────────────────
    bx, bw = 0.5, 1.0
    ingress_x = bx + bw
    label_x0 = ingress_x + 0.35
    x_right = label_x0 + 3.2

    ax.set_xlim(bx - 0.55, x_right)
    ax.set_ylim(y_bot, y_top)
    ax.set_aspect('auto')
    ax.axis('off')

    # ── ground ───────────────────────────────────────────────────────────────
    ax.axhspan(-0.25, 0.0, xmin=0, xmax=1, color='#d4b483', alpha=0.35, zorder=0)
    ax.hlines(0.0, bx - 0.55, x_right, colors='#8B6914', linewidth=1.5, zorder=1)

    # ── building walls ───────────────────────────────────────────────────────
    wall = patches.Rectangle((bx, 0), bw, building_height,
                               linewidth=1.5, edgecolor='#555', facecolor='#f5f0e8', zorder=2)
    ax.add_patch(wall)

    # ── roof ─────────────────────────────────────────────────────────────────
    roof_h = building_height * 0.16
    roof = patches.Polygon([
        (bx - 0.06, building_height),
        (bx + bw / 2, building_height + roof_h),
        (bx + bw + 0.06, building_height),
    ], closed=True, facecolor='#7B3F00', edgecolor='#5C2D00', linewidth=1.2, zorder=3)
    ax.add_patch(roof)

    # ── manual y-axis (height ticks on the left of the building) ─────────────
    tick_step = 0.5 if building_height <= 4.0 else 1.0
    tick_val = 0.0
    while tick_val <= building_height + 0.01:
        ax.hlines(tick_val, bx - 0.18, bx - 0.07, colors='#666', linewidth=0.8, zorder=5)
        ax.text(bx - 0.22, tick_val, f'{tick_val:.1f}', ha='right', va='center',
                fontsize=7.5, color='#444')
        tick_val = round(tick_val + tick_step, 6)
    ax.text(bx - 0.42, building_height / 2, 'Height above\nground floor (m)',
            ha='center', va='center', fontsize=8, color='#444', rotation=90)

    # ── colour map (discharge coefficient) ───────────────────────────────────
    coeffs = [ing.coeff for ing in ingress_list]
    c_lo, c_hi = min(coeffs), max(coeffs)
    if c_lo == c_hi:
        c_lo, c_hi = max(0.0, c_lo - 0.15), c_hi + 0.15
    cmap = cm.get_cmap('plasma')
    norm = plt.Normalize(c_lo, c_hi)

    # ── marker size (area) ────────────────────────────────────────────────────
    areas = [ing.area for ing in ingress_list]
    a_lo, a_hi = min(areas), max(areas)

    def _area_to_ms(a):
        if a_hi == a_lo:
            return 90
        return 35 + 165 * (a - a_lo) / (a_hi - a_lo)

    # items_sorted and label_ys already computed above

    # ── draw markers + connectors + labels ────────────────────────────────────
    for ing, y_lbl in zip(items_sorted, label_ys):
        y = ing.height
        color = cmap(norm(ing.coeff))

        # small slot on the building wall
        slot = patches.Rectangle((ingress_x - 0.05, y - 0.025), 0.05, 0.05,
                                   facecolor=color, edgecolor='#333', linewidth=0.7, zorder=5)
        ax.add_patch(slot)

        # circle marker at the slot exit
        ax.scatter([ingress_x + 0.01], [y], s=_area_to_ms(ing.area),
                    color=color, edgecolors='#222', linewidth=0.7, zorder=6, clip_on=False)

        # dashed connector from marker to label
        ax.annotate('', xy=(label_x0, y_lbl),
                    xytext=(ingress_x + 0.09, y),
                    arrowprops=dict(arrowstyle='-', color='#bbb',
                                    connectionstyle='arc3,rad=0.0',
                                    linestyle='dashed', linewidth=0.8))

        # label box
        safe_name = ing.name.replace('_', r'\_')
        label = (f"$\\bf{{{safe_name}}}$"
                 f"\n  A = {ing.area:.4f} m²    C = {ing.coeff:.2f}")
        ax.text(label_x0, y_lbl, label, va='center', ha='left', fontsize=8.5,
                color='#222', linespacing=1.5,
                bbox=dict(boxstyle='round,pad=0.35', fc='white',
                          ec=color, lw=1.2, alpha=0.95))

    # ── colourbar ─────────────────────────────────────────────────────────────
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.018, pad=0.01, aspect=35,
                        location='right')
    cbar.set_label('Discharge coefficient  C', fontsize=8)
    cbar.ax.tick_params(labelsize=7.5)

    # ── area legend (inside axes, top-left corner) ───────────────────────────
    if a_hi > a_lo:
        legend_sizes = [a_lo, (a_lo + a_hi) / 2, a_hi]
        legend_handles = [
            plt.scatter([], [], s=_area_to_ms(a), color='#999',
                        edgecolors='#333', linewidth=0.7, label=f'{a:.4f} m²')
            for a in legend_sizes
        ]
        ax.legend(handles=legend_handles, title='Opening area', title_fontsize=7.5,
                  fontsize=7.5, loc='upper left',
                  framealpha=0.9, edgecolor='#ccc', handletextpad=0.6)

    ax.set_title('Ingress pathways — building facade', fontsize=11,
                  fontweight='bold', pad=8)

    fig.savefig(outpath, dpi=130, bbox_inches='tight')
    plt.close(fig)


def save_simulation_result(sim_times, sim_levels, external_levels, outpath, time_unit=None, basement_levels=None, velocity_series=None):
    """Save a combined plot of external/indoor (and optional basement) levels.

    If `velocity_series` is provided (same length as `sim_times`) it will be
    plotted on a secondary y-axis on the right in m/s.
    """
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(sim_times, external_levels, label='External Level (h_out)', color='tab:blue')
    ax.plot(sim_times, sim_levels, label='Indoor Level (h_in)', color='tab:orange')
    if basement_levels is not None:
        ax.plot(sim_times, basement_levels, label='Basement Level (h_b)', linestyle='--', color='#2ca02c')
    xlabel = 'Time'
    if time_unit:
        xlabel = f'Time ({time_unit})'
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Water Level (m)')
    ax.set_title('Flood Ingress Simulation')

    # add secondary axis for velocity if provided
    if velocity_series is not None:
        ax2 = ax.twinx()
        ax2.plot(sim_times, velocity_series, label='Velocity (m/s)', color='tab:green', linestyle=':')
        ax2.set_ylabel('Velocity (m/s)')
        # combine legends from both axes
        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines + lines2, labels + labels2, loc='upper left')
    else:
        ax.legend()

    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


def save_forces_result(sim_times, forces_rows, outpath, time_unit=None):
    """Plot forces and overturning moment over time.

    Args:
        sim_times: list of times (in display units)
        forces_rows: iterable of rows as produced by main forces_out: tuples
            (t, F_hydro, F_drag, F_total, M_overturn, H_net, H_wet, v, lever_h, lever_d)
        outpath: output PNG path
        time_unit: optional label for x-axis
    """
    if not sim_times:
        raise ValueError('No simulation times provided')
    # unpack columns
    times = list(sim_times)
    F_h = [r[1] for r in forces_rows]
    F_d = [r[2] for r in forces_rows]
    F_t = [r[3] for r in forces_rows]
    M_o = [r[4] for r in forces_rows]

    fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(8, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    ax1.plot(times, F_h, label='Hydrostatic (N)', color='tab:blue')
    ax1.plot(times, F_d, label='Drag (N)', color='tab:green')
    ax1.plot(times, F_t, label='Total (N)', color='tab:red', linewidth=1.5)
    ax1.set_ylabel('Force (N)')
    ax1.legend(loc='upper left')
    # annotate peaks
    try:
        peak_idx = max(range(len(F_t)), key=lambda i: F_t[i])
        ax1.annotate(f'Peak {F_t[peak_idx]:.1f} N', xy=(times[peak_idx], F_t[peak_idx]), xytext=(10, 10), textcoords='offset points', fontsize=8, arrowprops=dict(arrowstyle='->'))
    except Exception:
        pass

    ax2.plot(times, M_o, label='Overturning moment (Nm)', color='tab:purple')
    ax2.set_ylabel('Moment (Nm)')
    ax2.set_xlabel('Time' if not time_unit else f'Time ({time_unit})')
    ax2.legend(loc='upper left')

    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


def generate_animation(sim_times, sim_levels, external_levels, ingress_list, outpath, fps=10, max_frames=200, time_unit=None, basement_levels=None, basement_abs_levels=None, velocity_series=None):
    # Prepare frames (downsample if too many)
    n_frames = len(sim_times)
    if n_frames <= 0:
        raise ValueError('No simulation times for animation')
    step = max(1, n_frames // max_frames)
    frame_indices = list(range(0, n_frames, step))

    # Geometry
    building_width = 1.0
    bx = 0.5
    max_ingress_h = max((ing.height for ing in ingress_list), default=0.0)
    max_level = max(max(external_levels or [0]), max(sim_levels or [0]), max_ingress_h)
    # Always show at least 3 m of building so door/window have room
    building_height = max(3.0, max_level * 1.4 + 0.5)
    unit_label = 's' if (time_unit is None or time_unit == 'seconds') else ('min' if time_unit.startswith('min') else ('h' if time_unit.startswith('hour') else time_unit))

    # Pre-compute ground<->basement flow series
    Qgb_series = [0.0] * len(sim_times)
    if ingress_list and basement_levels is not None:
        abs_basement = basement_abs_levels if basement_abs_levels is not None else basement_levels
        if abs_basement is not None:
            for i in range(len(sim_times)):
                h_in_i = sim_levels[i]
                H_b_i = abs_basement[i]
                total = 0.0
                for ing in ingress_list:
                    src = getattr(ing, 'source', 'outside')
                    tgt = getattr(ing, 'target', 'ground')
                    if src == 'ground' and tgt == 'basement':
                        total += ing.compute_flow(h_in_i, H_b_i)
                    elif src == 'basement' and tgt == 'ground':
                        total -= ing.compute_flow(H_b_i, h_in_i)
                Qgb_series[i] = total

    # ------------------------------------------------------------------ layout
    # Left: building cross-section.  Right: live time-series chart.
    # If a basement exists, the building panel is split top/bottom.
    if basement_levels is None:
        fig = plt.figure(figsize=(12, 5))
        gs = fig.add_gridspec(1, 2, width_ratios=[3, 2], wspace=0.4)
        ax_top = fig.add_subplot(gs[0, 0])
        ax_chart = fig.add_subplot(gs[0, 1])
        ax_b = None
    else:
        fig = plt.figure(figsize=(12, 6))
        gs = fig.add_gridspec(2, 2, width_ratios=[3, 2], height_ratios=[3, 1],
                              wspace=0.4, hspace=0.2)
        ax_top = fig.add_subplot(gs[0, 0])
        ax_b = fig.add_subplot(gs[1, 0])
        ax_chart = fig.add_subplot(gs[:, 1])

    # -------------------------------------------------------- building panel
    ax_top.set_xlim(-0.5, 4.0)
    ax_top.set_ylim(0, building_height)
    ax_top.set_xlabel('Horizontal position', fontsize=8)
    ax_top.set_ylabel('Height (m)', fontsize=8)
    ax_top.set_title('Flood Ingress Simulation', fontsize=10, fontweight='bold')
    ax_top.grid(True, alpha=0.15, linestyle=':')

    # Ground line + fill
    ax_top.hlines(0, -0.5, 4.0, colors='saddlebrown', linewidth=2)
    ax_top.axhspan(-building_height * 0.05, 0, color='#c8a064', alpha=0.25)

    # Building walls
    building_rect = patches.Rectangle((bx, 0), building_width, building_height,
                                       linewidth=2, edgecolor='#444', facecolor='#f5f0e8')
    ax_top.add_patch(building_rect)

    # Roof (triangle)
    roof_h = building_height * 0.18
    roof_pts = [(bx - 0.05, building_height),
                (bx + building_width / 2, building_height + roof_h),
                (bx + building_width + 0.05, building_height)]
    roof = patches.Polygon(roof_pts, closed=True, facecolor='#8B4513',
                            edgecolor='#5C2D00', linewidth=1.5, zorder=4)
    ax_top.add_patch(roof)

    # Ingress markers on the right face — spread labels to avoid overlap
    ingress_x = bx + building_width
    # sort by height ascending, then spread label positions upward
    items_sorted = sorted(ingress_list, key=lambda ing: ing.height)
    min_label_sep = max(0.20, building_height * 0.07)
    label_ys = []
    last_y = -999.0
    for ing in items_sorted:
        y_lbl = max(ing.height, last_y + min_label_sep)
        label_ys.append(y_lbl)
        last_y = y_lbl

    for ing, y_lbl in zip(items_sorted, label_ys):
        y = ing.height
        mark = patches.Rectangle((ingress_x - 0.04, y - 0.025), 0.04, 0.05,
                                   color='sienna', zorder=5)
        ax_top.add_patch(mark)
        # connector line from marker to (possibly offset) label
        if abs(y_lbl - y) > 0.01:
            ax_top.plot([ingress_x + 0.01, ingress_x + 0.08], [y, y_lbl],
                        color='#bbb', linewidth=0.7, zorder=4)
        label = f"{ing.name}"
        ax_top.text(ingress_x + 0.09, y_lbl, label, va='center', fontsize=7.5, color='#444')

    # Interior water patch
    interior_patch = patches.Rectangle((bx + 0.02, 0), building_width - 0.04, 0.0,
                                        facecolor='#5ba4cf', alpha=0.65, zorder=3)
    ax_top.add_patch(interior_patch)
    interior_lbl = ax_top.text(bx + building_width / 2, 0.0, '',
                                ha='center', va='bottom', fontsize=9,
                                color='#1a3d6b', fontweight='bold', zorder=6)

    # Exterior water body
    ex_x = 2.2
    ex_width = 1.5
    ext_rect = patches.Rectangle((ex_x, 0), ex_width, 0.0,
                                   facecolor='#2980b9', alpha=0.55, zorder=3)
    ax_top.add_patch(ext_rect)
    ax_top.text(ex_x + ex_width / 2, building_height * 0.97,
                'External\nwater', ha='center', va='top', fontsize=8, color='#1a3d6b')
    ext_lbl = ax_top.text(ex_x + ex_width / 2, 0.0, '',
                           ha='center', va='bottom', fontsize=9,
                           color='#1a3d6b', fontweight='bold', zorder=6)

    # Time & velocity text
    time_text = ax_top.text(bx + 0.02, building_height * 0.93, '',
                             fontsize=10, fontweight='bold', color='#222',
                             bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='#ccc', alpha=0.8))
    vel_text = ax_top.text(ex_x + ex_width / 2, building_height * 0.87, '',
                            ha='center', va='center', fontsize=8.5, color='#2d6a4f',
                            bbox=dict(boxstyle='round,pad=0.2', fc='#eafaf1', ec='#a9dfbf', alpha=0.85))

    ingress_arrows = []

    # Basement panel
    if basement_levels is not None:
        max_basement = max(basement_levels or [0.0])
        ax_b.set_xlim(-0.5, 4.0)
        ax_b.set_ylim(0, max(0.1, max_basement * 1.2 + 0.05))
        ax_b.set_ylabel('Basement (m)', fontsize=8)
        ax_b.grid(True, alpha=0.15, linestyle=':')
        base_patch = patches.Rectangle((bx + 0.02, 0), building_width - 0.04, 0.0,
                                        facecolor='#27ae60', alpha=0.60)
        ax_b.add_patch(base_patch)

    # --------------------------------------------------------- time-series chart
    ax_chart.plot(sim_times, external_levels, color='#2980b9',
                  label='External (h_out)', linewidth=1.8, alpha=0.85)
    ax_chart.plot(sim_times, sim_levels, color='#e67e22',
                  label='Indoor (h_in)', linewidth=1.8, alpha=0.85)
    if basement_levels is not None:
        ax_chart.plot(sim_times, basement_levels, color='#27ae60', linestyle='--',
                      label='Basement (h_b)', linewidth=1.4, alpha=0.80)
    ax_chart_v = None
    if velocity_series is not None:
        ax_chart_v = ax_chart.twinx()
        ax_chart_v.plot(sim_times, velocity_series, color='#8e44ad',
                        linestyle=':', linewidth=1.4, label='v (m/s)', alpha=0.75)
        ax_chart_v.set_ylabel('Velocity (m/s)', fontsize=8)
        lines1, labs1 = ax_chart.get_legend_handles_labels()
        lines2, labs2 = ax_chart_v.get_legend_handles_labels()
        ax_chart.legend(lines1 + lines2, labs1 + labs2, fontsize=7, loc='upper left')
    else:
        ax_chart.legend(fontsize=7, loc='upper left')

    xlabel = f'Time ({unit_label})'
    ax_chart.set_xlabel(xlabel, fontsize=9)
    ax_chart.set_ylabel('Water Level (m)', fontsize=9)
    ax_chart.set_title('Water Levels', fontsize=10, fontweight='bold')
    ax_chart.grid(True, alpha=0.25, linestyle=':')

    # Animated cursor (vertical dashed red line)
    cursor_line = ax_chart.axvline(sim_times[0], color='red', linewidth=1.5,
                                    linestyle='--', alpha=0.7, zorder=5)

    # ----------------------------------------------------------- animation funcs
    def init():
        interior_patch.set_height(0.0)
        ext_rect.set_height(0.0)
        time_text.set_text('')
        interior_lbl.set_text('')
        ext_lbl.set_text('')
        vel_text.set_text('')
        cursor_line.set_xdata([sim_times[0]])
        if basement_levels is not None:
            base_patch.set_height(0.0)
        return []

    def update(frame_i):
        for a in ingress_arrows:
            try:
                a.remove()
            except Exception:
                pass
        ingress_arrows.clear()

        i = frame_indices[frame_i]
        h_in = sim_levels[i]
        h_out = external_levels[i]
        t_now = sim_times[i]

        # Water patches
        interior_patch.set_height(h_in)
        ext_rect.set_height(h_out)

        # Level labels on water surfaces
        if h_in > 0.02 * building_height:
            interior_lbl.set_position((bx + building_width / 2, h_in + 0.01))
            interior_lbl.set_text(f'{h_in:.2f} m')
        else:
            interior_lbl.set_text('')

        if h_out > 0.02 * building_height:
            ext_lbl.set_position((ex_x + ex_width / 2, h_out + 0.01))
            ext_lbl.set_text(f'{h_out:.2f} m')
        else:
            ext_lbl.set_text('')

        # Velocity text
        if velocity_series is not None:
            try:
                v_now = velocity_series[i]
                vel_text.set_text(f'v = {v_now:.2f} m/s')
            except Exception:
                vel_text.set_text('')

        # Basement
        if basement_levels is not None:
            base_patch.set_height(basement_levels[i])

        # Time label
        time_text.set_text(f'T = {t_now:.1f} {unit_label}')

        # Move chart cursor
        cursor_line.set_xdata([t_now, t_now])

        # Flow arrows (outside -> inside on main facade)
        max_area = max((ing.area for ing in ingress_list), default=1.0)
        for ing in ingress_list:
            if not (ing.target == 'ground' or ing.source == 'ground' or
                    (ing.source == 'outside' and ing.target == 'ground')):
                continue
            Q = ing.compute_flow(h_out, h_in)
            y = ing.height
            if Q > 0:
                xa, xb = ex_x + 0.05, ingress_x - 0.04
                color = 'dodgerblue'
            elif Q < 0:
                xa, xb = ingress_x - 0.04, ex_x + 0.05
                color = 'crimson'
            else:
                xa = xb = ingress_x - 0.04
                color = 'gray'
            mag = min(1.0, abs(Q) / max(1e-9, max_area))
            arr = ax_top.annotate('', xy=(xb, y), xytext=(xa, y),
                                   arrowprops=dict(arrowstyle='-|>', color=color,
                                                   linewidth=1 + 3 * mag,
                                                   shrinkA=0, shrinkB=0))
            ingress_arrows.append(arr)

        # Ground<->basement vertical flow arrows (if basement present)
        if basement_levels is not None and any(abs(q) > 0 for q in Qgb_series):
            Q_current = Qgb_series[i] if i < len(Qgb_series) else 0.0
            Q_scale = max(1e-6, max(abs(q) for q in Qgb_series))
            for ing in ingress_list:
                src = getattr(ing, 'source', 'outside')
                tgt = getattr(ing, 'target', 'ground')
                if not ((src == 'ground' and tgt == 'basement') or
                        (src == 'basement' and tgt == 'ground')):
                    continue
                y0 = ing.height
                x0 = ingress_x - 0.08
                Qgb = Q_current
                arrow_len = 0.25 + 0.75 * min(1.0, abs(Qgb) / Q_scale)
                linewidth = 1.0 + 4.0 * min(1.0, abs(Qgb) / Q_scale)
                color = 'gray'
                y1 = max(0.0, y0 - arrow_len)
                if ax_b is not None:
                    try:
                        top_y_b = ax_b.get_ylim()[1]
                        disp = ax_b.transData.transform((x0, top_y_b))
                        _, y_edge = ax_top.transData.inverted().transform(disp)
                        y1 = min(y0 - 0.02, y_edge + 0.02 * building_height)
                    except Exception:
                        pass
                if Qgb > 0:
                    color = 'dodgerblue'
                elif Qgb < 0:
                    color = 'crimson'
                mag = min(1.0, abs(Qgb) / Q_scale)
                arr_v = ax_top.annotate('', xy=(x0, y1), xytext=(x0, y0),
                                         arrowprops=dict(arrowstyle='-|>', color=color,
                                                         linewidth=linewidth,
                                                         shrinkA=0, shrinkB=0))
                ingress_arrows.append(arr_v)
                lbl = ax_top.text(x0 - 0.12, (y0 + y1) / 2.0,
                                   f'{Qgb * 1000.0:.2f} L/s',
                                   fontsize=7, color='black', va='center', ha='right',
                                   bbox=dict(boxstyle='round,pad=0.1', fc='white', ec='none'))
                ingress_arrows.append(lbl)

        return []

    ani = animation.FuncAnimation(fig, update, frames=len(frame_indices),
                                   init_func=init, blit=False)
    try:
        writer = animation.PillowWriter(fps=fps)
        ani.save(outpath, writer=writer)
    except Exception:
        writer = animation.FFMpegWriter(fps=fps)
        ani.save(outpath.replace('.gif', '.mp4'), writer=writer)
    finally:
        plt.close(fig)


def save_batch_scatter(h_peak_ext, h_peak_int, outpath):
    """Scatter plot of peak exterior vs peak interior water depth.

    Parameters
    ----------
    h_peak_ext : sequence of float — peak exterior depth per case (m)
    h_peak_int : sequence of float — peak interior depth per case (m)
    outpath    : output PNG file path
    """
    fig, ax = plt.subplots(figsize=(5, 5))

    ax.scatter(h_peak_ext, h_peak_int, s=18, alpha=0.7,
               color='steelblue', edgecolors='white', linewidths=0.4, zorder=3)

    # 1:1 reference line
    lim = max(max(h_peak_ext, default=0), max(h_peak_int, default=0)) * 1.05
    lim = max(lim, 0.1)
    ax.plot([0, lim], [0, lim], color='#888', lw=1, ls='--', zorder=2, label='1:1')

    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel('Peak exterior depth  $h_{ext}^{max}$ (m)')
    ax.set_ylabel('Peak interior depth  $h_{int}^{max}$ (m)')
    ax.set_title(f'Batch run — {len(h_peak_ext)} cases')
    ax.legend(fontsize=8)
    ax.set_aspect('equal')
    ax.grid(True, lw=0.4, color='#ddd', zorder=1)

    fig.tight_layout()
    fig.savefig(outpath, dpi=130)
    plt.close(fig)


def save_loss_scatter(h_peak_ext, aggregate_losses, outpath):
    """Scatter plot of peak exterior water depth against aggregate loss."""
    fig, ax = plt.subplots(figsize=(6, 4.5))

    ax.scatter(h_peak_ext, aggregate_losses, s=22, alpha=0.75,
               color='#1f77b4', edgecolors='white', linewidths=0.4, zorder=3)

    avg_loss = (sum(aggregate_losses) / len(aggregate_losses)) if aggregate_losses else 0.0
    ax.axhline(avg_loss, color='#c0392b', lw=1.3, ls='--', zorder=2,
               label=f'Average loss = GBP {avg_loss:,.0f}')

    ax.set_xlabel('Peak exterior depth  $h_{ext}^{max}$ (m)')
    ax.set_ylabel('Aggregate loss (GBP)')
    ax.set_title(f'Peak exterior water vs aggregate loss ({len(h_peak_ext)} cases)')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.grid(True, lw=0.4, color='#ddd', zorder=1)
    ax.legend(fontsize=8, loc='upper left')

    ax.text(
        0.98, 0.03,
        f'Average loss: GBP {avg_loss:,.0f}',
        transform=ax.transAxes,
        ha='right', va='bottom',
        fontsize=8.5,
        bbox=dict(boxstyle='round,pad=0.28', fc='white', ec='#c0392b', alpha=0.9),
    )

    fig.tight_layout()
    fig.savefig(outpath, dpi=130)
    plt.close(fig)
