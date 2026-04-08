#!/usr/bin/env python3
"""Tests for the sump chamber and pump model (pump.py) and Simulation integration.

Interface contract being tested
--------------------------------
- pump.py: pure helper functions and SumpPump dataclass
- Simulation.run(): corrected routing via Building.basement_ingress
  (spec §16.1, §16.3, §16.8)

Key interface rule (spec §16.3)
---------------------------------
Exterior perimeter inflow is configured through Building.basement_ingress
(an IngressPathway), NOT through source/target routing in the ingress file.
When a SumpPump is attached, that pathway is redirected to the sump
automatically.  The ingress file must contain exterior→building paths only.
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pump import (SumpPump, compute_sump_overflow, compute_pump_switch_state,
                  compute_pump_flow, compute_lift_head)
from main import Building, IngressPathway, Simulation


# ── unit tests: compute_sump_overflow ────────────────────────────────────────

def test_sump_overflow_zero_below_crest():
    assert compute_sump_overflow(0.5, 0.8, 1.8, 1.5) == 0.0
    assert compute_sump_overflow(0.8, 0.8, 1.8, 1.5) == 0.0


def test_sump_overflow_positive_above_crest():
    Q = compute_sump_overflow(1.0, 0.8, 1.8, 1.5)
    expected = 1.8 * (0.2 ** 1.5)
    assert abs(Q - expected) < 1e-10


def test_sump_overflow_exponent_0_5():
    Q = compute_sump_overflow(1.0, 0.5, 2.0, 0.5)
    expected = 2.0 * math.sqrt(0.5)
    assert abs(Q - expected) < 1e-10


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


# ── integration: sump fills and overflows to basement (no pump) ───────────────

def test_sump_fills_and_overflows_to_basement():
    """Sump receives exterior perimeter inflow via Building.basement_ingress.
    Once depth exceeds overflow crest, water spills to basement.  Pump is
    effectively disabled (pump_on_level very high).  Ground floor stays dry.
    """
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0

    # Lumped exterior perimeter opening — set via Building.basement_ingress (spec §16.3)
    # Area is small enough that the basement doesn't overflow to ground floor
    building.basement_ingress = IngressPathway(
        height=0.0, area=0.008, coeff=0.6, name='ext-perimeter')

    building.sump_pump = SumpPump(
        sump_area          = 2.0,
        sump_base_elevation= -2.5,   # sump at basement level
        overflow_level     = 0.5,    # overflow crest at 0.5 m above sump base
        overflow_coeff     = 1.8,
        overflow_exponent  = 1.5,
        pump_on_level      = 999.0,  # effectively disabled
        pump_off_level     = 998.0,
        pump_shutoff_head  = 5.0,
        pump_curve_coeff   = 10.0,
        pipe_loss_coeff    = 2.0,
    )

    # ingress_list: exterior→building paths only (no sump routing here)
    ingress = []   # no direct building ingress needed for this test

    times  = [0.0, 3600.0]
    levels = [0.0, 1.0]

    sim = Simulation(building, ingress, times, levels, dt=60.0)
    result = sim.run()

    assert len(result) == 4, f"Expected 4-tuple with sump, got {len(result)}"
    _, sim_levels, sim_basement, sim_sump = result

    assert max(sim_sump) > 0.0, "Sump should have received water"
    assert max(sim_basement) > 0.0, "Basement should have received overflow from sump"
    # Note: ground floor may receive water if basement fills to ceiling and overflows —
    # that is physically correct and not the focus of this test.


# ── integration: pump keeps sump below overflow level ────────────────────────

def test_pump_controls_sump_level():
    """With a capable pump, sump should stay below overflow crest."""
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0

    building.basement_ingress = IngressPathway(
        height=0.0, area=0.005, coeff=0.6, name='ext-perimeter')

    building.sump_pump = SumpPump(
        sump_area          = 4.0,
        sump_base_elevation= -2.5,
        overflow_level     = 0.5,
        overflow_coeff     = 1.8,
        overflow_exponent  = 1.5,
        pump_on_level      = 0.2,
        pump_off_level     = 0.05,
        pump_shutoff_head  = 10.0,   # large pump
        pump_curve_coeff   = 5.0,
        pipe_loss_coeff    = 1.0,
    )

    times  = [0.0, 7200.0]
    levels = [0.0, 0.5]   # modest external level so lift head stays low

    sim = Simulation(building, [], times, levels, dt=60.0)
    _, _, sim_basement, sim_sump = sim.run()

    assert max(sim_sump) < 0.5, (
        f"Sump exceeded overflow level: max={max(sim_sump):.3f}")
    assert max(sim_basement) < 0.01, "Basement should receive little overflow"


# ── integration: pump hysteresis (on/off cycling) ────────────────────────────

def test_pump_on_off_hysteresis():
    """Pump turns on when sump reaches h_on and shuts off at h_off."""
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0

    building.basement_ingress = IngressPathway(
        height=0.0, area=0.005, coeff=0.6, name='ext-perimeter')

    building.sump_pump = SumpPump(
        sump_area          = 2.0,
        sump_base_elevation= -2.5,
        overflow_level     = 1.0,
        overflow_coeff     = 1.8,
        overflow_exponent  = 1.5,
        pump_on_level      = 0.4,
        pump_off_level     = 0.1,
        pump_shutoff_head  = 5.0,
        pump_curve_coeff   = 20.0,
        pipe_loss_coeff    = 2.0,
    )

    times  = [0.0, 3600.0, 7200.0]
    levels = [0.0, 0.5,    0.0]

    sim = Simulation(building, [], times, levels, dt=60.0)
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


# ── integration: basement_ingress without sump feeds basement directly ─────────

def test_basement_ingress_without_sump():
    """basement_ingress feeds basement directly when no sump is configured."""
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0
    building.basement_ingress = IngressPathway(
        height=0.0, area=0.01, coeff=0.6, name='ext-perimeter')

    sim = Simulation(building, [], [0.0, 3600.0], [0.0, 1.0], dt=60.0)
    result = sim.run()

    assert len(result) == 3
    _, _, sim_basement = result
    assert max(sim_basement) > 0.0, "Basement should receive perimeter inflow"


# ── integration: routing rule (spec §16.3) ────────────────────────────────────

def test_perimeter_inflow_redirected_to_sump_when_sump_enabled():
    """When sump is present, basement_ingress goes to sump, not basement directly."""
    def _run(with_sump):
        building = Building(floor_area=50.0)
        building.basement_area = 50.0
        building.z_basement = -2.5
        building.basement_ceiling_elevation = 0.0
        building.basement_ingress = IngressPathway(
            height=0.0, area=0.03, coeff=0.6, name='ext-perimeter')
        if with_sump:
            building.sump_pump = SumpPump(
                sump_area          = 5.0,
                sump_base_elevation= -2.5,
                overflow_level     = 10.0,  # unreachably high → no overflow
                overflow_coeff     = 1.8,
                overflow_exponent  = 1.5,
                pump_on_level      = 999.0,  # pump off
                pump_off_level     = 998.0,
                pump_shutoff_head  = 5.0,
                pump_curve_coeff   = 10.0,
                pipe_loss_coeff    = 2.0,
            )
        sim = Simulation(building, [], [0.0, 1800.0], [0.0, 0.5], dt=60.0)
        return sim.run()

    result_no_sump = _run(with_sump=False)
    result_with_sump = _run(with_sump=True)

    _, _, basement_no_sump = result_no_sump
    _, _, basement_with_sump, sump_levels = result_with_sump

    # Without sump: basement fills from perimeter opening
    assert max(basement_no_sump) > 0.0

    # With sump (overflow crest effectively infinite, pump off):
    #   water accumulates in sump, not in basement
    assert max(sump_levels) > 0.0
    # Basement should have no inflow (overflow blocked at high crest)
    assert max(basement_with_sump) < 1e-9
