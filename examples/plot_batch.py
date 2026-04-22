#!/usr/bin/env python3
"""Visualisation for batch and batch-MC case studies."""
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

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
_GREY   = '#7f8c8d'


def _load(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def plot_batch_deterministic(case_dir, title, out_name='batch_result.png'):
    """Scatter + monotonic-response plot for a deterministic batch run."""
    rows = _load(os.path.join(case_dir, 'out', 'batch_results.csv'))
    h_ext = np.array([float(r['h_peak_ext']) for r in rows])
    h_int = np.array([float(r['h_peak_int']) for r in rows])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.patch.set_facecolor('white')

    # ── Left: scatter ─────────────────────────────────────────────────────────
    ax = axes[0]
    ax.scatter(h_ext, h_int, color=_BLUE, alpha=0.7, s=55, zorder=4,
               edgecolors='white', lw=0.5, label='Simulation result')
    lim = max(h_ext.max(), h_int.max()) * 1.08
    ax.plot([0, lim], [0, lim], color=_GREY, lw=1.0, ls='--', alpha=0.5,
            label='h_int = h_ext  (no attenuation)')
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax.set_ylabel('Peak interior depth  $h_{in}^{max}$  (m)')
    ax.set_title('Peak h_ext vs peak h_int')
    ax.legend(fontsize=8)

    # ── Right: attenuation ratio vs h_ext ─────────────────────────────────────
    ax2 = axes[1]
    ratio = np.where(h_ext > 1e-6, h_int / h_ext, np.nan)
    ax2.scatter(h_ext, ratio, color=_ORANGE, alpha=0.7, s=55, zorder=4,
                edgecolors='white', lw=0.5)
    ax2.axhline(1.0, color=_GREY, lw=1.0, ls='--', alpha=0.5)
    ax2.set_xlim(0)
    ax2.set_ylim(0, min(1.5, np.nanmax(ratio) * 1.15))
    ax2.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax2.set_ylabel('Attenuation ratio  $h_{in} / h_{ext}$')
    ax2.set_title('Interior/exterior attenuation ratio')
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.2f}'))

    fig.suptitle(title, fontsize=12, fontweight='bold', color='#1e2433', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    out = os.path.join(case_dir, 'out', out_name)
    fig.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  Saved {out}')


def plot_batch_mc_fragility(case_dir, title, out_name='batch_mc_result.png'):
    """Fragility-curve style plot for a batch MC run.

    batch_results.csv must have columns: case_id, replicate, h_peak_ext, h_peak_int.
    Rows are all replicates across all hydrographs.
    """
    rows = _load(os.path.join(case_dir, 'out', 'batch_results.csv'))
    h_ext_all = np.array([float(r['h_peak_ext']) for r in rows])
    h_int_all = np.array([float(r['h_peak_int']) for r in rows])

    # Group by h_peak_ext level
    by_level = defaultdict(list)
    for r in rows:
        by_level[round(float(r['h_peak_ext']), 4)].append(float(r['h_peak_int']))

    levels   = np.array(sorted(by_level))
    p10_arr  = np.array([np.percentile(by_level[lv], 10) for lv in levels])
    p50_arr  = np.array([np.percentile(by_level[lv], 50) for lv in levels])
    p90_arr  = np.array([np.percentile(by_level[lv], 90) for lv in levels])
    threshold = max(h_int_all) * 0.05 if h_int_all.max() > 0 else 0.01
    p_fail   = np.array([np.mean(np.array(by_level[lv]) > threshold) for lv in levels])

    fig = plt.figure(figsize=(14, 5.5))
    fig.patch.set_facecolor('white')
    gs = gridspec.GridSpec(1, 2, figure=fig, wspace=0.34,
                           left=0.07, right=0.97, top=0.88, bottom=0.12)

    # ── Left: scatter + percentile bands ──────────────────────────────────────
    ax_s = fig.add_subplot(gs[0, 0])
    ax_s.scatter(h_ext_all, h_int_all, color=_BLUE, alpha=0.18, s=14,
                 zorder=2, linewidths=0, label='Replicate')
    ax_s.fill_between(levels, p10_arr, p90_arr, alpha=0.20, color=_ORANGE, zorder=3)
    ax_s.plot(levels, p10_arr, color=_ORANGE, lw=1.0, ls='--', alpha=0.8, label='P10 / P90')
    ax_s.plot(levels, p90_arr, color=_ORANGE, lw=1.0, ls='--', alpha=0.8)
    ax_s.plot(levels, p50_arr, color=_RED,    lw=2.0, ls='-',  zorder=5, label='P50 (median)')
    ax_s.set_xlim(0)
    ax_s.set_ylim(bottom=0)
    ax_s.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax_s.set_ylabel('Peak interior depth  $h_{in}^{max}$  (m)')
    ax_s.set_title('Replicate scatter + P10 / P50 / P90 bands')
    ax_s.legend(fontsize=8, loc='upper left')

    # ── Right: failure probability vs h_ext ───────────────────────────────────
    ax_f = fig.add_subplot(gs[0, 1])
    ax_f.fill_between(levels, p_fail * 100, alpha=0.15, color=_RED, step='mid')
    ax_f.step(levels, p_fail * 100, color=_RED, lw=2.0, where='mid',
              label='Failure probability')
    ax_f.set_xlim(0)
    ax_f.set_ylim(0, 108)
    ax_f.set_xlabel('Peak exterior depth  $h_{ext}^{max}$  (m)')
    ax_f.set_ylabel('P(significant ingress)  (%)')
    ax_f.set_title('Fragility curve\n'
                   r'(fraction of replicates with $h_{in} > 5\%\,h_{in}^{max}$)')
    ax_f.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.0f}%'))
    ax_f.axvline(0.5, color=_GREY, lw=0.9, ls=':', alpha=0.6,
                 label='h_ext = 0.5 m  (membrane median)')
    ax_f.legend(fontsize=8, loc='upper left')

    n_hydros = len(levels)
    n_reps   = len(rows) // n_hydros if n_hydros else 0
    fig.suptitle(
        f'{title}\n'
        f'({n_hydros} hydrographs × {n_reps} replicates = {len(rows)} total)',
        fontsize=12, fontweight='bold', color='#1e2433', y=0.99)

    out = os.path.join(case_dir, 'out', out_name)
    fig.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  Saved {out}')


if __name__ == '__main__':
    plot_batch_deterministic(
        os.path.join(HERE, 'ex10'),
        'Case 10 — Batch deterministic: 20 hydrographs, single ground-floor opening',
        'batch_result.png',
    )
    plot_batch_mc_fragility(
        os.path.join(HERE, 'ex11'),
        'Case 11 — Batch + fragility MC: 20 hydrographs × 50 replicates, membrane',
        'batch_mc_result.png',
    )
    print('Done.')
