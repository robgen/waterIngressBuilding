#!/usr/bin/env python3
"""Pathway-resolved hydraulic diagnostics for the water ingress model.

This module implements the interpretation layer described in
docs/INTERPRETATION_DASHBOARD_TUTORIAL.md and spec section 17.2.

Design principle (spec §17.2)
------------------------------
The diagnostics runner uses the **same pure helper functions** as
Simulation.run() (via pump.py) and the same IngressPathway.compute_flow()
logic.  It does NOT replicate hydraulic equations independently.

The runner replays the simulation from scratch with identical arithmetic,
recording per-timestep pathway flows, cumulative volumes, control states,
and key event timings.  This guarantees that diagnostics are always
consistent with the main simulation output.

Usage
-----
    from diagnostics import run_diagnostics
    diag = run_diagnostics(building, ingress_list, times_s, levels, dt=dt_s,
                           v_times=v_t, v_vals=v_v)
    # diag is a dict of lists, one entry per simulation timestep

Keys returned
-------------
times              : simulation times (seconds, internal)
H_out              : external water surface head at each step
h_in               : building interior depth
h_basement         : basement depth
h_sump             : sump depth (0 if no sump)
H_lift             : pump lift head at each step (0 if no sump)
pump_state         : pump on/off state  u(t)  (0 if no sump)
Q_ext_b            : exterior→ground-floor flow (m³/s)
Q_b_bs             : ground-floor→basement flow (positive = g→bs, m³/s)
Q_ext_perimeter    : lumped exterior perimeter flow (to basement or sump, m³/s)
Q_pump             : pump discharge from sump (m³/s, 0 if no sump)
Q_sump_overflow    : sump→basement overflow (m³/s, 0 if no sump)
vol_ext_b_cum      : cumulative exterior→building volume (m³)
vol_b_bs_cum       : cumulative ground→basement volume (m³)
vol_perimeter_cum  : cumulative perimeter inflow volume (m³)
vol_pump_cum       : cumulative pump discharge volume (m³)
vol_sump_overflow_cum : cumulative sump overflow volume (m³)
events             : dict of named event timings (keyed strings → time in seconds)
"""

import copy
import math

from pump import (compute_sump_overflow, compute_pump_switch_state,
                  compute_lift_head, compute_pump_flow)


