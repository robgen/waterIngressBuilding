"""Probabilistic fragility layer for water ingress modelling.

Implements the Monte Carlo fragility extension specified in
docs/fragility_ingress_spec.md.  The deterministic solver (main.py) is
untouched except for the conductance_resolver hook added to Simulation.

Public API
----------
Data model:   FragilityState, FragilityDefinition, FragilePath, Membrane,
              BasementFragility, SampledThresholds
Parsing:      parse_ingress_fragility_file, parse_membrane_file,
              parse_membrane_args, merge_membrane_source,
              parse_basement_fragility_args
Validation:   validate_fragility_inputs, assign_representative_paths
Sampling:     sample_thresholds, sample_all_thresholds
State logic:  select_active_state, get_conductance
Resolver:     make_conductance_resolver
Runner:       run_fragility_montecarlo, MonteCarloResult
"""

from __future__ import annotations

import csv
import math
import warnings
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import norm as _norm


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FragilityState:
    """One degraded hydraulic state and its lognormal fragility parameters."""
    state_name: str
    median_m: float    # η_k — depth above sill at 50 % exceedance (m)
    beta_ln: float     # β_k — log-standard deviation (–)
    area_m2: float     # orifice area in this state (m²)
    Cd: float          # discharge coefficient in this state (–)


@dataclass
class FragilityDefinition:
    """Ordered sequence of degraded states for one element.

    State 0 (base) is represented by the element's own area_m2 / Cd.
    States 1…N are represented by this list in ascending index order.
    Medians must be strictly increasing.
    """
    states: List[FragilityState]

    def validate(self, element_name: str = "?") -> None:
        """Raise ValueError if medians are non-monotonic or states are empty."""
        if not self.states:
            raise ValueError(f"FragilityDefinition for '{element_name}' has no states")
        medians = [s.median_m for s in self.states]
        for i in range(1, len(medians)):
            if medians[i] <= medians[i - 1]:
                raise ValueError(
                    f"Non-monotonic medians for '{element_name}': "
                    f"η_{i} = {medians[i]} ≤ η_{i-1} = {medians[i-1]}"
                )

    def sample_thresholds(self, u: float) -> List[float]:
        """Invert all fragility curves for a single uniform draw u ∈ (0,1).

        Returns [h*_1, …, h*_N] — capacity thresholds fixed for one replicate.
        h*_k = η_k · exp(β_k · Φ⁻¹(u))
        """
        z = float(_norm.ppf(u))
        return [s.median_m * math.exp(s.beta_ln * z) for s in self.states]


@dataclass
class FragilePath:
    """Canonical internal representation of one ingress path (all modes).

    Deterministic paths have fragility=None and group_id=0.
    Probabilistic paths have fragility defined and group_id=0.
    Membrane-protected paths have group_id != 0 and fragility=None (validated).
    """
    name: str
    height_m: float
    area_m2: float          # base-state orifice area
    Cd: float               # base-state discharge coefficient
    group_id: int = 0
    fragility: Optional[FragilityDefinition] = None


@dataclass
class Membrane:
    """Perimeter flood protection element shielding a group of ingress paths."""
    group_id: int
    height_m: float
    area_m2: float          # base-state lumped leakage area
    Cd: float
    fragility: FragilityDefinition   # always present; governs overtopping
    representative_path_idx: int = -1   # set by assign_representative_paths


@dataclass
class BasementFragility:
    """Optional fragility definition for the basement connection."""
    fragility: FragilityDefinition


@dataclass
class SampledThresholds:
    """Per-replicate capacity thresholds drawn before the time loop."""
    # path name  → [h*_1, …, h*_N]
    path_thresholds: Dict[str, List[float]] = field(default_factory=dict)
    # group_id   → [h*_1, …, h*_N]
    membrane_thresholds: Dict[int, List[float]] = field(default_factory=dict)
    # [h*_1, …, h*_N] or None
    basement_thresholds: Optional[List[float]] = None
    # element name → u draw (for output recording)
    u_values: Dict[str, float] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_fragility_states_from_parts(
    parts: List[str],
    start: int,
    element_name: str,
) -> Optional[FragilityDefinition]:
    """Parse zero or more fragility state blocks from a split CSV row.

    Each block occupies 5 columns: state_name, median_m, beta_ln, area_m2, Cd.
    Returns None when no state columns are present.
    Raises ValueError when a partial block is found.
    """
    states: List[FragilityState] = []
    idx = start
    block = 1
    while idx < len(parts):
        remaining = len(parts) - idx
        if remaining == 0:
            break
        if remaining < 5:
            raise ValueError(
                f"Incomplete fragility state block for '{element_name}' "
                f"(state {block}): expected 5 columns, got {remaining}"
            )
        sname = parts[idx].strip()
        try:
            median = float(parts[idx + 1])
            beta   = float(parts[idx + 2])
            area   = float(parts[idx + 3])
            cd     = float(parts[idx + 4])
        except ValueError as exc:
            raise ValueError(
                f"Non-numeric fragility parameter for '{element_name}' "
                f"state {block}: {exc}"
            ) from exc
        states.append(FragilityState(sname, median, beta, area, cd))
        idx += 5
        block += 1
    return FragilityDefinition(states) if states else None


