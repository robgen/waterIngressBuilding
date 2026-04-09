#!/usr/bin/env python3
"""Generate tutorial dashboard and result-plot assets for the interpretation guide."""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import viz
from diagnostics import run_diagnostics
from main import Building, IngressPathway, parse_external_file, parse_ingress_file
from pump import SumpPump


EXTERNAL_PATH = REPO_ROOT / 'example_run' / 'example_external_levels.csv'
INGRESS_PATH = REPO_ROOT / 'example_run' / 'example_ingress_paths.txt'
ASSET_DIR = REPO_ROOT / 'docs' / 'assets' / 'interpretation_dashboard'


CASE_STUDIES = [
    {
        'slug': 'case1_ground_only',
        'title': 'Case Study 1: Ground-Floor Ingress Only',
        'floor_area': 50.0,
        'dt_minutes': 0.1,
    },
    {
        'slug': 'case2_basement_no_sump',
        'title': 'Case Study 2: Basement Without Sump',
        'floor_area': 50.0,
        'dt_minutes': 0.1,
        'basement': {
            'area': 50.0,
            'floor_elevation': -2.5,
            'ceiling_elevation': 0.0,
            'ingress_height': 0.0,
            'ingress_area': 0.0035,
            'ingress_coeff': 0.5,
            'connection_height': 0.0,
            'connection_area': 0.001,
        },
    },
    {
        'slug': 'case3_basement_sump_effective',
        'title': 'Case Study 3: Basement With Effective Sump Protection',
        'floor_area': 50.0,
        'dt_minutes': 0.1,
        'basement': {
            'area': 50.0,
            'floor_elevation': -2.5,
            'ceiling_elevation': 0.0,
            'ingress_height': 0.0,
            'ingress_area': 0.0035,
            'ingress_coeff': 0.5,
            'connection_height': 0.0,
            'connection_area': 0.001,
        },
        'sump': {
            'sump_area': 8.0,
            'overflow_level': 0.8,
            'overflow_coeff': 1.8,
            'overflow_exponent': 1.5,
            'pump_on_level': 0.5,
            'pump_off_level': 0.2,
            'pump_shutoff_head': 3.5,
            'pump_curve_coeff': 800.0,
            'pipe_loss_coeff': 200.0,
            'sump_base_elevation': -2.5,
            'pump_availability': 1.0,
        },
    },
    {
        'slug': 'case4_bypass_dominated',
        'title': 'Case Study 4: Bypass-Dominated Basement Flooding',
        'floor_area': 50.0,
        'dt_minutes': 0.1,
        'basement': {
            'area': 50.0,
            'floor_elevation': -2.5,
            'ceiling_elevation': 0.0,
            'ingress_height': 0.0,
            'ingress_area': 0.0035,
            'ingress_coeff': 0.5,
            'connection_height': 0.0,
            'connection_area': 0.010,
        },
        'sump': {
            'sump_area': 8.0,
            'overflow_level': 0.8,
            'overflow_coeff': 1.8,
            'overflow_exponent': 1.5,
            'pump_on_level': 0.5,
            'pump_off_level': 0.2,
            'pump_shutoff_head': 3.5,
            'pump_curve_coeff': 800.0,
            'pipe_loss_coeff': 200.0,
            'sump_base_elevation': -2.5,
            'pump_availability': 1.0,
        },
    },
    {
        'slug': 'case5_pump_limited',
        'title': 'Case Study 5: Pump-Limited Or Near-Failure Sump Behaviour',
        'floor_area': 50.0,
        'dt_minutes': 0.1,
        'basement': {
            'area': 50.0,
            'floor_elevation': -2.5,
            'ceiling_elevation': 0.0,
            'ingress_height': 0.0,
            'ingress_area': 0.0035,
            'ingress_coeff': 0.5,
            'connection_height': 0.0,
            'connection_area': 0.001,
        },
        'sump': {
            'sump_area': 4.0,
            'overflow_level': 0.6,
            'overflow_coeff': 1.8,
            'overflow_exponent': 1.5,
            'pump_on_level': 0.35,
            'pump_off_level': 0.15,
            'pump_shutoff_head': 2.8,
            'pump_curve_coeff': 1400.0,
            'pipe_loss_coeff': 300.0,
            'sump_base_elevation': -2.5,
            'pump_availability': 1.0,
        },
    },
]


def build_case(case):
    """Return a fresh Building and ingress list for one case study."""
    building = Building(case['floor_area'])
    ingress = list(parse_ingress_file(str(INGRESS_PATH)))

    basement = case.get('basement')
    if basement:
        building.basement_area = float(basement['area'])
        building.h_basement = 0.0
        building.z_basement = float(basement['floor_elevation'])
        building.basement_ceiling_elevation = float(basement['ceiling_elevation'])
        building.basement_ingress = IngressPathway(
            height=float(basement['ingress_height']),
            area=float(basement['ingress_area']),
            coeff=float(basement['ingress_coeff']),
            name='ext-basement-perimeter',
            source='outside',
            target='basement',
        )
        if float(basement['connection_area']) > 0.0:
            ingress.append(IngressPathway(
                height=float(basement['connection_height']),
                area=float(basement['connection_area']),
                coeff=1.0,
                name='ground-basement-conn',
                source='ground',
                target='basement',
            ))

    sump = case.get('sump')
    if sump:
        building.sump_pump = SumpPump(
            sump_area=float(sump['sump_area']),
            overflow_level=float(sump['overflow_level']),
            overflow_coeff=float(sump['overflow_coeff']),
            overflow_exponent=float(sump['overflow_exponent']),
            pump_on_level=float(sump['pump_on_level']),
            pump_off_level=float(sump['pump_off_level']),
            pump_shutoff_head=float(sump['pump_shutoff_head']),
            pump_curve_coeff=float(sump['pump_curve_coeff']),
            pipe_loss_coeff=float(sump['pipe_loss_coeff']),
            sump_base_elevation=float(sump['sump_base_elevation']),
            pump_availability=float(sump['pump_availability']),
        )

    return building, ingress


def run_case(case):
    """Run one case and save both dashboard and standard result PNGs."""
    times_minutes, levels = parse_external_file(str(EXTERNAL_PATH))
    times_seconds = [t * 60.0 for t in times_minutes]
    dt_seconds = float(case['dt_minutes']) * 60.0
    building, ingress = build_case(case)

    diag = run_diagnostics(
        building,
        ingress,
        times_seconds,
        levels,
        dt=dt_seconds,
    )

    dashboard_path = ASSET_DIR / f"{case['slug']}_dashboard.png"
    result_path = ASSET_DIR / f"{case['slug']}_result.png"
    times_display = [t / 60.0 for t in diag['times']]

    viz.save_interpretation_dashboard(
        diag,
        str(dashboard_path),
        time_unit='minutes',
        title_suffix=case['title'],
    )
    viz.save_simulation_result(
        times_display,
        diag['h_in'],
        diag['H_out'],
        str(result_path),
        time_unit='minutes',
        basement_levels=diag['h_basement'],
        sump_levels=diag['h_sump'],
    )
    return dashboard_path, result_path


def main():
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    print(f'Writing tutorial assets to {ASSET_DIR}')
    for case in CASE_STUDIES:
        dashboard_path, result_path = run_case(case)
        print(f"- {case['title']}")
        print(f"  dashboard: {dashboard_path.relative_to(REPO_ROOT)}")
        print(f"  result:    {result_path.relative_to(REPO_ROOT)}")


if __name__ == '__main__':
    main()
