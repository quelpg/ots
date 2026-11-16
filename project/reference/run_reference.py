"""Reference case: cost of N-1 security on the original topology (K = 0) for a grid of load levels.

For each load factor lambda (every load = lambda x nominal load):
  1. unconstrained dispatch : no network, merit order
  2. DCOPF                  : base case with the network (no contingencies)
  3. SC-DCOPF               : base case + every contingency of the list
  base-case network cost = DCOPF - unconstrained dispatch
  security premium       = SC-DCOPF - DCOPF   (what switching tries to recover)
plus lambda_max, the highest load factor at which the SC-DCOPF is feasible (one LP, max lambda).

Output (<out-root>/<source>/<formulation>/):
  summary_lambda.csv                       one row per lambda (costs, premium, binding lines)
  contingencies/lambda<l>/K0/              SC-DCOPF solution (same files as model/run_ots.py)
  basecase/lambda<l>/K0/                   DCOPF solution
  run.log
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import OTSModel, unconstrained_dispatch_cost                  # noqa: E402
from model.data import load_system                                             # noqa: E402
from model.solution import export, get_logger, read_solution                  # noqa: E402
from model.states import CONFIG_NAME, EXCLUSIONS, build_states, summary_lines  # noqa: E402

GRID = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]

EPILOG = """examples (from project/):
  python reference/run_reference.py                                  # default grid, full list
  python reference/run_reference.py --lambdas 0.80 0.82 0.84 0.85     # other load levels
  python reference/run_reference.py --formulation redispatch_with_exclusions --out-root <folder>
"""


class _Quiet:
    def info(self, *_):
        pass


def binding_lines(system, sol, emerg_factor, tol=1e-6):
    """(lines at their limit in the base case, lines at their emergency limit in some contingency)."""
    rate = system.rate
    base = np.abs(sol.f[:, 0]) >= rate * (1 - tol)
    cont = (np.abs(sol.f[:, 1:]) >= (emerg_factor * rate)[:, None] * (1 - tol)).any(axis=1) \
        if sol.f.shape[1] > 1 else np.zeros_like(base)
    return int(base.sum()), int(cont.sum())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="matpower", help="processed dataset (default: matpower)")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full contingency list (default)")
    ap.add_argument("--lambdas", type=float, nargs="+", default=GRID,
                    help=f"load factors (default: {' '.join(map(str, GRID))})")
    ap.add_argument("--out-root", default=os.path.join(ROOT, "reference", "results"),
                    help="results root (default: reference/results)")
    args = ap.parse_args(argv)

    out = os.path.join(args.out_root, args.source, args.formulation)
    log = get_logger(out)
    log.info(f"run_reference.py {' '.join(sys.argv[1:])}")
    log.info(f"output -> {out}")
    s = load_system(args.source)
    for line in s.summary_lines():
        log.info(line)
    st_sc = build_states(s, args.formulation, "all")
    for line in summary_lines(s, st_sc, args.formulation, "all"):
        log.info(line)

    sc = OTSModel(s, st_sc)
    dc = OTSModel(s, build_states(s, args.formulation, "none"))
    for line in sc.size_lines():
        log.info(line)

    # lambda_max of the original topology (one LP)
    sc.open_lines([])
    sc.set_objective("max_load")
    sc.solve()
    lam_max = float(sc.lam.X[0]) if sc.status_name == "OPTIMAL" else None
    sc.set_objective("cost")
    log.info(f"lambda_max (SC-DCOPF feasible up to) = {lam_max:.5f} "
             f"({lam_max * s.pd_nom.sum() * s.base_mva:,.1f} MW)")

    rows = []
    for lam in args.lambdas:
        tag = f"lambda{lam:.3f}"
        ud = unconstrained_dispatch_cost(s, lam)
        row = {"load_factor": lam, "load_mw": round(lam * s.pd_nom.sum() * s.base_mva, 1),
               "unconstrained_usd_h": None if ud is None else round(ud, 2)}
        for name, model, cfg in [("dcopf", dc, "basecase"), ("scdcopf", sc, "contingencies")]:
            model.set_load_factor(lam)
            model.open_lines([])
            model.solve()
            sol = read_solution(model, duals=True)
            row[f"{name}_usd_h"] = None if sol is None else round(sol.cost, 2)
            if sol is not None:
                nb, nc = binding_lines(s, sol, model.emerg_factor)
                row[f"{name}_lines_at_limit_base"] = nb
                if name == "scdcopf":
                    row["scdcopf_lines_at_limit_contingency"] = nc
                export(_Quiet(), model, sol, os.path.join(out, cfg, tag, "K0"),
                       meta={"formulation": args.formulation, "contingencies": "all" if cfg != "basecase" else "none",
                             "source": args.source})
        d, c = row.get("dcopf_usd_h"), row.get("scdcopf_usd_h")
        row["network_cost_usd_h"] = None if d is None or ud is None else round(d - ud, 2)
        row["security_premium_usd_h"] = None if d is None or c is None else round(c - d, 2)
        row["security_premium_pct"] = None if d is None or c is None else round(100 * (c - d) / d, 2)
        rows.append(row)
        log.info(f"lambda={lam:.3f} ({row['load_mw']:,.0f} MW): unconstrained {row['unconstrained_usd_h']} | "
                 f"DCOPF {d} | SC-DCOPF {'infeasible' if c is None else c} | "
                 f"premium {row['security_premium_usd_h']} ({row['security_premium_pct']}%)")

    tab = pd.DataFrame(rows)
    tab.to_csv(os.path.join(out, "summary_lambda.csv"), index=False)
    pd.set_option("display.width", 250)
    log.info("\nReference by load level (K = 0, $/h):\n" + tab.to_string(index=False))
    log.info(f"Saved summary_lambda.csv and the solutions to {out}/")
    sc.dispose()
    dc.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
