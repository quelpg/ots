"""Read, report and export a solution
"""

import logging
import math
import os
from collections import deque
from dataclasses import dataclass

import numpy as np
import pandas as pd

LOG_NAME = "ots"


# ----------------------------------------------------------------------------- logging
def get_logger(out_dir=None, name=LOG_NAME):
    """Console + `<out_dir>/run.log` (same messages). The log is appended to, with a separator
    per run, so a new run never erases the history of earlier runs in the same folder."""
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in log.handlers):
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(ch)
    if out_dir is not None:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.abspath(os.path.join(out_dir, "run.log"))
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == path for h in log.handlers):
            new_file = not os.path.exists(path)
            fh = logging.FileHandler(path, mode="a", encoding="utf-8")
            if not new_file:
                fh.stream.write("\n" + "#" * 100 + "\n")             # separator between runs
            fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
            log.addHandler(fh)
    return log


# ----------------------------------------------------------------------------- solution
@dataclass
class Solution:
    status: str
    objective: str
    cost: float                # base-case cost [$/h]
    bound: float               # best bound (MILP) [$/h or lambda]
    gap: float
    runtime: float
    load_factor: float
    K: object                  # switching limit (None = unlimited)
    p0: np.ndarray             # base-case dispatch [pu]
    f0: np.ndarray             # base-case flows [pu]
    theta0: np.ndarray         # base-case angles [rad]
    z: np.ndarray              # topology (0 = open)
    f: np.ndarray = None       # flows in every state [pu], NL x NS (LP only, if asked)
    pi: np.ndarray = None      # balance duals d cost / d load [$/h per pu], NB x NS
    mu: np.ndarray = None      # flow-limit duals (upper - lower) [$/h per pu], NL x NS

    @property
    def open_ids(self):
        return [int(l) for l in np.flatnonzero(self.z < 0.5)]


def read_solution(model, duals=False):
    """Solution of the last solve, or None if there is none. duals=True only for LPs."""
    if not model.has_solution:
        return None
    m, s = model.m, model.sys
    is_mip = m.IsMIP
    cost = float(model.cost_vec @ model.P.X[:, 0])
    sol = Solution(
        status=model.status_name, objective=model.objective, cost=cost,
        bound=float(m.ObjBound) if is_mip else float(m.ObjVal),
        gap=float(m.MIPGap) if is_mip else 0.0, runtime=float(m.Runtime),
        load_factor=float(model.lam.X[0]), K=getattr(model, "K", None),
        p0=model.P.X[:, 0].copy(), f0=model.F.X[:, 0].copy(), theta0=model.T.X[:, 0].copy(),
        z=np.round(model.z.X).astype(int))
    if duals and not is_mip:
        sol.f = model.F.X.copy()
        sol.pi = np.column_stack([c.Pi for c in model.c_bal])
        sol.mu = -np.column_stack([c.Pi for c in model.c_fmax]) - np.column_stack([c.Pi for c in model.c_fmin])
    return sol


# ----------------------------------------------------------------------------- islanding
def isolated_buses(system, z, out_branch=None):
    """Bus positions not connected to the slack through closed branches (optionally one more out)."""
    closed = np.asarray(z) > 0.5
    if out_branch is not None:
        closed = closed.copy()
        closed[out_branch] = False
    adj = [[] for _ in range(system.n_bus)]
    for l in np.flatnonzero(closed):
        adj[system.br_from[l]].append(system.br_to[l])
        adj[system.br_to[l]].append(system.br_from[l])
    seen = np.zeros(system.n_bus, dtype=bool)
    seen[system.slack] = True
    queue = deque([system.slack])
    while queue:
        for v in adj[queue.popleft()]:
            if not seen[v]:
                seen[v] = True
                queue.append(v)
    return [int(i) for i in np.flatnonzero(~seen)]


def islanding_by_state(system, states, z):
    """{state id: isolated bus positions} for the base case and every branch contingency that islands."""
    out = {}
    base = isolated_buses(system, z)
    if base:
        out[0] = base
    for st in states:
        if st.kind == "line":
            iso = isolated_buses(system, z, st.element)
            if iso:
                out[st.id] = iso
    return out


