#!/usr/bin/env python3
"""engine.py — canonical single-simulation runner.

Public API
----------
Data structures:
    SimConfig     — building geometry, timestep, and run-control parameters
    Hydrograph    — external flood time series (times in seconds)
    SimResult     — deterministic simulation output

Entry point:
    run(config, hydro, pathways, *, basement_pathway, conductance_resolver) → SimResult

Low-level classes (also used by fragility.py and batch.py):
    Building, IngressPathway, Simulation

I/O helpers:
    parse_combined_file, parse_combined_text, parse_external_text, sample_with_zero_padding
"""

import copy
import csv
import math
import warnings
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from pump import (
    SumpPump,
    compute_lift_head,
    compute_pump_flow,
    compute_pump_switch_state,
    compute_sump_overflow,
)


# ── building model ────────────────────────────────────────────────────────────

class Building:
    def __init__(self, floor_area):
        self.floor_area = floor_area
        self.h_in = 0.0
        self.basement_area = 0.0
        self.h_basement = 0.0
        self.z_basement = 0.0
        self.basement_ceiling_elevation = 0.0
        self.basement_ingress = None   # IngressPathway or None
        self.sump_pump = None          # SumpPump or None

    def update_water_level(self, volume_change, zone='ground'):
        if zone == 'ground':
            if self.floor_area <= 0:
                return
            self.h_in += volume_change / self.floor_area
            if self.h_in < 0:
                self.h_in = 0.0
            return 0.0
        elif zone == 'basement':
            if self.basement_area <= 0:
                return 0.0
            self.h_basement += volume_change / self.basement_area
            if self.h_basement < 0:
                self.h_basement = 0.0
                return 0.0
            max_depth = max(0.0, self.basement_ceiling_elevation - self.z_basement)
            if self.h_basement > max_depth:
                overflow_h = self.h_basement - max_depth
                overflow_vol = overflow_h * self.basement_area
                self.h_basement = max_depth
                return overflow_vol
            return 0.0
        else:
            raise ValueError(f'Unknown zone: {zone}')


class IngressPathway:
    def __init__(self, height, area, coeff, name='Opening',
                 source='outside', target='ground'):
        self.height = float(height)
        self.area = float(area)
        self.coeff = float(coeff)
        self.name = name
        self.source = source
        self.target = target

    def compute_flow(self, H_source, H_target, v_source=0.0):
        if H_source <= self.height and H_target < self.height:
            return 0.0
        g = 9.81
        sill = float(self.height)
        h_src = max(0.0, float(H_source) - sill) + float(v_source) ** 2 / (2.0 * g)
        h_tgt = max(0.0, float(H_target) - sill)
        delta_H_eff = h_src - h_tgt
        if delta_H_eff == 0.0:
            return 0.0
        flow_rate = self.coeff * self.area * math.sqrt(2.0 * g * abs(delta_H_eff))
        return flow_rate if delta_H_eff > 0.0 else -flow_rate


