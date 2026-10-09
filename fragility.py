"""Probabilistic fragility layer for water ingress modelling.

Public API
----------
Data model:   FragilityState, FragilityDefinition, FragilePath, Membrane,
              SampledThresholds
Parsing:      parse_pathway_text, parse_pathway_file, fragile_path_to_membrane
Assembly:     assemble_pathways, load_pathways
Validation:   validate_fragility_inputs, assign_representative_paths
Sampling:     FragilityDefinition.sample_thresholds, sample_all_thresholds
State logic:  select_active_state, get_conductance
Resolver:     make_conductance_resolver
Runner:       run_replicate, run, MonteCarloResult

Every simulation (deterministic or Monte Carlo) is one replicate: thresholds
are sampled, a conductance resolver is built, and engine.run() does the rest.
"""

from __future__ import annotations

import csv
import math
import warnings
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import norm as _norm

import engine
from engine import IngressPathway


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

    `reversible` is mandatory for fragile elements (fragility is not None):
      True  — state follows the instantaneous head (overtopping / bathtub measures).
      False — state latches to the worst reached so far; never decreases within
              an event (failure-type: door seals, airbrick covers, pipe seals).
    Deterministic paths (fragility=None) leave reversible=None.
    """
    name: str
    height_m: float
    area_m2: float          # base-state orifice area
    Cd: float               # base-state discharge coefficient
    group_id: int = 0
    fragility: Optional[FragilityDefinition] = None
    target: str = 'ground'  # 'ground' or 'basement'
    reversible: Optional[bool] = None  # required when fragility is not None


@dataclass
class Membrane:
    """Perimeter flood protection element shielding a group of ingress paths.

    `reversible` is mandatory (no default):
      True  — state follows the instantaneous head (skirts, bunds, barriers).
      False — state latches to the worst reached so far (irreversible failure).
    """
    group_id: int
    height_m: float
    area_m2: float          # base-state lumped leakage area
    Cd: float
    fragility: FragilityDefinition   # always present; governs overtopping
    reversible: bool                 # required — see class docstring
    representative_path_idx: int = -1   # set by assign_representative_paths




@dataclass
class SampledThresholds:
    """Per-replicate capacity thresholds drawn before the time loop."""
    # path name  → [h*_1, …, h*_N]
    path_thresholds: Dict[str, List[float]] = field(default_factory=dict)
    # group_id   → [h*_1, …, h*_N]
    membrane_thresholds: Dict[int, List[float]] = field(default_factory=dict)
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



# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_fragility_inputs(paths: List[FragilePath]) -> None:
    """Raise ValueError on any specification error.

    Checks:
    1. Fragility–membrane conflict: group_id != 0 paths must not have fragility.
    2. Monotonic medians for every probabilistic path.
    3. Missing reversible flag on fragile elements.
    4. (Membrane monotonicity is checked at parse time.)
    """
    for p in paths:
        if p.group_id != 0 and p.fragility is not None:
            raise ValueError(
                f"Path '{p.name}' has group_id={p.group_id} (membrane-protected) "
                "but also defines fragility columns — a membrane-protected path "
                "takes its fragility from the membrane"
            )
        if p.fragility is not None:
            p.fragility.validate(p.name)
            if p.reversible is None:
                raise ValueError(
                    f"Fragile path '{p.name}' is missing the required 'reversible' flag. "
                    "Set reversible=True for overtopping/membrane elements, "
                    "reversible=False for failure-type seals/covers."
                )


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

def sample_all_thresholds(
    paths: List[FragilePath],
    membranes: List[Membrane],
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
    """
    # Build fast lookup: group_id -> list of (path_index, FragilePath)
    group_map: Dict[int, List[Tuple[int, FragilePath]]] = {}
    for i, p in enumerate(paths):
        if p.group_id != 0:
            group_map.setdefault(p.group_id, []).append((i, p))

    # Pre-build suppressed IngressPathway stubs (10⁻⁹ m²) for group members
    suppressed: Dict[str, IngressPathway] = {
        p.name: IngressPathway(
            height=p.height_m, area=1e-9, coeff=0.6, name=p.name,
            source='outside', target=p.target,
        )
        for p in paths if p.group_id != 0
    }

    # Per-replicate latch memory — accumulates the highest degraded state reached
    # so far for irreversible elements.  The resolver closure captures these dicts;
    # they are fresh for each call to make_conductance_resolver (i.e. each replicate), so the latch resets
    # correctly between replicates without touching the RNG state or seeds.
    path_attained: Dict[str, int] = {}   # path.name  → highest state index so far
    mem_attained:  Dict[int, int]  = {}  # group_id   → highest membrane state so far

    def resolver(h_ext: float) -> list:
        result: list = []
        # Track which paths have already been handled by membrane logic
        membrane_handled: set = set()

        for m in membranes:
            gid = m.group_id
            h_mem = max(0.0, h_ext - m.height_m)
            mem_thresholds = sampled.membrane_thresholds.get(gid, [])
            mem_state = select_active_state(h_mem, mem_thresholds)

            # Irreversible membrane: latch to highest state reached so far
            if not m.reversible:
                mem_state = max(mem_state, mem_attained.get(gid, 0))
                mem_attained[gid] = mem_state

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
                    # when state == 2 (docs/fragility.md, membrane states).
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

                # Irreversible path: latch to highest state reached so far
                if not p.reversible:
                    state = max(state, path_attained.get(p.name, 0))
                    path_attained[p.name] = state

                area, cd = get_conductance(p, state)
                result.append(IngressPathway(
                    height=p.height_m, area=area, coeff=cd, name=p.name,
                    source='outside', target=p.target,
                ))

        return result

    return resolver




# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReplicateRecord:
    replicate_id: int
    u_values: Dict[str, float]
    capacity_thresholds: Dict[str, List[float]]
    result: engine.SimResult


@dataclass
class MonteCarloResult:
    replicates: List[ReplicateRecord]
    percentiles: Dict[str, Dict[str, float]]   # metric → {P10, P50, P90, …}
    state_frequencies: Dict[str, List[float]]  # element → [f_state0, f_state1, …]
    rank_correlations: Dict[str, float]        # element_u → Spearman ρ with peak_h_in


def run_replicate(config, hydro, paths: List[FragilePath],
                  membranes: List[Membrane], rng: np.random.Generator,
                  progress_callback=None) -> Tuple[engine.SimResult, SampledThresholds]:
    """Sample one set of capacity thresholds and run the simulation.

    Deterministic paths (fragility=None, no membrane) consume no random draws,
    so a model without fragile elements gives the same result for any rng.
    """
    sampled = sample_all_thresholds(paths, membranes, rng)
    result = engine.run(
        config, hydro,
        conductance_resolver=make_conductance_resolver(paths, membranes, sampled),
        progress_callback=progress_callback,
    )
    return result, sampled


def run(config, hydro, paths: List[FragilePath],
        membranes: Optional[List[Membrane]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        ) -> MonteCarloResult:
    """Run config.n_replicates replicates (seeded by config.random_seed).

    Args:
        config: engine.SimConfig.
        hydro: engine.Hydrograph (times in seconds).
        paths: all ingress paths (ground floor and basement).
        membranes: membranes protecting groups of paths (may be empty).
        progress_callback: optional callable(replicate_idx, n_replicates).
    """
    membranes = membranes or []
    rng = np.random.default_rng(config.random_seed)
    n_replicates = config.n_replicates
    records: List[ReplicateRecord] = []

    for r in range(n_replicates):
        if progress_callback:
            try:
                progress_callback(r, n_replicates)
            except Exception:
                pass

        result, sampled = run_replicate(config, hydro, paths, membranes, rng)

        cap_thresholds: Dict[str, List[float]] = {}
        cap_thresholds.update(sampled.path_thresholds)
        for gid, thr in sampled.membrane_thresholds.items():
            cap_thresholds[f'membrane:{gid}'] = thr

        records.append(ReplicateRecord(
            replicate_id=r,
            u_values=dict(sampled.u_values),
            capacity_thresholds=cap_thresholds,
            result=result,
        ))

    if progress_callback:
        try:
            progress_callback(n_replicates, n_replicates)
        except Exception:
            pass

    return _aggregate(records, config.output_percentiles, paths, membranes)


def _aggregate(
    records: List[ReplicateRecord],
    percentile_values: Tuple[int, ...],
    paths: List[FragilePath],
    membranes: List[Membrane],
) -> MonteCarloResult:
    """Compute percentiles, state frequencies, and rank correlations."""
    from scipy.stats import spearmanr

    peak_h_in       = np.array([r.result.peak_h_in       for r in records])
    peak_h_basement = np.array([r.result.peak_h_basement for r in records])
    total_volume    = np.array([r.result.total_volume_in for r in records])

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
    max_h_ext = max((r.result.peak_h_ext for r in records), default=0.0)

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
            res = rec.result
            row += [res.peak_h_in, res.peak_h_basement, res.peak_h_sump,
                    res.peak_h_ext, res.total_volume_in]
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

def parse_pathway_text(text: str, source: str = '<text>') -> List[FragilePath]:
    """Parse pathway CSV text (ingress, basement-opening, or membrane) into FragilePaths.

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
    col_name = col_height = col_area = col_cd = col_group = col_reversible = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
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
                    f"{source}:{lineno}: positional ingress format (height,area,coeff,name) "
                    "is no longer supported. Use the header-based unified pathway format: "
                    "name, height_m, area_m2, Cd[, group_id[, reversible[, state columns]]]"
                )
            except ValueError as exc:
                if 'positional' in str(exc):
                    raise
                # Non-numeric first col → treat as header
                lower = [p.lower() for p in parts]
                col_name       = next((i for i, h in enumerate(lower) if 'name' in h), 0)
                col_height     = next((i for i, h in enumerate(lower) if 'height' in h), 1)
                col_area       = next((i for i, h in enumerate(lower) if 'area' in h and 'state' not in lower[max(0,i-1)]), 2)
                col_cd         = next((i for i, h in enumerate(lower) if h in ('cd', 'coeff', 'discharge')), 3)
                col_group      = next((i for i, h in enumerate(lower) if 'group' in h), None)
                col_reversible = next((i for i, h in enumerate(lower) if 'reversible' in h), None)
                header_seen = True
                continue

        # Data row
        if len(parts) < 4:
            warnings.warn(f"{source}:{lineno}: row has fewer than 4 columns, skipped", stacklevel=2)
            continue
        try:
            name   = parts[col_name]
            height = float(parts[col_height])
            area   = float(parts[col_area])
            cd     = float(parts[col_cd])
            gid    = int(parts[col_group]) if col_group is not None and col_group < len(parts) else 0
        except (ValueError, IndexError) as exc:
            raise ValueError(f"{source}:{lineno}: bad base columns — {exc}") from exc

        # Parse reversible flag (optional column; mandatory for fragile rows)
        reversible: Optional[bool] = None
        if col_reversible is not None and col_reversible < len(parts):
            val = parts[col_reversible].strip().lower()
            if val in ('1', 'true', 'yes'):
                reversible = True
            elif val in ('0', 'false', 'no'):
                reversible = False
            elif val != '':
                raise ValueError(
                    f"{source}:{lineno}: invalid value for 'reversible' on "
                    f"'{name}': {parts[col_reversible]!r}. Use 1/true or 0/false."
                )

        # Fragility states start after all known meta columns
        meta_cols = [c for c in (col_name, col_height, col_area, col_cd,
                                 col_group, col_reversible) if c is not None]
        frag_start = max(meta_cols) + 1
        fragility = _parse_fragility_states_from_parts(parts, frag_start, name)

        # Mandate reversible for fragile elements at parse time
        if fragility is not None and reversible is None:
            raise ValueError(
                f"{source}:{lineno}: fragile element '{name}' is missing the "
                "required 'reversible' column. Add a 'reversible' column with "
                "value 1 (overtopping/reversible) or 0 (failure-type/irreversible)."
            )

        paths.append(FragilePath(name, height, area, cd, gid, fragility,
                                 reversible=reversible))

    if not paths:
        raise ValueError(f"No pathway rows found in {source}")
    return paths


def parse_pathway_file(filepath: str) -> List[FragilePath]:
    """Parse a pathway CSV file into FragilePaths (see parse_pathway_text)."""
    with open(filepath, newline='') as fh:
        return parse_pathway_text(fh.read(), source=filepath)


def fragile_path_to_membrane(fp: FragilePath) -> 'Membrane':
    """Convert a FragilePath with group_id > 0 and fragility to a Membrane object."""
    if fp.group_id == 0:
        raise ValueError(f"Cannot convert ungrouped path '{fp.name}' to Membrane (group_id must be > 0)")
    if fp.fragility is None:
        raise ValueError(f"Cannot convert path '{fp.name}' to Membrane: no fragility states defined")
    if fp.reversible is None:
        raise ValueError(
            f"Cannot convert path '{fp.name}' to Membrane: 'reversible' flag is missing. "
            "Add reversible=1 (skirts/barriers) or reversible=0 (irreversible) to the file."
        )
    return Membrane(
        group_id=fp.group_id,
        height_m=fp.height_m,
        area_m2=fp.area_m2,
        Cd=fp.Cd,
        fragility=fp.fragility,
        reversible=fp.reversible,
    )



# ── pathway assembly ──────────────────────────────────────────────────────────

def assemble_pathways(
    ingress: List[FragilePath] = (),
    basement: List[FragilePath] = (),
    membrane_rows: List[FragilePath] = (),
) -> Tuple[List[FragilePath], List[Membrane]]:
    """Combine parsed rows into the (paths, membranes) model input.

    `basement` rows are exterior→basement pathways (target='basement');
    `membrane_rows` with group_id > 0 and fragility become Membranes.
    Validates the result and assigns each membrane its representative path.
    """
    paths = list(ingress)
    for p in basement:
        p.target = 'basement'
        paths.append(p)
    membranes = [fragile_path_to_membrane(fp) for fp in membrane_rows
                 if fp.group_id > 0 and fp.fragility is not None]
    validate_fragility_inputs(paths)
    assign_representative_paths(paths, membranes)
    return paths, membranes


def load_pathways(
    ingress_file: Optional[str] = None,
    basement_file: Optional[str] = None,
    membrane_file: Optional[str] = None,
) -> Tuple[List[FragilePath], List[Membrane]]:
    """Parse the pathway CSV files and assemble them (see assemble_pathways)."""
    def _rows(path):
        return parse_pathway_file(path) if path else []
    return assemble_pathways(_rows(ingress_file), _rows(basement_file),
                             _rows(membrane_file))
