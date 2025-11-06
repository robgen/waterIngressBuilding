import math

from main import IngressPathway, Simulation, Building


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
