#!/usr/bin/env python3
"""Pathway-resolved hydraulic diagnostics for the water ingress model.

This module implements the interpretation layer described in
docs/INTERPRETATION_DASHBOARD_TUTORIAL.md and spec section 17.2.

Design principle (spec §17.2)
------------------------------
Diagnostics are built from the per-step trace emitted by Simulation.run()
(stored as sim._last_trace).  There is no independent replay loop here —
all hydraulic arithmetic lives in Simulation.run() and pump.py.

``run_diagnostics`` is a convenience wrapper that creates a Simulation,
calls run(), and returns the diagnostics dict.  When you already have a
Simulation that has been run, call ``diagnostics_from_trace`` directly
to avoid a second simulation pass.

Usage
-----
    # Preferred — single simulation pass
    sim = Simulation(building, ingress, times_s, levels, dt=dt_s)
    sim.run()
    diag = diagnostics_from_trace(sim._last_trace, sim.dt)

    # Convenience wrapper (creates and runs a fresh Simulation internally)
    from diagnostics import run_diagnostics
    diag = run_diagnostics(building, ingress_list, times_s, levels, dt=dt_s,
                           v_times=v_t, v_vals=v_v)

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


def diagnostics_from_trace(trace, dt):
    """Build the diagnostics dict from a per-step trace emitted by Simulation.run().

    Parameters
    ----------
    trace : dict
        The ``_last_trace`` dict populated by ``Simulation.run()``.
    dt : float
        Simulation timestep (same units as trace['times']).

    Returns
    -------
    dict
        Full diagnostics dict (same structure as returned by run_diagnostics).
    """
    dt = float(dt)

    times         = trace['times']
    H_out         = trace['H_out']
    h_in          = trace['h_in']
    h_basement    = trace['h_basement']
    h_sump        = trace['h_sump']
    H_lift        = trace['H_lift']
    pump_state    = trace['pump_state']
    Q_ext_b       = trace['Q_ext_b']
    Q_b_bs        = trace['Q_b_bs']
    Q_ext_perim   = trace['Q_ext_perimeter']
    Q_pump        = trace['Q_pump']
    Q_sump_ov     = trace['Q_sump_overflow']

    # Use the explicit flag written by Simulation.run(); fall back to flow activity
    # for traces produced by older code that lacks the flag.
    has_sump = trace.get('sump_configured',
                         any(ps != 0 for ps in pump_state)
                         or any(q > 0 for q in Q_pump)
                         or any(q > 0 for q in Q_sump_ov))

    # ── cumulative sums ───────────────────────────────────────────────────────
    vol_ext_b_cum     = list(_cumsum(Q_ext_b,     dt))
    vol_b_bs_cum      = list(_cumsum(Q_b_bs,      dt))
    vol_perimeter_cum = list(_cumsum(Q_ext_perim,  dt))
    vol_pump_cum      = list(_cumsum(Q_pump,       dt))
    vol_sump_ov_cum   = list(_cumsum(Q_sump_ov,    dt))

    cum_ext_b     = vol_ext_b_cum[-1]     if vol_ext_b_cum     else 0.0
    cum_b_bs      = vol_b_bs_cum[-1]      if vol_b_bs_cum      else 0.0
    cum_perimeter = vol_perimeter_cum[-1] if vol_perimeter_cum else 0.0
    cum_pump      = vol_pump_cum[-1]      if vol_pump_cum      else 0.0
    cum_sump_ov   = vol_sump_ov_cum[-1]  if vol_sump_ov_cum   else 0.0

    # ── event detection ───────────────────────────────────────────────────────
    events = {}

    for i, t in enumerate(times):
        if 't_first_gf_inundation' not in events and h_in[i] > 0.0:
            events['t_first_gf_inundation'] = t
        if 't_first_basement_inundation' not in events and h_basement[i] > 0.0:
            events['t_first_basement_inundation'] = t
        if 't_first_pump_on' not in events and pump_state[i] == 1:
            events['t_first_pump_on'] = t
        if 't_first_sump_overflow' not in events and Q_sump_ov[i] > 0.0:
            events['t_first_sump_overflow'] = t

    def _argmax(lst):
        return max(range(len(lst)), key=lambda i: lst[i]) if lst else 0

    if times:
        events['t_peak_ext']      = times[_argmax(H_out)]
        events['t_peak_gf']       = times[_argmax(h_in)]
        events['t_peak_basement'] = times[_argmax(h_basement)]
        if has_sump:
            events['t_peak_sump'] = times[_argmax(h_sump)]

    # Dominant basement source
    if cum_perimeter > 0 or cum_b_bs > 0:
        events['dominant_basement_source'] = 'bypass' if cum_b_bs > cum_perimeter else 'perimeter'
    else:
        events['dominant_basement_source'] = 'none'

    # Pump interception ratio
    if cum_perimeter > 0:
        events['pump_interception_ratio'] = min(1.0, cum_pump / cum_perimeter)
    else:
        events['pump_interception_ratio'] = None

    events['vol_ext_b_total']        = cum_ext_b
    events['vol_perimeter_total']    = cum_perimeter
    events['vol_b_bs_total']         = cum_b_bs
    events['vol_pump_total']         = cum_pump
    events['vol_sump_overflow_total'] = cum_sump_ov
    events['sump_configured']        = has_sump

    return {
        'times':                 times,
        'H_out':                 H_out,
        'h_in':                  h_in,
        'h_basement':            h_basement,
        'h_sump':                h_sump,
        'H_lift':                H_lift,
        'pump_state':            pump_state,
        'Q_ext_b':               Q_ext_b,
        'Q_b_bs':                Q_b_bs,
        'Q_ext_perimeter':       Q_ext_perim,
        'Q_pump':                Q_pump,
        'Q_sump_overflow':       Q_sump_ov,
        'vol_ext_b_cum':         vol_ext_b_cum,
        'vol_b_bs_cum':          vol_b_bs_cum,
        'vol_perimeter_cum':     vol_perimeter_cum,
        'vol_pump_cum':          vol_pump_cum,
        'vol_sump_overflow_cum': vol_sump_ov_cum,
        'events':                events,
    }


def run_diagnostics(building, ingress_list, external_times, external_levels,
                    dt=60.0, v_times=None, v_vals=None):
    """Run a fresh simulation and return pathway-resolved diagnostics.

    This is a convenience wrapper.  Internally it creates a Simulation,
    calls run() (which populates sim._last_trace), then calls
    diagnostics_from_trace().  The building state is deep-copied so the
    caller's building is not modified.

    When you already have a Simulation that has been run, prefer:
        diag = diagnostics_from_trace(sim._last_trace, sim.dt)
    to avoid a second simulation pass.
    """
    # Local import avoids a module-level dependency on main.py (main.py does
    # not import from diagnostics.py, so there is no circular import).
    from main import Simulation

    bldg = copy.deepcopy(building)
    sim = Simulation(
        bldg, ingress_list, external_times, external_levels,
        dt=dt,
        external_vel_times=v_times,
        external_velocities=v_vals,
    )
    sim.run()
    return diagnostics_from_trace(sim._last_trace, sim.dt)


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

    h_peak_gf   = max(diag['h_in'])       if diag['h_in']       else 0.0
    h_peak_bs   = max(diag['h_basement']) if diag['h_basement'] else 0.0
    h_peak_sump = max(diag['h_sump'])     if diag.get('h_sump') else 0.0

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
