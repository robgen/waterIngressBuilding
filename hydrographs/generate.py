#!/usr/bin/env python3
"""
Generate 100 synthetic flood hydrographs (depth + velocity).

Physical basis
--------------
Hydrograph shape: gamma-type rising limb + exponential recession (SCS-like).

  Rising  : h(t) = h_peak * (t/T_p)^α * exp(α*(1 - t/T_p))
            → zero at t=0, monotonically increasing, peaks exactly at T_p
  Recession: h(t) = h_peak * exp(-k*(t - T_p))
            → k chosen so h drops to 1 % of peak at t = T_p + T_rec

Three flood types (Brunner et al. 2017, WRR doi:10.1002/2016WR019535):
  40 flash/urban  T_peak  30 – 240 min   dt = 5 min
  40 short-rain   T_peak 240 – 1440 min  dt = 15 min
  20 prolonged    T_peak 1440 – 7200 min dt = 60 min

Peak depths: log-normal, median 0.5 m, σ_ln = 0.75
  (DEFRA FD2320; EA Surface Water risk map thresholds 0.2–1.2 m)

Velocities: V_peak = C · h_peak^β  (Manning-type scatter)
  C  ~ Uniform(0.3, 1.5),  β ~ Uniform(0.40, 0.70)
  (Kreibich et al. 2009, NHESS doi:10.5194/nhess-9-1679-2009)
  Velocity peaks 0–20 % earlier than depth (lead_ratio).

References
----------
Brunner MI et al. (2017) WRR 53:3427–3446
DEFRA/EA (2003) Flood Hazard Ratings FD2320/FD2321
Kreibich H et al. (2009) NHESS 9:1679–1692
UK Surface Water risk map depth thresholds (Environment Agency)
"""

import csv
import math
import os
import random

SEED = 42
random.seed(SEED)

try:
    import numpy as np
    np.random.seed(SEED)
    _HAS_NP = True
except ImportError:
    _HAS_NP = False


# ── sampling helpers ──────────────────────────────────────────────────────────

def _lognormal(median, sigma_ln):
    if _HAS_NP:
        return float(np.random.lognormal(math.log(median), sigma_ln))
    u1 = max(1e-12, random.random())
    u2 = random.random()
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    return math.exp(math.log(median) + sigma_ln * z)


def _loguniform(lo, hi):
    return math.exp(random.uniform(math.log(lo), math.log(hi)))


def _u(lo, hi):
    return random.uniform(lo, hi)


# ── hydrograph constructors ───────────────────────────────────────────────────

def _depth_series(t_peak, h_peak, alpha, recession_ratio, dt):
    """Return (times_min, depths_m) lists."""
    t_rec = t_peak * recession_ratio
    k = math.log(100.0) / max(t_rec, 1e-3)   # h → 1 % at t_peak + t_rec
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

    # guarantee leading and trailing zeros
    if depths[0] > 1e-6:
        times.insert(0, 0.0)
        depths.insert(0, 0.0)
    times.append(round(times[-1] + 5 * dt, 2))
    depths.append(0.0)
    return times, depths


def _velocity_series(depth_times, depth_vals, v_peak, lead_ratio,
                     alpha_v, recession_ratio_v):
    """Return (times_min, velocities_m_s) on the same time-base as depth."""
    t_depth_peak = depth_times[depth_vals.index(max(depth_vals))]
    t_vel_peak = max(depth_times[1], t_depth_peak * (1.0 - lead_ratio))
    t_rec = t_vel_peak * recession_ratio_v
    k = math.log(100.0) / max(t_rec, 1e-3)

    vels = []
    for t in depth_times:
        if t <= t_vel_peak:
            tau = t / t_vel_peak if t_vel_peak > 0 else 1.0
            v = v_peak * (tau ** alpha_v) * math.exp(alpha_v * (1.0 - tau))
        else:
            v = v_peak * math.exp(-k * (t - t_vel_peak))
        vels.append(round(max(0.0, v), 4))
    return depth_times, vels


