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
  - [x] Add a minimum-switching option to `core_screening.py`: min sum(1 - z) over L^S,
        same constraints, no K limit -> K_min and a feasible topology
        (`--min-switching --min-open 4`, optional `--norel-time`)
  - First runs (local, min switching on small cores = base case + the listed contingencies):
    8-5 alone needs 3 open (proven); 38-65, gen bus 10, and both together need 0;
    8-5 + gen bus 10 needs 4 (proven); **8-5 + 38-65 found no solution in 150 s**, nor did
    the 3 together (nor the 4-scenario core in 8 min with NoRel).
  - [x] Pair 8-5 + 38-65 is **feasible** (2026-11-09): greedy local search on the open set
        (min total flow-limit violation, soft F limits) from the 8-5 topology reached 0 with
        7 open: 23-24, 23-32, 25-27, 26-25, 49-50, 65-66, 65-68 (exact LP: OPTIMAL,
        base cost $106,779.94/h on that core). Not proven minimal (lower bound 3, from 8-5).
        Why it was hard: with all closed, 8-5 out overloads 15-17 (flow 17 -> 15) by 0.33 pu,
        0.40 pu with 38-65 too; switching must reroute the supply of the pocket of buses 1-16
  - [ ] **Blocker now: 8-5 + 38-65 + gen bus 10** (the 4-scenario core). That topology fails
        the gen bus 10 and 56-57 contingencies; the local search got stuck at 0.021 pu of
        violation (18 open); the MILP min violation (8 min, 8 threads) found 0.038 pu with
        bound 0. The big-M relaxation is a transport model (no KVL), so its bound never moves
        and Gurobi cannot prove infeasibility this way. N-1 without gen bus 10, from the pair
        topology: 12 contingencies still fail (22-23, 26-30, 56-57, 7 generators); the local
        search is too slow on cores this large. Feasibility of the full N-1 still undecided
  - [x] Added `--max-open N` to `--min-switching` (cut sum(1 - z) <= N): searches only
        topologies with at most N open branches, so the question becomes finite
  - [ ] 4-scenario core with 4 <= open <= 10 (local, 8 threads, 8 min): no solution,
        7,140 nodes explored, 4,134 still open, bound 4 -> undecided. Run long on the cluster:
        ```
        cd project/ots-sc-dcopf
        python -u core_screening.py --min-switching --min-open 4 --max-open 10 --time-limit 7200 --norel-time 600 --threads 16 --max-iter 20 *> minsw_max10_log.txt
        ```
        INFEASIBLE -> no topology with <= 10 open lines covers the full N-1 (proof, as the
        core is a relaxation); feasible -> K_min <= n_open and a topology for the sweep
  - [ ] Find K_min: `python core_screening.py --min-switching --min-open 4 --time-limit 3600
        --norel-time 600` (or prove the full N-1 set infeasible for every topology)
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