def parse_ingress_fragility_file(filepath: str) -> List[FragilePath]:
    """Parse extended ingress CSV into a list of FragilePath objects.

    Format (per spec §3.1):
        name, height_m, area_m2, Cd, group_id
            [, state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1 [, …]]

    Comment lines (#) and blank lines are skipped.
    Validates inputs before returning (monotonic medians, completeness,
    fragility–membrane conflicts).
    """
    paths: List[FragilePath] = []
    n_skipped = 0
    with open(filepath, newline='') as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 5:
                n_skipped += 1
                continue
            try:
                name     = parts[0]
                height   = float(parts[1])
                area     = float(parts[2])
                cd       = float(parts[3])
                group_id = int(parts[4])
            except ValueError as exc:
                raise ValueError(
                    f"{filepath}:{lineno}: bad base columns — {exc}"
                ) from exc

            fragility = _parse_fragility_states_from_parts(parts, 5, name)
            paths.append(FragilePath(name, height, area, cd, group_id, fragility))

    if n_skipped:
        warnings.warn(f"{n_skipped} short line(s) skipped in {filepath}", stacklevel=2)
    if not paths:
        raise ValueError(f"No ingress paths found in {filepath}")

    validate_fragility_inputs(paths, [])
    return paths


def parse_membrane_file(filepath: str) -> List[Membrane]:
    """Parse membrane CSV into a list of Membrane objects.

    Format (per spec §3.2):
        group_id, height_m, area_m2, Cd,
        state_name_1, median_m_1, beta_ln_1, area_m2_1, Cd_1
            [, state_name_2, median_m_2, beta_ln_2, area_m2_2, Cd_2]

    At least one fragility state is required for every membrane row.
    """
    membranes: List[Membrane] = []
    with open(filepath, newline='') as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 9:
                warnings.warn(
                    f"{filepath}:{lineno}: membrane row needs ≥9 columns, skipped",
                    stacklevel=2,
                )
                continue
            try:
                group_id = int(parts[0])
                height   = float(parts[1])
                area     = float(parts[2])
                cd       = float(parts[3])
            except ValueError as exc:
                raise ValueError(
                    f"{filepath}:{lineno}: bad membrane base columns — {exc}"
                ) from exc

            fragility = _parse_fragility_states_from_parts(parts, 4, f"membrane:{group_id}")
            if fragility is None:
                raise ValueError(
                    f"{filepath}:{lineno}: membrane group_id={group_id} has no fragility states"
                )
            fragility.validate(f"membrane:{group_id}")
            membranes.append(Membrane(group_id, height, area, cd, fragility))

    if not membranes:
        raise ValueError(f"No membrane rows found in {filepath}")
    return membranes


def parse_membrane_args(args) -> Optional[Membrane]:
    """Build a single Membrane from --membrane-* CLI args, or None."""
    needed = ['membrane_group', 'membrane_height', 'membrane_area',
              'membrane_Cd', 'membrane_median', 'membrane_beta']
    if not any(getattr(args, k, None) is not None for k in needed):
        return None
    missing = [k for k in needed if getattr(args, k, None) is None]
    if missing:
        raise ValueError(f"Incomplete --membrane-* arguments; missing: {missing}")
    frag = FragilityDefinition([FragilityState(
        state_name='overtopped',
        median_m=float(args.membrane_median),
        beta_ln=float(args.membrane_beta),
        area_m2=1e-9,   # overtopped → paths carry their own params; membrane suppressed
        Cd=0.6,
    )])
    frag.validate('membrane (args)')
    return Membrane(
        group_id=int(args.membrane_group),
        height_m=float(args.membrane_height),
        area_m2=float(args.membrane_area),
        Cd=float(args.membrane_Cd),
        fragility=frag,
    )


