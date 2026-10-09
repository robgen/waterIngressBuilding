"""Validation case studies: model inputs and the metrics recorded for each.

Single definition used by examples/make_reference.py (writes
examples/reference/exNN.json) and tests/test_regression.py (compares
against those files).  Every case runs through the public model API:
fragility.run_replicate for one-replicate cases, fragility.run for Monte Carlo.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine  # noqa: E402
import fragility as F  # noqa: E402
from pump import SumpPump  # noqa: E402


def hydro(points):
    """Hydrograph from (time_min, depth_m) points."""
    return engine.hydrograph_from_columns([t for t, _ in points], [h for _, h in points],
                                          time_units='minutes')


def triangle(peak):
    """Shared triangular flood: rise to `peak` at 30 min, dry by 60 min, end 360 min."""
    return hydro([(0, 0.0), (30, peak), (60, 0.0), (360, 0.0)])


TRI = triangle(0.50)
# Ex 05: 1.0 m flood held 30–240 min so the basement fills
LONG_05 = hydro([(0, 0.0), (30, 1.0), (240, 1.0), (270, 0.0), (360, 0.0)])

DT_6S = 0.1 * 60    # used for ex01/ex02 (matches run_examples.py)
DT_60S = 1.0 * 60   # default for the other cases

BASEMENT = dict(basement_area=30.0, basement_floor_elevation=-2.5)
BATCH_PEAKS = [round(0.10 + i * 0.05, 2) for i in range(20)]


def config(dt=DT_60S, **kw):
    return engine.SimConfig(floor_area=50.0, dt=dt, **kw)


def sump(curve_coeff):
    """0.5 m² pit, 0.8 m deep below the basement floor (−2.5 m)."""
    return SumpPump(
        sump_area=0.5, sump_base_elevation=-3.3,
        pump_on_level=0.10, pump_off_level=0.02,
        pump_shutoff_head=5.0, pump_curve_coeff=curve_coeff,
        pipe_loss_coeff=0.0, pump_availability=1.0,
    )


def path(name, height, area, cd=0.6, **kw):
    return F.FragilePath(name=name, height_m=height, area_m2=area, Cd=cd, **kw)


def membrane_row(median, beta):
    return path('membrane', 0.0, 1e-6, group_id=1, reversible=True,
                fragility=F.FragilityDefinition(states=[
                    F.FragilityState('overtopped', median, beta, 1e-9, 0.6)]))


def basement_model(*extra_ground):
    """Basement cases: no effective ground-floor opening + perimeter opening."""
    return F.assemble_pathways(
        [path('never_reached', 10.0, 0.001), *extra_ground],
        [path('ext_basement', 0.0, 0.005, 0.5)])


def membrane_model(median, beta):
    """Airbrick + door gap behind one membrane (group 1)."""
    return F.assemble_pathways(
        [path('airbrick', 0.1, 6e-3, group_id=1), path('door_gap', 0.0, 2e-3, group_id=1)],
        [], [membrane_row(median, beta)])


def run_one(cfg, hyd, model):
    paths, membranes = model
    result, _ = F.run_replicate(cfg, hyd, paths, membranes, np.random.default_rng(0))
    return result


def _mc_metrics(mc):
    pct = mc.percentiles
    return {
        'p10_peak_h_in': pct['peak_h_in']['P10'],
        'p50_peak_h_in': pct['peak_h_in']['P50'],
        'p90_peak_h_in': pct['peak_h_in']['P90'],
        'p50_total_volume_in': pct['total_volume_in']['P50'],
    }


def _depths(result, *keys):
    return {k: getattr(result, k) for k in keys}


# ── cases ─────────────────────────────────────────────────────────────────────

def ex01():
    r = run_one(config(DT_6S), TRI, F.assemble_pathways([path('door_gap', 0.0, 0.05)]))
    return _depths(r, 'peak_h_in')


def ex02():
    r = run_one(config(DT_6S), TRI, F.assemble_pathways([path('door_gap_raised', 0.3, 0.05)]))
    return _depths(r, 'peak_h_in')


def ex03():
    r = run_one(config(), TRI, F.assemble_pathways(
        [path('base_crack', 0.0, 0.001), path('door_gap_high', 0.3, 0.005)]))
    return _depths(r, 'peak_h_in')


def ex04():
    r = run_one(config(**BASEMENT), TRI, basement_model())
    return _depths(r, 'peak_h_in', 'peak_h_basement')


def ex05():
    r = run_one(config(**BASEMENT), LONG_05, basement_model())
    return _depths(r, 'peak_h_in', 'peak_h_basement')


def ex06():
    r = run_one(config(sumppump=sump(1000), **BASEMENT), TRI, basement_model())
    return _depths(r, 'peak_h_in', 'peak_h_basement', 'peak_h_sump')


def ex07():
    r = run_one(config(sumppump=sump(100000), **BASEMENT), TRI, basement_model())
    return _depths(r, 'peak_h_in', 'peak_h_basement', 'peak_h_sump')


def ex08():
    paths, membranes = F.assemble_pathways([path(
        'seal_door', 0.0, 1e-7, reversible=False,
        fragility=F.FragilityDefinition(states=[
            F.FragilityState('failed', 0.5, 0.3, 5e-3, 0.6)]))])
    return _mc_metrics(F.run(config(n_replicates=500, random_seed=42), TRI, paths, membranes))


def ex09():
    paths, membranes = membrane_model(median=0.5, beta=0.1)
    return _mc_metrics(F.run(config(n_replicates=500, random_seed=42), TRI, paths, membranes))


def ex10():
    paths, membranes = membrane_model(median=0.6, beta=0.0)
    return _mc_metrics(F.run(config(n_replicates=500, random_seed=42), TRI, paths, membranes))


def ex11_peaks():
    model = F.assemble_pathways([path('door_gap', 0.0, 0.05)])
    return [run_one(config(), triangle(p), model).peak_h_in for p in BATCH_PEAKS]


def ex11():
    peaks = ex11_peaks()
    return {
        'n_results':         len(peaks),
        'peak_h_int_at_h05': peaks[BATCH_PEAKS.index(0.50)],
        'peak_h_int_max':    max(peaks),
    }


def ex12():
    paths, membranes = membrane_model(median=0.5, beta=0.1)
    cfg = config(n_replicates=50, random_seed=42)
    total_reps, p50 = 0, {}
    for peak in BATCH_PEAKS:
        mc = F.run(cfg, triangle(peak), paths, membranes)
        total_reps += len(mc.replicates)
        sorted_h = sorted(r.result.peak_h_in for r in mc.replicates)
        p50[peak] = sorted_h[len(sorted_h) // 2]
    return {
        'n_results':             total_reps,
        'p50_peak_h_int_at_h05': p50[0.50],
        'p50_peak_h_int_at_h10': p50[1.00],
    }


CASES = {f.__name__: f for f in
         (ex01, ex02, ex03, ex04, ex05, ex06, ex07, ex08, ex09, ex10, ex11, ex12)}