# ── parameter sampling ────────────────────────────────────────────────────────

def _sample(flood_type):
    if flood_type == 'flash':
        t_peak          = _loguniform(30, 240)
        recession_ratio = _u(1.2, 2.0)
        dt              = 5
    elif flood_type == 'short':
        t_peak          = _loguniform(240, 1440)
        recession_ratio = _u(1.5, 3.5)
        dt              = 15
    else:  # prolonged
        t_peak          = _loguniform(1440, 7200)
        recession_ratio = _u(2.0, 6.0)
        dt              = 60

    h_peak = max(0.05, min(2.50, _lognormal(0.50, 0.75)))
    alpha  = _u(1.5, 4.0)

    # velocity: Manning-type  V = C * h^beta
    v_peak = max(0.05, min(5.0, _u(0.3, 1.5) * h_peak ** _u(0.40, 0.70)))

    return dict(
        flood_type      = flood_type,
        t_peak          = round(t_peak,          2),
        h_peak          = round(h_peak,          3),
        alpha           = round(alpha,           3),
        recession_ratio = round(recession_ratio, 3),
        dt              = dt,
        v_peak          = round(v_peak,          3),
        lead_ratio      = round(_u(0.00, 0.20),  3),
        alpha_v         = round(_u(1.2,  3.5),   3),
        recession_ratio_v = round(recession_ratio * _u(0.8, 1.2), 3),
    )


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    here     = os.path.dirname(os.path.abspath(__file__))
    dep_dir  = os.path.join(here, 'depth')
    vel_dir  = os.path.join(here, 'velocity')
    os.makedirs(dep_dir, exist_ok=True)
    os.makedirs(vel_dir, exist_ok=True)

    types = ['flash'] * 40 + ['short'] * 40 + ['prolonged'] * 20
    random.shuffle(types)

    metadata = []

    for idx, ftype in enumerate(types):
        n   = idx + 1
        p   = _sample(ftype)
        metadata.append({'case': n, **p})

        t_d, h_d = _depth_series(
            p['t_peak'], p['h_peak'], p['alpha'], p['recession_ratio'], p['dt'])

        t_v, v_v = _velocity_series(
            t_d, h_d, p['v_peak'], p['lead_ratio'],
            p['alpha_v'], p['recession_ratio_v'])

        # depth file
        with open(os.path.join(dep_dir, f'depth_{n:03d}.csv'), 'w', newline='') as f:
            f.write(f'# Synthetic flood depth hydrograph — case {n:03d}\n')
            f.write(f'# type={ftype}  T_peak={p["t_peak"]:.1f} min'
                    f'  h_peak={p["h_peak"]:.3f} m'
                    f'  alpha={p["alpha"]:.3f}'
                    f'  recession_ratio={p["recession_ratio"]:.3f}\n')
            f.write('# time (min), depth (m)\n')
            csv.writer(f).writerows(zip(t_d, h_d))

        # velocity file
        with open(os.path.join(vel_dir, f'velocity_{n:03d}.csv'), 'w', newline='') as f:
            f.write(f'# Synthetic flood velocity hydrograph — case {n:03d}\n')
            f.write(f'# type={ftype}  V_peak={p["v_peak"]:.3f} m/s'
                    f'  lead_ratio={p["lead_ratio"]:.3f}'
                    f'  alpha_v={p["alpha_v"]:.3f}'
                    f'  recession_ratio_v={p["recession_ratio_v"]:.3f}\n')
            f.write('# time (min), velocity (m/s)\n')
            csv.writer(f).writerows(zip(t_v, v_v))

    # metadata
    fields = list(metadata[0].keys())
    with open(os.path.join(here, 'metadata.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(metadata)

    print(f'Generated {len(types)} cases → {here}')


if __name__ == '__main__':
    main()
