# OTS-SC-DCOPF — Results Notes (IEEE 118-bus, MATPOWER data)

> Tracking of results and open decisions. Numeric CSVs live under
> `results/<source>/<formulation>/<config>/<K>/`. This file is for notes and interpretation.
>
> **Model:** SC-DCOPF (`../sc-dcopf/`) + preventive transmission switching: one binary $z_{ij}$
> per branch, shared by every operating state. Thesis formulation: section 3.3.1, eqs (3.8)–(3.16),
> plus the additions listed in §5.
>
> **Settings used so far (unless noted):** radial branches fixed closed ($z=1$), per-branch big-M
> $M_{ij} = \Delta\theta^{\max}/x_{ij}$, `MIP_GAP = 1e-4`, `RHO_GEN = 1e-2`, `RHO_LINE = 1e-3`.
> Gurobi 13.0.2, i7-1360P, 16 threads.

---

## 1. Base case ($\mathcal{C}=\{0\}$)

| | Cost ($/h) | Lines opened | Notes |
|---|---|---|---|
| SC-DCOPF, fixed topology | 93,152.38 | 0 | reference (`../sc-dcopf/RESULTS_NOTES.md`) |
| OTS, `MIP_GAP = 1e-4` | 93,029.48 | 43 | saved in `results/.../basecase/`; 0.6 s |
| OTS, exact optimum (`MIP_GAP = 0`) | **93,026.73** | — | −$125.65/h (−0.13%) |
| OTS, exact + tie-break (min. lines opened) | **93,026.73** | **4** | 47-69, 49-69, 89-92, 103-110 (scratch test, not in notebook) |

- The saving is small: with the original case118 load the network has few bottlenecks. The 4
  lines of the tie-break solution sit exactly in the congested region of the SC-DCOPF base case
  (49-69 and 89-92 were at ~100%).
- **The list of 43 opened lines is not meaningful** (degenerate optimum, see §4.2): the same cost
  is reached with 4 openings. Do not report the CSV list as is.
- `results/.../basecase/` folders predate the K-tagged layout (`<config>/<K>/`) and were run with
  $\Delta\theta^{\max} = 180°$.

---

## 2. N-1 of lines, `redispatch_only` (`cont_trans`: base + 177 non-radial line contingencies)

Without switching this case is **infeasible** (SC-DCOPF: lines 8-5 and 38-37 have no corrective
solution). Question: can switching make it feasible?

### 2.1 Without a switching limit (K unlimited)

| $\Delta\theta^{\max}$ | Time | Outcome |
|---|---|---|
| 180° | 600 s (limit) | no feasible solution found, still at the root node |
| 90° | ~19 min (stopped) | same; best bound stalled at 93,031.96 |

Inconclusive (neither feasible nor infeasible). Root LP alone took 120–200 s; the cut loop
barely moved the bound. Motivated the switching limit $K$ and the solver settings
(`MIPFocus=1`, `NoRelHeurTime=300`, `Cuts=1`).

### 2.2 Diagnostic with only the two critical contingencies (scratch, K unlimited, 180°)

| States | Without OTS | With OTS ($/h) |
|---|---|---|
| base + 8-5 | infeasible | 93,035.78 |
| base + 38-37 | infeasible | 93,031.38 |
| base + both | infeasible | 93,032.52 |

Solved in seconds. Caveat: islanding was only checked in the base topology at that time, so
these may also rely on islands (see §2.4).

### 2.3 Switching-limit sweep ($\Delta\theta^{\max} = 90°$)

| K | Outcome | Cost ($/h) | Time | Lines opened |
|---|---|---|---|---|
| 1 | **infeasible** (proven) | — | 374 s | — |
| 2 | **infeasible** (proven) | — | not recorded | — |
| 3 | **optimal** (gap 0.00%) | **93,208.34** | 2,930 s (680 nodes) | **8-30, 34-37, 30-38** |
| 4 | **optimal** (gap 0.00%) | **93,157.85** | 2,936 s | 8-30, 34-37, 30-38, **103-105** |
| 5 | time limit (gap 0.12%, bound 93,037.40) | **93,148.55** | 3,600 s | 8-30, 34-37, 30-38, **82-96**, 103-105 |

