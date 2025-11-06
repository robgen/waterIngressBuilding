#!/usr/bin/env python3
import math
import argparse
import os
import sys

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
    def __init__(self, height, area, coeff, name="Opening", always_open=False, source='outside', target='ground'):
        """An ingress pathway (orifice/opening).

        Arguments:
            height: elevation of the orifice (same units as water levels)
            area: opening area (m^2)
            coeff: discharge coefficient
            name: optional name
            always_open: if True, allow flow based solely on head difference
                         even when both sides are below the orifice height.
                         Default False preserves the previous behaviour.
        """
        self.height = float(height)
        self.area = float(area)
        self.coeff = float(coeff)
        self.name = name
        self.always_open = bool(always_open)
        # semantic endpoints: 'outside'|'ground'|'basement'
        self.source = source
        self.target = target

    def compute_flow(self, H_source, H_target, v_source=0.0):
        """Compute volumetric flow (m^3 / time-unit) using absolute surface heads.

        H_source and H_target are absolute water surface elevations (m) on the
        source and target sides measured on a common datum. The pathway sill is
        `self.height` on the same datum. If both sides are below the sill and
        `always_open` is False then Q=0. Otherwise the orifice-like law is
        evaluated with the head difference \Delta H = H_source - H_target.
        """
        # if the opening is above the water on both sides and it's not forced-open,
        # there is no flow.
        if (not self.always_open) and H_source < self.height and H_target < self.height:
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

    def run(self, progress_callback=None, verbose=False):
        indoor_levels = []
        times = []
        basement_levels = []
        current_h_in = self.building.h_in
        current_h_basement = self.building.h_basement
        start_time = self.t_ext[0] if len(self.t_ext) > 0 else 0.0
        end_time = self.t_ext[-1] if len(self.t_ext) > 0 else 0.0
        # Use a fixed-step loop to avoid depending on external hydrograph spacing.
        # Compute number of steps (ceil) to cover the entire period.
        import math
        total_steps = max(1, int(math.ceil((end_time - start_time) / max(self.dt, 1e-9))))
        # current external hydrograph segment index
        i = 0

        # Step through with a for-loop to avoid floating-point accumulation issues
        for step in range(total_steps + 1):
            t = start_time + step * self.dt
            # clamp to end_time for the final step
            if t > end_time:
                t = end_time

            # find the segment in the external hydrograph that contains t
            # advance index i as needed
            if i < len(self.t_ext) - 1:
                # advance i until t is before the next timestamp
                while i < len(self.t_ext) - 1 and t >= self.t_ext[i+1]:
                    i += 1

            if i < len(self.t_ext) - 1:
                t1, h1 = self.t_ext[i], self.h_ext[i]
                t2, h2 = self.t_ext[i+1], self.h_ext[i+1]
                if t2 != t1:
                    frac = (t - t1) / (t2 - t1)
                    h_out = h1 + frac * (h2 - h1)
                else:
                    h_out = h1
            else:
                h_out = self.h_ext[-1] if len(self.h_ext) > 0 else 0.0

            # compute absolute surfaces for use in orifice evaluation
            H_out = h_out
            H_in = current_h_in
            H_basement = self.building.z_basement + current_h_basement

            # interpolate external velocity to current time (if provided).
            # Short velocity series are treated as padded with zeros beyond
            # their last timestamp (explicitly requested behavior).
            v_out = 0.0
            if self.v_t and len(self.v_t) > 0 and len(self.v_vals) > 0:
                # maintain a velocity segment index to avoid re-scanning
                j_v = getattr(self, '_vel_index', 0)
                while j_v < len(self.v_t) - 1 and t >= self.v_t[j_v + 1]:
                    j_v += 1
                self._vel_index = j_v
                if j_v < len(self.v_t) - 1:
                    vt1, vv1 = self.v_t[j_v], self.v_vals[j_v]
                    vt2, vv2 = self.v_t[j_v+1], self.v_vals[j_v+1]
                    if vt2 != vt1:
                        frac = (t - vt1) / (vt2 - vt1)
                        v_out = vv1 + frac * (vv2 - vv1)
                    else:
                        v_out = vv1
                else:
                    # beyond last velocity timestamp -> pad with zero
                    if t > self.v_t[-1]:
                        v_out = 0.0
                    else:
                        v_out = self.v_vals[-1] if self.v_vals else 0.0

            # flows: outside->ground (flow_og), outside->basement (flow_ob),
            # ground->basement (flow_gb; positive if ground->basement)
            flow_og = 0.0
            flow_ob = 0.0
            flow_gb = 0.0

            for ingress in self.ingress_list:
                src = getattr(ingress, 'source', 'outside')
                tgt = getattr(ingress, 'target', 'ground')
                if src == 'outside' and tgt == 'ground':
                    Q = ingress.compute_flow(H_out, H_in, v_source=v_out)
                    flow_og += Q
                elif src == 'outside' and tgt == 'basement':
                    Q = ingress.compute_flow(H_out, H_basement, v_source=v_out)
                    flow_ob += Q
                elif src == 'ground' and tgt == 'basement':
                    Q = ingress.compute_flow(H_in, H_basement)
                    flow_gb += Q
                elif src == 'basement' and tgt == 'ground':
                    Q = ingress.compute_flow(H_basement, H_in)
                    # subtract because flow_gb is defined positive ground->basement
                    flow_gb -= Q
                else:
                    # unsupported or unknown pairing; ignore
                    pass

            # apply volume changes to zones
            vol_ground = (flow_og - flow_gb) * self.dt
            # apply to ground; update_water_level returns overflow (unused for ground)
            _ = self.building.update_water_level(vol_ground, zone='ground')
            current_h_in = self.building.h_in

            vol_basement = (flow_ob + flow_gb) * self.dt
            # apply to basement; if basement overflows, spill to ground
            overflow = self.building.update_water_level(vol_basement, zone='basement')
            if overflow and overflow > 0.0:
                # add overflow to ground
                _ = self.building.update_water_level(overflow, zone='ground')
            current_h_basement = self.building.h_basement

            times.append(t)
            indoor_levels.append(current_h_in)
            basement_levels.append(current_h_basement)

            # report progress (callable)
            if progress_callback and total_steps > 0:
                try:
                    progress_callback(min(1.0, (step + 1) / (total_steps + 1)))
                except Exception:
                    pass
            if verbose and (step + 1) % 1000 == 0:
                print(f"Progress: {min(100, int(100*(step+1)/(total_steps+1)))}%")

        # Backwards-compatible return: if no basement zone is configured,
        # return the original (times, indoor_levels) tuple. If a basement
        # exists, return (times, indoor_levels, basement_levels).
        if getattr(self.building, 'basement_area', 0.0) and self.building.basement_area > 0.0:
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
    ingress = []
    with open(filepath, 'r') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            parts = s.split(',')
            if len(parts) < 3:
                continue
            try:
                h = float(parts[0])
                area = float(parts[1])
                coeff = float(parts[2])
            except ValueError:
                continue
            # optional name in 4th column
            name = parts[3].strip() if len(parts) >= 4 else f"ing{len(ingress)}"
            ingress.append(IngressPathway(height=h, area=area, coeff=coeff, name=name))
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


