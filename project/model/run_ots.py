"""Solve one SC-DCOPF / OTS-SC-DCOPF case from the command line (replaces running the notebook).

Output folder: <out-root>/<source>/<formulation>/<config>/lambda<load factor>/<K tag>/
with summary.csv, dispatch.csv, line_loading.csv, angles.csv, switching.csv, run.log, gurobi.log.
"""

import argparse
import os
import sys
import time

if __package__ in (None, ""):                       # allow `python model/run_ots.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "model"

from model.build import MILP_PARAMS, OTSModel
from model.data import case_tag, load_case
from model.solution import cheapest_saved, export, get_logger, read_solution, report
from model.states import CONFIG_NAME, EXCLUSIONS, build_states, summary_lines

EPILOG = """examples (from project/):
  # SC-DCOPF on the original topology, full list, lambda = 0.85
  python model/run_ots.py --load-factor 0.85 --out-root reference/results
  # OTS MILP with K = 3, 30 min, warm start from the cheapest saved K' <= 3
  python model/run_ots.py --load-factor 0.85 --K 3 --time-limit 1800 --out-root cs1-cost/results
  # fixed topology (lines 64-65 and 77-80 open), reduced list, lambda = 1
  python model/run_ots.py --formulation redispatch_with_exclusions --open 96 122 --out-root /tmp/x
  # maximum load factor of the original topology under N-1
  python model/run_ots.py --objective max_load --out-root reference/results
  # K_min at lambda = 0.90: fewest open lines that make N-1 feasible (warm start: heuristic)
  python model/run_ots.py --objective min_switching --load-factor 0.90 --time-limit 3600       --warm-start-dir heuristics/results/... --out-root cs2-feasibility/results
"""


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_argument_group("case")
    g.add_argument("--source", default="matpower", help="processed dataset (default: matpower)")
    g.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                   help="redispatch_only = full contingency list (default); "
                        "redispatch_with_exclusions = reduced list (heuristic benchmark)")
    g.add_argument("--contingencies", default="all", choices=list(CONFIG_NAME),
                   help="states besides the base case: all (default), lines, gens, none")
    g.add_argument("--load-factor", type=float, default=1.0,
                   help="lambda: every load = lambda x nominal load (default: 1.0)")
    g.add_argument("--renewables", default=None,
                   help="renewable scenario (cs3-renewables/scenarios/<name>.csv, or a CSV path); default: none")
    g.add_argument("--penetration", type=float, default=0.0,
                   help="renewable available power as a share of lambda x nominal load, e.g. 0.20 (default: 0)")
    g.add_argument("--objective", default="cost", choices=["cost", "max_load", "min_switching"],
                   help="cost (default); max_load (maximize lambda, --load-factor is ignored); "
                        "min_switching (MILP: minimum number of open lines that makes N-1 feasible "
                        "at --load-factor, i.e. K_min; --K is then the maximum it may open)")
    t = ap.add_argument_group("topology (choose one; default: original topology, K = 0)")
    t.add_argument("--K", type=int, default=None, help="MILP: at most K open lines")
    t.add_argument("--K-unlimited", action="store_true", help="MILP without switching limit")
    t.add_argument("--open", type=int, nargs="*", default=None, metavar="BRANCH_ID",
                   help="LP on a fixed topology: branch ids to open")
    t.add_argument("--min-open", type=int, default=0,
                   help="min_switching: cut sum(1 - z) >= this, e.g. a K proven infeasible + 1 (default: 0)")
    s = ap.add_argument_group("MILP solver (defaults = the K sweep settings)")
    s.add_argument("--time-limit", type=float, default=3600, help="[s] (default: 3600)")
    s.add_argument("--mip-gap", type=float, default=MILP_PARAMS["MIPGap"], help="(default: 1e-4)")
    s.add_argument("--mip-focus", type=int, default=MILP_PARAMS["MIPFocus"], help="(default: 1)")
    s.add_argument("--norel-time", type=float, default=MILP_PARAMS["NoRelHeurTime"],
                   help="[s] NoRel heuristic before the root LP, 0 = off (default: 300)")
    s.add_argument("--cuts", type=int, default=MILP_PARAMS["Cuts"], help="(default: 1)")
    s.add_argument("--threads", type=int, default=None, help="(default: all cores)")
    s.add_argument("--warm-start", default="auto",
                   help="auto (default): cheapest saved result with K' <= K in this lambda folder "
                        "and in --warm-start-dir; none; or a result folder (with line_loading.csv)")
    s.add_argument("--warm-start-dir", action="append", default=[],
                   help="extra folder with K<k>/ subfolders to search (repeatable), "
                        "e.g. heuristic results")
    o = ap.add_argument_group("output")
    o.add_argument("--out-root", required=True, help="results root of the study case, e.g. cs1-cost/results")
    o.add_argument("--out-dir", default=None, help="override the full output folder")
    return ap.parse_args(argv)


