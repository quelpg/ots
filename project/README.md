# OTS-SC-DCOPF on the IEEE 118-bus system

Optimal transmission switching (OTS) under a preventive N-1 security criterion (SC-DCOPF),
solved with Gurobi. Undergraduate thesis code.

> **Reorganized on 2026-11-16.** The project is now organized by study case. The model is being
> rewritten as a Python package (`model/`); the notebooks that produced the results so far are
> kept, unchanged, in `old/pre-reorg-2026-11/`. The git tag `pre-reorg` marks the last commit
> before the reorganization (`git checkout pre-reorg` restores the old layout).

## Study cases → folders

| Study case (thesis) | Question | Folder | Status |
|---|---|---|---|
| Reference (K = 0) | Cost of N-1 security without switching (security premium); which contingencies are infeasible | `reference-k0/` | done (old code) |
| CS1a – Cost reduction under N-1 | How much does switching reduce the cost, with how many open lines (K sweep)? | `cs1a-k-sweep/` | MILP sweep K = 0–10 done (old code); heuristic warm start next |
| CS1b – Load-level sensitivity | How do the savings and the maximum N-1 load change with the load level? | `cs1b-load-levels/` | to do |
| CS2 – Recovery of N-1 feasibility | With the full contingency list, which topology makes N-1 feasible? | `cs2-full-n1/` | K ≤ 3 proven infeasible; violation heuristic next |
| CS3 – Renewable siting and curtailment | Concentrated vs. distributed renewables: curtailment and cost | `cs3-renewables/` | to do |
| Model validation | Do the solutions hold in an independent DC power flow (pandapower `rundcpp`)? | `validation/` | SC-DCOPF done (old code); OTS to do |

Tools shared by the cases:

| Folder | What it is |
|---|---|
| `model/` | The single source of the formulation (SC-DCOPF and OTS-SC-DCOPF). *(being written)* |
| `heuristics/` | Sequential sensitivity-based switching heuristic (Fuller 2012, Ruiz 2012), used as MILP warm start. |
| `preprocessing/` | Raw data → `processed/`, and the single-line diagram. |
| `tests/` | Reference checks every change must pass. *(being written)* |

Data and outputs:

| Folder | What it is |
|---|---|
| `data/` | Raw input data (MATPOWER case118, SCUC/StarGenLite, SIN). Never written by the code. |
| `processed/<source>/` | Clean tables read by every model (`gens`, `loads`, `branches`, `system_meta`). |
| `<case>/results/<source>/<formulation>/<config>/K<k>/` | Results of each run (`summary.csv`, `dispatch.csv`, `line_loading.csv`, `switching.csv`, `angles.csv`). |
| `figures/` | Figures used in the thesis. |
| `old/` | Superseded code and results, kept for reference. |

Notes and task list: `RESULTS_NOTES.md` (results and interpretation, OTS cases),
`reference-k0/RESULTS_NOTES.md` (reference case), `TODO.md` (task list, in Portuguese).

## Reference values

Any change to the model must reproduce these (MATPOWER data, `redispatch_with_exclusions`,
194 states):

| Case | Cost ($/h) |
|---|---|
| DCOPF without N-1 | 93,152.38 |
| SC-DCOPF, original topology (K = 0) | 109,681.25 |
| OTS, saved K = 2 topology (lines 64-65, 77-80) | 107,665.95 |

## How to run

Environment: the virtual environment at `../venv` (Python 3.13, Gurobi 13.0.2). From `project/`:

```
..\venv\Scripts\activate
```

| I want to... | Command (run from) | Output |
|---|---|---|
| Rebuild the processed data (MATPOWER) | `jupyter nbconvert --to notebook --execute --inplace pre-processing.ipynb` (`preprocessing/`) | `processed/matpower/` |
| Rebuild the processed data (SCUC) | same, with `pre-processing-scuc.ipynb` (`preprocessing/`) | `processed/scuc/` |
| Redraw the single-line diagram | `python preprocessing/single_line_diagram.py` (anywhere) | `figures/ieee118_unifilar.drawio` |
| Check the heuristic's LP against the reference values | `python ranking_test.py --check-only` (`heuristics/`) | console |

Each folder's `README.md` lists its own commands. Every script prints its options with `--help`.
