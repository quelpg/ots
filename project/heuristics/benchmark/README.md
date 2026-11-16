# Heuristic benchmark: MILP K sweep at λ = 1 with the reduced contingency list

The K sweep run before the 2026-11-16 restructuring (old Analysis A). It is no longer a study
case: it is the reference used to validate the heuristic (MILP × heuristic × MILP with warm start).

Load level λ = 1 (nominal load, 4,242 MW). Contingency list: reduced (`redispatch_with_exclusions`,
194 states: line 8-5, line 38-65 and the bus-10 generator excluded).

## Results

`results/matpower/redispatch_with_exclusions/`:

| Folder | What it is |
|---|---|
| `contingencies/K0..K10/` | MILP K sweep (Gurobi, chained warm start; K ≥ 3 stopped at the time limit with a gap of ~7%) |
| `basecase/` | OTS without N-1 |
| `contingencies_run1/` | *(to be created)* backup of `contingencies/` before any rerun |
| `contingencies_improved/K<n>/` | *(to be created)* topologies from the heuristic, used as warm starts |

`logs/`: console logs of the sweep runs.

Results table, figure and interpretation: `../../RESULTS_NOTES.md` §1.

## Code

Produced by `old/pre-reorg-2026-11/ots-sc-dcopf/` (`ots-sc-dcopf.ipynb`, `sweep_k.py`,
`plot_k_sweep.py`, `solution-quality/`). It does not run from `old/`.
