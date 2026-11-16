# heuristics/ – sequential sensitivity-based switching heuristic

References: Fuller, Ramasra & Cha (2012), *Fast heuristics for transmission-line switching*, IEEE
TPWRS 27(3); Ruiz, Foster, Rudkevich & Caramanis (2012), *Tractable transmission topology control
using sensitivity analysis*, IEEE TPWRS 27(3).

Ruiz et al. (2012, *Tractable transmission topology control using sensitivity analysis*, Fig. 1),
with the criteria of Fuller et al. (2012) and Ruiz et al. (2012), adapted to N-1 by summing over
the states. Used to give the MILP a good starting topology (warm start); the MILP stays the
reference and gives the gap.

At each step: solve the SC-DCOPF LP on the current topology (`model/` package, duals included),
rank the closed switchable lines by the criterion, open the best one and re-solve. Keep it if the
LP is feasible and cheaper; otherwise drop the line from the candidates. Lines whose opening islands
the base topology are never candidates.
Islanding criterion: an opening is rejected if, in any branch contingency, it isolates buses with
load or a generator; an isolated empty bus (no load, no generator) is accepted (`--allow-islands`
turns the check off). Every reported solution lists its isolated buses per state.

| Criterion | Formula (line k, states c; f flow, dpi = π_to − π_from, μ flow-limit dual, φ self-PTDF) | Source |
|---|---|---|
| LP0 | f₀·dpi₀ | Fuller α, base case only |
| LP | Σ_c f_c·dpi_c | Fuller α / Ruiz line profit |
| PD | LP / \|f₀\| (only LP < 0) | Ruiz eq. 37, adapted |
| PW | Σ_c f_c·(dpi_c − μ_c) / \|f₀\| | Ruiz eq. 42, adapted |
| TD | Σ_c f_c·(dpi_c − μ_c) / (1 − φ_c) | Ruiz eqs. 28/39, adapted |

More negative = more promising. φ in every state comes from one PTDF of the current topology plus
the single-outage LODF update for the branch out of service, φ_k^(−m) = H_kk + H_km·H_mk / (1 − H_mm)
(LODF: Wood, Wollenberg & Sheblé, *Power Generation, Operation, and Control*, chapter on linear
sensitivity factors; generalized LODF: Güler, Gross & Liu 2007, IEEE TPWRS 22(2)). The test checks
it against one inversion per state.

Observation: in the SC-DCOPF the base-state prices are all equal (no base-case limit is binding;
the congestion comes from the contingency states), so LP0 is always zero and never proposes a line.

## Files

| File | What it is |
|---|---|
| `sequential.py` | the heuristic (command line, `--help`) |
| `benchmark/` | the old MILP K sweep (λ = 1, reduced list), used to validate the heuristic |

## Commands

From `project/`:

```
# benchmark: reduced list, lambda = 1, all criteria, with the MILP cost per K for comparison
python heuristics/sequential.py --formulation redispatch_with_exclusions --out-root heuristics/benchmark/results --milp-dir heuristics/benchmark/results/matpower/redispatch_with_exclusions/contingencies
# CS1: full list, lambda = 0.80
python heuristics/sequential.py --load-factor 0.80 --out-root cs1-cost/results
```

Output: `<out-root>/<source>/<formulation>/<config>/lambda<λ>/heuristic/` with `path_<criterion>.csv`
(one row per accepted opening), `summary_criteria.csv`, `criteria_K0.csv`, `run.log`, and
`<criterion>/K<n>/` (same files as `model/run_ots.py`). To use them as MILP warm start:

```
python model/run_ots.py --load-factor 0.80 --K 6 --time-limit 1800 --out-root cs1-cost/results --warm-start-dir cs1-cost/results/matpower/redispatch_only/contingencies/lambda0.800/heuristic/TD
```

## Validation

- Same criteria (to 1e-8) and same paths (TD, LP) as the first test of 2026-11-15 (HiGHS).
- Benchmark (λ = 1, reduced list), criterion TD: 77-80, 89-92, 64-65, 68-69, 103-105, 103-104,
  15-19, 11-12. K = 8 reaches the MILP cost (106,784.01, same 8 lines); K = 6 (106,816.21) and
  K = 7 (106,788.34) are cheaper than the saved MILP solutions (106,826.95 and 106,822.62).
- `tests/check_reference.py` checks the PTDF update; `--slow` reruns the TD path.
