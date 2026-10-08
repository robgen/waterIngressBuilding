#!/usr/bin/env python3
"""Generate reference metric JSONs for all validation case studies.

Run from the repo root:
    python3 examples/make_reference.py

Overwrites examples/reference/exNN.json with current simulation output for
every case in examples/reference_cases.py.  Commit the resulting files;
tests/test_regression.py compares against them.
"""

import json
import os

from reference_cases import CASES

REFDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reference')
os.makedirs(REFDIR, exist_ok=True)

for name, case in CASES.items():
    metrics = case()
    with open(os.path.join(REFDIR, f'{name}.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f'  wrote {name}.json  {metrics}')

print('\nDone. Reference files written to', REFDIR)
