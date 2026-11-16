# OTS-SC-DCOPF on the IEEE 118-bus system

Optimal transmission switching (OTS) under a preventive N-1 security criterion (SC-DCOPF),
solved with Gurobi. Undergraduate thesis code.

> **Reorganized on 2026-11-16.** The project is organized by study case. The model is being
> rewritten as a Python package (`model/`); the notebooks that produced the results so far are
> kept, unchanged, in `old/pre-reorg-2026-11/`. The git tag `pre-reorg` marks the last commit
> before the reorganization (`git checkout pre-reorg` restores the old layout).

## Study cases → folders

Every case uses the **full contingency list** (197 states: base + 177 non-radial branches + 19
generators, no exclusions). What changes between cases is the **load level λ**: every load is
scaled by λ (generation is not scaled). With the original topology, N-1 is feasible up to
**λ_max = 0.850** (3,606 MW of the 4,242 MW nominal load). K = maximum number of open lines.

| Study case (thesis) | Question | Folder | Status |
|---|---|---|---|
| Reference (K = 0) | Cost of N-1 security without switching, per λ: copper plate, DCOPF, SC-DCOPF and the security premium (SC-DCOPF − DCOPF) | `reference/` | λ = 1 with the reduced list done (old code); λ grid to do |
| CS1 – Cost reduction (λ ≤ λ_max) | How much does switching reduce the cost, with how many open lines? | `cs1-cost/` | to do: heuristic at every λ, MILP with warm start at 2–3 λ |
| CS2 – Recovery of N-1 feasibility (λ > λ_max) | How many open lines make N-1 feasible again at a given λ? K_min(λ): violation heuristic + minimum-switching MILP with warm start | `cs2-feasibility/` | at λ = 1, K ≤ 3 proven infeasible (old code); to do |
| CS3 – Renewables | Concentrated vs. distributed renewables at a fixed feasible λ: curtailment and cost | `cs3-renewables/` | to do |
| Model validation | Do the solutions hold in an independent DC power flow (pandapower `rundcpp`)? | `validation/` | SC-DCOPF done (old code); OTS to do |

Tools shared by the cases:

| Folder | What it is |
|---|---|
| `model/` | The single source of the formulation (SC-DCOPF and OTS-SC-DCOPF). *(being written)* |
| `heuristics/` | Sequential sensitivity-based switching heuristic (Fuller 2012, Ruiz 2012), used as MILP warm start. `heuristics/benchmark/`: the old MILP K sweep (λ = 1, reduced list), used to validate the heuristic. |
| `preprocessing/` | Raw data → `processed/`, and the single-line diagram. |
| `tests/` | Reference checks every change must pass. *(being written)* |

Data and outputs:

| Folder | What it is |
|---|---|
| `data/` | Raw input data (MATPOWER case118, SCUC/StarGenLite, SIN). Never written by the code. |
| `processed/<source>/` | Clean tables read by every model (`gens`, `loads`, `branches`, `system_meta`). |
| `<case>/results/` | Results of each run (`summary.csv`, `dispatch.csv`, `line_loading.csv`, `switching.csv`, `angles.csv`). Layout of the new runs: defined with the `model/` package. |
| `figures/` | Figures used in the thesis. |
| `old/` | Superseded code and results, kept for reference. |

Notes and task list: `RESULTS_NOTES.md` (results and interpretation),
`reference/RESULTS_NOTES.md` (reference case, old runs), `TODO.md` (task list, in Portuguese).

## Reference values

Any change to the model must reproduce these (MATPOWER data, no renewables, K = 0 unless stated):

| List | λ | Case | Cost ($/h) |
|---|---|---|---|
| reduced (194 states) | 1.00 | DCOPF without N-1 | 93,152.38 |
| reduced (194 states) | 1.00 | SC-DCOPF, original topology | 109,681.25 |
| reduced (194 states) | 1.00 | OTS, saved K = 2 topology (lines 64-65, 77-80) | 107,665.95 |
| full (197 states) | 0.50 / 0.60 / 0.70 / 0.80 / 0.85 | SC-DCOPF | 42,326.93 / 52,583.90 / 63,568.33 / 81,401.76 / 91,817.97 |
| full (197 states) | 0.8501 | SC-DCOPF | λ_max (infeasible above) |
| reduced (194 states) | 1.0099 | SC-DCOPF | λ_max (infeasible above) |

The reduced list excludes line 8-5, line 38-65 and the bus-10 generator (`redispatch_with_exclusions`).

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
