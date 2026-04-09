#!/usr/bin/env python3
"""Generate interpretation dashboard PNG assets for the tutorial.

Runs five case studies as described in docs/INTERPRETATION_DASHBOARD_TUTORIAL.md
and writes dashboard images to docs/assets/interpretation_dashboard/.

Usage (from repository root):
    ./.venv/bin/python example_run/generate_interpretation_tutorial_assets.py

Each case uses example_run/example_external_levels.csv as the hydrograph and
example_run/example_ingress_paths.txt as the building ingress file.
"""

import os
import sys

# Allow importing from the repository root
_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _repo)

from main import Building, IngressPathway, Simulation, parse_external_file, parse_ingress_file
from pump import SumpPump
from diagnostics import diagnostics_from_trace
import viz

# ── paths ─────────────────────────────────────────────────────────────────────
EXTERNAL_CSV  = os.path.join(_repo, 'example_run', 'example_external_levels.csv')
INGRESS_TXT   = os.path.join(_repo, 'example_run', 'example_ingress_paths.txt')
ASSET_DIR     = os.path.join(_repo, 'docs', 'assets', 'interpretation_dashboard')
os.makedirs(ASSET_DIR, exist_ok=True)

# Shared hydrograph — times in minutes, convert to seconds
_times_min, _levels = parse_external_file(EXTERNAL_CSV)
TIMES_S = [t * 60.0 for t in _times_min]
LEVELS  = _levels
DT_S    = 6.0   # 6-second timestep (0.1 min) per tutorial commands

# Shared ingress (exterior→building only)
INGRESS_LIST = parse_ingress_file(INGRESS_TXT)

FLOOR = 50.0
BASEMENT_AREA  = 50.0
BASEMENT_ELEV  = -2.5
BASEMENT_CEIL  = 0.0

# Perimeter opening and bypass from tutorial
PERI_H    = 0.0
PERI_A    = 0.0035
PERI_CD   = 0.5
BYPASS_H  = 0.0
BYPASS_A_SMALL = 0.001   # cases 2,3,5
BYPASS_A_LARGE = 0.010   # case 4


def _make_building(with_basement=False, with_peri=False,
                   bypass_area=0.0, sump_cfg=None):
    """Construct a Building instance for the given configuration."""
    building = Building(floor_area=FLOOR)
    if with_basement:
        building.basement_area = BASEMENT_AREA
        building.z_basement    = BASEMENT_ELEV
        building.basement_ceiling_elevation = BASEMENT_CEIL
    if with_peri and with_basement:
        building.basement_ingress = IngressPathway(
            height=PERI_H, area=PERI_A, coeff=PERI_CD,
            name='ext-perimeter')
    if sump_cfg is not None and with_basement:
        building.sump_pump = SumpPump(**sump_cfg)
    return building


def _make_ingress(bypass_area=0.0):
    """Return ingress list with optional bypass connection appended."""
    ing = list(INGRESS_LIST)  # exterior→building paths
    if bypass_area > 0.0:
        ing.append(IngressPathway(
            height=BYPASS_H, area=bypass_area, coeff=1.0,
            name='ground-basement-conn', source='ground', target='basement'))
    return ing


def _run(building, ingress, label):
    """Run simulation and return diagnostics built from the trace."""
    print(f'  Running {label}...')
    sim = Simulation(building, ingress, TIMES_S, LEVELS, dt=DT_S)
    sim.run()
    return diagnostics_from_trace(sim._last_trace, sim.dt)


def _save(diag, name, label):
    path = os.path.join(ASSET_DIR, f'{name}_dashboard.png')
    viz.save_interpretation_dashboard(diag, path, time_unit='minutes',
                                      title_suffix=label)
    print(f'  Saved → {path}')


# ── Case 1: ground-floor ingress only ─────────────────────────────────────────
print('Case 1: Ground-floor ingress only')
b1 = _make_building(with_basement=False)
i1 = _make_ingress(bypass_area=0.0)
d1 = _run(b1, i1, 'case1_ground_only')
_save(d1, 'case1_ground_only', 'Case 1 — Ground floor only')

# ── Case 2: basement without sump ─────────────────────────────────────────────
print('Case 2: Basement without sump')
b2 = _make_building(with_basement=True, with_peri=True, bypass_area=BYPASS_A_SMALL)
i2 = _make_ingress(bypass_area=BYPASS_A_SMALL)
d2 = _run(b2, i2, 'case2_basement_no_sump')
_save(d2, 'case2_basement_no_sump', 'Case 2 — Basement, no sump')

# ── Case 3: basement with effective sump ──────────────────────────────────────
print('Case 3: Basement with effective sump')
sump3 = dict(
    sump_area          = 8.0,
    sump_base_elevation= BASEMENT_ELEV,
    overflow_level     = 0.8,
    overflow_coeff     = 1.8,
    overflow_exponent  = 1.5,
    pump_on_level      = 0.5,
    pump_off_level     = 0.2,
    pump_shutoff_head  = 3.5,
    pump_curve_coeff   = 800.0,
    pipe_loss_coeff    = 200.0,
)
b3 = _make_building(with_basement=True, with_peri=True, sump_cfg=sump3)
i3 = _make_ingress(bypass_area=BYPASS_A_SMALL)
d3 = _run(b3, i3, 'case3_basement_sump_effective')
_save(d3, 'case3_basement_sump_effective', 'Case 3 — Effective sump protection')

# ── Case 4: bypass-dominated basement flooding ────────────────────────────────
print('Case 4: Bypass-dominated basement flooding')
b4 = _make_building(with_basement=True, with_peri=True, sump_cfg=sump3)
i4 = _make_ingress(bypass_area=BYPASS_A_LARGE)
d4 = _run(b4, i4, 'case4_bypass_dominated')
_save(d4, 'case4_bypass_dominated', 'Case 4 — Bypass-dominated flooding')

# ── Case 5: pump-limited / near-failure ───────────────────────────────────────
print('Case 5: Pump-limited / near-failure')
sump5 = dict(
    sump_area          = 4.0,
    sump_base_elevation= BASEMENT_ELEV,
    overflow_level     = 0.6,
    overflow_coeff     = 1.8,
    overflow_exponent  = 1.5,
    pump_on_level      = 0.35,
    pump_off_level     = 0.15,
    pump_shutoff_head  = 2.8,
    pump_curve_coeff   = 1400.0,
    pipe_loss_coeff    = 300.0,
)
b5 = _make_building(with_basement=True, with_peri=True, sump_cfg=sump5)
i5 = _make_ingress(bypass_area=BYPASS_A_SMALL)
d5 = _run(b5, i5, 'case5_pump_limited')
_save(d5, 'case5_pump_limited', 'Case 5 — Pump-limited sump')

print('\nDone. All dashboard PNGs written to:')
print(f'  {ASSET_DIR}')
