"""Full-basement surcharge: basement and ground floor act as one compartment.

When the basement (and sump) is full to the ceiling and there is water above
the ground floor, exterior→basement pathways discharge against the
ground-floor level.  Checks:
  - the indoor level never exceeds the exterior peak (plus velocity head);
  - water is conserved at every step, across the switch into and out of the
    merged state, with and without a sump/pump;
  - the merged state is actually entered and left in these cases.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import engine  # noqa: E402
from engine import IngressPathway  # noqa: E402
from pump import SumpPump  # noqa: E402

G = 9.81
BASEMENT = dict(basement_area=30.0, basement_floor_elevation=-2.5)
MAX_BSMT = 2.5


def _airbrick_case(velocity_mode='zero'):
    """Strong airbricks into the basement, tight above-ground openings,
    long event (hydrographs/generated/0212.csv: 1.5 m peak, ~56 h)."""
    config = engine.SimConfig(floor_area=50.0, dt=60.0, velocity_mode=velocity_mode,
                              **BASEMENT)
    hydro = engine.read_hydrograph(
        os.path.join(ROOT, 'hydrographs', 'generated', '0212.csv'),
        time_units='minutes', velocity_mode=velocity_mode)
    pathways = [
        IngressPathway(0.0, 1e-4, 0.6, 'door_gap'),
        IngressPathway(0.0, 6e-3 / 0.6, 0.6, 'airbricks', 'outside', 'basement'),
    ]
    return config, hydro, pathways


def _fill_and_drain_case(sumppump=None, bypass=False):
    """Basement fills under a 1.0 m flood held 30–360 min, then the ground
    floor drains back out through a door gap after the flood recedes."""
    config = engine.SimConfig(
        floor_area=50.0, dt=6.0, sumppump=sumppump,
        basement_connection_height=0.0 if bypass else None,
        basement_connection_area=0.002 if bypass else 0.0,
        **BASEMENT)
    hydro = engine.hydrograph_from_columns(
        [0, 30, 360, 390, 720], [0.0, 1.0, 1.0, 0.0, 0.0], time_units='minutes')
    pathways = [
        IngressPathway(0.0, 0.002, 0.6, 'door_gap'),
        IngressPathway(0.0, 0.005, 0.5, 'perimeter', 'outside', 'basement'),
    ]
    return config, hydro, pathways


def _weak_pump():
    return SumpPump(
        sump_area=0.5, sump_base_elevation=-2.5,
        overflow_level=0.8, overflow_coeff=1.8, overflow_exponent=1.5,
        pump_on_level=0.10, pump_off_level=0.02,
        pump_shutoff_head=5.0, pump_curve_coeff=100000,
        pipe_loss_coeff=0.0, pump_availability=1.0,
    )


def _stored(config, result, k):
    """Water stored indoors after step k: ground floor + basement + sump."""
    v = result.h_in[k] * config.floor_area
    sp = config.sumppump
    if sp is None:
        return v + result.h_basement[k] * config.basement_area
    return (v + sp.sump_area * min(result.h_sump[k], sp.overflow_level)
            + (sp.sump_area + config.basement_area) * result.h_basement[k])


def _merged_steps(result):
    return [hb >= MAX_BSMT and hi > 0.0 for hb, hi in zip(result.h_basement, result.h_in)]


@pytest.mark.parametrize('velocity_mode', ['zero', 'file'])
def test_indoor_level_bounded_by_exterior(velocity_mode):
    config, hydro, pathways = _airbrick_case(velocity_mode)
    result = engine.run(config, hydro, pathways)
    _, v_ext = engine.exterior_series(config, hydro, result.times)
    bound = result.peak_h_ext + max(v_ext) ** 2 / (2 * G)
    assert max(result.h_basement) == pytest.approx(MAX_BSMT)       # basement filled
    assert result.peak_h_in + config.floor_datum <= bound + 1e-3


@pytest.mark.parametrize('sumppump,bypass', [(None, False), (None, True),
                                             (_weak_pump(), False)],
                         ids=['basement', 'basement+bypass', 'basement+sump'])
def test_mass_balance_across_merged_switches(sumppump, bypass):
    config, hydro, pathways = _fill_and_drain_case(sumppump, bypass)
    result = engine.run(config, hydro, pathways)
    tr = result.trace

    merged = _merged_steps(result)
    assert any(merged), 'merged state never entered'
    assert any(a and not b for a, b in zip(merged, merged[1:])), 'merged state never left'

    net_in = 0.0
    for k in range(len(result.times)):
        net_in += (tr['Q_ext_b'][k] + tr['Q_ext_perimeter'][k] - tr['Q_pump'][k]) * config.dt
        assert _stored(config, result, k) == pytest.approx(net_in, rel=1e-9, abs=1e-9), k


def test_indoor_level_bounded_when_ground_floor_has_no_opening():
    """Case 05 geometry: the merged compartment fills towards the exterior level."""
    config = engine.SimConfig(floor_area=50.0, dt=60.0, **BASEMENT)
    hydro = engine.hydrograph_from_columns(
        [0, 30, 240, 270, 360], [0.0, 1.0, 1.0, 0.0, 0.0], time_units='minutes')
    result = engine.run(config, hydro, [
        IngressPathway(0.0, 0.005, 0.5, 'perimeter', 'outside', 'basement')])
    assert result.peak_h_in <= 1.0 + 1e-3
