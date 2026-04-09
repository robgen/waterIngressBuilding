# Sump and Pump Extension for the Water Ingress Model

## Purpose

This document specifies the governing equations, assumptions, scope limits, implementation choices, and coding requirements for extending the existing water ingress model with a **separate sump chamber** and a **head-dependent pump system**.

The current codebase already solves the hydraulic problem for:

- main building chamber
- basement chamber

The new functionality must add:

- a **sump chamber**
- a **pump** extracting water from the sump
- **overflow from sump to basement**
- **lumped exterior perimeter inflow represented in the sump balance**
- a structure ready for future Monte Carlo support of **pump fragility / availability**

---

## 1. Hydraulic architecture to implement

The model must contain three storage chambers:

1. **Main building chamber**
2. **Basement chamber**
3. **Sump chamber**

### Routing logic

The intended routing is:

- exterior water entering around the basement perimeter is routed **directly to the sump chamber**
- if the sump exceeds its overflow crest, water spills from the **sump chamber to the basement chamber**
- water flowing from the **main building to the basement** goes to the **basement chamber**
- the pump extracts water **only from the sump chamber**
- the non-return valve is assumed **ideal**, so there is **no backflow** through the pump discharge line

This means the sump acts as a lumped hydraulic representation of a perimeter interception system around the basement.

---

## 2. State variables

Use the following hydraulic state variables:

- \( h_b(t) \): water depth in the **main building chamber**
- \( h_{bs}(t) \): water depth in the **basement chamber**
- \( h_s(t) \): water depth in the **sump chamber**

Use these geometric functions:

- \( A_b(h_b) \): horizontal wetted area of the main building chamber
- \( A_{bs}(h_{bs}) \): horizontal wetted area of the basement chamber
- \( A_s \): horizontal area of the sump chamber

### Sump geometry

The sump is assumed to be a **simple vertical chamber**, therefore:

\[
V_s(t) = A_s \, h_s(t)
\]

with constant \( A_s \).

---

## 3. Flow terms

Use the following flow variables:

- \( Q_{ext,b}(t) \): direct exterior inflow to the main building chamber
- \( Q_{b \to bs}(t) \): flow from main building chamber to basement chamber
- \( Q_{ext,s}(t) \): direct exterior inflow to the sump chamber
- \( Q_{s \to bs}(t) \): overflow from sump chamber to basement chamber
- \( Q_p(t) \): pump discharge from the sump chamber

No backflow term is needed because the non-return valve is assumed ideal.

---

## 4. Governing equations

## 4.1 Main building chamber

\[
A_b(h_b)\,\frac{dh_b}{dt} = Q_{ext,b}(t) - Q_{b \to bs}(t)
\]

This equation is unchanged in structure from the existing model, except that the new sump system does **not** directly interact with the main building chamber.

---

## 4.2 Basement chamber

\[
A_{bs}(h_{bs})\,\frac{dh_{bs}}{dt} = Q_{b \to bs}(t) + Q_{s \to bs}(t)
\]

This means basement water increases through:

- inflow descending from the building
- overflow arriving from the sump

At this stage, **do not** include direct exterior-to-basement inflow, unless such a pathway already exists in the current code and is intentionally retained.

---

## 4.3 Sump chamber

\[
A_s\,\frac{dh_s}{dt} = Q_{ext,s}(t) - Q_p(t) - Q_{s \to bs}(t)
\]

This is the new balance equation to add.

The sump receives direct exterior inflow, loses water through the pump, and may overflow to the basement.

---

## 5. Sump overflow model

Define:

- \( z_{ov} \): sump overflow crest elevation, measured from sump base

Then model sump overflow into the basement as:

\[
Q_{s \to bs}(t) =
\begin{cases}
0, & h_s \le z_{ov} \\
C_{ov}\,\bigl(h_s - z_{ov}\bigr)^{m_{ov}}, & h_s > z_{ov}
\end{cases}
\]

where:

- \( C_{ov} \): effective overflow coefficient
- \( m_{ov} \): overflow exponent

