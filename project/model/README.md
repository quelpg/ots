# model/ – SC-DCOPF and OTS-SC-DCOPF (single source of the formulation)

Formulation transcribed from `old/pre-reorg-2026-11/sc-dcopf/sc-dcopf.ipynb`
and `old/pre-reorg-2026-11/ots-sc-dcopf/ots-sc-dcopf.ipynb` (both notebooks build the same model;
the OTS adds $z$, the big-M and the limit $K$). The package must reproduce their results.

## Formulation

Sets: buses $\mathcal{N}$ (118), generators $\mathcal{G}$ (19), branches $\mathcal{L}$ (186),
switchable branches $\mathcal{L}^S$ (177 non-radial; the 9 radial ones are fixed closed),
states $\mathcal{C} = \{0\} \cup \mathcal{C}_T \cup \mathcal{C}_G$.
Per unit on $S_{base}$ = 100 MVA. Slack (reference) bus 69.

| # | Name (constraint prefix) | Equation | For | Notebook |
|---|---|---|---|---|
| obj | objective | $\min \sum_g c_g P_{g,0} S_{base}$ (base case only, linear cost `c1`) | – | §5 |
| (3.9) | balance `bal` | $\sum_{g\in\mathcal{G}_i} P_{g,c} - \lambda P_{d,i} = \sum_{\Omega_i^+} f_{ij,c} - \sum_{\Omega_i^-} f_{ji,c}$ | $i, c$ | §6 |
| (3.10) | generator limits `pmin`/`pmax` | $P_g^{\min} N1_{g,c} \le P_{g,c} \le P_g^{\max} N1_{g,c}$ | $g, c$ | §6 |
| – | thermal limits `fmin`/`fmax` | $\lvert f_{ij,0}\rvert \le F^{\max}_{ij} z_{ij}$; $\lvert f_{ij,c}\rvert \le F^{em}_{ij} z_{ij}$ ($c \ne 0$), $F^{em} = 1.15\,F^{\max}$ | $l, c$ | §6 |
| (3.13)/(3.14) | DC law, big-M `dcflow_lo`/`dcflow_hi` | $\lvert f_{ij,c} - (\theta_{i,c}-\theta_{j,c})/x_{ij}\rvert \le M_{ij}(1-z_{ij})$, $M_{ij} = (\theta^{\max}-\theta^{\min})/x_{ij}$ | $l$ in service in $c$ | §6 |
| (3.15) | branch out `dcflow_off` | $f_{ij,c} = 0$, no angle coupling | $l$ = contingency of $c$ | §6 |
| – | preventive coupling `couple` | $P_{g,c} = P_{g,0}$ | $g$, $c \in \mathcal{C}_T$ | §6 |
| – | generator response `resp` | $P_{g,c} = P_{g,0} + \alpha_{g,c} P_{k,0}$, $\alpha_{g,c} = P_g^{\max} / \sum_h N1_{h,c} P_h^{\max}$ ($k$ = failed unit) | $g$ in service, $c \in \mathcal{C}_G$ | §3.1, §6 |
| – | angle limits `thmin`/`thmax` | $-0.6 \le \theta_{i,c} \le 0.6$ rad | $i, c$ | §6 |
| (3.16) | reference `ref` | $\theta_{69,c} = 0$ | $c$ | §6 |
| (3.11) | switching | $z_l \in \{0,1\}$ for $l \in \mathcal{L}^S$, $z_l = 1$ otherwise (`zfix`) | $l$ | §4 |
| – | switching limit `max_switched` | $\sum_{\mathcal{L}^S} (1 - z_l) \le K$ | – | §4 |

$z$ has no scenario index (preventive switching). $\mathcal{C}_T$ = non-radial branches of the
original topology. $K = 0$ (or $z$ fixed to 1) is the SC-DCOPF.

### Load level λ

Every load is scaled by λ ($P_{d,i} = \lambda P_{d,i}^{nom}$); generation is not scaled. λ = 1 is the
nominal load (4,242 MW). Objective modes: `cost` (above); `max_load` (λ becomes a variable and
the LP maximizes it: the highest load a topology supports under N-1); `min_switching` (MILP:
minimize the number of open lines, $\sum_{\mathcal{L}^S}(1-z_l)$, at a fixed λ, i.e. $K_{\min}$, for CS2).

### Cost layers (reference case, per λ)


Unconstrained dispatch (`unconstrained_dispatch_cost`: no network, merit order), DCOPF (base case
with the network, `contingencies="none"`), SC-DCOPF (all states). Base-case network cost =
DCOPF − unconstrained dispatch; security premium = SC-DCOPF − DCOPF.

### Contingency sets

| `formulation` | Excluded | States (`contingencies="all"`) |
|---|---|---|
| `redispatch_only` (**default**, "full list") | none | 197 = 1 + 177 non-radial branches + 19 generators |
| `redispatch_with_exclusions` ("reduced list", heuristic benchmark only) | line 7 (8-5), line 95 (38-65), generator 0 (bus 10) | 194 |

