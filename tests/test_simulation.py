import math
import os
import tempfile
import pytest

from damage import VulnerabilityCurve, load_vulnerability_curve
from main import Building, IngressPathway, Simulation, parse_ingress_text


def test_no_ingress_no_change():
    building = Building(floor_area=50.0)
    ingress = []
    times = [0.0, 60.0, 120.0]
    levels = [0.0, 0.5, 1.0]

    sim = Simulation(building, ingress, times, levels, dt=10.0)
    sim_times, sim_levels = sim.run()

    # With no ingress, indoor level should remain at initial 0.0 throughout
    assert all(abs(h - 0.0) < 1e-12 for h in sim_levels)


def test_dt_convergence():
    # Simple hydrograph and a single ingress at floor level so flow occurs
    ingress = [IngressPathway(height=0.0, area=0.05, coeff=1.0, name='test')]
    times = [0.0, 60.0, 120.0]
    levels = [0.0, 1.0, 2.0]

    # run with coarse, medium and fine timesteps
    sim_coarse = Simulation(Building(50.0), ingress, times, levels, dt=60.0)
    t_coarse, h_coarse = sim_coarse.run()

    sim_medium = Simulation(Building(50.0), ingress, times, levels, dt=10.0)
    t_med, h_med = sim_medium.run()

    sim_fine = Simulation(Building(50.0), ingress, times, levels, dt=1.0)
    t_fine, h_fine = sim_fine.run()

    final_coarse = h_coarse[-1]
    final_med = h_med[-1]
    final_fine = h_fine[-1]

    # results should be finite numbers
    assert math.isfinite(final_coarse)
    assert math.isfinite(final_med)
    assert math.isfinite(final_fine)

    # convergence heuristic: the fine and medium results should be closer
    # than medium and coarse results (i.e. reducing dt moves result closer)
    diff_med_fine = abs(final_med - final_fine)
    diff_coarse_med = abs(final_coarse - final_med)

    assert diff_med_fine <= diff_coarse_med + 1e-8


def test_vulnerability_curve_interpolation_and_clamping():
    curve = VulnerabilityCurve(
        heights_m=[0.0, 0.5, 1.0],
        losses=[1000.0, 2000.0, 5000.0],
    )

    assert curve.interpolate_loss(-0.1) == 1000.0
    assert curve.interpolate_loss(1.2) == 5000.0
    assert abs(curve.interpolate_loss(0.25) - 1500.0) < 1e-9
    assert abs(curve.interpolate_loss(0.75) - 3500.0) < 1e-9


def test_load_vulnerability_curve_averages_duplicate_heights():
    fd, path = tempfile.mkstemp(suffix='.csv')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write('height_m,mean_repair_loss_GBP\n')
            f.write('0.0,1000\n')
            f.write('0.5,2000\n')
            f.write('0.5,3000\n')
            f.write('1.0,6000\n')

        curve = load_vulnerability_curve(path)

        assert curve.heights_m == (0.0, 0.5, 1.0)
        assert curve.losses == (1000.0, 2500.0, 6000.0)
        assert abs(curve.interpolate_loss(0.75) - 4250.0) < 1e-9
    finally:
        os.remove(path)


def test_parse_ingress_text_rejects_routing_columns():
    with pytest.raises(ValueError):
        parse_ingress_text("0.0, 0.01, 0.6, crack, outside, basement")