### Recommended default

Use:

\[
m_{ov} = \frac{3}{2}
\]

if overflow is represented as a weir-like discharge.

A simpler fallback is:

\[
m_{ov} = \frac{1}{2}
\]

if the rest of the codebase already uses square-root flow laws and consistency is preferred over physical refinement.

### Recommendation for implementation

Use the weir-like form first if it does not complicate the existing code structure.

---

## 6. Pump model

## 6.1 Pump control logic

Define:

- \( h_{on} \): pump activation level
- \( h_{off} \): pump deactivation level
- \( u(t) \in \{0,1\} \): pump on/off state
- \( \eta_p \): pump availability factor

For now, set:

\[
\eta_p = 1
\]

This is intentionally retained in the equations so that, later, a fragility model can switch pump availability on or off in each Monte Carlo realisation.

### Hysteretic control rule

\[
u(t) =
\begin{cases}
1, & h_s \ge h_{on} \\
0, & h_s \le h_{off} \\
\text{previous state}, & h_{off} < h_s < h_{on}
\end{cases}
\]

This hysteresis is required to avoid unrealistic rapid switching.

---

## 6.2 Head-dependent pump discharge

The pump must be modelled with a **proper head-dependent discharge law**, not with constant flow.

### Pump head curve

\[
H_{pump}(Q) = H_{shut} - k_{pump}\,Q^2
\]

where:

- \( H_{shut} \): shut-off head of the pump
- \( k_{pump} \): pump-curve coefficient

### System head curve

\[
H_{system}(Q,t) = H_{lift}(t) + k_{pipe}\,Q^2
\]

where:

- \( H_{lift}(t) \): static and downstream-controlled head
- \( k_{pipe} \): coefficient representing pipe friction and minor losses

### Operating point equation

The pump operating point is obtained by equating pump head and system head:

\[
H_{shut} - k_{pump}\,Q_p^2 = H_{lift}(t) + k_{pipe}\,Q_p^2
\]

which gives:

\[
Q_p^{*}(t) =
\begin{cases}
\sqrt{\dfrac{H_{shut} - H_{lift}(t)}{k_{pump} + k_{pipe}}}, & H_{shut} > H_{lift}(t) \\
0, & H_{shut} \le H_{lift}(t)
\end{cases}
\]

The effective pumped discharge is then:

\[
Q_p(t) = u(t)\,\eta_p\,Q_p^{*}(t)
\]

Since \( \eta_p = 1 \) for now:

\[
Q_p(t) = u(t)\,Q_p^{*}(t)
\]

---

## 7. Definition of lift head

The implementation needs a quantity \( H_{lift}(t) \). At minimum, define it as:

\[
H_{lift}(t) = z_{out}(t) - z_{pump}
\]

where:

- \( z_{pump} \): pump datum elevation
- \( z_{out}(t) \): hydraulic head at the discharge point

### Simplest acceptable implementation

If the discharge condition is fixed:

\[
H_{lift}(t) = H_{lift,0}
\]

constant in time.

### Better implementation

If the outfall is exposed to floodwater or a time-varying downstream hydraulic condition, then \( z_{out}(t) \) should vary in time.

### Scope decision

For the first implementation:

- allow the code to accept either a constant \( H_{lift} \), or
- a time-dependent function / time series if already supported by the codebase architecture

The algebraic pump law should remain the same in both cases.

---

## 8. What to model

The agent introducing this functionality should model the following items.

### 8.1 New hydraulic state

Add a new state variable for sump depth:

- \( h_s(t) \)

### 8.2 New geometry definition

Add parameters for:

- \( A_s \): sump chamber area
- \( z_{ov} \): overflow crest elevation
- \( h_{on} \): pump start level
- \( h_{off} \): pump stop level

### 8.3 New inflow pathway

Add a lumped hydraulic pathway representing perimeter inflow intercepted by the
sump:

- exterior \(\rightarrow\) sump

represented through \( Q_{ext,s}(t) \)

In the public interface, this should not require users to author explicit routed
ingress rows. Instead:

- the regular ingress file remains exterior \(\rightarrow\) main-building only
- the exterior perimeter inflow to the basement system is provided through
  dedicated basement arguments
- when a sump is enabled, that lumped perimeter inflow is redirected internally
  to the sump balance and becomes \( Q_{ext,s}(t) \)

This must remain separate from the exterior \(\rightarrow\) building pathways and
from the building \(\rightarrow\) basement bypass.

### 8.4 New overflow pathway

Add a pathway:

- sump \(\rightarrow\) basement

represented through \( Q_{s \to bs}(t) \)

### 8.5 New pump object or module

Add a pump calculation that evaluates:

1. current control state \( u(t) \)
2. current lift head \( H_{lift}(t) \)
3. current head-dependent discharge \( Q_p(t) \)

### 8.6 Availability factor placeholder

Keep \( \eta_p \) in the code structure, even though for now it is fixed to 1.

This is necessary so that later a fragility model can set:

- \( \eta_p = 1 \) if pump survives and is active
- \( \eta_p = 0 \) if pump fails or is unavailable

without rewriting the hydraulic solver structure.

---

## 9. What not to model in this implementation

Do **not** model the following in this first extension.

### 9.1 Pump backflow

Do not include reverse flow through the discharge line.

Reason: the non-return valve is assumed ideal.

### 9.2 Pump degradation or clogging

Do not model:

- debris blockage
- sediment effects
- mechanical wear
- thermal failure
- reduced efficiency with time

Reason: these belong to a later pump fragility / reliability extension.

### 9.3 Detailed basement perimeter hydraulics

Do not explicitly model:

- distributed perimeter drains
- local trench geometry
- separate collector channels around the basement walls
- travel time around the perimeter

Reason: the sump chamber already acts as a lumped perimeter interception chamber.

### 9.4 Detailed internal free-surface flow within the basement

Do not model:

- spatially varying ponding inside the basement
- local floor gradients inside the basement
- wave effects
- momentum conservation within chambers

Reason: this model is a lumped storage model, not a spatial CFD model.

### 9.5 Pump transient mechanics

Do not model:

- motor spin-up
- pump inertia
- pressure surges
- water hammer
- transient cavitation

Reason: unnecessary for the intended low-order ingress model.

### 9.6 Direct exterior-to-basement inflow via the new sump feature

Do not add an additional direct exterior \(\rightarrow\) basement flow linked to the new sump feature.

Reason: all perimeter-related exterior inflow intended in this extension is assumed to go first to the sump.

---

## 10. Assumptions to lock in

The following assumptions must be documented and retained in the implementation.

### 10.1 Chamber idealisation

- main building, basement, and sump are each treated as lumped storage chambers
- each chamber is described by a single water depth variable

### 10.2 Sump geometry

- the sump is a simple vertical chamber with constant plan area \( A_s \)

### 10.3 Routing assumption

- exterior water around the basement perimeter is intercepted directly by the sump chamber

### 10.4 Overflow assumption

- sump overflow spills into the basement chamber only

### 10.5 Building-to-basement routing

- water moving from the building to the basement enters the basement chamber, not the sump chamber

### 10.6 Pump location

- the pump is located in the sump chamber associated with the basement system

### 10.7 Valve assumption

- the non-return valve is ideal, so reverse flow is impossible

### 10.8 Pump availability

- pump availability factor exists in the equations but is fixed to one for now:

\[
\eta_p = 1
\]

### 10.9 Drainage-to-sump efficiency

- exterior perimeter drainage to the sump is assumed perfect within the lumped model
- therefore no separate drainage conveyance losses or delays are modelled

### 10.10 Flow law level

- the model remains low-order and lumped
- no momentum equation or distributed pipe network solution is required

---

## 11. Numerical implementation notes

### 11.1 Computational cost

The proper pump model adds only a very small computational burden relative to a constant-flow pump.

The added cost consists of:

- one extra algebraic evaluation for \( H_{lift}(t) \)
- one square-root evaluation for \( Q_p^{*}(t) \)
- the existing on/off logic