class Simulation:
    def __init__(self, building, ingress_list, external_times, external_levels,
                 dt=60.0, external_vel_times=None, external_velocities=None,
                 conductance_resolver=None,
                 velocity_mode='zero', vel_a=1.5, vel_b=0.5):
        self.building = building
        self.ingress_list = ingress_list
        self._conductance_resolver = conductance_resolver
        self.t_ext = external_times
        self.h_ext = external_levels
        self.v_t = external_vel_times if external_vel_times is not None else []
        self.v_vals = external_velocities if external_velocities is not None else []
        self.dt = float(dt) if dt is not None else 60.0
        self.velocity_mode = velocity_mode
        self.vel_a = vel_a
        self.vel_b = vel_b
        self._last_trace = None
        self._initial_h_in = building.h_in
        self._initial_h_basement = building.h_basement
        if building.sump_pump is not None:
            self._initial_h_sump = building.sump_pump.h_sump
            self._initial_pump_state = building.sump_pump.pump_state
        else:
            self._initial_h_sump = 0.0
            self._initial_pump_state = 0

    def run(self, progress_callback=None, verbose=False):
        self.building.h_in = self._initial_h_in
        self.building.h_basement = self._initial_h_basement
        if self.building.sump_pump is not None:
            self.building.sump_pump.h_sump = self._initial_h_sump
            self.building.sump_pump.pump_state = self._initial_pump_state
        self._vel_index = 0

        indoor_levels = []
        times = []
        basement_levels = []
        sump_levels = []

        current_h_in = self.building.h_in
        current_h_basement = self.building.h_basement

        sp = self.building.sump_pump
        bi = self.building.basement_ingress

        _trace = {
            'times': [], 'H_out': [], 'h_in': [], 'h_basement': [], 'h_sump': [],
            'H_lift': [], 'pump_state': [], 'Q_ext_b': [], 'Q_b_bs': [],
            'Q_ext_perimeter': [], 'Q_pump': [], 'Q_sump_overflow': [],
            'sump_configured': sp is not None,
        }

        start_time = self.t_ext[0] if self.t_ext else 0.0
        end_time = self.t_ext[-1] if self.t_ext else 0.0
        total_steps = max(1, int(math.ceil((end_time - start_time) / max(self.dt, 1e-9))))
        i = 0

        for step in range(total_steps + 1):
            t = start_time + step * self.dt
            if t > end_time:
                t = end_time

            if i < len(self.t_ext) - 1:
                while i < len(self.t_ext) - 1 and t >= self.t_ext[i + 1]:
                    i += 1
            if i < len(self.t_ext) - 1:
                t1, h1 = self.t_ext[i], self.h_ext[i]
                t2, h2 = self.t_ext[i + 1], self.h_ext[i + 1]
                h_out = h1 + (h2 - h1) * (t - t1) / (t2 - t1) if t2 != t1 else h1
            else:
                h_out = self.h_ext[-1] if self.h_ext else 0.0

            H_out = h_out
            H_in = current_h_in
            H_basement = self.building.z_basement + current_h_basement
            H_sump_abs = (sp.sump_base_elevation + sp.h_sump) if sp is not None else 0.0

            v_out = 0.0
            if self.velocity_mode == 'file' and self.v_t and self.v_vals:
                j_v = self._vel_index
                while j_v < len(self.v_t) - 1 and t >= self.v_t[j_v + 1]:
                    j_v += 1
                self._vel_index = j_v
                if j_v < len(self.v_t) - 1:
                    vt1, vv1 = self.v_t[j_v], self.v_vals[j_v]
                    vt2, vv2 = self.v_t[j_v + 1], self.v_vals[j_v + 1]
                    v_out = vv1 + (vv2 - vv1) * (t - vt1) / (vt2 - vt1) if vt2 != vt1 else vv1
                else:
                    v_out = 0.0 if t > self.v_t[-1] else (self.v_vals[-1] if self.v_vals else 0.0)
            elif self.velocity_mode == 'power_law':
                v_out = self.vel_a * (max(0.0, h_out) ** self.vel_b)

            flow_og = 0.0
            flow_gb = 0.0

            active_ingress = (self._conductance_resolver(H_out)
                              if self._conductance_resolver is not None
                              else self.ingress_list)
            for ingress in active_ingress:
                src = getattr(ingress, 'source', 'outside')
                tgt = getattr(ingress, 'target', 'ground')
                if src == 'outside' and tgt == 'ground':
                    flow_og += ingress.compute_flow(H_out, H_in, v_source=v_out)
                elif src == 'ground' and tgt == 'basement':
                    flow_gb += ingress.compute_flow(H_in, H_basement)
                elif src == 'basement' and tgt == 'ground':
                    flow_gb -= ingress.compute_flow(H_basement, H_in)

            flow_ob = 0.0
            flow_os = 0.0
            if bi is not None:
                if sp is not None:
                    flow_os = bi.compute_flow(H_out, H_sump_abs, v_source=v_out)
                else:
                    flow_ob = bi.compute_flow(H_out, H_basement, v_source=v_out)

            vol_ground = (flow_og - flow_gb) * self.dt
            self.building.update_water_level(vol_ground, zone='ground')
            current_h_in = self.building.h_in

            current_h_sump = 0.0
            Q_s_bs = 0.0
            H_lift = 0.0
            Q_p = 0.0
            pump_state_t = 0

            if sp is not None:
                sump_depth = sp.overflow_level
                V_sump_full = sp.sump_area * sump_depth
                V_total = (sp.sump_area * min(sp.h_sump, sump_depth)
                           + (sp.sump_area + self.building.basement_area) * current_h_basement)
                H_lift = compute_lift_head(H_out, sp.sump_base_elevation)
                sp.pump_state = compute_pump_switch_state(
                    sp.h_sump, sp.pump_on_level, sp.pump_off_level, sp.pump_state)
                pump_state_t = sp.pump_state
                Q_p = compute_pump_flow(
                    sp.pump_state, sp.pump_availability,
                    sp.pump_shutoff_head, H_lift,
                    sp.pump_curve_coeff, sp.pipe_loss_coeff)
                dV = (flow_os + flow_gb - Q_p) * self.dt
                V_total = max(0.0, V_total + dV)
                if V_total <= V_sump_full:
                    sp.h_sump = V_total / sp.sump_area if sp.sump_area > 0 else 0.0
                    self.building.h_basement = 0.0
                else:
                    V_above = V_total - V_sump_full
                    h_above = V_above / (sp.sump_area + self.building.basement_area)
                    sp.h_sump = sump_depth + h_above
                    self.building.h_basement = h_above
                max_bsmt = max(0.0, self.building.basement_ceiling_elevation
                               - self.building.z_basement)
                if self.building.h_basement > max_bsmt:
                    excess = self.building.h_basement - max_bsmt
                    overflow_vol = excess * (sp.sump_area + self.building.basement_area)
                    self.building.h_basement = max_bsmt
                    sp.h_sump = sump_depth + max_bsmt
                    self.building.update_water_level(overflow_vol, zone='ground')
                current_h_sump = sp.h_sump
                current_h_basement = self.building.h_basement
            else:
                vol_basement = (flow_ob + flow_gb) * self.dt
                overflow = self.building.update_water_level(vol_basement, zone='basement')
                if overflow and overflow > 0.0:
                    self.building.update_water_level(overflow, zone='ground')
                current_h_basement = self.building.h_basement

            times.append(t)
            indoor_levels.append(current_h_in)
            basement_levels.append(current_h_basement)
            sump_levels.append(current_h_sump)

            _trace_perim = flow_os if sp is not None else flow_ob
            _trace['times'].append(t)
            _trace['H_out'].append(H_out)
            _trace['h_in'].append(current_h_in)
            _trace['h_basement'].append(current_h_basement)
            _trace['h_sump'].append(current_h_sump)
            _trace['H_lift'].append(H_lift)
            _trace['pump_state'].append(pump_state_t)
            _trace['Q_ext_b'].append(flow_og)
            _trace['Q_b_bs'].append(flow_gb)
            _trace['Q_ext_perimeter'].append(_trace_perim)
            _trace['Q_pump'].append(Q_p)
            _trace['Q_sump_overflow'].append(Q_s_bs)

            if progress_callback and total_steps > 0:
                try:
                    progress_callback(min(1.0, (step + 1) / (total_steps + 1)))
                except Exception:
                    pass

        self._last_trace = _trace

        has_basement = bool(getattr(self.building, 'basement_area', 0.0)
                            and self.building.basement_area > 0.0)
        has_sump = self.building.sump_pump is not None
        if has_basement and has_sump:
            return times, indoor_levels, basement_levels, sump_levels
        elif has_basement:
            return times, indoor_levels, basement_levels
        else:
            return times, indoor_levels


