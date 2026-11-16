"""Sequential sensitivity-based switching heuristic (Ruiz et al. 2012, Fig. 1) on the model/ package.

At each step: solve the SC-DCOPF LP on the current topology, rank the switchable lines by a
criterion computed from the LP solution, open the best candidate and re-solve. The opening is
kept if the LP is feasible and cheaper; otherwise the line is dropped from the candidates. The
criteria are recomputed after every accepted opening.

Criteria (line k from bus m = from to n = to; for every state c: f = flow [MW],
dpi = pi_n - pi_m [$/MWh] with pi = d cost / d load, mu = flow-limit dual (upper - lower) [$/MWh],
phi = self-PTDF of k in the topology of state c). More negative = more promising:
  LP0  f_0 dpi_0                                   line profit, base state only (Fuller alpha)
  LP   sum_c f_c dpi_c                             line profit over all states (Fuller / Ruiz)
  PD   LP / |f_0|, only lines with LP < 0          price difference (Ruiz eq. 37, adapted)
  PW   sum_c f_c (dpi_c - mu_c) / |f_0|            PTDF-weighted (Ruiz eq. 42, adapted)
  TD   sum_c f_c (dpi_c - mu_c) / (1 - phi_c)      total derivative (Ruiz eqs. 28/39, adapted)
Adaptation to N-1 (heuristic, not proven): the topology is shared by every state, so the
contributions of the states are summed. Lines whose opening islands the base topology
(phi_0 = 1) are never candidates; feasibility is always checked by the full LP.
Islanding criterion: an opening is rejected if, in any branch contingency, it isolates buses
with load or a generator (an isolated empty bus is accepted: no load or generation is lost).

Output: <out-root>/<source>/<formulation>/<config>/lambda<l>/heuristic/
  path_<criterion>.csv            one row per accepted opening (cost, LPs, time, MILP cost if given)
  <criterion>/K<n>/               full result of each accepted topology (same files as run_ots.py),
                                  usable as warm start: run_ots.py --warm-start-dir <...>/<criterion>
  criteria_K0.csv, run.log
"""

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import OTSModel                                           # noqa: E402
from model.data import load_system                                         # noqa: E402
from model.solution import (export, forbidden_islands, get_logger, islanding_by_state,   # noqa: E402
                            isolated_buses, read_solution)
from model.states import CONFIG_NAME, EXCLUSIONS, build_states, summary_lines   # noqa: E402

CRITERIA = ["LP0", "LP", "PD", "PW", "TD"]


# ----------------------------------------------------------------------------- sensitivities
def self_ptdf(system, z, out_branch=None):
    """phi[k]: PTDF of branch k for a transfer from its from bus to its to bus, on topology z
    (with out_branch also out). 1.0 for branches whose outage islands, or that are out.
    Direct version (one inversion per call): reference for state_self_ptdf in the tests."""
    on = np.asarray(z) > 0.5
    if out_branch is not None:
        on = on.copy()
        on[out_branch] = False
    NB, NL = system.n_bus, system.n_branch
    keep = np.array([i for i in range(NB) if i != system.slack])
    col = -np.ones(NB, dtype=int)
    col[keep] = np.arange(NB - 1)
    A = np.zeros((NL, NB - 1))                       # reduced incidence (slack column removed)
    rows = np.flatnonzero(on)
    fr, to = system.br_from[rows], system.br_to[rows]
    A[rows[col[fr] >= 0], col[fr[col[fr] >= 0]]] = 1.0
    A[rows[col[to] >= 0], col[to[col[to] >= 0]]] = -1.0
    b = np.where(on, 1.0 / system.x, 0.0)
    try:
        X = np.linalg.inv(A.T @ (b[:, None] * A))    # inverse of the reduced B'
    except np.linalg.LinAlgError:                    # topology already islanded
        return np.ones(NL)
    psi = np.zeros((NL, NB))
    psi[:, keep] = (b[:, None] * A) @ X              # injection shift factors
    phi = psi[np.arange(NL), system.br_from] - psi[np.arange(NL), system.br_to]
    phi[~on] = 1.0
    return phi


