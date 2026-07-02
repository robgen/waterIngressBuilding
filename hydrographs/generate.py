#!/usr/bin/env python3
"""Generate synthetic flood hydrographs as a deterministic parameter-space sweep.

Hydrograph shape: gamma-type rising limb + exponential recession.

  Rising   : h(t) = h_peak * (t/T_p)^α * exp(α*(1 − t/T_p))
             → zero at t=0, peaks exactly at T_p
  Recession: h(t) = h_peak * exp(−k*(t − T_p))
             k chosen so h drops to 1 % of peak at t = T_p + T_rec

Velocity is derived directly from depth at each timestep (no independent shaping):
  v(t) = VEL_A * h(t)^VEL_B

The full case list is the Cartesian product of all parameter grids.
Output: one 3-column CSV per case (time, depth, velocity) written to
<script_dir>/depth/.

Edit the constants below to change coverage or resolution.
"""

import csv
import itertools
import math
import os

# ── Parameter grids ───────────────────────────────────────────────────────────

H_PEAK_VALUES    = [0.01, 0.15, 0.30, 0.45, 0.60, 0.90, 1.20, 1.50, 1.80, 2.10, 2.40] # m  — depth stripes
T_PEAK_VALUES    = [60,   480,  960]                       # minutes
ALPHA_VALUES     = [1.5,  2.5,  4.0]                        # shape exponent
RECESSION_RATIOS = [1.5,  2.5,  4.0]                        # T_rec / T_peak

DT = 1   # minutes — fixed timestep for all cases

VEL_A = 1.5   # m/s per m^b  — coefficient in v = a * h^b
VEL_B = 0.5   # depth exponent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _depth_series(t_peak, h_peak, alpha, recession_ratio, dt):
    """Return (times_min, depths_m) for one hydrograph."""
    t_rec = t_peak * recession_ratio
    k = math.log(100.0) / max(t_rec, 1e-3)   # h → 1 % of peak at T_p + T_rec
    t_end = t_peak + t_rec + 3 * dt

    times, depths = [], []
    t = 0.0
    while t <= t_end + 0.5 * dt:
        if t <= t_peak:
            tau = t / t_peak if t_peak > 0 else 1.0
            h = h_peak * (tau ** alpha) * math.exp(alpha * (1.0 - tau))
        else:
            h = h_peak * math.exp(-k * (t - t_peak))
        times.append(round(t, 2))
        depths.append(round(max(0.0, h), 4))
        t += dt

    # guarantee a leading zero
    if depths[0] > 1e-6:
        times.insert(0, 0.0)
        depths.insert(0, 0.0)
    # trailing zero
    times.append(round(times[-1] + 5 * dt, 2))
    depths.append(0.0)
    return times, depths


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    here    = os.path.dirname(os.path.abspath(__file__))
    dep_dir = os.path.join(here, 'generated')
    os.makedirs(dep_dir, exist_ok=True)

    grid = list(itertools.product(
        H_PEAK_VALUES,
        T_PEAK_VALUES,
        ALPHA_VALUES,
        RECESSION_RATIOS,
    ))

    metadata = []

    for idx, (h_peak, t_peak, alpha, rec_ratio) in enumerate(grid):
        n = idx + 1

        times, depths = _depth_series(t_peak, h_peak, alpha, rec_ratio, DT)
        velocities = [round(VEL_A * (h ** VEL_B) if h > 0.0 else 0.0, 4)
                      for h in depths]

        fname = os.path.join(dep_dir, f'{n:04d}.csv')
        with open(fname, 'w', newline='') as f:
            f.write(
                f'# case {n:04d}'
                f'  h_peak={h_peak:.2f} m'
                f'  t_peak={t_peak} min'
                f'  alpha={alpha}'
                f'  rec_ratio={rec_ratio}\n'
            )
            f.write('# time (min), depth (m), velocity (m/s)\n')
            csv.writer(f).writerows(zip(times, depths, velocities))

        metadata.append({
            'case':            n,
            'h_peak':          h_peak,
            't_peak':          t_peak,
            'alpha':           alpha,
            'recession_ratio': rec_ratio,
            'n_steps':         len(times),
        })

    fields = list(metadata[0].keys())
    with open(os.path.join(here, 'metadata.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(metadata)

    print(f'Generated {len(grid)} cases  →  {dep_dir}')
    print(f'  h_peak stripes : {H_PEAK_VALUES}')
    print(f'  t_peak values  : {T_PEAK_VALUES} min')
    print(f'  alpha          : {ALPHA_VALUES}')
    print(f'  rec_ratio      : {RECESSION_RATIOS}')
    print(f'  velocity       : v = {VEL_A} * h^{VEL_B}  (fixed)')


if __name__ == '__main__':
    main()
