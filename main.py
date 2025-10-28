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
        self.h_in = 0.0

    def update_water_level(self, volume_change):
        if self.floor_area <= 0:
            return
        delta_h = volume_change / self.floor_area
        self.h_in += delta_h
        if self.h_in < 0:
            self.h_in = 0.0

class IngressPathway:
    def __init__(self, height, area, coeff, name="Opening"):
        self.height = height
        self.area = area
        self.coeff = coeff
        self.name = name

    def compute_flow(self, h_out, h_in):
        if h_out < self.height and h_in < self.height:
            return 0.0
        delta_h = h_out - h_in
        if delta_h == 0:
            return 0.0
        flow_rate = self.coeff * self.area * math.sqrt(2 * 9.81 * abs(delta_h))
        if delta_h < 0:
            flow_rate = -flow_rate
        return flow_rate

class Simulation:
    def __init__(self, building, ingress_list, external_times, external_levels, dt=60.0):
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
        # simulation timestep (seconds or same units as t_ext). Default is 60.
        self.dt = float(dt) if dt is not None else 60.0

    def run(self, progress_callback=None, verbose=False):
        indoor_levels = []
        times = []
        current_h_in = self.building.h_in
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

            total_flow = 0.0
            for ingress in self.ingress_list:
                Q = ingress.compute_flow(h_out, current_h_in)
                total_flow += Q

            # volume change during this fixed timestep
            volume_change = total_flow * self.dt
            self.building.update_water_level(volume_change)
            current_h_in = self.building.h_in
            times.append(t)
            indoor_levels.append(current_h_in)

            # report progress (callable)
            if progress_callback and total_steps > 0:
                try:
                    progress_callback(min(1.0, (step + 1) / (total_steps + 1)))
                except Exception:
                    pass
            if verbose and (step + 1) % 1000 == 0:
                print(f"Progress: {min(100, int(100*(step+1)/(total_steps+1)))}%")

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
    sim = Simulation(building, ingress_list, times, levels, dt=dt_seconds)

    print('Running simulation...')
    def progress(p):
        if args.verbose:
            print(f'Progress: {int(p*100)}%')

    sim_times, sim_levels = sim.run(progress_callback=progress, verbose=args.verbose)

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

    # Convert simulation times back to the original units for plotting/display
    sim_times_display = [t / mul for t in sim_times]

    sim_out_path = os.path.join(outdir, 'simulation_result.png')
    viz.save_simulation_result(sim_times_display, sim_levels, sampled_external, sim_out_path, time_unit=units)
    print(f"Saved simulation result to {sim_out_path}")

    if args.animate:
        anim_path = os.path.join(outdir, args.anim_out)
        print(f'Generating animation to: {anim_path}')
        try:
            # pass times in original units for animation display
            sampled_for_anim = sampled_external
            sim_times_display = [t / mul for t in sim_times]
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