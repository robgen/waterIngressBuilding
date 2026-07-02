"""Tests for the probabilistic fragility layer (fragility.py).

Covers:
  - Data model and FragilityDefinition validation
  - sample_thresholds (lognormal inversion)
  - select_active_state
  - Parsing: ingress fragility file, membrane file, membrane args,
             basement fragility args
  - validate_fragility_inputs
  - assign_representative_paths
  - make_conductance_resolver (membrane intact / overtopped, path fragility)
  - make_basement_step_resolver
  - Monte Carlo: single deterministic replicate matches classic solver;
                 ensemble percentiles have correct ordering
"""

import math
import os
import tempfile

import numpy as np
import pytest

from fragility import (
    FragilityDefinition,
    FragilityState,
    FragilePath,
    Membrane,
    BasementFragility,
    SampledThresholds,
    parse_pathway_file,
    fragile_path_to_membrane,
    parse_membrane_args,
    merge_membrane_source,
    parse_basement_fragility_args,
    validate_fragility_inputs,
    assign_representative_paths,
    sample_all_thresholds,
    sample_thresholds,
    select_active_state,
    get_conductance,
    make_conductance_resolver,
    make_basement_step_resolver,
    run_fragility_montecarlo,
)
from engine import Building, IngressPathway, Simulation


# ─────────────────────────────────────────────────────────────────────────────
# FragilityDefinition — validation and sampling
# ─────────────────────────────────────────────────────────────────────────────

def test_fragility_definition_rejects_empty():
    frag = FragilityDefinition(states=[])
    with pytest.raises(ValueError):
        frag.validate("test")


def test_fragility_definition_rejects_non_monotonic():
    frag = FragilityDefinition(states=[
        FragilityState("s1", median_m=0.5, beta_ln=0.3, area_m2=1e-2, Cd=0.6),
        FragilityState("s2", median_m=0.3, beta_ln=0.3, area_m2=1e-1, Cd=0.6),
    ])
    with pytest.raises(ValueError, match="Non-monotonic"):
        frag.validate("door")


def test_fragility_definition_accepts_monotonic():
    frag = FragilityDefinition(states=[
        FragilityState("s1", median_m=0.4, beta_ln=0.3, area_m2=1e-2, Cd=0.6),
        FragilityState("s2", median_m=0.8, beta_ln=0.3, area_m2=1e-1, Cd=0.6),
    ])
    frag.validate("door")  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# sample_thresholds
# ─────────────────────────────────────────────────────────────────────────────

def _make_one_state_frag(median=0.6, beta=0.35):
    return FragilityDefinition([
        FragilityState("baseline", median, beta, 3e-2, 0.6)
    ])


def test_sample_thresholds_at_u_half_equals_median():
    """At u=0.5, Φ⁻¹(0.5)=0, so h* = η·exp(0) = η."""
    frag = _make_one_state_frag(median=0.6, beta=0.35)
    thresholds = frag.sample_thresholds(0.5)
    assert len(thresholds) == 1
    assert abs(thresholds[0] - 0.6) < 1e-10


def test_sample_thresholds_increases_with_u():
    """Higher u → stronger specimen → higher capacity threshold."""
    frag = _make_one_state_frag(median=0.6, beta=0.35)
    h_low  = frag.sample_thresholds(0.1)[0]
    h_mid  = frag.sample_thresholds(0.5)[0]
    h_high = frag.sample_thresholds(0.9)[0]
    assert h_low < h_mid < h_high


def test_sample_thresholds_two_states_monotonic():
    """Sampled thresholds must be strictly increasing for any u."""
    frag = FragilityDefinition([
        FragilityState("s1", 0.4, 0.30, 1e-2, 0.6),
        FragilityState("s2", 0.8, 0.30, 1e-1, 0.6),
    ])
    for u in [0.1, 0.3, 0.5, 0.7, 0.9]:
        thr = frag.sample_thresholds(u)
        assert thr[0] < thr[1], f"Non-monotonic thresholds at u={u}: {thr}"