def run_diagnostics(building, ingress_list, external_times, external_levels,
                    dt=60.0, v_times=None, v_vals=None):
    """Replay the simulation and return pathway-resolved diagnostics.

    Parameters are the same as Simulation.__init__.  The building and its
    sump_pump/basement_ingress state is deep-copied internally so the caller's
    state is not modified.

    Returns a dict with time-series lists (one value per simulation timestep)
    and an 'events' sub-dict with key event timings.
    """
    # Deep-copy the building so we do not disturb the caller's state
    bldg = copy.deepcopy(building)
    sp   = bldg.sump_pump          # SumpPump or None (already deep-copied)
    bi   = bldg.basement_ingress   # IngressPathway or None

    v_t   = list(v_times) if v_times else []
    v_v   = list(v_vals)  if v_vals  else []

    # ── output arrays ─────────────────────────────────────────────────────────
    out_times          = []
    out_H_out          = []
    out_h_in           = []
    out_h_basement     = []
    out_h_sump         = []
    out_H_lift         = []
    out_pump_state     = []
    out_Q_ext_b        = []   # exterior → ground floor
    out_Q_b_bs         = []   # ground floor → basement (net)
    out_Q_perimeter    = []   # lumped perimeter flow (→ basement or → sump)
    out_Q_pump         = []   # pump discharge
    out_Q_sump_ov      = []   # sump overflow → basement

    cum_ext_b      = 0.0
    cum_b_bs       = 0.0
    cum_perimeter  = 0.0
    cum_pump       = 0.0
    cum_sump_ov    = 0.0

    events = {}

    # ── time-stepping (mirrors Simulation.run exactly) ─────────────────────────
    dt = float(dt)
    t_ext   = external_times
    h_ext   = external_levels
    start_t = t_ext[0]  if t_ext else 0.0
    end_t   = t_ext[-1] if t_ext else 0.0
    total_steps = max(1, int(math.ceil((end_t - start_t) / max(dt, 1e-9))))

    current_h_in       = bldg.h_in
    current_h_basement = bldg.h_basement
    ext_idx = 0
    vel_idx = 0

    for step in range(total_steps + 1):
        t = start_t + step * dt
        if t > end_t:
            t = end_t

        # interpolate external level
        while ext_idx < len(t_ext) - 1 and t >= t_ext[ext_idx + 1]:
            ext_idx += 1
        if ext_idx < len(t_ext) - 1:
            t1, h1 = t_ext[ext_idx], h_ext[ext_idx]
            t2, h2 = t_ext[ext_idx+1], h_ext[ext_idx+1]
            h_out = h1 + (h2 - h1) * (t - t1) / (t2 - t1) if t2 != t1 else h1
        else:
            h_out = h_ext[-1] if h_ext else 0.0

        H_out      = h_out
        H_in       = current_h_in
        H_basement = bldg.z_basement + current_h_basement
        H_sump_abs = (sp.sump_base_elevation + sp.h_sump) if sp is not None else 0.0

        # interpolate velocity
        v_out = 0.0
        if v_t and v_v:
            while vel_idx < len(v_t) - 1 and t >= v_t[vel_idx + 1]:
                vel_idx += 1
            if vel_idx < len(v_t) - 1:
                vt1, vv1 = v_t[vel_idx], v_v[vel_idx]
                vt2, vv2 = v_t[vel_idx+1], v_v[vel_idx+1]
                v_out = vv1 + (vv2 - vv1)*(t-vt1)/(vt2-vt1) if vt2 != vt1 else vv1
            else:
                v_out = 0.0 if t > v_t[-1] else (v_v[-1] if v_v else 0.0)

        # ingress flows (exterior→building only)
        flow_og = 0.0
        flow_gb = 0.0
        for ing in ingress_list:
            src = getattr(ing, 'source', 'outside')
            tgt = getattr(ing, 'target', 'ground')
            if src == 'outside' and tgt == 'ground':
                flow_og += ing.compute_flow(H_out, H_in, v_source=v_out)
            elif src == 'ground' and tgt == 'basement':
                flow_gb += ing.compute_flow(H_in, H_basement)
            elif src == 'basement' and tgt == 'ground':
                flow_gb -= ing.compute_flow(H_basement, H_in)

        # lumped perimeter pathway
        flow_ob = 0.0
        flow_os = 0.0
        if bi is not None:
            if sp is not None:
                flow_os = bi.compute_flow(H_out, H_sump_abs, v_source=v_out)
            else:
                flow_ob = bi.compute_flow(H_out, H_basement, v_source=v_out)

        # ground floor update
        bldg.update_water_level((flow_og - flow_gb) * dt, zone='ground')
        current_h_in = bldg.h_in

        # sump update
        Q_pump_t  = 0.0
        Q_sov_t   = 0.0
        H_lift_t  = 0.0
        u_t       = 0
        if sp is not None:
            H_lift_t = compute_lift_head(H_out, sp.sump_base_elevation)
            sp.pump_state = compute_pump_switch_state(
                sp.h_sump, sp.pump_on_level, sp.pump_off_level, sp.pump_state)
            u_t = sp.pump_state
            Q_pump_t = compute_pump_flow(
                sp.pump_state, sp.pump_availability,
                sp.pump_shutoff_head, H_lift_t,
                sp.pump_curve_coeff, sp.pipe_loss_coeff)
            Q_sov_t = compute_sump_overflow(
                sp.h_sump, sp.overflow_level,
                sp.overflow_coeff, sp.overflow_exponent)
            sp.h_sump = max(0.0, sp.h_sump + (flow_os - Q_pump_t - Q_sov_t) * dt / sp.sump_area)

        # basement update
        vol_basement = (flow_ob + flow_gb + Q_sov_t) * dt
        ov = bldg.update_water_level(vol_basement, zone='basement')
        if ov and ov > 0.0:
            bldg.update_water_level(ov, zone='ground')
        current_h_basement = bldg.h_basement

        # record step
        out_times.append(t)
        out_H_out.append(H_out)
        out_h_in.append(current_h_in)
        out_h_basement.append(current_h_basement)
        out_h_sump.append(sp.h_sump if sp is not None else 0.0)
        out_H_lift.append(H_lift_t)
        out_pump_state.append(u_t)
        out_Q_ext_b.append(flow_og)
        out_Q_b_bs.append(flow_gb)
        Q_perim = flow_os if sp is not None else flow_ob
        out_Q_perimeter.append(Q_perim)
        out_Q_pump.append(Q_pump_t)
        out_Q_sump_ov.append(Q_sov_t)

        cum_ext_b     += flow_og * dt
        cum_b_bs      += flow_gb * dt
        cum_perimeter += Q_perim * dt
        cum_pump      += Q_pump_t * dt
        cum_sump_ov   += Q_sov_t * dt

        # ── event detection ────────────────────────────────────────────────
        if 't_first_gf_inundation' not in events and current_h_in > 0.0:
            events['t_first_gf_inundation'] = t
        if 't_first_basement_inundation' not in events and current_h_basement > 0.0:
            events['t_first_basement_inundation'] = t
        if sp is not None and 't_first_pump_on' not in events and u_t == 1:
            events['t_first_pump_on'] = t
        if sp is not None and 't_first_sump_overflow' not in events and Q_sov_t > 0.0:
            events['t_first_sump_overflow'] = t

    # ── cumulative volume final ────────────────────────────────────────────────
    # Find peak indices
    def _argmax(lst):
        return max(range(len(lst)), key=lambda i: lst[i]) if lst else 0

    events['t_peak_ext']      = out_times[_argmax(out_H_out)]
    events['t_peak_gf']       = out_times[_argmax(out_h_in)]
    events['t_peak_basement'] = out_times[_argmax(out_h_basement)]
    if sp is not None:
        events['t_peak_sump'] = out_times[_argmax(out_h_sump)]

    # Dominant basement source
    if cum_perimeter > 0 or cum_b_bs > 0:
        if cum_b_bs > cum_perimeter:
            events['dominant_basement_source'] = 'bypass'
        else:
            events['dominant_basement_source'] = 'perimeter'
    else:
        events['dominant_basement_source'] = 'none'

    # Pump interception ratio  (how much of perimeter inflow was pumped out)
    if cum_perimeter > 0:
        events['pump_interception_ratio'] = min(1.0, cum_pump / cum_perimeter)
    else:
        events['pump_interception_ratio'] = None

    # Cumulative volume totals
    events['vol_ext_b_total']         = cum_ext_b
    events['vol_perimeter_total']      = cum_perimeter
    events['vol_b_bs_total']           = cum_b_bs
    events['vol_pump_total']           = cum_pump
    events['vol_sump_overflow_total']  = cum_sump_ov

    return {
        'times':              out_times,
        'H_out':              out_H_out,
        'h_in':               out_h_in,
        'h_basement':         out_h_basement,
        'h_sump':             out_h_sump,
        'H_lift':             out_H_lift,
        'pump_state':         out_pump_state,
        'Q_ext_b':            out_Q_ext_b,
        'Q_b_bs':             out_Q_b_bs,
        'Q_ext_perimeter':    out_Q_perimeter,
        'Q_pump':             out_Q_pump,
        'Q_sump_overflow':    out_Q_sump_ov,
        'vol_ext_b_cum':      list(_cumsum(out_Q_ext_b, dt)),
        'vol_b_bs_cum':       list(_cumsum(out_Q_b_bs,  dt)),
        'vol_perimeter_cum':  list(_cumsum(out_Q_perimeter, dt)),
        'vol_pump_cum':       list(_cumsum(out_Q_pump,  dt)),
        'vol_sump_overflow_cum': list(_cumsum(out_Q_sump_ov, dt)),
        'events':             events,
    }


