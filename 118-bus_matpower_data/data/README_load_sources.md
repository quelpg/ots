# Data sources (IEEE 118-bus)

> ⚠️ **PRELIMINARY — SCUC files auto-extracted for a quick assessment.**
> The SCUC CSVs (`gen_data_scuc.csv`, `load_hourly_scuc.csv`, `demand_hourly_scuc.csv`) were
> extracted programmatically from `StarGenLite_SCUC.xlsm` by an automated pass, to quickly
> evaluate whether the data is usable. They are **not yet validated**. Before relying on them,
> the intent is to re-export them deterministically from the Excel by hand and confirm the
> values. Treat these files as provisional.

Two datasets are available for the 118-bus system. They describe the **same network**
(topology, R, X are identical) but differ in generation, load values and line ratings.

## Generators

- **MATPOWER:** `gen_data_118-bus.csv` — 54 rows, but 35 are synchronous condensers
  (`Pmax = 0`); only 19 produce active power. All `Pmin = 0`. Linear cost `c1` [$/MWh].
- **SCUC / StarGenLite:** `gen_data_scuc.csv` — 54 real generators (all `MaxProd > 0`), with
  realistic `MinProd > 0` (technical minimum). Total capacity 7220 MW, total MinProd 2134 MW.
  Includes UC fields (RampUp/Dw, MinTU, MinTD, SDduration, ShutdownCost) for later use.
  For SC-DCOPF the linear cost is taken as `c1 = FuelCost * SlopeVarCost` (FuelCost = 1, so
  `c1 = SlopeVarCost`); the intercept `InterVarCost` is ignored (it belongs to UC).
  Buses differ slightly from MATPOWER: SCUC has a generator at bus 82, MATPOWER at bus 1.

## Hourly demand (SCUC only)

- `demand_hourly_scuc.csv` — total system demand per hour (h001..h024), 1037 to 5592 MW.

---

## Loads (spatial)

The two load datasets describe the same network but differ in load values and distribution.

## 1. MATPOWER (current default)
- File: processed as `processed/loads.csv` (columns `bus, pd_pu`), a **single operating point**.
- Total load: **4242 MW**.
- Load present on **99 buses**.

## 2. SCUC / StarGenLite (hourly, from `SCUC-using-LODF/StarGenLite_SCUC.xlsm`)
- File: `data/load_hourly_scuc.csv` (columns `bus, h001 ... h024`), a **24-hour profile** in p.u.
- Built as `load[bus, h] = demand_total[h] * load_factor[bus] / base_mva`.
- Total demand ranges from **1037 MW** (h004, valley) to **5592 MW** (h021, peak).
- Load present on **91 buses**.

## Important difference: buses that carry load

The two sources do NOT place load on exactly the same buses. The SCUC distribution factors
cover 91 buses, all of which also have load in MATPOWER. However, **8 buses have load in
MATPOWER but zero load in SCUC**:

    buses 8, 24, 72, 73, 91, 99, 113, 116

So switching load source changes not only the total demand but also the **spatial pattern**
of consumption. This can change which N-1 contingencies are feasible/infeasible, because the
power-flow pattern differs. Keep this in mind when comparing results between the two sources.

## Choosing a source
- For a single-snapshot SC-DCOPF comparable to the current baseline, pick one hour of the
  SCUC profile (e.g. peak h021) or use the MATPOWER single point.
- For Unit Commitment, use the full 24-hour SCUC profile.
- Whatever the choice, use the **same network (branch limits)** across SC-DCOPF / UC / OTS so
  model comparisons stay fair.