def test_sample_thresholds_standalone_function():
    """The module-level sample_thresholds function mirrors FragilityDefinition.sample_thresholds."""
    frag = _make_one_state_frag(median=0.5, beta=0.2)
    assert sample_thresholds(frag, 0.5) == frag.sample_thresholds(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# select_active_state
# ─────────────────────────────────────────────────────────────────────────────

def test_select_active_state_below_all_thresholds():
    assert select_active_state(0.1, [0.5, 1.0]) == 0


def test_select_active_state_above_first_only():
    assert select_active_state(0.7, [0.5, 1.0]) == 1


def test_select_active_state_above_all():
    assert select_active_state(1.5, [0.5, 1.0]) == 2


def test_select_active_state_no_thresholds():
    assert select_active_state(999.0, []) == 0


def test_select_active_state_exact_boundary():
    # at exactly the threshold → transitions to that state
    assert select_active_state(0.5, [0.5]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# get_conductance
# ─────────────────────────────────────────────────────────────────────────────

def test_get_conductance_base_state():
    p = FragilePath("door", 0.0, 4e-7, 0.6, 0, _make_one_state_frag(0.6, 0.35),
                    reversible=False)
    area, cd = get_conductance(p, 0)
    assert area == 4e-7
    assert cd == 0.6


def test_get_conductance_degraded_state():
    frag = _make_one_state_frag(0.6, 0.35)
    frag.states[0].area_m2 = 3e-2
    frag.states[0].Cd = 0.65
    p = FragilePath("door", 0.0, 4e-7, 0.6, 0, frag, reversible=False)
    area, cd = get_conductance(p, 1)
    assert area == 3e-2
    assert cd == 0.65


def test_get_conductance_no_fragility_any_state():
    p = FragilePath("crack", 0.0, 5e-4, 0.6, 0, None)
    area, cd = get_conductance(p, 0)
    assert area == 5e-4


# ─────────────────────────────────────────────────────────────────────────────
# Parsing — pathway file (unified format)
# ─────────────────────────────────────────────────────────────────────────────

def _write_temp_csv(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix='.csv')
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    return path


def test_parse_pathway_deterministic_paths():
    path = _write_temp_csv(
        "name, height_m, area_m2, Cd\n"
        "crack, 0.00, 5.0e-4, 0.60\n"
        "vent,  0.10, 8.0e-3, 0.60\n"
    )
    try:
        paths = parse_pathway_file(path)
        assert len(paths) == 2
        assert paths[0].name == 'crack'
        assert paths[0].fragility is None
        assert paths[0].group_id == 0
        assert paths[1].height_m == pytest.approx(0.10)
    finally:
        os.remove(path)


def test_parse_pathway_one_fragility_state():
    path = _write_temp_csv(
        "name, height_m, area_m2, Cd, group_id, reversible,"
        " state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1\n"
        "flood_door, 0.00, 4.0e-7, 0.60, 0, 0, baseline, 0.70, 0.35, 3.0e-2, 0.60\n"
    )
    try:
        paths = parse_pathway_file(path)
        assert len(paths) == 1
        p = paths[0]
        assert p.fragility is not None
        assert p.reversible is False
        assert len(p.fragility.states) == 1
        assert p.fragility.states[0].median_m == pytest.approx(0.70)
        assert p.fragility.states[0].area_m2 == pytest.approx(3e-2)
    finally:
        os.remove(path)


def test_parse_pathway_two_fragility_states():
    path = _write_temp_csv(
        "name, height_m, area_m2, Cd, group_id, reversible,"
        " state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1,"
        " state_name_2, median_m_2, beta_ln_2, area_m2_2, Cd_2\n"
        "door, 0.00, 4e-7, 0.6, 0, 0, s1, 0.4, 0.3, 1e-2, 0.6, s2, 0.8, 0.3, 3e-2, 0.6\n"
    )
    try:
        paths = parse_pathway_file(path)
        frag = paths[0].fragility
        assert len(frag.states) == 2
        assert frag.states[0].median_m < frag.states[1].median_m
    finally:
        os.remove(path)


def test_validate_rejects_non_monotonic():
    path = _write_temp_csv(
        "name, height_m, area_m2, Cd, group_id, reversible,"
        " state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1,"
        " state_name_2, median_m_2, beta_ln_2, area_m2_2, Cd_2\n"
        "door, 0.00, 4e-7, 0.6, 0, 0, s1, 0.8, 0.3, 1e-2, 0.6, s2, 0.4, 0.3, 3e-2, 0.6\n"
    )
    try:
        paths = parse_pathway_file(path)
        with pytest.raises(ValueError, match="Non-monotonic"):
            validate_fragility_inputs(paths, [])
    finally:
        os.remove(path)


def test_parse_pathway_grouped_path_no_fragility():
    path = _write_temp_csv(
        "name, height_m, area_m2, Cd, group_id\n"
        "airbrick, 0.10, 8e-3, 0.60, 1\n"
    )
    try:
        paths = parse_pathway_file(path)
        assert paths[0].group_id == 1
        assert paths[0].fragility is None
    finally:
        os.remove(path)


def test_validate_rejects_grouped_ingress_with_fragility():
    # reversible column present so parse succeeds; group_id+fragility conflict
    # is then caught by validate_fragility_inputs
    path = _write_temp_csv(
        "name, height_m, area_m2, Cd, group_id, reversible,"
        " state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1\n"
        "airbrick, 0.10, 8e-3, 0.60, 1, 0, s1, 0.4, 0.3, 1e-2, 0.6\n"
    )
    try:
        paths = parse_pathway_file(path)
        with pytest.raises(ValueError, match="membrane-protected"):
            validate_fragility_inputs(paths, [])
    finally:
        os.remove(path)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing — membrane file (unified format + fragile_path_to_membrane)
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_membrane_unified_format():
    path = _write_temp_csv(
        "name, height_m, area_m2, Cd, group_id, reversible,"
        " state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1\n"
        "perimeter_barrier, 0.00, 1.0e-5, 0.60, 1, 1, overtopped, 0.60, 0.07, 1e-9, 0.6\n"
    )
    try:
        fps = parse_pathway_file(path)
        assert len(fps) == 1
        assert fps[0].reversible is True
        m = fragile_path_to_membrane(fps[0])
        assert m.group_id == 1
        assert m.reversible is True
        assert m.height_m == pytest.approx(0.0)
        assert m.fragility.states[0].median_m == pytest.approx(0.60)
        assert m.fragility.states[0].beta_ln == pytest.approx(0.07)
    finally:
        os.remove(path)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing — membrane args
# ─────────────────────────────────────────────────────────────────────────────

class _Args:
    """Minimal argparse.Namespace stand-in."""
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_parse_membrane_args_none_when_not_supplied():
    args = _Args()
    assert parse_membrane_args(args) is None


def test_parse_membrane_args_builds_membrane():
    args = _Args(
        membrane_group=2, membrane_height=0.0,
        membrane_area=1e-5, membrane_Cd=0.6,
        membrane_median=0.6, membrane_beta=0.07,
        membrane_reversible=1,
    )
    m = parse_membrane_args(args)
    assert m is not None
    assert m.group_id == 2
    assert m.reversible is True
    assert m.fragility.states[0].median_m == pytest.approx(0.6)


def test_parse_membrane_args_raises_on_partial():
    args = _Args(membrane_group=1, membrane_height=0.0)
    with pytest.raises(ValueError, match="Incomplete"):
        parse_membrane_args(args)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing — merge_membrane_source
# ─────────────────────────────────────────────────────────────────────────────

def _make_membrane(gid, reversible=True):
    frag = FragilityDefinition([FragilityState("ot", 0.6, 0.07, 1e-9, 0.6)])
    return Membrane(gid, 0.0, 1e-5, 0.6, frag, reversible=reversible)


def test_merge_membrane_source_file_only():
    result = merge_membrane_source([_make_membrane(1)], None)
    assert len(result) == 1 and result[0].group_id == 1


def test_merge_membrane_source_args_only():
    result = merge_membrane_source(None, _make_membrane(2))
    assert len(result) == 1 and result[0].group_id == 2


def test_merge_membrane_source_args_override_file():
    file_m = _make_membrane(1)
    file_m.area_m2 = 1e-4
    arg_m = _make_membrane(1)
    arg_m.area_m2 = 9e-6
    result = merge_membrane_source([file_m], arg_m)
    assert len(result) == 1
    assert result[0].area_m2 == pytest.approx(9e-6)


def test_merge_membrane_source_both_empty():
    assert merge_membrane_source(None, None) == []


# ─────────────────────────────────────────────────────────────────────────────
# Parsing — basement fragility args
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_basement_fragility_args_none_when_absent():
    args = _Args()
    assert parse_basement_fragility_args(args) is None


def test_parse_basement_fragility_args_one_state():
    args = _Args(
        basement_state_name_1='baseline',
        basement_median_1=0.65,
        basement_beta_1=0.35,
        basement_area_1=0.02,
        basement_Cd_1=0.6,
    )
    bf = parse_basement_fragility_args(args)
    assert bf is not None
    assert bf.fragility.states[0].median_m == pytest.approx(0.65)


def test_parse_basement_fragility_args_raises_on_partial():
    args = _Args(basement_state_name_1='s1', basement_median_1=0.5)
    with pytest.raises(ValueError, match="Incomplete basement"):
        parse_basement_fragility_args(args)


# ─────────────────────────────────────────────────────────────────────────────
# validate_fragility_inputs & assign_representative_paths
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_rejects_grouped_path_with_fragility():
    # group_id+fragility conflict is caught before reversible check
    frag = FragilityDefinition([FragilityState("s1", 0.5, 0.3, 1e-2, 0.6)])
    paths = [FragilePath("ab1", 0.1, 8e-3, 0.6, 1, frag, reversible=False)]
    with pytest.raises(ValueError, match="membrane-protected"):
        validate_fragility_inputs(paths, [])


def test_validate_accepts_valid_inputs():
    frag = FragilityDefinition([FragilityState("s1", 0.5, 0.3, 1e-2, 0.6)])
    paths = [
        FragilePath("door", 0.0, 4e-7, 0.6, 0, frag, reversible=False),
        FragilePath("ab1",  0.1, 8e-3, 0.6, 1, None),
    ]
    validate_fragility_inputs(paths, [])  # must not raise


def test_validate_rejects_fragile_path_missing_reversible():
    """A fragile path without reversible flag must fail validation."""
    frag = FragilityDefinition([FragilityState("s1", 0.5, 0.3, 1e-2, 0.6)])
    paths = [FragilePath("door", 0.0, 4e-7, 0.6, 0, frag)]  # no reversible
    with pytest.raises(ValueError, match="reversible"):
        validate_fragility_inputs(paths, [])


def test_assign_representative_paths():
    paths = [
        FragilePath("ab1", 0.1, 8e-3, 0.6, 1, None),
        FragilePath("ab2", 0.1, 8e-3, 0.6, 1, None),
    ]
    m = _make_membrane(1)
    assign_representative_paths(paths, [m])
    assert m.representative_path_idx == 0


def test_assign_representative_paths_raises_for_unknown_group():
    paths = [FragilePath("ab1", 0.1, 8e-3, 0.6, 2, None)]
    m = _make_membrane(99)
    with pytest.raises(ValueError, match="group_id=99"):
        assign_representative_paths(paths, [m])


# ─────────────────────────────────────────────────────────────────────────────
# make_conductance_resolver — membrane logic
# ─────────────────────────────────────────────────────────────────────────────

def _paths_with_membrane():
    """Two grouped paths (group_id=1) + one ungrouped deterministic path."""
    return [
        FragilePath("ab1", 0.10, 8e-3, 0.60, 1, None),  # representative (idx 0)
        FragilePath("ab2", 0.10, 8e-3, 0.60, 1, None),
        FragilePath("crack", 0.00, 5e-4, 0.60, 0, None),
    ]


def _membrane_gid1(median=0.60, beta=0.07, reversible=True):
    frag = FragilityDefinition([FragilityState("overtopped", median, beta, 1e-9, 0.6)])
    m = Membrane(1, 0.0, 1e-5, 0.6, frag, reversible=reversible,
                 representative_path_idx=0)
    return m


def test_resolver_membrane_intact_representative_carries_membrane_params():
    paths = _paths_with_membrane()
    m = _membrane_gid1(median=0.60)
    # Force threshold = 0.60; set h_ext = 0.30 → depth above sill = 0.30 < 0.60 → intact
    sampled = SampledThresholds(
        membrane_thresholds={1: [0.60]},
        u_values={'membrane:1': 0.5},
    )
    resolver = make_conductance_resolver(paths, [m], sampled)
    active = resolver(0.30)  # h_ext below membrane threshold
    by_name = {ip.name: ip for ip in active}
    # representative path should carry membrane area
    assert by_name['ab1'].area == pytest.approx(1e-5)
    # non-representative grouped path suppressed
    assert by_name['ab2'].area == pytest.approx(1e-9)
    # ungrouped path unchanged
    assert by_name['crack'].area == pytest.approx(5e-4)


def test_resolver_membrane_overtopped_restores_group_paths():
    paths = _paths_with_membrane()
    m = _membrane_gid1(median=0.60)
    sampled = SampledThresholds(
        membrane_thresholds={1: [0.60]},
        u_values={'membrane:1': 0.5},
    )
    resolver = make_conductance_resolver(paths, [m], sampled)
    # h_ext = 0.80 → depth above sill = 0.80 ≥ 0.60 → overtopped
    active = resolver(0.80)
    by_name = {ip.name: ip for ip in active}
    # both group paths restored to their own base area
    assert by_name['ab1'].area == pytest.approx(8e-3)
    assert by_name['ab2'].area == pytest.approx(8e-3)


def test_resolver_probabilistic_path_state_switches():
    """A path with fragility uses degraded conductance once depth exceeds threshold."""
    frag = FragilityDefinition([FragilityState("baseline", 0.5, 0.3, 3e-2, 0.6)])
    paths = [FragilePath("door", 0.0, 4e-7, 0.6, 0, frag, reversible=True)]
    # Fix threshold at exactly 0.50
    sampled = SampledThresholds(
        path_thresholds={'door': [0.50]},
        u_values={'door': 0.5},
    )
    resolver = make_conductance_resolver(paths, [], sampled)

    # Below threshold → base state
    below = resolver(0.40)
    assert below[0].area == pytest.approx(4e-7)

    # Above threshold → degraded state
    above = resolver(0.70)
    assert above[0].area == pytest.approx(3e-2)


# ─────────────────────────────────────────────────────────────────────────────
# make_basement_step_resolver
# ─────────────────────────────────────────────────────────────────────────────

def test_basement_step_resolver_no_fragility_returns_base():
    step = make_basement_step_resolver(None, SampledThresholds(), 0.02, 0.6, 0.0)
    area, cd = step(0.5)
    assert area == pytest.approx(0.02)
    assert cd == pytest.approx(0.6)


def test_basement_step_resolver_switches_state():
    frag = FragilityDefinition([FragilityState("s1", 0.5, 0.3, 0.02, 0.6)])
    bf = BasementFragility(frag)
    sampled = SampledThresholds(basement_thresholds=[0.50])
    step = make_basement_step_resolver(bf, sampled, 4e-7, 0.6, 0.0)
    # Below threshold
    area, _ = step(0.30)
    assert area == pytest.approx(4e-7)
    # Above threshold
    area, _ = step(0.70)
    assert area == pytest.approx(0.02)


# ─────────────────────────────────────────────────────────────────────────────
# Monte Carlo integration tests
# ─────────────────────────────────────────────────────────────────────────────

def _simple_building():
    return Building(floor_area=50.0)


def _hydrograph():
    # 0 → 1 m over 10 minutes, then flat
    times   = [0.0, 300.0, 600.0, 1200.0]
    levels  = [0.0, 0.5,   1.0,   1.0]
    return times, levels


def test_montecarlo_single_replicate_no_fragility_matches_classic():
    """With no fragility, a 1-replicate MC must match the classic Simulation exactly."""
    times, levels = _hydrograph()
    ingress_classic = [IngressPathway(0.0, 5e-4, 0.6, 'crack')]
    sim = Simulation(_simple_building(), ingress_classic, times, levels, dt=30.0)
    _, classic_levels = sim.run()

    paths = [FragilePath('crack', 0.0, 5e-4, 0.6, 0, None)]

    def factory():
        return _simple_building()

    result = run_fragility_montecarlo(
        building_factory=factory,
        paths=paths,
        membranes=[],
        basement_fragility=None,
        external_times=times,
        external_levels=levels,
        n_replicates=1,
        dt=30.0,
        seed=0,
    )
    assert len(result.replicates) == 1
    mc_peak = result.replicates[0].peak_h_in
    assert abs(mc_peak - max(classic_levels)) < 1e-9


def test_montecarlo_percentile_ordering():
    """P10 ≤ P50 ≤ P90 for peak_h_in across a non-trivial ensemble."""
    times, levels = _hydrograph()
    frag = FragilityDefinition([FragilityState("s1", 0.6, 0.35, 3e-2, 0.6)])
    paths = [FragilePath("door", 0.0, 4e-7, 0.6, 0, frag, reversible=True)]

    def factory():
        return _simple_building()

    result = run_fragility_montecarlo(
        building_factory=factory,
        paths=paths,
        membranes=[],
        basement_fragility=None,
        external_times=times,
        external_levels=levels,
        n_replicates=200,
        dt=30.0,
        seed=42,
    )
    pcts = result.percentiles['peak_h_in']
    assert pcts['P10'] <= pcts['P50'] <= pcts['P90']


def test_montecarlo_state_frequency_bounded():
    """State frequencies must be in [0, 1] and state_0 frequency == 1.0."""
    times, levels = _hydrograph()
    frag = FragilityDefinition([FragilityState("s1", 0.6, 0.35, 3e-2, 0.6)])
    paths = [FragilePath("door", 0.0, 4e-7, 0.6, 0, frag, reversible=True)]

    def factory():
        return _simple_building()

    result = run_fragility_montecarlo(
        building_factory=factory,
        paths=paths,
        membranes=[],
        basement_fragility=None,
        external_times=times,
        external_levels=levels,
        n_replicates=100,
        dt=30.0,
        seed=7,
    )
    freqs = result.state_frequencies.get('door', [])
    assert len(freqs) == 2  # state 0 and state 1
    assert freqs[0] == pytest.approx(1.0)
    assert 0.0 <= freqs[1] <= 1.0


def test_montecarlo_rank_correlation_keys():
    """Rank correlations dict contains a key for each probabilistic element."""
    times, levels = _hydrograph()
    frag = FragilityDefinition([FragilityState("s1", 0.6, 0.35, 3e-2, 0.6)])
    paths = [FragilePath("door", 0.0, 4e-7, 0.6, 0, frag, reversible=True)]

    def factory():
        return _simple_building()

    result = run_fragility_montecarlo(
        building_factory=factory,
        paths=paths,
        membranes=[],
        basement_fragility=None,
        external_times=times,
        external_levels=levels,
        n_replicates=100,
        dt=30.0,
        seed=11,
    )
    assert 'door' in result.rank_correlations


def test_montecarlo_reproducible_with_seed():
    """Two runs with the same seed produce identical results."""
    times, levels = _hydrograph()
    frag = FragilityDefinition([FragilityState("s1", 0.6, 0.35, 3e-2, 0.6)])
    paths = [FragilePath("door", 0.0, 4e-7, 0.6, 0, frag, reversible=True)]

    def factory():
        return _simple_building()

    r1 = run_fragility_montecarlo(factory, paths, [], None, times, levels, 50, 30.0, seed=99)
    r2 = run_fragility_montecarlo(factory, paths, [], None, times, levels, 50, 30.0, seed=99)
    peaks1 = [rec.peak_h_in for rec in r1.replicates]
    peaks2 = [rec.peak_h_in for rec in r2.replicates]
    assert peaks1 == peaks2


def test_montecarlo_membrane_intact_reduces_ingress():
    """With membrane intact (threshold never exceeded), peak ingress is lower
    than without membrane (paths carrying 10⁻⁹ vs 8e-3 m²)."""
    times, levels = _hydrograph()
    # Without membrane — paths carry full 8e-3 area
    paths_bare = [
        FragilePath("ab1", 0.10, 8e-3, 0.6, 0, None),
        FragilePath("ab2", 0.10, 8e-3, 0.6, 0, None),
    ]
    # With membrane — threshold at 2.0 m (never exceeded), so paths suppressed
    frag_mem = FragilityDefinition([FragilityState("ot", 2.0, 0.05, 1e-9, 0.6)])
    m = Membrane(1, 0.0, 1e-9, 0.6, frag_mem, reversible=True,
                 representative_path_idx=0)
    paths_with_mem = [
        FragilePath("ab1", 0.10, 8e-3, 0.6, 1, None),
        FragilePath("ab2", 0.10, 8e-3, 0.6, 1, None),
    ]

    def factory():
        return _simple_building()

    r_bare = run_fragility_montecarlo(factory, paths_bare, [], None,
                                      times, levels, 1, 30.0, seed=0)
    r_mem  = run_fragility_montecarlo(factory, paths_with_mem, [m], None,
                                      times, levels, 1, 30.0, seed=0)
    peak_bare = r_bare.replicates[0].peak_h_in
    peak_mem  = r_mem.replicates[0].peak_h_in
    assert peak_mem < peak_bare


# ─────────────────────────────────────────────────────────────────────────────
# Reversible vs irreversible latch behaviour
# ─────────────────────────────────────────────────────────────────────────────

def test_irreversible_path_latches_degraded_state_after_recession():
    """An irreversible element stays degraded after the head drops below its
    capacity threshold; a reversible element reverts to base state."""
    # Hydrograph: rises to 0.8 m (above threshold 0.5 m), then drops to 0.1 m
    # (below threshold), then stays at 0.1 m.  After the recession the
    # irreversible path must remain in state 1; the reversible path must be
    # back in state 0.
    from fragility import SampledThresholds, make_conductance_resolver

    frag = FragilityDefinition([
        FragilityState("failed", median_m=0.5, beta_ln=0.3, area_m2=3e-2, Cd=0.6)
    ])
    # Fix capacity threshold at exactly 0.50 m
    sampled = SampledThresholds(
        path_thresholds={
            'irrev': [0.50],
            'rev':   [0.50],
        },
        u_values={'irrev': 0.5, 'rev': 0.5},
    )

    paths_irrev = [FragilePath("irrev", 0.0, 4e-7, 0.6, 0, frag, reversible=False)]
    paths_rev   = [FragilePath("rev",   0.0, 4e-7, 0.6, 0, frag, reversible=True)]

    resolver_irrev = make_conductance_resolver(paths_irrev, [], sampled)
    resolver_rev   = make_conductance_resolver(paths_rev,   [], sampled)

    # --- rising: h_ext = 0.8 m → depth above sill = 0.8 ≥ 0.5 → state 1 ---
    irrev_above = resolver_irrev(0.8)[0]
    rev_above   = resolver_rev(0.8)[0]
    assert irrev_above.area == pytest.approx(3e-2), "irrev should be degraded at peak"
    assert rev_above.area   == pytest.approx(3e-2), "rev should be degraded at peak"

    # --- recession: h_ext = 0.1 m → depth above sill = 0.1 < 0.5 ---
    irrev_below = resolver_irrev(0.1)[0]
    rev_below   = resolver_rev(0.1)[0]
    # irreversible: latched to state 1 → still degraded area
    assert irrev_below.area == pytest.approx(3e-2), \
        "irreversible path must stay degraded after head recedes below threshold"
    # reversible: back to base state → tiny base area
    assert rev_below.area == pytest.approx(4e-7), \
        "reversible path must revert to base state once head drops below threshold"


def test_irreversible_membrane_latches_overtopped_state():
    """An irreversible membrane latches in the overtopped state once triggered,
    even when head drops back below the threshold."""
    from fragility import SampledThresholds, make_conductance_resolver

    frag_mem = FragilityDefinition([
        FragilityState("overtopped", median_m=0.5, beta_ln=0.07, area_m2=1e-9, Cd=0.6)
    ])
    sampled = SampledThresholds(
        membrane_thresholds={1: [0.50]},
        u_values={'membrane:1': 0.5},
    )

    paths = [
        FragilePath("ab1", 0.0, 8e-3, 0.6, 1, None),
    ]
    m_irrev = Membrane(1, 0.0, 1e-5, 0.6, frag_mem, reversible=False,
                       representative_path_idx=0)
    m_rev   = Membrane(1, 0.0, 1e-5, 0.6, frag_mem, reversible=True,
                       representative_path_idx=0)

    res_irrev = make_conductance_resolver(paths, [m_irrev], sampled)
    res_rev   = make_conductance_resolver(paths, [m_rev],   sampled)

    # Rising: h_ext = 0.8 m → membrane depth = 0.8 ≥ 0.5 → overtopped
    irrev_above = {ip.name: ip for ip in res_irrev(0.8)}
    rev_above   = {ip.name: ip for ip in res_rev(0.8)}
    # When overtopped, ab1 is restored to its own area (8e-3)
    assert irrev_above['ab1'].area == pytest.approx(8e-3)
    assert rev_above['ab1'].area   == pytest.approx(8e-3)

    # Recession: h_ext = 0.1 m → membrane depth = 0.1 < 0.5 m
    irrev_below = {ip.name: ip for ip in res_irrev(0.1)}
    rev_below   = {ip.name: ip for ip in res_rev(0.1)}
    # Irreversible: still latched overtopped → ab1 at own area
    assert irrev_below['ab1'].area == pytest.approx(8e-3), \
        "irreversible membrane must remain overtopped after head recedes"
    # Reversible: back to intact → representative carries membrane area (1e-5)
    assert rev_below['ab1'].area == pytest.approx(1e-5), \
        "reversible membrane must restore to intact state once head drops below threshold"