def merge_membrane_source(
    file_membranes: Optional[List[Membrane]],
    arg_membrane: Optional[Membrane],
) -> List[Membrane]:
    """Apply override precedence (spec §3.3)."""
    if arg_membrane is None and not file_membranes:
        return []
    if arg_membrane is None:
        return list(file_membranes)
    if not file_membranes:
        return [arg_membrane]
    # both supplied — args override
    warnings.warn(
        "Both --membrane-file and --membrane-* arguments supplied; "
        "arguments override the file for matching group_id.",
        stacklevel=2,
    )
    merged = {m.group_id: m for m in file_membranes}
    merged[arg_membrane.group_id] = arg_membrane
    return list(merged.values())


def parse_basement_fragility_args(args) -> Optional[BasementFragility]:
    """Extract indexed --basement-state-name-N etc. args (up to state index 9).

    Returns None when no basement fragility arguments are present.
    Raises ValueError when a partial state definition is found.
    """
    states: List[FragilityState] = []
    for idx in range(1, 10):
        sname  = getattr(args, f'basement_state_name_{idx}', None)
        median = getattr(args, f'basement_median_{idx}', None)
        beta   = getattr(args, f'basement_beta_{idx}', None)
        area   = getattr(args, f'basement_area_{idx}', None)
        cd     = getattr(args, f'basement_Cd_{idx}', None)
        present = [x for x in (sname, median, beta, area, cd) if x is not None]
        if not present:
            break   # no more states
        if len(present) < 5:
            raise ValueError(
                f"Incomplete basement fragility definition for state {idx}: "
                "all five of --basement-state-name, --basement-median, "
                "--basement-beta, --basement-area, --basement-Cd are required"
            )
        states.append(FragilityState(
            state_name=str(sname),
            median_m=float(median),
            beta_ln=float(beta),
            area_m2=float(area),
            Cd=float(cd),
        ))
    if not states:
        return None
    frag = FragilityDefinition(states)
    frag.validate('basement')
    return BasementFragility(frag)


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_fragility_inputs(
    paths: List[FragilePath],
    membranes: List[Membrane],
) -> None:
    """Raise ValueError on any specification error.

    Checks:
    1. Fragility–membrane conflict: group_id != 0 paths must not have fragility.
    2. Monotonic medians for every probabilistic path.
    3. (Membrane monotonicity is checked at parse time.)
    """
    for p in paths:
        if p.group_id != 0 and p.fragility is not None:
            raise ValueError(
                f"Path '{p.name}' has group_id={p.group_id} (membrane-protected) "
                "but also defines fragility columns — this is not permitted "
                "(spec §4 / §3.1 rule)"
            )
        if p.fragility is not None:
            p.fragility.validate(p.name)


def assign_representative_paths(
    paths: List[FragilePath],
    membranes: List[Membrane],
) -> None:
    """Set representative_path_idx on each membrane (mutates in place).

    The representative path is the lowest row-index path in the ingress list
    that shares the membrane's group_id.  Raises ValueError if none found.
    """
    group_to_first: Dict[int, int] = {}
    for i, p in enumerate(paths):
        if p.group_id != 0 and p.group_id not in group_to_first:
            group_to_first[p.group_id] = i
    for m in membranes:
        if m.group_id not in group_to_first:
            raise ValueError(
                f"Membrane group_id={m.group_id} has no matching paths "
                "in the ingress list"
            )
        m.representative_path_idx = group_to_first[m.group_id]


# ─────────────────────────────────────────────────────────────────────────────
# Sampling
# ─────────────────────────────────────────────────────────────────────────────

def sample_thresholds(fragility_def: FragilityDefinition, u: float) -> List[float]:
    """Module-level convenience wrapper around FragilityDefinition.sample_thresholds."""
    return fragility_def.sample_thresholds(u)


