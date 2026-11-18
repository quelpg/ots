# CS3 – Renewable siting and curtailment

**Question:** does the location of the renewables, i.e. the type of network bottleneck that holds
them back (local pocket, radial connection, interconnection between regions, none), change the
curtailment and the benefit of switching?

Set-up: load level λ = 0.80 (uniform; N-1 feasible without switching), full contingency list.
Renewables as in the methodology (`metodologia_tcc_v2.tex`): cost 0 (no tie-break), 0 ≤ P_r,c ≤ Ḡ_r,
participation factor α = 0 (the conventional units cover any loss, including the loss of a
renewable plant, which is a generator contingency), curtailment C = Σ_r (Ḡ_r − P_r,0), total only.

## Scenarios (`scenarios/<name>.csv`: columns `bus`, `share`)

| Scenario | Buses | Why |
|---|---|---|
| `concentrated` | 104, 106, 107, 110 (equal split) | meshed buses of the far south-east, top of the electrical-distance ranking (`electrical_distance.py`); radial buses (87, 111, 112, 117, 10) excluded |
| `distributed` | 10, 31, 46, 70, 87, 103, 111 (equal split) | locations of Ruiz et al. (2012) |
| `regional_c` | 82, 83, 85, 92, 94, 96 (equal split) | exporting region C (80-112): meshed buses outside the pocket 101-112, no existing generator; held by the C interconnection (77-82) |
| `regional_a` | 3, 5, 8, 11, 15, 17, 19, 23, 24, 27, 30, 32 (equal split) | exporting region A (1-32, 113-115, 117): meshed buses, no existing generator; held by the A interconnection (19-34, 24-70), mostly under N-1 |
| `near_control` | 15, 34, 54, 56, 60, 62, 75, 77 (equal split) | control near the load (d_load ≈ 0.15, outside 80-118, 3+ branches, 500-1,100 MW of branch capacity) |

Bottleneck of each scenario (`binding_constraints.py`, `screen_arrangements.py`): `concentrated` =
the pocket 101-112, which reaches the rest of the system only through bus 100 (binding 94-100,
100-103), not the interconnection; `distributed` = radial buses 87 and 111 (not switchable);
`regional_c` / `regional_a` = interconnection of the region; `near_control` = none (no curtailment
up to 50%). The regional scenarios follow a rule fixed before the heuristic runs (meshed buses of
an exporting region: 3+ branches, 2+ distinct neighbours, outside internal pockets, without an
existing generator); all the arrangements screened are in `results/screening/`.

Penetration = share of the load served: total available = penetration × λ × nominal load
(10% / 20% / 30% / 40% / 50% at λ = 0.80 = 339 / 679 / 1,018 / 1,357 / 1,697 MW). In
`concentrated`, the split among buses (equal or by line capacity) gives the same result
(differences below 0.4 MW of curtailment and 4 $/h at 20% and 30%), so the split is equal.

Note on the layers: the security layer (SC-DCOPF − DCOPF) can be negative. In `regional_c` at 20%,
N-1 lowers the 653 MW unit at bus 100 (its loss is a contingency) from 653 to 403 MW, which frees
interconnection capacity for the renewables (curtailment 100 MW in the DCOPF, 39 MW in the
SC-DCOPF; unique: a −0.001 $/MWh tie-break on the renewables does not change it).

## Commands (from `project/`)

```
python cs3-renewables/electrical_distance.py           # ranking of the buses by distance to the load
python cs3-renewables/screen_arrangements.py           # K = 0 screening of candidate arrangements -> results/screening/
python cs3-renewables/run_scenarios.py                 # K = 0: unconstrained / DCOPF / SC-DCOPF per scenario and level
python cs3-renewables/run_scenarios.py --scenarios regional_c regional_a near_control   # only some (summary rows merged)
# any script of the project takes --renewables <scenario> --penetration <share>, e.g.
python heuristics/sequential.py --load-factor 0.80 --renewables concentrated --penetration 0.20 --out-root cs3-renewables/results
# curtailment by type (energy / congestion / security) for every saved topology of a case -> decomposition.csv
python cs3-renewables/decompose.py --renewables concentrated --penetration 0.30
# binding flow limits, duals, interconnection flows and renewable output per bus on one topology -> diagnostics/
python cs3-renewables/binding_constraints.py --renewables concentrated --penetration 0.30
python cs3-renewables/binding_constraints.py --renewables concentrated --penetration 0.30 --topology heuristic/TD/K10
python cs3-renewables/binding_constraints.py --renewables regional_a --penetration 0.50 --watch 43 44 53 108 110   # region A interconnection
# single-line diagrams (A4 pages): 'Regions' + one page per scenario -> figures/ieee118_cs3_scenarios.drawio
python preprocessing/single_line_diagram.py --layout regions     # base drawing with the regions apart (once)
python cs3-renewables/scenario_diagram.py
python cs3-renewables/scenario_diagram.py --landscape            # A4 landscape instead of portrait
python cs3-renewables/scenario_diagram.py --preview cs3-renewables/results/diagram_preview   # + PNG previews
```

Results go to `lambda0.800_ren-<scenario>_p<pct>/` folders.

`scenario_diagram.py` reads `figures/ieee118_unifilar_regions.drawio` (the single-line diagram with
the blocks of the regions moved apart; not modified) and draws one rectangle per region, A (1-32,
113-115, 117), B (33-79, 116, 118) and C (80-112), the interconnection branches of A and C thicker in
black and a renewable symbol (wind turbine + solar panel, illustrative: the scenarios do not set the
technology) on each renewable bus. It checks that the branches crossing the region borders are
exactly the ten interconnection branches and that the rectangles do not overlap. Each page is an A4
sheet; each overlay is a draw.io layer (View > Layers); export each page as PDF/SVG from draw.io.
The base drawing uses `--size large` (fonts and symbols x2, stretched vertically), so on A4 portrait
bus numbers print at ~7.7 pt. For every page the script prints an overlap check (symbols / texts that
overlap, and texts / symbols crossed by a line); `--preview` draws the pages at true A4 size.

## Results without switching (K = 0, λ = 0.80, 2026-11-16)

`results/matpower/redispatch_only/summary_scenarios_lambda0.800.csv`:

| Scenario | Level | Unconstrained ($/h) | DCOPF ($/h, curtailment) | SC-DCOPF ($/h, curtailment) |
|---|---|---|---|---|
| none | 0 | 71,283 | 71,332 (0) | 81,402 (0) |
| concentrated | 10% | 62,804 | 67,019 (0) | 77,104 (0) |
| concentrated | 20% | 54,366 | 64,288 (108 MW) | 74,837 (159 MW, 23%) |
| concentrated | 30% | 46,016 | 63,801 (405 MW) | 74,664 (485 MW, 48%) |
| distributed | 10% | 62,804 | 63,999 (0) | 73,337 (0) |
| distributed | 20% | 54,366 | 56,826 (0) | 65,610 (0) |
| distributed | 30% | 46,016 | 49,998 (4 MW) | 58,195 (4 MW) |

- No curtailment without network in any case: every curtailment above is caused by the network or
  by N-1 security.
- Concentrated: most curtailment comes from the base-case network (the DCOPF already curtails), and
  the base-case network cost grows fast (DCOPF − unconstrained: 4,215 → 9,922 → 17,784 $/h);
  distributed: 1,195 → 2,460 → 3,981 $/h. The security premium is similar (~10,000 $/h) in all cases.
