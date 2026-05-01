"""Probabilistic fragility layer for water ingress modelling.

Public API
----------
Data model:   FragilityState, FragilityDefinition, FragilePath, Membrane,
              BasementFragility, SampledThresholds
Parsing:      parse_pathway_file, fragile_path_to_membrane,
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

    `target` selects which compartment the pathway flows into ('ground' or
    'basement'). The same `group_id` may be shared by ground-floor and basement
    pathways, in which case a single membrane fragility governs both — they
    overtop together for each replicate.
    """
    name: str
    height_m: float
    area_m2: float          # base-state orifice area
    Cd: float               # base-state discharge coefficient
    group_id: int = 0
    fragility: Optional[FragilityDefinition] = None
    target: str = 'ground'  # 'ground' or 'basement'


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
    from engine import IngressPathway  # engine has no upstream project imports

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
            source='outside', target=p.target,
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
                            name=p.name, source='outside', target=p.target,
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
                            name=p.name, source='outside', target=p.target,
                        ))
                    else:
                        result.append(IngressPathway(
                            height=p.height_m, area=p.area_m2, coeff=p.Cd,
                            name=p.name, source='outside', target=p.target,
                        ))

        # Non-membrane paths
        for p in paths:
            if p.name in membrane_handled:
                continue
            if p.fragility is None:
                result.append(IngressPathway(
                    height=p.height_m, area=p.area_m2, coeff=p.Cd, name=p.name,
                    source='outside', target=p.target,
                ))
            else:
                h_path = max(0.0, h_ext - p.height_m)
                thresholds = sampled.path_thresholds.get(p.name, [])
                state = select_active_state(h_path, thresholds)
                area, cd = get_conductance(p, state)
                result.append(IngressPathway(
                    height=p.height_m, area=area, coeff=cd, name=p.name,
                    source='outside', target=p.target,
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
    peak_h_ext: float            # peak exterior depth (same for all reps in fixed hydrograph)
    v_peak_ext: float            # peak exterior velocity (same for all reps in fixed hydrograph)
    u_basement: Optional[float]
    basement_thresholds: Optional[List[float]]
    h_in: List[float] = field(default_factory=list)
    h_basement: List[float] = field(default_factory=list)
    h_sump: List[float] = field(default_factory=list)
    sim_times: List[float] = field(default_factory=list)


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
    velocity_mode: str = 'zero',
    vel_a: float = 1.5,
    vel_b: float = 0.5,
    static_pathways: Optional[list] = None,
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
        external_vel_times / external_velocities: velocity time series (file mode only).
        velocity_mode: 'zero', 'power_law', or 'file'.
        vel_a / vel_b: power-law coefficients (used when velocity_mode='power_law').
        seed: random seed for reproducibility (None → non-deterministic).
        percentile_values: percentiles to report (default: 10, 25, 50, 75, 90).
        progress_callback: optional callable(replicate_idx, n_replicates).

    Returns:
        MonteCarloResult with per-replicate records and aggregated statistics.
    """
    from engine import Building, IngressPathway, Simulation  # engine has no upstream imports

    rng = np.random.default_rng(seed)
    records: List[ReplicateRecord] = []
    v_peak_ext_shared = max(external_velocities, default=0.0) if external_velocities else 0.0

    for r in range(n_replicates):
        if progress_callback:
            try:
                progress_callback(r, n_replicates)
            except Exception:
                pass

        sampled = sample_all_thresholds(paths, membranes, basement_fragility, rng)
        resolver = make_conductance_resolver(paths, membranes, sampled)

        building = building_factory()

        # Static (deterministic) pathways supplied by the caller — typically the
        # ground↔basement bypass connection.  Fragile and membrane-protected
        # paths flow through the resolver; both are merged in the engine.
        ingress_list = list(static_pathways or [])

        # Legacy basement-fragility hook: when supplied, mutate the building's
        # singleton basement_ingress per-step.  Modern callers should instead
        # express the basement perimeter as FragilePath rows with target='basement'
        # and let the membrane logic protect them.
        bi = building.basement_ingress
        if basement_fragility is not None and bi is not None:
            bsill = float(getattr(bi, 'height', 0.0))
            barea = float(getattr(bi, 'area', 0.0))
            bcd   = float(getattr(bi, 'coeff', 0.6))
            bstep = make_basement_step_resolver(
                basement_fragility, sampled, barea, bcd, bsill
            )

            def _full_resolver(h_ext: float, _resolver=resolver, _bstep=bstep, _bi=bi) -> list:
                new_area, new_cd = _bstep(h_ext)
                _bi.area  = new_area
                _bi.coeff = new_cd
                return _resolver(h_ext)

            active_resolver = _full_resolver
            # legacy bi flow path — keep singleton in ingress_list so engine sees it
            ingress_list.append(bi)
        else:
            active_resolver = resolver

        sim = Simulation(
            building, ingress_list,
            external_times, external_levels,
            dt=dt,
            external_vel_times=external_vel_times,
            external_velocities=external_velocities,
            conductance_resolver=active_resolver,
            velocity_mode=velocity_mode,
            vel_a=vel_a,
            vel_b=vel_b,
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
        peak_h_ext_val  = max(external_levels, default=0.0)

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
            peak_h_ext=peak_h_ext_val,
            v_peak_ext=v_peak_ext_shared,
            u_basement=sampled.u_values.get('basement'),
            basement_thresholds=sampled.basement_thresholds,
            h_in=list(sim_levels),
            h_basement=list(sim_basement),
            h_sump=list(sim_sump),
            sim_times=list(sim_times),
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
        header += ['peak_h_in_m', 'peak_h_basement_m', 'peak_h_sump_m',
                   'peak_h_ext_m', 'total_volume_in_m3']
        writer.writerow(header)
        for rec in result.replicates:
            row = [rec.replicate_id]
            row += [rec.u_values.get(k, '') for k in all_u_keys]
            for tk in all_thr_keys:
                for v in rec.capacity_thresholds.get(tk, []):
                    row.append(v)
            row += [rec.peak_h_in, rec.peak_h_basement, rec.peak_h_sump,
                    rec.peak_h_ext, rec.total_volume_in]
            writer.writerow(row)


def write_summary_csv(result: MonteCarloResult, filepath: str) -> None:
    """Write percentile summary to CSV (values formatted to 5 decimal places)."""
    with open(filepath, 'w', newline='') as fh:
        writer = csv.writer(fh)
        all_pct_keys = sorted({k for d in result.percentiles.values() for k in d})
        writer.writerow(['metric'] + all_pct_keys)
        for metric, pcts in sorted(result.percentiles.items()):
            row = [metric]
            for k in all_pct_keys:
                v = pcts.get(k)
                row.append(f'{v:.5f}' if v is not None else '')
            writer.writerow(row)


def write_state_freq_csv(result: MonteCarloResult, filepath: str) -> None:
    """Write per-state frequency table to CSV.

    Each state_k_freq column is the fraction of replicates in **exactly** state k
    (not cumulative exceedance).  Rows sum to 1.0 per element.
    """
    with open(filepath, 'w', newline='') as fh:
        writer = csv.writer(fh)
        max_states = max((len(v) for v in result.state_frequencies.values()), default=0)
        writer.writerow(['element'] + [f'state_{k}_freq' for k in range(max_states)])
        for elem, cum_freqs in sorted(result.state_frequencies.items()):
            # cum_freqs[k] = P(state >= k); convert to P(state == k)
            exact = []
            for k, cum_k in enumerate(cum_freqs):
                next_cum = cum_freqs[k + 1] if k + 1 < len(cum_freqs) else 0.0
                exact.append(round(max(0.0, cum_k - next_cum), 6))
            row = [elem] + exact + [''] * (max_states - len(exact))
            writer.writerow(row)


# ── unified pathway file parser ───────────────────────────────────────────────

def parse_pathway_file(filepath: str) -> List[FragilePath]:
    """Parse any pathway CSV (ingress, basement-opening, or membrane) into FragilePaths.

    Unified format (header row optional, always header-based):
        name, height_m, area_m2, Cd[, group_id[, state_name_N, median_m_N, beta_ln_N, area_m2_N, Cd_N, …]]

    - group_id defaults to 0 when the column is absent.
    - Rows without fragility state columns produce deterministic FragilePaths.
    - When used as a membrane file (via --membrane), the caller converts rows
      with group_id > 0 and fragility to Membrane objects via fragile_path_to_membrane().

    Skips comment lines (#) and blank lines.
    """
    paths: List[FragilePath] = []
    header_seen = False
    col_name = col_height = col_area = col_cd = col_group = None

    with open(filepath, newline='') as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]

            # Detect header row (first non-comment non-blank row that has text in col 0)
            if not header_seen:
                try:
                    float(parts[0])
                    # First col is numeric → positional legacy format (not supported)
                    raise ValueError(
                        f"{filepath}:{lineno}: positional ingress format (height,area,coeff,name) "
                        "is no longer supported. Use the header-based unified pathway format: "
                        "name, height_m, area_m2, Cd[, group_id[, state columns]]"
                    )
                except ValueError as exc:
                    if 'positional' in str(exc):
                        raise
                    # Non-numeric first col → treat as header
                    lower = [p.lower() for p in parts]
                    col_name   = next((i for i, h in enumerate(lower) if 'name' in h), 0)
                    col_height = next((i for i, h in enumerate(lower) if 'height' in h), 1)
                    col_area   = next((i for i, h in enumerate(lower) if 'area' in h and 'state' not in lower[max(0,i-1)]), 2)
                    col_cd     = next((i for i, h in enumerate(lower) if h in ('cd', 'coeff', 'discharge')), 3)
                    col_group  = next((i for i, h in enumerate(lower) if 'group' in h), None)
                    header_seen = True
                    continue

            # Data row
            if len(parts) < 4:
                warnings.warn(f"{filepath}:{lineno}: row has fewer than 4 columns, skipped", stacklevel=2)
                continue
            try:
                name   = parts[col_name]
                height = float(parts[col_height])
                area   = float(parts[col_area])
                cd     = float(parts[col_cd])
                gid    = int(parts[col_group]) if col_group is not None and col_group < len(parts) else 0
            except (ValueError, IndexError) as exc:
                raise ValueError(f"{filepath}:{lineno}: bad base columns — {exc}") from exc

            frag_start = (col_group + 1) if col_group is not None else 4
            fragility = _parse_fragility_states_from_parts(parts, frag_start, name)
            paths.append(FragilePath(name, height, area, cd, gid, fragility))

    if not paths:
        raise ValueError(f"No pathway rows found in {filepath}")
    return paths


def fragile_path_to_membrane(fp: FragilePath) -> 'Membrane':
    """Convert a FragilePath with group_id > 0 and fragility to a Membrane object."""
    if fp.group_id == 0:
        raise ValueError(f"Cannot convert ungrouped path '{fp.name}' to Membrane (group_id must be > 0)")
    if fp.fragility is None:
        raise ValueError(f"Cannot convert path '{fp.name}' to Membrane: no fragility states defined")
    return Membrane(
        group_id=fp.group_id,
        height_m=fp.height_m,
        area_m2=fp.area_m2,
        Cd=fp.Cd,
        fragility=fp.fragility,
    )


# ── high-level public run() ───────────────────────────────────────────────────

def run(config, hydro, paths: List[FragilePath],
        membranes: Optional[List['Membrane']] = None,
        basement_frag: Optional['BasementFragility'] = None,
        basement_pathway=None) -> 'MonteCarloResult':
    """Run the Monte Carlo ensemble using SimConfig + Hydrograph.

    This is the high-level fragility entry point.  Internally it wraps
    run_fragility_montecarlo() using a building_factory derived from config.

    Parameters
    ----------
    config           : engine.SimConfig
    hydro            : engine.Hydrograph (times in seconds)
    paths            : List[FragilePath] — all ingress paths
    membranes        : List[Membrane] or None
    basement_frag    : BasementFragility or None
    basement_pathway : engine.IngressPathway for exterior→basement perimeter, or None
    """
    import copy as _copy

    def _building_factory():
        from engine import Building
        b = Building(floor_area=config.floor_area)
        if config.basement_area > 0.0:
            b.basement_area = config.basement_area
            b.z_basement = config.basement_floor_elevation
            b.basement_ceiling_elevation = config.basement_ceiling_elevation
        if basement_pathway is not None and config.basement_area > 0.0:
            b.basement_ingress = basement_pathway
        if config.sumppump is not None and config.basement_area > 0.0:
            b.sump_pump = _copy.deepcopy(config.sumppump)
        return b

    return run_fragility_montecarlo(
        building_factory=_building_factory,
        paths=paths,
        membranes=membranes or [],
        basement_fragility=basement_frag,
        external_times=hydro.times,
        external_levels=hydro.levels,
        n_replicates=config.n_replicates,
        dt=config.dt,
        external_vel_times=hydro.vel_times,
        external_velocities=hydro.velocities,
        seed=config.random_seed,
        percentile_values=config.output_percentiles,
        velocity_mode=config.velocity_mode,
        vel_a=config.velocity_power_law_a,
        vel_b=config.velocity_power_law_b,
    )
