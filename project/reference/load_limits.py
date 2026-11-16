"""What limits the load under N-1 on the original topology (K = 0)? Diagnostic of the load regimes.

1. lambda_max with each family of constraints relaxed, one at a time and combined (diagnostic
   only: the model keeps every limit). If relaxing a family raises lambda_max, that family holds
   the load. Families: flow limits (overload slacks free), angle limits (+-0.6 rad -> +-10 rad),
   generator capacity (every Pmax x 10; alpha does not change, it is proportional to Pmax).
2. Minimum flow-limit violation per load level above lambda_max (LP with overload slacks, equal
   weights): total overload [MW], states and lines involved, worst line and state.
3. (--conflict-sets) Minimal set of conflicting contingencies just above each limit (lambda_max
   with every limit, and lambda_max with the flow limits relaxed), found by a deletion filter:
   start with every contingency; drop one at a time if the rest is still infeasible without it.
   What remains is a smallest set that is infeasible together (with the base case); removing any
   one of them makes it feasible (checked). The set depends on the order of the filter: it is
   *a* minimal set, not necessarily the only one.

Output (<out-root>/<source>/<formulation>/): load_limits.csv, violation_by_lambda.csv,
conflict_set_<limit>.csv, run.log.
"""

import argparse
import copy
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import THETA_MAX, OTSModel                                    # noqa: E402
from model.data import load_system                                             # noqa: E402
from model.solution import get_logger                                          # noqa: E402
from model.states import EXCLUSIONS, State, build_states                       # noqa: E402

THETA_RELAXED = 10.0      # [rad] "no angle limit"
PMAX_RELAXED = 10.0       # Pmax multiplier "no capacity limit"
VIOLATION_GRID = [0.86, 0.88, 0.90, 0.95, 0.99, 1.00]

EPILOG = """examples (from project/):
  python reference/load_limits.py                     # lambda_max table + violation per lambda (~1 min)
  python reference/load_limits.py --conflict-sets     # + minimal conflicting sets (~10 min)
"""


def make_model(system, states, theta, relax_flow, load_factor=1.0):
    m = OTSModel(system, states, load_factor=load_factor, theta_max=theta, flow_slack=True)
    m.open_lines([])
    if relax_flow:
        m.relax_flow_limits(True)
    return m


def lambda_max(system, states, theta, relax_flow):
    m = make_model(system, states, theta, relax_flow)
    m.set_objective("max_load")
    if relax_flow:
        m.relax_flow_limits(True)
    m.solve()
    val = float(m.lam.X[0]) if m.status_name == "OPTIMAL" else None
    m.dispose()
    return val


def feasible(system, states, lam, theta, relax_flow):
    m = make_model(system, states, theta, relax_flow, load_factor=lam)
    m.solve()
    ok = m.status_name == "OPTIMAL"
    m.dispose()
    return ok


def renumber(states):
    return [State(i, s.kind, s.element, s.desc) for i, s in enumerate(states)]