def transfer_ptdf(system, z):
    """H[l, k]: flow on branch l per unit transfer from the from bus to the to bus of branch k,
    on topology z (one inversion of the reduced B'). diag(H) is the self-PTDF."""
    on = np.asarray(z) > 0.5
    NB, NL = system.n_bus, system.n_branch
    keep = np.array([i for i in range(NB) if i != system.slack])
    col = -np.ones(NB, dtype=int)
    col[keep] = np.arange(NB - 1)
    Ar = np.zeros((NL, NB - 1))
    for l in np.flatnonzero(on):
        if col[system.br_from[l]] >= 0:
            Ar[l, col[system.br_from[l]]] = 1.0
        if col[system.br_to[l]] >= 0:
            Ar[l, col[system.br_to[l]]] = -1.0
    b = np.where(on, 1.0 / system.x, 0.0)
    try:
        X = np.linalg.inv(Ar.T @ (b[:, None] * Ar))
    except np.linalg.LinAlgError:                    # topology already islanded
        return None
    psi = np.zeros((NL, NB))
    psi[:, keep] = (b[:, None] * Ar) @ X
    return psi[:, system.br_from] - psi[:, system.br_to]


def state_self_ptdf(system, states, z):
    """phi[k, c]: self-PTDF of branch k in the topology of state c (z with the branch of c out).

    One inversion for the current topology (H = transfer PTDFs), then, for the outage of branch m,
    the single-outage LODF update of the PTDFs:
        H'_lk = H_lk + LODF_lm H_mk,   LODF_lm = H_lm / (1 - H_mm)
    which for l = k gives  phi_k^(-m) = H_kk + H_km H_mk / (1 - H_mm).
    References: line outage distribution factors in Wood, Wollenberg & Sheble, "Power Generation,
    Operation, and Control" (chapter on linear sensitivity factors); generalization to multiple
    outages in Guler, Gross & Liu (2007), "Generalized line outage distribution factors",
    IEEE Trans. Power Syst. 22(2). Checked against direct inversion in tests/check_reference.py.
    1.0 where the branch is out or its outage islands (H_mm = 1)."""
    H = transfer_ptdf(system, z)
    if H is None:
        return np.ones((system.n_branch, len(states)))
    d = np.diag(H).copy()
    on = np.asarray(z) > 0.5
    phi = np.tile(d[:, None], (1, len(states)))
    for st in states:
        if st.kind == "line":
            m = st.element
            if 1 - H[m, m] < 1e-9:                       # outage of m islands: no update
                phi[:, st.id] = 1.0
                continue
            phi[:, st.id] = d + H[:, m] * H[m, :] / (1 - H[m, m])
            phi[m, st.id] = 1.0
    phi[~on, :] = 1.0
    return np.minimum(phi, 1.0)


def criteria_table(model, sol):
    """Criteria for every switchable line still closed (candidates only)."""
    s, states = model.sys, model.states
    base = s.base_mva
    flow = sol.f * base                                            # MW, NL x NS
    dpi = (sol.pi[s.br_to, :] - sol.pi[s.br_from, :]) / base       # $/MWh
    mu = sol.mu / base                                             # $/MWh
    phi = state_self_ptdf(s, states, sol.z)
    f0 = np.abs(flow[:, 0]) + 1e-6
    lp0 = flow[:, 0] * dpi[:, 0]
    lp = (flow * dpi).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        td = np.where(phi < 1 - 1e-9, flow * (dpi - mu) / (1 - phi), 0.0).sum(axis=1)
    df = pd.DataFrame({
        "branch_id": np.arange(s.n_branch), "label": s.label, "flow0_MW": flow[:, 0],
        "dpi0": dpi[:, 0], "LP0": lp0, "LP": lp, "PD": np.where(lp < 0, lp / f0, 0.0),
        "PW": (flow * (dpi - mu)).sum(axis=1) / f0, "TD": td,
        "self_ptdf0": phi[:, 0], "islanding": phi[:, 0] > 1 - 1e-9})
    cand = np.isin(df.branch_id, model.LS) & (sol.z == 1) & ~df.islanding
    return df[cand].reset_index(drop=True)


# ----------------------------------------------------------------------------- heuristic
def solve_topology(model, open_ids, duals):
    model.open_lines(open_ids)
    model.solve()
    return read_solution(model, duals=duals)


