"""Binding flow limits of a CS3 case on a fixed topology (where the renewable power gets stuck).

For one renewable scenario and penetration level, the DCOPF (base case only) and the SC-DCOPF (full
N-1 list) are solved on a fixed topology (K0 or any saved heuristic/MILP folder of the case). For
each one it prints:
  1. the binding flow limits, |f_lc| >= 99.9% of the limit (F_l in the base case, 1.15 F_l in a
     contingency), with state, branch, flow, limit and dual mu (d cost / d limit, $/MWh), and the
     branches ranked by the sum of |mu| over the states (top N);
  2. the base-case flow on the watched branches (default: the 5 branches between the south-east
     region and the rest of the system) and their sum;
  3. the renewable output per bus (available, generated, curtailed).
The duals measure how much the cost would drop per MW of extra capacity on that branch, so the
branches with the largest sum of |mu| are the ones holding the renewable power back.

Output: <case>/diagnostics/binding_<layer>_<topology>.csv (one row per binding limit) and the console.
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import OTSModel                                              # noqa: E402
from model.data import case_tag, load_case                                     # noqa: E402
from model.solution import curtailment, read_solution, saved_topology          # noqa: E402
from model.states import EXCLUSIONS, build_states                              # noqa: E402

# south-east region (buses 80-112) <-> rest of the system: 77-80 (x2), 79-80, 68-81, 77-82
INTERCONNECTION = [122, 123, 124, 125, 127]

EPILOG = """examples (from project/):
  python cs3-renewables/binding_constraints.py --renewables concentrated --penetration 0.30
  python cs3-renewables/binding_constraints.py --renewables concentrated --penetration 0.30 --topology heuristic/TD/K10
  python cs3-renewables/binding_constraints.py --renewables regional_far --penetration 0.50 --top 20
