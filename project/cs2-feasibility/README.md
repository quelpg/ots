# CS2 – Recovery of N-1 feasibility above λ_max

**Question:** with the full contingency list (197 states), the original topology is N-1 secure
only up to λ_max = 0.850. Above it, can switching make N-1 feasible again, with how many open
lines, and up to which load?

Why this range (`../reference/README.md`, `load_limits.py`): between λ = 0.850 and 0.992 unlimited
transmission capacity would restore N-1 (the infeasibility is caused by transmission limits);
above 0.992 not even that helps. The minimum overload at λ = 0.86 is 12.6 MW (2 states), at 0.88
39.5 MW, always worst on line 23-25 with 26-30 out.

## Method

1. **Heuristic, two phases** (`../heuristics/sequential.py`, same command as CS1): if the original
   topology is infeasible, it starts with the **violation phase** – LP with overload slacks on the
   flow limits (minimum total overload, equal weights); the criteria use its duals; an opening is
   kept if the overload decreases. When the overload reaches zero, the LP **without slacks** proves
   N-1 feasibility and the **cost phase** (as in CS1) continues up to the maximum K. Openings that
   isolate load or generation in any contingency are rejected.
2. **Maximum load of each feasible topology** (`topology_lambda_max.py`): max-λ LP with the topology
   fixed and every limit.
3. **MILP** (to run): minimum number of open lines (K_min) with warm start from the first feasible
   heuristic topology; then the cost K sweep from K_min (`../cs1-cost/sweep_k.py` with this λ and
   `--out-root cs2-feasibility/results`). Where the heuristic does not reach feasibility (λ = 0.88),
   a MILP minimizing the overload with K limited would say whether any topology does.

## Commands (from `project/`)

```
python heuristics/sequential.py --load-factor 0.86 --max-open 20 --max-lp 100 --out-root cs2-feasibility/results
python heuristics/sequential.py --load-factor 0.88 --max-open 20 --max-lp 100 --out-root cs2-feasibility/results
python cs2-feasibility/topology_lambda_max.py --load-factor 0.86
```

## Results (2026-11-16)

`results/matpower/redispatch_only/contingencies/lambda<λ>/heuristic/` (`path_<criterion>.csv`,
`summary_criteria.csv`, feasible topologies in `<criterion>/K<n>/`) and `topology_lambda_max.csv`.

**λ = 0.86** (overload 12.6 MW at K = 0): N-1 recovered.

| Criterion | Feasible from | Cost at K = 10 ($/h) |
|---|---|---|
| LP (Fuller) | K = 5 | 94,673 |
| PW | K = 5 | 92,424 |
| TD | K = 6 | **90,470** |
| PD | K = 12 | – |

At λ = 0.86 with 10 open lines (TD) the cost is lower than without switching at λ = 0.85 (91,818).

**λ = 0.88** (overload 39.5 MW): no criterion reaches feasibility in 20 openings; minimum overload
10.9 MW (TD), 11.7 (PD), 18.1 (PW), 19.0 (LP).

**Maximum N-1 load with switching** (topologies found at λ = 0.86):

| Open lines | Best topology | λ_max | Load (MW) |
|---|---|---|---|
| 0 | original | 0.850 | 3,606 |
| 5 | PW | 0.864 | 3,665 |
| 8 | TD | 0.869 | 3,684 |
| 10 | TD | **0.875** | **3,713** |
| 11–17 | TD | ~0.875 | (saturates) |

With 10 open lines (15-17, 34-37, 47-49, 49-51, 49-54, 65-66, 49-69, 68-69, 69-77, 77-80) switching
extends the maximum N-1 load by 107 MW (+3%). These topologies were chosen to lower the cost at
λ = 0.86, not to maximize the load, so the true limit with switching may be a little higher.

## Maximum load per K: heuristic in load mode (2026-11-16)

`python heuristics/sequential.py --mode load --max-open 10 --out-root cs2-feasibility/results` –
max-λ LP at each step (written as min −λ, so the criteria keep their sign convention); an opening
is kept if λ_max increases. Results in `results/matpower/redispatch_only/contingencies/max_load/heuristic/`.

| K | Best criterion | λ_max | Load (MW) |
|---|---|---|---|
| 0 | – | 0.8501 | 3,606 |
| 1 | LP | 0.8539 | 3,622 |
| 2 | LP | 0.8571 | 3,636 |
| 4 | PW | 0.8590 | 3,644 |
| 5 | PW | 0.8640 | 3,665 |
| 8 | TD | 0.8692 | 3,687 |
| 9 | TD | 0.8754 | 3,713 |
| 10 | TD | **0.8765** | **3,718** |

The load-mode criteria reach the same or slightly higher λ_max than the topologies chosen for cost
(0.8753 at K = 10), and give the whole curve from K = 1 (the cost/violation runs only had feasible
topologies from K = 5 at λ = 0.86). Next: MILP max λ for K = 1..10 with warm start from these
topologies (`python model/run_ots.py --objective max_load --K <k> --warm-start-dir
cs2-feasibility/results/matpower/redispatch_only/contingencies/max_load/heuristic/TD ...`).

## Old results (λ = 1)

`results/matpower/redispatch_only/screening/`: core screening at λ = 1 (MILP on a 4-state core +
IIS + constraint generation). K = 1, 2, 3 are infeasible on the core (a relaxation): **no topology
with K ≤ 3 is feasible at λ = 1**. K = 4–7: time limit without a solution. Minimum-switching run of
2026-11-13: undecided. Produced by `old/pre-reorg-2026-11/ots-sc-dcopf/full-ct-feasibility/`.
