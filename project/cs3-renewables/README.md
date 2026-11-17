# CS3 – Renewable siting and curtailment

**Question:** does the location of the renewables (concentrated far from the load × distributed)
change the curtailment and the benefit of switching?

Set-up: load level λ = 0.80 (uniform; N-1 feasible without switching), full contingency list.
Renewables as in the methodology (`metodologia_tcc_v2.tex`): cost 0 (no tie-break), 0 ≤ P_r,c ≤ Ḡ_r,
participation factor α = 0 (the conventional units cover any loss, including the loss of a
renewable plant, which is a generator contingency), curtailment C = Σ_r (Ḡ_r − P_r,0), total only.

## Scenarios (`scenarios/<name>.csv`: columns `bus`, `share`)

| Scenario | Buses | Why |
|---|---|---|
| `concentrated` | 104, 106, 107, 110 (equal split) | meshed buses of the far south-east, top of the electrical-distance ranking (`electrical_distance.py`); radial buses (87, 111, 112, 117, 10) excluded |
| `distributed` | 10, 31, 46, 70, 87, 103, 111 (equal split) | locations of Ruiz et al. (2012) |

Penetration = share of the load served: total available = penetration × λ × nominal load
(10% / 20% / 30% at λ = 0.80 = 339 / 679 / 1,018 MW). The split among buses (equal or by line
capacity) gives the same result (differences below 0.4 MW of curtailment and 4 $/h at 20% and
30%): the curtailment comes from the export limit of the south-east region, not from one bus, so
the split is equal.

## Commands (from `project/`)

```
python cs3-renewables/electrical_distance.py           # ranking of the buses by distance to the load
python cs3-renewables/run_scenarios.py                 # K = 0: unconstrained / DCOPF / SC-DCOPF per scenario and level
# any script of the project takes --renewables <scenario> --penetration <share>, e.g.
python heuristics/sequential.py --load-factor 0.80 --renewables concentrated --penetration 0.20 --out-root cs3-renewables/results
# curtailment by type (energy / congestion / security) for every saved topology of a case -> decomposition.csv
python cs3-renewables/decompose.py --renewables concentrated --penetration 0.30
# binding flow limits, duals, interconnection flows and renewable output per bus on one topology -> diagnostics/
python cs3-renewables/binding_constraints.py --renewables concentrated --penetration 0.30
python cs3-renewables/binding_constraints.py --renewables concentrated --penetration 0.30 --topology heuristic/TD/K10
```

Results go to `lambda0.800_ren-<scenario>_p<pct>/` folders.

## Results without switching (K = 0, λ = 0.80, 2026-11-16)

`results/matpower/redispatch_only/summary_scenarios_lambda0.800.csv`:

| Scenario | Level | Unconstrained ($/h) | DCOPF ($/h, curtailment) | SC-DCOPF ($/h, curtailment) |
|---|---|---|---|---|
| none | 0 | 71,283 | 71,332 (0) | 81,402 (0) |
| concentrated | 10% | 62,804 | 67,019 (0) | 77,104 (0) |
| concentrated | 20% | 54,366 | 64,288 (108 MW) | 74,837 (159 MW, 23%) |
| concentrated | 30% | 46,016 | 63,801 (405 MW) | 74,664 (485 MW, 48%) |
| distributed | 10% | 62,804 | 63,999 (0) | 73,337 (0) |
| distributed | 20% | 54,366 | 56,826 (0) | 65,610 (0) |
| distributed | 30% | 46,016 | 49,998 (4 MW) | 58,195 (4 MW) |

- No curtailment without network in any case: every curtailment above is caused by the network or
  by N-1 security.
- Concentrated: most curtailment comes from the base-case network (the DCOPF already curtails), and
  the base-case network cost grows fast (DCOPF − unconstrained: 4,215 → 9,922 → 17,784 $/h);
  distributed: 1,195 → 2,460 → 3,981 $/h. The security premium is similar (~10,000 $/h) in all cases.