This is negligible compared with the ODE integration itself.

### 11.2 Solver behaviour

The main numerical non-smoothness comes from:

- pump on/off switching
- onset of sump overflow

These threshold behaviours already justify careful handling of time stepping.

### 11.3 Recommended implementation style

Use a time-stepping loop or ODE callback that, at each evaluation:

1. computes all external inflows
2. computes \( Q_{b \to bs}(t) \)
3. updates pump control state \( u(t) \)
4. computes \( Q_p(t) \)
5. computes \( Q_{s \to bs}(t) \)
6. assembles the three chamber derivatives

### 11.4 Guard conditions

Guard against the following:

- negative argument inside the square root for \( Q_p^{*}(t) \)
- negative overflow when \( h_s \le z_{ov} \)
- negative chamber depths due to numerical overshoot

### 11.5 State handling for hysteresis

The control variable \( u(t) \) depends on its previous state, so it should be stored explicitly.

The implementation must not recompute it statelessly using only the current depth.

### 11.6 Timestep note for first release

The first implementation may continue using a single global solver timestep for the building, basement, sump, and pump.

This means threshold-sensitive behaviours such as:

- pump on/off switching
- onset of sump overflow

may show timestep sensitivity when `dt` is coarse.

Document this clearly for users and recommend smaller `dt` values when threshold timing matters.

Internal hydraulic substeps or adaptive stepping may be added later as a future refinement, but they are not required for the first implementation.

---

## 12. Recommended software structure

The exact class and file names depend on the codebase, but the agent should introduce the feature with a structure similar to this.

### 12.1 New data / parameter group

Create a sump-pump parameter group containing at least:

- `sump_area`
- `sump_overflow_level`
- `pump_on_level`
- `pump_off_level`
- `pump_shutoff_head`
- `pump_curve_coefficient`
- `pipe_loss_coefficient`
- `sump_base_elevation` or equivalent downstream-head definition
- `pump_availability_factor`

### 12.2 New state variable

Add:

- `h_sump`

to the system state vector.

### 12.3 New helper functions

Implement small, testable functions for:

- `compute_sump_overflow(h_sump, overflow_level, overflow_coefficient, overflow_exponent)`
- `compute_pump_switch_state(h_sump, h_on, h_off, previous_state)`
- `compute_pump_flow(pump_on, availability, H_shut, H_lift, k_pump, k_pipe)`

### 12.4 Separation of concerns

Do not bury the pump logic inside a large monolithic derivative function if avoidable.

Keep:

- chamber continuity equations
- overflow logic
- pump control logic
- pump discharge logic

as separate functions or methods.

This will matter later when adding fragility-driven availability.

---

## 13. Calibration and inputs

The implementation requires the following user inputs or defaults.

### Public input structure

The recommended public input structure is:

- ingress file: exterior-to-main-building pathways only
- basement inputs: basement geometry, one lumped exterior-to-basement perimeter
  opening, and one building-to-basement connection
- sump inputs: sump geometry, overflow settings, and pump settings

Users should not be asked to define internal routing syntax such as
`source,target` for the sump feature.

### Mandatory hydraulic inputs

- sump area \( A_s \)
- sump overflow level \( z_{ov} \)
- pump on level \( h_{on} \)
- pump off level \( h_{off} \)
- pump shut-off head \( H_{shut} \)
- pump curve coefficient \( k_{pump} \)
- pipe loss coefficient \( k_{pipe} \)
- sump base elevation \( z_{sump,base} \), from which \( H_{lift}(t) \) is derived
  using the external flood level in the current implementation

### Overflow inputs

- overflow coefficient \( C_{ov} \)
- overflow exponent \( m_{ov} \)

### Future-ready input

- pump availability factor \( \eta_p \), defaulting to 1

---

## 14. Minimum acceptance criteria for the implementation

The agent's implementation should be considered correct only if all the following are true.

### Functional requirements