def overload_mw(model):
    """Total overload of the last 'min_violation' LP [MW]."""
    return float(model.m.ObjVal) * model.sys.base_mva


def run_sequential(model, criterion, max_open, max_lp, log, export_root=None, milp_cost=None,
                   allow_islands=False, tol_mw=1e-4):
    """Ruiz Fig. 1 with one criterion. Returns the list of accepted steps (dicts).

    Two phases (the first one only if the original topology is infeasible and the model has flow
    slacks, i.e. CS2):
      'violation': LP with overload slacks (min total overload); the criteria use its duals; an
                   opening is kept if the overload decreases. When the overload reaches zero the
                   topology is checked by the LP WITHOUT slacks (proof of N-1 feasibility).
      'cost'     : the cost heuristic (CS1), continued from that topology up to max_open.
    Only feasible topologies (cost phase) are exported as warm starts."""
    s = model.sys
    t0 = time.time()
    open_ids, n_lp, steps, banned = [], 0, [], set()

    def cost_lp(ids):
        model.set_objective("cost")
        return solve_topology(model, ids, duals=True)

    def violation_lp(ids):
        model.set_objective("min_violation")
        sol = solve_topology(model, ids, duals=True)
        return sol, (overload_mw(model) if sol is not None else None)

    sol = cost_lp(open_ids)
    n_lp += 1
    phase, viol = "cost", 0.0
    if sol is None:
        if model.S is None:
            log.info(f"{criterion}: the original topology is infeasible at this load level "
                     "(build the model with flow_slack=True for the violation phase)")
            return []
        phase = "violation"
        sol, viol = violation_lp(open_ids)
        n_lp += 1
        if sol is None:
            log.info(f"{criterion}: infeasible even without flow limits at this load level")
            return []
        log.info(f"{criterion}: start K=0 infeasible, minimum overload {viol:,.2f} MW")
    else:
        log.info(f"{criterion}: start K=0 cost ${sol.cost:,.2f}/h")

    while len(open_ids) < max_open and n_lp < max_lp:
        cr = criteria_table(model, sol)
        cr = cr[~cr.branch_id.isin(banned) & (cr[criterion] < -1e-9)].sort_values(criterion)
        if cr.empty:
            log.info(f"{criterion}: no candidate left (all criteria >= 0 or tried)")
            break
        k = int(cr.iloc[0].branch_id)
        trial = open_ids + [k]
        z = np.ones(s.n_branch)
        z[trial] = 0.0
        banned.add(k)
        if isolated_buses(s, z):                          # connectivity of the base topology
            log.info(f"  reject {s.label[k]:>8}: islands the base topology")
            continue
        if not allow_islands and forbidden_islands(s, model.states, z):
            log.info(f"  reject {s.label[k]:>8}: isolates load or generation in a contingency state")
            continue
        if phase == "violation":
            new, new_viol = violation_lp(trial)
            n_lp += 1
            if new is None:
                log.info(f"  reject {s.label[k]:>8}: infeasible even with overload slacks")
                continue
            if new_viol >= viol - tol_mw:
                log.info(f"  reject {s.label[k]:>8}: overload {new_viol:,.2f} MW does not decrease")
                continue
            sol, viol, open_ids = new, new_viol, trial
            if viol <= tol_mw:                            # proof: LP without slacks
                proof = cost_lp(open_ids)
                n_lp += 1
                if proof is None:                         # only a numerical zero: keep searching
                    log.info(f"  K={len(open_ids)}: overload ~0 but the LP without slacks is infeasible")
                    model.set_objective("min_violation")
                else:
                    sol, phase, viol = proof, "cost", 0.0
                    banned = set()                        # lines rejected for the overload may lower the cost
                    log.info(f"  {criterion} K={len(open_ids)}: N-1 FEASIBLE (LP without slacks) "
                             f"-> ${sol.cost:,.2f}/h")
        else:
            new = cost_lp(trial)
            n_lp += 1
            if new is None:
                log.info(f"  reject {s.label[k]:>8}: LP infeasible")
                continue
            if new.cost >= sol.cost - 1e-6:
                log.info(f"  reject {s.label[k]:>8}: cost ${new.cost:,.2f}/h does not improve")
                continue
            sol, open_ids = new, trial
        K = len(open_ids)
        feasible = phase == "cost"
        isl = islanding_by_state(s, model.states, sol.z)
        ref = (milp_cost or {}).get(K)
        step = {"criterion": criterion, "K": K, "opened": s.label[k], "branch_id": k,
                "phase": phase, "overload_mw": 0.0 if feasible else round(viol, 4),
                "cost": round(sol.cost, 2) if feasible else None, "milp_cost": ref,
                "lp_solves": n_lp, "time_s": round(time.time() - t0, 1),
                "states_with_islands": len(isl), "open_lines": " ".join(s.label[l] for l in open_ids)}
        steps.append(step)
        log.info(f"  {criterion} K={K}: open {s.label[k]:>8} -> "
                 + (f"${sol.cost:,.2f}/h" if feasible else f"overload {viol:,.2f} MW")
                 + (f" (MILP ${ref:,.2f}/h)" if ref else "")
                 + (f" | {len(isl)} states with islands" if isl else "")
                 + f" | {n_lp} LPs, {time.time() - t0:.0f} s")
        if export_root and feasible:
            export(_Quiet(), model, sol, os.path.join(export_root, criterion, f"K{K}"),
                   meta={"heuristic": criterion, "lp_solves": n_lp})
    log.info(f"{criterion}: {len(open_ids)} openings, {n_lp} LPs, {time.time() - t0:.0f} s, "
             + (f"final cost ${sol.cost:,.2f}/h" if phase == "cost"
                else f"NOT feasible, overload {viol:,.2f} MW"))
    model.set_objective("cost")
    return steps


