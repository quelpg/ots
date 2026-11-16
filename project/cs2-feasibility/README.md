# CS2 – Recovery of N-1 feasibility above λ_max

**Question:** with the full contingency list (197 states), the original topology is N-1 secure
only up to λ_max = 0.850. At a load level above it, how many open lines (K) does switching need
to make N-1 feasible again, and at what cost?

Above λ_max no single contingency is infeasible alone: the minimal conflicting set at λ = 0.852 is
the base case + line 8-5 + line 26-30 + the bus-10 generator + the bus-66 generator (removing any
one of them makes it feasible). The limit comes from the network, not from generation capacity
(even without the largest unit, 5,333 MW remain), so switching can help.

## Method (for each λ chosen above 0.850, e.g. 0.90, 0.95, 1.0)

1. **Relaxed LP:** SC-DCOPF with slacks on the flow limits, minimizing the total violation. Its
   duals feed the heuristic criteria (the slack weights only guide the heuristic; they do not
   affect the final result).
2. **Heuristic:** open the best candidate, re-solve, keep it if the violation decreases; repeat
   until the violation is zero. The topology found (K_h open lines) is proven feasible by the LP
   without slacks.
3. **MILP** minimizing the number of open lines subject to the full N-1, with warm start from the
   heuristic: may find a smaller K and gives the lower bound. Result: K_min(λ) between the lower
   bound and K_h. At λ = 1, K ≤ 3 is already proven infeasible (results below).
4. **Cost** at that K: cost MILP with warm start.

Output for the thesis: K_min per λ, and the cost of N-1 secure operation at each λ.

Auxiliary tool: the max-λ LP (λ as a variable) gives, in one LP, the highest load a fixed
topology supports under N-1.

## Results (old code)

`results/matpower/redispatch_only/screening/`: core screening at λ = 1 (MILP on a small core of
states + IIS + constraint generation):

- `summary_K1-10.csv`, `summary_K5-10.csv`, `K*_it1.log`, `first_sweep/`: cost-mode runs on a
  4-state core (base, 8-5 out, 38-65 out, bus-10 generator out). K = 1, 2, 3 are infeasible on
  the core, which is a relaxation: this is the **proof that no topology with K ≤ 3 is feasible
  at λ = 1**. K = 4–7 hit the time limit without a solution (unknown).
- `summary_min_switching.csv`, `minsw_it1.log`, `progress_min_switching.log`: minimum-switching
  run of 2026-11-13 (4..10 open lines, 1 h, no warm start): undecided, no topology found.

Produced by `old/pre-reorg-2026-11/ots-sc-dcopf/full-ct-feasibility/` (`core_screening.py`,
`ots-full-ct-feasibility.ipynb`). It does not run from `old/`. Interpretation: `../RESULTS_NOTES.md`.

Commands for the new scripts will be listed here when they are ready.
