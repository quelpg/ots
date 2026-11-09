"""Feasibility screening of the OTS-SC-DCOPF by contingency subsets.

The topology z and the base-case dispatch P_g0 are shared by every scenario, so the problem
restricted to a subset of scenarios (the "core", always including the base case) is a
relaxation of the full one:
- core infeasible for K  ->  full problem infeasible for K (safe to discard K);
- core feasible for K    ->  fix its topology and solve the full SC-DCOPF on it (one LP, all
  scenarios together, since they are coupled through P_g0). If it is feasible, the topology
  is feasible for the full problem (a warm start). If not, the scenarios in the IIS of that
  LP are added to the core and the core is solved again (constraint generation).

The core starts with the base case plus the contingencies that make the SC-DCOPF infeasible
on the full topology (vulnerability analysis, Section 10 of ../sc-dcopf/sc-dcopf.ipynb).

Same formulation as ots-sc-dcopf.ipynb.

Minimum-switching mode (--min-switching): same constraint generation, but the core MILP
minimizes the number of open branches, sum(1 - z) over L^S, with no K limit. The result is a
topology feasible for the full N-1 set with n_open branches open, so K_min <= n_open; the bound
of the last core MILP is a lower bound on K_min (the core is a relaxation), so K_min is proven
when both match. The topology is saved as min_switching_topology.csv and as
K<n_open>_topology.csv, which ots-sc-dcopf.ipynb uses as the warm start for K = n_open.

Usage (from project/ots-sc-dcopf/):
    python core_screening.py --k-min 1 --k-max 10
    python core_screening.py --k-min 4 --k-max 4 --threads 8
    python core_screening.py --formulation redispatch_with_exclusions --k-min 1 --k-max 3
    python core_screening.py --min-switching --min-open 4 --time-limit 3600
    python core_screening.py --min-switching --min-open 4 --max-open 10 --time-limit 3600
"""

import argparse
import math
import os
import re
import time

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

# --- same parameters as the notebook (keep them in sync) ---
EMERG_FACTOR = 1.15                                     # F^em = EMERG_FACTOR * F^max
par_rate_em  = {l: EMERG_FACTOR * par_rate[l] for l in set_L}
THETA_MAX    = 0.6                                      # bus angle limits [rad]
THETA_MIN    = -THETA_MAX
par_M        = {l: (THETA_MAX - THETA_MIN) / par_x[l] for l in set_L}

# Contingencies that make the SC-DCOPF infeasible on the full topology (the initial core).
# They are also the exclusions of 'redispatch_with_exclusions'.
HARD = [("line", 7),    # line 8-5    (infeasible alone)
        ("line", 95),   # line 38-65  (joint conflict)
        ("gen", 0)]     # generator at bus 10, 505 MW (joint conflict)

# --- scenarios: same ids as the notebook (base, then lines, then generators) ---
scenarios, scen, set_C = [], {}, []


def set_scenarios(exclude):
    """Build the scenario list for a formulation (exclude = list of ('line'|'gen', id))."""
    global scenarios, scen, set_C
    scenarios = [{"id": 0, "type": "base", "out_line": None, "out_gen": None, "desc": "base case"}]
    for l in set_LS:
        if ("line", l) not in exclude:
            scenarios.append({"id": len(scenarios), "type": "line", "out_line": l, "out_gen": None,
                              "desc": f"line {l} ({par_label[l]}) out"})
    for g in set_G:
        if ("gen", g) not in exclude:
            scenarios.append({"id": len(scenarios), "type": "gen", "out_line": None, "out_gen": g,
                              "desc": f"gen {g} (bus {par_g_bus[g]}) out"})
    scen  = {s["id"]: s for s in scenarios}
    set_C = list(scen)


def scenario_id(kind, element):
    key = "out_line" if kind == "line" else "out_gen"
    return next(s["id"] for s in scenarios if s["type"] == kind and s[key] == element)


def line_on(l, c):
    return 0 if scen[c]["out_line"] == l else 1


def gen_on(g, c):
    return 0 if scen[c]["out_gen"] == g else 1


