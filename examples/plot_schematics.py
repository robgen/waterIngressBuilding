#!/usr/bin/env python3
"""Generate building cross-section schematic diagrams for all 9 case studies.

Each diagram shows:
  - Building outline (walls, roof, floor slab)
  - Exterior ground (hatched soil fill)
  - Ingress paths  – red tick: deterministic path at its sill height
                   – blue filled bar: probabilistic seal (fragility)
                   – faint red tick: path protected by a membrane
  - Basement pit (cases 04-06)
  - Sump pit + pump discharge arrow (cases 05-06)
  - Membrane line: blue dashed = probabilistic, blue solid = deterministic

Run from the repo root::

    python examples/plot_schematics.py

Output:
    examples/schematics.png
"""

import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# ── colour palette (matches plot.py / plot_mc.py) ─────────────────────────────
_BLACK      = '#1c2027'
_RED        = '#c0392b'
_BLUE       = '#2980b9'
_EARTH_FC   = '#c8b89a'   # soil fill colour
_EARTH_EC   = '#a09070'   # soil edge / hatch colour
_INT_GF     = '#f5f6f7'   # ground-floor interior fill
_INT_BS     = '#edf0f2'   # basement interior fill

# ══════════════════════════════════════════════════════════════════════════════
# Case definitions
# ══════════════════════════════════════════════════════════════════════════════
#
# Path styles:
#   'det'    – deterministic ingress path  (solid red tick)
#   'prob'   – probabilistic seal          (blue filled bar + faint dashed red tick)
#   'behind' – path behind a membrane      (faint/light red tick)
#
# Membrane styles:
#   'prob'   – probabilistic (blue dashed line)
#   'det'    – deterministic (blue solid line)
# ──────────────────────────────────────────────────────────────────────────────

