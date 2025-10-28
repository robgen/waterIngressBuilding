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


def save_simulation_result(sim_times, sim_levels, external_levels, outpath, time_unit=None):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(sim_times, external_levels, label='External Level (h_out)')
    ax.plot(sim_times, sim_levels, label='Indoor Level (h_in)')
    xlabel = 'Time'
    if time_unit:
        xlabel = f'Time ({time_unit})'
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Water Level (m)')
    ax.set_title('Flood Ingress Simulation')
    ax.legend()
    fig.tight_layout()
    fig.savefig(outpath)
    plt.close(fig)


def generate_animation(sim_times, sim_levels, external_levels, ingress_list, outpath, fps=10, max_frames=200, time_unit=None):
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
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(-0.5, 4.0)
    ax.set_ylim(0, building_height)
    ax.set_xlabel('Horizontal position')
    ax.set_ylabel('Height (m)')
    ax.set_title('Flood Ingress Animation')

    # Ground
    ax.hlines(0, -0.5, 4.0, colors='saddlebrown', linewidth=2)

    # Building (simple block)
    bx = 0.5
    building_rect = patches.Rectangle((bx, 0), building_width, building_height, linewidth=2, edgecolor='black', facecolor='#f7f7f7')
    ax.add_patch(building_rect)

    # Door and small details
    door = patches.Rectangle((bx + 0.35, 0.0), 0.3, 0.02, facecolor='saddlebrown')
    ax.add_patch(door)

    # Ingress markers and labels on the right face
    ingress_x = bx + building_width
    for idx, ing in enumerate(ingress_list):
        y = ing.height
        mark = patches.Rectangle((ingress_x - 0.04, y - 0.03), 0.04, 0.06, color='sienna')
        ax.add_patch(mark)
        # single-line label for animation
        label = f"{ing.name} (h={ing.height:.2f} m) — A={ing.area:.3f} m^2, C={ing.coeff:.2f}"
        ax.text(ingress_x + 0.06, y, label, va='center', fontsize=8)

    # Interior water (inside building)
    interior_patch = patches.Rectangle((bx, 0), building_width, 0.0, facecolor='#1f77b4', alpha=0.6)
    ax.add_patch(interior_patch)

    # Exterior water body on the right
    ex_x = 2.2
    ex_width = 1.5
    ext_rect = patches.Rectangle((ex_x, 0), ex_width, 0.0, facecolor='#0b63a6', alpha=0.5)
    ax.add_patch(ext_rect)
    ax.text(ex_x + ex_width / 2, building_height * 0.95, 'External water', ha='center', va='center', fontsize=9, color='#0b63a6')

    # Time label
    unit_label = 's' if (time_unit is None or time_unit == 'seconds') else ('min' if time_unit.startswith('min') else ('h' if time_unit.startswith('hour') else time_unit))
    time_text = ax.text(bx, building_height * 0.96, '', fontsize=10)

    # Container for dynamic ingress arrows
    ingress_arrows = []

    def init():
        interior_patch.set_height(0.0)
        ext_rect.set_height(0.0)
        time_text.set_text('')
        return [interior_patch, ext_rect, time_text]

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

        # draw instantaneous flow arrows for each ingress
        max_area = max((ing.area for ing in ingress_list), default=1.0)
        for idx, ing in enumerate(ingress_list):
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
            arr = ax.annotate('', xy=(xb, y), xytext=(xa, y), arrowprops=dict(arrowstyle='-|>', color=color, linewidth=1 + 3 * mag, shrinkA=0, shrinkB=0))
            ingress_arrows.append(arr)
            time_text.set_text(f'Time: {sim_times[i]:.1f} {unit_label}')
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
