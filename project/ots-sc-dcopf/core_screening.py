"""Feasibility screening of the OTS-SC-DCOPF by contingency subsets.

The topology z is shared by every scenario, so the problem restricted to a subset of
scenarios (the "core") is a relaxation of the full one:
- core infeasible for K  ->  full problem infeasible for K (safe to discard K);
- core feasible for K    ->  fix its topology and check every other contingency (one LP
  each). If all pass, the topology is feasible for the full problem (a warm start). If some
  fail, they are added to the core and the core is solved again (constraint generation).

The core starts with the base case plus the contingencies that are infeasible on the full
topology (identified by ../sc-dcopf/vulnerability.ipynb).

Same formulation as ots-sc-dcopf.ipynb ('redispatch_only'): equations (3.9)-(3.16).

Usage (from project/ots-sc-dcopf/):
    python core_screening.py --k-min 1 --k-max 10
    python core_screening.py --k-min 4 --k-max 4 --threads 8
"""

import argparse
import os
import time

import numpy as np
import pandas as pd
import gurobipy as gp
from gurobipy import GRB

# --- data (same layout as the notebook) ---
ROOT   = ".."
SOURCE = "matpower"
PROC   = f"{ROOT}/processed/{SOURCE}"

gens     = pd.read_csv(f"{PROC}/gens.csv")
loads    = pd.read_csv(f"{PROC}/loads.csv")
branches = pd.read_csv(f"{PROC}/branches.csv")
meta     = pd.read_csv(f"{PROC}/system_meta.csv").set_index("key")["value"]

BASE_MVA  = float(meta["base_mva"])
SLACK_BUS = int(meta["slack_bus"])

set_N = loads["bus"].tolist()
set_G = gens["gen_id"].tolist()
set_L = branches["branch_id"].tolist()

par_pd    = dict(zip(loads["bus"],          loads["pd_pu"]))
par_g_bus = dict(zip(gens["gen_id"],        gens["bus"]))
par_pmin  = dict(zip(gens["gen_id"],        gens["pmin_pu"]))
par_pmax  = dict(zip(gens["gen_id"],        gens["pmax_pu"]))
par_cost  = dict(zip(gens["gen_id"],        gens["c1"]))
par_from  = dict(zip(branches["branch_id"], branches["from_bus"]))
par_to    = dict(zip(branches["branch_id"], branches["to_bus"]))
par_x     = dict(zip(branches["branch_id"], branches["x_pu"]))
par_rate  = dict(zip(branches["branch_id"], branches["rate_pu"]))
par_label = dict(zip(branches["branch_id"], branches["label"]))

set_gens_at   = {i: [] for i in set_N}
set_out_lines = {i: [] for i in set_N}
set_in_lines  = {i: [] for i in set_N}
for g in set_G:
    set_gens_at[par_g_bus[g]].append(g)
for l in set_L:
    set_out_lines[par_from[l]].append(l)
    set_in_lines[par_to[l]].append(l)

set_LS = branches.loc[~branches["is_bridge"], "branch_id"].tolist()   # switchable (non-radial)

# --- scenarios: same ids as the notebook with INCLUDE_CT = INCLUDE_CG = True ---
scenarios = [{"id": 0, "type": "base", "out_line": None, "out_gen": None, "desc": "base case"}]
for l in set_LS:
    scenarios.append({"id": len(scenarios), "type": "line", "out_line": l, "out_gen": None,
                      "desc": f"line {l} ({par_label[l]}) out"})
for g in set_G:
    scenarios.append({"id": len(scenarios), "type": "gen", "out_line": None, "out_gen": g,
                      "desc": f"gen {g} (bus {par_g_bus[g]}) out"})
scen  = {s["id"]: s for s in scenarios}
set_C = list(scen)

RHO_GEN, RHO_LINE = 1e-2, 1e-3
par_rho = {c: RHO_GEN if scen[c]["type"] == "gen" else RHO_LINE for c in set_C if c != 0}
par_rho[0] = 1.0 - sum(par_rho.values())

DTHETA_MAX = np.pi / 2
par_M = {l: DTHETA_MAX / par_x[l] for l in set_L}

# Contingencies infeasible on the full topology (vulnerability.ipynb): the initial core.
HARD = [("line", 7), ("line", 50), ("gen", 0)]


