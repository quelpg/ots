# SC-DCOPF — Results Notes (IEEE 118-bus, MATPOWER data)

> Tracking of results. Numeric CSVs live under `results/<formulation>/<config>/`.
> This file is for notes and interpretation.
>
> **Organization:** results are indexed by **formulation** (how infeasibilities are handled)
> and by **config** (which contingencies are included):
> - Formulations: `redispatch_only` · `redispatch_with_exclusions` · `with_load_shedding` (future)
> - Configs: `basecase` (C={0}) · `cont_gen` (generators only) · `cont_trans` (lines only) · `contingencies` (all)

---

## 1. N-1 vulnerability diagnostic

See `results/vulnerability/`. Each contingency is solved **in isolation** (one DCOPF per
state), giving the **complete and deterministic** picture of which ones fail — unlike the IIS,
which only reveals one conflict at a time.

Of **196 contingencies tested, only 3 are infeasible** (without load shedding):

| scenario_id | type | element | branch_id / gen_id |
|---|---|---|---|
| 7   | line | **8-5**   | branch_id 7 |
| 49  | line | **38-37** | branch_id 50 |
| 178 | gen  | **bus 10 (505 MW)** | gen_id 0 |

- The 2 line cases are **congestion**: removing the line pushes flow onto weaker neighbors and
  exceeds the thermal limit (3.4). Not islanding (none of them is a bridge).
- The generator case (bus 10, 505 MW) is more severe: losing a large unit leaves the remaining
  capacity + network unable to redistribute within limits.
- **Numbering note:** `scenario_id` (state index, base = 0), `branch_id` (branch index) and the
  physical label (`38-37`) are three names for the same element. E.g. scenario 49 = branch_id 50
  = line 38-37. The `+1` offset comes from the base case taking id 0.

---

## 2. Formulation `redispatch_only` (no infeasibility handling)

Pure corrective redispatch, with **no** exclusions and **no** load shedding. Shows that the
network cannot survive all N-1 contingencies in this form.

| Config | Result | Note |
|---|---|---|
| `basecase`       | **OK** — $93,152.38/h | plain DCOPF (validation) |
| `cont_gen`       | **INFEASIBLE** | IIS points to scenario 1 = **gen 0 out** (bus 10) |
| `cont_trans`     | **INFEASIBLE** | IIS points to scenario 7 = **line 8-5** |
| `contingencies`  | **INFEASIBLE** | IIS points to scenario 7 = **line 8-5** |

The IIS shows one conflict at a time; the full list (3 elements) comes from the vulnerability
analysis above. For each infeasible case the notebook saves `iis_full.ilp` (Gurobi's ground
truth) and `iis_summary.csv` (deterministic per-scenario summary, with an `out_element` column
translating the scenario into the physical element).

---

## 3. Formulation `redispatch_with_exclusions` (Step 1 — working baseline)

The 3 infeasible contingencies are **removed** from the set (element-wise exclusion via
`EXCLUDE`). This is a **temporary** scope choice — they will be brought back in the load-shedding
formulation. With this, the model solves in every config.

**Probability weights (current):** each generator contingency `ρ_G = 10⁻²`, each line
contingency `ρ_L = 10⁻³`, and the base case takes the remainder (`ρ_0 = 1 − Σ`). Weights reflect
the per-equipment failure rate and do **not** depend on how many contingencies exist.

| Config | Expected cost | # states | ρ_base | Status |
|---|---|---|---|---|
| `basecase`       | $93,152.38 /h | 1   | 1.0000 | OK (same as redispatch_only/basecase) |
| `cont_gen`       | **$93,492.33 /h** | 19  | 0.8200 | OK (18 generator contingencies; 1 excluded) |
| `cont_trans`     | **$93,169.37 /h** | 176 | 0.8250 | OK (175 line contingencies; 2 excluded) |
| `contingencies`  | **$93,509.32 /h** | 194 | 0.6450 | OK (193 contingencies; 3 excluded) |

In all cases: load = generation = 4242 MW, 13 generators dispatched.

### Reading the costs

- With per-type weights, the expected cost rises more visibly than with equal weights, where
  the effect was almost invisible. Contingencies now carry a physical weight.
- **`cont_gen` is far more expensive** (+$340/h over base) than `cont_trans` (+$17/h). Two
  effects add up: (i) generator contingencies are physically more expensive to compensate, and
  (ii) they weigh 10× more per scenario (`ρ_G = 10⁻²` vs `ρ_L = 10⁻³`).
- `contingencies` ($93,509) is close to `cont_gen`, confirming that the expected cost is
  **dominated by generator contingencies** — the line ones barely move the number.
- To compare the *physical* impact of each type without the weight effect, see the per-scenario
  cost below.

### Per-scenario cost (fair comparison, unweighted)

Solving each contingency in isolation and measuring its redispatch cost (reproducible from the
vulnerability sweep):

| | mean cost | worst case | over base |
|---|---|---|---|
| base | $93,152 | — | — |
| **generator** contingency | $95,041 | $103,511 | up to **+$10,359** |
| **line** contingency      | $93,249 | $95,773  | up to **+$2,621** |

- Without the weight bias, generator contingencies are confirmed to be **genuinely more
  expensive** — on average and in the worst case, ~4× the impact of a line contingency. A real
  physical effect: losing a cheap generator forces more expensive units on; losing a line only
  reroutes flow, which is cheaper to compensate.
- **Methodology takeaway:** to compare the impact of contingency *types*, use the per-scenario
  cost (mean/max), not the weighted expected cost — the latter depends on how many scenarios
  each config has.

---

## 4. Base case — details (common to all formulations)

The base case (C={0}) has no contingencies, so exclusion does not affect it: same result in any
formulation. See `results/redispatch_only/basecase/`.

- 19 generators available, **13 dispatched** (merit order: cheapest first).
- Cheapest generator (bus 100, c1=12.61) at **100%** (653 MW). Several cheap units at full load.
- Bus **69 (slack)** is the **marginal generator**: it dispatches 629.7 of 1182 MW (53%); it does
  not saturate because the load runs out first. Its cost (c1=25.76) sets the system marginal price.
- 6 generators stay at zero (the most expensive, c1 from 28.9 to 124.6).

### Congestion already in the base case

| Line | Flow (MW) | Limit (MW) | Loading |
|---|---|---|---|
| 100-103 | 151.0 | 151.0 | **100%** |
| 49-69   | -87.0 | 87.0  | **100%** |
| 89-92   | 185.05| 186.0 | 99.5% |
| 47-69   | -96.03| 102.0 | 94.1% |
| 94-100  | -131.05| 150.0| 87.4% |

The network already runs at the limit on some branches — anticipating the violations under
contingency.

### Angles (θ)

Slack (bus 69) = 0°; others relative to it. Observed range ≈ **-29° to +26°**, within the typical
±30° validity limit of the DC approximation (the angle limit was **not** imposed; it appeared
naturally). Largest positive: bus 89 (637 MW generator at full load). Largest negative: bus 41.

---

## 5. Pending / next steps

- [ ] **Step 2 — load shedding (VOLL):** bring back the 3 excluded contingencies with a penalized
      unserved-load variable. Makes every state feasible, and "how much was shed" becomes a
      result. Formulation `with_load_shedding`. Align with advisor.
- [ ] ρ_c: currently `ρ_G = 10⁻²` and `ρ_L = 10⁻³` (per-type failure), base takes the remainder.
      Possible sensitivity study: test `ρ_L = 10⁻⁴` and observe the effect on expected cost.
- [ ] Compare base cost against case118 literature (external sanity check).
