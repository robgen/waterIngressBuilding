import math
import forces


def test_hydrostatic_force_basic():
    H = 2.0
    W = 5.0
    rho = 1000.0
    g = 9.81
    F_h, lever = forces.compute_hydrostatic_force(H, W, rho=rho, g=g)
    # analytical value
    expected = 0.5 * rho * g * (H ** 2) * W
    assert math.isclose(F_h, expected, rel_tol=1e-9)
    assert math.isclose(lever, H / 3.0, rel_tol=1e-12)


def test_drag_scales_with_v2():
    H_wet = 1.5
    W = 4.0
    v1 = 0.5
    v2 = 1.0
    F1, _ = forces.compute_drag_force(H_wet, v1, W, C_D=1.0, rho=1000.0)
    F2, _ = forces.compute_drag_force(H_wet, v2, W, C_D=1.0, rho=1000.0)
    # because drag ~ v^2, F2 should be approximately (v2/v1)^2 times F1
    ratio = (v2 / v1) ** 2
    assert math.isclose(F2, F1 * ratio, rel_tol=1e-9)


def test_combined_when_v_zero_reduces_to_hydro():
    H_net = 0.8
    H_wet = 1.2
    v = 0.0
    W = 3.0
    res = forces.compute_combined_forces(H_net, H_wet, v, W, C_D=1.0, rho=1000.0)
    F_h_expected, lever_h = forces.compute_hydrostatic_force(H_net, W)
    assert math.isclose(res['F_hydro'], F_h_expected, rel_tol=1e-9)
    assert math.isclose(res['F_drag'], 0.0, abs_tol=1e-12)
    assert math.isclose(res['F_total'], F_h_expected, rel_tol=1e-9)
