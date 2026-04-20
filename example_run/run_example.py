#!/usr/bin/env python3
"""Run the example using the headless `main.py` from the repository root.

This script changes the working directory to its own folder so relative input
filenames are resolved to files inside `example_run/` and then calls
`main.main(...)` programmatically.
"""
import os
import sys
from pathlib import Path

this_dir = Path(__file__).resolve().parent
repo_root = str(this_dir.parent)

# Ensure repository root is on sys.path so we can import main
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import main

if __name__ == '__main__':
    print(f"Running example from: {this_dir}")
    # run from example directory so default relative filenames resolve
    os.chdir(str(this_dir))
    # Call main with explicit args pointing to local files and output to '.'

    # --- Example A: no basement ---
    # args = [
    #     '--external', 'example_external_levels.csv',
    #     '--ingress', 'example_ingress_paths.txt',
    #     '--outdir', '.',
    #     '--floor', '50',
    #     '--animate',
    #     '--anim-out', 'simulation_animation.gif'
    # ]

    # --- Example B: with basement ---
    # To run the basement example replace the `args` above or uncomment the
    # block below.
    # args = [
    #     '--external', 'example_external_levels.csv',
    #     '--ingress', 'example_ingress_paths.txt',
    #     '--outdir', '.',
    #     '--floor', '50',
    #     '--basement-area', '50',
    #     '--basement-floor-elevation', '-2.5',
    #     '--basement-connection-height', '0.0',
    #     '--basement-connection-area', '0.01',
    #     '--animate',
    #     '--anim-out', 'simulation_animation_basement.gif'
    # ]

    # --- Example C: include external velocity hydrograph ---
    # This example demonstrates the new external velocity input and will
    # produce `velocity_preview.png` in the output directory.
    # args = [
    #     '--external', 'example_external_levels.csv',
    #     '--ingress', 'example_ingress_paths.txt',
    #     '--outdir', '.',
    #     '--floor', '50',
    #     '--animate',
    #     '--anim-out', 'simulation_animation_with_velocity.gif',
    #     '--external-velocity', 'example_external_velocities.csv'
    # ]

    # --- Example D: compute forces and plot results ---
    # This runs the same hydrograph but requests per-timestep forces and a plot.
    # args = [
    #     '--external', 'example_external_levels.csv',
    #     '--ingress', 'example_ingress_paths.txt',
    #     '--outdir', '.',
    #     '--floor', '50',
    #     '--compute-forces',
    #     '--building-width', '12.0',
    #     '--drag-coeff', '1.0',
    #     '--rho', '1000.0',
    #     '--animate',
    #     '--anim-out', 'simulation_animation_forces.gif',
    #     '--external-velocity', 'example_external_velocities.csv'
    # ]

    # --- Example E: basement with separate building and basement vulnerability ---
    # Demonstrates separate loss estimation for ground-floor and basement contents.
    # Uses uk_buildingContents_vulnerability.csv for the ground floor and
    # uk_basementContents_vulnerability.csv for the basement.
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    import batch
    from main import parse_ingress_file

    ingress_list = parse_ingress_file('example_ingress_paths.txt')
    from damage import load_vulnerability_curve
    building_content_vulnerability = load_vulnerability_curve('uk_buildingContents_vulnerability.csv')
    basement_content_vulnerability = load_vulnerability_curve('uk_basementContents_vulnerability.csv')

    results = batch.run_batch(
        depth_dir='.',
        velocity_dir=None,
        ingress_list=ingress_list,
        floor_area=50.0,
        time_units='minutes',
        dt=1.0,
        thresholds=[0.10, 0.30, 0.60, 1.00],
        default_velocity=0.2,
        building_content_vulnerability=building_content_vulnerability,
        basement_content_vulnerability=basement_content_vulnerability,
        basement_area=50.0,
        basement_floor_elev=-2.5,
        basement_ceiling_elev=0.0,
        basement_conn_height=0.0,
        basement_conn_area=0.01,
        outdir='.',
        verbose=True,
    )
    print(f"\nExample E complete — {len(results)} result(s) written.")
