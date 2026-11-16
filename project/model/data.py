"""Read the processed system data (`processed/<source>/`) into a `System`.

Replaces sections 1-2 of the old notebooks (imports, processed data, index sets). Every array is
indexed by position: generator g is row g of gens.csv, branch l is row l of branches.csv and
bus i is position i in loads.csv (bus numbers are kept in `bus` for reporting).

Renewables (CS3, metodologia_tcc_v2.tex): `add_renewables` appends the units of a scenario after
the conventional generators (ids n_conv, n_conv + 1, ...), with cost 0, Pmin = 0 and Pmax = the
available power Gbar_r, and marks them in `is_renewable`. Without a scenario the system is the
conventional one, unchanged.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]      # project/


@dataclass
class System:
    source: str
    base_mva: float
    slack_bus: int                 # bus number
    bus: np.ndarray                # bus numbers, by position
    pd_nom: np.ndarray             # nominal load per bus [pu] (lambda = 1)
    gen_bus: np.ndarray            # bus position of each generator
    pmin: np.ndarray               # [pu]
    pmax: np.ndarray               # [pu]
    cost: np.ndarray               # c1 [$/MWh]
    br_from: np.ndarray            # bus position of the from end
    br_to: np.ndarray              # bus position of the to end
    x: np.ndarray                  # reactance [pu]
    rate: np.ndarray               # normal rating F^max [pu]
    label: list                    # 'from-to' (bus numbers)
    is_bridge: np.ndarray          # radial branch (its outage islands buses)
    bus_pos: dict = field(default_factory=dict)   # bus number -> position
    is_renewable: np.ndarray = None               # per generator (None = all conventional)
    renewables: str = None                        # scenario name (None = no renewables)
    penetration: float = 0.0                      # renewable available / (lambda x nominal load)

    def __post_init__(self):
        if self.is_renewable is None:
            self.is_renewable = np.zeros(len(self.pmax), dtype=bool)

    @property
    def conventional(self):
        return ~self.is_renewable

    @property
    def n_bus(self):
        return len(self.bus)

    @property
    def n_gen(self):
        return len(self.pmax)

    @property
    def n_branch(self):
        return len(self.x)

    @property
    def slack(self):
        """Position of the slack (reference) bus."""
        return self.bus_pos[self.slack_bus]

    @property
    def switchable(self):
        """L^S: non-radial branches (the only ones that may be opened)."""
        return np.flatnonzero(~self.is_bridge)

    def gen_name(self, g):
        kind = "renewable" if self.is_renewable[g] else "gen"
        return f"{kind} {g} (bus {self.bus[self.gen_bus[g]]}, {self.pmax[g] * self.base_mva:.0f} MW)"

    def summary_lines(self):
        """What the old notebooks printed in sections 1-2."""
        return [
            f"source = {self.source} | base_mva = {self.base_mva:.0f} MVA | slack bus = {self.slack_bus}",
            f"|N| = {self.n_bus} buses | |G| = {self.n_gen} generators | |L| = {self.n_branch} branches "
            f"({int(self.is_bridge.sum())} radial)",
            f"nominal load = {self.pd_nom.sum() * self.base_mva:,.1f} MW | "
            f"conventional Pmax = {self.pmax[self.conventional].sum() * self.base_mva:,.1f} MW",
        ] + ([] if not self.is_renewable.any() else [
            f"renewables: scenario {self.renewables!r}, penetration {100 * self.penetration:.0f}% -> "
            f"{self.is_renewable.sum()} units, {self.pmax[self.is_renewable].sum() * self.base_mva:,.1f} MW "
            f"available at buses {[int(self.bus[self.gen_bus[g]]) for g in np.flatnonzero(self.is_renewable)]}"])


def renewable_scenario_path(name, source="matpower", root=PROJECT_ROOT):
    """A scenario name (file cs3-renewables/scenarios/<name>.csv) or a path to a CSV."""
    p = Path(name)
    return p if p.suffix == ".csv" else Path(root) / "cs3-renewables" / "scenarios" / f"{name}.csv"


def add_renewables(system, scenario, penetration, load_factor=1.0, root=PROJECT_ROOT):
    """New System with the renewable units of `scenario` appended (cost 0, Pmin 0, Pmax = Gbar_r).

    The scenario CSV gives where the units are and how the total is split: columns `bus` and
    `share` (normalized to 1). Total available power = penetration x lambda x nominal load, so the
    penetration is a share of the load actually served (e.g. 0.20 = 20%)."""
    path = renewable_scenario_path(scenario, system.source, root)
    sc = pd.read_csv(path)
    share = sc["share"].to_numpy(dtype=float)
    share = share / share.sum()
    total = penetration * load_factor * system.pd_nom.sum()                 # [pu]
    gbar = share * total
    pos = sc["bus"].map(system.bus_pos)
    if pos.isna().any():
        raise ValueError(f"unknown bus in {path}: {sc.loc[pos.isna(), 'bus'].tolist()}")
    n = len(sc)
    name = scenario if Path(scenario).suffix != ".csv" else Path(scenario).stem
    return System(
        source=system.source, base_mva=system.base_mva, slack_bus=system.slack_bus,
        bus=system.bus, pd_nom=system.pd_nom,
        gen_bus=np.r_[system.gen_bus, pos.to_numpy(dtype=int)],
        pmin=np.r_[system.pmin, np.zeros(n)], pmax=np.r_[system.pmax, gbar],
        cost=np.r_[system.cost, np.zeros(n)],
        br_from=system.br_from, br_to=system.br_to, x=system.x, rate=system.rate,
        label=system.label, is_bridge=system.is_bridge, bus_pos=system.bus_pos,
        is_renewable=np.r_[system.is_renewable, np.ones(n, dtype=bool)],
        renewables=name, penetration=penetration)


def case_tag(load_factor, renewables=None, penetration=0.0):
    """Folder name of a case: lambda<l>, plus _ren-<scenario>_p<pct> with renewables."""
    tag = f"lambda{load_factor:.3f}"
    if renewables:
        name = Path(renewables).stem
        tag += f"_ren-{name}_p{100 * penetration:.0f}"
    return tag


def load_case(source="matpower", renewables=None, penetration=0.0, load_factor=1.0, root=PROJECT_ROOT):
    """load_system, plus the renewables of a scenario if given."""
    s = load_system(source, root)
    if renewables:
        s = add_renewables(s, renewables, penetration, load_factor, root)
    return s


def load_system(source="matpower", root=PROJECT_ROOT):
    proc = Path(root) / "processed" / source
    gens = pd.read_csv(proc / "gens.csv")
    loads = pd.read_csv(proc / "loads.csv")
    branches = pd.read_csv(proc / "branches.csv")
    meta = pd.read_csv(proc / "system_meta.csv").set_index("key")["value"]

    assert (gens["gen_id"].to_numpy() == np.arange(len(gens))).all(), "gen_id must be 0..G-1 in order"
    assert (branches["branch_id"].to_numpy() == np.arange(len(branches))).all(), \
        "branch_id must be 0..L-1 in order"

    bus = loads["bus"].to_numpy()
    bus_pos = {int(b): i for i, b in enumerate(bus)}
    slack_bus = int(meta["slack_bus"])
    assert slack_bus in bus_pos, "slack bus not found among the buses"

    return System(
        source=source,
        base_mva=float(meta["base_mva"]),
        slack_bus=slack_bus,
        bus=bus,
        pd_nom=loads["pd_pu"].to_numpy(dtype=float),
        gen_bus=gens["bus"].map(bus_pos).to_numpy(),
        pmin=gens["pmin_pu"].to_numpy(dtype=float),
        pmax=gens["pmax_pu"].to_numpy(dtype=float),
        cost=gens["c1"].to_numpy(dtype=float),
        br_from=branches["from_bus"].map(bus_pos).to_numpy(),
        br_to=branches["to_bus"].map(bus_pos).to_numpy(),
        x=branches["x_pu"].to_numpy(dtype=float),
        rate=branches["rate_pu"].to_numpy(dtype=float),
        label=branches["label"].tolist(),
        is_bridge=branches["is_bridge"].to_numpy(dtype=bool),
        bus_pos=bus_pos,
    )
