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
    summ   = _load(os.path.join(case_dir, 'out', 'fragility_summary.csv'))
    sfreq  = _load(os.path.join(case_dir, 'out', 'fragility_state_freq.csv'))

    peak_h  = np.array([float(r['peak_h_in_m'])         for r in reps])
    peak_bs = np.array([float(r['peak_h_basement_m'])    for r in reps])
    vol_in  = np.array([float(r['total_volume_in_m3'])   for r in reps])
    n       = len(peak_h)

    # percentile values keyed by "P10" etc.
    pct: dict[str, dict[str, float]] = {}
    for row in summ:
        m = row['metric']
        pct[m] = {k: float(v) for k, v in row.items()
                  if k.startswith('P') and v != ''}

    pct_h = pct.get('peak_h_in', {})
    labels_sorted = sorted(pct_h.keys(), key=lambda x: int(x[1:]))

    # split replicates: "low" (near-zero) vs "high"
    threshold = max(peak_h) * 0.05 if max(peak_h, default=0) > 0 else 0.01
    low_mask  = peak_h < threshold
    high_mask = ~low_mask
    n_low     = int(low_mask.sum())
    n_high    = int(high_mask.sum())

    # ── figure layout ─────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 9))
    fig.patch.set_facecolor('white')
    gs = gridspec.GridSpec(
        2, 3, figure=fig,
        hspace=0.46, wspace=0.38,
        left=0.07, right=0.97, top=0.91, bottom=0.08)

    # ── (0,0)+(0,1) — histogram spanning two columns ──────────────────────────
    ax_hist = fig.add_subplot(gs[0, :2])

    # separate colour for the two clusters
    if n_high > 0 and n_low > 0:
        ax_hist.hist(peak_h[low_mask],  bins=25, color=_BLUE,   alpha=0.75,
                     edgecolor='white', lw=0.4, label=f'Intact  (n = {n_low})',  zorder=3)
        ax_hist.hist(peak_h[high_mask], bins=25, color=_ORANGE, alpha=0.75,
                     edgecolor='white', lw=0.4, label=f'Degraded  (n = {n_high})', zorder=3)
    else:
        ax_hist.hist(peak_h, bins=35, color=_BLUE, alpha=0.78,
                     edgecolor='white', lw=0.4, zorder=3)

    # percentile vertical lines
    for pname in ('P10', 'P25', 'P50', 'P75', 'P90'):
        val = pct_h.get(pname)
        if val is None:
            continue
        ax_hist.axvline(val, color=PCT_COLOURS[pname], lw=1.8,
                        ls=PCT_LS[pname], zorder=5,
                        label=f'{pname} = {val:.3f} m')

    ax_hist.set_xlabel('Peak ground-floor depth  $h_{in}^{max}$  (m)')
    ax_hist.set_ylabel('Number of replicates')
    ax_hist.set_title('Distribution of peak interior depth')
    ax_hist.legend(fontsize=8, loc='upper right', ncol=2)
    ax_hist.text(0.02, 0.96, f'n = {n} replicates',
                 transform=ax_hist.transAxes,
                 fontsize=8.5, va='top', color='#555',
                 bbox=dict(boxstyle='round,pad=0.28', fc='white',
                           ec='#ccc', alpha=0.88))

    # ── (0,2) — percentile bar chart ──────────────────────────────────────────
    ax_bar = fig.add_subplot(gs[0, 2])
    if labels_sorted:
        vals  = [pct_h[l] for l in labels_sorted]
        cols  = [PCT_COLOURS.get(l, _BLUE) for l in labels_sorted]
        xpos  = np.arange(len(labels_sorted))
        bars  = ax_bar.bar(xpos, vals, color=cols, edgecolor='white',
                           width=0.65, zorder=3)
        ax_bar.bar_label(bars, fmt='%.3f', fontsize=7.5, padding=3,
                         color='#333')
        ax_bar.set_xticks(xpos)
        ax_bar.set_xticklabels(labels_sorted, fontsize=8.5)
        ax_bar.set_ylabel('Peak ground-floor depth  (m)')
        ax_bar.set_title('Percentile summary\n$h_{in}^{max}$')
        ax_bar.set_ylim(0, max(vals) * 1.25 if max(vals) > 0 else 0.1)
        ax_bar.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f'))

    # ── (1,0)+(1,1) — empirical CDF with shaded band ─────────────────────────
    ax_cdf = fig.add_subplot(gs[1, :2])
    h_sort = np.sort(peak_h)
    cdf    = np.linspace(1 / n, 1.0, n)

    # shade P10–P90 band
    p10 = pct_h.get('P10', h_sort[0])
    p90 = pct_h.get('P90', h_sort[-1])
    ax_cdf.axvspan(p10, p90, color=_BLUE, alpha=0.07, zorder=1,
                   label='P10–P90 band')

    ax_cdf.fill_between(h_sort, cdf * 100,
                        color=_BLUE, alpha=0.10, step='post', zorder=2)
    ax_cdf.step(h_sort, cdf * 100, color=_BLUE, lw=2.0,
                where='post', zorder=4, label='Empirical CDF')

    for pname in ('P10', 'P25', 'P50', 'P75', 'P90'):
        val = pct_h.get(pname)
        if val is None:
            continue
        p_val = int(pname[1:])
        ax_cdf.plot([val, val], [0, p_val],
                    color=PCT_COLOURS[pname], lw=0.9, ls=':',
                    zorder=3, alpha=0.70)
        ax_cdf.plot([0, val], [p_val, p_val],
                    color=PCT_COLOURS[pname], lw=0.9, ls=':',
                    zorder=3, alpha=0.70)
        ax_cdf.scatter([val], [p_val], s=28, color=PCT_COLOURS[pname],
                       zorder=5, edgecolors='white', lw=0.5)

    ax_cdf.set_xlabel('Peak ground-floor depth  $h_{in}^{max}$  (m)')
    ax_cdf.set_ylabel('Cumulative probability  (%)')
    ax_cdf.set_title('Empirical CDF of peak interior depth')
    ax_cdf.set_ylim(0, 105)
    ax_cdf.set_xlim(left=0)
    ax_cdf.legend(fontsize=8, loc='upper left')
    ax_cdf.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.0f}%'))

    # ── (1,2) — element state frequencies ────────────────────────────────────
    ax_sf = fig.add_subplot(gs[1, 2])
    if sfreq:
        state_cols = [k for k in sfreq[0] if k.startswith('state_')]
        elems      = [r['element'] for r in sfreq]
        n_el = len(elems); n_st = len(state_cols)
        x    = np.arange(n_el)
        bw   = 0.75 / max(n_st, 1)
        blues = matplotlib.colormaps.get_cmap('Blues_r')

        for si, col in enumerate(state_cols):
            freqs  = [float(r[col]) if r.get(col, '') != '' else 0.0
                      for r in sfreq]
            colour = blues(0.15 + 0.60 * si / max(n_st - 1, 1))
            lbl    = col.replace('state_', 'State ≥ ').replace('_freq', '')
            b      = ax_sf.bar(x + si * bw, freqs, bw,
                               label=lbl, color=colour,
                               edgecolor='white', lw=0.4, zorder=3)
            ax_sf.bar_label(b, fmt='%.2f', fontsize=7, padding=2, color='#333')

        ax_sf.set_xticks(x + bw * (n_st - 1) / 2)
        ax_sf.set_xticklabels(
            [e.replace('membrane:', 'mem:')[:16] for e in elems],
            rotation=30, ha='right', fontsize=7.5)
        ax_sf.set_ylabel('Fraction of replicates')
        ax_sf.set_title('Element state frequencies\n(proxy via peak $h_{in}$)')
        ax_sf.set_ylim(0, 1.12)
        ax_sf.legend(fontsize=7.5, loc='upper right')
        ax_sf.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f'{x:.0%}'))
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
        fig.text(0.50, 0.935, split_txt,
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
    print('Done.')
