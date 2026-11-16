"""Plot the OTS-SC-DCOPF switching-limit sweep (cost vs K).

Reads results/<source>/<formulation>/<config>/K*/summary.csv and writes
../figures/k_sweep_<formulation>_<config>.png / .pdf.

Usage: python plot_k_sweep.py [results_dir]
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "results/matpower/redispatch_with_exclusions/contingencies")
FIGURES = Path("../figures")

SERIES = "#2a78d6"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
GUROBI_OPTIMAL = 2


def load_sweep(root: Path) -> pd.DataFrame:
    rows = []
    for d in root.glob("K*"):
        f = d / "summary.csv"
        if not (d.is_dir() and d.name[1:].isdigit() and f.exists()):
            continue
        s = pd.read_csv(f).set_index("metric")["value"]
        rows.append({
            "K": int(d.name[1:]),
            "cost": s["base_cost_usd_per_h"],
            "gap": s["mip_gap"],
            "optimal": int(s["solver_status"]) == GUROBI_OPTIMAL,
            "n_open": int(s["n_switched_lines"]),
        })
    return pd.DataFrame(rows).sort_values("K").reset_index(drop=True)


def main() -> None:
    df = load_sweep(RESULTS)
    c0 = df.loc[df.K == 0, "cost"].iloc[0]
    df["saving_pct"] = 100 * (c0 - df.cost) / c0
    print(df.to_string(index=False))

    plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK_2,
                         "xtick.color": INK_2, "ytick.color": INK_2})
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=200)

    ax.plot(df.K, df.cost / 1e3, color=SERIES, lw=2, zorder=2)
    opt, tl = df[df.optimal], df[~df.optimal]
    ax.scatter(opt.K, opt.cost / 1e3, s=48, color=SERIES, zorder=3,
               edgecolor="white", linewidth=1.5, label="Proven optimal")
    ax.scatter(tl.K, tl.cost / 1e3, s=48, facecolor="white", zorder=3,
               edgecolor=SERIES, linewidth=2,
               label="Best found (time limit, gap 6.9-7.8%)")

    for k in (1, 2, 4, 8):
        r = df[df.K == k]
        if r.empty:
            continue
        r = r.iloc[0]
        ax.annotate(f"−{r.saving_pct:.2f}%\n({r.n_open} open)",
                    (r.K, r.cost / 1e3), xytext=(7, 5),
                    textcoords="offset points", ha="left", va="bottom",
                    fontsize=8, color=INK_2)

    ax.set_xlabel("Switching limit K (max. branches open)", color=INK)
    ax.set_ylabel("Base-case operating cost (k$/h)", color=INK)
    ax.set_xticks(df.K)
    lo, hi = df.cost.min() / 1e3, c0 / 1e3
    ax.set_ylim(lo - 0.4, hi + 0.6)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.set_title("OTS SC-DCOPF, IEEE 118-bus, N-1 (reduced $\\mathcal{C}_T$)",
                 fontsize=10, color=INK, loc="left")

    fig.tight_layout()
    FIGURES.mkdir(exist_ok=True)
    stem = "k_sweep_" + "_".join(RESULTS.parts[-2:])   # e.g. k_sweep_redispatch_with_exclusions_contingencies
    for ext in ("png", "pdf"):
        out = FIGURES / f"{stem}.{ext}"
        fig.savefig(out, facecolor="white")
        print(f"Saved {out}")


if __name__ == "__main__":
    main()
