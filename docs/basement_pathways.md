# Basement pathway handling

Two related shortcomings in the current basement-perimeter pathway model. Both are limitations rather than bugs, and both should be addressed together since the second depends on the first.

---

## 1. The basement-ingress file is collapsed to a single pathway

`batch.py` — argument handling for `--basement-ingress`

When a basement-ingress CSV is supplied, only the **first data row** is used. The file is parsed via `fragility.parse_pathway_file()` (which returns a list of `FragilePath`), but the wrapper takes `bsmt_paths[0]` and constructs a single `IngressPathway(source='outside', target='basement')`:

```python
# batch.py
basement_ingress = None
if args.basement_ingress:
    bsmt_paths = _frag.parse_pathway_file(args.basement_ingress)
    if bsmt_paths:
        bp = bsmt_paths[0]
        basement_ingress = IngressPathway(
            height=bp.height_m, area=bp.area_m2, coeff=bp.Cd,
            name=bp.name, source='outside', target='basement')
```

Any subsequent rows (e.g. `Basement wall leakage` alongside `Basement airbricks`) are silently dropped. The engine likewise stores a single `building.basement_ingress` slot.

**Consequence.** Multi-pathway basement perimeters (airbricks + wall seepage + light-well drains, etc.) cannot be modelled; users have to either lump them analytically into one equivalent orifice or split them across the bypass connection.

**Possible fix.** Mirror the ground-floor ingress flow: parse the basement CSV into a list of `FragilePath`, route the list through the fragility machinery (so per-row `group_id` and fragility states are honoured), and store all resulting pathways on the `Building` (e.g. `building.basement_ingress_list: List[IngressPathway]`). In `Simulation.run`, iterate over the list — same pattern already used for the ground-floor `ingress_list`.

---

## 2. Membranes do not protect basement pathways

`fragility.py` — `make_conductance_resolver`, `Membrane.representative_path_idx`
`engine.py` — `Simulation.run` (basement perimeter flow)

Membranes are tied to ground-floor pathways exclusively:

- `make_conductance_resolver` only emits `IngressPathway` objects with the default `target='ground'`. There is no mechanism for it to produce membrane-modulated `target='basement'` pathways.
- `Membrane.representative_path_idx` is computed against the ground-floor `paths` list only (`assign_representative_paths`).
- The engine reads basement perimeter flow directly from `building.basement_ingress`, **bypassing the resolver**, so even if the resolver produced a basement-targeted pathway it would never reach the simulation loop.

The only fragility hook on the basement perimeter is `make_basement_step_resolver`, driven by a separate `BasementFragility` object — independent of the membrane group concept.

**Consequence.** For UK property-flood-resilience archetypes where the perimeter membrane wraps the entire building (sealing both ground-floor pathways and basement airbricks/light wells), the model can only protect the ground floor. The basement remains exposed at base parameters, fills via airbricks once h_ext exceeds the airbrick sill, and — when the basement fills to its ceiling — spills excess water back up onto the ground floor through the engine's basement-overflow rule. The membrane scenario can therefore produce **higher** ground-floor peak depths than the unprotected baseline, which is non-physical for installations that include basement coverage.

**Possible fix (depends on §1).** Once basement pathways are stored as a list of `FragilePath`/`IngressPathway` rather than a single object, allow `Membrane.group_id` to match basement-targeted pathways and extend `make_conductance_resolver` to emit membrane-modulated basement pathways alongside the ground-floor ones. The engine loop then treats `target='basement'` pathways from the resolver identically to today's `building.basement_ingress`. No new fragility class is needed — the existing membrane mechanism applies once basement pathways live in the same data structure as the ground-floor ones.

---

## Workaround in the case-study scripts

Until both items are implemented, scenarios that include a perimeter membrane should point `--basement-ingress` at a separate CSV whose **first row** carries the membrane-intact (suppressed) airbrick parameters. This pins basement ingress to the protected steady state — an over-protection relative to the eventual fragility model (which would occasionally overtop at high external depths) but a much closer approximation to the physical scenario than the unprotected base file.

Example: `case studies/p2b_uk_midterrace_ingress_basement.csv` accompanies `case studies/p2b_membrane.csv` in the flood-water-ingress case study repo.
