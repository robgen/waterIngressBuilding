#!/usr/bin/env python3
"""Generate high-quality visualisation figures for fragility MC cases."""
import csv
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# ── inherit the same rcParams as viz.py ───────────────────────────────────────
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
    'lines.linewidth':     2.0,
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
    'legend.framealpha':   0.93,
    'legend.edgecolor':    '#d0d5dd',
    'savefig.dpi':         150,
    'savefig.bbox':        'tight',
    'savefig.pad_inches':  0.12,
    'axes.spines.top':     False,
    'axes.spines.right':   False,
})

_BLUE   = '#2980b9'
_ORANGE = '#e67e22'
_RED    = '#c0392b'
_GREEN  = '#27ae60'
_PURPLE = '#8e5fbf'
_GREY   = '#7f8c8d'

PCT_COLOURS = {'P10': '#f39c12', 'P25': '#2980b9', 'P50': '#c0392b',
               'P75': '#2980b9', 'P90': '#f39c12'}
PCT_LS      = {'P10': '--',      'P25': ':',       'P50': '-',
               'P75': ':',       'P90': '--'}


def _load(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def plot_mc_case(case_dir, title, out_name):
    reps   = _load(os.path.join(case_dir, 'out', 'fragility_replicates.csv'))
    sfreq  = _load(os.path.join(case_dir, 'out', 'fragility_state_freq.csv'))

    peak_h   = np.array([float(r['peak_h_in_m'])              for r in reps])
    peak_ext = np.array([float(r.get('peak_h_ext_m', 0.5))    for r in reps])
    n        = len(peak_h)

    # split replicates: "intact" (near-zero) vs "degraded"
    threshold = max(peak_h) * 0.05 if max(peak_h, default=0) > 0 else 0.01
    low_mask  = peak_h < threshold
    high_mask = ~low_mask
    n_low     = int(low_mask.sum())
    n_high    = int(high_mask.sum())

    # ── figure layout ─────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 6.5))
    fig.patch.set_facecolor('white')
    gs = gridspec.GridSpec(
        1, 2, figure=fig,
        width_ratios=[2.8, 1],
        hspace=0.0, wspace=0.32,
        left=0.07, right=0.97, top=0.88, bottom=0.12)

    # ── Scatter: peak h_ext vs peak h_int, with CDF on right y-axis ──────────
    ax_s = fig.add_subplot(gs[0, 0])

    sc_handles = []
    if n_high > 0 and n_low > 0:
        sc1 = ax_s.scatter(
            peak_h[low_mask], peak_ext[low_mask],
            color=_BLUE, alpha=0.45, s=22, zorder=3, linewidths=0,
            label=f'Intact  (n = {n_low})')
        sc2 = ax_s.scatter(
            peak_h[high_mask], peak_ext[high_mask],
            color=_ORANGE, alpha=0.55, s=22, zorder=4, linewidths=0,
            label=f'Degraded  (n = {n_high})')
        sc_handles = [sc1, sc2]
    else:
        sc = ax_s.scatter(
            peak_h, peak_ext,
            color=_BLUE, alpha=0.45, s=22, zorder=3, linewidths=0,
            label=f'n = {n}')
        sc_handles = [sc]

    ax_s.set_xlabel('Peak interior depth  $h_{in}^{max}$  (m)')
    ax_s.set_ylabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax_s.set_xlim(left=0)

    # If h_ext is constant (fixed hydrograph), tighten the y-axis so the strip
    # of scatter points is visible rather than lost at the centre of a wide range.
    ext_range = float(peak_ext.max() - peak_ext.min())
    if ext_range < 1e-4:
        mid = float(peak_ext.mean())
        ax_s.set_ylim(mid * 0.7, mid * 1.3)
    else:
        ax_s.set_ylim(bottom=0)

    # ── CDF of peak interior depth on right y-axis (shares x = h_int) ────────
    ax_cdf = ax_s.twinx()
    plt.rcParams['axes.spines.right'] = True   # re-enable for twin axis
    ax_cdf.spines['right'].set_visible(True)
    ax_cdf.spines['right'].set_color('#c8cdd2')
    ax_cdf.spines['right'].set_linewidth(0.8)

    h_sort   = np.sort(peak_h)
    cdf_pct  = np.linspace(100.0 / n, 100.0, n)

    ax_cdf.fill_between(h_sort, cdf_pct, step='post', color=_RED, alpha=0.06, zorder=1)
    cdf_line, = ax_cdf.step(h_sort, cdf_pct, color=_RED, lw=1.8,
                             where='post', zorder=5, label='Empirical CDF')
    ax_cdf.set_ylim(0, 108)
    ax_cdf.set_ylabel('Cumulative probability  (%)', color=_RED)
    ax_cdf.tick_params(axis='y', labelcolor=_RED)
    ax_cdf.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.0f}%'))
    ax_cdf.grid(False)   # avoid double grid

    # Subtle percentile hairlines on the CDF panel
    for pname, pval_arr in [('P25', np.percentile(peak_h, 25)),
                             ('P50', np.percentile(peak_h, 50)),
                             ('P75', np.percentile(peak_h, 75))]:
        p_num = int(pname[1:])
        ax_cdf.plot([pval_arr, pval_arr], [0, p_num],
                    color=PCT_COLOURS[pname], lw=0.8, ls=':', alpha=0.6, zorder=2)
        ax_cdf.plot([0, pval_arr], [p_num, p_num],
                    color=PCT_COLOURS[pname], lw=0.8, ls=':', alpha=0.6, zorder=2)

    # Combined legend (scatter handles + CDF line)
    ax_s.legend(handles=sc_handles + [cdf_line], fontsize=8, loc='upper right')
    ax_s.set_title('Peak $h_{ext}$ vs peak $h_{in}$ — scatter and empirical CDF')

    # ── Element state frequencies ─────────────────────────────────────────────
    ax_sf = fig.add_subplot(gs[0, 1])
    if sfreq:
        # Sort columns by state index so cumulative→exact differencing is correct
        state_cols = sorted(
            [k for k in sfreq[0] if k.startswith('state_')],
            key=lambda c: int(c.split('_')[1]))
        elems = [r['element'] for r in sfreq]
        n_el  = len(elems); n_st = len(state_cols)
        x     = np.arange(n_el)
        bw    = 0.75 / max(n_st, 1)
        blues = matplotlib.colormaps.get_cmap('Blues_r')

        for si, col in enumerate(state_cols):
            freqs  = [float(r.get(col, 0) or 0) for r in sfreq]
            colour = blues(0.15 + 0.60 * si / max(n_st - 1, 1))
            lbl    = f'State {si}'
            b      = ax_sf.bar(x + si * bw, freqs, bw,
                               label=lbl, color=colour,
                               edgecolor='white', lw=0.4, zorder=3)
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

        # Explanation annotation
        expl = (
            'Each bar: fraction of replicates\n'
            'in exactly that state.\n\n'
            'State 0  base state (not degraded)\n'
            'State k  degraded to state k\n'
            '  (e.g. seal failure,\n'
            '   membrane overtopping)\n\n'
            'Bars sum to 100% per element.'
        )
        ax_sf.text(0.04, 0.60, expl,
                   transform=ax_sf.transAxes,
                   fontsize=7.2, va='top', ha='left',
                   color='#444',
                   bbox=dict(boxstyle='round,pad=0.4', fc='white',
                             ec='#d0d5dd', alpha=0.95))
    else:
        ax_sf.text(0.5, 0.5, 'No state data',
                   transform=ax_sf.transAxes,
                   ha='center', va='center', fontsize=10, color='#888')

    # ── figure title ──────────────────────────────────────────────────────────
    fig.suptitle(title, fontsize=13, fontweight='bold', color='#1e2433', y=0.97)

    # ── split annotation ──────────────────────────────────────────────────────
    if n_low > 0 and n_high > 0:
        split_txt = (f'{n_low}/{n}  replicates at near-zero  ({100*n_low/n:.1f}%)\n'
                     f'{n_high}/{n}  replicates with significant ingress  ({100*n_high/n:.1f}%)')
        fig.text(0.42, 0.935, split_txt,
                 ha='center', va='top', fontsize=8.5, color='#444',
                 style='italic',
                 bbox=dict(boxstyle='round,pad=0.35', fc='#f4f6f9',
                           ec='#d0d5dd', alpha=0.95))

    out = os.path.join(case_dir, 'out', out_name)
    fig.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  Saved {out}')


if __name__ == '__main__':
    plot_mc_case(
        os.path.join(HERE, 'ex07'),
        'Case 07 — Fragility MC: single probabilistic seal  (n = 500, seed = 42)',
        'mc_result.png',
    )
    plot_mc_case(
        os.path.join(HERE, 'ex08'),
        'Case 08 — Fragility MC: membrane-protected group  (n = 500, seed = 42)',
        'mc_result.png',
    )
    plot_mc_case(
        os.path.join(HERE, 'ex09'),
        'Case 09 — Deterministic membrane: design capacity above flood peak  (n = 500, seed = 42)',
        'mc_result.png',
    )
    print('Done.')
