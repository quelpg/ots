# Reference case: SC-DCOPF on the original topology (K = 0)

**Question:** how much does N-1 security cost without switching (the *security premium*), and
which contingencies cannot be covered at all?

## Results (MATPOWER data)

`results/matpower/<formulation>/<config>/`, where `<config>` is the set of contingencies:

| `<formulation>` / `<config>` | States | Cost ($/h) |
|---|---|---|
| `redispatch_with_exclusions/basecase` (no N-1) | 1 | 93,152.38 |
| `redispatch_with_exclusions/cont_gen` (generator contingencies only) | 19 | 99,253.64 |
| `redispatch_with_exclusions/cont_trans` (line contingencies only) | 176 | 102,020.06 |
| `redispatch_with_exclusions/contingencies` (both) | 194 | **109,681.25** |
| `redispatch_only/*` (full contingency list) | — | infeasible except `basecase` (IIS saved) |

`redispatch_with_exclusions` excludes line 8-5 (infeasible alone), line 38-65 and the bus-10
generator (infeasible together). Security premium: 109,681.25 − 93,152.38 = **16,528.87 $/h (+17.7%)**.

`results/matpower/vulnerability/`: each contingency solved in isolation (which ones fail).

Interpretation: `RESULTS_NOTES.md`.

## Code

Produced by `old/pre-reorg-2026-11/sc-dcopf/sc-dcopf.ipynb` (run before the reorganization;
it does not run from `old/`). The new code (`model/` package) must reproduce these values;
commands will be listed here when it is ready.
