# Code before the reorganization of 2026-11-16

Kept unchanged for reference while the model is rewritten as a Python package (`../../model/`).
These files produced every result saved so far; the results themselves were moved to the
study-case folders (`../../reference-k0/`, `../../cs1a-k-sweep/`, `../../cs2-full-n1/`).

**They do not run from here** (relative paths point to the old layout). To run them as they
were, check out the tag `pre-reorg` (`git checkout pre-reorg`, then `git switch -` to come back).

| Old path | What it did | Results now in |
|---|---|---|
| `sc-dcopf/sc-dcopf.ipynb` | SC-DCOPF (K = 0), vulnerability analysis (Section 10) | `reference-k0/results/` |
| `ots-sc-dcopf/ots-sc-dcopf.ipynb` | OTS-SC-DCOPF MILP, one K per run, warm start (§6.1) | `cs1a-k-sweep/results/` |
| `ots-sc-dcopf/sweep_k.py`, `plot_k_sweep.py` | K sweep runner (executes the notebook) and figure | `cs1a-k-sweep/`, `figures/` |
| `ots-sc-dcopf/solution-quality/` | fixed-topology LP check, local search, limiting contingencies (duals) | `cs1a-k-sweep/results/` |
| `ots-sc-dcopf/full-ct-feasibility/` | core screening (`core_screening.py` + notebook; `run_minsw.ipynb` = run of 2026-11-13) | `cs2-full-n1/results/` |
| `validation/scdcopf-pandapower.ipynb` | pandapower validation of the SC-DCOPF dispatch | — |
| `results-legacy/` | OTS runs with the legacy model (2026-11-02): base case only, line contingencies only | — |

What is reused in the new code: the formulation (equations in the notebooks' markdown), the
reference values, and the checks (K = 0, saved K = 2 topology, pandapower comparison).
