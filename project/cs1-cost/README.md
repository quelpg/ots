# CS1 – Cost reduction under N-1 security (λ ≤ λ_max)

**Question:** at load levels where the original topology is N-1 secure (λ ≤ λ_max = 0.850, full
contingency list, 197 states), how much does preventive switching reduce the operating cost, and
with how many open lines (K)?

Load levels (chosen from the reference grid, `../reference/README.md`): **λ = 0.70** (security
premium 4%, little to recover), **0.80** (14%) and **0.85** (20%, close to the limit).

## Steps and commands

From `project/`, in your own PowerShell (the MILP runs take hours):

```
# 1. heuristic, five criteria (minutes per lambda; gives the warm starts)
python heuristics/sequential.py --load-factor 0.70 --out-root cs1-cost/results
python heuristics/sequential.py --load-factor 0.80 --out-root cs1-cost/results
python heuristics/sequential.py --load-factor 0.85 --out-root cs1-cost/results

# 2. MILP K sweep with warm start (30 min per K): one lambda at a time
python cs1-cost/sweep_k.py --load-factor 0.70 --k-min 1 --k-max 8  --time-limit 1800 *> cs1-cost/sweep_0.70.log
python cs1-cost/sweep_k.py --load-factor 0.80 --k-min 1 --k-max 10 --time-limit 1800 *> cs1-cost/sweep_0.80.log
python cs1-cost/sweep_k.py --load-factor 0.85 --k-min 1 --k-max 10 --time-limit 1800 *> cs1-cost/sweep_0.85.log
```

(`*>` sends everything to the log file in PowerShell; drop it to see the output in the console.
`python cs1-cost/sweep_k.py --help` lists every option, e.g. `--threads`.)

For each K the sweep takes as warm start the cheapest saved topology with K' ≤ K among its own
results (chained) and the heuristic results of every criterion. The NoRel heuristic is off by
default (the warm start replaces it).

## Results

`results/matpower/redispatch_only/contingencies/lambda<λ>/`:

| File / folder | What it is |
|---|---|
| `heuristic/path_<criterion>.csv`, `summary_criteria.csv` | heuristic path per criterion (cost per accepted opening) |
| `heuristic/<criterion>/K<n>/` | heuristic topologies (warm starts) |
| `K<k>/` | MILP solution per K (summary, dispatch, line loading, angles, switching, gurobi.log) |
| `summary_sweep.csv`, `run.log` | MILP sweep: cost, bound, gap, time and warm start per K |

## Heuristic (2026-11-16)

Share of the security premium recovered (best criterion):

| λ | Premium ($/h) | LP (Fuller) | PD | PW | TD | Saturation |
|---|---|---|---|---|---|---|
| 0.70 | 2,467 | 40% | 40% | 51% | **51%** | K ≈ 6 |
| 0.80 | 10,070 | 15% | 15% | **42%** | 42% | K ≈ 9 (PW), 12 (TD) |
| 0.85 | 15,118 | 6% | 6% | **18%** (K = 10; 21% at K = 14) | 18% (K = 10; 20% at K = 13) | K ≈ 12–14 |

PW and TD (the criteria that use the flow-limit duals μ) are far ahead of LP and PD (prices
only); no criterion islands buses in any contingency at these λ. LP0 never opens a line.
The comparison between criteria is up to K = 10 (the MILP range). At λ = 0.80 and 0.85, PW and
TD were also run up to 20 openings, only to see where the saving saturates (the first 10 steps
are the same: the heuristic is deterministic); LP and PD stopped at 10.