The 19 generators are the units with Pmax > 0; the other 35 MATPOWER units are synchronous
condensers, dropped by the pre-processing.

Renewables (CS3, later): set ℛ with zero cost and availability limit, α = 0, loss of a renewable
plant in $\mathcal{C}_G$. Without a renewable
scenario the model is exactly the one above.

`contingencies` (folder name in `results/`): `none` → `basecase`, `lines` → `cont_trans`,
`gens` → `cont_gen`, `all` → `contingencies`. State order: base, then lines (by branch id),
then generators (by gen id), as in the notebooks.

### Solver settings (MILP)

`MIPGap = 1e-4`, `TimeLimit`, `MIPFocus = 1`, `NoRelHeurTime`, `Cuts = 1` (as in the K sweep).
`DualReductions = 0` only for LPs (so an infeasible LP is reported as INFEASIBLE, not
INF_OR_UNBD); the MILP keeps the default (1), which the sweep used.
Warm start: only $z$ is given (`Start`); Gurobi completes the rest.

## Printed output (console + `run.log` in the results folder)

| Notebook section | Printed by the package |
|---|---|
| §1–2 data and sets | source, base MVA, slack bus, number of buses/generators/branches, total load |
| §3 states | formulation, excluded elements (with labels), $\lvert\mathcal{C}_T\rvert$, $\lvert\mathcal{C}_G\rvert$, $\lvert\mathcal{C}\rvert$; check $\sum \alpha = 1$ |
| §3.2 big-M, solver | $\theta$ limits, range of $M_{ij}$, solver parameters |
| §4 model | $\lvert\mathcal{L}^S\rvert$, radial branches fixed closed (labels), $K$; model size (rows, columns, binaries); build time |
| §6.1 warm start | source folder and cost of the start, open branches (labels) |
| §7 solve | Gurobi log (console and `gurobi.log`) |
| §8 results | status, cost, best bound, gap, total load and generation, number of states, $K$, open lines (labels), active generators table |
| §8.1 connectivity | isolated buses in the base topology **and in every state** (new) |
| §9 export | files written and folder |
| §10 vulnerability | contingencies infeasible alone / jointly, accepted set and its cost |

## Files

| File | What it does | Old notebook |
|---|---|---|
| `data.py` | `load_system(source)`: reads `processed/<source>/` into a `System` (arrays by position) | §1–2 |
| `states.py` | `build_states(system, formulation, contingencies)`, `participation_factors` | §3 |
| `build.py` | `OTSModel`: built once; `fix_topology(z)` / `open_lines(ids)` (LP), `free_topology(K)` (MILP), `set_load_factor(λ)`, `set_objective('cost' \| 'max_load' \| 'min_switching')`, `set_min_open(n)`, `warm_start(ids)`, `solve(**gurobi_params)`. `unconstrained_dispatch_cost(system, λ)` | §3.2–7 |
| `solution.py` | `read_solution` (with duals for LPs), `report` (printed block), `export` (CSV files), islanding check in every state, `get_logger` (console + `run.log`), warm-start search | §6.1, §8–9 |
| `run_ots.py` | command line: one case | the whole notebook |

The model is built with Gurobi's matrix API (one block per state): ~1 s to build and ~1 s per LP
for 194 states. Changing the topology, K or λ only changes bounds/right-hand sides.

## Commands

From `project/` (see `python model/run_ots.py --help` for every option):

```
# SC-DCOPF on the original topology, full list, lambda = 0.85
python model/run_ots.py --load-factor 0.85 --out-root reference/results
# OTS MILP, K = 3, 30 min, warm start from the cheapest saved K' <= 3 (same lambda folder)
python model/run_ots.py --load-factor 0.85 --K 3 --time-limit 1800 --out-root cs1-cost/results
# LP on a fixed topology (open 64-65 and 77-80), reduced list, lambda = 1
python model/run_ots.py --formulation redispatch_with_exclusions --open 96 122 --out-root <folder>
# maximum load factor of the original topology under N-1
python model/run_ots.py --objective max_load --out-root reference/results
# K_min at lambda = 0.90: fewest open lines that make N-1 feasible (MILP), warm start from a folder
python model/run_ots.py --objective min_switching --load-factor 0.90 --time-limit 3600 --warm-start <result folder> --out-root cs2-feasibility/results
```

Output: `<out-root>/<source>/<formulation>/<config>/lambda<λ>/<K0 | K<k> | open_<ids>>/` with
`summary.csv`, `dispatch.csv`, `line_loading.csv`, `angles.csv`, `switching.csv` (same columns as
the old notebooks), `run.log` (everything printed) and `gurobi.log`.

Reference checks (run after any change): `python tests/check_reference.py` (~2 min),
`--slow` adds the brute force K = 1 (~5 min).

From Python:

```python
from model.data import load_system
from model.states import build_states
from model.build import OTSModel
s = load_system()
m = OTSModel(s, build_states(s, "redispatch_only"), load_factor=0.85)
m.solve(); print(m.m.ObjVal)              # 91,817.97
m.free_topology(K=3); m.solve(TimeLimit=1800)
```
