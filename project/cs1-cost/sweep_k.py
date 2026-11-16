"""K sweep of the OTS-SC-DCOPF MILP at one load level, with warm start (CS1).

For each K (maximum number of open lines), in increasing order:
  1. warm start = cheapest saved topology with K' <= K, searched in the results of this sweep
     (chained: K starts from the best of K - 1, ...) and in the heuristic results of every
     criterion (heuristics/sequential.py, folder .../lambda<l>/heuristic/<criterion>/K<n>/);
  2. solve the MILP with a time limit (one model, built once; only K changes);
  3. export the solution to <out-root>/<source>/<formulation>/contingencies/lambda<l>/K<k>/.
A run.log and summary_sweep.csv (cost, bound, gap, time, warm start per K) are written to
<...>/lambda<l>/. Re-running a K overwrites its folder; the warm start then includes the
previous result of that K.
"""

import argparse
import os
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import MILP_PARAMS, OTSModel                                   # noqa: E402
from model.data import case_tag, load_case                                      # noqa: E402
from model.solution import cheapest_saved, export, get_logger, read_solution, report   # noqa: E402
from model.states import EXCLUSIONS, build_states, summary_lines                # noqa: E402

CRITERIA = ["LP0", "LP", "PD", "PW", "TD"]

EPILOG = """examples (from project/, in your own PowerShell: each K takes up to --time-limit):
  python cs1-cost/sweep_k.py --load-factor 0.80 --k-min 1 --k-max 8 --time-limit 1800
  python cs1-cost/sweep_k.py --load-factor 0.85 --k-min 3 --k-max 3 --time-limit 3600 --threads 8
Run the heuristic first (it provides the warm starts):
  python heuristics/sequential.py --load-factor 0.80 --out-root cs1-cost/results
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--load-factor", type=float, required=True, help="lambda")
    ap.add_argument("--renewables", default=None,
                    help="renewable scenario (cs3-renewables/scenarios/<name>.csv, or a CSV path); default: none")
    ap.add_argument("--penetration", type=float, default=0.0,
                    help="renewable available power as a share of lambda x nominal load, e.g. 0.20 (default: 0)")
    ap.add_argument("--k-min", type=int, default=1, help="first K (default: 1)")
    ap.add_argument("--k-max", type=int, default=8, help="last K (default: 8)")
    ap.add_argument("--time-limit", type=float, default=1800, help="[s] per K (default: 1800)")
    ap.add_argument("--threads", type=int, default=None, help="(default: all cores)")
    ap.add_argument("--norel-time", type=float, default=0,
                    help="[s] NoRel heuristic; 0 = off, the warm start replaces it (default: 0)")
    ap.add_argument("--mip-focus", type=int, default=MILP_PARAMS["MIPFocus"], help="(default: 1)")
    ap.add_argument("--mip-gap", type=float, default=MILP_PARAMS["MIPGap"], help="(default: 1e-4)")
    ap.add_argument("--cuts", type=int, default=MILP_PARAMS["Cuts"], help="(default: 1)")
    ap.add_argument("--no-heuristic-start", action="store_true",
                    help="do not use the heuristic topologies as warm start (only the chained sweep)")
    ap.add_argument("--source", default="matpower", help="(default: matpower)")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full contingency list (default)")
    ap.add_argument("--out-root", default=os.path.join(ROOT, "cs1-cost", "results"),
                    help="results root (default: cs1-cost/results)")
    args = ap.parse_args(argv)

    lam_dir = os.path.join(args.out_root, args.source, args.formulation, "contingencies",
                           case_tag(args.load_factor, args.renewables, args.penetration))
    log = get_logger(lam_dir)
    log.info(f"sweep_k.py {' '.join(sys.argv[1:])}")
    log.info(f"output -> {lam_dir}")
    s = load_case(args.source, args.renewables, args.penetration, args.load_factor)
    for line in s.summary_lines():
        log.info(line)
    states = build_states(s, args.formulation, "all")
    for line in summary_lines(s, states, args.formulation, "all"):
        log.info(line)

    model = OTSModel(s, states, load_factor=args.load_factor, output=True)
    model.free_topology(args.k_min)
    for line in model.size_lines():
        log.info(line)
    heur = [] if args.no_heuristic_start else \
        [os.path.join(lam_dir, "heuristic", c) for c in CRITERIA if os.path.isdir(os.path.join(lam_dir, "heuristic", c))]
    log.info(f"warm-start sources: this sweep + {len(heur)} heuristic criteria "
             f"({[os.path.basename(h) for h in heur]})")

    rows, t_all = [], time.time()
    for K in range(args.k_min, args.k_max + 1):
        out_k = os.path.join(lam_dir, f"K{K}")
        os.makedirs(out_k, exist_ok=True)
        model.free_topology(K)
        model.m.reset()                                   # forget the previous K's search
        best = cheapest_saved([lam_dir] + heur, K)
        if best is not None:
            model.warm_start(best[1])
            ws = f"{os.path.relpath(best[0], lam_dir)} (${best[2]:,.2f}/h)"
        else:
            ws = "none"
        log.info(f"\n===== K = {K} | warm start: {ws}: open {[s.label[l] for l in best[1]] if best else []}")
        model.set_params(TimeLimit=args.time_limit, Threads=args.threads, MIPGap=args.mip_gap,
                         MIPFocus=args.mip_focus, NoRelHeurTime=args.norel_time, Cuts=args.cuts,
                         LogFile=os.path.join(out_k, "gurobi.log"))
        t0 = time.time()
        model.solve()
        sol = read_solution(model)
        report(log, model, sol)
        export(log, model, sol, out_k, meta={"formulation": args.formulation, "contingencies": "all",
                                             "source": args.source, "warm_start": ws})
        row = {"K": K, "status": model.status_name, "runtime_s": round(time.time() - t0, 1),
               "warm_start": ws, "warm_start_cost": None if best is None else round(best[2], 2)}
        if sol is not None:
            row.update({"cost": round(sol.cost, 2), "best_bound": round(sol.bound, 2),
                        "gap_pct": round(100 * sol.gap, 3), "n_open": len(sol.open_ids),
                        "open_lines": " ".join(s.label[l] for l in sol.open_ids)})
        rows.append(row)
        log.info(f"K={K}: {row.get('cost', 'no solution')} $/h, bound {row.get('best_bound')}, "
                 f"gap {row.get('gap_pct')}%, {row['runtime_s']} s")
        pd.DataFrame(rows).to_csv(os.path.join(lam_dir, "summary_sweep.csv"), index=False)

    tab = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    log.info(f"\nK sweep at lambda = {args.load_factor} ({time.time() - t_all:.0f} s):\n"
             + tab.drop(columns=["open_lines"], errors="ignore").to_string(index=False))
    model.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