def conflict_set(system, all_states, lam, theta, relax_flow, log):
    """Deletion filter over the contingencies (the base case is always kept)."""
    base, conts = all_states[0], list(all_states[1:])
    if feasible(system, renumber([base] + conts), lam, theta, relax_flow):
        return None
    core = list(conts)
    t0 = time.time()
    for i, c in enumerate(conts):
        trial = [x for x in core if x != c]
        if not feasible(system, renumber([base] + trial), lam, theta, relax_flow):
            core = trial                                   # c is not needed for the conflict
        if (i + 1) % 25 == 0:
            log.info(f"    filter: {i + 1}/{len(conts)} tested, {len(core)} left ({time.time() - t0:.0f} s)")
    check = {c.desc: feasible(system, renumber([base] + [x for x in core if x != c]), lam, theta, relax_flow)
             for c in core}
    return core, check


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="matpower", help="(default: matpower)")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full contingency list (default)")
    ap.add_argument("--lambdas", type=float, nargs="+", default=VIOLATION_GRID,
                    help=f"load levels for the violation table (default: {' '.join(map(str, VIOLATION_GRID))})")
    ap.add_argument("--conflict-sets", action="store_true",
                    help="also find the minimal conflicting sets just above each limit (~10 min)")
    ap.add_argument("--out-root", default=os.path.join(ROOT, "reference", "results"),
                    help="results root (default: reference/results)")
    args = ap.parse_args(argv)

    out = os.path.join(args.out_root, args.source, args.formulation)
    log = get_logger(out)
    log.info(f"load_limits.py {' '.join(sys.argv[1:])}")
    s = load_system(args.source)
    s_cap = copy.deepcopy(s)
    s_cap.pmax = s.pmax * PMAX_RELAXED
    states = build_states(s, args.formulation, "all")
    log.info(f"{len(states)} states ({args.formulation}); nominal load {s.pd_nom.sum() * s.base_mva:,.0f} MW")

    # 1. lambda_max with each family relaxed --------------------------------------------------
    families = [("none (actual model)", s, THETA_MAX, False),
                ("flow limits", s, THETA_MAX, True),
                ("angle limits", s, THETA_RELAXED, False),
                ("generator capacity", s_cap, THETA_MAX, False),
                ("flow + angle", s, THETA_RELAXED, True),
                ("flow + capacity", s_cap, THETA_MAX, True),
                ("angle + capacity", s_cap, THETA_RELAXED, False)]
    rows = []
    for name, sysv, theta, rf in families:
        lm = lambda_max(sysv, states, theta, rf)
        rows.append({"relaxed": name, "lambda_max": None if lm is None else round(lm, 5),
                     "load_mw": None if lm is None else round(lm * s.pd_nom.sum() * s.base_mva, 1)})
        log.info(f"lambda_max, relaxed {name:22s}: {rows[-1]['lambda_max']} ({rows[-1]['load_mw']} MW)")
    lim = pd.DataFrame(rows)
    lim.to_csv(os.path.join(out, "load_limits.csv"), index=False)

    # 2. minimum flow-limit violation per lambda ------------------------------------------------
    m = make_model(s, states, THETA_MAX, False)
    m.set_objective("min_violation")
    vrows = []
    for lam in args.lambdas:
        m.set_load_factor(lam)
        m.solve()
        row = {"load_factor": lam, "load_mw": round(lam * s.pd_nom.sum() * s.base_mva, 1)}
        if m.status_name != "OPTIMAL":
            row["status"] = "infeasible even without flow limits"
        else:
            S = m.S.X * s.base_mva                                  # MW, NL x NS
            by_line = S.sum(axis=1)
            l, c = np.unravel_index(int(S.argmax()), S.shape)
            top = np.argsort(-by_line)[:3]
            row.update({"status": "feasible with overload" if S.sum() > 1e-6 else "feasible",
                        "total_overload_mw": round(S.sum(), 2),
                        "n_states": int((S.sum(axis=0) > 1e-6).sum()),
                        "n_lines": int((by_line > 1e-6).sum()),
                        "worst_mw": round(S.max(), 2), "worst_line": s.label[l],
                        "worst_state": states[c].desc,
                        "lines_by_overload": "; ".join(f"{s.label[k]} {by_line[k]:.1f}" for k in top if by_line[k] > 1e-6)})
        vrows.append(row)
        log.info(f"lambda={lam:.3f}: {row['status']}"
                 + (f", {row['total_overload_mw']} MW in {row['n_states']} states / {row['n_lines']} lines;"
                    f" worst {row['worst_mw']} MW on {row['worst_line']} ({row['worst_state']})"
                    if "total_overload_mw" in row else ""))
    m.dispose()
    pd.DataFrame(vrows).to_csv(os.path.join(out, "violation_by_lambda.csv"), index=False)

    # 3. minimal conflicting sets just above each limit ---------------------------------------
    if args.conflict_sets:
        for tag, relaxed_flow in [("all_limits", False), ("flow_relaxed", True)]:
            lm = lim.loc[lim.relaxed == ("flow limits" if relaxed_flow else "none (actual model)"), "lambda_max"].iloc[0]
            lam = round(lm + 0.002, 4)
            log.info(f"\nMinimal conflicting set at lambda = {lam} ({tag}):")
            res = conflict_set(s, states, lam, THETA_MAX, relaxed_flow, log)
            if res is None:
                log.info("  feasible: no conflict")
                continue
            core, check = res
            pd.DataFrame({"state": [c.desc for c in core], "kind": [c.kind for c in core],
                          "element": [c.element for c in core],
                          "feasible_without_it": [check[c.desc] for c in core]}).to_csv(
                os.path.join(out, f"conflict_set_{tag}.csv"), index=False)
            log.info(f"  base case + {[c.desc for c in core]}")
            log.info(f"  removing any one makes it feasible: {all(check.values())}")

    log.info(f"\nSaved to {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