PATH_COLUMNS = ["criterion", "K", "opened", "branch_id", "phase", "overload_mw", "cost", "milp_cost",
                "lp_solves", "time_s", "states_with_islands", "open_lines"]


def summarize(out, cost0, overload0=None):
    """One row per criterion from every path_<criterion>.csv in the folder (also from earlier runs).
    cost0: cost at K = 0 (None if infeasible); overload0: overload at K = 0 [MW] (CS2)."""
    rows = []
    for crit in CRITERIA:
        f = os.path.join(out, f"path_{crit}.csv")
        if not os.path.exists(f):
            continue
        try:
            p = pd.read_csv(f)
        except pd.errors.EmptyDataError:           # criterion that opened nothing
            p = pd.DataFrame(columns=PATH_COLUMNS)
        if "phase" not in p.columns:               # files written before the violation phase
            p["phase"] = "cost"
        feas = p[p.phase == "cost"]
        best = feas.iloc[-1] if len(feas) else None
        row = {"criterion": crit, "openings": len(p)}
        if overload0 is not None:                  # CS2: infeasible at K = 0
            row["overload_K0_mw"] = round(overload0, 2)
            row["first_feasible_K"] = int(feas.K.iloc[0]) if len(feas) else None
            row["min_overload_mw"] = 0.0 if len(feas) else (float(p.overload_mw.min()) if len(p) else overload0)
        row["best_cost"] = round(float(best["cost"]), 2) if best is not None else cost0
        if cost0 is not None and row["best_cost"] is not None:
            row["saving_pct"] = round(100 * (1 - row["best_cost"] / cost0), 3)
        row["lp_solves"] = int(p.lp_solves.iloc[-1]) if len(p) else 1
        row["time_s"] = float(p.time_s.iloc[-1]) if len(p) else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


class _Quiet:
    """Logger stand-in that drops export messages (one per step would clutter the log)."""
    def info(self, *_):
        pass


def saved_milp_costs(folder):
    """{K: cost} from <folder>/K<k>/summary.csv (e.g. the benchmark MILP sweep)."""
    out = {}
    if folder and os.path.isdir(folder):
        for k in range(0, 200):
            p = os.path.join(folder, f"K{k}", "summary.csv")
            if os.path.exists(p):
                v = pd.read_csv(p).set_index("metric")["value"]
                out[k] = float(v["base_cost_usd_per_h"])
    return out


