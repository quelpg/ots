"""CS3 reference: renewable scenarios on the original topology (K = 0) at a fixed load level.

For every scenario (cs3-renewables/scenarios/<name>.csv) and penetration level (share of the
load lambda x nominal load), three layers, as in the reference case:
  unconstrained dispatch (no network) -> energy curtailment (more renewable than load)
  DCOPF (base case, network)          -> curtailment caused by the network in the base case
  SC-DCOPF (full N-1 list)            -> curtailment caused by the network and N-1 security
Curtailment C = sum_r (Gbar_r - P_r,0) [MW]; only the total is reported (its split among units
may not be unique). By type (layers): energy = no-network curtailment (ENE); congestion = DCOPF -
energy (REL, transmission bottleneck); security = SC-DCOPF - DCOPF (CNF, N-1 margin). The SC-DCOPF solution of each case is saved (same files as model/run_ots.py).

Output: <out-root>/matpower/redispatch_only/summary_scenarios_lambda<l>.csv and run.log.
"""

import argparse
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import OTSModel, unconstrained_dispatch                       # noqa: E402
from model.data import add_renewables, case_tag, load_system                   # noqa: E402
from model.solution import curtailment, export, get_logger, read_solution     # noqa: E402
from model.states import EXCLUSIONS, build_states                              # noqa: E402

SCENARIOS = ["concentrated", "distributed"]
LEVELS = [0.10, 0.20, 0.30, 0.40, 0.50]

EPILOG = """examples (from project/):
  python cs3-renewables/run_scenarios.py                                   # lambda 0.80, both scenarios, 10-50%
  python cs3-renewables/run_scenarios.py --levels 0.20 0.30
"""


class _Quiet:
    def info(self, *_):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--load-factor", type=float, default=0.80, help="lambda (default: 0.80)")
    ap.add_argument("--scenarios", nargs="+", default=SCENARIOS, help=f"(default: {' '.join(SCENARIOS)})")
    ap.add_argument("--levels", type=float, nargs="+", default=LEVELS,
                    help="penetration levels, share of the load (default: 0.10 ... 0.50)")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full contingency list (default)")
    ap.add_argument("--out-root", default=os.path.join(ROOT, "cs3-renewables", "results"),
                    help="results root (default: cs3-renewables/results)")
    args = ap.parse_args(argv)

    out = os.path.join(args.out_root, "matpower", args.formulation)
    log = get_logger(out)
    log.info(f"run_scenarios.py {' '.join(sys.argv[1:])}")
    base = load_system("matpower")
    lam = args.load_factor
    load_mw = lam * base.pd_nom.sum() * base.base_mva
    rows = []
    for name in ["none"] + args.scenarios:
        for pen in ([0.0] if name == "none" else args.levels):
            s = base if name == "none" else add_renewables(base, name, pen, lam)
            row = {"scenario": name, "penetration_pct": round(100 * pen), "load_mw": round(load_mw, 1),
                   "renewable_available_mw": round(float(s.pmax[s.is_renewable].sum()) * s.base_mva, 1)}
            ud_cost, ud_curt = unconstrained_dispatch(s, lam)
            row.update({"unconstrained_usd_h": round(ud_cost, 2), "unconstrained_curtailment_mw": round(ud_curt, 2)})
            for layer, cont in [("dcopf", "none"), ("scdcopf", "all")]:
                states = build_states(s, args.formulation, cont)
                m = OTSModel(s, states, load_factor=lam)
                m.solve()
                sol = read_solution(m)
                if sol is None:
                    row[f"{layer}_usd_h"] = None
                    row[f"{layer}_curtailment_mw"] = None
                else:
                    row[f"{layer}_usd_h"] = round(sol.cost, 2)
                    row[f"{layer}_curtailment_mw"] = round(curtailment(s, sol)[1], 2)
                    if layer == "scdcopf":
                        tag = case_tag(lam, None if name == "none" else name, pen)
                        export(_Quiet(), m, sol, os.path.join(out, "contingencies", tag, "K0"),
                               meta={"formulation": args.formulation, "contingencies": "all"})
                m.dispose()
            d, c = row["dcopf_usd_h"], row["scdcopf_usd_h"]
            row["security_premium_usd_h"] = None if d is None or c is None else round(c - d, 2)
            # curtailment by type (layers): energy (no network), congestion (REL), security (CNF)
            dcu, scu = row.get("dcopf_curtailment_mw"), row.get("scdcopf_curtailment_mw")
            row["curt_energy_mw"] = round(ud_curt, 2)
            row["curt_congestion_mw"] = None if dcu is None else round(dcu - ud_curt, 2)
            row["curt_security_mw"] = None if dcu is None or scu is None else round(scu - dcu, 2)
            rows.append(row)
            log.info(f"{name:20s} {row['penetration_pct']:3d}% ({row['renewable_available_mw']:7.1f} MW): "
                     f"unconstrained {ud_cost:,.0f} (curt {ud_curt:.0f}) | DCOPF {d} (curt {row['dcopf_curtailment_mw']}) | "
                     f"SC-DCOPF {c} (curt {row['scdcopf_curtailment_mw']})")
    tab = pd.DataFrame(rows)
    tab.to_csv(os.path.join(out, f"summary_scenarios_lambda{lam:.3f}.csv"), index=False)
    pd.set_option("display.width", 250)
    log.info("\n" + tab.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