# ── I/O helpers ───────────────────────────────────────────────────────────────

def parse_combined_file(filepath):
    """Parse a 2- or 3-column CSV (time, depth[, velocity]).

    Returns (times, levels, velocities_or_None).  Inline comment lines
    (starting with #) and malformed rows are silently skipped.
    """
    times, levels, velocities = [], [], []
    has_velocity = None
    with open(filepath) as f:
        for raw in f:
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 2:
                continue
            try:
                t = float(parts[0])
                d = float(parts[1])
            except ValueError:
                continue
            if has_velocity is None:
                has_velocity = len(parts) >= 3
            times.append(t)
            levels.append(d)
            if has_velocity:
                velocities.append(float(parts[2]) if len(parts) >= 3 else 0.0)
    if not times:
        raise ValueError(f'No data found in external file: {filepath}')
    return times, levels, velocities if has_velocity else None


def parse_combined_text(text):
    """Parse a 2- or 3-column text block (time, depth[, velocity]).

    Returns (times, levels, velocities_or_None).
    """
    times, levels, velocities = [], [], []
    has_velocity = None
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 2:
            continue
        try:
            t = float(parts[0])
            d = float(parts[1])
        except ValueError:
            continue
        if has_velocity is None:
            has_velocity = len(parts) >= 3
        times.append(t)
        levels.append(d)
        if has_velocity:
            velocities.append(float(parts[2]) if len(parts) >= 3 else 0.0)
    if not times:
        raise ValueError('No data found in hydrograph text')
    return times, levels, velocities if has_velocity else None


