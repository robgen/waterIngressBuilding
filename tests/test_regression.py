"""Regression tests for all validation case studies.

Each test re-runs a case study programmatically and checks peak metrics against
the stored reference values in examples/reference/exNN.json.

Tolerances (from docs/model.md regression contract):
  - peak depths :  1 %  (rel), with 1e-5 m absolute floor for near-zero values
  - volumes     :  5 %  (rel), with 1e-8 m³ absolute floor

To update the reference files after a deliberate change:
    python3 examples/make_reference.py
"""

import json
import os
import sys

import pytest

HERE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.dirname(HERE)
REFDIR = os.path.join(ROOT, 'examples', 'reference')

sys.path.insert(0, ROOT)

from engine import Building, IngressPathway, Simulation
from pump import SumpPump
from fragility import (
    FragilityDefinition,
    FragilePath,
    FragilityState,
    Membrane,
    run_fragility_montecarlo,
)

# ── shared hydrograph (seconds) ───────────────────────────────────────────────
HYDRO_T = [t * 60 for t in [0.0, 30.0, 60.0, 360.0]]
HYDRO_H = [0.00, 0.50, 0.00, 0.00]

DT_6S  = 0.1 * 60   # 6 s  — used for ex01/ex02
DT_60S = 1.0 * 60   # 60 s — used for ex03-ex09


def _ref(name):
    path = os.path.join(REFDIR, f'{name}.json')
    if not os.path.exists(path):
        pytest.skip(f'reference file missing: {path}')
    with open(path) as f:
        return json.load(f)


def _building(floor=50.0):
    return Building(floor_area=floor)


def _approx_depth(ref_val):
    return pytest.approx(ref_val, rel=0.01, abs=1e-5)


def _approx_volume(ref_val):
    return pytest.approx(ref_val, rel=0.05, abs=1e-8)


# ── deterministic cases ───────────────────────────────────────────────────────

def test_ex01_single_opening():
    b = _building()
    ingress = [IngressPathway(height=0.0, area=0.05, coeff=0.6, name='door_gap')]
    _, h_in = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_6S).run()
    ref = _ref('ex01')
    assert max(h_in) == _approx_depth(ref['peak_h_in'])


def test_ex02_raised_sill():
    b = _building()
    ingress = [IngressPathway(height=0.3, area=0.05, coeff=0.6, name='door_gap_raised')]
    _, h_in = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_6S).run()
    ref = _ref('ex02')
    assert max(h_in) == _approx_depth(ref['peak_h_in'])


def test_ex03_two_openings():
    b = _building()
    ingress = [
        IngressPathway(height=0.0, area=0.001, coeff=0.6, name='base_crack'),
        IngressPathway(height=0.3, area=0.005, coeff=0.6, name='door_gap_high'),
    ]
    _, h_in = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_60S).run()
    ref = _ref('ex03')
    assert max(h_in) == _approx_depth(ref['peak_h_in'])


def test_ex04_basement():
    b = _building()
    b.basement_area = 30.0
    b.z_basement = -2.5
    b.basement_ingress = IngressPathway(
        height=0.0, area=0.005, coeff=0.5, name='ext_basement',
        source='outside', target='basement',
    )
    ingress = [IngressPathway(height=10.0, area=0.001, coeff=0.6, name='never_reached')]
    _, h_in, h_basement = Simulation(b, ingress, HYDRO_T, HYDRO_H, dt=DT_60S).run()
    ref = _ref('ex04')
    assert max(h_in) == _approx_depth(ref['peak_h_in'])
    assert max(h_basement) == _approx_depth(ref['peak_h_basement'])


def test_ex05_basement_pump_keeps_up():
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
    ref = _ref('ex05')
    assert max(h_in) == _approx_depth(ref['peak_h_in'])
    assert max(h_basement) == _approx_depth(ref['peak_h_basement'])
    assert max(h_sump) == _approx_depth(ref['peak_h_sump'])


def test_ex06_basement_pump_overwhelmed():
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
    ref = _ref('ex06')
    assert max(h_in) == _approx_depth(ref['peak_h_in'])
    assert max(h_basement) == _approx_depth(ref['peak_h_basement'])
    assert max(h_sump) == _approx_depth(ref['peak_h_sump'])


# ── fragility / Monte Carlo cases ─────────────────────────────────────────────

def test_ex07_fragility_single_path():
    paths = [
        FragilePath(
            name='seal_door', height_m=0.0, area_m2=1e-7, Cd=0.6, group_id=0,
            fragility=FragilityDefinition(states=[
                FragilityState(state_name='failed', median_m=0.5, beta_ln=0.3,
                               area_m2=5e-3, Cd=0.6),
            ]),
        ),
    ]
    result = run_fragility_montecarlo(
        building_factory=lambda: _building(),
        paths=paths,
        membranes=[],
        basement_fragility=None,
        external_times=HYDRO_T,
        external_levels=HYDRO_H,
        n_replicates=500,
        dt=DT_60S,
        seed=42,
    )
    ref = _ref('ex07')
    pct = result.percentiles
    assert pct['peak_h_in']['P10'] == _approx_depth(ref['p10_peak_h_in'])
    assert pct['peak_h_in']['P50'] == _approx_depth(ref['p50_peak_h_in'])
    assert pct['peak_h_in']['P90'] == _approx_depth(ref['p90_peak_h_in'])
    assert pct['total_volume_in']['P50'] == _approx_volume(ref['p50_total_volume_in'])