def build_model(scen_ids, max_switched=None, z_fixed=None, env=None,
                objective="cost", min_open=0):
    """OTS-SC-DCOPF over scen_ids (must include the base case 0).
    z_fixed = {branch: 0/1} turns it into an LP (the SC-DCOPF on that topology).
    objective = 'cost' (base-case generation cost) or 'switching' (number of open branches,
    min sum(1 - z) over L^S); min_open adds the cut sum(1 - z) >= min_open (a proven lower bound)."""
    assert 0 in scen_ids, "the base case is coupled to every scenario: it must be included"
    model = gp.Model(env=env)

    var_p     = {(g, c): model.addVar(lb=-GRB.INFINITY) for g in set_G for c in scen_ids}
    var_f     = {(l, c): model.addVar(lb=-GRB.INFINITY) for l in set_L for c in scen_ids}
    var_theta = {(i, c): model.addVar(lb=-GRB.INFINITY) for i in set_N for c in scen_ids}
    if z_fixed is None:
        var_z = {l: model.addVar(vtype=GRB.BINARY, name=f"z[{l}]") for l in set_L}
        for l in set_L:
            if l not in set_LS:
                model.addConstr(var_z[l] == 1)
        n_open = gp.quicksum(1 - var_z[l] for l in set_LS)
        if max_switched is not None:
            model.addConstr(n_open <= max_switched)
        if min_open:
            model.addConstr(n_open >= min_open)
    else:
        var_z = z_fixed   # constants: the big-M terms below become plain numbers

    if objective == "switching":
        assert z_fixed is None, "the switching objective needs free z"
        model.setObjective(n_open, GRB.MINIMIZE)
    else:   # base-case generation cost
        model.setObjective(gp.quicksum(par_cost[g] * var_p[(g, 0)] * BASE_MVA for g in set_G),
                           GRB.MINIMIZE)

    # constraint names end in ',c]' so the scenarios of an IIS can be read back
    for c in scen_ids:
        kind = scen[c]["type"]
        for i in set_N:                                                       # energy balance
            model.addConstr(gp.quicksum(var_p[(g, c)] for g in set_gens_at[i]) - par_pd[i]
                            == gp.quicksum(var_f[(l, c)] for l in set_out_lines[i])
                            - gp.quicksum(var_f[(l, c)] for l in set_in_lines[i]),
                            name=f"bal[{i},{c}]")
        for g in set_G:                                                       # generator limits
            model.addConstr(var_p[(g, c)] >= par_pmin[g] * gen_on(g, c), name=f"pmin[{g},{c}]")
            model.addConstr(var_p[(g, c)] <= par_pmax[g] * gen_on(g, c), name=f"pmax[{g},{c}]")
        if kind == "line":                                                    # preventive coupling
            for g in set_G:
                model.addConstr(var_p[(g, c)] == var_p[(g, 0)], name=f"couple[{g},{c}]")
        if kind == "gen":                                                     # contingency response
            cap_on = sum(gen_on(h, c) * par_pmax[h] for h in set_G)
            lost = gp.quicksum((1 - gen_on(h, c)) * var_p[(h, 0)] for h in set_G)
            for g in set_G:
                if gen_on(g, c):
                    model.addConstr(var_p[(g, c)] == var_p[(g, 0)] + par_pmax[g] / cap_on * lost,
                                    name=f"resp[{g},{c}]")
        rate = par_rate if c == 0 else par_rate_em                            # F^max / F^em
        for l in set_L:
            i, j = par_from[l], par_to[l]
            model.addConstr(var_f[(l, c)] >= -rate[l] * var_z[l], name=f"fmin[{l},{c}]")
            model.addConstr(var_f[(l, c)] <=  rate[l] * var_z[l], name=f"fmax[{l},{c}]")
            if line_on(l, c) == 1:                                            # big-M DC flow
                dc_law = var_f[(l, c)] - (1.0 / par_x[l]) * (var_theta[(i, c)] - var_theta[(j, c)])
                model.addConstr(dc_law + par_M[l] * (1 - var_z[l]) >= 0, name=f"dcflow_lo[{l},{c}]")
                model.addConstr(dc_law - par_M[l] * (1 - var_z[l]) <= 0, name=f"dcflow_hi[{l},{c}]")
            else:
                model.addConstr(var_f[(l, c)] == 0.0, name=f"dcflow_off[{l},{c}]")
        for i in set_N:                                                       # angle limits
            model.addConstr(var_theta[(i, c)] >= THETA_MIN, name=f"thmin[{i},{c}]")
            model.addConstr(var_theta[(i, c)] <= THETA_MAX, name=f"thmax[{i},{c}]")
        model.addConstr(var_theta[(SLACK_BUS, c)] == 0.0, name=f"ref[{c}]")   # reference bus

    return model, var_z