def scenario_id(kind, element):
    key = "out_line" if kind == "line" else "out_gen"
    return next(s["id"] for s in scenarios if s["type"] == kind and s[key] == element)


def line_on(l, c):
    return 0 if scen[c]["out_line"] == l else 1


def gen_on(g, c):
    return 0 if scen[c]["out_gen"] == g else 1


def build_model(scen_ids, max_switched=None, z_fixed=None, env=None):
    """OTS-SC-DCOPF over scen_ids. z_fixed = {branch: 0/1} turns it into an LP."""
    model = gp.Model(env=env)

    var_p     = {(g, c): model.addVar(lb=-GRB.INFINITY) for g in set_G for c in scen_ids}
    var_f     = {(l, c): model.addVar(lb=-GRB.INFINITY) for l in set_L for c in scen_ids}
    var_theta = {(i, c): model.addVar(lb=-GRB.INFINITY) for i in set_N for c in scen_ids}
    if z_fixed is None:
        var_z = {l: model.addVar(vtype=GRB.BINARY, name=f"z[{l}]") for l in set_L}
        for l in set_L:
            if l not in set_LS:
                model.addConstr(var_z[l] == 1)
        if max_switched is not None:
            model.addConstr(gp.quicksum(1 - var_z[l] for l in set_LS) <= max_switched)
    else:
        var_z = z_fixed   # constants: the big-M terms below become plain numbers

    model.setObjective(gp.quicksum(par_rho[c] * par_cost[g] * var_p[(g, c)] * BASE_MVA
                                   for g in set_G for c in scen_ids), GRB.MINIMIZE)

    for c in scen_ids:
        for i in set_N:                                                       # (3.9)
            model.addConstr(gp.quicksum(var_p[(g, c)] for g in set_gens_at[i]) - par_pd[i]
                            == gp.quicksum(var_f[(l, c)] for l in set_out_lines[i])
                            - gp.quicksum(var_f[(l, c)] for l in set_in_lines[i]))
        for g in set_G:                                                       # (3.10)
            model.addConstr(var_p[(g, c)] >= par_pmin[g] * gen_on(g, c))
            model.addConstr(var_p[(g, c)] <= par_pmax[g] * gen_on(g, c))
        for l in set_L:
            i, j = par_from[l], par_to[l]
            model.addConstr(var_f[(l, c)] >= -par_rate[l] * var_z[l])        # (3.12)
            model.addConstr(var_f[(l, c)] <=  par_rate[l] * var_z[l])
            if line_on(l, c) == 1:
                dc_law = var_f[(l, c)] - (1.0 / par_x[l]) * (var_theta[(i, c)] - var_theta[(j, c)])
                model.addConstr(dc_law + par_M[l] * (1 - var_z[l]) >= 0)      # (3.13)
                model.addConstr(dc_law - par_M[l] * (1 - var_z[l]) <= 0)      # (3.14)
            else:
                model.addConstr(var_f[(l, c)] == 0.0)                         # (3.15)
        model.addConstr(var_theta[(SLACK_BUS, c)] == 0.0)                     # (3.16)

    return model, var_z


def failing_contingencies(z_fixed, env):
    """Solve one LP per scenario with the topology fixed; return the infeasible ones."""
    failing = []
    for c in set_C:
        model, _ = build_model([c], z_fixed=z_fixed, env=env)
        model.optimize()
        if model.status != GRB.OPTIMAL:
            failing.append(c)
        model.dispose()
    return failing


