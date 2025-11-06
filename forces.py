"""Analytical hydrostatic and hydrodynamic force calculators.

All formulas are closed-form analytical expressions only (no numerical
integration is used). Functions expect SI units: metres, seconds, kg.
"""

def compute_hydrostatic_force(H, building_width, rho=1000.0, g=9.81):
    """Compute hydrostatic resultant force on a vertical planar facade.

    Args:
        H: net hydrostatic depth (m). This is the net outside-minus-inside
           depth used for pressure (use max(0, h_out - h_in)).
        building_width: horizontal extent of the flow-facing facade (m).
        rho: fluid density (kg/m^3).
        g: gravitational acceleration (m/s^2).

    Returns:
        F_hydro: resultant hydrostatic force (N).
        lever_arm: vertical distance from base to force resultant (m) = H/3.
    """
    if H <= 0.0 or building_width <= 0.0:
        return 0.0, 0.0
    F_hydro = 0.5 * rho * g * (H ** 2) * building_width
    lever = H / 3.0
    return F_hydro, lever


def compute_drag_force(H_wet, v, building_width, C_D=1.0, rho=1000.0):
    """Compute steady hydrodynamic drag force on the wetted facade area.

    Args:
        H_wet: external wetted height (m) (use max(0, h_out) if datum=0).
        v: external velocity (m/s), assumed orthogonal to the facade.
        building_width: horizontal extent of facade (m).
        C_D: drag coefficient (dimensionless).
        rho: fluid density (kg/m^3).

    Returns:
        F_drag: steady drag force (N).
        lever_arm: centroid location for drag moment (m) = H_wet/2.
    """
    if H_wet <= 0.0 or building_width <= 0.0 or v == 0.0:
        return 0.0, 0.0
    A = building_width * H_wet
    F_drag = 0.5 * rho * C_D * (v ** 2) * A
    lever = H_wet / 2.0
    return F_drag, lever


def compute_combined_forces(H_net, H_wet, v, building_width, C_D=1.0, rho=1000.0, g=9.81):
    """Compute combined lateral force and overturning moment.

    Args:
        H_net: net hydrostatic depth (m) = max(0, h_out - h_in).
        H_wet: external wetted height (m) = max(0, h_out) (basement excluded).
        v: external velocity (m/s).
        building_width: facade horizontal extent (m).
        C_D: drag coefficient.
        rho: fluid density.
        g: gravitational acceleration (unused here but kept for signature parity).

    Returns:
        dict with keys: F_hydro, F_drag, F_total, M_overturn, lever_hydro, lever_drag
    """
    F_hydro, lever_hydro = compute_hydrostatic_force(H_net, building_width, rho=rho, g=g)
    F_drag, lever_drag = compute_drag_force(H_wet, v, building_width, C_D=C_D, rho=rho)
    F_total = F_hydro + F_drag
    # Overturning moment about base: hydrostatic at H/3, drag at H/2
    M_overturn = F_hydro * lever_hydro + F_drag * lever_drag
    return {
        'F_hydro': F_hydro,
        'F_drag': F_drag,
        'F_total': F_total,
        'M_overturn': M_overturn,
        'lever_hydro': lever_hydro,
        'lever_drag': lever_drag,
    }