def parse_ingress_text(text):
    """Parse ingress definitions from a text block (h,area,coeff lines)."""
    ingress = []
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',') if p.strip()]
        if len(parts) < 3:
            continue
        name = parts[3] if len(parts) >= 4 else f"ing{len(ingress)}"
        ingress.append(IngressPathway(parts[0], parts[1], parts[2], name=name))
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
    parser.add_argument('--basement-area', type=float, default=0.0, help='Basement floor area (m^2). If >0, a basement zone is created')
    parser.add_argument('--basement-floor-elevation', type=float, default=None, help='Basement floor elevation relative to ground-floor datum (m). Use negative for below ground')
    parser.add_argument('--basement-connection-height', type=float, default=None, help='Height of opening between ground and basement (if omitted no connection is created)')
    parser.add_argument('--basement-connection-area', type=float, default=0.0, help='Area of connection between ground and basement')
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
    print(f"Found {len(ingress_list)} ingress paths")
    # optionally add a connection between ground and basement if requested
    if getattr(args, 'basement_connection_height', None) is not None and getattr(args, 'basement_connection_area', 0.0) and args.basement_connection_area > 0.0:
        conn_name = 'ground-basement-conn'
        print(f"Adding ground<->basement connection: h={args.basement_connection_height}, A={args.basement_connection_area}")
        ingress_list.append(IngressPathway(height=args.basement_connection_height, area=args.basement_connection_area, coeff=1.0, name=conn_name, source='ground', target='basement'))
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
    # support both old (times, levels) and new (times, levels, basement_levels) return signatures
    if isinstance(sim_ret, tuple) and len(sim_ret) == 3:
        sim_times, sim_levels, sim_basement = sim_ret
    else:
        sim_times, sim_levels = sim_ret
        sim_basement = None

    # interpolate external hydrograph to simulation times so plots/animation have matching lengths
    def sample_external(sim_times, t_ext, h_ext):
        sampled = []
        j = 0
        for t in sim_times:
            # advance segment index
            while j < len(t_ext) - 1 and t >= t_ext[j+1]:
                j += 1
            if j < len(t_ext) - 1:
                t1, h1 = t_ext[j], h_ext[j]
                t2, h2 = t_ext[j+1], h_ext[j+1]
                if t2 != t1:
                    frac = (t - t1) / (t2 - t1)
                    sampled.append(h1 + frac * (h2 - h1))
                else:
                    sampled.append(h1)
            else:
                sampled.append(h_ext[-1] if h_ext else 0.0)
        return sampled

    # sample external using the original hydrograph times (converted to seconds)
    sampled_external = sample_external(sim_times, times, levels)

    # use the canonical zero-padding sampler defined at module scope
    # (sample_with_zero_padding is imported from the module scope above)

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
        viz.save_simulation_result(sim_times_display, sim_levels, sampled_external, sim_out_path, time_unit=units, basement_levels=sim_basement, velocity_series=sampled_velocity_plot)
    except TypeError:
        viz.save_simulation_result(sim_times_display, sim_levels, sampled_external, sim_out_path, time_unit=units)
    print(f"Saved simulation result to {sim_out_path}")

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
                viz.generate_animation(sim_times_display, sim_levels, sampled_for_anim, ingress_list, anim_path, time_unit=units, basement_levels=sim_basement, basement_abs_levels=sim_basement_abs, velocity_series=sampled_velocity_for_anim)
            except TypeError:
                # Fall back if viz.generate_animation doesn't accept the new arg (backwards compatibility)
                viz.generate_animation(sim_times_display, sim_levels, sampled_for_anim, ingress_list, anim_path, time_unit=units)
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