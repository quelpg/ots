"""CS3 screening: candidate renewable arrangements on the original topology (K = 0), before any heuristic.

Each arrangement (a list of buses, equal shares) is solved at every penetration level with the DCOPF
(base case) and the SC-DCOPF (full N-1 list), and reported with:
  - renewable curtailment in both models [MW];
  - the highest base-case loading among the interconnection branches of region C (80-112: 77-80 x2,
    79-80, 68-81, 77-82) and of region A (1-32, 113-115, 117: 15-33, 19-34, 30-38, 24-70, 24-72);
  - the branches with the largest sum of |mu| over the states (binding flow limits; * = interconnection).
The arrangements and the selection rule are fixed in ARRANGEMENTS below and every one is reported, so
the choice of the final scenarios can be traced (it is not tuned after the heuristic results).
Selection rule of the regional scenarios: meshed buses of an exporting region (3 or more branches,
2 or more distinct neighbours, not radial), outside internal pockets, without an existing generator,
equal shares. Target: the interconnection is the binding regional limit at K = 0.

Output: <results>/screening/screening_k0_lambda<l>.csv, the arrangement files (arrangements/<name>.csv)
and the console table.
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import OTSModel                                              # noqa: E402
from model.data import add_renewables, load_system, renewable_scenario_path   # noqa: E402
from model.solution import curtailment, read_solution                         # noqa: E402
from model.states import EXCLUSIONS, build_states                             # noqa: E402

# name -> (buses, description); a name that is also a file in scenarios/ is a scenario kept for CS3
ARRANGEMENTS = {
    "concentrated": ([104, 106, 107, 110], "pocket 101-112 behind bus 100 (existing scenario)"),
    "distributed": (None, "Ruiz et al. buses (existing scenario, scenarios/distributed.csv)"),
    "regional_c": ([82, 83, 85, 92, 94, 96], "region C, meshed, outside the pocket, no generator"),
    "regional_c_plus90": ([82, 83, 85, 90, 92, 94, 96], "regional_c + bus 90 (2 neighbours, double line)"),
    "regional_c_border": ([80, 82, 96, 97], "region C, next to the interconnection"),
    "regional_c_with_gen": ([80, 82, 83, 85, 89, 90, 92, 94, 96, 100], "region C, meshed, incl. buses with generators"),
    "regional_a": ([3, 5, 8, 11, 15, 17, 19, 23, 24, 27, 30, 32], "region A, meshed, no generator"),
    "near_control": ([15, 34, 54, 56, 60, 62, 75, 77], "near the load (d_load ~0.15), outside 80-118"),
}
INTERCONNECTION = {"C": [122, 123, 124, 125, 127], "A": [43, 44, 53, 108, 110]}
LEVELS = [0.10, 0.20, 0.30, 0.40, 0.50]

EPILOG = """examples (from project/):
  python cs3-renewables/screen_arrangements.py
  python cs3-renewables/screen_arrangements.py --only regional_c regional_a --levels 0.30 0.50
"""


def arrangement_file(name, buses, folder):
    if buses is None:                                  # existing scenario file
        return renewable_scenario_path(name, "matpower")
    path = os.path.join(folder, f"{name}.csv")
    pd.DataFrame({"bus": buses, "share": 1.0}).to_csv(path, index=False)
    return path


def screen(s, formulation, load_factor, top=4):
    """DCOPF and SC-DCOPF at K = 0: curtailment, interconnection loading, binding branches."""
    row, mva = {}, s.base_mva
    inter = set(INTERCONNECTION["C"]) | set(INTERCONNECTION["A"])
    for layer, cont in [("dcopf", "none"), ("scdcopf", "all")]:
        states = build_states(s, formulation, cont)
        m = OTSModel(s, states, load_factor=load_factor)
        m.solve()
        sol = read_solution(m, duals=True)
        if sol is None:
            row[f"{layer}_status"] = m.status_name
            m.dispose()
            continue
        row[f"{layer}_usd_h"] = round(sol.cost, 2)
        row[f"{layer}_curt_mw"] = round(curtailment(s, sol)[1], 2)
        for r, cut in INTERCONNECTION.items():
            row[f"{layer}_inter{r}_max_loading_pct"] = round(max(100 * abs(sol.f0[l]) / s.rate[l] for l in cut), 1)
        lim = s.rate[:, None] * np.where(np.arange(len(states)) == 0, 1.0, m.emerg_factor)[None, :]
        mu = np.abs(sol.mu) / mva
        score = (mu * ((np.abs(sol.f) >= 0.999 * lim) & (mu > 1e-3))).sum(1)
        order = [l for l in np.argsort(-score)[:top] if score[l] > 0]
        row[f"{layer}_binding"] = " ".join(f"{s.label[l]}{'*' if l in inter else ''}:{score[l]:.0f}" for l in order)
        m.dispose()
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--load-factor", type=float, default=0.80, help="lambda (default: 0.80)")
    ap.add_argument("--levels", type=float, nargs="+", default=LEVELS,
                    help="penetration levels, share of the load (default: 0.10 ... 0.50)")
    ap.add_argument("--only", nargs="+", choices=list(ARRANGEMENTS), help="screen only these arrangements")
    ap.add_argument("--formulation", default="redispatch_only", choices=list(EXCLUSIONS),
                    help="redispatch_only = full contingency list (default)")
    ap.add_argument("--results", default=os.path.join(ROOT, "cs3-renewables", "results"),
                    help="results root (default: cs3-renewables/results)")
    args = ap.parse_args(argv)

    out = os.path.join(args.results, "screening")
    folder = os.path.join(out, "arrangements")
    os.makedirs(folder, exist_ok=True)
    base = load_system("matpower")
    names = args.only or list(ARRANGEMENTS)
    rows = []
    for name in names:
        buses, desc = ARRANGEMENTS[name]
        path = arrangement_file(name, buses, folder)
        print(f"{name}: {desc} | buses {' '.join(map(str, pd.read_csv(path)['bus']))}", flush=True)
        for pen in args.levels:
            s = add_renewables(base, path, pen, args.load_factor)
            row = {"arrangement": name, "penetration_pct": round(100 * pen),
                   **screen(s, args.formulation, args.load_factor)}
            rows.append(row)
            print(f"  {row['penetration_pct']:3d}%: curtailment DCOPF {row.get('dcopf_curt_mw')} / SC-DCOPF "
                  f"{row.get('scdcopf_curt_mw')} MW | SC binding {row.get('scdcopf_binding')}", flush=True)
    tab = pd.DataFrame(rows)
    path = os.path.join(out, f"screening_k0_lambda{args.load_factor:.3f}.csv")
    if args.only and os.path.exists(path):      # keep the arrangements not screened this time
        old = pd.read_csv(path)
        tab = pd.concat([old[~old["arrangement"].isin(names)], tab], ignore_index=True)
    tab.to_csv(path, index=False)
    pd.set_option("display.width", 300)
    pd.set_option("display.max_colwidth", 70)
    cols = ["arrangement", "penetration_pct", "dcopf_curt_mw", "scdcopf_curt_mw", "scdcopf_interC_max_loading_pct",
            "scdcopf_interA_max_loading_pct", "dcopf_binding", "scdcopf_binding"]
    print("\n" + tab[[c for c in cols if c in tab]].to_string(index=False))
    print("(* = interconnection branch; number = sum of |mu| over the states, $/MWh)")
    print(f"\nSaved {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