def sample_all_thresholds(
    paths: List[FragilePath],
    membranes: List[Membrane],
    basement_fragility: Optional[BasementFragility],
    rng: np.random.Generator,
) -> SampledThresholds:
    """Draw one u per probabilistic element and invert all fragility curves."""
    result = SampledThresholds()
    for p in paths:
        if p.fragility is None:
            continue
        u = float(rng.uniform())
        result.u_values[p.name] = u
        result.path_thresholds[p.name] = p.fragility.sample_thresholds(u)
    for m in membranes:
        u = float(rng.uniform())
        key = f"membrane:{m.group_id}"
        result.u_values[key] = u
        result.membrane_thresholds[m.group_id] = m.fragility.sample_thresholds(u)
    if basement_fragility is not None:
        u = float(rng.uniform())
        result.u_values['basement'] = u
        result.basement_thresholds = basement_fragility.fragility.sample_thresholds(u)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# State selection
# ─────────────────────────────────────────────────────────────────────────────

def select_active_state(
    depth_above_sill: float,
    thresholds: List[float],
) -> int:
    """Return the highest state index k with depth_above_sill >= thresholds[k-1].

    Returns 0 (base state) when depth is below all thresholds.
    """
    active = 0
    for k, h_star in enumerate(thresholds, start=1):
        if depth_above_sill >= h_star:
            active = k
    return active


def get_conductance(
    path: FragilePath,
    active_state: int,
) -> Tuple[float, float]:
    """Return (area_m2, Cd) for the given active state index."""
    if active_state == 0 or path.fragility is None:
        return path.area_m2, path.Cd
    state = path.fragility.states[active_state - 1]
    return state.area_m2, state.Cd


# ─────────────────────────────────────────────────────────────────────────────
# Conductance resolver
# ─────────────────────────────────────────────────────────────────────────────

def make_conductance_resolver(
    paths: List[FragilePath],
    membranes: List[Membrane],
    sampled: SampledThresholds,
) -> Callable[[float], list]:
    """Return a callable(h_ext) -> list[IngressPathway] for one replicate.

    The returned list is a fresh set of IngressPathway objects with the
    correct (area_m2, Cd) for the current external head h_ext, taking into
    account both path-level fragility and membrane protection logic.

    Import is deferred to avoid a circular dependency with main.py.
    """
    from main import IngressPathway  # local import — main imports nothing from fragility

    # Build fast lookup: group_id -> list of (path_index, FragilePath)
    group_map: Dict[int, List[Tuple[int, FragilePath]]] = {}
    for i, p in enumerate(paths):
        if p.group_id != 0:
            group_map.setdefault(p.group_id, []).append((i, p))
    membrane_by_gid: Dict[int, Membrane] = {m.group_id: m for m in membranes}

    # Pre-build suppressed IngressPathway stubs (10⁻⁹ m²) for group members
    suppressed: Dict[str, IngressPathway] = {
        p.name: IngressPathway(
            height=p.height_m, area=1e-9, coeff=0.6, name=p.name,
        )
        for p in paths if p.group_id != 0
    }

    def resolver(h_ext: float) -> list:
        result: list = []
        # Track which paths have already been handled by membrane logic
        membrane_handled: set = set()

        for m in membranes:
            gid = m.group_id
            h_mem = max(0.0, h_ext - m.height_m)
            mem_thresholds = sampled.membrane_thresholds.get(gid, [])
            mem_state = select_active_state(h_mem, mem_thresholds)

            group_paths = group_map.get(gid, [])
            rep_idx = m.representative_path_idx

            for i, p in group_paths:
                membrane_handled.add(p.name)
                if mem_state == 0:
                    # Membrane intact: representative carries membrane params,
                    # all others suppressed
                    if i == rep_idx:
                        result.append(IngressPathway(
                            height=m.height_m, area=m.area_m2, coeff=m.Cd,
                            name=p.name,
                        ))
                    else:
                        result.append(suppressed[p.name])
                else:
                    # Membrane overtopped: all group paths restored to own base params.
                    # Representative additionally carries second-state conductance
                    # when state == 2 (spec §2.6).
                    if mem_state == 2 and i == rep_idx and len(m.fragility.states) >= 2:
                        s2 = m.fragility.states[1]
                        result.append(IngressPathway(
                            height=p.height_m, area=s2.area_m2, coeff=s2.Cd,
                            name=p.name,
                        ))
                    else:
                        result.append(IngressPathway(
                            height=p.height_m, area=p.area_m2, coeff=p.Cd,
                            name=p.name,
                        ))

        # Non-membrane paths
        for p in paths:
            if p.name in membrane_handled:
                continue
            if p.fragility is None:
                result.append(IngressPathway(
                    height=p.height_m, area=p.area_m2, coeff=p.Cd, name=p.name,
                ))
            else:
                h_path = max(0.0, h_ext - p.height_m)
                thresholds = sampled.path_thresholds.get(p.name, [])
                state = select_active_state(h_path, thresholds)
                area, cd = get_conductance(p, state)
                result.append(IngressPathway(
                    height=p.height_m, area=area, coeff=cd, name=p.name,
                ))

        return result

    return resolver