def k_tag(args):
    if args.objective == "min_switching":
        return "Kmin"
    if args.open is not None:
        return "open_" + "-".join(map(str, sorted(args.open))) if args.open else "K0"
    if args.K_unlimited:
        return "K_inf"
    return "K0" if args.K is None else f"K{args.K}"


def main(argv=None):
    args = parse_args(argv)
    lam_tag = "max_load" if args.objective == "max_load" else case_tag(args.load_factor, args.renewables, args.penetration)
    base_dir = os.path.join(args.out_root, args.source, args.formulation, CONFIG_NAME[args.contingencies], lam_tag)
    out_dir = args.out_dir or os.path.join(base_dir, k_tag(args))
    log = get_logger(out_dir)
    log.info(f"run_ots.py {' '.join(sys.argv[1:])}")
    log.info(f"output -> {out_dir}")

    system = load_case(args.source, args.renewables, args.penetration, args.load_factor)
    for line in system.summary_lines():
        log.info(line)
    states = build_states(system, args.formulation, args.contingencies)
    for line in summary_lines(system, states, args.formulation, args.contingencies):
        log.info(line)
    log.info(f"radial branches fixed closed: {[system.label[l] for l in range(system.n_branch) if system.is_bridge[l]]}")

    model = OTSModel(system, states, load_factor=args.load_factor, output=True)
    milp = args.K is not None or args.K_unlimited or args.objective == "min_switching"
    if milp:
        model.free_topology(None if args.K_unlimited else args.K)
        if args.objective == "min_switching":
            model.set_min_open(args.min_open)
        model.set_params(MIPGap=args.mip_gap, MIPFocus=args.mip_focus, NoRelHeurTime=args.norel_time,
                         Cuts=args.cuts)
        log.info(f"MILP: |L^S| = {len(model.LS)} switchable, K = {'inf' if args.K is None else args.K}"
                 + (f", min open = {args.min_open}" if args.objective == "min_switching" else ""))
    else:
        model.open_lines(args.open or [])
        log.info(f"LP on a fixed topology: open {[system.label[l] for l in (args.open or [])] or 'none'}")
    if args.objective != "cost":
        model.set_objective(args.objective)
    for line in model.size_lines():
        log.info(line)

    if milp and args.warm_start != "none":
        if args.warm_start == "auto":
            kmax = len(model.LS) if args.K is None else args.K
            key = {"min_switching": "n_open", "max_load": "lambda"}.get(args.objective, "cost")
            best = cheapest_saved([base_dir] + args.warm_start_dir, kmax, key)
        else:
            from model.solution import saved_topology
            ids, cost = saved_topology(args.warm_start)
            best = (args.warm_start, ids, cost)
        if best is None:
            log.info("Warm start: none (no saved result found)")
        else:
            model.warm_start(best[1])
            log.info(f"Warm start from {best[0]} (cost ${best[2]:,.2f}/h): "
                     f"open {[system.label[l] for l in best[1]]}")

    model.set_params(TimeLimit=args.time_limit, Threads=args.threads,
                     LogFile=os.path.join(out_dir, "gurobi.log"))
    t0 = time.time()
    model.solve()
    log.info(f"solve finished: {model.status_name} in {time.time() - t0:.1f} s")
    sol = read_solution(model)
    report(log, model, sol)
    export(log, model, sol, out_dir, meta={"formulation": args.formulation,
                                           "contingencies": args.contingencies, "source": args.source})
    model.dispose()
    return 0 if sol is not None else 1


if __name__ == "__main__":
    sys.exit(main())
