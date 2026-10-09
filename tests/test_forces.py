import math

import pytest

import forces

RHO, G, W = 1000.0, 9.81, 5.0
K = 0.5 * RHO * G * W


def test_dry_interior_is_full_exterior_triangle():
    F, M = forces.compute_hydrostatic_force(2.0, 0.0, W, rho=RHO, g=G)
    assert math.isclose(F, K * 2.0 ** 2, rel_tol=1e-12)
    assert math.isclose(M / F, 2.0 / 3.0, rel_tol=1e-12)


def test_water_both_sides_uses_difference_of_squares():
    # 0.5 m outside, 0.4 m inside on the same floor: the net pressure is
    # constant below the interior surface, so F = K (0.5² − 0.4²), not K (0.1)².
    F, _ = forces.compute_hydrostatic_force(0.5, 0.4, W, rho=RHO, g=G)
    assert math.isclose(F, K * (0.25 - 0.16), rel_tol=1e-12)


def test_equal_levels_on_same_datum_give_no_net_force():
    F, M = forces.compute_hydrostatic_force(0.5, 0.5, W, rho=RHO, g=G)
    assert F == 0.0 and M == 0.0


def test_raised_floor_leaves_net_force_at_equal_surfaces():
    # Floor 0.1 m above ground, interior surface level with the exterior:
    # the wall below the floor is loaded from outside only.
    F, M = forces.compute_hydrostatic_force(0.5, 0.4, W, floor_datum=0.1, rho=RHO, g=G)
    assert math.isclose(F, K * (0.25 - 0.16), rel_tol=1e-12)
    expected_M = K * (0.5 ** 3 / 3 - 0.4 ** 2 * (0.1 + 0.4 / 3))
    assert math.isclose(M, expected_M, rel_tol=1e-12)


def test_interior_higher_pushes_outward():
    F, _ = forces.compute_hydrostatic_force(0.1, 0.4, W, rho=RHO, g=G)
    assert F < 0.0


def test_drag_scales_with_v2():
    F1, _ = forces.compute_drag_force(1.5, 0.5, 4.0)
    F2, _ = forces.compute_drag_force(1.5, 1.0, 4.0)
    assert math.isclose(F2, 4.0 * F1, rel_tol=1e-9)


def test_combined_when_v_zero_reduces_to_hydro():
    res = forces.compute_combined_forces(0.8, 0.3, 0.0, W, floor_datum=0.1)
    F_h, M_h = forces.compute_hydrostatic_force(0.8, 0.3, W, floor_datum=0.1)
    assert res['F_drag'] == 0.0
    assert res['F_total'] == pytest.approx(F_h)
    assert res['M_overturn'] == pytest.approx(M_h)
    assert res['lever_hydro'] == pytest.approx(M_h / F_h)