def make_basement_resolver(
    basement_fragility: Optional[BasementFragility],
    sampled: SampledThresholds,
    base_area: float,
    base_Cd: float,
    sill_elevation: float,
) -> Tuple[float, float]:
    """Return the (area_m2, Cd) to use for the basement connection this replicate.

    Because basement conductance is constant within a replicate (the threshold
    is fixed before the time loop), this returns a single (area, Cd) pair
    representing the *worst* state reached at peak external depth.

    For the time-loop we instead apply per-step basement state selection via
    make_basement_step_resolver.
    """
    if basement_fragility is None or sampled.basement_thresholds is None:
        return base_area, base_Cd
    # Return base values; actual per-step selection done by step resolver
    return base_area, base_Cd


def make_basement_step_resolver(
    basement_fragility: Optional[BasementFragility],
    sampled: SampledThresholds,
    base_area: float,
    base_Cd: float,
    sill_elevation: float,
):
    """Return a callable(h_ext) -> (area_m2, Cd) for the basement connection."""
    if basement_fragility is None or sampled.basement_thresholds is None:
        def _fixed(_h):
            return base_area, base_Cd
        return _fixed

    thresholds = sampled.basement_thresholds
    states_list = basement_fragility.fragility.states

    def _step(h_ext: float) -> Tuple[float, float]:
        h = max(0.0, h_ext - sill_elevation)
        active = select_active_state(h, thresholds)
        if active == 0:
            return base_area, base_Cd
        s = states_list[active - 1]
        return s.area_m2, s.Cd

    return _step


# ─────────────────────────────────────────────────────────────────────────────
# Monte Carlo runner
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReplicateRecord:
    replicate_id: int
    u_values: Dict[str, float]
    capacity_thresholds: Dict[str, List[float]]
    peak_h_in: float
    peak_h_basement: float
    peak_h_sump: float
    total_volume_in: float       # m³ ingressed to ground floor
    u_basement: Optional[float]
    basement_thresholds: Optional[List[float]]


@dataclass
class MonteCarloResult:
    replicates: List[ReplicateRecord]
    percentiles: Dict[str, Dict[str, float]]   # metric → {P10, P50, P90, …}
    state_frequencies: Dict[str, List[float]]  # element → [f_state0, f_state1, …]
    rank_correlations: Dict[str, float]        # element_u → Spearman ρ with peak_h_in


