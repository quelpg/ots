"""Decompose cost and curtailment of every saved topology of a CS3 case into layers (same topology).

For one renewable scenario and penetration level, every topology saved in the case folder
(<results>/.../lambda<l>_ren-<scenario>_p<pct>/: K0 of run_scenarios.py, heuristic/<criterion>/K<n>/,
and MILP K<k>/) is evaluated with that topology fixed:
  unconstrained dispatch (no network)  -> energy curtailment (ENE)
  DCOPF (base case only)               -> + congestion curtailment (REL: transmission bottleneck)
  SC-DCOPF (full N-1 list)             -> + security curtailment (CNF: N-1 margin)
congestion = DCOPF - energy, security = SC-DCOPF - DCOPF, for curtailment and cost. The layers are
computed on the same topology because switching may reduce one part and increase the other.

Output: decomposition.csv in the case folder, and the console table (best topology per source and K).
"""

import argparse
import glob
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import OTSModel, unconstrained_dispatch                       # noqa: E402
from model.data import case_tag, load_case                                     # noqa: E402
from model.solution import curtailment, read_solution, saved_topology          # noqa: E402
from model.states import EXCLUSIONS, build_states                              # noqa: E402

EPILOG = """examples (from project/):
  python cs3-renewables/decompose.py --renewables concentrated --penetration 0.30
  python cs3-renewables/decompose.py --renewables distributed --penetration 0.50
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--renewables", required=True, help="scenario name (cs3-renewables/scenarios/)")
    ap.add_argument("--penetration", type=float, required=True, help="share of the load, e.g. 0.30")
    ap.add_argument("--load-factor", type=float, default=0.80, help="lambda (default: 0.80)")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full contingency list (default)")
    ap.add_argument("--results", default=os.path.join(ROOT, "cs3-renewables", "results"),
                    help="results root (default: cs3-renewables/results)")
    args = ap.parse_args(argv)

    case_dir = os.path.join(args.results, "matpower", args.formulation, "contingencies",
                            case_tag(args.load_factor, args.renewables, args.penetration))
    folders = sorted(set(glob.glob(os.path.join(case_dir, "K*")) +
                         glob.glob(os.path.join(case_dir, "heuristic", "*", "K*"))))
    if not folders:
        print(f"No saved topology in {case_dir}")
        return 1
    s = load_case("matpower", args.renewables, args.penetration, args.load_factor)
    _, curt_energy = unconstrained_dispatch(s, args.load_factor)
    cost_energy, _ = unconstrained_dispatch(s, args.load_factor)
    dc = OTSModel(s, build_states(s, args.formulation, "none"), load_factor=args.load_factor)
    sc = OTSModel(s, build_states(s, args.formulation, "all"), load_factor=args.load_factor)

    rows = []
    for d in folders:
        if not os.path.exists(os.path.join(d, "line_loading.csv")):
            continue
        ids, _ = saved_topology(d)
        rel = os.path.relpath(d, case_dir).replace("\\", "/")
        src = ("no switching" if rel == "K0" else "MILP") if rel.startswith("K") else rel.split("/")[1]
        row = {"topology": rel, "source": src, "K": len(ids)}
        for name, m in [("dcopf", dc), ("scdcopf", sc)]:
            m.open_lines(ids)
            m.solve()
            sol = read_solution(m)
            row[f"{name}_usd_h"] = None if sol is None else round(sol.cost, 2)
            row[f"{name}_curt_mw"] = None if sol is None else round(curtailment(s, sol)[1], 2)
        dcu, scu = row["dcopf_curt_mw"], row["scdcopf_curt_mw"]
        row.update({
            "curt_energy_mw": round(curt_energy, 2),
            "curt_congestion_mw": None if dcu is None else round(dcu - curt_energy, 2),
            "curt_security_mw": None if dcu is None or scu is None else round(scu - dcu, 2),
            "cost_network_usd_h": None if row["dcopf_usd_h"] is None else round(row["dcopf_usd_h"] - cost_energy, 2),
            "cost_security_usd_h": None if row["dcopf_usd_h"] is None or row["scdcopf_usd_h"] is None
            else round(row["scdcopf_usd_h"] - row["dcopf_usd_h"], 2),
            "open_lines": " ".join(s.label[l] for l in ids)})
        rows.append(row)
    dc.dispose()
    sc.dispose()
    tab = pd.DataFrame(rows).sort_values(["source", "K"])
    tab.to_csv(os.path.join(case_dir, "decomposition.csv"), index=False)
    pd.set_option("display.width", 250)
    cols = ["source", "K", "scdcopf_usd_h", "scdcopf_curt_mw", "curt_congestion_mw", "curt_security_mw",
            "cost_network_usd_h", "cost_security_usd_h"]
    print(f"{args.renewables} {100 * args.penetration:.0f}% (lambda {args.load_factor}): unconstrained cost "
          f"{cost_energy:,.2f} $/h, energy curtailment {curt_energy:.2f} MW")
    print(tab[cols].to_string(index=False))
    print(f"\nSaved {os.path.join(case_dir, 'decomposition.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
