"""Read the processed system data (`processed/<source>/`) into a `System`.

Replaces sections 1-2 of the old notebooks (imports, processed data, index sets). Every array is
indexed by position: generator g is row g of gens.csv, branch l is row l of branches.csv and
bus i is position i in loads.csv (bus numbers are kept in `bus` for reporting).
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
        return f"gen {g} (bus {self.bus[self.gen_bus[g]]}, {self.pmax[g] * self.base_mva:.0f} MW)"

    def summary_lines(self):
        """What the old notebooks printed in sections 1-2."""
        return [
            f"source = {self.source} | base_mva = {self.base_mva:.0f} MVA | slack bus = {self.slack_bus}",
            f"|N| = {self.n_bus} buses | |G| = {self.n_gen} generators | |L| = {self.n_branch} branches "
            f"({int(self.is_bridge.sum())} radial)",
            f"nominal load = {self.pd_nom.sum() * self.base_mva:,.1f} MW | "
            f"total Pmax = {self.pmax.sum() * self.base_mva:,.1f} MW",
        ]


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