def parse_external_text(text):
    """Parse a 2-column text block (time, level). Ignores any third column."""
    times, levels, _ = parse_combined_text(text)
    return times, levels


def parse_ingress_file(filepath):
    """Parse ingress from a positional CSV file: height, area, coeff[, name].

    Deprecated: prefer header-based CSV via fragility.parse_pathway_file().
    """
    import warnings
    with open(filepath) as f:
        return parse_ingress_text(f.read())


def sample_with_zero_padding(target_times, src_times, src_vals):
    """Interpolate src_vals onto target_times; pad with 0 beyond last src point."""
    if not src_times or not src_vals:
        return [0.0] * len(target_times)
    sampled = []
    j = 0
    for t in target_times:
        while j < len(src_times) - 1 and t >= src_times[j + 1]:
            j += 1
        if j < len(src_times) - 1:
            t1, v1 = src_times[j], src_vals[j]
            t2, v2 = src_times[j + 1], src_vals[j + 1]
            frac = (t - t1) / (t2 - t1) if t2 != t1 else 0.0
            sampled.append(v1 + frac * (v2 - v1))
        else:
            sampled.append(0.0 if t > src_times[-1] else src_vals[-1])
    return sampled


# ── data structures ───────────────────────────────────────────────────────────

@dataclass
class SimConfig:
    """All building geometry and run-control parameters for one simulation."""
    floor_area: float
    dt: float = 60.0                          # seconds
    basement_area: float = 0.0
    basement_floor_elevation: float = 0.0
    basement_ceiling_elevation: float = 0.0
    basement_connection_height: Optional[float] = None
    basement_connection_area: float = 0.0
    sumppump: Optional[SumpPump] = None
    n_replicates: int = 1
    random_seed: Optional[int] = None
    output_percentiles: Tuple[int, ...] = (10, 25, 50, 75, 90)
    velocity_mode: str = 'zero'                # 'zero' | 'power_law' | 'file'
    velocity_power_law_a: float = 1.5
    velocity_power_law_b: float = 0.5
    time_units: str = 'minutes'               # for display only
    compute_forces: bool = False
    building_width: float = 10.0
    drag_coeff: float = 1.0
    rho: float = 1000.0
    animate: bool = False
    verbose: bool = False


@dataclass
class Hydrograph:
    """External flood time series. All times are in seconds."""
    times: List[float]
    levels: List[float]
    vel_times: Optional[List[float]] = None
    velocities: Optional[List[float]] = None
    name: str = ''   # identifier (file stem for batch)


@dataclass
class SimResult:
    """Output of one deterministic simulation."""
    times: List[float]
    h_in: List[float]
    h_basement: List[float]
    h_sump: List[float]
    peak_h_in: float
    peak_h_basement: float
    peak_h_sump: float
    peak_h_ext: float
    v_peak_ext: float
    total_volume_in: float
    trace: dict = field(default_factory=dict)


# ── public API ────────────────────────────────────────────────────────────────