def screen_k(K, core, args, env, out_dir):
    """Constraint generation for one K. Returns a result row for the summary."""
    core = list(core)
    t0 = time.time()
    for it in range(1, args.max_iter + 1):
        model, var_z = build_model(core, max_switched=K, env=env)
        model.setParam("OutputFlag", 1)                        # always write the log file...
        model.setParam("LogToConsole", 1 if args.verbose else 0)   # ...console only if asked
        log_file = f"{out_dir}/K{K}_it{it}.log"
        if os.path.exists(log_file):
            os.remove(log_file)   # Gurobi appends to an existing log; keep only this run
        model.setParam("LogFile", log_file)
        model.setParam("MIPGap", args.mip_gap)
        model.setParam("TimeLimit", args.time_limit)
        model.setParam("MIPFocus", 1)
        model.setParam("DualReductions", 0)   # INFEASIBLE instead of INF_OR_UNBD
        if args.threads:
            model.setParam("Threads", args.threads)
        model.optimize()

        print(f"  K={K} it={it}: core={len(core)} scenarios, status={model.status}, "
              f"{model.Runtime:.0f}s", flush=True)

        row = {"K": K, "iterations": it, "core_size": len(core),
               "core": ";".join(scen[c]["desc"] for c in core)}

        if model.status == GRB.INFEASIBLE:
            return {**row, "verdict": "infeasible", "time_s": round(time.time() - t0, 1)}
        if model.SolCount == 0:
            return {**row, "verdict": "unknown (time limit, no solution)",
                    "time_s": round(time.time() - t0, 1)}

        z = {l: int(round(var_z[l].X)) for l in set_L}
        core_cost, core_bound = model.ObjVal, model.ObjBound
        model.dispose()

        failing = failing_contingencies(z, env)
        print(f"         topology opens {[par_label[l] for l in set_L if z[l] == 0]}, "
              f"{len(failing)} contingencies fail on it", flush=True)
        if not failing:
            pd.DataFrame({"branch_id": set_L, "label": [par_label[l] for l in set_L],
                          "z": [z[l] for l in set_L]}).to_csv(f"{out_dir}/K{K}_topology.csv",
                                                                index=False)
            return {**row, "verdict": "feasible (full N-1)",
                    "opened": ";".join(par_label[l] for l in set_L if z[l] == 0),
                    "core_cost": round(core_cost, 2), "core_bound": round(core_bound, 2),
                    "time_s": round(time.time() - t0, 1)}
        core += [c for c in failing if c not in core]

    return {**row, "verdict": f"undecided after {args.max_iter} iterations",
            "time_s": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--k-min", type=int, default=1)
    ap.add_argument("--k-max", type=int, default=10)
    ap.add_argument("--time-limit", type=float, default=600, help="per core solve [s]")
    ap.add_argument("--mip-gap", type=float, default=1e-2)
    ap.add_argument("--threads", type=int, default=0, help="0 = all cores")
    ap.add_argument("--max-iter", type=int, default=10)
    ap.add_argument("--stop-at-first", action="store_true",
                    help="stop the sweep at the first K feasible for the full N-1 set")
    ap.add_argument("--verbose", action="store_true", help="also print the Gurobi logs")
    ap.add_argument("--core-from", metavar="CSV",
                    help="start from the final core of a previous run (its summary CSV)...")
    ap.add_argument("--core-k", type=int, help="...taken from the row of this K")
    args = ap.parse_args()

    out_dir = f"results/{SOURCE}/redispatch_only/screening"
    os.makedirs(out_dir, exist_ok=True)

    # Losing a generator cannot be fixed by switching if the remaining capacity is too small.
    total_load = sum(par_pd.values())
    for g in set_G:
        if sum(par_pmax.values()) - par_pmax[g] < total_load:
            print(f"WARNING: without gen {g} the capacity is below the load: "
                  f"infeasible for every K.")

    if args.core_from:
        # reuse the contingencies that a previous run found to be binding
        prev     = pd.read_csv(args.core_from).set_index("K")
        id_of    = {s["desc"]: s["id"] for s in scenarios}
        core     = [id_of[d] for d in prev.loc[args.core_k, "core"].split(";")]
    else:
        core = [0] + [scenario_id(kind, e) for kind, e in HARD]
    print(f"Initial core: {[scen[c]['desc'] for c in core]}")

    env  = gp.Env(params={"OutputFlag": 0})
    rows = []
    for K in range(args.k_min, args.k_max + 1):
        rows.append(screen_k(K, core, args, env, out_dir))
        print(f"K={K}: {rows[-1]['verdict']}", flush=True)
        pd.DataFrame(rows).to_csv(f"{out_dir}/summary_K{args.k_min}-{args.k_max}.csv",
                                  index=False)
        if args.stop_at_first and rows[-1]["verdict"].startswith("feasible"):
            break

    print(f"\nSaved to {out_dir}/")
    print(pd.DataFrame(rows)[["K", "verdict", "iterations", "core_size", "time_s"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
