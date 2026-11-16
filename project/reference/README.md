# Reference case: SC-DCOPF on the original topology (K = 0)

**Question:** how much does N-1 security cost without switching (the *security premium*), and
which contingencies cannot be covered at all?

**New structure (2026-11-16):** full contingency list (197 states) and load level λ. To do: per λ
(0.50 … 0.85), the unconstrained dispatch cost (no network), DCOPF and SC-DCOPF, the base-case
network cost (DCOPF − unconstrained dispatch) and the security premium (SC-DCOPF − DCOPF). The results below
are the old runs at λ = 1, where the full list is infeasible and three contingencies were excluded.

## Load-level grid (full list, 197 states)

`results/matpower/redispatch_only/summary_lambda.csv` (one row per λ) and, per λ,
`contingencies/lambda<λ>/K0/` (SC-DCOPF) and `basecase/lambda<λ>/K0/` (DCOPF). Command (from `project/`):

```
python reference/run_reference.py                               # default grid, ~30 s
python reference/run_reference.py --lambdas 0.80 0.82 0.84      # other load levels
```

| λ | Load (MW) | Unconstrained | DCOPF | SC-DCOPF | Network cost | Security premium |
|---|---|---|---|---|---|---|
| 0.50 | 2,121 | 39,753.76 | 40,807.42 | 42,326.93 | 1,053.66 | 1,519.51 (3.7%) |
| 0.60 | 2,545 | 50,191.25 | 50,946.08 | 52,583.90 | 754.83 | 1,637.82 (3.2%) |
| 0.70 | 2,969 | 60,692.25 | 61,100.86 | 63,568.33 | 408.61 | 2,467.47 (4.0%) |
| 0.75 | 3,182 | 65,983.87 | 66,200.04 | 71,777.20 | 216.17 | 5,577.16 (8.4%) |
| 0.80 | 3,394 | 71,282.86 | 71,332.19 | 81,401.76 | 49.33 | 10,069.57 (14.1%) |
| 0.85 | 3,606 | 76,636.63 | 76,700.08 | 91,817.97 | 63.45 | 15,117.89 (19.7%) |
| 0.90 / 0.95 / 1.00 | 3,818 / 4,030 / 4,242 | 82,100.00 / 87,563.36 / 93,026.73 | 82,111.43 / 87,599.60 / 93,152.38 | infeasible | – | – |

Costs in $/h. λ_max = 0.85013 (3,606 MW). Network cost = DCOPF − unconstrained dispatch;
security premium = SC-DCOPF − DCOPF.

- The security premium jumps between λ = 0.70 and 0.75 and then grows fast (4% → 8% → 14% → 20%).
- The base-case network cost does the opposite (1,054 → ~50 $/h): at high load almost all the extra
  cost comes from security.
- No line is at its limit in the base case of the SC-DCOPF at any λ (the DCOPF has 2): the binding
  limits are in the contingency states (3–4 lines, 8 at λ = 0.85).

## Old results at λ = 1 (MATPOWER data, old notebook)

`results/matpower/<formulation>/<config>/lambda1.000/`, where `<config>` is the set of
contingencies (`basecase` = none, `cont_gen` = generators only, `cont_trans` = branches only,
`contingencies` = both):

| `<formulation>` / `<config>` | States | Cost ($/h) |
|---|---|---|
| `redispatch_with_exclusions/basecase` (no N-1) | 1 | 93,152.38 |
| `redispatch_with_exclusions/cont_gen` (generator contingencies only) | 19 | 99,253.64 |
| `redispatch_with_exclusions/cont_trans` (line contingencies only) | 176 | 102,020.06 |
| `redispatch_with_exclusions/contingencies` (both) | 194 | **109,681.25** |
| `redispatch_only/*` (full contingency list) | — | infeasible except `basecase` (`iis_summary.csv` in each `lambda1.000/`) |

`redispatch_with_exclusions` excludes line 8-5 (infeasible alone), line 38-65 and the bus-10
generator (infeasible together). Security premium: 109,681.25 − 93,152.38 = **16,528.87 $/h (+17.7%)**.

`results/matpower/vulnerability/lambda1.000/`: each contingency solved in isolation (which ones fail).

Interpretation: `RESULTS_NOTES.md`.

## Code

Old results at λ = 1: `old/pre-reorg-2026-11/sc-dcopf/sc-dcopf.ipynb` (does not run from `old/`;
the `model/` package reproduces them, see `tests/check_reference.py`). Load-level grid:
`run_reference.py` (above).