def failing_contingencies(z_fixed, env):
    """Solve the full SC-DCOPF with the topology fixed (one LP, all scenarios together).
    Return [] if it is feasible, otherwise the contingencies in the IIS of that LP."""
    model, _ = build_model(set_C, z_fixed=z_fixed, env=env)
    model.setParam("DualReductions", 0)
    model.optimize()
    if model.status == GRB.OPTIMAL:
        model.dispose()
        return []
    model.computeIIS()
    pat = re.compile(r",?(\d+)\]$")
    failing = sorted({int(pat.search(con.ConstrName).group(1))
                      for con in model.getConstrs() if con.IISConstr} - {0})
    model.dispose()
    return failing


def save_topology(z, path):
    pd.DataFrame({"branch_id": set_L, "label": [par_label[l] for l in set_L],
                  "z": [z[l] for l in set_L]}).to_csv(path, index=False)


def screen_k(K, core, args, env, out_dir):
    """Constraint generation for one K (K = None: minimum-switching mode, no K limit).
    Returns a result row for the summary."""
    core = list(core)
    t0 = time.time()
    min_sw = K is None
    tag = "minsw" if min_sw else f"K{K}"
    for it in range(1, args.max_iter + 1):
        if min_sw:
            model, var_z = build_model(core, max_switched=args.max_open, env=env,
                                       objective="switching", min_open=args.min_open)
        else:
            model, var_z = build_model(core, max_switched=K, env=env)
        model.setParam("OutputFlag", 1)                        # always write the log file...
        model.setParam("LogToConsole", 1 if args.verbose else 0)   # ...console only if asked
        log_file = f"{out_dir}/{tag}_it{it}.log"
        if os.path.exists(log_file):
            os.remove(log_file)   # Gurobi appends to an existing log; keep only this run
        model.setParam("LogFile", log_file)
        model.setParam("MIPGap", args.mip_gap)
        model.setParam("TimeLimit", args.time_limit)
        model.setParam("MIPFocus", 1)
        if args.norel_time:
            model.setParam("NoRelHeurTime", args.norel_time)   # finds feasible z before the root LP
        model.setParam("DualReductions", 0)   # INFEASIBLE instead of INF_OR_UNBD
        if args.threads:
            model.setParam("Threads", args.threads)
        model.optimize()

        print(f"  {tag} it={it}: core={len(core)} scenarios, status={model.status}, "
              f"{model.Runtime:.0f}s", flush=True)

        row = {"K": "min" if min_sw else K, "iterations": it, "core_size": len(core),
               "core": ";".join(scen[c]["desc"] for c in core)}

        if model.status == GRB.INFEASIBLE:
            bounds = (([f">= {args.min_open}"] if args.min_open else [])
                      + ([f"<= {args.max_open}"] if args.max_open is not None else []))
            verdict = ("infeasible for every topology"
                       + (f" with {' and '.join(bounds)} open" if bounds else "")
                       if min_sw else "infeasible")
            return {**row, "verdict": verdict, "time_s": round(time.time() - t0, 1)}
        if model.SolCount == 0:
            return {**row, "verdict": "unknown (time limit, no solution)",
                    "time_s": round(time.time() - t0, 1)}

        z = {l: int(round(var_z[l].X)) for l in set_L}
        core_obj, core_bound = model.ObjVal, model.ObjBound
        model.dispose()
        n_open = sum(1 - z[l] for l in set_LS)

        failing = failing_contingencies(z, env)
        print(f"         topology opens {n_open}: {[par_label[l] for l in set_L if z[l] == 0]}, "
              f"{len(failing)} contingencies in the IIS of the full LP", flush=True)
        if not failing:
            if min_sw:
                # The core is a relaxation, so its bound is a lower bound on K_min for the full
                # problem too (the objective is an integer: round the bound up).
                k_lower = max(math.ceil(core_bound - 1e-6), args.min_open)
                save_topology(z, f"{out_dir}/min_switching_topology.csv")
                save_topology(z, f"{out_dir}/K{n_open}_topology.csv")   # warm start for K = n_open
                return {**row, "verdict": "feasible (full N-1)",
                        "n_open": n_open, "k_min_lower_bound": k_lower,
                        "k_min_proven": n_open == k_lower,
                        "opened": ";".join(par_label[l] for l in set_L if z[l] == 0),
                        "time_s": round(time.time() - t0, 1)}
            save_topology(z, f"{out_dir}/K{K}_topology.csv")
            return {**row, "verdict": "feasible (full N-1)",
                    "opened": ";".join(par_label[l] for l in set_L if z[l] == 0),
                    "core_cost": round(core_obj, 2), "core_bound": round(core_bound, 2),
                    "time_s": round(time.time() - t0, 1)}
        core += [c for c in failing if c not in core]

    return {**row, "verdict": f"undecided after {args.max_iter} iterations",
            "time_s": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--formulation", default="redispatch_only",
                    choices=["redispatch_only", "redispatch_with_exclusions"])
    ap.add_argument("--k-min", type=int, default=1)
    ap.add_argument("--k-max", type=int, default=10)
    ap.add_argument("--time-limit", type=float, default=600, help="per core solve [s]")
    ap.add_argument("--mip-gap", type=float, default=1e-2)
    ap.add_argument("--threads", type=int, default=0, help="0 = all cores")
    ap.add_argument("--norel-time", type=float, default=0,
                    help="Gurobi NoRelHeurTime per core solve [s] (0 = off); counts toward "
                         "--time-limit")
    ap.add_argument("--max-iter", type=int, default=10)
    ap.add_argument("--stop-at-first", action="store_true",
                    help="stop the sweep at the first K feasible for the full N-1 set")
    ap.add_argument("--verbose", action="store_true", help="also print the Gurobi logs")
    ap.add_argument("--core-from", metavar="CSV",
                    help="start from the final core of a previous run (its summary CSV)...")
    ap.add_argument("--core-k", type=int, help="...taken from the row of this K")
    ap.add_argument("--min-switching", action="store_true",
                    help="find K_min instead: min sum(1 - z) over L^S, no K limit (--k-min/--k-max "
                         "and --stop-at-first are ignored)")
    ap.add_argument("--min-open", type=int, default=0,
                    help="with --min-switching: add the cut sum(1 - z) >= this (a K proven "
                         "infeasible + 1, e.g. 4 for redispatch_only)")
    ap.add_argument("--max-open", type=int, default=None,
                    help="with --min-switching: add the cut sum(1 - z) <= this (search only "
                         "topologies with at most this many open branches)")
    args = ap.parse_args()

    exclude = HARD if args.formulation == "redispatch_with_exclusions" else []
    set_scenarios(exclude)

    out_dir = f"results/{SOURCE}/{args.formulation}/screening"
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
        core = [0] + [scenario_id(kind, e) for kind, e in HARD if (kind, e) not in exclude]
    print(f"Formulation: {args.formulation} | |C| = {len(set_C)}")
    print(f"Initial core: {[scen[c]['desc'] for c in core]}")

    env  = gp.Env(params={"OutputFlag": 0})

    if args.min_switching:
        row = screen_k(None, core, args, env, out_dir)
        pd.DataFrame([row]).to_csv(f"{out_dir}/summary_min_switching.csv", index=False)
        print(f"\nMinimum switching: {row['verdict']}")
        if "n_open" in row:
            proven = "proven" if row["k_min_proven"] else f"lower bound {row['k_min_lower_bound']}"
            print(f"K_min = {row['n_open']} ({proven}) -> opens {row['opened']}")
        print(f"Saved to {out_dir}/")
        return

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
