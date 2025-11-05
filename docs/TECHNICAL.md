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