- **Minimum number of switching actions that makes the line N-1 feasible: 3** — under the
  assumption that islanding is allowed (§2.4).
- **K = 4 is K = 3 plus one line** (103-105): the solutions are nested. The extra opening cuts
  the expected cost by $50.49/h.
- **K = 5 is K = 4 plus 82-96** (nested again), −$9.30/h vs K = 4. Not proven optimal: the
  remaining gap ($111/h) is larger than the K4→K5 gain, so K = 5 could still improve.
  Diminishing returns: K3→K4 −$50.49/h, K4→K5 −$9.30/h.
- K = 1 and 2 leave no files (the notebook only exports when a solution exists).
- K = 3 results: `results/matpower/redispatch_only/cont_trans/K3/`. 178 states, 13 active
  generators, no island in the base topology.
- The three opened lines are in the region of the two critical contingencies (8-5, 38-37), so
  the switching acts where the bottleneck is.
- **Cost is not directly comparable** with the SC-DCOPF `redispatch_with_exclusions/cont_trans`
  ($93,169.37/h): different state sets (8-5 and 38-37 included here) and different $\rho_0$. The
  gain in this case is *feasibility*, not cost.

### 2.4 Islanding in the K = 3 solution

The big-M check warned "binding" (90°). The cause is an **island**, not the big-M:

- Scenario 7 = contingency of line **8-5**. With **8-30** opened by the OTS, buses **8, 9, 10** lose
  every path to the slack and form an island: the bus-10 unit (505 MW) feeds the 28 MW load of
  bus 8 alone.
- Angles inside an island have no reference and drift to the big-M bound, hence the 90°. The
  next largest angle difference across an open line is 22.6° → the 90° limit is **not** really
  active, and the K = 1 / K = 2 infeasibility results stand.
- So contingency 8-5 is "solved" by islanding.

### 2.5 Fixed-topology verification (K = 0, 3, 4)

With $z$ fixed the states decouple, so each state was re-solved as a plain DCOPF (independent LP
per state, Gurobi; scratch script, not in the notebook). Expected cost recomposed with the same
$\rho$:

| Topology | Infeasible states | Expected cost ($/h) | Base-case cost ($/h) | States with islands |
|---|---|---|---|---|
| K0 (no switching) | 8-5, 38-37 | — | 93,152.38 | 0 |
| K3 | none | **93,208.34** (= MILP) | 93,167.40 | 1: 8-5 → island {8, 9, 10} |
| K4 | none | **93,157.85** (= MILP) | 93,117.03 | 1: 8-5 → island {8, 9, 10} |
| K5 | none | **93,148.55** (= MILP) | 93,108.88 | 1: 8-5 → island {8, 9, 10} |

- Both MILP costs are reproduced exactly → the K3/K4 solutions are consistent.
- **Only contingency 8-5 relies on islanding.** **38-37 is made feasible without any island**:
  a genuine OTS gain.
- The island state (8-5 out) is expensive: ~$104,000/h, because the bus-10 unit (505 MW, cheap)
  can only serve the 28 MW inside the island and the rest is re-dispatched elsewhere.
- **K3 makes the base case more expensive** than the fixed topology (+$15/h): part of the cost
  of N-1 security. **K4 makes it cheaper** (−$35/h): the 4th line pays for itself.
- Where the 4th line (103-105) helps, K4 − K3 per state: base −$50.37/h; line states mean
  −$51.04/h, best −$345/h (contingencies 80-98, 80-99, 98-100, 99-100, 92-93 — the 80–100 region),
  never worse. Weighted contribution: base −$41.45/h, contingencies −$9.03/h. 103-105 is in the
  same region as the base-case OTS openings (§1: 103-110), i.e. it mostly relieves the
  base-case congestion around 100-103.
- K5 − K4 per state (82-96 added): base −$8.15/h; line states mean −$14.66/h, best −$323/h
  (98-100, 99-100, 80-99, 94-96, 94-95), but **not always better**: worst +$199/h. Weighted:
  base −$6.71/h, contingencies −$2.60/h. Same 80–100 region.