"""


def binding_table(s, states, sol, emerg_factor, tol=0.999):
    """One row per binding flow limit (state, branch) of an LP solved with duals."""
    rows = []
    for st in states:
        c = st.id
        lim = s.rate * (1.0 if c == 0 else emerg_factor) * sol.z
        f = sol.f[:, c]
        hit = np.flatnonzero((lim > 0) & (np.abs(f) >= tol * lim))
        for l in hit:
            rows.append({"state": c, "state_desc": st.desc, "branch_id": int(l), "label": s.label[l],
                         "f_mw": round(f[l] * s.base_mva, 2), "limit_mw": round(lim[l] * s.base_mva, 2),
                         "mu_usd_mwh": round(sol.mu[l, c] / s.base_mva, 4)})
    return pd.DataFrame(rows, columns=["state", "state_desc", "branch_id", "label", "f_mw", "limit_mw",
                                       "mu_usd_mwh"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--renewables", required=True, help="scenario name (cs3-renewables/scenarios/)")
    ap.add_argument("--penetration", type=float, required=True, help="share of the load, e.g. 0.30")
    ap.add_argument("--load-factor", type=float, default=0.80, help="lambda (default: 0.80)")
    ap.add_argument("--topology", default="K0",
                    help="saved folder inside the case, e.g. K0 or heuristic/TD/K10 (default: K0)")
    ap.add_argument("--top", type=int, default=15, help="branches listed in the ranking (default: 15)")
    ap.add_argument("--watch", type=int, nargs="+", default=INTERCONNECTION,
                    help="branch ids whose base-case flow is listed (default: south-east interconnection "
                         + " ".join(map(str, INTERCONNECTION)) + ")")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full contingency list (default)")
    ap.add_argument("--results", default=os.path.join(ROOT, "cs3-renewables", "results"),
                    help="results root (default: cs3-renewables/results)")
    args = ap.parse_args(argv)

    case_dir = os.path.join(args.results, "matpower", args.formulation, "contingencies",
                            case_tag(args.load_factor, args.renewables, args.penetration))
    topo_dir = os.path.join(case_dir, args.topology)
    if args.topology == "K0":
        open_ids = []
    elif os.path.exists(os.path.join(topo_dir, "line_loading.csv")):
        open_ids, _ = saved_topology(topo_dir)
    else:
        print(f"No saved topology in {topo_dir}")
        return 1
    s = load_case("matpower", args.renewables, args.penetration, args.load_factor)
    out_dir = os.path.join(case_dir, "diagnostics")
    os.makedirs(out_dir, exist_ok=True)
    tag = args.topology.replace("/", "-")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    print(f"=== {args.renewables} {100 * args.penetration:.0f}% (lambda {args.load_factor}), topology "
          f"{args.topology} (open: {' '.join(s.label[l] for l in open_ids) or 'none'}) ===")

    for layer, cont in [("dcopf", "none"), ("scdcopf", "all")]:
        states = build_states(s, args.formulation, cont)
        m = OTSModel(s, states, load_factor=args.load_factor)
        m.open_lines(open_ids)
        m.solve()
        sol = read_solution(m, duals=True)
        if sol is None:
            print(f"\n[{layer}] {m.status_name}")
            m.dispose()
            continue
        avail, curt = curtailment(s, sol)
        print(f"\n[{layer.upper()}] cost {sol.cost:,.2f} $/h | renewable {avail:.1f} MW available, "
              f"{curt:.2f} MW curtailed | {len(states)} states")

        tab = binding_table(s, states, sol, m.emerg_factor)
        tab.to_csv(os.path.join(out_dir, f"binding_{layer}_{tag}.csv"), index=False)
        print(f"binding flow limits: {len(tab)} in {tab['state'].nunique() if len(tab) else 0} states")
        if len(tab):
            rank = (tab.assign(abs_mu=tab["mu_usd_mwh"].abs())
                    .groupby(["branch_id", "label"], as_index=False)
                    .agg(n_states=("state", "size"), sum_abs_mu=("abs_mu", "sum"),
                         max_abs_mu=("abs_mu", "max"), limit_base_mw=("limit_mw", "min"))
                    .sort_values("sum_abs_mu", ascending=False).head(args.top))
            rank["sum_abs_mu"] = rank["sum_abs_mu"].round(3)
            rank["max_abs_mu"] = rank["max_abs_mu"].round(3)
            print(f"branches ranked by sum of |mu| over the states (top {args.top}):")
            print(rank.to_string(index=False))
            top_rows = tab.reindex(tab["mu_usd_mwh"].abs().sort_values(ascending=False).index).head(args.top)
            print(f"largest single binding limits (top {args.top}):")
            print(top_rows.to_string(index=False))

        f0 = sol.f0 * s.base_mva
        watch = pd.DataFrame({"branch_id": args.watch, "label": [s.label[l] for l in args.watch],
                              "z": sol.z[args.watch], "f_mw": f0[args.watch].round(2),
                              "rate_mw": (s.rate[args.watch] * s.base_mva).round(1)})
        watch["loading_pct"] = (100 * watch["f_mw"].abs() / watch["rate_mw"]).round(1)
        print(f"base-case flow on the watched branches (sum of f = {watch['f_mw'].sum():.1f} MW, "
              f"sum of |f| = {watch['f_mw'].abs().sum():.1f} MW, sum of ratings = {watch['rate_mw'].sum():.0f} MW):")
        print(watch.to_string(index=False))

        ren = np.flatnonzero(s.is_renewable)
        rt = pd.DataFrame({"bus": s.bus[s.gen_bus[ren]],
                           "available_mw": (s.pmax[ren] * s.base_mva).round(2),
                           "generated_mw": (sol.p0[ren] * s.base_mva).round(2)})
        rt["curtailed_mw"] = (rt["available_mw"] - rt["generated_mw"]).round(2)
        print("renewable output per bus (base case):")
        print(rt.to_string(index=False))
        m.dispose()
    print(f"\nSaved {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
