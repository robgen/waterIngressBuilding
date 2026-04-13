#!/usr/bin/env python3
import math
import argparse
import os
import sys
import csv
import warnings

import forces
from pump import (SumpPump, compute_sump_overflow, compute_pump_switch_state,
                  compute_lift_head, compute_pump_flow)

"""Headless runner for Flood Ingress Simulation

This script replaces the GUI. It reads two files (external levels CSV and ingress paths file),
runs the simulation and writes three PNGs into the output directory:
 - external_preview.png
 - ingress_preview.png
 - simulation_result.png

Usage:
    python3 main.py --external example_external_levels.csv --ingress example_ingress_paths.txt

"""

# Model classes
class Building:
    def __init__(self, floor_area):
        self.floor_area = floor_area
        # ground-floor interior depth above ground-floor datum
        self.h_in = 0.0
        # optional basement compartment
        self.basement_area = 0.0
        # basement depth above basement floor
        self.h_basement = 0.0
        # basement floor elevation relative to ground-floor datum (m).
        # negative values place the basement below the ground-floor datum.
        self.z_basement = 0.0
        # basement ceiling elevation on the same datum (default: ground-floor datum = 0.0)
        # water in the basement cannot rise above this elevation; the maximum
        # basement depth is (basement_ceiling_elevation - z_basement)
        self.basement_ceiling_elevation = 0.0

        # Lumped exterior-perimeter-to-basement opening (IngressPathway or None).
        # This represents exterior water around the basement perimeter entering the
        # basement system.  It is kept separate from the user-authored ingress file
        # (which must contain exterior→building pathways only) to avoid the
        # double-counting problem described in spec section 16.2.
        #
        # Routing rule (spec section 16.3):
        #   • When no sump is configured: this pathway feeds the basement directly.
        #   • When a SumpPump is configured: this pathway is redirected to the sump.
        #   The building-to-basement connection always bypasses the sump.
        self.basement_ingress = None  # IngressPathway or None

        # Optional sump+pump system (SumpPump instance or None).
        # When set, the basement_ingress pathway is redirected to the sump chamber.
        self.sump_pump = None  # SumpPump or None

    def update_water_level(self, volume_change, zone='ground'):
        """Apply a volume change (m^3) to a zone: 'ground' or 'basement'."""
        if zone == 'ground':
            if self.floor_area <= 0:
                return
            delta_h = volume_change / self.floor_area
            self.h_in += delta_h
            if self.h_in < 0:
                self.h_in = 0.0
            # no overflow concept for ground in this simple model
            return 0.0
        elif zone == 'basement':
            if self.basement_area <= 0:
                return 0.0
            delta_h = volume_change / self.basement_area
            self.h_basement += delta_h
            if self.h_basement < 0:
                self.h_basement = 0.0
                return 0.0
            # enforce a maximum basement depth implied by the ceiling elevation
            max_depth = max(0.0, self.basement_ceiling_elevation - self.z_basement)
            if self.h_basement > max_depth:
                # compute overflow volume that cannot be stored in basement
                overflow_h = self.h_basement - max_depth
                overflow_vol = overflow_h * self.basement_area
                # clamp basement to max depth
                self.h_basement = max_depth
                return overflow_vol
            return 0.0
        else:
            raise ValueError(f'Unknown zone: {zone}')

class IngressPathway:
    def __init__(self, height, area, coeff, name="Opening", source='outside', target='ground'):
        """An ingress pathway (orifice/opening).

        Arguments:
            height: elevation of the orifice (same units as water levels)
            area: opening area (m^2)
            coeff: discharge coefficient
            name: optional name
        """
        self.height = float(height)
        self.area = float(area)
        self.coeff = float(coeff)
        self.name = name
        # semantic endpoints: 'outside'|'ground'|'basement'
        self.source = source
        self.target = target

    def compute_flow(self, H_source, H_target, v_source=0.0):
        """Compute volumetric flow (m^3 / time-unit) using absolute surface heads.

        H_source and H_target are absolute water surface elevations (m) on the
        source and target sides measured on a common datum. The pathway sill is
        `self.height` on the same datum. If both sides are below the sill then
        Q=0. Otherwise the orifice-like law is evaluated with the head
        difference delta_H = H_source - H_target.
        """
        # If the opening is above the water on both sides, there is no flow.
        if H_source < self.height and H_target < self.height:
            return 0.0

        # The submerged/open test above intentionally uses the raw surface
        # elevations (no dynamic head). However, when computing the driving
        # head for the orifice we optionally include a hydrodynamic correction
        # from an external velocity at the source side:  v^2/(2g).
        g = 9.81
        delta_H_eff = float(H_source) + (float(v_source) ** 2) / (2.0 * g) - float(H_target)
        if delta_H_eff == 0.0:
            return 0.0

        flow_rate = self.coeff * self.area * math.sqrt(2.0 * g * abs(delta_H_eff))
        return flow_rate if delta_H_eff > 0.0 else -flow_rate

