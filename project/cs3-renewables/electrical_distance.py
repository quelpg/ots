"""Electrical distance from every bus to the load (to choose the buses of the concentrated
renewable scenario of CS3 by an explicit criterion).

Effective reactance between buses i and j (DC network, original topology, every path in parallel):
    X_ij = L+_ii + L+_jj - 2 L+_ij,   L = A^T diag(1/x) A (bus susceptance Laplacian), L+ its
                                      Moore-Penrose pseudo-inverse.
It is the reactance "seen" between the two buses: the larger it is, the harder it is to transfer
power from one to the other. Two distances per bus:
    d_load(i)   = sum_j Pd_j X_ij / sum_j Pd_j      (load-weighted distance to every load)
    d_center(i) = same, only the loads of the central region (buses 40-79, 41% of the load)
Also per bus: number of branches, total rating of those branches [MW] (how much power can leave
the bus in the base case) and the existing generation.

Output: electrical_distance.csv (one row per bus, sorted by d_load) and the console ranking.
Pure linear algebra (no solver).
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model.data import load_system                                         # noqa: E402

CENTER = (40, 79)          # central region by bus number (41% of the load)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="matpower", help="(default: matpower)")
    ap.add_argument("--top", type=int, default=25, help="buses shown in the ranking (default: 25)")
    ap.add_argument("--out", default=os.path.join(ROOT, "cs3-renewables", "results"),
                    help="output folder (default: cs3-renewables/results)")
    args = ap.parse_args(argv)

    s = load_system(args.source)
    NB, NL = s.n_bus, s.n_branch
    A = np.zeros((NL, NB))
    A[np.arange(NL), s.br_from] = 1.0
    A[np.arange(NL), s.br_to] = -1.0
    L = A.T @ np.diag(1.0 / s.x) @ A                     # bus susceptance Laplacian [pu]
    Lp = np.linalg.pinv(L)
    d = np.diag(Lp)
    X = d[:, None] + d[None, :] - 2 * Lp                  # effective reactance between buses [pu]

    pd_mw = s.pd_nom * s.base_mva
    center = (s.bus >= CENTER[0]) & (s.bus <= CENTER[1])
    d_load = X @ pd_mw / pd_mw.sum()
    d_center = X[:, center] @ pd_mw[center] / pd_mw[center].sum()

    n_br = np.zeros(NB, dtype=int)
    cap = np.zeros(NB)
    for l in range(NL):
        for b in (s.br_from[l], s.br_to[l]):
            n_br[b] += 1
            cap[b] += s.rate[l] * s.base_mva
    gen_mw = np.zeros(NB)
    np.add.at(gen_mw, s.gen_bus, s.pmax * s.base_mva)
    neighbors = [[] for _ in range(NB)]
    for l in range(NL):
        neighbors[s.br_from[l]].append(int(s.bus[s.br_to[l]]))
        neighbors[s.br_to[l]].append(int(s.bus[s.br_from[l]]))

    region = np.where(s.bus <= 39, "1-39", np.where(s.bus <= 79, "40-79", "80-118"))
    df = pd.DataFrame({"bus": s.bus, "region": region, "d_load_pu": d_load.round(4),
                       "d_center_pu": d_center.round(4), "load_mw": pd_mw.round(1),
                       "existing_gen_pmax_mw": gen_mw.round(1), "n_branches": n_br,
                       "branch_rating_sum_mw": cap.round(0),
                       "neighbors": [" ".join(map(str, sorted(set(n)))) for n in neighbors]})
    df["rank_d_load"] = df.d_load_pu.rank(ascending=False, method="min").astype(int)
    df["rank_d_center"] = df.d_center_pu.rank(ascending=False, method="min").astype(int)
    df = df.sort_values("d_load_pu", ascending=False)
    os.makedirs(args.out, exist_ok=True)
    df.to_csv(os.path.join(args.out, "electrical_distance.csv"), index=False)

    pd.set_option("display.width", 220)
    print(f"Effective reactance to the load (load-weighted), original topology. "
          f"Median over all buses: d_load = {np.median(d_load):.4f} pu, d_center = {np.median(d_center):.4f} pu")
    print(df.head(args.top).to_string(index=False))
    print(f"\nSaved {os.path.join(args.out, 'electrical_distance.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