---

## 3. Computational notes

- Full `cont_trans` model: ~160k rows, ~58k columns, 186 binaries (86 after presolve).
- The K limit makes the problem tractable: K = 1 was proven infeasible in ~6 min, while the
  unlimited run did not leave the root node in 19 min.
- The IIS is **useless** for this MILP: $z$ couples all states, so the IIS contains the whole
  model (160,211 constraints, 900 s on K = 1). `COMPUTE_IIS = False` by default.
- `NoRelHeurTime = 300`: did not find a solution on K = 1, 2, 3 (it got close on K = 2). The
  K = 3 incumbent came from the branch-and-bound tree (node 70, ~990 s).

---

## 4. Open decisions

### 4.1 Islanding in contingency states — *discuss with advisor*
- **Allow (current):** islanding under contingency happens in practice (controlled islanding);
  here the island is small and self-sufficient.
- **Forbid:** a 505 MW unit feeding 28 MW raises frequency-control, stability and resynchronization
  issues, and the island is *planned* by the preventive switching (8-30 opened in advance).
- If forbidden: per-state single-commodity fictitious-flow connectivity constraints for
  $c \in \{0\} \cup \mathcal{C}_T$ (generator contingencies keep the base topology). ~33k extra
  continuous variables, no new binaries. Designed, not implemented; K = 3 may become infeasible.

### 4.2 Degenerate optimum / tie-break
$z$ has no cost, so lines that do not change the dispatch are opened arbitrarily (43 vs 4 in the
base case). Needed before reporting "lines opened by the OTS" as a metric. Option: lexicographic
objective (cost first, then minimize $\sum(1-z)$). With K small this matters less, but still applies.

### 4.3 Per-state islanding check
Section 8.1 of the notebook checks islands only in the base topology. It should check every state
and list which contingencies rely on islands. Diagnostic only, does not change the model. (Done
offline for K3/K4 in §2.5; still to be added to the notebook.)

### 4.4 $\Delta\theta^{\max}$
Currently 90°. Either a purely computational big-M sizing (must never be active) or an
operational limit on the standing angle across an open breaker (then declared in the model and a
candidate sensitivity parameter).

---

## 5. Still to add to the thesis text (section 3.3.1)

- [ ] Switchable set $\mathcal{L}^S$ (non-radial branches); $z_{ij} \in \{0,1\}\ \forall \mathcal{L}^S$ and
      $z_{ij} = 1\ \forall \mathcal{L}\setminus\mathcal{L}^S$ (replaces (3.11) over all of $\mathcal{L}$).
- [ ] Per-branch big-M $M_{ij} = \Delta\theta^{\max}/x_{ij}$ in (3.13)/(3.14), and the definition of $\Delta\theta^{\max}$.
- [ ] Switching limit $\sum_{\mathcal{L}^S}(1-z_{ij}) \le K$ ($K=0$ recovers the fixed-topology SC-DCOPF).
- [ ] State explicitly that switching is **preventive** ($z$ has no scenario index).
- [ ] Islanding assumption (§4.1), whatever is decided.

---

## 6. Next steps

- [ ] Record K = 2 run time (from the notebook log, if still available).
- [ ] Export a `summary.csv` also for infeasible runs (status, K, time) so the K sweep is recorded.
- [ ] Add the per-state islanding check to the notebook (§4.3).
- [ ] Validate the K3/K4 topologies in pandapower: with $z$ fixed the states decouple again, so
      the per-scenario decomposition of `../validation/scdcopf-pandapower.ipynb` applies (§2.5 was
      a Gurobi-only re-solve).
- [ ] Continue the K sweep (K = 5, …, K_inf) → cost and time vs K.
- [ ] Generator contingencies (`cont_gen`) and the full set (`contingencies`); bus-10 unit loss is
      a capacity problem, switching is unlikely to fix it.
- [ ] Nothing committed yet (`ots-sc-dcopf/` is untracked).
