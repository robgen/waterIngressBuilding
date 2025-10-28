import math

from main import Building, IngressPathway, Simulation


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
