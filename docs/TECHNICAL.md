# Technical description — flood ingress formulation

This document describes the simplified hydraulic model used in the simulation, the numerical scheme, assumptions and limitations.

Symbols and units

- $t$ — time (s)
- $h_{out}(t)$ — external water level (m)
- $h_{in}(t)$ — indoor water level (m)
- $A_i$ — opening area for ingress pathway $i$ (m^2)
- $z_i$ — sill/entry height for ingress pathway $i$ (m)
- $C_i$ — discharge coefficient for ingress pathway $i$ (dimensionless)
- $g$ — gravitational acceleration (9.81 m/s^2)
- $V(t)$ — water volume inside the building (m^3)
- $S$ — building floor plan area (m^2)

Ingress discharge

Each ingress pathway is treated as an orifice-like opening. If both exterior and interior water levels are below the opening sill, there is no flow. Otherwise the instantaneous volumetric flow rate through opening $i$ is computed as:

$$
Q_i(t) = \mathrm{sign}(\Delta h(t)) C_i A_i \sqrt{2 g |\Delta h(t)|}
$$

where

$$
\Delta h(t) = h_{out}(t) - h_{in}(t).
$$

The sign indicates flow direction: positive when water flows from outside to inside (i.e. $h_{out} > h_{in}$).

Building mass balance

The volume change inside the building over a timestep is the integral of net inflow:

$$
\frac{dV}{dt} = \sum_i Q_i(t).
$$

We convert volume to water depth (uniform over the floor) with the building floor area $S$:

$$
h_{in}(t) = \frac{V(t)}{S}.
$$

Numerical integration

The simulator uses a fixed-step explicit Euler scheme with a user-specified timestep $\Delta t$ (CLI `--dt` or Streamlit UI field). For simulation step index $n$ (time $t_n$) we compute:

1. Sample (or linearly interpolate) the external level to get $h_{out}(t_n)$.
2. For each ingress compute instantaneous flow $Q_i(t_n)$ using the formula above.
3. Update the internal volume (Euler forward):

$$
V_{n+1} = V_n + \left(\sum_i Q_i(t_n)\right) \Delta t.
$$

4. Update indoor depth:

$$
h_{in, n+1} = \max\left(0, \frac{V_{n+1}}{S}\right).
$$

Stability and timestep selection

The explicit Euler scheme is conditionally stable in the sense that smaller $\Delta t$ reduces numerical integration error. There is no CFL condition here tied to wave propagation; however, choose $\Delta t$ small enough to capture the dynamics of short-lived flows (e.g., sudden step increases in $h_{out}$).

Assumptions and limitations

- The model treats each ingress independently and ignores complex hydraulic interactions such as flow through multiple chained compartments, inertia, or entrapped air effects.
- The discharge formula is a simplified orifice-like approximation and may not be accurate for all opening geometries.
- Water is assumed to spread uniformly across the floor area S; vertical storage above furnishings, two-level buildings, and internal drainage are not modelled.
- Evaporation, infiltration into substrates, pumps, and active mitigation are not represented.

Suggested improvements (future work)

- Add a semi-implicit integration scheme to improve stability with larger timesteps.
- Model multiple compartments and internal routing/path losses.
- Calibrate discharge coefficients $C_i$ to experimental data or CFD results for more accurate predictions.

Including external flow velocity (hydrodynamic correction)

Useful reference: https://nhess.copernicus.org/articles/9/1679/2009/nhess-9-1679-2009.pdf

This section describes a conservative, lightweight extension to account for external water velocity (flood flow) that influences infiltration through openings. The goal is to capture two coupled effects with a simple correction:

- dynamic (stagnation) pressure that increases the effective head on the flow-facing side; and
- velocity-driven forcing that can push water into small gaps even when the hydrostatic depth is small.

Model additions and conventions