def forbidden_islands(system, states, z):
    """Islands that contain load or a generator ({state id: bus positions}). Criterion of the
    project: an isolated bus with no load and no generator (a de-energized transit bus) is
    accepted; isolating load or generation in any state is not."""
    has_gen = np.zeros(system.n_bus, dtype=bool)
    has_gen[system.gen_bus] = True
    out = {}
    for c, buses in islanding_by_state(system, states, z).items():
        b = np.asarray(buses)
        if (system.pd_nom[b] > 0).any() or has_gen[b].any():
            out[c] = buses
    return out


# ----------------------------------------------------------------------------- tables
def dispatch_table(system, sol):
    mw, pmax = sol.p0 * system.base_mva, system.pmax * system.base_mva
    df = pd.DataFrame({"gen_id": range(system.n_gen), "bus": system.bus[system.gen_bus],
                       "p_mw": mw.round(2), "pmax_mw": pmax.round(2),
                       "loading_pct": np.where(pmax > 0, 100 * mw / np.where(pmax > 0, pmax, 1), 0).round(1),
                       "c1": system.cost.round(3)})
    if system.is_renewable.any():                 # pmax_mw of a renewable unit = available Gbar_r
        df["renewable"] = system.is_renewable
    return df.sort_values("c1", kind="stable")


def curtailment(system, sol):
    """(available, curtailed) renewable power in the base case [MW]: C = sum_r (Gbar_r - P_r,0)."""
    ren = system.is_renewable
    avail = system.pmax[ren].sum() * system.base_mva
    return avail, avail - sol.p0[ren].sum() * system.base_mva


def line_loading_table(system, sol):
    f, fmax = sol.f0 * system.base_mva, system.rate * system.base_mva
    df = pd.DataFrame({"branch_id": range(system.n_branch), "label": system.label, "z": sol.z,
                       "f_mw": f.round(2), "fmax_mw": fmax.round(2),
                       "loading_pct": (100 * np.abs(f) / fmax).round(1)})
    return df.sort_values("loading_pct", ascending=False, kind="stable")


def angles_table(system, sol):
    df = pd.DataFrame({"bus": system.bus, "theta_rad": sol.theta0.round(6),
                       "theta_deg": np.degrees(sol.theta0).round(4),
                       "is_slack": system.bus == system.slack_bus})
    return df.sort_values("theta_deg", kind="stable")


def switching_table(system, sol):
    ids = sol.open_ids
    return pd.DataFrame({"branch_id": ids, "label": [system.label[l] for l in ids],
                         "x_pu": system.x[ids], "fmax_mw": (system.rate[ids] * system.base_mva).round(2)},
                        columns=["branch_id", "label", "x_pu", "fmax_mw"])


# ----------------------------------------------------------------------------- report / export
def report(log, model, sol):
    """The result block the notebooks printed in section 8 (+ islanding in every state)."""
    s = model.sys
    if sol is None:
        log.info(f"Solver status: {model.status_name} (no solution available)")
        return
    gen_mw = sol.p0.sum() * s.base_mva
    load_mw = sol.load_factor * s.pd_nom.sum() * s.base_mva
    log.info("=" * 60)
    log.info("  OTS-SC-DCOPF SOLUTION - IEEE 118-bus")
    log.info("=" * 60)
    log.info(f"  Status          : {sol.status} (gap {100 * sol.gap:.4f}%)")
    log.info(f"  Base-case cost  : ${sol.cost:,.2f} /h")
    if model.m.IsMIP:
        unit = {"cost": "$/h", "min_switching": "open lines (lower bound on K_min)",
                "max_load": "lambda"}[sol.objective]
        log.info(f"  Best bound      : {sol.bound:,.2f} {unit}")
    log.info(f"  Load factor     : {sol.load_factor:.4f} ({load_mw:,.2f} MW)")
    log.info(f"  Total generation: {gen_mw:,.2f} MW (base case)")
    log.info(f"  States          : {len(model.states)}")
    log.info(f"  Switching limit : K = {sol.K}")
    log.info(f"  Lines open      : {len(sol.open_ids)} -> {[s.label[l] for l in sol.open_ids]}")
    if s.is_renewable.any():
        avail, curt = curtailment(s, sol)
        log.info(f"  Renewables      : {avail:,.2f} MW available, curtailment {curt:,.2f} MW "
                 f"({100 * curt / avail if avail else 0:.1f}%)")
    log.info(f"  Runtime         : {sol.runtime:.1f} s")
    disp = dispatch_table(s, sol)
    act = disp[disp.p_mw > 0.01]
    log.info(f"Active generators ({len(act)}):\n" + act.to_string(index=False))
    isl = islanding_by_state(s, model.states, sol.z)
    bad = forbidden_islands(s, model.states, sol.z)
    if not isl:
        log.info("Islanding: no isolated bus in the base case or in any branch contingency")
    else:
        for c, buses in isl.items():
            kind = "LOAD OR GENERATION ISOLATED (not accepted)" if c in bad else "empty buses only (accepted)"
            log.info(f"Islanding: {model.states[c].desc}: buses {[int(s.bus[i]) for i in buses]} "
                     f"(load {model.sys.pd_nom[buses].sum() * sol.load_factor * s.base_mva:.1f} MW) - {kind}")