def test_ex08_fragility_membrane_group():
    paths = [
        FragilePath(name='airbrick', height_m=0.1, area_m2=6e-3, Cd=0.6, group_id=1),
        FragilePath(name='door_gap', height_m=0.0, area_m2=2e-3, Cd=0.6, group_id=1),
    ]
    membranes = [
        Membrane(
            group_id=1, height_m=0.0, area_m2=1e-6, Cd=0.6,
            fragility=FragilityDefinition(states=[
                FragilityState(state_name='overtopped', median_m=0.5, beta_ln=0.1,
                               area_m2=1e-9, Cd=0.6),
            ]),
        ),
    ]
    result = run_fragility_montecarlo(
        building_factory=lambda: _building(),
        paths=paths,
        membranes=membranes,
        basement_fragility=None,
        external_times=HYDRO_T,
        external_levels=HYDRO_H,
        n_replicates=500,
        dt=DT_60S,
        seed=42,
    )
    ref = _ref('ex08')
    pct = result.percentiles
    assert pct['peak_h_in']['P10'] == _approx_depth(ref['p10_peak_h_in'])
    assert pct['peak_h_in']['P50'] == _approx_depth(ref['p50_peak_h_in'])
    assert pct['peak_h_in']['P90'] == _approx_depth(ref['p90_peak_h_in'])
    assert pct['total_volume_in']['P50'] == _approx_volume(ref['p50_total_volume_in'])


BATCH_PEAKS = [round(0.10 + i * 0.05, 2) for i in range(20)]


def test_ex09_deterministic_membrane_no_failure():
    paths = [
        FragilePath(name='airbrick', height_m=0.1, area_m2=6e-3, Cd=0.6, group_id=1),
        FragilePath(name='door_gap', height_m=0.0, area_m2=2e-3, Cd=0.6, group_id=1),
    ]
    membranes = [
        Membrane(
            group_id=1, height_m=0.0, area_m2=1e-6, Cd=0.6,
            fragility=FragilityDefinition(states=[
                FragilityState(state_name='overtopped', median_m=0.6, beta_ln=0.0,
                               area_m2=1e-9, Cd=0.6),
            ]),
        ),
    ]
    result = run_fragility_montecarlo(
        building_factory=lambda: _building(),
        paths=paths,
        membranes=membranes,
        basement_fragility=None,
        external_times=HYDRO_T,
        external_levels=HYDRO_H,
        n_replicates=500,
        dt=DT_60S,
        seed=42,
    )
    ref = _ref('ex09')
    pct = result.percentiles
    assert pct['peak_h_in']['P10'] == _approx_depth(ref['p10_peak_h_in'])
    assert pct['peak_h_in']['P50'] == _approx_depth(ref['p50_peak_h_in'])
    assert pct['peak_h_in']['P90'] == _approx_depth(ref['p90_peak_h_in'])
    assert pct['total_volume_in']['P50'] == _approx_volume(ref['p50_total_volume_in'])


# ── batch cases ───────────────────────────────────────────────────────────────

def test_ex10_batch_deterministic():
    """20 hydrographs, deterministic: count, monotonic, known value at h_ext=0.5."""
    ingress = [IngressPathway(height=0.0, area=0.05, coeff=0.6, name='door_gap')]
    peak_h_ints = []
    for peak in BATCH_PEAKS:
        b = Building(floor_area=50.0)
        t = [0, 30 * 60, 60 * 60, 360 * 60]
        h = [0.0, peak, 0.0, 0.0]
        _, h_in = Simulation(b, ingress, t, h, dt=DT_60S).run()
        peak_h_ints.append(max(h_in))

    ref = _ref('ex10')
    assert len(peak_h_ints) == ref['n_results']
    assert all(peak_h_ints[i] <= peak_h_ints[i + 1]
               for i in range(len(peak_h_ints) - 1)), 'peak_h_int not monotonic'
    idx_05 = BATCH_PEAKS.index(0.50)
    assert peak_h_ints[idx_05] == _approx_depth(ref['peak_h_int_at_h05'])


def test_ex11_batch_mc_membrane():
    """20 hydrographs × 50 replicates with membrane: count, P50 at two h_ext levels."""
    paths = [
        FragilePath(name='airbrick', height_m=0.1, area_m2=6e-3, Cd=0.6, group_id=1),
        FragilePath(name='door_gap', height_m=0.0, area_m2=2e-3, Cd=0.6, group_id=1),
    ]
    membranes = [
        Membrane(
            group_id=1, height_m=0.0, area_m2=1e-6, Cd=0.6,
            fragility=FragilityDefinition(states=[
                FragilityState(state_name='overtopped', median_m=0.5,
                               beta_ln=0.1, area_m2=1e-9, Cd=0.6),
            ]),
        ),
    ]
    total_reps = 0
    p50_at_h05 = None
    p50_at_h10 = None
    for peak in BATCH_PEAKS:
        t = [0, 30 * 60, 60 * 60, 360 * 60]
        h = [0.0, peak, 0.0, 0.0]
        mc = run_fragility_montecarlo(
            building_factory=lambda: _building(),
            paths=paths,
            membranes=membranes,
            basement_fragility=None,
            external_times=t,
            external_levels=h,
            n_replicates=50,
            dt=DT_60S,
            seed=42,
        )
        total_reps += len(mc.replicates)
        sorted_h = sorted(r.peak_h_in for r in mc.replicates)
        p50 = sorted_h[len(sorted_h) // 2]
        if abs(peak - 0.50) < 1e-9:
            p50_at_h05 = p50
        if abs(peak - 1.00) < 1e-9:
            p50_at_h10 = p50

    ref = _ref('ex11')
    assert total_reps == ref['n_results']
    assert p50_at_h05 == _approx_depth(ref['p50_peak_h_int_at_h05'])
    assert p50_at_h10 == _approx_depth(ref['p50_peak_h_int_at_h10'])