- External velocity: a time series (hydrograph) v_out(t) in m/s, given at the same timestamps style as the external level hydrograph. If not provided, the model will assume a conservative default constant velocity v0 = 0.2 m/s.
- Units: velocity in m/s, heights in m, time units follow the CLI `--time-units` convention. The gravitational constant g = 9.81 m/s^2 is used as before.
- Conservative placement: for simplicity we assume all ingress paths are on the flow-facing facade and thus are affected by the external velocity. This is conservative for risk assessment; if you have site-specific exposure (e.g., openings on a sheltered face) extend the ingress definitions to include orientation.

Effective head for velocity-augmented flow

We approximate the additional effect of kinetic energy (dynamic pressure) as an equivalent head term. The effective head difference used in the orifice formula becomes

$$
\Delta h_{\mathrm{eff}}(t) = h_{\mathrm{out}}(t) + \frac{v_{\mathrm{out}}(t)^2}{2g} - h_{\mathrm{in}}(t).
$$

This expression adds the dynamic head $v^2/(2g)$ to the external water level before computing the orifice flow. The orifice/discharge equation is otherwise unchanged, i.e.

$$
Q_i(t) = \operatorname{sign}(\Delta h_{\mathrm{eff}})\; C_i A_i \sqrt{2 g |\Delta h_{\mathrm{eff}}|}.
$$

Submerged test and sign

- To preserve the conservative 'sill' behaviour used elsewhere in the model we retain the existing submerged test: if both sides are below the opening sill height $z_i$ (i.e. $h_{\mathrm{out}} < z_i$ and $h_{\mathrm{in}} < z_i$), then $Q_i=0$. Note that the submerged test uses raw levels (not the dynamic-head-augmented level). The rationale is that the opening must be physically submerged to allow free flow; the velocity correction increases the local driving head once the opening is submerged on at least one side.
- The sign of $Q_i$ follows $\operatorname{sign}(h_{\mathrm{source}} + v^2/(2g) - h_{\mathrm{target}})$; when a connection is ground→basement we use the analogous expression with source/target roles.

Implementation notes (numerical)

- Interpolation: v_out(t) should be interpolated to the simulation time grid the same way the external level is interpolated. When no velocity hydrograph is supplied use the constant default v0.
- Units and dt: since the dynamic term contains v^2 and g, ensure v is in m/s and g in m/s^2; dt remains in the user-selected time units (converted to seconds internally as before). The product Q*dt yields volume as before.

Limitations and caveats

- This is a first-order correction that approximates dynamic pressure as an equivalent head; it does not replace a full hydrodynamic CFD treatment of flow around structures, wave impact, or transient pressure spikes.
- Using the dynamic head term is conservative for flow-driven infiltration but does not model additional effects such as boundary-layer pumping or turbulence-enhanced infiltration through porous materials.
- If continuous leakage below the sill is desired (small seepage even when both sides below the sill), model that with an additional small-area connection at a low sill or use a small explicit leakage pathway.

## Hydrostatic and hydrodynamic forces (engineering outputs)

This section documents the analytical, closed-form expressions used to estimate lateral forces and overturning moments on flow-facing building façades. The project uses only analytical formulas (closed-form expressions) for these quantities — no numerical integration approaches are used or referenced here.

Assumptions and conventions

- Forces are computed only for flow-facing façades (conservative assumption unless facade orientation is specified). The external velocity used in hydrodynamic calculations is assumed to be orthogonal to the flow-facing building wall.
- Building width: the horizontal extent of the flow-facing façade exposed to the flood. The term "building width" is used throughout (not "wall width").
- Fluid density: use ρ = 1000 kg/m^3 unless overridden.
- Gravity: g = 9.81 m/s^2.
- Drag coefficient: a default conservative value C_D = 1.0 is recommended; this may be adjusted with site-specific data.
- Wetted height H is the vertical depth of water against the façade measured from the base reference used for moment calculations. For a uniformly wetted vertical face, the closed-form expressions below apply directly.
- Basement compartments are excluded from facade lateral force calculations (they are handled in mass-balance and storage calculations only).

