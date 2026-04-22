import math

from engine import Simulation, Building, IngressPathway, sample_with_zero_padding


def test_zero_padding_on_sim_times():
    # simple external hydrograph spanning 0..120
    times = [0.0, 60.0, 120.0]
    levels = [0.0, 0.0, 0.0]
    ingress = [IngressPathway(height=-1.0, area=0.1, coeff=1.0)]

    # velocity only provided at t=0 -> should be padded with zeros later
    v_times = [0.0]
    v_vals = [1.0]

    sim = Simulation(Building(10.0), ingress, times, levels, dt=60.0, external_vel_times=[t for t in v_times], external_velocities=[v for v in v_vals])
    sim_ret = sim.run()
    if isinstance(sim_ret, tuple) and len(sim_ret) == 3:
        sim_times, _, _ = sim_ret
    else:
        sim_times, _ = sim_ret

    sampled = sample_with_zero_padding(sim_times, [t for t in v_times], [v for v in v_vals])
    # last sampled value (at or after 120) should be zero due to padding
    assert abs(sampled[-1] - 0.0) < 1e-12


def test_linear_interpolation_between_points():
    # check interpolation behaviour between two velocity samples
    target = [0.0, 30.0, 60.0]
    src_times = [0.0, 60.0]
    src_vals = [0.0, 2.0]
    sampled = sample_with_zero_padding(target, src_times, src_vals)
    # at t=30 we expect 1.0 (midpoint)
    assert abs(sampled[1] - 1.0) < 1e-12