def _cumsum(flow_list, dt):
    """Running cumulative volume integral (flow * dt)."""
    total = 0.0
    for q in flow_list:
        total += q * dt
        yield total


def diagnostics_to_csv_rows(diag):
    """Yield header + data rows for CSV export of diagnostics dict."""
    keys = [k for k in diag if k != 'events' and isinstance(diag[k], list)]
    yield keys
    for i in range(len(diag['times'])):
        yield [diag[k][i] for k in keys]


def generate_narrative(diag):
    """Return a list of plain-English interpretation bullets from diagnostics."""
    ev = diag.get('events', {})
    has_sump = any(q > 0 for q in diag.get('Q_pump', []))
    lines = []

    h_peak_gf = max(diag['h_in']) if diag['h_in'] else 0.0
    h_peak_bs = max(diag['h_basement']) if diag['h_basement'] else 0.0
    h_peak_sump = max(diag['h_sump']) if diag.get('h_sump') else 0.0

    lines.append(f"Peak ground-floor depth: {h_peak_gf:.3f} m")
    lines.append(f"Peak basement depth: {h_peak_bs:.3f} m")
    if has_sump:
        lines.append(f"Peak sump depth: {h_peak_sump:.3f} m")

    dom = ev.get('dominant_basement_source', 'none')
    if dom == 'bypass':
        lines.append("Dominant basement source: ground-floor→basement bypass. "
                      "Sump protection alone cannot prevent basement flooding in this event.")
    elif dom == 'perimeter':
        lines.append("Dominant basement source: exterior perimeter inflow. "
                      "Sump/pump effectiveness directly determines basement flooding.")
    else:
        lines.append("No significant basement inflow recorded.")

    ratio = ev.get('pump_interception_ratio')
    if ratio is not None:
        pct = ratio * 100
        if pct >= 90:
            lines.append(f"Pump intercepted {pct:.0f}% of perimeter inflow — effective protection.")
        elif pct >= 60:
            lines.append(f"Pump intercepted {pct:.0f}% of perimeter inflow — partial protection.")
        else:
            lines.append(f"Pump intercepted {pct:.0f}% of perimeter inflow — pump-limited or near-failure.")

    v_ov = ev.get('vol_sump_overflow_total', 0.0)
    if v_ov and v_ov > 0.001:
        lines.append(f"Sump overflowed: {v_ov:.3f} m³ spilled into basement.")
    elif has_sump:
        lines.append("Sump did not overflow — perimeter inflow stayed below crest.")

    t_on = ev.get('t_first_pump_on')
    if t_on is not None:
        lines.append(f"Pump first activated at t = {t_on:.1f} s.")

    return lines