Hydrostatic lateral force (analytical expression)

For a vertical, planar, flow-facing façade with uniform wetted depth H (m) and building width W (m), the resultant hydrostatic force acting horizontally on that façade is the closed-form expression:

F_hydro = 0.5 * ρ * g * H^2 * W

This is the standard resultant for a hydrostatic pressure distribution on a vertical face. The line of action (resultant centroid) is located at H/3 above the base (i.e., one-third of the wetted height measured from the base).

Hydrodynamic (drag) force (analytical expression)

For steady flow with external velocity v (m/s) impinging orthogonally on the façade, the steady-state drag force on the wetted facade area A = W * H (m^2) is given by the usual steady drag formula:

F_drag = 0.5 * ρ * C_D * v^2 * A = 0.5 * ρ * C_D * v^2 * W * H

The drag force scales with v^2 and acts over the wetted area. For a uniformly distributed drag over the wetted height, the centroid of the drag force is at H/2 above the base (i.e., the overturning moment contribution uses lever arm H/2).

Combined lateral force and overturning moment (closed-form)

Compute the total lateral force on the flow-facing façade as the sum of the hydrostatic and drag components (both using the wetted height H at the timestep of interest):

F_total = F_hydro + F_drag

The overturning moment about the base of the façade (perpendicular to the plane of the building) is approximated by the sum of the moments produced by each component using their analytical centroids:

M_overturn = F_hydro * (H/3) + F_drag * (H/2)

Notes and limitations

- These expressions are closed-form analytical formulas valid for vertical planar façades with uniform wetted depth. They are widely used in preliminary design and risk-assessment stages.
- The drag coefficient C_D depends on flow regime and façade roughness; the default C_D = 1.0 is conservative but can be refined with experimental or site-specific data.
- This modelling approach does not attempt to capture impulsive or wave-induced loads. For impulsive/wave impacts, consult the FEMA guideline you provided earlier; such events require specialized design criteria and should be handled per that FEMA guidance rather than by the steady hydrostatic/drag formulas above.

Outputs

- The simulator will (when enabled) compute time series of F_hydro, F_drag, F_total and M_overturn at each simulation timestep using the sampled wetted height H(t) and sampled external velocity v(t). Peak values and times of occurrence are reported as summary statistics.
- Outputs are provided as time series (CSV) and as simple peak-value summaries for easy inspection. (Support for additional formats can be added later.)

Suggested validation checks

- Verify that F_drag scales with v^2 by running two identical hydrographs with different constant velocities and checking the ratio of resulting drag forces.
- Check that when v=0 the drag term vanishes and the computed lateral force reduces to the hydrostatic expression above.

Suggested tests

- Compare two runs with identical hydrographs but with v_out(t)=0 (hydrostatic only) and v_out(t)=0.2 m/s to observe sensitivity of infiltration timing and volume.
- Unit test: for a single orifice with fixed h_out, h_in and v_out check analytical change in Q predicted by the formula above.


## Basement positioning and elevation-aware modelling

This short technical note explains how to represent basements (cellars, low-lying compartments) in the flood ingress model using absolute elevations so that the orifice law works naturally — i.e. a basement can retain water when external levels fall below connection sills without any artificial clamping of flows.

Reference datum and symbols

- $z_{ref}$ — reference datum (m). By default the model uses the interior ground-floor level as the datum ($z_{ref} = 0$). All sill/entry elevations and compartment floor elevations are expressed relative to this datum.

- $z_b$ — basement floor elevation (m) relative to $z_{ref}$ (typically negative if the basement floor lies below the ground-floor datum).

- $h_b(t)$ — basement water depth measured above the basement floor (m).

- $S_b$ — basement plan area (m^2).

