"""Run ots-sc-dcopf.ipynb for a range of switching limits K, unattended.

Executes the notebook's code cells once per K (no copy of the model: the notebook is the
single source of the formulation), overriding only the run settings below. Each K exports
its results to results/<source>/<formulation>/<config>/K<K>/ exactly as a manual run would,
plus the Gurobi log (gurobi.log). The notebook warm-starts from the result of the largest
lower K that exists, so running K in increasing order chains the warm starts; running one
job per K in parallel works too, as long as K = 0 was run first (every K then starts from it).

Usage (from project/ots-sc-dcopf/):
    python sweep_k.py --formulation redispatch_with_exclusions --k-min 1 --k-max 10
    python sweep_k.py --formulation redispatch_only --k-min 4 --k-max 4 --time-limit 7200
    # parallel: run K = 0 first, then one job per K (--k-min K --k-max K)
"""

import argparse
import json
import os
import re
import time
import traceback

NOTEBOOK = "ots-sc-dcopf.ipynb"


def setting(code, name, value):
    # replace a top-level assignment 'NAME = ...' (keeps any trailing comment out)
    new, n = re.subn(rf"^{name} = .*$", f"{name} = {value!r}", code, flags=re.M)
    return new, n


def run_k(cells, K, args):
    g = {"display": lambda x: print(x.to_string() if hasattr(x, "to_string") else x)}
    found = set()
    for code in cells:
        for name, value in [("INCLUDE_CT", args.ct), ("INCLUDE_CG", args.cg),
                            ("FORMULATION", args.formulation), ("MAX_SWITCHED", K),
                            ("TIME_LIMIT", args.time_limit)]:
            code, n = setting(code, name, value)
            if n:
                found.add(name)
        # Gurobi log to a file in the run folder instead of the console. Gurobi appends to an
        # existing log, so the old one is removed first (keep only this run).
        code = code.replace(
            'model.setParam("OutputFlag", 1)',
            'os.makedirs(OUT_DIR, exist_ok=True); '
            'os.path.exists(f"{OUT_DIR}/gurobi.log") and os.remove(f"{OUT_DIR}/gurobi.log"); '
            'model.setParam("OutputFlag", 1); '
            'model.setParam("LogToConsole", 0); model.setParam("LogFile", f"{OUT_DIR}/gurobi.log")')
        if "os.makedirs(OUT_DIR" in code:
            code = "import os\n" + code
        exec(code, g)
    missing = {"INCLUDE_CT", "INCLUDE_CG", "FORMULATION", "MAX_SWITCHED", "TIME_LIMIT"} - found
    assert not missing, f"settings not found in the notebook: {missing}"
    model = g["model"]
    model.dispose()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--formulation", default="redispatch_with_exclusions",
                    choices=["redispatch_only", "redispatch_with_exclusions"])
    ap.add_argument("--k-min", type=int, default=1)
    ap.add_argument("--k-max", type=int, default=10)
    ap.add_argument("--time-limit", type=float, default=3600, help="per K [s]")
    ap.add_argument("--no-ct", dest="ct", action="store_false", help="drop line contingencies")
    ap.add_argument("--no-cg", dest="cg", action="store_false", help="drop generator contingencies")
    args = ap.parse_args()

    nb = json.load(open(NOTEBOOK, encoding="utf-8"))
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]

    for K in range(args.k_min, args.k_max + 1):
        print(f"\n{'#' * 70}\n# K = {K} | {args.formulation} | CT={args.ct} CG={args.cg}\n{'#' * 70}",
              flush=True)
        t0 = time.time()
        try:
            run_k(cells, K, args)
        except Exception:
            traceback.print_exc()
            print(f"K = {K} FAILED, moving on", flush=True)
        print(f"K = {K} done in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
