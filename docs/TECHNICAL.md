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
Q_i(t) = C_i A_i \sqrt{2 g |\Delta h_i(t)|} \;\mathrm{sign}(\Delta h_i(t)),
$$

where

$$
\Delta h_i(t) = h_{out}(t) - h_{in}(t).
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