CASES = [
    dict(
        label='Case 01', subtitle='Single opening\nsill = 0 m',
        floor_h=2.5, bsmt_d=None, sump=False, pump=False,
        gf_paths=[dict(sill=0.0, name='door gap', style='det')],
        bsmt_paths=[], membrane=None,
    ),
    dict(
        label='Case 02', subtitle='Raised sill\nsill = 0.3 m',
        floor_h=2.5, bsmt_d=None, sump=False, pump=False,
        gf_paths=[dict(sill=0.3, name='door gap', style='det')],
        bsmt_paths=[], membrane=None,
    ),
    dict(
        label='Case 03', subtitle='Two openings\nsills 0 m and 0.3 m',
        floor_h=2.5, bsmt_d=None, sump=False, pump=False,
        gf_paths=[
            dict(sill=0.0, name='crack',    style='det'),
            dict(sill=0.3, name='door gap', style='det'),
        ],
        bsmt_paths=[], membrane=None,
    ),
    dict(
        label='Case 04', subtitle='Basement\n(no pump)',
        floor_h=2.5, bsmt_d=2.5, sump=False, pump=False,
        gf_paths=[],
        bsmt_paths=[dict(sill=0.0, name='bsmt crack', style='det')],
        membrane=None,
    ),
    dict(
        label='Case 05', subtitle='Basement + pump\n(keeps up)',
        floor_h=2.5, bsmt_d=2.5, sump=True, pump=True,
        gf_paths=[],
        bsmt_paths=[dict(sill=0.0, name='bsmt crack', style='det')],
        membrane=None,
    ),
    dict(
        label='Case 06', subtitle='Basement + pump\n(overwhelmed)',
        floor_h=2.5, bsmt_d=2.5, sump=True, pump=True,
        gf_paths=[],
        bsmt_paths=[dict(sill=0.0, name='bsmt crack', style='det')],
        membrane=None,
    ),
    dict(
        label='Case 07', subtitle='Probabilistic seal\n(MC fragility)',
        floor_h=2.5, bsmt_d=None, sump=False, pump=False,
        gf_paths=[dict(sill=0.0, name='seal door', style='prob')],
        bsmt_paths=[], membrane=None,
    ),
    dict(
        label='Case 08', subtitle='Membrane group\n(probabilistic)',
        floor_h=2.5, bsmt_d=None, sump=False, pump=False,
        gf_paths=[
            dict(sill=0.0, name='door gap', style='behind'),
            dict(sill=0.1, name='airbrick', style='behind'),
        ],
        bsmt_paths=[],
        membrane=dict(sill=0.0, capacity=0.5, style='prob'),
    ),
    dict(
        label='Case 09', subtitle='Membrane\n(deterministic)',
        floor_h=2.5, bsmt_d=None, sump=False, pump=False,
        gf_paths=[
            dict(sill=0.0, name='door gap', style='behind'),
            dict(sill=0.1, name='airbrick', style='behind'),
        ],
        bsmt_paths=[],
        membrane=dict(sill=0.0, capacity=0.6, style='det'),
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# Drawing constants (all in metres — used as data-unit coordinates)
# ══════════════════════════════════════════════════════════════════════════════
W        = 1.0    # building width
EXT_W    = 0.45   # exterior strip width on each side
LW_WALL  = 1.8    # wall line width (pt)
LW_THIN  = 0.9    # thin line width (pt)
TICK     = 0.13   # half-length of ingress tick mark
SUMP_W   = 0.22   # sump pit width
SUMP_D   = 0.28   # sump pit extra depth below basement floor


# ══════════════════════════════════════════════════════════════════════════════
# Core drawing function
# ══════════════════════════════════════════════════════════════════════════════

def draw_schematic(ax, cfg):
    """Draw one building cross-section schematic on *ax*.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes to draw on (turned off: no ticks, spines, labels).
    cfg : dict
        Case configuration – see the CASES list above for the required keys.
    """
    floor_h  = cfg['floor_h']
    bsmt_d   = cfg.get('bsmt_d') or 0.0
    has_sump = cfg.get('sump', False) and bsmt_d > 0
    has_pump = cfg.get('pump', False) and bsmt_d > 0
    membrane = cfg.get('membrane', None)

    y_gnd    = 0.0              # exterior ground datum
    y_top    = floor_h          # roof level
    y_bsmt   = -bsmt_d          # basement floor level (0 if no basement)
    y_sump   = y_bsmt - SUMP_D  # sump pit floor (only relevant if has_sump)

    # ── axes limits (slight margins) ──────────────────────────────────────────
    x_lo  = -(EXT_W + 0.15)
    x_hi  = W + EXT_W + 0.40   # extra space for pump-arrow label / membrane text
    y_lo  = (y_sump - 0.20) if has_sump else (y_bsmt - 0.20) if bsmt_d else -0.35
    y_hi  = y_top + 0.30

    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.axis('off')

    # ── exterior soil fill (hatched) ──────────────────────────────────────────
    # Everything outside the building walls (x < 0 or x > W) below y_gnd
    soil_bot = y_lo  # extend soil fill to bottom of plot
    for x0_fill, w_fill in [(-EXT_W, EXT_W), (W, EXT_W)]:
        ax.add_patch(mpatches.Rectangle(
            (x0_fill, soil_bot), w_fill, y_gnd - soil_bot,
            fc=_EARTH_FC, ec=_EARTH_EC, lw=0.35,
            hatch='//////', zorder=1,
        ))
    # Ground surface line
    ax.plot([-(EXT_W + 0.10), W + EXT_W + 0.10], [y_gnd, y_gnd],
            color=_BLACK, lw=LW_THIN, zorder=4)

    # ── interior fill ─────────────────────────────────────────────────────────
    ax.add_patch(mpatches.Rectangle(
        (0, y_gnd), W, floor_h,
        fc=_INT_GF, ec='none', zorder=2,
    ))
    if bsmt_d > 0:
        ax.add_patch(mpatches.Rectangle(
            (0, y_bsmt), W, bsmt_d,
            fc=_INT_BS, ec='none', zorder=2,
        ))

    # ── building walls ────────────────────────────────────────────────────────
    wall_bot = y_bsmt if bsmt_d > 0 else y_gnd
    # Left wall
    ax.plot([0, 0], [wall_bot, y_top], color=_BLACK, lw=LW_WALL, zorder=5)
    # Right wall
    ax.plot([W, W], [wall_bot, y_top], color=_BLACK, lw=LW_WALL, zorder=5)
    # Roof
    ax.plot([0, W], [y_top, y_top],   color=_BLACK, lw=LW_WALL, zorder=5)
    # Bottom slab
    ax.plot([0, W], [wall_bot, wall_bot], color=_BLACK, lw=LW_WALL, zorder=5)
    # Ground-floor slab separator (dashed, only for basement cases)
    if bsmt_d > 0:
        ax.plot([0, W], [y_gnd, y_gnd],
                color=_BLACK, lw=LW_THIN, ls=(0, (4, 3)), alpha=0.55, zorder=4)

    # ── sump pit ──────────────────────────────────────────────────────────────
    if has_sump:
        # Sump positioned in the lower-right corner of the basement
        sx0 = W - 0.08 - SUMP_W
        sx1 = W - 0.08
        sy_top = y_bsmt          # basement floor level
        sy_bot = y_sump          # sump pit floor

        # White fill (cut into basement fill)
        ax.add_patch(mpatches.Rectangle(
            (sx0, sy_bot), SUMP_W, SUMP_D,
            fc='white', ec='none', zorder=3,
        ))
        # Basement floor left of sump, then U-shape, then right of sump
        ax.plot([0, sx0], [sy_top, sy_top], color=_BLACK, lw=LW_WALL, zorder=6)
        ax.plot([sx0, sx0], [sy_top, sy_bot], color=_BLACK, lw=LW_WALL, zorder=6)
        ax.plot([sx0, sx1], [sy_bot, sy_bot], color=_BLACK, lw=LW_WALL, zorder=6)
        ax.plot([sx1, sx1], [sy_bot, sy_top], color=_BLACK, lw=LW_WALL, zorder=6)
        ax.plot([sx1, W],   [sy_top, sy_top], color=_BLACK, lw=LW_WALL, zorder=6)

        # Sump centre (used for pump arrow)
        sump_cx = (sx0 + sx1) / 2
        sump_cy = (sy_top + sy_bot) / 2
    else:
        sump_cx = W * 0.75
        sump_cy = y_bsmt

    # ── pump discharge arrow ──────────────────────────────────────────────────
    if has_pump:
        # Dashed line from sump centre → right wall, then continuing to exterior
        arrow_y = sump_cy
        x_pipe_exit = W + EXT_W - 0.05   # tip of arrow in exterior
        # Dashed pipe line
        ax.plot([sump_cx, x_pipe_exit], [arrow_y, arrow_y],
                color=_BLUE, lw=1.6, ls=(0, (4, 2.5)),
                solid_capstyle='butt', zorder=6)
        # Arrowhead (separate small annotation so we get a proper arrowhead)
        ax.annotate(
            '', xy=(x_pipe_exit, arrow_y),
            xytext=(x_pipe_exit - 0.001, arrow_y),
            arrowprops=dict(arrowstyle='-|>', color=_BLUE,
                            lw=1.6, mutation_scale=11),
            zorder=7,
        )
        # Label
        ax.text(x_pipe_exit + 0.04, arrow_y + 0.07,
                r'$Q_p$', color=_BLUE, fontsize=6.5, ha='left', va='bottom',
                zorder=7)

    # ── ingress path marks ────────────────────────────────────────────────────
    # (drawn on the left wall at x = 0)
    # ─────────────────────────────────────────────────────────────────────────
    def _path(sill_y, style, name):
        if style == 'det':
            # Solid red horizontal tick
            ax.plot([-TICK, TICK], [sill_y, sill_y],
                    color=_RED, lw=2.4, solid_capstyle='round',
                    zorder=8)
            ax.text(-TICK - 0.05, sill_y, name,
                    ha='right', va='center', fontsize=6.0, color=_RED)

        elif style == 'prob':
            # Blue filled rectangle centred on the wall (probabilistic seal)
            bh = 0.13   # bar half-height
            ax.add_patch(mpatches.FancyBboxPatch(
                (-0.045, sill_y - bh), 0.09, 2 * bh,
                boxstyle='round,pad=0.01',
                fc=_BLUE, ec=_BLUE, lw=0.5, alpha=0.80, zorder=8,
            ))
            # Faint dashed red tick for the underlying sill
            ax.plot([-TICK, TICK], [sill_y, sill_y],
                    color=_RED, lw=1.0, ls='--', alpha=0.45, zorder=7)
            ax.text(-TICK - 0.05, sill_y, name,
                    ha='right', va='center', fontsize=6.0, color=_BLUE)

        elif style == 'behind':
            # Faint red tick (path shielded by membrane)
            ax.plot([-TICK * 0.55, TICK * 0.55], [sill_y, sill_y],
                    color=_RED, lw=1.4, alpha=0.32, solid_capstyle='round',
                    zorder=7)
            ax.text(-TICK * 0.55 - 0.05, sill_y, name,
                    ha='right', va='center', fontsize=5.5,
                    color=_RED, alpha=0.38)

    for p in cfg.get('gf_paths', []):
        _path(p['sill'], p['style'], p.get('name', ''))
    for p in cfg.get('bsmt_paths', []):
        _path(p['sill'], p['style'], p.get('name', ''))

    # ── membrane ──────────────────────────────────────────────────────────────
    if membrane is not None:
        y_m    = membrane.get('sill', 0.0)
        cap    = membrane.get('capacity', 0.5)
        mstyle = membrane.get('style', 'prob')
        ls_m   = (0, (5, 3)) if mstyle == 'prob' else '-'
        lw_m   = 2.2

        x_m0 = -(EXT_W - 0.05)   # left edge of membrane line
        x_m1 = 0.0                # membrane stops at the building wall

        # The membrane line sits on the exterior face of the left wall
        ax.plot([x_m0, x_m1], [y_m, y_m],
                color=_BLUE, lw=lw_m, ls=ls_m,
                solid_capstyle='butt', zorder=8)

        # Small vertical indicator showing design capacity height
        x_cap_mark = x_m0 + 0.06
        ax.plot([x_cap_mark, x_cap_mark], [y_m, y_m + cap],
                color=_BLUE, lw=0.9, ls=':', alpha=0.65, zorder=7)
        ax.plot([x_cap_mark - 0.04, x_cap_mark + 0.04], [y_m + cap, y_m + cap],
                color=_BLUE, lw=0.9, alpha=0.65, zorder=7)

        # Label
        prob_tag = ' (prob.)' if mstyle == 'prob' else ''
        ax.text(x_m0 - 0.03, y_m + cap / 2,
                f'membrane\n{cap:.1f} m{prob_tag}',
                ha='right', va='center', fontsize=5.5,
                color=_BLUE, style='italic' if mstyle == 'prob' else 'normal',
                zorder=8)

    # ── case label ────────────────────────────────────────────────────────────
    # Draw it as an inset text in the top-left of the building interior
    ax.text(0.05, y_top - 0.12, cfg['label'],
            ha='left', va='top', fontsize=7.5, fontweight='bold',
            color='#1e2433', zorder=9)
    ax.text(0.05, y_top - 0.32, cfg['subtitle'],
            ha='left', va='top', fontsize=6.2, color='#3a4254',
            linespacing=1.35, zorder=9)

    # ── "exterior" label ──────────────────────────────────────────────────────
    ax.text(-(EXT_W / 2), y_hi - 0.05, 'exterior',
            ha='center', va='top', fontsize=5.5, color='#888',
            style='italic')

    # ── height reference tick on right side ───────────────────────────────────
    # Small tick + "0 m" label at ground datum
    ax.plot([W + 0.04, W + 0.10], [y_gnd, y_gnd],
            color='#aaa', lw=0.7, zorder=4)
    ax.text(W + 0.13, y_gnd, '0 m',
            ha='left', va='center', fontsize=5.0, color='#999')


# ══════════════════════════════════════════════════════════════════════════════
# Build the 3 × 3 figure
# ══════════════════════════════════════════════════════════════════════════════

def plot_all_schematics(out_path=None):
    """Draw all 9 case-study schematics in a 3 × 3 grid and save."""
    # Row 1 (cases 01-03) and Row 3 (07-09): ground floor only → shorter row
    # Row 2 (cases 04-06): basement → taller row
    plt.rcParams.update({'font.family': 'sans-serif',
                         'font.sans-serif': ['Helvetica Neue', 'Arial',
                                             'DejaVu Sans']})
    fig, axes = plt.subplots(
        3, 3,
        figsize=(13, 13),
        gridspec_kw={'height_ratios': [1.0, 1.9, 1.0],
                     'hspace': 0.14, 'wspace': 0.10},
    )
    fig.patch.set_facecolor('white')

    for idx, (ax, cfg) in enumerate(zip(axes.flat, CASES)):
        draw_schematic(ax, cfg)
        # Light boundary box around each panel
        for spine in ax.spines.values():
            spine.set_visible(False)

    # ── legend (bottom of figure) ─────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(fc=_RED,  ec=_RED,  lw=0, label='Deterministic ingress path (red tick)'),
        mpatches.Patch(fc=_BLUE, ec=_BLUE, lw=0, label='Probabilistic seal — fragility element (blue bar)'),
        mpatches.Patch(fc='none', ec=_BLUE, lw=0,
                       label='Protected path (faint tick — behind membrane)'),
    ]
    from matplotlib.lines import Line2D
    legend_items += [
        Line2D([0], [0], color=_BLUE, lw=2, ls=(0, (5, 3)),
               label='Probabilistic membrane (blue dashed)'),
        Line2D([0], [0], color=_BLUE, lw=2, ls='-',
               label='Deterministic membrane (blue solid)'),
        Line2D([0], [0], color=_BLUE, lw=1.6, ls=(0, (4, 2.5)),
               marker='>', markersize=5, markevery=[-1],
               label='Pump discharge (dashed arrow)'),
    ]
    fig.legend(
        handles=legend_items,
        loc='lower center', ncol=3,
        fontsize=7.5, framealpha=0.95,
        edgecolor='#d0d5dd',
        bbox_to_anchor=(0.5, 0.01),
    )

    fig.suptitle('Case study building schematics — cross-section',
                 fontsize=13, fontweight='bold', color='#1e2433', y=0.995)

    if out_path is None:
        out_path = os.path.join(HERE, 'schematics.png')
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'Saved {out_path}')
    return out_path


if __name__ == '__main__':
    plot_all_schematics()
