from engine import IngressPathway, Simulation, Building


def test_compute_flow_increases_with_velocity():
    ing = IngressPathway(height=0.0, area=0.1, coeff=1.0)
    H_source = 0.5
    H_target = 0.0
    q_no_v = ing.compute_flow(H_source, H_target, v_source=0.0)
    q_with_v = ing.compute_flow(H_source, H_target, v_source=1.0)
    assert abs(q_with_v) >= abs(q_no_v)
    # direction should remain the same (source higher than target)
    assert q_with_v > 0 and q_no_v > 0


def test_velocity_padding_in_simulation():
    # external hydrograph constant elevated level
    times = [0.0, 60.0, 120.0]
    levels = [1.0, 1.0, 1.0]
    # a large opening so flows produce observable level changes
    ingress = [IngressPathway(height=-1.0, area=0.5, coeff=1.0, name='big')]

    # case A: velocity defined across full period (constant 1.0)
    v_times_full = [0.0, 60.0, 120.0]
    v_vals_full = [1.0, 1.0, 1.0]
    sim_full = Simulation(Building(10.0), ingress, times, levels, dt=60.0, external_vel_times=v_times_full, external_velocities=v_vals_full)
    ret_full = sim_full.run()
    if isinstance(ret_full, tuple) and len(ret_full) == 3:
        t_full, h_full, _ = ret_full
    else:
        t_full, h_full = ret_full

    # case B: velocity only provided at t=0 (should be padded with zeros afterwards)
    v_times_short = [0.0]
    v_vals_short = [1.0]
    sim_short = Simulation(Building(10.0), ingress, times, levels, dt=60.0, external_vel_times=v_times_short, external_velocities=v_vals_short)
    ret_short = sim_short.run()
    if isinstance(ret_short, tuple) and len(ret_short) == 3:
        t_short, h_short, _ = ret_short
    else:
        t_short, h_short = ret_short

    # final indoor level with full velocity should be higher than padded-short velocity
    assert h_full[-1] >= h_short[-1]


# ── velocity head only when the source water reaches the sill ────────────────
# Regression: the velocity head v²/2g was added even when the exterior water
# was below the sill, so a dry floor level with the sill (H_target == sill)
# drew water in from velocity alone, and a flowing street below the sill
# blocked or reversed drainage of indoor water above it.

def test_no_inflow_from_velocity_when_water_below_sill():
    ing = IngressPathway(height=0.10, area=0.01, coeff=0.6)
    # street 9 cm below the sill, dry floor exactly at the sill
    assert ing.compute_flow(0.01, 0.10, v_source=0.15) == 0.0
    assert ing.compute_flow(0.01, 0.10, v_source=3.0) == 0.0


def test_velocity_does_not_block_drainage_below_sill():
    ing = IngressPathway(height=0.10, area=0.01, coeff=0.6)
    # indoor water 5 cm above the sill, street below the sill: outflow,
    # whatever the street velocity
    q_still = ing.compute_flow(0.05, 0.15, v_source=0.0)
    q_moving = ing.compute_flow(0.05, 0.15, v_source=1.0)
    assert q_still < 0.0
    assert q_moving == q_still


def test_velocity_head_applies_once_water_reaches_sill():
    ing = IngressPathway(height=0.10, area=0.01, coeff=0.6)
    assert ing.compute_flow(0.11, 0.10, v_source=1.0) > ing.compute_flow(0.11, 0.10, v_source=0.0) > 0.0


def test_event_below_sill_leaves_floor_dry():
    """0.01 m flood (hydrographs/generated/0001.csv) against an opening at the
    floor datum (0.10 m): no water enters with any velocity mode."""
    import os
    import engine

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'hydrographs', 'generated', '0001.csv')
    for mode in ('zero', 'file', 'power_law'):
        config = engine.SimConfig(floor_area=50.0, dt=60.0, floor_datum=0.10,
                                  velocity_mode=mode)
        hydro = engine.read_hydrograph(path, time_units='minutes', velocity_mode=mode)
        result = engine.run(config, hydro, [IngressPathway(0.10, 0.01, 0.6, 'crack')])
        assert result.peak_h_ext == 0.01
        assert result.peak_h_in == 0.0, mode