class Simulation:
    def __init__(self, building, ingress_list, external_times, external_levels, dt=60.0, external_vel_times=None, external_velocities=None):
        """Create a simulation.

        Args:
            building: Building instance
            ingress_list: list of IngressPathway
            external_times: list of times for external hydrograph
            external_levels: list of external levels
            dt: simulation timestep in same units as external_times (default 60.0)
        """
        self.building = building
        self.ingress_list = ingress_list
        self.t_ext = external_times
        self.h_ext = external_levels
        # optional external velocity hydrograph (separate timebase allowed)
        self.v_t = external_vel_times if external_vel_times is not None else []
        self.v_vals = external_velocities if external_velocities is not None else []
        # simulation timestep (seconds or same units as t_ext). Default is 60.
        self.dt = float(dt) if dt is not None else 60.0
        # populated after run() — per-step trace consumed by diagnostics layer
        self._last_trace = None
        # snapshot of building state at construction time so run() is idempotent
        self._initial_h_in = building.h_in
        self._initial_h_basement = building.h_basement
        if building.sump_pump is not None:
            self._initial_h_sump = building.sump_pump.h_sump
            self._initial_pump_state = building.sump_pump.pump_state
        else:
            self._initial_h_sump = 0.0
            self._initial_pump_state = 0

    def run(self, progress_callback=None, verbose=False):
        """Run the simulation and return results.

        Return value (backwards-compatible):
            (times, indoor_levels)                        — no basement, no sump
            (times, indoor_levels, basement_levels)       — basement, no sump
            (times, indoor_levels, basement_levels,
             sump_levels)                                 — basement + sump

        Routing convention (spec section 16.3):
            • ingress_list  — exterior→building pathways only (unchanged)
            • building.basement_ingress — lumped exterior perimeter opening:
                  if no sump → feeds basement directly (Q_ext_b)
                  if sump    → redirected to sump (Q_ext_s)
            • building-to-basement connection (ground↔basement in ingress_list)
              always bypasses the sump
        """
        # Reset building to its state at Simulation construction so run() is idempotent
        self.building.h_in = self._initial_h_in
        self.building.h_basement = self._initial_h_basement
        if self.building.sump_pump is not None:
            self.building.sump_pump.h_sump = self._initial_h_sump
            self.building.sump_pump.pump_state = self._initial_pump_state
        # Reset velocity interpolation index (fixes stale index on second call)
        self._vel_index = 0

        indoor_levels = []
        times = []
        basement_levels = []
        sump_levels = []

        current_h_in = self.building.h_in
        current_h_basement = self.building.h_basement

        sp = self.building.sump_pump          # SumpPump or None
        bi = self.building.basement_ingress   # IngressPathway or None (lumped perimeter)

        _trace = {
            'times': [], 'H_out': [], 'h_in': [], 'h_basement': [], 'h_sump': [],
            'H_lift': [], 'pump_state': [], 'Q_ext_b': [], 'Q_b_bs': [],
            'Q_ext_perimeter': [], 'Q_pump': [], 'Q_sump_overflow': [],
            'sump_configured': sp is not None,  # scalar flag for diagnostics layer
        }

        start_time = self.t_ext[0] if len(self.t_ext) > 0 else 0.0
        end_time = self.t_ext[-1] if len(self.t_ext) > 0 else 0.0
        total_steps = max(1, int(math.ceil((end_time - start_time) / max(self.dt, 1e-9))))
        i = 0

        for step in range(total_steps + 1):
            t = start_time + step * self.dt
            if t > end_time:
                t = end_time

            # interpolate external hydrograph
            if i < len(self.t_ext) - 1:
                while i < len(self.t_ext) - 1 and t >= self.t_ext[i+1]:
                    i += 1
            if i < len(self.t_ext) - 1:
                t1, h1 = self.t_ext[i], self.h_ext[i]
                t2, h2 = self.t_ext[i+1], self.h_ext[i+1]
                h_out = h1 + (h2 - h1) * (t - t1) / (t2 - t1) if t2 != t1 else h1
            else:
                h_out = self.h_ext[-1] if len(self.h_ext) > 0 else 0.0

            H_out      = h_out
            H_in       = current_h_in
            H_basement = self.building.z_basement + current_h_basement
            # Absolute head at sump water surface (sump base + sump depth)
            H_sump_abs = (sp.sump_base_elevation + sp.h_sump) if sp is not None else 0.0

            # interpolate external velocity
            v_out = 0.0
            if self.v_t and self.v_vals:
                j_v = self._vel_index
                while j_v < len(self.v_t) - 1 and t >= self.v_t[j_v + 1]:
                    j_v += 1
                self._vel_index = j_v
                if j_v < len(self.v_t) - 1:
                    vt1, vv1 = self.v_t[j_v], self.v_vals[j_v]
                    vt2, vv2 = self.v_t[j_v+1], self.v_vals[j_v+1]
                    v_out = vv1 + (vv2 - vv1) * (t - vt1) / (vt2 - vt1) if vt2 != vt1 else vv1
                else:
                    v_out = 0.0 if t > self.v_t[-1] else (self.v_vals[-1] if self.v_vals else 0.0)

            # ── ingress flows ────────────────────────────────────────────────
            # ingress_list: exterior→building pathways only
            flow_og = 0.0   # outside → ground floor
            flow_gb = 0.0   # ground ↔ basement connection (positive = ground→basement)

            for ingress in self.ingress_list:
                src = getattr(ingress, 'source', 'outside')
                tgt = getattr(ingress, 'target', 'ground')
                if src == 'outside' and tgt == 'ground':
                    flow_og += ingress.compute_flow(H_out, H_in, v_source=v_out)
                elif src == 'ground' and tgt == 'basement':
                    flow_gb += ingress.compute_flow(H_in, H_basement)
                elif src == 'basement' and tgt == 'ground':
                    flow_gb -= ingress.compute_flow(H_basement, H_in)
                # other source/target pairs are ignored (future-proofing)

            # Lumped exterior perimeter opening — routing depends on sump config
            flow_ob = 0.0   # outside → basement direct (no sump)
            flow_os = 0.0   # outside → sump          (sump enabled)
            if bi is not None:
                if sp is not None:
                    flow_os = bi.compute_flow(H_out, H_sump_abs, v_source=v_out)
                else:
                    flow_ob = bi.compute_flow(H_out, H_basement, v_source=v_out)

            # ── ground-floor update ──────────────────────────────────────────
            vol_ground = (flow_og - flow_gb) * self.dt
            self.building.update_water_level(vol_ground, zone='ground')
            current_h_in = self.building.h_in

            # ── sump/pump update ─────────────────────────────────────────────
            current_h_sump = 0.0
            Q_s_bs = 0.0
            H_lift = 0.0
            Q_p = 0.0
            pump_state_t = 0
            if sp is not None:
                H_lift = compute_lift_head(H_out, sp.sump_base_elevation)
                sp.pump_state = compute_pump_switch_state(
                    sp.h_sump, sp.pump_on_level, sp.pump_off_level, sp.pump_state)
                pump_state_t = sp.pump_state
                Q_p = compute_pump_flow(
                    sp.pump_state, sp.pump_availability,
                    sp.pump_shutoff_head, H_lift,
                    sp.pump_curve_coeff, sp.pipe_loss_coeff)
                Q_s_bs = compute_sump_overflow(
                    sp.h_sump, sp.overflow_level,
                    sp.overflow_coeff, sp.overflow_exponent)
                delta_h = (flow_os - Q_p - Q_s_bs) * self.dt / sp.sump_area
                sp.h_sump = max(0.0, sp.h_sump + delta_h)
                current_h_sump = sp.h_sump

            # ── basement update ──────────────────────────────────────────────
            # flow_ob: perimeter inflow when no sump (0 when sump active)
            # Q_s_bs: sump overflow into basement (0 when no sump)
            vol_basement = (flow_ob + flow_gb + Q_s_bs) * self.dt
            overflow = self.building.update_water_level(vol_basement, zone='basement')
            if overflow and overflow > 0.0:
                self.building.update_water_level(overflow, zone='ground')
            current_h_basement = self.building.h_basement

            times.append(t)
            indoor_levels.append(current_h_in)
            basement_levels.append(current_h_basement)
            sump_levels.append(current_h_sump)

            # per-step trace (consumed by diagnostics layer — no replay needed)
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
            if verbose and (step + 1) % 1000 == 0:
                print(f"Progress: {min(100, int(100*(step+1)/(total_steps+1)))}%")

        # Store trace for diagnostics layer (eliminates replay loop)
        self._last_trace = _trace

        # Backwards-compatible return tuple
        has_basement = bool(getattr(self.building, 'basement_area', 0.0)
                            and self.building.basement_area > 0.0)
        has_sump = self.building.sump_pump is not None
        if has_basement and has_sump:
            return times, indoor_levels, basement_levels, sump_levels
        elif has_basement:
            return times, indoor_levels, basement_levels
        else:
            return times, indoor_levels

