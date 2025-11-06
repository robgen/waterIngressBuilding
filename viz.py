#!/usr/bin/env python3
"""Plotting and animation helpers for headless use (uses Agg backend).

This module sets the Agg backend on import so it is safe to import only
from CLI (not from GUI). Callers that need GUI-backed plotting should not
import this module.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import patches


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
    """Save a clear plot showing ingress points distributed on a building face.

    The plot shows a simple building block and, for each ingress, a marker at
    its height and an annotated label with name, area and coefficient. Labels
    are adjusted to avoid overlapping by stacking with minimal vertical spacing.
    """
    if not ingress_list:
        raise ValueError('No ingress points provided')

    # compute max height for display
    max_h = max((ing.height for ing in ingress_list), default=1.0)
    ylim_top = max_h * 1.2 + 0.5

    fig, ax = plt.subplots(figsize=(4, 6))
    bx = 0.5
    bw = building_width
    # building rectangle
    building_height = ylim_top
    building_rect = patches.Rectangle((bx, 0), bw, building_height, linewidth=1, edgecolor='black', facecolor='#eee')
    ax.add_patch(building_rect)

    ingress_x = bx + bw
    marker_x = ingress_x

    # draw ground
    ax.hlines(0, bx - 0.2, ingress_x + 1.0, colors='saddlebrown')

    # prepare labels sorted by height descending (top-down)
    items = sorted(ingress_list, key=lambda ig: ig.height, reverse=True)
    labels = []
    placed_ys = []
    min_sep = max(0.05, (building_height) * 0.02)

    for ing in items:
        y = ing.height
        # initial label y same as marker
        y_label = y
        # avoid overlap with previously placed labels
        for py in placed_ys:
            if abs(y_label - py) < min_sep:
                y_label = py - min_sep
        placed_ys.append(y_label)

        # draw marker
        ax.plot([marker_x], [y], marker='o', color='sienna')
        # label string on a single line to reduce overlap
        label = f"{ing.name} — A={ing.area:.3f} m^2, C={ing.coeff:.2f}"

        # annotate with an arrow pointing to marker
        ax.annotate(label, xy=(marker_x, y), xytext=(marker_x + 0.4, y_label),
                    arrowprops=dict(arrowstyle='-', color='gray'), va='center', fontsize=8,
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='gray', lw=0.5))

    ax.set_xlim(bx - 0.2, ingress_x + 1.0)
    ax.set_ylim(0, building_height)
    ax.set_xlabel('Building face')
    ax.set_ylabel('Height (m)')
    ax.set_title('Ingress points (name, area, coeff)')
    fig.tight_layout()
    fig.savefig(outpath)
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


def generate_animation(sim_times, sim_levels, external_levels, ingress_list, outpath, fps=10, max_frames=200, time_unit=None, basement_levels=None, basement_abs_levels=None, velocity_series=None):
    # Prepare frames (downsample if too many)
    n_frames = len(sim_times)
    if n_frames <= 0:
        raise ValueError('No simulation times for animation')
    step = max(1, n_frames // max_frames)
    frame_indices = list(range(0, n_frames, step))

    # Layout and geometry
    building_width = 1.0
    max_ingress_h = max((ing.height for ing in ingress_list), default=0.0)
    max_level = max(max(external_levels or [0]), max(sim_levels or [0]), max_ingress_h)
    building_height = max_level * 1.4 + 0.5

    fig_w = 9
    fig_h = 5
    if basement_levels is None:
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax_top = ax
        ax_b = None
        ax_q = None
        ax_top.set_xlim(-0.5, 4.0)
        ax_top.set_ylim(0, building_height)
        ax_top.set_xlabel('Horizontal position')
        ax_top.set_ylabel('Height (m)')
        ax_top.set_title('Flood Ingress Animation')
    else:
        # stacked panels: main building + basement + Qgb panel
        fig, (ax_top, ax_b, ax_q) = plt.subplots(nrows=3, ncols=1, figsize=(fig_w, fig_h), gridspec_kw={'height_ratios': [3, 1, 1]})
        ax_top.set_xlim(-0.5, 4.0)
        ax_top.set_ylim(0, building_height)
        ax_top.set_xlabel('Horizontal position')
        ax_top.set_ylabel('Height (m)')
        ax_top.set_title('Flood Ingress Animation')
        # basement axis setup
        max_basement = max(basement_levels or [0.0])
        ax_b.set_xlim(-0.5, 4.0)
        ax_b.set_ylim(0, max(0.1, max_basement * 1.2 + 0.05))
        ax_b.set_xlabel('')
        ax_b.set_ylabel('Basement (m)')
        # Qgb axis setup (bottom subpanel)
        ax_q.set_xlim(sim_times[0], sim_times[-1])
        # set a reasonable ylim placeholder; will be updated after Qgb_series computed
        ax_q.set_ylim(-0.01, 0.01)
        ax_q.set_xlabel('Time')
        ax_q.set_ylabel('Q (m^3/s)')

    # Pre-compute ground<->basement flow time series (total over connectors)
    Qgb_series = [0.0] * len(sim_times)
    if ingress_list:
        # determine absolute basement head values per time step
        abs_basement = None
        if basement_abs_levels is not None:
            abs_basement = basement_abs_levels
        elif basement_levels is not None:
            # best-effort: treat basement_levels as absolute if caller passed absolute
            abs_basement = basement_levels
        # accumulate flows for each time index
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
        else:
            # leave zeros if no basement absolute series available
            Qgb_series = [0.0] * len(sim_times)

    # Ground
    ax_top.hlines(0, -0.5, 4.0, colors='saddlebrown', linewidth=2)

    # Building (simple block)
    bx = 0.5
    building_rect = patches.Rectangle((bx, 0), building_width, building_height, linewidth=2, edgecolor='black', facecolor='#f7f7f7')
    ax_top.add_patch(building_rect)

    # Door and small details
    door = patches.Rectangle((bx + 0.35, 0.0), 0.3, 0.02, facecolor='saddlebrown')
    ax_top.add_patch(door)

    # Ingress markers and labels on the right face (drawn on the top panel)
    ingress_x = bx + building_width
    for idx, ing in enumerate(ingress_list):
        y = ing.height
        mark = patches.Rectangle((ingress_x - 0.04, y - 0.03), 0.04, 0.06, color='sienna')
        ax_top.add_patch(mark)
        # single-line label for animation
        label = f"{ing.name} (h={ing.height:.2f} m) — A={ing.area:.3f} m^2, C={ing.coeff:.2f}"
        ax_top.text(ingress_x + 0.06, y, label, va='center', fontsize=8)

    # Interior water (inside building)
    interior_patch = patches.Rectangle((bx, 0), building_width, 0.0, facecolor='#1f77b4', alpha=0.6)
    ax_top.add_patch(interior_patch)

    # Exterior water body on the right
    ex_x = 2.2
    ex_width = 1.5
    ext_rect = patches.Rectangle((ex_x, 0), ex_width, 0.0, facecolor='#0b63a6', alpha=0.5)
    ax_top.add_patch(ext_rect)
    ax_top.text(ex_x + ex_width / 2, building_height * 0.95, 'External water', ha='center', va='center', fontsize=9, color='#0b63a6')

    # Time label
    unit_label = 's' if (time_unit is None or time_unit == 'seconds') else ('min' if time_unit.startswith('min') else ('h' if time_unit.startswith('hour') else time_unit))
    time_text = ax_top.text(bx, building_height * 0.96, '', fontsize=10)
    # velocity display text near the external water label (will be updated each frame)
    vel_text = ax_top.text(ex_x + ex_width / 2.0, building_height * 0.90, '', ha='center', va='center', fontsize=9, color='black')

    # Container for dynamic ingress arrows
    ingress_arrows = []

    # basement visual (bottom panel) - a single rectangle that grows with basement level
    if basement_levels is not None:
        base_patch = patches.Rectangle((bx, 0), building_width, 0.0, facecolor='#2ca02c', alpha=0.6)
        ax_b.add_patch(base_patch)

    # bottom Q panel (only if basement present)
    ax_q_line = None
    ax_q_marker = None
    if ax_q is not None and any(abs(q) > 0 for q in Qgb_series):
        ax_q_line, = ax_q.plot(sim_times, Qgb_series, color='tab:purple')
        ax_q.axhline(0.0, color='gray', linewidth=0.6)
        # set y-limits based on data with a small margin
        qmax = max(abs(q) for q in Qgb_series) if any(Qgb_series) else 0.01
        ax_q.set_ylim(-1.2 * qmax, 1.2 * qmax)
        ax_q_marker, = ax_q.plot([sim_times[0]], [Qgb_series[0]], marker='o', color='red')

    def init():
        interior_patch.set_height(0.0)
        ext_rect.set_height(0.0)
        time_text.set_text('')
        if velocity_series is not None:
            vel_text.set_text('')
        if basement_levels is not None:
            base_patch.set_height(0.0)
            return [interior_patch, ext_rect, time_text, base_patch]
        artists = [interior_patch, ext_rect, time_text]
        if velocity_series is not None:
            artists.append(vel_text)
        return artists

    def update(frame_i):
        # remove previous dynamic arrows
        for a in ingress_arrows:
            try:
                a.remove()
            except Exception:
                pass
        ingress_arrows.clear()

        i = frame_indices[frame_i]
        h_in = sim_levels[i]
        h_out = external_levels[i]

        # update water heights
        interior_patch.set_height(h_in)
        ext_rect.set_height(h_out)

        # update velocity text if available
        if velocity_series is not None:
            try:
                v_now = velocity_series[i]
            except Exception:
                v_now = None
            if v_now is not None:
                vel_text.set_text(f'v = {v_now:.2f} m/s')
            else:
                vel_text.set_text('')

        # update basement panel if present
        if basement_levels is not None:
            hb = basement_levels[i]
            base_patch.set_height(hb)

        # draw instantaneous flow arrows for each ingress (only those that
        # involve the ground-floor face are drawn on the main panel)
        max_area = max((ing.area for ing in ingress_list), default=1.0)
        for idx, ing in enumerate(ingress_list):
            # draw only arrows that refer to the main face (target or source is ground)
            if not (ing.target == 'ground' or ing.source == 'ground' or (ing.source == 'outside' and ing.target == 'ground')):
                continue
            # compute flow using absolute heads on the main panel
            Q = ing.compute_flow(h_out, h_in)
            y = ing.height
            if Q > 0:
                xa = ex_x + 0.05
                xb = ingress_x - 0.04
                color = 'dodgerblue'
            elif Q < 0:
                xa = ingress_x - 0.04
                xb = ex_x + 0.05
                color = 'crimson'
            else:
                xa = xb = ingress_x - 0.04
                color = 'gray'
            mag = min(1.0, abs(Q) / (max(1e-9, max_area)))
            arr = ax_top.annotate('', xy=(xb, y), xytext=(xa, y), arrowprops=dict(arrowstyle='-|>', color=color, linewidth=1 + 3 * mag, shrinkA=0, shrinkB=0))
            ingress_arrows.append(arr)
        # draw vertical arrows on the top panel for ground<->basement connections
        # to indicate flow between ground and basement (downwards if ground->basement)
        # and add a numeric label; place arrows next to the ingress face for clarity
        Q_current = Qgb_series[i] if i < len(Qgb_series) else 0.0
        # compute a sensible scale for arrow visuals
        Q_scale = max(1e-6, max(abs(q) for q in Qgb_series))
        for ing in ingress_list:
            src = getattr(ing, 'source', 'outside')
            tgt = getattr(ing, 'target', 'ground')
            if not ((src == 'ground' and tgt == 'basement') or (src == 'basement' and tgt == 'ground')):
                continue
            y0 = ing.height
            # place arrow near the right face (just inside the building)
            x0 = ingress_x - 0.08
            # use the precomputed total Q for visualisation (per-connector split not available here)
            Qgb = Q_current
            # arrow length and linewidth scaled more aggressively for visibility
            arrow_len = 0.25 + 0.75 * min(1.0, abs(Qgb) / Q_scale)
            linewidth = 1.0 + 4.0 * min(1.0, abs(Qgb) / Q_scale)
            # determine arrow tip on the shared edge between top and basement panels
            color = 'gray'
            if ax_b is not None:
                try:
                    # top edge of the basement panel in ax_b data coords
                    top_y_b = ax_b.get_ylim()[1]
                    # get display coords of that edge at ingress_x and transform back to ax_top data coords
                    disp = ax_b.transData.transform((ingress_x - 0.08, top_y_b))
                    _, y_edge_top = ax_top.transData.inverted().transform(disp)
                    # offset the tip slightly upward into the top panel so it is visible
                    offset_up = 0.02 * building_height
                    # ensure the tip does not cross the arrow start (y0)
                    y1 = min(y0 - 0.02, y_edge_top + offset_up)
                except Exception:
                    # fallback
                    y1 = max(0.0, y0 - arrow_len)
            else:
                y1 = max(0.0, y0 - arrow_len)
            if Qgb > 0:
                # ground -> basement (downwards)
                color = 'dodgerblue'
            elif Qgb < 0:
                # basement -> ground (upwards)
                color = 'crimson'
            mag = min(1.0, abs(Qgb) / Q_scale)
            arr_v = ax_top.annotate('', xy=(x0, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle='-|>', color=color, linewidth=linewidth, shrinkA=0, shrinkB=0))
            ingress_arrows.append(arr_v)
            # numeric label in L/s to the left of the arrow
            q_label_text = f"{Qgb*1000.0:.2f} L/s"
            lbl = ax_top.text(x0 - 0.12, (y0 + y1) / 2.0, q_label_text, fontsize=7, color='black', va='center', ha='right', bbox=dict(boxstyle='round,pad=0.1', fc='white', ec='none'))
            ingress_arrows.append(lbl)
        time_text.set_text(f'Time: {sim_times[i]:.1f} {unit_label}')
        # update bottom Q panel marker if present
        if ax_q_marker is not None:
            ax_q_marker.set_data([sim_times[i]], [Qgb_series[i]])
        # ensure artists include bottom panel elements when present
        artists = [interior_patch, ext_rect, time_text] + ingress_arrows
        if velocity_series is not None:
            artists.append(vel_text)
        if basement_levels is not None:
            artists = [base_patch] + artists
        if ax_q is not None and ax_q_marker is not None:
            artists += [ax_q_marker, ax_q_line]
            return artists
        if basement_levels is not None:
            return artists
        return [interior_patch, ext_rect, time_text] + ingress_arrows

    ani = animation.FuncAnimation(fig, update, frames=len(frame_indices), init_func=init, blit=False)

    try:
        writer = animation.PillowWriter(fps=fps)
        ani.save(outpath, writer=writer)
    except Exception:
        writer = animation.FFMpegWriter(fps=fps)
        ani.save(outpath.replace('.gif', '.mp4'), writer=writer)
    finally:
        plt.close(fig)