- the model solves three water depths: building, basement, sump
- lumped exterior perimeter inflow to the basement system is redirected to the
  sump when the sump feature is enabled
- sump overflow adds water to basement
- pump removes water only from sump
- pump discharge depends on head
- pump switches on and off with hysteresis
- pump availability factor is present in the equations

### Numerical requirements

- no negative square-root failures occur
- no reverse flow through the pump is allowed
- sump overflow activates only above crest level
- the solver remains stable for cases with repeated pump cycling

### Structural requirements

- the new sump-pump feature can be turned on or off without breaking the existing building-basement solver
- future Monte Carlo support can replace the fixed \( \eta_p = 1 \) by a sampled binary state without changing the hydraulic equations
- the Streamlit app should expose the sump inputs, show the resulting sump state,
  and provide pathway-resolved diagnostics
- the implementation should include reproducible tutorial material showing at
  least: no-sump basement flooding, effective sump interception, and
  bypass-dominated flooding

---

## 15. Final compact equation block

For implementation, the full system is:

### Main building chamber

\[
A_b(h_b)\,\frac{dh_b}{dt} = Q_{ext,b}(t) - Q_{b \to bs}(t)
\]

### Basement chamber

\[
A_{bs}(h_{bs})\,\frac{dh_{bs}}{dt} = Q_{b \to bs}(t) + Q_{s \to bs}(t)
\]

### Sump chamber

\[
A_s\,\frac{dh_s}{dt} = Q_{ext,s}(t) - Q_p(t) - Q_{s \to bs}(t)
\]

### Sump overflow

\[
Q_{s \to bs}(t) =
\begin{cases}
0, & h_s \le z_{ov} \\
C_{ov}\,\bigl(h_s - z_{ov}\bigr)^{m_{ov}}, & h_s > z_{ov}
\end{cases}
\]

### Pump control

\[
u(t) =
\begin{cases}
1, & h_s \ge h_{on} \\
0, & h_s \le h_{off} \\
\text{previous state}, & h_{off} < h_s < h_{on}
\end{cases}
\]

### Pump characteristic

\[
H_{pump}(Q) = H_{shut} - k_{pump}\,Q^2
\]

### System head

\[
H_{system}(Q,t) = H_{lift}(t) + k_{pipe}\,Q^2
\]

### Pump operating point

\[
Q_p^{*}(t) =
\begin{cases}
\sqrt{\dfrac{H_{shut} - H_{lift}(t)}{k_{pump} + k_{pipe}}}, & H_{shut} > H_{lift}(t) \\
0, & H_{shut} \le H_{lift}(t)
\end{cases}
\]

### Effective pump discharge

\[
Q_p(t) = u(t)\,\eta_p\,Q_p^{*}(t)
\]

with

\[
\eta_p = 1
\]

for the current implementation.

## 16. Lessons learned from the first implementation

The first implementation was valuable because it exposed where the model was
clear internally but still too easy to misinterpret at the user interface.

The main lesson is that the sump-pump extension should be treated as a
**conceptually simple lumped hydraulic add-on**, not as a user-authored routing
network.

### 16.1 Keep the public interface aligned with the conceptual model

The first implementation exposed route labels such as `source,target` in the
user-facing ingress file and allowed users to author exterior-to-basement paths
there directly.

That turned out to be the wrong abstraction for this model.

The public interface should reflect the intended conceptual structure:

- the ingress file represents **exterior-to-main-building** ingress only
- the basement is activated through dedicated basement arguments
- exterior perimeter inflow to the basement system is represented by **one
  lumped opening**
- the building-to-basement pathway is represented by **one separate lumped
  connection**
- the sump is an **optional interception layer** added on top of the lumped
  exterior-to-basement opening

This is simpler for users and better aligned with the low-order nature of the
model.

### 16.2 Avoid interface choices that encourage double counting

The routed-ingress approach made it too easy to describe the same physical
process twice.

In particular, it blurred the distinction between:

- exterior perimeter inflow to the basement system
- building-to-basement bypass flow

That created a common failure mode:

- the building-to-basement connection remained active
- additional exterior-to-basement rows were added in the ingress file
- the resulting basement response looked far more severe than intended because
  two conceptually distinct pathways had been mixed without a clear accounting
  framework

The lesson is that the model should **separate hydraulic concepts in the
inputs**, rather than expecting users to reproduce internal routing correctly.

### 16.3 Preserve one routing rule and document it explicitly

The intended simplified routing is:

- the lumped exterior-to-basement opening feeds the basement directly when no
  sump is configured
- that same lumped exterior-to-basement opening is redirected to the sump when
  a sump is configured
- the building-to-basement connection always bypasses the sump

This rule should remain explicit in the specification, code, examples, and UI.

It is the key assumption that makes the sump interpretable as a lumped perimeter
interception system rather than as a generic extra storage chamber.

### 16.4 A sump that works can still coincide with a flooded basement

Early example runs showed an important interpretation trap: the sump and pump
may perform well on the intercepted perimeter inflow while the basement still
floods badly through the building-to-basement bypass.

That is not a contradiction. It simply means:

- the sump protects only the exterior-to-basement perimeter inflow
- it does **not** protect the building-to-basement connection
- therefore basement performance must be interpreted by pathway, not only by the
  final basement depth

This is why pathway-level diagnostics and cumulative volumes are important. A
single water-level plot is not always sufficient to explain whether the sump
system is effective.

### 16.5 The pump model needs explicit interpretation limits

The implemented pump model derives lift head from the external flood level and
the sump base elevation:

\[
H_{lift}(t) = H_{out}(t) - z_{sump,base}
\]

This is a useful first implementation because it introduces a time-varying,
head-dependent pump discharge without adding a more detailed discharge-network
model.

However, it also creates an interpretation limit that should always be made
explicit:

- as the external flood rises, the modeled pump capacity falls
- at sufficiently high external levels, the pump may approach shutoff
- this makes the current model conservative for severe events if the real
  discharge outfall is better protected than the exterior flood level implies

So the lesson is not that the pump model is wrong, but that its physical meaning
must be stated clearly whenever results are discussed.

### 16.6 Threshold-controlled sump behavior is timestep-sensitive

The sump and pump dynamics include:

- on/off hysteresis
- overflow activation at a crest threshold
- explicit time stepping

The first implementation showed that coarse timesteps can produce visually odd
or exaggerated sawtooth behavior in \( h_s(t) \), especially when the pump is
strong relative to the sump storage.

For the current implementation, the practical lessons are:

- use smaller user `dt` values when analyzing sump behavior
- be cautious when interpreting short-cycle behavior from coarse timesteps
- document internal substepping or adaptive timestepping as a future
  improvement, not as hidden present behavior

In other words, timestep sensitivity should be **visible and documented**, not
silently masked.

### 16.7 Good examples and diagnostics matter as much as equations

The first implementation also showed that users can easily misread the model if
they see only:

- final water depths
- a single time-series plot
- an example with mixed pathways but little explanation

For this reason, the extension benefits from:

- pathway-resolved diagnostics
- cumulative transferred volumes
- explicit case studies showing effective sump behavior, bypass-dominated
  flooding, and pump-limited behavior
- tutorial material that explains what the sump is protecting and what it is not
  protecting

This is not ancillary documentation work. It is part of making the model
interpretable.

### 16.8 Recommended public interface after these lessons

The preferred user-facing structure is:

- ingress file: exterior-to-main-building pathways only
- basement: enabled through dedicated basement arguments
- exterior-to-basement perimeter inflow: one lumped opening configured through
  dedicated basement arguments
- building-to-basement bypass: a separate dedicated connection
- sump: enabled through additional sump and pump arguments

This interface is more robust because it:

- matches the conceptual equations
- avoids accidental double counting
- makes the routing rule obvious
- keeps the user focused on hydraulic meaning rather than internal graph syntax

---

## 17. Prioritised implementation steps for the redeployment from `main`

The redevelopment should start from `main`, not by incrementally patching the
previous experimental branch.