def export(log, model, sol, out_dir, meta=None):
    """Write the five CSV files (only when there is a solution)."""
    if sol is None:
        log.info("No solution - nothing exported.")
        return []
    s = model.sys
    os.makedirs(out_dir, exist_ok=True)
    isl = islanding_by_state(s, model.states, sol.z)
    metrics = {
        "base_cost_usd_per_h": round(sol.cost, 2), "best_bound_usd_per_h": round(sol.bound, 2),
        "mip_gap": sol.gap, "solver_status": sol.status, "runtime_s": round(sol.runtime, 1),
        "load_factor": sol.load_factor,
        "total_load_mw": round(sol.load_factor * s.pd_nom.sum() * s.base_mva, 2),
        "total_generation_mw": round(sol.p0.sum() * s.base_mva, 2),
        "n_scenarios": len(model.states),
        "n_active_generators": int((sol.p0 * s.base_mva > 0.01).sum()),
        "max_switched": "inf" if sol.K is None else sol.K, "n_switched_lines": len(sol.open_ids),
        "theta_max_rad": model.theta_max, "objective": sol.objective,
        "n_states_with_islands": len(isl),
        "n_states_isolating_load_or_gen": len(forbidden_islands(s, model.states, sol.z)),
        "renewable_scenario": s.renewables or "none", "renewable_penetration": s.penetration,
        "renewable_available_mw": round(curtailment(s, sol)[0], 2),
        "curtailment_mw": round(curtailment(s, sol)[1], 2),
    }
    metrics.update(meta or {})
    pd.DataFrame({"metric": list(metrics), "value": list(metrics.values())}).to_csv(
        os.path.join(out_dir, "summary.csv"), index=False)
    dispatch_table(s, sol).to_csv(os.path.join(out_dir, "dispatch.csv"), index=False)
    line_loading_table(s, sol).to_csv(os.path.join(out_dir, "line_loading.csv"), index=False)
    angles_table(s, sol).to_csv(os.path.join(out_dir, "angles.csv"), index=False)
    switching_table(s, sol).to_csv(os.path.join(out_dir, "switching.csv"), index=False)
    files = ["summary.csv", "dispatch.csv", "line_loading.csv", "angles.csv", "switching.csv"]
    log.info(f"Saved {len(files)} files to {out_dir}/ (cost ${sol.cost:,.2f}/h, "
             f"{metrics['n_active_generators']} active generators, {len(sol.open_ids)} lines open)")
    return files


def saved_topology(result_dir):
    """(open branch ids, cost) of a saved result folder (summary.csv + line_loading.csv)."""
    summ = pd.read_csv(os.path.join(result_dir, "summary.csv")).set_index("metric")["value"]
    ll = pd.read_csv(os.path.join(result_dir, "line_loading.csv"))
    return ll.loc[ll["z"] == 0, "branch_id"].astype(int).tolist(), float(summ["base_cost_usd_per_h"])


def cheapest_saved(dirs, max_k, key="cost"):
    """Warm start (notebook section 6.1): saved result with K' <= max_k in <dir>/<sub>/ (any
    subfolder with summary.csv + line_loading.csv). key='cost': the cheapest;
    key='n_open': the one with fewest open lines (for the minimum-switching MILP)."""
    best = None
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for sub in sorted(os.listdir(d)):
            rd = os.path.join(d, sub)
            if os.path.exists(os.path.join(rd, "summary.csv")) and os.path.exists(os.path.join(rd, "line_loading.csv")):
                ids, cost = saved_topology(rd)
                rank = (cost,) if key == "cost" else (len(ids), cost)
                if len(ids) <= max_k and (best is None or rank < best[3]):
                    best = (rd, ids, cost, rank)
    return None if best is None else best[:3]