def parse_external_file(filepath):
    times = []
    levels = []
    with open(filepath, 'r') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            parts = s.split(',')
            if len(parts) < 2:
                continue
            try:
                t_val = float(parts[0])
                h_val = float(parts[1])
            except ValueError:
                continue
            times.append(t_val)
            levels.append(h_val)
    if not times:
        raise ValueError(f"No data found in external file: {filepath}")
    return times, levels


def sample_with_zero_padding(target_times, src_times, src_vals):
    """Interpolate src_vals defined at src_times onto target_times.

    For t beyond the last src_time, pad with zero (explicit zero-padding).
    This is factored out so tests can import and validate sampling behaviour.
    """
    sampled = []
    if not src_times or not src_vals:
        return [0.0 for _ in target_times]
    j = 0
    for t in target_times:
        while j < len(src_times) - 1 and t >= src_times[j+1]:
            j += 1
        if j < len(src_times) - 1:
            t1, v1 = src_times[j], src_vals[j]
            t2, v2 = src_times[j+1], src_vals[j+1]
            if t2 != t1:
                frac = (t - t1) / (t2 - t1)
                sampled.append(v1 + frac * (v2 - v1))
            else:
                sampled.append(v1)
        else:
            # beyond last src timestamp -> pad with zero
            if t > src_times[-1]:
                sampled.append(0.0)
            else:
                sampled.append(src_vals[-1])
    return sampled