- $H_x(t)$ — absolute water surface elevation for compartment or external node x (m). For the basement: $H_b(t) = z_b + h_b(t). For the ground-floor interior, when $z_{ref} = 0$, $H_{in}(t) = h_{in}(t)$.

### Elevation-aware orifice condition

Every opening $i$ has a sill elevation $z_i$ (m, relative to $z_{ref}$). Let $H_{src}(t)$ and $H_{tgt}(t)$ be the absolute water surface elevations on the source and target sides of opening $i$. Define the head difference

$$
\Delta H_i(t) = H_{src}(t) - H_{tgt}(t).
$$

Flow through opening $i$ is permitted only when at least one side of the opening is at or above the sill elevation (i.e. when the opening is submerged):

$$
\max(H_{src}(t), H_{tgt}(t)) \ge z_i.
$$

If submerged, the instantaneous volumetric flow rate is evaluated with the orifice-like law used elsewhere in the simulator:

$$
Q_i(t) = \mathrm{sign}(\Delta H_i(t)) \; C_i \; A_i \; \sqrt{2 g |\Delta H_i(t)|}.
$$

Note: the sign convention used in the simulator makes $Q$ positive in the ``source->target`` sense. The formula therefore supports reverse flow when the head reverses, but reverse flow will not occur if the opening is not submerged (because the submerged condition is false).

### Mass balances and updating

Write a separate mass balance for each compartment (ground-floor interior and basement). For example, if $I_{in}$ is the set of openings connected to the interior and $I_b$ the set connected to the basement:

$$
\frac{dV}{dt} = \sum_{i \in I_{in}} Q_i(t), \\
\frac{dV_b}{dt} = \sum_{i \in I_b} Q_i(t),
$$

and convert volumes to depths by dividing by the compartment plan areas $S$ and $S_b$:

$$
h_{in}(t) = \frac{V(t)}{S}, \qquad h_b(t) = \frac{V_b(t)}{S_b}.
$$

### Numerical implementation (recipe)

1. Choose a reference datum $z_{ref}$ (ground-floor interior level is convenient).
2. Express sill elevations $z_i$ and any compartment floor elevations ($z_b$) relative to $z_{ref}$.
3. At each timestep compute absolute surfaces $H$ for every compartment ($H = z_{comp} + h_{comp}$).
4. For each opening check the submerged condition ($\max(H_{src},H_{tgt}) \ge z_i$). If submerged evaluate $Q_i$ using the elevation-aware orifice law.
5. Update compartment volumes by summing signed $Q_i$ over their incident openings and applying the explicit Euler step; convert volumes back to depths.

### Why this models retention naturally

Because the submerged test uses absolute sill elevations, a basement that lies below the ground-floor datum can (and will) retain water when both the external level and the interior ground-floor surface fall below the connection sill: then $\max(H_{src},H_{tgt}) < z_i$ and no flow is computed. This behaviour requires no artificial suppression of negative flows — the orifice law simply becomes inactive when the opening is unsubmerged.

### Practical advice

- Use negative $z_b$ values to represent basement floors below the ground-floor datum (for instance $z_b = -2.5\,$m to indicate a basement floor 2.5 m below the interior ground-floor level).

- Express all sill elevations $z_i$ on the same datum. For example a ground-> basement connection at the ground-floor level has $z_i = 0$; a hole in the basement ceiling 1.5 m below ground would have $z_i = -1.5$.

- If you need devices or behaviours not captured by the elevation-aware orifice law (one-way check valves, pumps, trapped-air hysteresis), model them explicitly as additional pathway/device terms in the mass balances.

Notes

This is a documentation-level modelling recommendation. Implementing it exactly requires that the simulator compute absolute elevations for compartments and use the submerged test above when evaluating $Q_i$. The current code already contains the building/basement compartments and a sill height for ingress pathways; the elevation-aware interpretation clarifies how to choose heights so that basements behave physically (i.e. retain water) without ad-hoc flow clamping.

