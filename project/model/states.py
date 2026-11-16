"""Operating states C = {0} u C_T u C_G and participation factors (section 3 of the old notebooks).

Order: base case, then branch contingencies (by branch id), then generator contingencies (by
generator id), as in the notebooks, so state ids match the old results one to one.
"""

from dataclasses import dataclass

import numpy as np

# Contingencies dropped by each formulation ("full list" = redispatch_only).
EXCLUSIONS = {
    "redispatch_only": [],
    "redispatch_with_exclusions": [("line", 7),    # 8-5 (infeasible alone at lambda = 1)
                                   ("line", 95),   # 38-65 (joint)
                                   ("gen", 0)],    # bus 10, 505 MW (joint)
}

# contingencies -> folder name used in results/ (same as the notebooks' 'config')
CONFIG_NAME = {"none": "basecase", "lines": "cont_trans", "gens": "cont_gen", "all": "contingencies"}


@dataclass(frozen=True)
class State:
    id: int
    kind: str           # 'base' | 'line' | 'gen'
    element: int        # branch or generator out of service (-1 for the base case)
    desc: str


def build_states(system, formulation="redispatch_only", contingencies="all"):
    if formulation not in EXCLUSIONS:
        raise ValueError(f"unknown formulation {formulation!r}; options: {list(EXCLUSIONS)}")
    if contingencies not in CONFIG_NAME:
        raise ValueError(f"unknown contingencies {contingencies!r}; options: {list(CONFIG_NAME)}")
    excl = EXCLUSIONS[formulation]
    states = [State(0, "base", -1, "base case")]
    if contingencies in ("lines", "all"):
        for l in system.switchable:                      # C_T: non-radial branches only
            if ("line", int(l)) not in excl:
                states.append(State(len(states), "line", int(l), f"line {system.label[l]} out"))
    if contingencies in ("gens", "all"):
        for g in range(system.n_gen):
            if ("gen", g) not in excl:
                states.append(State(len(states), "gen", g, f"{system.gen_name(g)} out"))
    return states


def participation_factors(system, states):
    """alpha[g, c] = Pmax_g / sum of Pmax in service in c, for generator contingencies (0 elsewhere)."""
    alpha = np.zeros((system.n_gen, len(states)))
    for s in states:
        if s.kind == "gen":
            on = np.ones(system.n_gen, dtype=bool)
            on[s.element] = False
            alpha[on, s.id] = system.pmax[on] / system.pmax[on].sum()
    return alpha


def summary_lines(system, states, formulation, contingencies):
    """What the old notebooks printed in section 3."""
    excl = EXCLUSIONS[formulation]
    names = [f"line {system.label[e]}" if k == "line" else system.gen_name(e) for k, e in excl]
    n_line = sum(s.kind == "line" for s in states)
    n_gen = sum(s.kind == "gen" for s in states)
    return [
        f"formulation = {formulation} | contingencies = {contingencies} "
        f"({CONFIG_NAME[contingencies]}) | excluded: {names or 'none'}",
        f"|C_T| = {n_line} branches | |C_G| = {n_gen} generators | "
        f"|C| = {len(states)} states (1 base + {len(states) - 1} contingencies)",
    ]
