"""Helper: run all code cells of a notebook as a plain script.
Skips cells that call plotting/show so we don't need a display.
Usage: python _run_nb.py <notebook.ipynb>
"""
import json
import sys

nb_path = sys.argv[1]
with open(nb_path, "r", encoding="utf-8") as fh:
    nb = json.load(fh)

# Use a non-interactive matplotlib backend so plot cells don't block.
preamble = "import matplotlib\nmatplotlib.use('Agg')\n"
g = {"__name__": "__main__"}
exec(preamble, g)

for idx, cell in enumerate(nb["cells"]):
    if cell.get("cell_type") != "code":
        continue
    src = "".join(cell.get("source", []))
    if not src.strip():
        continue
    print(f"\n===== CELL {idx} =====")
    is_plot_cell = ("plotly" in src) or ("pplt" in src) or ("plt.show" in src) or ("simple_plotly" in src)
    try:
        exec(src, g)
    except Exception as e:
        if is_plot_cell:
            print(f"SKIPPED plot cell {idx}: {type(e).__name__}: {e}")
            continue
        print(f"ERROR in cell {idx}: {type(e).__name__}: {e}")
        raise
