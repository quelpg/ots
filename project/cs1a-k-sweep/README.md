# CS1a – Cost reduction under N-1 security: K sweep

**Question:** how much does preventive switching reduce the cost of N-1 secure operation, and
with how many open lines (K = maximum number of open lines)?

Contingency set: `redispatch_with_exclusions` (194 states, see `../reference-k0/README.md`).

## Results

`results/matpower/redispatch_with_exclusions/`:

| Folder | What it is |
|---|---|
| `contingencies/K0..K10/` | MILP K sweep (Gurobi, chained warm start; K ≥ 3 stopped at the time limit with a gap of ~7%) |
| `basecase/` | OTS without N-1 (reference) |
| `contingencies_run1/` | *(to be created)* backup of `contingencies/` before the warm-start rerun |
| `contingencies_improved/K<n>/` | *(to be created)* topologies from the heuristic, used as warm starts |

`logs/`: console logs of the sweep runs.

Results table, figure and interpretation: `../RESULTS_NOTES.md` §1.

## Code

The sweep so far was produced by `old/pre-reorg-2026-11/ots-sc-dcopf/` (`ots-sc-dcopf.ipynb`,
`sweep_k.py`, `plot_k_sweep.py`, `solution-quality/`). It does not run from `old/`.

Next (with the new `model/` package): K sweep with warm start from the heuristic
(`../heuristics/`), and the table "MILP × heuristic × MILP with warm start" per K.
Commands will be listed here when the scripts are ready.
