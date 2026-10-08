"""Regression tests for all validation case studies.

Each case in examples/reference_cases.py is re-run and its metrics compared
with the stored reference values in examples/reference/exNN.json.

Tolerances (from docs/model.md regression contract):
  - peak depths :  1 %  (rel), with 1e-5 m absolute floor for near-zero values
  - volumes     :  5 %  (rel), with 1e-8 m³ absolute floor
  - counts      :  exact

To update the reference files after a deliberate change:
    python3 examples/make_reference.py
"""

import json
import os
import sys

import pytest

HERE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.dirname(HERE)
REFDIR = os.path.join(ROOT, 'examples', 'reference')

sys.path.insert(0, os.path.join(ROOT, 'examples'))

import reference_cases as rc  # noqa: E402


def _ref(name):
    path = os.path.join(REFDIR, f'{name}.json')
    if not os.path.exists(path):
        pytest.skip(f'reference file missing: {path}')
    with open(path) as f:
        return json.load(f)


def _approx(key, ref_val):
    if key.startswith('n_'):
        return ref_val
    if 'volume' in key:
        return pytest.approx(ref_val, rel=0.05, abs=1e-8)
    return pytest.approx(ref_val, rel=0.01, abs=1e-5)


@pytest.mark.parametrize('name', list(rc.CASES))
def test_case_matches_reference(name):
    ref = _ref(name)
    metrics = rc.CASES[name]()
    assert set(metrics) == set(ref)
    for key, value in metrics.items():
        assert value == _approx(key, ref[key]), key


def test_ex05_basement_fills():
    assert rc.ex05()['peak_h_basement'] == pytest.approx(2.5)   # full to ceiling


def test_ex05_indoor_level_bounded_by_exterior():
    assert rc.ex05()['peak_h_in'] <= max(rc.LONG_05.levels) + 1e-3


def test_ex11_peak_interior_monotonic_in_peak_exterior():
    peaks = rc.ex11_peaks()
    assert all(a <= b for a, b in zip(peaks, peaks[1:])), 'peak_h_int not monotonic'
