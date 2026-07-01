#!/usr/bin/env python3
"""Generate reference metric JSONs for all validation case studies.

Run from the repo root:
    python3 examples/make_reference.py

Overwrites examples/reference/exNN.json with current simulation output.
Commit the resulting files; tests/test_regression.py compares against them.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import Building, IngressPathway, Simulation
from pump import SumpPump
from fragility import (
    BasementFragility,
    FragilityDefinition,
    FragilePath,
    FragilityState,
    Membrane,
    run_fragility_montecarlo,
)

REFDIR = os.path.join(HERE, 'reference')
os.makedirs(REFDIR, exist_ok=True)

# Shared triangular hydrograph — times in seconds (Simulation always uses seconds)
# Original definition is in minutes: 0, 30, 60, 360 → multiply by 60
HYDRO_T = [t * 60 for t in [0.0, 30.0, 60.0, 360.0]]
HYDRO_H = [0.00, 0.50, 0.00, 0.00]

# Timesteps in seconds
DT_6S  = 0.1 * 60   # 6 s  (used for ex01/02 to match run_examples.py)
DT_60S = 1.0 * 60   # 60 s (default for ex03-09)


def _save(name, metrics):
    path = os.path.join(REFDIR, f'{name}.json')
    with open(path, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f'  wrote {name}.json  {metrics}')


def _building(floor=50.0):
    return Building(floor_area=floor)


# ── Ex 01: single opening, sill = 0 ──────────────────────────────────────────
print('ex01 – single opening, sill = 0 m')
b = _building()
ingress = [IngressPathway(height=0.0, area=0.05, coeff=0.6, name='door_gap')]
_, h_in = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_6S).run()
_save('ex01', {'peak_h_in': max(h_in)})

# ── Ex 02: raised sill ────────────────────────────────────────────────────────
print('ex02 – raised sill, sill = 0.3 m')
b = _building()
ingress = [IngressPathway(height=0.3, area=0.05, coeff=0.6, name='door_gap_raised')]
_, h_in = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_6S).run()
_save('ex02', {'peak_h_in': max(h_in)})

# ── Ex 03: two openings ───────────────────────────────────────────────────────
print('ex03 – two openings')
b = _building()
ingress = [
    IngressPathway(height=0.0, area=0.001, coeff=0.6, name='base_crack'),
    IngressPathway(height=0.3, area=0.005, coeff=0.6, name='door_gap_high'),
]
_, h_in = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_60S).run()
_save('ex03', {'peak_h_in': max(h_in)})

# ── Ex 04: basement compartment ───────────────────────────────────────────────
print('ex04 – basement compartment')
b = _building()
b.basement_area = 30.0
b.z_basement = -2.5
b.basement_ingress = IngressPathway(
    height=0.0, area=0.005, coeff=0.5, name='ext_basement',
    source='outside', target='basement',
)
ingress = [IngressPathway(height=10.0, area=0.001, coeff=0.6, name='never_reached')]
_, h_in, h_basement = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_60S).run()
_save('ex04', {'peak_h_in': max(h_in), 'peak_h_basement': max(h_basement)})

# ── Ex 05: basement + sump/pump (keeps up) ────────────────────────────────────
print('ex05 – basement + strong sump/pump')
b = _building()
b.basement_area = 30.0
b.z_basement = -2.5
b.basement_ingress = IngressPathway(
    height=0.0, area=0.005, coeff=0.5, name='ext_basement',
    source='outside', target='basement',
)
b.sump_pump = SumpPump(
    sump_area=0.5, sump_base_elevation=-2.5,
    overflow_level=0.8, overflow_coeff=1.8, overflow_exponent=1.5,
    pump_on_level=0.10, pump_off_level=0.02,
    pump_shutoff_head=5.0, pump_curve_coeff=1000,
    pipe_loss_coeff=0.0, pump_availability=1.0,
)
ingress = [IngressPathway(height=10.0, area=0.001, coeff=0.6, name='never_reached')]
_, h_in, h_basement, h_sump = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_60S).run()
_save('ex05', {
    'peak_h_in': max(h_in),
    'peak_h_basement': max(h_basement),
    'peak_h_sump': max(h_sump),
})

# ── Ex 06: basement + sump/pump (overwhelmed) ─────────────────────────────────
print('ex06 – basement + weak sump/pump (overwhelmed)')
b = _building()
b.basement_area = 30.0
b.z_basement = -2.5
b.basement_ingress = IngressPathway(
    height=0.0, area=0.005, coeff=0.5, name='ext_basement',
    source='outside', target='basement',
)
b.sump_pump = SumpPump(
    sump_area=0.5, sump_base_elevation=-2.5,
    overflow_level=0.8, overflow_coeff=1.8, overflow_exponent=1.5,
    pump_on_level=0.10, pump_off_level=0.02,
    pump_shutoff_head=5.0, pump_curve_coeff=100000,
    pipe_loss_coeff=0.0, pump_availability=1.0,
)
ingress = [IngressPathway(height=10.0, area=0.001, coeff=0.6, name='never_reached')]
_, h_in, h_basement, h_sump = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_60S).run()
_save('ex06', {
    'peak_h_in': max(h_in),
    'peak_h_basement': max(h_basement),
    'peak_h_sump': max(h_sump),
})

# ── Ex 07: fragility MC – single probabilistic path ───────────────────────────
print('ex07 – fragility MC, single path, 500 replicates')
paths_07 = [
    FragilePath(
        name='seal_door', height_m=0.0, area_m2=1e-7, Cd=0.6, group_id=0,
        fragility=FragilityDefinition(states=[
            FragilityState(state_name='failed', median_m=0.5, beta_ln=0.3, area_m2=5e-3, Cd=0.6),
        ]),
        reversible=False,  # door seal: physically irreversible failure
    ),
]
result_07 = run_fragility_montecarlo(
    building_factory=lambda: _building(),
    paths=paths_07,
    membranes=[],
    basement_fragility=None,
    external_times=HYDRO_T,
    external_levels=HYDRO_H,
    n_replicates=500,
    dt=DT_60S,
    seed=42,
)
pct_07 = result_07.percentiles
_save('ex07', {
    'p10_peak_h_in': pct_07['peak_h_in']['P10'],
    'p50_peak_h_in': pct_07['peak_h_in']['P50'],
    'p90_peak_h_in': pct_07['peak_h_in']['P90'],
    'p50_total_volume_in': pct_07['total_volume_in']['P50'],
})

# ── Ex 08: fragility MC – membrane-protected group ────────────────────────────
print('ex08 – fragility MC, membrane group, 500 replicates')
paths_08 = [
    FragilePath(name='airbrick', height_m=0.1, area_m2=6e-3, Cd=0.6, group_id=1),
    FragilePath(name='door_gap', height_m=0.0, area_m2=2e-3, Cd=0.6, group_id=1),
]
membranes_08 = [
    Membrane(
        group_id=1, height_m=0.0, area_m2=1e-6, Cd=0.6,
        fragility=FragilityDefinition(states=[
            FragilityState(state_name='overtopped', median_m=0.5, beta_ln=0.1, area_m2=1e-9, Cd=0.6),
        ]),
        reversible=True,  # flood membrane: overtopping-type, reversible
    ),
]
result_08 = run_fragility_montecarlo(
    building_factory=lambda: _building(),
    paths=paths_08,
    membranes=membranes_08,
    basement_fragility=None,
    external_times=HYDRO_T,
    external_levels=HYDRO_H,
    n_replicates=500,
    dt=DT_60S,
    seed=42,
)
pct_08 = result_08.percentiles
_save('ex08', {
    'p10_peak_h_in': pct_08['peak_h_in']['P10'],
    'p50_peak_h_in': pct_08['peak_h_in']['P50'],
    'p90_peak_h_in': pct_08['peak_h_in']['P90'],
    'p50_total_volume_in': pct_08['total_volume_in']['P50'],
})

# ── Ex 09: deterministic membrane (design capacity above flood peak) ───────────
print('ex09 – deterministic membrane, no failure expected')
paths_09 = paths_08  # same airbrick + door_gap behind membrane group 1
membranes_09 = [
    Membrane(
        group_id=1, height_m=0.0, area_m2=1e-6, Cd=0.6,
        fragility=FragilityDefinition(states=[
            FragilityState(state_name='overtopped', median_m=0.6, beta_ln=0.0, area_m2=1e-9, Cd=0.6),
        ]),
        reversible=True,  # flood membrane: overtopping-type, reversible
    ),
]
result_09 = run_fragility_montecarlo(
    building_factory=lambda: _building(),
    paths=paths_09,
    membranes=membranes_09,
    basement_fragility=None,
    external_times=HYDRO_T,
    external_levels=HYDRO_H,
    n_replicates=500,
    dt=DT_60S,
    seed=42,
)
pct_09 = result_09.percentiles
_save('ex09', {
    'p10_peak_h_in': pct_09['peak_h_in']['P10'],
    'p50_peak_h_in': pct_09['peak_h_in']['P50'],
    'p90_peak_h_in': pct_09['peak_h_in']['P90'],
    'p50_total_volume_in': pct_09['total_volume_in']['P50'],
})

# ── Ex 10: batch deterministic (20 hydrographs) ───────────────────────────────
print('ex10 – batch deterministic, 20 hydrographs')
BATCH_PEAKS = [round(0.10 + i * 0.05, 2) for i in range(20)]
ingress_10 = [IngressPathway(height=0.0, area=0.05, coeff=0.6, name='door_gap')]

peak_h_ints_10 = []
for peak in BATCH_PEAKS:
    b = _building()
    hydro_t_b = [0, 30 * 60, 60 * 60, 360 * 60]
    hydro_h_b = [0.0, peak, 0.0, 0.0]
    _, h_in = Simulation(b, ingress_10, hydro_t_b, hydro_h_b, dt=DT_60S).run()
    peak_h_ints_10.append(max(h_in))

idx_05 = BATCH_PEAKS.index(0.50)
_save('ex10', {
    'n_results':          len(BATCH_PEAKS),
    'peak_h_int_at_h05':  peak_h_ints_10[idx_05],
    'peak_h_int_max':     max(peak_h_ints_10),
})

# ── Ex 11: batch + fragility MC (20 hydrographs × 50 replicates) ─────────────
print('ex11 – batch + fragility MC, 20 × 50 = 1 000 replicates')
paths_11 = [
    FragilePath(name='airbrick', height_m=0.1, area_m2=6e-3, Cd=0.6, group_id=1),
    FragilePath(name='door_gap', height_m=0.0, area_m2=2e-3, Cd=0.6, group_id=1),
]
membranes_11 = [
    Membrane(
        group_id=1, height_m=0.0, area_m2=1e-6, Cd=0.6,
        fragility=FragilityDefinition(states=[
            FragilityState(state_name='overtopped', median_m=0.5,
                           beta_ln=0.1, area_m2=1e-9, Cd=0.6),
        ]),
        reversible=True,  # flood membrane: overtopping-type, reversible
    ),
]

total_reps_11 = 0
p50_at_h05_11 = None
p50_at_h10_11 = None

for peak in BATCH_PEAKS:
    hydro_t_b = [0, 30 * 60, 60 * 60, 360 * 60]
    hydro_h_b = [0.0, peak, 0.0, 0.0]
    mc = run_fragility_montecarlo(
        building_factory=lambda: _building(),
        paths=paths_11,
        membranes=membranes_11,
        basement_fragility=None,
        external_times=hydro_t_b,
        external_levels=hydro_h_b,
        n_replicates=50,
        dt=DT_60S,
        seed=42,
    )
    total_reps_11 += len(mc.replicates)
    sorted_h = sorted(r.peak_h_in for r in mc.replicates)
    p50 = sorted_h[len(sorted_h) // 2]
    if abs(peak - 0.50) < 1e-9:
        p50_at_h05_11 = p50
    if abs(peak - 1.00) < 1e-9:
        p50_at_h10_11 = p50

_save('ex11', {
    'n_results':              total_reps_11,
    'p50_peak_h_int_at_h05':  p50_at_h05_11,
    'p50_peak_h_int_at_h10':  p50_at_h10_11,
})

print('\nDone. Reference files written to', REFDIR)