# ----------------------------------------------------------------------------- command line
EPILOG = """examples (from project/):
  # benchmark: reduced list, lambda = 1, compare with the saved MILP K sweep
  python heuristics/sequential.py --formulation redispatch_with_exclusions --out-root heuristics/benchmark/results \\
      --milp-dir heuristics/benchmark/results/matpower/redispatch_with_exclusions/contingencies
  # CS1: full list, lambda = 0.80, all criteria
  python heuristics/sequential.py --load-factor 0.80 --out-root cs1-cost/results
  # CS2: above lambda_max the original topology is infeasible: violation phase, then cost phase
  python heuristics/sequential.py --load-factor 0.90 --out-root cs2-feasibility/results
  # only TD, up to 10 openings and 120 LPs
  python heuristics/sequential.py --load-factor 0.85 --criteria TD --max-open 10 --max-lp 120 --out-root cs1-cost/results
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="matpower", help="processed dataset (default: matpower)")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full list (default); redispatch_with_exclusions = reduced")
    ap.add_argument("--contingencies", default="all", choices=list(CONFIG_NAME),
                    help="states besides the base case (default: all)")
    ap.add_argument("--load-factor", type=float, default=1.0, help="lambda (default: 1.0)")
    ap.add_argument("--criteria", nargs="+", default=CRITERIA, choices=CRITERIA,
                    help="criteria to run, each one separately (default: all five)")
    ap.add_argument("--max-open", type=int, default=10, help="stop after this many openings (default: 10)")
    ap.add_argument("--max-lp", type=int, default=90, help="max LP solves per criterion (default: 90)")
    ap.add_argument("--allow-islands", action="store_true",
                    help="accept openings that isolate load or generation in a contingency, if the LP is "
                         "feasible (default: rejected; isolated empty buses are always accepted)")
    ap.add_argument("--milp-dir", default=None,
                    help="folder with K<k>/summary.csv of a MILP sweep, to print and save its cost per K")
    ap.add_argument("--out-root", required=True, help="results root of the study case")
    ap.add_argument("--no-export", action="store_true", help="do not write the K<n>/ folders")
    args = ap.parse_args(argv)

    out = os.path.join(args.out_root, args.source, args.formulation, CONFIG_NAME[args.contingencies],
                       f"lambda{args.load_factor:.3f}", "heuristic")
    log = get_logger(out)
    log.info(f"sequential.py {' '.join(sys.argv[1:])}")
    log.info(f"output -> {out}")
    system = load_system(args.source)
    for line in system.summary_lines():
        log.info(line)
    states = build_states(system, args.formulation, args.contingencies)
    for line in summary_lines(system, states, args.formulation, args.contingencies):
        log.info(line)
    model = OTSModel(system, states, load_factor=args.load_factor, flow_slack=True)  # slacks fixed at 0 in cost mode
    for line in model.size_lines():
        log.info(line)
    milp = saved_milp_costs(args.milp_dir)
    if milp:
        log.info(f"MILP costs read from {args.milp_dir}: K = {sorted(milp)}")

    sol0 = solve_topology(model, [], duals=True)
    cost0, overload0 = (None if sol0 is None else sol0.cost), None
    if sol0 is None:                                  # CS2: start with the violation phase
        model.set_objective("min_violation")
        sol0 = solve_topology(model, [], duals=True)
        if sol0 is None:
            log.info(f"Infeasible at lambda = {args.load_factor} even without flow limits: "
                     "switching cannot be evaluated by the overload (see reference/load_limits.py).")
            return 1
        overload0 = overload_mw(model)
        model.set_objective("cost")
        log.info(f"K=0 N-1 INFEASIBLE; minimum overload {overload0:,.2f} MW (violation phase first)")
    else:
        log.info(f"K=0 cost ${sol0.cost:,.2f}/h")
    criteria_table(model, sol0).to_csv(os.path.join(out, "criteria_K0.csv"), index=False)

    for crit in args.criteria:
        steps = run_sequential(model, crit, args.max_open, args.max_lp, log,
                               export_root=None if args.no_export else out, milp_cost=milp,
                               allow_islands=args.allow_islands)
        pd.DataFrame(steps, columns=PATH_COLUMNS).to_csv(os.path.join(out, f"path_{crit}.csv"), index=False)
    tab = summarize(out, cost0, overload0)
    tab.to_csv(os.path.join(out, "summary_criteria.csv"), index=False)
    log.info("\nSummary by criterion:\n" + tab.to_string(index=False))
    model.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
