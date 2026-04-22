#!/usr/bin/env python3
"""Tests for diagnostics generation and interpretation plotting."""

from pathlib import Path
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from report import (diagnostics_from_trace, diagnostics_to_csv_rows,
                    generate_narrative, run_diagnostics)
from engine import Building, IngressPathway, Simulation
from pump import SumpPump
import plot as viz


def _make_sump_building():
    building = Building(floor_area=50.0)
    building.basement_area = 50.0
    building.z_basement = -2.5
    building.basement_ceiling_elevation = 0.0
    building.basement_ingress = IngressPathway(
        height=0.0,
        area=0.0035,
        coeff=0.5,
        name='ext-basement-perimeter',
        source='outside',
        target='basement',
    )
    building.sump_pump = SumpPump(
        sump_area=8.0,
        overflow_level=0.8,
        overflow_coeff=1.8,
        overflow_exponent=1.5,
        pump_on_level=0.5,
        pump_off_level=0.2,
        pump_shutoff_head=3.5,
        pump_curve_coeff=800.0,
        pipe_loss_coeff=200.0,
        sump_base_elevation=-2.5,
        pump_availability=1.0,
    )
    return building


def _make_runtime_ingress():
    return [
        IngressPathway(0.0, 0.01, 0.6, name='wall_crack'),
        IngressPathway(
            height=0.0,
            area=0.001,
            coeff=1.0,
            name='ground-basement-conn',
            source='ground',
            target='basement',
        ),
    ]


def _make_case():
    return (
        _make_sump_building(),
        _make_runtime_ingress(),
        [0.0, 1800.0, 3600.0],
        [0.0, 0.8, 0.0],
        6.0,
    )


def test_run_diagnostics_matches_trace_based_diagnostics_for_sump_case():
    building, ingress, times, levels, dt = _make_case()
    sim = Simulation(_make_sump_building(), _make_runtime_ingress(), times, levels, dt=dt)
    sim.run()

    diag_from_trace = diagnostics_from_trace(sim._last_trace, sim.dt)
    diag_from_wrapper = run_diagnostics(building, ingress, times, levels, dt=dt)

    list_keys = [
        'times', 'H_out', 'h_in', 'h_basement', 'h_sump', 'H_lift',
        'pump_state', 'Q_ext_b', 'Q_b_bs', 'Q_ext_perimeter',
        'Q_pump', 'Q_sump_overflow',
    ]
    for key in list_keys:
        assert len(diag_from_wrapper[key]) == len(diag_from_trace[key])
        assert max(abs(a - b) for a, b in zip(diag_from_wrapper[key], diag_from_trace[key])) < 1e-12

    scalar_event_keys = [
        'vol_ext_b_total',
        'vol_perimeter_total',
        'vol_b_bs_total',
        'vol_pump_total',
        'vol_sump_overflow_total',
    ]
    for key in scalar_event_keys:
        assert abs(diag_from_wrapper['events'][key] - diag_from_trace['events'][key]) < 1e-12


def test_diagnostics_summary_rows_and_narrative_are_populated():
    building, ingress, times, levels, dt = _make_case()
    diag = run_diagnostics(building, ingress, times, levels, dt=dt)
    events = diag['events']

    assert events['sump_configured'] is True
    assert events['vol_perimeter_total'] > 0.0
    assert events['vol_pump_total'] > 0.0
    assert events['pump_interception_ratio'] is not None
    assert events['dominant_basement_source'] in {'perimeter', 'bypass'}

    rows = list(diagnostics_to_csv_rows(diag))
    assert rows
    assert 'Q_pump' in rows[0]
    assert len(rows) == len(diag['times']) + 1

    narrative = generate_narrative(diag)
    assert any('Peak ground-floor depth' in line for line in narrative)
    assert any('Peak basement depth' in line for line in narrative)
    assert any('Pump' in line or 'pump' in line for line in narrative)


def test_interpretation_dashboard_and_result_plot_are_created(tmp_path):
    building, ingress, times, levels, dt = _make_case()
    diag = run_diagnostics(building, ingress, times, levels, dt=dt)

    dashboard_path = Path(tmp_path) / 'interpretation_dashboard.png'
    result_path = Path(tmp_path) / 'simulation_result.png'
    times_display = [t / 60.0 for t in diag['times']]

    viz.save_interpretation_dashboard(diag, str(dashboard_path), time_unit='minutes')
    viz.save_simulation_result(
        times_display,
        diag['h_in'],
        diag['H_out'],
        str(result_path),
        time_unit='minutes',
        basement_levels=diag['h_basement'],
        sump_levels=diag['h_sump'],
    )

    assert dashboard_path.exists()
    assert dashboard_path.stat().st_size > 0
    assert result_path.exists()
    assert result_path.stat().st_size > 0