def parse_velocity_file(filepath):
    """Parse external velocity file (time,velocity) into two lists.

    Short files are allowed; when interpolating later any times beyond the
    last velocity timestamp will be treated as zero velocity (padded with zeros).
    """
    times = []
    vals = []
    with open(filepath, 'r') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            parts = s.split(',')
            if len(parts) < 2:
                continue
            try:
                t_val = float(parts[0])
                v_val = float(parts[1])
            except ValueError:
                continue
            times.append(t_val)
            vals.append(v_val)
    if not times:
        raise ValueError(f"No data found in velocity file: {filepath}")
    return times, vals


def parse_ingress_file(filepath):
    """Parse ingress paths file (height, area, coeff[, name]).

    Columns:
        1: sill height (m)
        2: opening area (m²)
        3: discharge coefficient
        4: optional name

    Lines with fewer than 3 numeric columns are skipped with a warning.
    More than 4 columns is treated as an error because the public ingress-file
    format intentionally does not support extra flags or routed source/target
    columns.
    """
    ingress = []
    n_skipped = 0
    with open(filepath, 'r') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            parts = [p.strip() for p in s.split(',')]
            if len(parts) < 3:
                n_skipped += 1
                continue
            if len(parts) > 4:
                raise ValueError(
                    f"Unsupported ingress format in {filepath}: expected "
                    "height, area, coeff[,name] with no extra columns "
                    "(legacy always_open and source/target fields are not supported)"
                )
            try:
                h    = float(parts[0])
                area = float(parts[1])
                coeff = float(parts[2])
            except ValueError:
                n_skipped += 1
                continue
            name = parts[3] if len(parts) >= 4 else f"ing{len(ingress)}"
            ingress.append(IngressPathway(height=h, area=area, coeff=coeff,
                                          name=name))
    if n_skipped:
        warnings.warn(
            f"{n_skipped} malformed line(s) skipped in {filepath}", stacklevel=2)
    if not ingress:
        raise ValueError(f"No ingress paths found in file: {filepath}")
    return ingress


def parse_external_text(text):
    """Parse external levels from a text block (time,level lines)."""
    times = []
    levels = []
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',') if p.strip()]
        if len(parts) < 2:
            continue
        times.append(float(parts[0]))
        levels.append(float(parts[1]))
    if not times:
        raise ValueError('No external data provided')
    return times, levels


def parse_velocity_text(text):
    """Parse external velocity data from a text block (time,velocity lines)."""
    times = []
    vals = []
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',') if p.strip()]
        if len(parts) < 2:
            continue
        try:
            times.append(float(parts[0]))
            vals.append(float(parts[1]))
        except ValueError:
            continue
    if not times:
        raise ValueError('No velocity data provided')
    return times, vals


def parse_ingress_text(text):
    """Parse ingress definitions from a text block (h, area, coeff[, name]).

    See parse_ingress_file for column documentation.
    Malformed lines (fewer than 3 columns or non-numeric values) are skipped
    with a warning; the line number within the text block is reported.
    More than 4 columns is treated as an error because extra flags and routed
    source/target
    syntax is not part of the public text/file ingress interface.
    """
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
        ingress.append(IngressPathway(height=h, area=area, coeff=coeff,
                                      name=name))
    if n_skipped:
        warnings.warn(
            f"{n_skipped} malformed line(s) skipped in ingress text", stacklevel=2)
    if not ingress:
        raise ValueError('No ingress entries provided')
    return ingress


