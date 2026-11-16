"""Highest load factor each saved topology supports under N-1 (CS2).

For every topology saved by the heuristic (or the MILP) in <results>/.../lambda<l>/heuristic/<criterion>/K<n>/
(and any other folder with line_loading.csv given with --dirs), solve the max-lambda LP with that
topology fixed and every limit (no slacks). This gives "switching extends the maximum N-1 load from
lambda_max = 0.850 (original topology) to X with these K open lines".

Output: topology_lambda_max.csv next to the heuristic folder, and the console table.
"""

import argparse
import glob
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import OTSModel                                           # noqa: E402
from model.data import load_system                                         # noqa: E402
from model.solution import saved_topology                                  # noqa: E402
from model.states import EXCLUSIONS, build_states                          # noqa: E402

EPILOG = """example (from project/):
  python cs2-feasibility/topology_lambda_max.py --load-factor 0.86
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--load-factor", type=float, required=True,
                    help="lambda of the heuristic run whose topologies are evaluated")
    ap.add_argument("--source", default="matpower", help="(default: matpower)")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full list (default)")
    ap.add_argument("--results", default=os.path.join(ROOT, "cs2-feasibility", "results"),
                    help="results root (default: cs2-feasibility/results)")
    args = ap.parse_args(argv)

    lam_dir = os.path.join(args.results, args.source, args.formulation, "contingencies",
                           f"lambda{args.load_factor:.3f}")
    folders = sorted(glob.glob(os.path.join(lam_dir, "heuristic", "*", "K*")) + glob.glob(os.path.join(lam_dir, "K*")))
    s = load_system(args.source)
    model = OTSModel(s, build_states(s, args.formulation, "all"))
    model.set_objective("max_load")
    rows = []
    for d in folders:
        ids, cost = saved_topology(d)
        model.open_lines(ids)
        model.solve()
        lm = float(model.lam.X[0]) if model.status_name == "OPTIMAL" else None
        rel = os.path.relpath(d, lam_dir).replace("\\", "/")
        rows.append({"topology": rel, "K": len(ids), "cost_at_run_lambda": cost,
                     "lambda_max": None if lm is None else round(lm, 5),
                     "load_mw": None if lm is None else round(lm * s.pd_nom.sum() * s.base_mva, 1),
                     "open_lines": " ".join(s.label[l] for l in ids)})
    model.dispose()
    tab = pd.DataFrame(rows).sort_values(["K", "lambda_max"], ascending=[True, False])
    tab.to_csv(os.path.join(lam_dir, "topology_lambda_max.csv"), index=False)
    pd.set_option("display.width", 220)
    print(f"Original topology: lambda_max = 0.85013. Topologies of {lam_dir}:")
    print(tab.drop(columns=["open_lines"]).to_string(index=False))
    best = tab.loc[tab.lambda_max.idxmax()]
    print(f"\nHighest: {best.topology} (K = {best.K}): lambda_max = {best.lambda_max} ({best.load_mw} MW); "
          f"open {best.open_lines}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
