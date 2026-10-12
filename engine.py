#!/usr/bin/env python3
"""engine.py — canonical single-simulation runner.

Public API
----------
Data structures:
    SimConfig     — building geometry, timestep, and run-control parameters
    Hydrograph    — external flood time series (times in seconds)
    SimResult     — deterministic simulation output

Entry point (the only place a Building and Simulation are assembled):
    run(config, hydro, pathways, *, conductance_resolver, progress_callback) → SimResult

Hydrograph input:
    read_hydrograph, hydrograph_from_columns, parse_combined_file, parse_combined_text

Exterior series on the simulation grid:
    exterior_series, sample_with_zero_padding

Low-level classes:
    Building, IngressPathway, Simulation
"""

import copy
import math
import os
import warnings
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from pump import (
    SumpPump,
    compute_lift_head,
    compute_pump_flow,
    compute_pump_switch_state,
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
        h_src = max(0.0, float(H_source) - sill)
        if h_src > 0.0:
            # Velocity head acts only when the source water reaches the sill.
            h_src += float(v_source) ** 2 / (2.0 * g)
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
                 velocity_mode='zero', vel_a=1.5, vel_b=0.5,
                 floor_datum=0.0):
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
        self.floor_datum = float(floor_datum)
        self._last_trace = None
        self._initial_h_in = building.h_in
        self._initial_h_basement = building.h_basement
        if building.sump_pump is not None:
            self._initial_h_sump = building.sump_pump.h_sump
            self._initial_pump_state = building.sump_pump.pump_state
        else:
            self._initial_h_sump = 0.0
            self._initial_pump_state = 0

    # ── lower compartment (basement + sump) helpers ──────────────────────────

    def _max_basement_depth(self):
        return max(0.0, self.building.basement_ceiling_elevation - self.building.z_basement)

    @staticmethod
    def _pump_step(sp, H_out):
        """Update the pump switch state; return (H_lift, pump_state, Q_pump)."""
        H_lift = compute_lift_head(H_out, sp.sump_base_elevation)
        sp.pump_state = compute_pump_switch_state(
            sp.h_sump, sp.pump_on_level, sp.pump_off_level, sp.pump_state)
        Q_p = compute_pump_flow(
            sp.pump_state, sp.pump_availability,
            sp.pump_shutoff_head, H_lift,
            sp.pump_curve_coeff, sp.pipe_loss_coeff)
        return H_lift, sp.pump_state, Q_p

    def _drain_below(self, volume, basement, sump):
        """Take `volume` from the full compartments below a merged surface,
        basement first, then the sump pit."""
        if basement:
            stored = self.building.basement_area * self.building.h_basement
            self.building.h_basement = max(0.0, stored - volume) / self.building.basement_area
            volume = max(0.0, volume - stored)
        sp = self.building.sump_pump
        if sump and volume > 0.0:
            stored = sp.sump_area * sp.h_sump
            sp.h_sump = max(0.0, stored - volume) / sp.sump_area

    def run(self, progress_callback=None):
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
        has_basement = self.building.basement_area > 0.0
        max_bsmt = self._max_basement_depth()
        if sp is not None:
            sp.check_geometry(self.building.z_basement)
            sump_depth = sp.depth(self.building.z_basement)
            sump_opening = IngressPathway(
                height=self.building.z_basement,
                area=sp.opening_area if sp.opening_area is not None else sp.sump_area,
                coeff=sp.opening_coeff, name='sump-opening',
                source='basement', target='sump')

        _trace = {
            'times': [], 'H_out': [], 'h_in': [], 'h_basement': [], 'h_sump': [],
            'H_lift': [], 'pump_state': [], 'Q_ext_b': [], 'Q_b_bs': [],
            'Q_ext_perimeter': [], 'Q_pump': [], 'Q_sump_overflow': [], 'Q_b_sump': [],
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

            # Compartments, bottom to top: sump pit (below the basement floor),
            # basement, ground floor.  A compartment that is full and has
            # water in the compartment above is part of that compartment: it
            # shares its free surface, its pathways discharge against that
            # surface and its links to that compartment carry no flow.
            bsmt_merged = (has_basement
                           and current_h_basement >= max_bsmt
                           and current_h_in > 0.0)
            sump_merged = (sp is not None
                           and sp.h_sump >= sump_depth
                           and (current_h_basement > 0.0 or bsmt_merged))
            H_in_abs = current_h_in + self.floor_datum
            H_basement = H_in_abs if bsmt_merged else self.building.z_basement + current_h_basement
            H_sump_abs = H_basement if sump_merged else (
                sp.sump_base_elevation + sp.h_sump if sp is not None else 0.0)

            flow_og = 0.0
            flow_gb = 0.0
            flow_ob = 0.0
            flow_os = 0.0

            active_ingress = list(self.ingress_list)
            if self._conductance_resolver is not None:
                active_ingress.extend(self._conductance_resolver(H_out))
            for ingress in active_ingress:
                src = getattr(ingress, 'source', 'outside')
                tgt = getattr(ingress, 'target', 'ground')
                if src == 'outside' and tgt == 'ground':
                    flow_og += ingress.compute_flow(H_out, H_in_abs, v_source=v_out)
                elif bsmt_merged and src != 'outside':
                    continue
                elif src == 'ground' and tgt == 'basement':
                    flow_gb += ingress.compute_flow(H_in_abs, H_basement)
                elif src == 'basement' and tgt == 'ground':
                    flow_gb -= ingress.compute_flow(H_basement, H_in_abs)
                elif src == 'outside' and tgt == 'basement':
                    if sp is not None:
                        flow_os += ingress.compute_flow(H_out, H_sump_abs, v_source=v_out)
                    else:
                        flow_ob += ingress.compute_flow(H_out, H_basement, v_source=v_out)

            current_h_sump = 0.0
            Q_s_bs = 0.0
            Q_b_s = 0.0
            H_lift = 0.0
            Q_p = 0.0
            pump_state_t = 0
            if sp is not None:
                H_lift, pump_state_t, Q_p = self._pump_step(sp, H_out)
                if not sump_merged:
                    # Basement water drains into the pit, never more than the
                    # pit can take or the basement side holds in one step.
                    Q_b_s = sump_opening.compute_flow(H_basement, H_sump_abs)
                    room = sp.sump_area * (sump_depth - sp.h_sump)
                    held = self.building.basement_area * current_h_basement
                    if bsmt_merged:
                        held += self.building.floor_area * current_h_in
                    Q_b_s = min(Q_b_s, max(0.0, min(room, held)) / self.dt)

            # Net inflow (m³/s) of each compartment.
            Q_ground = flow_og - flow_gb
            Q_bsmt = flow_ob + flow_gb
            if sp is not None:
                Q_bsmt -= Q_b_s
            Q_sump = flow_os + Q_b_s - Q_p
            if sump_merged:
                # A full pit passes its net inflow through its opening:
                # recorded as spill (up) or drainage (down) for diagnostics.
                Q_s_bs = max(0.0, Q_sump)
                Q_b_s = max(0.0, -Q_sump)

            if bsmt_merged:
                # Ground floor + basement (+ full sump) share the ground-floor
                # surface; a deficit is taken from the compartments below.
                Q_group = Q_ground + Q_bsmt + (Q_sump if sump_merged else 0.0)
                h_new = current_h_in + Q_group * self.dt / self.building.floor_area
                if h_new >= 0.0:
                    self.building.h_in = h_new
                else:
                    self.building.h_in = 0.0
                    self._drain_below(-h_new * self.building.floor_area,
                                      basement=True, sump=sump_merged)
            else:
                self.building.update_water_level(Q_ground * self.dt, zone='ground')
                if sump_merged:
                    # Basement + full sump share the basement surface.
                    h_new = current_h_basement + (Q_bsmt + Q_sump) * self.dt / self.building.basement_area
                    if h_new < 0.0:
                        self.building.h_basement = 0.0
                        self._drain_below(-h_new * self.building.basement_area,
                                          basement=False, sump=True)
                    elif h_new > max_bsmt:
                        self.building.h_basement = max_bsmt
                        self.building.update_water_level(
                            (h_new - max_bsmt) * self.building.basement_area, zone='ground')
                    else:
                        self.building.h_basement = h_new
                elif has_basement:
                    overflow = self.building.update_water_level(Q_bsmt * self.dt, zone='basement')
                    if overflow and overflow > 0.0:
                        self.building.update_water_level(overflow, zone='ground')

            if sp is not None and not sump_merged:
                h_s = sp.h_sump + Q_sump * self.dt / sp.sump_area
                if h_s < 0.0:
                    # The pump cannot remove more water than the sump holds.
                    Q_p = max(0.0, Q_p + h_s * sp.sump_area / self.dt)
                    h_s = 0.0
                if h_s > sump_depth:
                    # A full pit spills onto the basement floor.
                    spill = (h_s - sump_depth) * sp.sump_area
                    Q_s_bs = spill / self.dt
                    h_s = sump_depth
                    overflow = self.building.update_water_level(spill, zone='basement')
                    if overflow and overflow > 0.0:
                        self.building.update_water_level(overflow, zone='ground')
                sp.h_sump = h_s

            current_h_in = self.building.h_in
            current_h_basement = self.building.h_basement
            if sp is not None:
                current_h_sump = sp.h_sump

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
            _trace['Q_b_sump'].append(Q_b_s)

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

TIME_UNIT_SECONDS = {'seconds': 1.0, 'minutes': 60.0, 'hours': 3600.0}


def parse_combined_text(text, source='hydrograph text'):
    """Parse a 2- or 3-column text block (time, depth[, velocity]).

    Returns (times, levels, velocities_or_None).  Inline comment lines
    (starting with #) and malformed rows are silently skipped.
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
        raise ValueError(f'No data found in {source}')
    return times, levels, velocities if has_velocity else None


def parse_combined_file(filepath):
    """Parse a 2- or 3-column CSV file (time, depth[, velocity])."""
    with open(filepath) as f:
        return parse_combined_text(f.read(), source=f'external file: {filepath}')


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
    """All building geometry and run-control parameters for one simulation.

    All elevations are in the external-ground frame (z=0 = external ground).
    `basement_ceiling_elevation` defaults to `floor_datum` (ceiling flush with
    internal floor) — override only if the basement ceiling is not flush.
    """
    floor_area: float
    dt: float = 60.0                          # seconds
    basement_area: float = 0.0
    basement_floor_elevation: float = 0.0
    basement_ceiling_elevation: Optional[float] = None
    basement_connection_height: Optional[float] = None
    basement_connection_area: float = 0.0
    basement_connection_coeff: float = 0.6
    sumppump: Optional[SumpPump] = None
    n_replicates: int = 1
    random_seed: Optional[int] = None
    output_percentiles: Tuple[int, ...] = (10, 25, 50, 75, 90)
    velocity_mode: str = 'zero'                # 'zero' | 'power_law' | 'file'
    velocity_power_law_a: float = 1.5
    velocity_power_law_b: float = 0.5
    time_units: str = 'minutes'               # units of hydrograph files and display
    compute_forces: bool = False
    building_width: float = 10.0
    drag_coeff: float = 1.0
    rho: float = 1000.0
    animate: bool = False
    verbose: bool = False
    floor_datum: float = 0.0   # internal floor elevation above external ground (m)

    def __post_init__(self):
        if self.basement_ceiling_elevation is None:
            self.basement_ceiling_elevation = self.floor_datum


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

def hydrograph_from_columns(times, levels, velocities=None, *,
                            time_units='minutes', velocity_mode='zero', name=''):
    """Build a Hydrograph from parsed columns given in `time_units`.

    Velocities are kept only for velocity_mode='file', which requires them.
    """
    times_s = [t * TIME_UNIT_SECONDS[time_units] for t in times]
    vel_times, vel = None, None
    if velocity_mode == 'file':
        if velocities is None:
            raise ValueError(
                f"velocity_mode='file' requires a 3-column hydrograph "
                f"(time, depth, velocity) but {name or 'the input'} has only 2 columns.")
        vel_times, vel = list(times_s), list(velocities)
    return Hydrograph(times=times_s, levels=list(levels),
                      vel_times=vel_times, velocities=vel, name=name)


def read_hydrograph(filepath, *, time_units='minutes', velocity_mode='zero'):
    """Read a hydrograph CSV into a Hydrograph (times converted to seconds)."""
    times, levels, velocities = parse_combined_file(filepath)
    return hydrograph_from_columns(
        times, levels, velocities, time_units=time_units,
        velocity_mode=velocity_mode,
        name=os.path.splitext(os.path.basename(filepath))[0])


def exterior_series(config: SimConfig, hydro: Hydrograph, times) -> Tuple[list, list]:
    """Return (h_ext, v_ext): exterior depth and velocity sampled on `times`."""
    h_ext = sample_with_zero_padding(times, hydro.times, hydro.levels)
    if config.velocity_mode == 'file' and hydro.vel_times and hydro.velocities:
        v_ext = sample_with_zero_padding(times, hydro.vel_times, hydro.velocities)
    elif config.velocity_mode == 'power_law':
        v_ext = [config.velocity_power_law_a * (max(0.0, h) ** config.velocity_power_law_b)
                 for h in h_ext]
    else:
        v_ext = [0.0] * len(times)
    return h_ext, v_ext


def _build_building(config: SimConfig) -> Building:
    building = Building(floor_area=config.floor_area)
    if config.basement_area > 0.0:
        building.basement_area = config.basement_area
        building.z_basement = config.basement_floor_elevation
        building.basement_ceiling_elevation = config.basement_ceiling_elevation
        if config.sumppump is not None:
            building.sump_pump = copy.deepcopy(config.sumppump)
    return building


def _internal_pathways(config: SimConfig) -> List[IngressPathway]:
    """Pathways defined by the building geometry: the ground↔basement bypass."""
    if (config.basement_area > 0.0
            and config.basement_connection_height is not None
            and config.basement_connection_area > 0.0):
        return [IngressPathway(
            height=config.basement_connection_height,
            area=config.basement_connection_area,
            coeff=config.basement_connection_coeff, name='ground-basement-conn',
            source='ground', target='basement',
        )]
    return []


class PumpStepWarning(UserWarning):
    """The integration step is too large for the sump pump to be stable."""


def _check_pump_step(config: SimConfig) -> None:
    """Warn when Δt exceeds 0.5 · A_sump · h_on / Q_p,max (pump at zero lift).

    The explicit scheme is only conditionally stable with a pump: a coarse
    step can empty the switch-on storage in one step.  The step is not
    changed; the user is told the largest stable value.
    """
    sp = config.sumppump
    if sp is None or config.basement_area <= 0.0:
        return
    dt_max = sp.max_stable_dt()
    if config.dt <= dt_max:
        return
    unit = TIME_UNIT_SECONDS[config.time_units]
    warnings.warn(
        f"Integration step Δt = {config.dt:g} s is too large for the sump pump: "
        f"the scheme is only conditionally stable and a single step can empty the "
        f"pump's switch-on storage.  Use Δt ≤ 0.5·A_sump·h_on / Q_p,max = "
        f"0.5 × {sp.sump_area:g} m² × {sp.pump_on_level:g} m / "
        f"{sp.max_pump_flow():.4g} m³/s = {dt_max:.3g} s "
        f"({dt_max / unit:.3g} {config.time_units}; Q_p,max at h_lift = 0).  "
        f"Results with the current step may show spurious pump cycling and pit spills.",
        PumpStepWarning, stacklevel=3)


def run(config: SimConfig, hydro: Hydrograph, pathways=(), *,
        conductance_resolver=None, progress_callback=None) -> SimResult:
    """Run one simulation and return SimResult.

    This is the only place where a Building and its Simulation are assembled.

    Parameters
    ----------
    config               : SimConfig — building geometry and run parameters
    hydro                : Hydrograph — external flood event (times in seconds)
    pathways             : IngressPathways with fixed conductance (any source/target)
    conductance_resolver : optional callable(h_ext) → List[IngressPathway] adding
                           the pathways whose conductance varies with the head
                           (fragility.make_conductance_resolver)
    progress_callback    : optional callable(fraction) forwarded to Simulation.run
    """
    _check_pump_step(config)
    sim = Simulation(
        _build_building(config), list(pathways) + _internal_pathways(config),
        hydro.times, hydro.levels,
        dt=config.dt,
        external_vel_times=hydro.vel_times,
        external_velocities=hydro.velocities,
        conductance_resolver=conductance_resolver,
        velocity_mode=config.velocity_mode,
        vel_a=config.velocity_power_law_a,
        vel_b=config.velocity_power_law_b,
        floor_datum=config.floor_datum,
    )
    raw = sim.run(progress_callback=progress_callback)

    if len(raw) == 4:
        times, h_in, h_basement, h_sump = raw
    elif len(raw) == 3:
        times, h_in, h_basement = raw
        h_sump = []
    else:
        times, h_in = raw
        h_basement = []
        h_sump = []

    h_ext, v_ext = exterior_series(config, hydro, times)

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
        peak_h_in=max(h_in, default=0.0),
        peak_h_basement=max(h_basement, default=0.0),
        peak_h_sump=max(h_sump, default=0.0),
        peak_h_ext=max(h_ext, default=0.0),
        v_peak_ext=max(v_ext, default=0.0),
        total_volume_in=total_volume_in,
        trace=sim._last_trace or {},
    )
