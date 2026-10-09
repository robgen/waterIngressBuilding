#!/usr/bin/env python3
"""Tests for diagnostics generation and interpretation plotting."""

from pathlib import Path
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from report import diagnostics_from_trace, diagnostics_to_csv_rows, generate_narrative
import engine
from engine import IngressPathway
from pump import SumpPump
import plot as viz


def _make_case():
    config = engine.SimConfig(
        floor_area=50.0,
        dt=6.0,
        basement_area=50.0,
        basement_floor_elevation=-2.5,
        basement_ceiling_elevation=0.0,
        basement_connection_height=0.0,
        basement_connection_area=0.001,
        basement_connection_coeff=1.0,
        sumppump=SumpPump(
            sump_area=8.0,
            pump_on_level=0.5,
            pump_off_level=0.2,
            pump_shutoff_head=3.5,
            pump_curve_coeff=800.0,
            pipe_loss_coeff=200.0,
            sump_base_elevation=-3.3,   # 0.8 m pit below the basement floor
            pump_availability=1.0,
        ),
        time_units='seconds',
    )
    hydro = engine.Hydrograph(times=[0.0, 1800.0, 3600.0], levels=[0.0, 0.8, 0.0])
    pathways = [
        IngressPathway(0.0, 0.01, 0.6, name='wall_crack'),
        IngressPathway(0.0, 0.0035, 0.5, name='ext-basement-perimeter',
                       source='outside', target='basement'),
    ]
    return config, hydro, pathways


def _run_case():
    config, hydro, pathways = _make_case()
    result = engine.run(config, hydro, pathways)
    return config, hydro, result, diagnostics_from_trace(result.trace, config.dt)


def test_diagnostics_summary_rows_and_narrative_are_populated():
    _, _, _, diag = _run_case()
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
    config, hydro, result, diag = _run_case()

    dashboard_path = Path(tmp_path) / 'interpretation_dashboard.png'
    result_path = Path(tmp_path) / 'simulation_result.png'

    viz.save_interpretation_dashboard(diag, str(dashboard_path), time_unit='seconds')
    viz.save_run_result(str(result_path), config, hydro, result)

    assert dashboard_path.exists()
    assert dashboard_path.stat().st_size > 0
    assert result_path.exists()
    assert result_path.stat().st_size > 0
