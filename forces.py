"""Analytical hydrostatic and hydrodynamic force calculators.

Lateral forces on the flow-facing façade (width W), per unit time step.
Elevations are measured from external ground (z = 0); the interior floor is
at z = floor_datum.  Forces are positive when they push the wall inward and
moments are taken about external ground level.

All formulas are closed-form analytical expressions only (no numerical
integration is used). Functions expect SI units: metres, seconds, kg.
"""


def compute_hydrostatic_force(h_ext, h_in, building_width, floor_datum=0.0,
                              rho=1000.0, g=9.81):
    """Net hydrostatic force and moment on the façade.

    Exterior water presses on the wall from z = 0 up to h_ext; interior water
    presses back from the floor (z = floor_datum) up to floor_datum + h_in.
    Integrating both hydrostatic distributions:

        F = ½ ρ g W (h_ext² − h_in²)
        M = ½ ρ g W [h_ext³/3 − h_in² (floor_datum + h_in/3)]

    Args:
        h_ext: exterior water depth above external ground (m).
        h_in: interior water depth above the floor (m).
        building_width: horizontal extent of the flow-facing façade (m).
        floor_datum: floor elevation above external ground (m).
        rho: fluid density (kg/m³).
        g: gravitational acceleration (m/s²).

    Returns:
        (F_hydro, M_hydro): net force (N, negative when the interior water
        pushes outward) and its moment about external ground (N·m).
    """
    if building_width <= 0.0:
        return 0.0, 0.0
    h_e = max(0.0, h_ext)
    h_i = max(0.0, h_in)
    k = 0.5 * rho * g * building_width
    F = k * (h_e ** 2 - h_i ** 2)
    M = k * (h_e ** 3 / 3.0 - h_i ** 2 * (floor_datum + h_i / 3.0))
    return F, M


def compute_drag_force(h_ext, v, building_width, C_D=1.0, rho=1000.0):
    """Steady hydrodynamic drag on the wetted façade area.

    F = ½ ρ C_D v² W h_ext, acting at h_ext/2.

    Args:
        h_ext: exterior water depth above external ground (m).
        v: exterior velocity (m/s), assumed orthogonal to the façade.
        building_width: horizontal extent of the façade (m).
        C_D: drag coefficient (–).
        rho: fluid density (kg/m³).

    Returns:
        (F_drag, M_drag): force (N) and its moment about external ground (N·m).
    """
    h_e = max(0.0, h_ext)
    if h_e <= 0.0 or building_width <= 0.0 or v == 0.0:
        return 0.0, 0.0
    F = 0.5 * rho * C_D * (v ** 2) * building_width * h_e
    return F, F * h_e / 2.0


def compute_combined_forces(h_ext, h_in, v, building_width, floor_datum=0.0,
                            C_D=1.0, rho=1000.0, g=9.81):
    """Hydrostatic + drag force and total overturning moment on the façade.

    Returns:
        dict with keys F_hydro, F_drag, F_total (N), M_overturn (N·m) and
        lever_hydro, lever_drag (m above external ground; 0 when the force is 0).
    """
    F_hydro, M_hydro = compute_hydrostatic_force(
        h_ext, h_in, building_width, floor_datum=floor_datum, rho=rho, g=g)
    F_drag, M_drag = compute_drag_force(h_ext, v, building_width, C_D=C_D, rho=rho)
    return {
        'F_hydro': F_hydro,
        'F_drag': F_drag,
        'F_total': F_hydro + F_drag,
        'M_overturn': M_hydro + M_drag,
        'lever_hydro': M_hydro / F_hydro if F_hydro != 0.0 else 0.0,
        'lever_drag': M_drag / F_drag if F_drag != 0.0 else 0.0,
    }
