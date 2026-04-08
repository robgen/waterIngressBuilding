#!/usr/bin/env python3
"""Sump chamber and head-dependent pump model.

This module implements the sump-pump extension described in
docs/sump_pump_extension_spec.md (sections 4–7, 12).

Design principles
-----------------
- Pure helper functions are separated from the dataclass so they are
  independently testable and reusable in the diagnostics layer.
- The pump availability factor (eta_p) is retained explicitly so that a
  future Monte Carlo fragility pass can set it per realisation without
  rewriting any hydraulic equations.
- Lift head H_lift(t) = H_out(t) - z_sump_base is computed each timestep
  from the external flood level.  This is the first-order assumption
  described in spec section 16.5 and should remain isolatable for later
  improvement.

Routing convention
------------------
The lumped exterior perimeter inflow (Q_ext_s or Q_ext_b) is owned by
Building.basement_ingress, not by the user-authored ingress file.  When a
sump is configured, Simulation.run() redirects that pathway to the sump.
When no sump is configured it feeds the basement directly.  This keeps the
user-facing ingress file as exterior-to-building-only pathways.
"""

import math
from dataclasses import dataclass, field


@dataclass
class SumpPump:
    """Parameters and mutable state for the sump chamber and pump system.

    Parameters (immutable intent)
    -----------------------------
    sump_area          : A_s (m²) — plan area of sump chamber
    overflow_level     : z_ov (m above sump base) — overflow crest elevation
    overflow_coeff     : C_ov — weir/overflow discharge coefficient
    overflow_exponent  : m_ov — exponent (1.5 = weir, 0.5 = orifice)
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

    Mutable state (reset between cases in batch runs via copy.deepcopy)
    -------------------------------------------------------------------
    h_sump    : current sump water depth (m above sump base)
    pump_state: current on/off state  u(t) ∈ {0, 1}
    """
    sump_area: float
    overflow_level: float
    overflow_coeff: float
    overflow_exponent: float
    pump_on_level: float
    pump_off_level: float
    pump_shutoff_head: float
    pump_curve_coeff: float
    pipe_loss_coeff: float
    sump_base_elevation: float
    pump_availability: float = 1.0
    # mutable state — deepcopy these between batch cases
    h_sump: float = 0.0
    pump_state: int = 0


# ── pure helper functions ─────────────────────────────────────────────────────

def compute_sump_overflow(h_sump, overflow_level, overflow_coeff, overflow_exponent):
    """Q_s→bs: weir/orifice overflow from sump into basement (m³/s).

    Returns 0 when h_sump ≤ overflow_level.
    Spec eq: Q_s→bs = C_ov * (h_s - z_ov)^m_ov  if h_s > z_ov else 0
    """
    excess = float(h_sump) - float(overflow_level)
    if excess <= 0.0:
        return 0.0
    return float(overflow_coeff) * (excess ** float(overflow_exponent))


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
    See spec sections 7 and 16.5 for interpretation limits.
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
