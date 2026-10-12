#!/usr/bin/env python3
"""Sump pit and head-dependent pump model (see docs/model.md, *Sump and pump*).

Design principles
-----------------
- Pure helper functions are separated from the dataclass so they are
  independently testable and reusable in the diagnostics layer.
- The pump availability factor (eta_p) is retained explicitly so that a
  future Monte Carlo fragility pass can set it per realisation without
  rewriting any hydraulic equations.
- Lift head H_lift(t) = H_out(t) - z_sump_base is computed each timestep
  from the external flood level.  This first-order assumption is kept in
  one function (compute_lift_head) so it can be refined later.

Geometry and routing
--------------------
The sump is a pit below the basement floor: its top is at the basement floor
elevation z_b and its base at sump_base_elevation, so its depth is
z_b - sump_base_elevation.  It is a compartment of its own (level h_sump):
  - exterior→basement pathways (target='basement', from --basement-ingress)
    discharge into the sump when one is configured;
  - basement water drains into the pit through its opening (an orifice at the
    basement floor, area opening_area, default the full sump area);
  - a full sump spills onto the basement floor;
  - the pump draws from the sump only.
"""

import math
import warnings
from dataclasses import dataclass
from typing import Optional


@dataclass
class SumpPump:
    """Parameters and mutable state for the sump chamber and pump system.

    Parameters (immutable intent)
    -----------------------------
    sump_area          : A_s (m²) — plan area of the sump pit
    pump_on_level      : h_on (m) — sump depth at which pump activates
    pump_off_level     : h_off (m) — sump depth at which pump deactivates
    pump_shutoff_head  : H_shut (m) — pump shut-off head
    pump_curve_coeff   : k_pump — pump-curve coefficient
    pipe_loss_coeff    : k_pipe — pipe friction + minor loss coefficient
    sump_base_elevation: z_sump_base (m) — elevation of sump base on the
                         ground-floor datum; used to derive lift head as
                         H_lift(t) = max(0, H_out(t) - z_sump_base)
    pump_availability  : eta_p — availability factor (1.0 = always available).
                         Placeholder for future fragility/Monte Carlo.
    opening_area       : area (m²) of the pit opening at the basement floor
                         through which basement water drains into the sump;
                         None = the full sump area (open pit)
    opening_coeff      : discharge coefficient of the pit opening

    Mutable state (reset between cases in batch runs via copy.deepcopy)
    -------------------------------------------------------------------
    h_sump    : current sump water depth (m above sump base)
    pump_state: current on/off state  u(t) ∈ {0, 1}
    """
    sump_area: float
    pump_on_level: float
    pump_off_level: float
    pump_shutoff_head: float
    pump_curve_coeff: float
    pipe_loss_coeff: float
    sump_base_elevation: float
    pump_availability: float = 1.0
    opening_area: Optional[float] = None
    opening_coeff: float = 0.6
    # mutable state — deepcopy these between batch cases
    h_sump: float = 0.0
    pump_state: int = 0

    def __post_init__(self):
        if self.sump_area <= 0.0:
            raise ValueError(
                f"SumpPump.sump_area must be > 0, got {self.sump_area}")
        if self.pump_off_level >= self.pump_on_level:
            raise ValueError(
                f"SumpPump.pump_off_level ({self.pump_off_level}) must be "
                f"< pump_on_level ({self.pump_on_level}): hysteresis band is inverted")
        if self.opening_area is not None and self.opening_area <= 0.0:
            raise ValueError(
                f"SumpPump.opening_area must be > 0, got {self.opening_area}")
        if self.pump_shutoff_head <= 0.0:
            warnings.warn(
                f"SumpPump.pump_shutoff_head is {self.pump_shutoff_head} ≤ 0; "
                "pump will always return zero flow.", stacklevel=2)

    def max_pump_flow(self):
        """Q_p,max: pump-curve flow at zero lift head (the largest it can deliver)."""
        return compute_pump_flow(1, self.pump_availability, self.pump_shutoff_head, 0.0,
                                 self.pump_curve_coeff, self.pipe_loss_coeff)

    def max_stable_dt(self):
        """Largest stable explicit step (s): Δt ≤ 0.5 · A_sump · h_on / Q_p,max.

        A single step then drains at most half of the switch-on storage volume
        at the maximum pumping rate.  Infinite when the pump delivers no flow.
        """
        q_max = self.max_pump_flow()
        if q_max <= 0.0:
            return math.inf
        return 0.5 * self.sump_area * self.pump_on_level / q_max

    def depth(self, basement_floor_elevation):
        """Pit depth: from the sump base up to the basement floor."""
        return float(basement_floor_elevation) - float(self.sump_base_elevation)

    def check_geometry(self, basement_floor_elevation):
        """Raise if the pit has no depth; warn if the pump never switches on."""
        depth = self.depth(basement_floor_elevation)
        if depth <= 0.0:
            raise ValueError(
                f"SumpPump.sump_base_elevation ({self.sump_base_elevation}) must be "
                f"below the basement floor ({basement_floor_elevation}): the sump "
                "is a pit whose top is at the basement floor.")
        if self.pump_on_level > depth:
            warnings.warn(
                f"SumpPump.pump_on_level ({self.pump_on_level}) > sump depth "
                f"({depth}): the pump only switches on once the sump has spilled "
                "into the basement.", stacklevel=2)


# ── pure helper functions ─────────────────────────────────────────────────────

def compute_pump_switch_state(h_sump, pump_on_level, pump_off_level, previous_state):
    """Hysteretic on/off control: u(t) ∈ {0, 1}.

    Spec eq (section 6.1):
        1  if h_s ≥ h_on
        0  if h_s ≤ h_off
        previous_state  otherwise  (hysteresis band)
    """
    h = float(h_sump)
    if h >= float(pump_on_level):
        return 1
    if h <= float(pump_off_level):
        return 0
    return int(previous_state)


def compute_lift_head(H_out, sump_base_elevation):
    """H_lift(t) = max(0, H_out(t) - z_sump_base).

    First-order lift-head assumption: the pump discharges against the external
    flood level referenced to the sump datum.  This is conservative when the
    real outfall is better-protected than the exterior flood level implies.
    """
    return max(0.0, float(H_out) - float(sump_base_elevation))


def compute_pump_flow(pump_on, availability, shutoff_head, lift_head,
                      pump_curve_coeff, pipe_loss_coeff):
    """Q_p(t) = u(t) * eta_p * Q*_p(t)  (m³/s, non-negative).

    Operating point from equating pump and system head curves:
        Q*_p = sqrt((H_shut - H_lift) / (k_pump + k_pipe))
              if H_shut > H_lift else 0

    Guard conditions:
    - Returns 0 if pump is off.
    - Returns 0 if H_shut ≤ H_lift (pump cannot overcome lift).
    - Returns 0 if denominator ≤ 0 (degenerate coefficients).
    No negative square-root can occur because net_head is clamped to ≥ 0.
    """
    if not pump_on:
        return 0.0
    denom = float(pump_curve_coeff) + float(pipe_loss_coeff)
    net_head = float(shutoff_head) - float(lift_head)
    if denom <= 0.0 or net_head <= 0.0:
        return 0.0
    return float(availability) * math.sqrt(net_head / denom)
