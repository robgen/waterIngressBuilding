#!/usr/bin/env python3
"""Tests for the sump chamber and pump model (pump.py) and Simulation integration.

Interface contract being tested
--------------------------------
- pump.py: pure helper functions and SumpPump dataclass
- Simulation.run(): routing of outside→basement pathways and the sump pit

Routing rule
------------
Exterior perimeter inflow is an IngressPathway with source='outside',
target='basement' in the Simulation ingress list.  When a SumpPump is
attached, such pathways discharge into the sump pit instead of the basement.
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pump import (SumpPump, compute_pump_switch_state,
                  compute_pump_flow, compute_lift_head)
from engine import Building, IngressPathway, Simulation


# ── unit tests: pit geometry ─────────────────────────────────────────────────

def _pit(base=-3.0, on=0.2, off=0.05):
    return SumpPump(sump_area=1.0, sump_base_elevation=base, pump_on_level=on,
                    pump_off_level=off, pump_shutoff_head=5.0, pump_curve_coeff=10.0,
                    pipe_loss_coeff=0.0)


def test_sump_depth_is_basement_floor_minus_base():
    assert _pit(base=-3.0).depth(-2.5) == pytest.approx(0.5)


def test_sump_base_must_be_below_basement_floor():
    with pytest.raises(ValueError, match="below the basement floor"):
        _pit(base=-2.5).check_geometry(-2.5)


def test_pump_on_level_above_pit_top_warns():
    with pytest.warns(UserWarning, match="spilled"):
        _pit(base=-2.6, on=0.2).check_geometry(-2.5)


# ── unit tests: compute_pump_switch_state ────────────────────────────────────

def test_pump_turns_on_at_h_on():
    assert compute_pump_switch_state(0.3, 0.3, 0.1, 0) == 1


def test_pump_turns_off_at_h_off():
    assert compute_pump_switch_state(0.1, 0.3, 0.1, 1) == 0


def test_pump_hysteresis_keeps_on():
    assert compute_pump_switch_state(0.2, 0.3, 0.1, 1) == 1


def test_pump_hysteresis_keeps_off():
    assert compute_pump_switch_state(0.2, 0.3, 0.1, 0) == 0


# ── unit tests: compute_lift_head ─────────────────────────────────────────────

def test_lift_head_positive():
    assert abs(compute_lift_head(1.5, -2.5) - 4.0) < 1e-10


def test_lift_head_clamped_to_zero():
    # External level below sump base → no lift (non-return valve)
    assert compute_lift_head(-1.0, 0.0) == 0.0


# ── unit tests: compute_pump_flow ────────────────────────────────────────────

def test_pump_flow_off_returns_zero():
    assert compute_pump_flow(0, 1.0, 5.0, 1.0, 10.0, 2.0) == 0.0


def test_pump_flow_shutoff_le_lift_returns_zero():
    assert compute_pump_flow(1, 1.0, 1.0, 1.5, 10.0, 2.0) == 0.0


def test_pump_flow_correct_q_star():
    expected = math.sqrt(4.0 / 12.0)
    Q = compute_pump_flow(1, 1.0, 5.0, 1.0, 10.0, 2.0)
    assert abs(Q - expected) < 1e-10


def test_pump_flow_availability_scales():
    Q_full = compute_pump_flow(1, 1.0, 5.0, 1.0, 10.0, 2.0)
    Q_half = compute_pump_flow(1, 0.5, 5.0, 1.0, 10.0, 2.0)
    assert abs(Q_half - 0.5 * Q_full) < 1e-10


def test_pump_flow_no_negative_sqrt():
    Q = compute_pump_flow(1, 1.0, 5.0, 1.0, 0.0, 0.0)
    assert Q == 0.0


# ── integration: pit fills and spills onto the basement floor (no pump) ──────

def test_sump_fills_and_overflows_to_basement():
    """Sump receives exterior perimeter inflow from an outside→basement pathway.
    Once the pit is full (top at the basement floor), water spills onto the
    basement floor.  Pump is
    effectively disabled (pump_on_level very high).  Ground floor stays dry.
    """
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0

    # Lumped exterior perimeter opening
    # Area is small enough that the basement doesn't overflow to ground floor
    bsmt = IngressPathway(
        height=0.0, area=0.008, coeff=0.6, name='ext-perimeter',
        source='outside', target='basement')

    building.sump_pump = SumpPump(
        sump_area          = 2.0,
        sump_base_elevation= -3.0,   # pit 0.5 m deep below the floor
        pump_on_level      = 999.0,  # effectively disabled
        pump_off_level     = 998.0,
        pump_shutoff_head  = 5.0,
        pump_curve_coeff   = 10.0,
        pipe_loss_coeff    = 2.0,
    )

    # ingress_list: exterior→building paths only (no sump routing here)
    ingress = [bsmt]   # perimeter only; no direct building ingress

    times  = [0.0, 3600.0]
    levels = [0.0, 1.0]

    sim = Simulation(building, ingress, times, levels, dt=60.0)
    result = sim.run()

    assert len(result) == 4, f"Expected 4-tuple with sump, got {len(result)}"
    _, sim_levels, sim_basement, sim_sump = result

    assert max(sim_sump) > 0.0, "Sump should have received water"
    assert max(sim_sump) == pytest.approx(0.5), "Pit should fill to the basement floor"
    assert max(sim_basement) > 0.0, "Basement should have received the spill"
    # Note: ground floor may receive water if basement fills to ceiling and overflows —
    # that is physically correct and not the focus of this test.


# ── integration: pump keeps the pit from filling ─────────────────────────────

def test_pump_controls_sump_level():
    """With a capable pump, the pit should never fill to the basement floor."""
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0

    bsmt = IngressPathway(
        height=0.0, area=0.005, coeff=0.6, name='ext-perimeter',
        source='outside', target='basement')

    building.sump_pump = SumpPump(
        sump_area          = 4.0,
        sump_base_elevation= -3.0,   # pit 0.5 m deep below the floor
        pump_on_level      = 0.2,
        pump_off_level     = 0.05,
        pump_shutoff_head  = 10.0,   # large pump
        pump_curve_coeff   = 5.0,
        pipe_loss_coeff    = 1.0,
    )

    times  = [0.0, 7200.0]
    levels = [0.0, 0.5]   # modest external level so lift head stays low

    sim = Simulation(building, [bsmt], times, levels, dt=60.0)
    _, _, sim_basement, sim_sump = sim.run()

    assert max(sim_sump) < 0.5, (
        f"Pit filled: max={max(sim_sump):.3f}")
    assert max(sim_basement) < 0.01, "Basement should receive little spill"


# ── integration: pump hysteresis (on/off cycling) ────────────────────────────

def test_pump_on_off_hysteresis():
    """Pump turns on when sump reaches h_on and shuts off at h_off."""
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0

    bsmt = IngressPathway(
        height=0.0, area=0.005, coeff=0.6, name='ext-perimeter',
        source='outside', target='basement')

    building.sump_pump = SumpPump(
        sump_area          = 2.0,
        sump_base_elevation= -3.5,   # pit 1.0 m deep below the floor
        pump_on_level      = 0.4,
        pump_off_level     = 0.1,
        pump_shutoff_head  = 5.0,
        pump_curve_coeff   = 20.0,
        pipe_loss_coeff    = 2.0,
    )

    times  = [0.0, 3600.0, 7200.0]
    levels = [0.0, 0.5,    0.0]

    sim = Simulation(building, [bsmt], times, levels, dt=60.0)
    _, _, _, sim_sump = sim.run()

    peak_idx = sim_sump.index(max(sim_sump))
    assert peak_idx > 0, "Sump should rise before falling"
    assert sim_sump[-1] < sim_sump[peak_idx], "Sump should decrease after pump activates"


# ── integration: no sump → 2/3-tuple return unchanged ────────────────────────

def test_no_sump_returns_two_tuple():
    building = Building(floor_area=50.0)
    ingress = [IngressPathway(height=0.0, area=0.01, coeff=0.6, name='crack')]
    sim = Simulation(building, ingress, [0.0, 60.0], [0.0, 0.5], dt=10.0)
    result = sim.run()
    assert len(result) == 2


def test_basement_no_sump_returns_three_tuple():
    building = Building(floor_area=50.0)
    building.basement_area = 20.0
    building.z_basement = -2.0
    building.basement_ceiling_elevation = 0.0
    ingress = [IngressPathway(height=0.0, area=0.01, coeff=0.6, name='crack')]
    sim = Simulation(building, ingress, [0.0, 60.0], [0.0, 0.5], dt=10.0)
    result = sim.run()
    assert len(result) == 3


# ── integration: perimeter pathway without sump feeds basement directly ───────

def test_perimeter_pathway_without_sump_feeds_basement():
    """An outside→basement pathway feeds the basement when no sump is configured."""
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0
    bsmt = IngressPathway(
        height=0.0, area=0.01, coeff=0.6, name='ext-perimeter',
        source='outside', target='basement')

    sim = Simulation(building, [bsmt], [0.0, 3600.0], [0.0, 1.0], dt=60.0)
    result = sim.run()

    assert len(result) == 3
    _, _, sim_basement = result
    assert max(sim_basement) > 0.0, "Basement should receive perimeter inflow"


# ── integration: routing rule ─────────────────────────────────────────────────

def test_perimeter_inflow_redirected_to_sump_when_sump_enabled():
    """When a sump is present, outside→basement pathways go to the sump pit."""
    def _run(with_sump):
        building = Building(floor_area=50.0)
        building.basement_area = 50.0
        building.z_basement = -2.5
        building.basement_ceiling_elevation = 0.0
        bsmt = IngressPathway(
            height=0.0, area=0.03, coeff=0.6, name='ext-perimeter',
            source='outside', target='basement')
        if with_sump:
            building.sump_pump = SumpPump(
                sump_area          = 10.0,   # 100 m³ pit: never fills here
                sump_base_elevation= -12.5,   # pit 10.0 m deep below the floor
                pump_on_level      = 999.0,  # pump off
                pump_off_level     = 998.0,
                pump_shutoff_head  = 5.0,
                pump_curve_coeff   = 10.0,
                pipe_loss_coeff    = 2.0,
            )
        sim = Simulation(building, [bsmt], [0.0, 1800.0], [0.0, 0.5], dt=60.0)
        return sim.run()

    result_no_sump = _run(with_sump=False)
    result_with_sump = _run(with_sump=True)

    _, _, basement_no_sump = result_no_sump
    _, _, basement_with_sump, sump_levels = result_with_sump

    # Without sump: basement fills from perimeter opening
    assert max(basement_no_sump) > 0.0

    # With sump (100 m³ pit, never fills; pump off):
    #   water accumulates in sump, not in basement
    assert max(sump_levels) > 0.0
    # Basement should have no inflow (the pit never spills)
    assert max(basement_with_sump) < 1e-9


# ── integration: basement water drains back into the pit ─────────────────────

def test_pump_drains_basement_through_pit():
    """After the flood, basement water drains into the pit and is pumped out."""
    building = Building(floor_area=50.0)
    building.basement_area = 30.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0
    bsmt = IngressPathway(height=0.0, area=0.005, coeff=0.5, name='ext-perimeter',
                          source='outside', target='basement')
    building.sump_pump = SumpPump(
        sump_area=0.5, sump_base_elevation=-3.3,
        pump_on_level=0.10, pump_off_level=0.02,
        pump_shutoff_head=5.0, pump_curve_coeff=100000, pipe_loss_coeff=0.0)

    sim = Simulation(building, [bsmt], [0.0, 1800.0, 3600.0, 9000.0],
                     [0.0, 0.5, 0.0, 0.0], dt=60.0)
    _, _, sim_basement, sim_sump = sim.run()
    trace = sim._last_trace

    assert max(sim_basement) > 0.1, "Weak pump: basement should flood"
    assert sim_basement[-1] == 0.0, "Pump should drain the basement through the pit"
    assert max(trace['Q_b_sump']) > 0.0, "Basement water should drain into the pit"



# ── integration step check for the pump ──────────────────────────────────────

def _pump_config(dt, **sump_kw):
    import engine
    sp = dict(sump_area=0.5, sump_base_elevation=-3.3, pump_on_level=0.10,
              pump_off_level=0.02, pump_shutoff_head=5.0, pump_curve_coeff=1000,
              pipe_loss_coeff=0.0)
    sp.update(sump_kw)
    return engine.SimConfig(floor_area=50.0, dt=dt, basement_area=30.0,
                            basement_floor_elevation=-2.5, sumppump=SumpPump(**sp))


def _hydro():
    import engine
    return engine.hydrograph_from_columns([0, 10, 20], [0.0, 0.5, 0.0])


def test_max_stable_dt_is_half_switch_on_volume_at_zero_lift():
    sp = _pump_config(1.0).sumppump
    q_max = math.sqrt(5.0 / 1000.0)            # η_p · √(H_shut / (k_pump + k_pipe))
    assert sp.max_pump_flow() == pytest.approx(q_max)
    assert sp.max_stable_dt() == pytest.approx(0.5 * 0.5 * 0.10 / q_max)


def test_max_stable_dt_infinite_when_pump_delivers_nothing():
    assert _pump_config(1.0, pump_availability=0.0).sumppump.max_stable_dt() == math.inf


def test_warns_when_step_too_large_for_pump():
    import engine
    with pytest.warns(engine.PumpStepWarning, match=r"Use Δt ≤ .* = 0\.354 s"):
        engine.run(_pump_config(60.0), _hydro())


def test_no_warning_when_step_is_stable_or_no_pump():
    import warnings
    import engine
    with warnings.catch_warnings():
        warnings.simplefilter('error', engine.PumpStepWarning)
        engine.run(_pump_config(0.3), _hydro())
        engine.run(engine.SimConfig(floor_area=50.0, dt=60.0, basement_area=30.0,
                                    basement_floor_elevation=-2.5), _hydro())