The priority order should be:

### 17.1 First priority: rebuild the hydraulic core with the corrected interface

Implement the sump-pump extension with the corrected public abstraction:

- ingress file: exterior-to-main-building pathways only
- basement perimeter inflow: one lumped exterior-to-basement opening
- building-to-basement bypass: one separate connection
- sump: intercepts the lumped exterior-to-basement opening when enabled

This is the most important correction from the first implementation and should be
locked in before adding higher-level features.

### 17.2 Second priority: keep one hydraulic source of truth

The solver and the diagnostics layer should not evolve as two independent copies
of the same equations.

Prefer one of the following:

- instrument the core solver so diagnostics are emitted directly from the same
  timestep loop, or
- factor the hydraulic update into shared helper functions used by both solver
  and diagnostics

This is a higher engineering priority than adding more visual features, because
it reduces long-term drift risk and keeps the advanced interpretation outputs
trustworthy.

### 17.3 Third priority: preserve the current pump model, but isolate it for later upgrade

For this redeployment, retain the current first-order pump assumption:

\[
H_{lift}(t) = H_{out}(t) - z_{sump,base}
\]

However, implement it in a way that can later be replaced by a more detailed
outfall-head model without restructuring the whole solver.

This is important because the current assumption is useful and simple, but it
can be conservative for severe floods if the real discharge outfall is better
protected than the exterior water level suggests.

### 17.4 Fourth priority: expose pathway-resolved interpretation, not only water levels

Reintroduce the advanced diagnostics and dashboard only after the corrected
hydraulic interface is in place.

The diagnostics should make it possible to distinguish:

- effective sump interception
- bypass-dominated basement flooding
- sump overflow contribution
- pump-limited behavior

This is necessary because basement depth alone is not sufficient to explain
whether the sump system is working.

### 17.5 Fifth priority: integrate the same interpretation layer into Streamlit

The Streamlit app should display:

- the original simulation result plot
- advanced diagnostics/interpretation views
- pathway tables and timings
- a downloadable diagnostics CSV

The app integration should use the same hydraulic source of truth described
above, not an inconsistent parallel implementation.

### 17.6 Sixth priority: keep the tutorial and case studies reproducible

The tutorial should not be treated as optional polish.

It should be part of the redeployment because the first implementation showed
that the sump model is easy to misread without:

- pathway-level interpretation
- worked case studies
- embedded figures
- a reproducible asset-generation workflow

### 17.7 Seventh priority: carry forward known limitations explicitly

The redeployed implementation should continue to document that:

- the model is lumped, not spatially distributed
- the pump-head assumption is simplified
- threshold behavior is timestep-sensitive
- no hydraulic substeps are included in this release

These are acceptable first-release limits, but they must be visible in the
documentation and examples.

### 17.8 Next improvements after the redeployment is stable

Once the clean redeployment from `main` is working, the next improvements should
be prioritised as follows:

1. Keep solver and diagnostics on one source of truth.
2. Improve the pump outfall / downstream-head representation.
3. Add optional internal hydraulic substeps or adaptive stepping for threshold-sensitive sump behavior.
4. Make the building-to-basement bypass more explicitly configurable if needed.
5. Add calibration or benchmark cases to support physical interpretation, not just numerical consistency.

---

## 18. Instruction to the coding agent

Introduce the sump-pump functionality as a **modular extension** to the existing building-basement solver.

The implementation should:

- preserve the existing building and basement equations
- add the sump as a third chamber
- add lumped exterior perimeter inflow that is redirected to the sump when enabled
- add sump-to-basement overflow
- add a head-dependent pump discharge law
- keep pump availability as an explicit multiplicative factor set to 1
- add advanced diagnostics and interpretation outputs using the same hydraulic source of truth as the solver
- integrate those diagnostics into the Streamlit app
- include a reproducible tutorial with case-study figures
- avoid modelling anything spatially distributed or mechanically detailed beyond the lumped equations above

The first goal is a stable, transparent, low-order implementation, not a detailed drainage network model.