def main(argv=None):
    parser = argparse.ArgumentParser(description='Headless Flood Ingress Simulation')
    parser.add_argument('--external', '-e', default='example_external_levels.csv', help='External levels CSV (time,level)')
    parser.add_argument('--ingress', '-i', default='example_ingress_paths.txt', help='Ingress paths file (height,area,coeff)')
    parser.add_argument('--floor', '-f', type=float, default=50.0, help='Floor area (m^2)')
    parser.add_argument('--outdir', '-o', default='.', help='Output directory for PNGs')
    parser.add_argument('--temp-output', action='store_true', help='Write outputs to a temporary directory that is removed when the program exits')
    parser.add_argument('--dt', type=float, default=None, help='Simulation timestep (in units of --time-units). If omitted: 60 seconds when units=seconds, otherwise 1 unit.')
    parser.add_argument('--time-units', '-u', choices=['seconds', 'minutes', 'hours'], default='minutes', help='Units of the external hydrograph times and of the --dt value (seconds, minutes or hours). Default: minutes')
    parser.add_argument('--animate', action='store_true', help='Create an animation (GIF) of the simulation')
    parser.add_argument('--anim-out', default='simulation_animation.gif', help='Animation output filename (GIF)')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--external-velocity', default=None, help='Optional external velocity CSV (time,velocity). If omitted a constant velocity is used from --external-velocity-default')
    parser.add_argument('--external-velocity-default', type=float, default=0.2, help='Default external velocity (m/s) used when no velocity file is supplied')
    parser.add_argument('--compute-forces', action='store_true', help='Compute hydrostatic and hydrodynamic lateral forces (CSV output)')
    parser.add_argument('--building-width', type=float, default=10.0, help='Building width (m) for force calculations (horizontal extent of flow-facing facade)')
    parser.add_argument('--drag-coeff', type=float, default=1.0, help='Drag coefficient C_D (dimensionless)')
    parser.add_argument('--rho', type=float, default=1000.0, help='Fluid density (kg/m^3)')
    # basement geometry
    parser.add_argument('--basement-area', type=float, default=0.0,
                        help='Basement floor area (m²). If >0 a basement zone is created.')
    parser.add_argument('--basement-floor-elevation', type=float, default=None,
                        help='Basement floor elevation relative to ground-floor datum (m). Negative = below datum.')
    # lumped exterior-perimeter opening to basement system (new dedicated args, spec §16.8)
    parser.add_argument('--basement-ingress-height', type=float, default=None,
                        help='Sill height of the lumped exterior→basement perimeter opening (m).')
    parser.add_argument('--basement-ingress-area', type=float, default=0.0,
                        help='Area of the lumped exterior→basement perimeter opening (m²).')
    parser.add_argument('--basement-ingress-coeff', type=float, default=0.5,
                        help='Discharge coefficient of the lumped exterior→basement perimeter opening (default 0.5).')
    # building-to-basement bypass connection
    parser.add_argument('--basement-connection-height', type=float, default=None,
                        help='Sill height of the ground↔basement connection (m). If omitted, no bypass.')
    parser.add_argument('--basement-connection-area', type=float, default=0.0,
                        help='Area of the ground↔basement connection (m²).')
    # sump + pump (all optional; sump activated when --sump-area > 0)
    parser.add_argument('--sump-area', type=float, default=0.0,
                        help='Sump chamber plan area (m²). If >0 a sump+pump zone is created.')
    parser.add_argument('--sump-base-elevation', type=float, default=None,
                        help='Sump base elevation on ground-floor datum (m). Used to derive lift head.')
    parser.add_argument('--sump-overflow-level', type=float, default=None,
                        help='Sump overflow crest elevation above sump base (m).')
    parser.add_argument('--sump-overflow-coeff', type=float, default=1.8,
                        help='Sump overflow coefficient C_ov (default 1.8).')
    parser.add_argument('--sump-overflow-exponent', type=float, default=1.5,
                        help='Sump overflow exponent m_ov: 1.5=weir (default), 0.5=orifice.')
    parser.add_argument('--pump-on-level', type=float, default=None,
                        help='Sump depth at which pump activates (m).')
    parser.add_argument('--pump-off-level', type=float, default=None,
                        help='Sump depth at which pump deactivates (m).')
    parser.add_argument('--pump-shutoff-head', type=float, default=None,
                        help='Pump shut-off head H_shut (m).')
    parser.add_argument('--pump-curve-coeff', type=float, default=None,
                        help='Pump-curve coefficient k_pump.')
    parser.add_argument('--pipe-loss-coeff', type=float, default=0.0,
                        help='Pipe friction + minor loss coefficient k_pipe (default 0).')
    parser.add_argument('--pump-availability', type=float, default=1.0,
                        help='Pump availability factor eta_p (default 1.0).')
    args = parser.parse_args(argv)

    outdir = args.outdir
    use_temp = bool(args.temp_output)
    temp_dir_ctx = None
    if use_temp:
        import tempfile
        temp_dir_ctx = tempfile.TemporaryDirectory()
        outdir = temp_dir_ctx.name
        print(f"Writing outputs to temporary directory: {outdir} (will be removed on exit)")
    else:
        os.makedirs(outdir, exist_ok=True)

    print(f"Reading external data from: {args.external}")
    times, levels = parse_external_file(args.external)
    # keep original times for previews, convert to internal seconds based on units
    orig_times = list(times)
    units = args.time_units
    mul = 1.0
    if units.startswith('min'):
        mul = 60.0
    elif units.startswith('hour'):
        mul = 3600.0
    # determine dt default if omitted: default to 1.0 in the selected time-units
    if args.dt is None:
        dt_input = 1.0
    else:
        dt_input = float(args.dt)
    dt_seconds = dt_input * mul
    # convert times to seconds internally
    times = [t * mul for t in times]
    print(f"Found {len(times)} external points")
    external_preview_path = os.path.join(outdir, 'external_preview.png')
    # plotting helpers are provided by viz.py (import at runtime to avoid backend side-effects)
    import importlib
    viz = importlib.import_module('viz')
    # show preview using original time units (what user uploaded)
    viz.save_external_preview(orig_times, levels, external_preview_path)
    print(f"Saved external preview to {external_preview_path}")

    print(f"Reading ingress data from: {args.ingress}")
    ingress_list = parse_ingress_file(args.ingress)
    print(f"Found {len(ingress_list)} ingress paths (exterior→building)")
    # Ground↔basement bypass connection (added to ingress_list, not basement_ingress)
    if (getattr(args, 'basement_connection_height', None) is not None
            and getattr(args, 'basement_connection_area', 0.0)
            and args.basement_connection_area > 0.0):
        conn_name = 'ground-basement-conn'
        print(f"Adding ground↔basement bypass: h={args.basement_connection_height}, A={args.basement_connection_area}")
        ingress_list.append(IngressPathway(
            height=args.basement_connection_height,
            area=args.basement_connection_area,
            coeff=1.0, name=conn_name,
            source='ground', target='basement'))
    ingress_preview_path = os.path.join(outdir, 'ingress_preview.png')
    viz.save_ingress_preview(ingress_list, ingress_preview_path)
    print(f"Saved ingress preview to {ingress_preview_path}")

    ingress_locations_path = os.path.join(outdir, 'ingress_locations.png')
    try:
        viz.save_ingress_locations(ingress_list, ingress_locations_path)
        print(f"Saved ingress locations plot to {ingress_locations_path}")
    except Exception as e:
        print(f"Failed to save ingress locations plot: {e}")

    building = Building(floor_area=args.floor)
    # optional basement
    if getattr(args, 'basement_area', None) and args.basement_area > 0.0:
        building.basement_area = float(args.basement_area)
        building.h_basement = 0.0
        if getattr(args, 'basement_floor_elevation', None) is not None:
            building.z_basement = float(args.basement_floor_elevation)

    # Lumped exterior perimeter opening (separate from ingress file; spec §16.8)
    if (getattr(args, 'basement_ingress_height', None) is not None
            and getattr(args, 'basement_ingress_area', 0.0)
            and args.basement_ingress_area > 0.0):
        building.basement_ingress = IngressPathway(
            height=float(args.basement_ingress_height),
            area=float(args.basement_ingress_area),
            coeff=float(args.basement_ingress_coeff),
            name='ext-basement-perimeter',
            source='outside', target='basement')
        print(f"Basement perimeter opening: h={args.basement_ingress_height}, "
              f"A={args.basement_ingress_area}, Cd={args.basement_ingress_coeff}")

    # Sump + pump (activated when --sump-area > 0 and required params present)
    if getattr(args, 'sump_area', 0.0) and args.sump_area > 0.0:
        required = ['sump_base_elevation', 'sump_overflow_level',
                    'pump_on_level', 'pump_off_level',
                    'pump_shutoff_head', 'pump_curve_coeff']
        missing = [k for k in required if getattr(args, k, None) is None]
        if missing:
            print(f"WARNING: sump enabled but missing params: {missing}. Sump disabled.")
        else:
            building.sump_pump = SumpPump(
                sump_area          = float(args.sump_area),
                sump_base_elevation= float(args.sump_base_elevation),
                overflow_level     = float(args.sump_overflow_level),
                overflow_coeff     = float(args.sump_overflow_coeff),
                overflow_exponent  = float(args.sump_overflow_exponent),
                pump_on_level      = float(args.pump_on_level),
                pump_off_level     = float(args.pump_off_level),
                pump_shutoff_head  = float(args.pump_shutoff_head),
                pump_curve_coeff   = float(args.pump_curve_coeff),
                pipe_loss_coeff    = float(args.pipe_loss_coeff),
                pump_availability  = float(args.pump_availability),
            )
            print(f"Sump+pump enabled: area={args.sump_area} m², base@{args.sump_base_elevation} m, "
                  f"overflow@{args.sump_overflow_level} m, pump on@{args.pump_on_level} m")

    # parse optional external velocity hydrograph (time,velocity)
    v_times = None
    v_vals = None
    if getattr(args, 'external_velocity', None):
        try:
            print(f"Reading external velocity from: {args.external_velocity}")
            v_times_raw, v_vals_raw = parse_velocity_file(args.external_velocity)
            # keep original velocity times for preview (in original units)
            orig_v_times = list(v_times_raw)
            # convert velocity times to internal seconds using same multiplier
            v_times = [t * mul for t in v_times_raw]
            v_vals = list(v_vals_raw)
        except Exception as e:
            print(f"Failed to read velocity file: {e}")
            print("Falling back to default velocity value")
            v_times = list(times)
            v_vals = [float(args.external_velocity_default) for _ in times]
    else:
        # use a constant default velocity sampled at the external hydrograph times
        v_times = list(times)
        v_vals = [float(args.external_velocity_default) for _ in times]

    sim = Simulation(building, ingress_list, times, levels, dt=dt_seconds, external_vel_times=v_times, external_velocities=v_vals)

    # (velocity preview will be saved after the simulation so it uses the
    # same interpolation/padding as the plotted/animated velocity)

    print('Running simulation...')
    def progress(p):
        if args.verbose:
            print(f'Progress: {int(p*100)}%')

    sim_ret = sim.run(progress_callback=progress, verbose=args.verbose)
    # unpack backwards-compatible tuple (2, 3, or 4 elements)
    if len(sim_ret) == 4:
        sim_times, sim_levels, sim_basement, sim_sump = sim_ret
    elif len(sim_ret) == 3:
        sim_times, sim_levels, sim_basement = sim_ret
        sim_sump = None
    else:
        sim_times, sim_levels = sim_ret
        sim_basement = None
        sim_sump = None

    # Interpolate external hydrograph to simulation times using the canonical sampler.
    # Times beyond the hydrograph end are padded with 0.0 (water has receded).
    sampled_external = sample_with_zero_padding(sim_times, times, levels)

    # sample external velocity (if available) to simulation times for plotting
    sampled_velocity_plot = None
    if 'v_times' in locals() and v_times and v_vals:
        try:
            sampled_velocity_plot = sample_with_zero_padding(sim_times, v_times, v_vals)
        except Exception:
            sampled_velocity_plot = None

    # Convert simulation times back to the original units for plotting/display
    sim_times_display = [t / mul for t in sim_times]

    # Save velocity preview using the same sampled/padded velocity used in
    # the simulation_result (this ensures the preview and plot match).
    try:
        velocity_preview_path = os.path.join(outdir, 'velocity_preview.png')
        if sampled_velocity_plot is not None:
            # sampled_velocity_plot corresponds to sim_times (seconds); use
            # sim_times_display (original units) for x-axis in preview
            viz.save_velocity_preview(sim_times_display, sampled_velocity_plot, velocity_preview_path, time_unit=units, orig_point_times=locals().get('orig_v_times', None), orig_point_vals=locals().get('v_vals_raw', None))
        else:
            # fallback: show constant/default velocity on the original hydrograph times
            viz.save_velocity_preview(sim_times_display, [float(args.external_velocity_default) for _ in sim_times_display], velocity_preview_path, time_unit=units)
        print(f"Saved velocity preview to {velocity_preview_path}")
    except Exception as e:
        print(f"Failed to save velocity preview: {e}")

    sim_out_path = os.path.join(outdir, 'simulation_result.png')
    try:
        viz.save_simulation_result(sim_times_display, sim_levels, sampled_external, sim_out_path,
                                   time_unit=units, basement_levels=sim_basement,
                                   velocity_series=sampled_velocity_plot, sump_levels=sim_sump)
    except TypeError:
        viz.save_simulation_result(sim_times_display, sim_levels, sampled_external, sim_out_path,
                                   time_unit=units)
    print(f"Saved simulation result to {sim_out_path}")

    # Compute analytical forces time series if requested
    if getattr(args, 'compute_forces', False):
        try:
            forces_out = []
            # ensure we have a velocity list matching sim_times
            if sampled_velocity_plot is None:
                vel_list = [float(args.external_velocity_default) for _ in sim_times]
            else:
                vel_list = list(sampled_velocity_plot)

            for i, t in enumerate(sim_times):
                h_out_i = sampled_external[i]
                h_in_i = sim_levels[i]
                v_i = vel_list[i] if i < len(vel_list) else float(args.external_velocity_default)

                # net hydrostatic depth opposed by interior water
                H_net = max(0.0, float(h_out_i) - float(h_in_i))
                # external wetted height for drag is the external water depth above datum
                H_wet = max(0.0, float(h_out_i))

                res = forces.compute_combined_forces(H_net, H_wet, v_i, float(args.building_width), C_D=float(args.drag_coeff), rho=float(args.rho))
                forces_out.append((t, res['F_hydro'], res['F_drag'], res['F_total'], res['M_overturn'], H_net, H_wet, v_i, res['lever_hydro'], res['lever_drag']))

            forces_csv = os.path.join(outdir, 'forces.csv')
            with open(forces_csv, 'w', newline='') as cf:
                writer = csv.writer(cf)
                writer.writerow(['time', 'F_hydro_N', 'F_drag_N', 'F_total_N', 'M_overturn_Nm', 'H_net_m', 'H_wet_m', 'v_m_per_s', 'lever_hydro_m', 'lever_drag_m'])
                for row in forces_out:
                    writer.writerow(row)

            # simple peak summary printout
            peak_F_total = max((r[3] for r in forces_out), default=0.0)
            peak_idx = next((i for i, r in enumerate(forces_out) if r[3] == peak_F_total), None)
            peak_time = forces_out[peak_idx][0] / mul if peak_idx is not None else None
            print(f"Saved forces time series to: {forces_csv}")
            if peak_time is not None:
                print(f"Peak total lateral force = {peak_F_total:.2f} N at time={peak_time} {units}")
            # create a simple forces_result.png plot
            try:
                forces_png = os.path.join(outdir, 'forces_result.png')
                viz.save_forces_result(sim_times_display, forces_out, forces_png, time_unit=units)
                print(f"Saved forces plot to: {forces_png}")
            except Exception as _e:
                print(f"Failed to save forces plot: {_e}")
        except Exception as e:
            print(f"Failed to compute or save forces: {e}")

    if args.animate:
        anim_path = os.path.join(outdir, args.anim_out)
        print(f'Generating animation to: {anim_path}')
        try:
            # pass times in original units for animation display
            sampled_for_anim = sampled_external
            sim_times_display = [t / mul for t in sim_times]
            try:
                # compute absolute basement surface elevations for animation use
                try:
                    sim_basement_abs = [building.z_basement + hb for hb in sim_basement]
                except Exception:
                    sim_basement_abs = None
                # sample velocities to simulation times for animation display (use seconds-based sim_times)
                try:
                    sampled_velocity_for_anim = sample_with_zero_padding(sim_times, v_times, v_vals) if (v_times and v_vals) else None
                except Exception:
                    sampled_velocity_for_anim = None
                _sp = building.sump_pump
                _tr = sim._last_trace
                viz.generate_animation(sim_times_display, sim_levels, sampled_for_anim,
                                       ingress_list, anim_path, time_unit=units,
                                       basement_levels=sim_basement,
                                       basement_abs_levels=sim_basement_abs,
                                       velocity_series=sampled_velocity_for_anim,
                                       sump_levels=sim_sump,
                                       sump_overflow_level=(_sp.overflow_level if _sp else None),
                                       Q_perim_series=(_tr['Q_ext_perimeter'] if _tr else None),
                                       Q_bypass_series=(_tr['Q_b_bs'] if _tr else None))
            except TypeError:
                viz.generate_animation(sim_times_display, sim_levels, sampled_for_anim,
                                       ingress_list, anim_path, time_unit=units)
            print(f'Animation saved to: {anim_path}')
        except Exception as e:
            print(f'Failed to generate animation: {e}')

    print('Done.')

    # clean up temporary dir (if any) by closing the context manager
    if temp_dir_ctx is not None:
        try:
            temp_dir_ctx.cleanup()
            print('(Temporary output directory removed)')
        except Exception:
            pass


if __name__ == '__main__':
    main()