def run(config: SimConfig, hydro: Hydrograph, pathways: list, *,
        basement_pathway: Optional[IngressPathway] = None,
        conductance_resolver=None) -> SimResult:
    """Run one deterministic simulation and return SimResult.

    Parameters
    ----------
    config            : SimConfig — building geometry and run parameters
    hydro             : Hydrograph — external flood event (times in seconds)
    pathways          : List[IngressPathway] — exterior→ground-floor openings
    basement_pathway  : optional IngressPathway for exterior→basement perimeter
    conductance_resolver : optional callable(h_ext) → List[IngressPathway],
                          used by fragility.py to inject per-replicate active paths
    """
    building = Building(floor_area=config.floor_area)

    if config.basement_area > 0.0:
        building.basement_area = config.basement_area
        building.z_basement = config.basement_floor_elevation
        building.basement_ceiling_elevation = config.basement_ceiling_elevation

    if basement_pathway is not None and config.basement_area > 0.0:
        building.basement_ingress = basement_pathway

    if config.sumppump is not None and config.basement_area > 0.0:
        building.sump_pump = copy.deepcopy(config.sumppump)

    ing = list(pathways)
    if (config.basement_connection_height is not None
            and config.basement_connection_area > 0.0
            and config.basement_area > 0.0):
        ing.append(IngressPathway(
            height=config.basement_connection_height,
            area=config.basement_connection_area,
            coeff=1.0, name='ground-basement-conn',
            source='ground', target='basement',
        ))

    sim = Simulation(
        building, ing,
        hydro.times, hydro.levels,
        dt=config.dt,
        external_vel_times=hydro.vel_times,
        external_velocities=hydro.velocities,
        conductance_resolver=conductance_resolver,
        velocity_mode=config.velocity_mode,
        vel_a=config.velocity_power_law_a,
        vel_b=config.velocity_power_law_b,
    )
    raw = sim.run()

    if len(raw) == 4:
        times, h_in, h_basement, h_sump = raw
    elif len(raw) == 3:
        times, h_in, h_basement = raw
        h_sump = [0.0] * len(times)
    else:
        times, h_in = raw
        h_basement = []
        h_sump = []

    sampled_ext = sample_with_zero_padding(times, hydro.times, hydro.levels)
    peak_h_ext = max(sampled_ext) if sampled_ext else 0.0
    peak_h_in = max(h_in, default=0.0)
    peak_h_basement = max(h_basement, default=0.0) if h_basement else 0.0
    peak_h_sump = max(h_sump, default=0.0) if h_sump else 0.0

    if config.velocity_mode == 'file' and hydro.vel_times and hydro.velocities:
        sampled_vel = sample_with_zero_padding(times, hydro.vel_times, hydro.velocities)
        v_peak_ext = max(sampled_vel) if sampled_vel else 0.0
    elif config.velocity_mode == 'power_law':
        v_peak_ext = (config.velocity_power_law_a * (max(sampled_ext) ** config.velocity_power_law_b)
                      if sampled_ext else 0.0)
    else:
        v_peak_ext = 0.0

    total_volume_in = 0.0
    for idx in range(1, len(h_in)):
        dh = h_in[idx] - h_in[idx - 1]
        if dh > 0:
            total_volume_in += dh * config.floor_area

    return SimResult(
        times=times,
        h_in=h_in,
        h_basement=h_basement,
        h_sump=h_sump,
        peak_h_in=peak_h_in,
        peak_h_basement=peak_h_basement,
        peak_h_sump=peak_h_sump,
        peak_h_ext=peak_h_ext,
        v_peak_ext=v_peak_ext,
        total_volume_in=total_volume_in,
        trace=sim._last_trace or {},
    )


# ── legacy text-format parser (kept for backward compatibility) ───────────────

def parse_ingress_text(text):
    """Parse ingress from a plain text block: height, area, coeff[, name].

    Raises ValueError for extra columns (routing or legacy always_open).
    Deprecated: prefer header-based CSV via fragility.parse_pathway_file().
    """
    import warnings
    ingress = []
    n_skipped = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',') if p.strip()]
        if len(parts) < 3:
            n_skipped += 1
            continue
        if len(parts) > 4:
            raise ValueError(
                "Unsupported ingress text format: expected "
                "height, area, coeff[,name] with no extra columns "
                "(legacy always_open and source/target fields are not supported)"
            )
        try:
            h     = float(parts[0])
            area  = float(parts[1])
            coeff = float(parts[2])
        except ValueError as exc:
            warnings.warn(
                f"Non-numeric value in ingress text at line {lineno}: {exc}",
                stacklevel=2)
            n_skipped += 1
            continue
        name = parts[3] if len(parts) >= 4 else f"ing{len(ingress)}"
        ingress.append(IngressPathway(height=h, area=area, coeff=coeff, name=name))
    if n_skipped:
        warnings.warn(f"{n_skipped} malformed line(s) skipped in ingress text",
                      stacklevel=2)
    if not ingress:
        raise ValueError('No ingress entries provided')
    return ingress
