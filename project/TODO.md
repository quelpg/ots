# TODO

## IEEE 118-bus - base case

- [x] SC-DCOPF with the revised formulation (base-case cost, F^em = 1.15 F^max,
      preventive coupling, participation factors alpha, theta in +-0.6 rad)
- [x] Vulnerability analysis (Section 10 of `sc-dcopf/sc-dcopf.ipynb`).
      Exclusions: line 8-5 (alone), line 38-65 and generator at bus 10 (joint)
- [x] SC-DCOPF validation with pandapower, a posteriori (194/194 states pass)
- [x] OTS-SC-DCOPF with the revised formulation (K = 0 reproduces the SC-DCOPF)
- [ ] **Analysis A** - OTS `redispatch_with_exclusions`, K = 1..10 (running)
      ```
      cd project/ots-sc-dcopf
      ..\..\venv\Scripts\python.exe -u sweep_k.py --formulation redispatch_with_exclusions --k-min 1 --k-max 10 *> sweep_log.txt
      ```
  - [ ] Cost x K compared with the SC-DCOPF ($109,681.25/h); savings per extra open line;
        share of the security cost (+$16,529/h over the base case) recovered by switching
  - [ ] Which lines open, whether they repeat across K, and which binding limits they relieve
  - [ ] Dispatch changes (which generators gain or lose)
- [ ] **Analysis B** - make the full N-1 set (`redispatch_only`) feasible
  - So far: K <= 3 proven infeasible; K = 4, 5, 6 undecided in 10 min (cost objective)
  - [ ] Add a minimum-switching option to `core_screening.py`: min sum(1 - z) over L^S,
        same constraints, no K limit -> K_min and a feasible topology
  - [ ] Run the OTS (cost objective) at K_min, K_min + 1, ... warm-started from it
  - [ ] Compare with Analysis A at the same K (cost of covering the 3 extra contingencies)
- [ ] **OTS validation** with pandapower, a posteriori (remove the opened lines)
  - [ ] Check connectivity per state and report any island (islanding is unlikely with
        the new model, but still possible in a line-contingency state in principle)
  - [ ] Compare with Hedman et al. (OTS with N-1 on the IEEE 118-bus system): same order of
        magnitude for cost and, mainly, relative savings (%) x number of open lines. The
        formulations and data differ (costs, ratings, contingency set, response model), so
        absolute values are not expected to match; check the paper's case data first
- [ ] **Review all the code written together**: `sc-dcopf.ipynb` (incl. Section 10),
      `scdcopf-pandapower.ipynb`, `ots-sc-dcopf.ipynb`, `core_screening.py`, `sweep_k.py`,
      and what Analysis B / OTS validation add

Notes:
- Do not run two Gurobi jobs at the same time with the default threads (each uses all cores);
  for parallel runs pass `--threads` to `sweep_k.py` so the jobs split the cores.
  The WLS license accepted 10 simultaneous sessions (tested 2026-11-09).
- Run long jobs in your own PowerShell, not inside Claude (they stop if the app closes),
  with Windows sleep set to "Never" while plugged in.

## Renewable scenarios (after the base case)

- [ ] Design two scenarios on the 118-bus system:
  - concentrated: renewable generation far from the load
  - distributed: renewable generation and load spread along the network
- [ ] Modelling decisions
  - [ ] Curtailment metric (e.g. sum_r (P_r^avail - P_r,0), in MW or % of available)
  - [ ] Renewable cost (zero cost makes the LP degenerate: tiny cost or curtailment penalty)
  - [ ] Whether renewables take part in the alpha response (probably not)
- [ ] Run SC-DCOPF and OTS-SC-DCOPF for each scenario, with a few K chosen from the
      Analysis A curve (e.g. K = 0, the knee, the saturation point)
- [ ] Renewable penetration sweep with fixed load (renewables curtailable,
      0 <= P_r <= P_r^avail): cost and curtailment x penetration, with and without OTS
- Main metrics: cost and curtailment

## Results analysis and thesis

- [ ] Consolidate the results of all cases (tables and figures)
- [ ] Write the thesis (results, discussion, conclusions)
