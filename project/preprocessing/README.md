# Pre-processing

Turns the raw data in `../data/` into the clean tables in `../processed/<source>/` that every
model reads, and draws the single-line diagram.

| File | Reads | Writes |
|---|---|---|
| `pre-processing.ipynb` | `../data/matpower/` (MATPOWER case118) | `../processed/matpower/` |
| `pre-processing-scuc.ipynb` | `../data/scuc/`, `../data/matpower/` (network) | `../processed/scuc/` |
| `single_line_diagram.py` | `../processed/matpower/`, `../data/matpower/`, `ieee118_bus_positions.csv` | `../figures/ieee118_unifilar.drawio`; with `--layout regions` (blocks of the CS3 regions A, B, C moved apart, each in its own rectangle): `../figures/ieee118_unifilar_regions.drawio` |

`processed/<source>/` holds `gens.csv`, `loads.csv`, `branches.csv` (with `is_bridge`, the radial
branches) and `system_meta.csv` (base MVA, slack bus).

## Commands

From `project/preprocessing/`:

```
jupyter nbconvert --to notebook --execute --inplace pre-processing.ipynb
jupyter nbconvert --to notebook --execute --inplace pre-processing-scuc.ipynb
python single_line_diagram.py
python single_line_diagram.py --layout regions
```

`--layout regions` uses `--size large` by default: fonts and symbols x2, the drawing stretched
vertically, bus numbers, load values and transformer symbols placed on free spots (fewest overlaps
and line crossings), the region blocks kept apart on the final boxes, and four buses moved by hand
(`REGION_NUDGE`: 98, 103, 116, 118) where a long branch leg ran through them. The classic layout is
unchanged (byte-identical output).

(or open the notebooks and run all cells). Re-running them must leave `processed/` unchanged
(`git status processed` shows nothing) unless the raw data or the processing changed.
