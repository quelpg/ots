"""Reference checks for the model/ package. Run after every change to the model.

Values: the old notebooks' results (heuristics/benchmark/, reference/) and the load-level test of
2026-11-16 (reproduced with Gurobi). Prints one line per check and exits with 1 if any fails.

    python tests/check_reference.py          # fast checks (~2 min)
    python tests/check_reference.py --slow   # + brute force K = 1 (177 LPs, ~5 min)
"""

import argparse
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.build import OTSModel, unconstrained_dispatch_cost                      # noqa: E402
from model.data import load_system                                       # noqa: E402
from model.solution import isolated_buses, saved_topology                # noqa: E402
from model.states import build_states, participation_factors             # noqa: E402

BENCH = os.path.join(ROOT, "heuristics", "benchmark", "results", "matpower",
                     "redispatch_with_exclusions", "contingencies")
REDUCED, FULL = "redispatch_with_exclusions", "redispatch_only"

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""), flush=True)


def close(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def lp_cost(model, load_factor=None, open_ids=()):
    if load_factor is not None:
        model.set_load_factor(load_factor)
    model.open_lines(open_ids)
    model.solve()
    return model.m.ObjVal if model.status_name == "OPTIMAL" else None


def max_load(model):
    model.open_lines([])
    model.set_objective("max_load")
    model.solve()
    val = model.lam.X[0] if model.status_name == "OPTIMAL" else None
    model.set_objective("cost")
    return val


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slow", action="store_true", help="also run the brute-force K = 1 check")
    args = ap.parse_args()
    t0 = time.time()
    s = load_system("matpower")

    # --- states and participation factors -------------------------------------------------
    st_red, st_full = build_states(s, REDUCED), build_states(s, FULL)
    check("reduced list has 194 states", len(st_red) == 194, len(st_red))
    check("full list has 197 states (1 + 177 + 19)", len(st_full) == 197, len(st_full))
    a = participation_factors(s, st_full)
    sums = [a[:, c.id].sum() for c in st_full if c.kind == "gen"]
    zero_failed = all(a[c.element, c.id] == 0 for c in st_full if c.kind == "gen")
    check("alpha sums to 1 in every generator contingency; alpha = 0 for the failed unit",
          np.allclose(sums, 1.0) and zero_failed)

    # --- reduced list, lambda = 1 (old notebooks) ---------------------------------------------
    m = OTSModel(s, st_red)
    c0 = lp_cost(m)
    check("T1  reduced, lambda=1, K=0: 109,681.25", close(c0, 109681.25, 0.01), f"{c0:,.2f}")
    c2 = lp_cost(m, open_ids=[96, 122])
    check("T1b reduced, lambda=1, K=2 topology (64-65, 77-80): 107,665.95", close(c2, 107665.95, 0.01), f"{c2:,.2f}")
    bad = []
    for k in range(11):
        rd = os.path.join(BENCH, f"K{k}")
        if os.path.exists(os.path.join(rd, "summary.csv")):
            ids, saved = saved_topology(rd)
            got = lp_cost(m, open_ids=ids)
            if not close(got, saved, 0.01):
                bad.append(f"K{k}: {got} vs {saved}")
    check("benchmark: LP reproduces the saved cost of every MILP topology K0..K10", not bad, "; ".join(bad))
    c085 = lp_cost(m, 0.85)
    check("T2b reduced, lambda=0.85: 80,678.23", close(c085, 80678.23, 0.01), f"{c085:,.2f}")
    lm = max_load(m)
    check("T2b reduced: lambda_max = 1.0099..1.0100", lm is not None and 1.0099 <= lm <= 1.0101, f"{lm:.5f}")
    m.set_load_factor(1.0)
    iso = isolated_buses(s, np.ones(s.n_branch))
    check("original topology: no isolated bus", not iso)

    if args.slow:
        t = time.time()
        best = min(((lp_cost(m, 1.0, [l]) or np.inf, l) for l in m.LS))
        check("slow: brute force K=1 -> 64-65 at 108,442.22 (MILP optimum)",
              best[1] == 96 and close(best[0], 108442.22, 0.01),
              f"{s.label[best[1]]} at {best[0]:,.2f}, {time.time() - t:.0f} s")
    m.dispose()

    # --- full list, load levels ---------------------------------------------------------------
    m = OTSModel(s, st_full)
    grid = {0.50: 42326.93, 0.60: 52583.90, 0.70: 63568.33, 0.80: 81401.76, 0.85: 91817.97}
    for lam, ref in grid.items():
        c = lp_cost(m, lam)
        check(f"T2  full, lambda={lam:.2f}: {ref:,.2f}", close(c, ref, 0.01), "infeasible" if c is None else f"{c:,.2f}")
    c = lp_cost(m, 0.851)
    check("T2  full, lambda=0.851: infeasible", c is None, "feasible" if c is not None else "")
    lm = max_load(m)
    check("T2  full: lambda_max = 0.8501", lm is not None and abs(lm - 0.8501) < 1e-4, f"{lm:.5f}")
    # minimum-switching MILP (CS2): below lambda_max the original topology is feasible -> K_min = 0
    m.set_load_factor(0.85)
    m.free_topology(None)
    m.set_objective("min_switching")
    m.solve(TimeLimit=300, MIPFocus=1, NoRelHeurTime=0)
    kmin = m.m.ObjVal if m.m.SolCount else None
    check("min_switching MILP, full, lambda=0.85: K_min = 0 (proven)",
          kmin is not None and round(kmin) == 0 and m.status_name == "OPTIMAL", f"{kmin}, {m.status_name}")
    m.set_objective("cost")
    m.dispose()

    # --- cost layers: unconstrained dispatch (merit order, no network), DCOPF -----------------
    m = OTSModel(s, build_states(s, FULL, "none"))
    layers = {0.60: (50191.25, 50946.08), 0.80: (71282.86, 71332.19), 0.85: (76636.63, 76700.08),
              1.00: (93026.73, 93152.38)}
    for lam, (ud_ref, dc_ref) in layers.items():
        ud, dc = unconstrained_dispatch_cost(s, lam), lp_cost(m, lam)
        check(f"T3  lambda={lam:.2f}: unconstrained dispatch {ud_ref:,.2f} / DCOPF {dc_ref:,.2f}",
              close(ud, ud_ref, 0.01) and close(dc, dc_ref, 0.01), f"{ud:,.2f} / {dc:,.2f}")
    m.dispose()

    n_fail = results.count(False)
    print(f"\n{len(results) - n_fail}/{len(results)} checks passed in {time.time() - t0:.0f} s")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
