# CS2 – Recovery of N-1 feasibility (full contingency list)

**Question:** with the full contingency list (`redispatch_only`, including line 8-5, line 38-65
and the bus-10 generator), the SC-DCOPF on the original topology is infeasible. Is there a
switching topology that makes it feasible, and with how many open lines?

## Results

`results/matpower/redispatch_only/screening/`: core screening (MILP on a small core of states
+ IIS + constraint generation):

- `summary_K1-10.csv`, `summary_K5-10.csv`, `K*_it1.log`, `first_sweep/`: cost-mode runs on a
  4-state core (base, 8-5 out, 38-65 out, bus-10 generator out). K = 1, 2, 3 are infeasible on
  the core, which is a relaxation: this is the **proof that no topology with K ≤ 3 is feasible**.
  K = 4–7 hit the time limit without a solution (unknown).
- `summary_min_switching.csv`, `minsw_it1.log`, `progress_min_switching.log`: minimum-switching
  run of 2026-11-13 (4..10 open lines, 1 h): undecided, no topology found.

Interpretation: `../RESULTS_NOTES.md`.

## Code

Produced by `old/pre-reorg-2026-11/ots-sc-dcopf/full-ct-feasibility/` (`core_screening.py`,
`ots-full-ct-feasibility.ipynb`). It does not run from `old/`.

Next: violation-minimizing heuristic (LP with slacks on the flow limits → violation prices →
sequential switching until the violation is zero → LP without slacks to prove feasibility).
Commands will be listed here when the scripts are ready.
