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
    # Two example argument sets are shown below. The first (active) runs
    # the simulation without a basement. The second (commented) shows the
    # same parameters but with a basement compartment — uncomment to run it.

    # --- Example A: no basement (active) ---
    args = [
        '--external', 'example_external_levels.csv',
        '--ingress', 'example_ingress_paths.txt',
        '--outdir', '.',
        '--floor', '50',
        '--animate',
        '--anim-out', 'simulation_animation.gif'
    ]

    # --- Example B: with basement (commented) ---
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

    main.main(args)