def run_fragility_montecarlo(
    building_factory,            # callable() → Building (fresh instance each replicate)
    paths: List[FragilePath],
    membranes: List[Membrane],
    basement_fragility: Optional[BasementFragility],
    external_times: list,
    external_levels: list,
    n_replicates: int,
    dt: float,
    external_vel_times: Optional[list] = None,
    external_velocities: Optional[list] = None,
    seed: Optional[int] = None,
    percentile_values: Tuple[int, ...] = (10, 25, 50, 75, 90),
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> MonteCarloResult:
    """Run the Monte Carlo ensemble.

    Args:
        building_factory: zero-arg callable returning a fresh Building instance.
            Called once per replicate so building state is never shared.
        paths: list of FragilePath (all ingress paths).
        membranes: list of Membrane (may be empty).
        basement_fragility: optional basement fragility definition.
        external_times / external_levels: hydrograph (seconds internally).
        n_replicates: number of Monte Carlo replicates.
        dt: simulation timestep (seconds).
        external_vel_times / external_velocities: optional velocity hydrograph.
        seed: random seed for reproducibility (None → non-deterministic).
        percentile_values: percentiles to report (default: 10, 25, 50, 75, 90).
        progress_callback: optional callable(replicate_idx, n_replicates).

    Returns:
        MonteCarloResult with per-replicate records and aggregated statistics.
    """
    from main import Building, IngressPathway, Simulation  # local import

    rng = np.random.default_rng(seed)
    records: List[ReplicateRecord] = []

    for r in range(n_replicates):
        if progress_callback:
            try:
                progress_callback(r, n_replicates)
            except Exception:
                pass

        sampled = sample_all_thresholds(paths, membranes, basement_fragility, rng)
        resolver = make_conductance_resolver(paths, membranes, sampled)

        building = building_factory()

        # Basement step resolver modifies building.basement_ingress conductance
        # per timestep via a wrapper.  We patch it below via a resolver wrapper.
        bsill = getattr(building.basement_ingress, 'height', 0.0) if building.basement_ingress else 0.0
        barea = getattr(building.basement_ingress, 'area', 0.0) if building.basement_ingress else 0.0
        bcd   = getattr(building.basement_ingress, 'coeff', 0.6) if building.basement_ingress else 0.6
        bstep = make_basement_step_resolver(
            basement_fragility, sampled, barea, bcd, bsill
        )

        # Wrap resolver to also update basement_ingress conductance each step
        bi = building.basement_ingress

        def _full_resolver(h_ext: float, _resolver=resolver, _bstep=bstep, _bi=bi) -> list:
            if _bi is not None:
                new_area, new_cd = _bstep(h_ext)
                _bi.area  = new_area
                _bi.coeff = new_cd
            return _resolver(h_ext)

        ingress_list = []  # resolver supplies all paths per-step
        sim = Simulation(
            building, ingress_list,
            external_times, external_levels,
            dt=dt,
            external_vel_times=external_vel_times,
            external_velocities=external_velocities,
            conductance_resolver=_full_resolver,
        )
        ret = sim.run()

        if len(ret) == 4:
            sim_times, sim_levels, sim_basement, sim_sump = ret
        elif len(ret) == 3:
            sim_times, sim_levels, sim_basement = ret
            sim_sump = [0.0] * len(sim_times)
        else:
            sim_times, sim_levels = ret
            sim_basement = [0.0] * len(sim_times)
            sim_sump = [0.0] * len(sim_times)

        peak_h_in       = max(sim_levels, default=0.0)
        peak_h_basement = max(sim_basement, default=0.0)
        peak_h_sump     = max(sim_sump, default=0.0)

        # Approximate total ingressed volume via trapezoidal integration of
        # indoor level × floor area  (change in stored volume = proxy for ingress)
        floor_area = building.floor_area
        vol_in = 0.0
        for i in range(1, len(sim_levels)):
            dh = sim_levels[i] - sim_levels[i - 1]
            if dh > 0:
                vol_in += dh * floor_area

        # Collect all thresholds for output
        cap_thresholds: Dict[str, List[float]] = {}
        cap_thresholds.update(sampled.path_thresholds)
        for gid, thr in sampled.membrane_thresholds.items():
            cap_thresholds[f'membrane:{gid}'] = thr

        records.append(ReplicateRecord(
            replicate_id=r,
            u_values=dict(sampled.u_values),
            capacity_thresholds=cap_thresholds,
            peak_h_in=peak_h_in,
            peak_h_basement=peak_h_basement,
            peak_h_sump=peak_h_sump,
            total_volume_in=vol_in,
            u_basement=sampled.u_values.get('basement'),
            basement_thresholds=sampled.basement_thresholds,
        ))

    if progress_callback:
        try:
            progress_callback(n_replicates, n_replicates)
        except Exception:
            pass

    return _aggregate(records, percentile_values, paths, membranes, external_levels)


def _aggregate(
    records: List[ReplicateRecord],
    percentile_values: Tuple[int, ...],
    paths: List[FragilePath],
    membranes: List[Membrane],
    external_levels: List[float],
) -> MonteCarloResult:
    """Compute percentiles, state frequencies, and rank correlations."""
    from scipy.stats import spearmanr

    peak_h_in       = np.array([r.peak_h_in       for r in records])
    peak_h_basement = np.array([r.peak_h_basement  for r in records])
    total_volume    = np.array([r.total_volume_in  for r in records])

    def _pct(arr):
        return {f'P{p}': float(np.percentile(arr, p)) for p in percentile_values}

    percentiles = {
        'peak_h_in':       _pct(peak_h_in),
        'peak_h_basement': _pct(peak_h_basement),
        'total_volume_in': _pct(total_volume),
    }

    # Rank correlations: u_element vs peak_h_in
    rank_corr: Dict[str, float] = {}
    # Collect all element names that have u values
    all_u_keys: set = set()
    for rec in records:
        all_u_keys.update(rec.u_values.keys())
    for key in all_u_keys:
        u_arr = np.array([rec.u_values.get(key, float('nan')) for rec in records])
        valid = ~np.isnan(u_arr)
        if valid.sum() >= 3:
            rho, _ = spearmanr(u_arr[valid], peak_h_in[valid])
            rank_corr[key] = float(rho)

    # State frequencies: for each probabilistic path / membrane, what fraction
    # of replicates reached state ≥ k?
    # An element reaches state k when the peak external head above its sill
    # equals or exceeds the sampled capacity threshold h*_k.  This is exactly
    # the condition used in select_active_state() during the time loop.
    max_h_ext = max(external_levels, default=0.0)

    state_freq: Dict[str, List[float]] = {}
    for p in paths:
        if p.fragility is None:
            continue
        # Max head above sill seen by this pathway during the event
        max_h_path = max(0.0, max_h_ext - p.height_m)
        n_states = len(p.fragility.states)
        freqs = []
        for k in range(n_states + 1):
            if k == 0:
                freqs.append(1.0)  # always in state ≥ 0
            else:
                exceeded = sum(
                    1 for rec in records
                    if p.name in rec.capacity_thresholds
                    and max_h_path >= rec.capacity_thresholds[p.name][k - 1]
                )
                freqs.append(exceeded / len(records))
        state_freq[p.name] = freqs

    for m in membranes:
        key = f'membrane:{m.group_id}'
        # Max head above membrane sill
        max_h_mem = max(0.0, max_h_ext - m.height_m)
        n_states = len(m.fragility.states)
        freqs = []
        for k in range(n_states + 1):
            if k == 0:
                freqs.append(1.0)
            else:
                exceeded = sum(
                    1 for rec in records
                    if key in rec.capacity_thresholds
                    and max_h_mem >= rec.capacity_thresholds[key][k - 1]
                )
                freqs.append(exceeded / len(records))
        state_freq[key] = freqs

    return MonteCarloResult(
        replicates=records,
        percentiles=percentiles,
        state_frequencies=state_freq,
        rank_correlations=rank_corr,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Output helpers
# ─────────────────────────────────────────────────────────────────────────────

def write_replicates_csv(result: MonteCarloResult, filepath: str) -> None:
    """Write per-replicate output to CSV."""
    if not result.replicates:
        return
    # Collect all u-value and threshold column names from first record
    all_u_keys = sorted(result.replicates[0].u_values.keys())
    all_thr_keys = sorted(result.replicates[0].capacity_thresholds.keys())

    with open(filepath, 'w', newline='') as fh:
        writer = csv.writer(fh)
        header = ['replicate_id']
        header += [f'u_{k}' for k in all_u_keys]
        for tk in all_thr_keys:
            n = len(result.replicates[0].capacity_thresholds.get(tk, []))
            for i in range(1, n + 1):
                header.append(f'h_star_{i}_{tk}')
        header += ['peak_h_in_m', 'peak_h_basement_m', 'peak_h_sump_m', 'total_volume_in_m3']
        writer.writerow(header)
        for rec in result.replicates:
            row = [rec.replicate_id]
            row += [rec.u_values.get(k, '') for k in all_u_keys]
            for tk in all_thr_keys:
                for v in rec.capacity_thresholds.get(tk, []):
                    row.append(v)
            row += [rec.peak_h_in, rec.peak_h_basement, rec.peak_h_sump, rec.total_volume_in]
            writer.writerow(row)


def write_summary_csv(result: MonteCarloResult, filepath: str) -> None:
    """Write percentile summary to CSV."""
    with open(filepath, 'w', newline='') as fh:
        writer = csv.writer(fh)
        all_pct_keys = sorted({k for d in result.percentiles.values() for k in d})
        writer.writerow(['metric'] + all_pct_keys)
        for metric, pcts in sorted(result.percentiles.items()):
            writer.writerow([metric] + [pcts.get(k, '') for k in all_pct_keys])


def write_state_freq_csv(result: MonteCarloResult, filepath: str) -> None:
    """Write state frequency table to CSV."""
    with open(filepath, 'w', newline='') as fh:
        writer = csv.writer(fh)
        max_states = max((len(v) for v in result.state_frequencies.values()), default=0)
        writer.writerow(['element'] + [f'state_{k}_freq' for k in range(max_states)])
        for elem, freqs in sorted(result.state_frequencies.items()):
            row = [elem] + freqs + [''] * (max_states - len(freqs))
            writer.writerow(row)
