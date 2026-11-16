"""SC-DCOPF / OTS-SC-DCOPF model (sections 3.2-6.1 of the old notebooks).

One Gurobi model holds every state. It is built once; afterwards only bounds and right-hand
sides change:
- `fix_topology(z)`  : z fixed (LP: SC-DCOPF on that topology; duals available),
- `free_topology(K)` : z binary on L^S with sum(1 - z) <= K (MILP; K = None: no limit),
- `set_load_factor(l)`: loads = l * nominal load,
- `set_objective('cost' | 'max_load' | 'min_switching' | 'min_violation')`, `set_min_open(n)`;
  'min_violation' needs `flow_slack=True` (overload slacks on every flow limit, CS2).

Formulation (per state c; see model/README.md):
  balance      sum_{g in G_i} P_gc - lambda * Pd_i = sum_out f - sum_in f
  gen limits   Pmin_g N1_gc <= P_gc <= Pmax_g N1_gc                    (variable bounds)
  thermal      |f_lc| <= F_l z_l (c = 0), |f_lc| <= F^em_l z_l (c != 0)
  DC law       |f_lc - (theta_i - theta_j) / x_l| <= M_l (1 - z_l)     (branch in service in c)
  branch out   f_lc = 0                                                (variable bounds)
  coupling     P_gc = P_g0                                             (c in C_T)
  response     P_gc = P_g0 + alpha_gc P_k0                             (c in C_G, k failed, g != k)
  angles       -theta_max <= theta_ic <= theta_max, theta_ref,c = 0    (variable bounds)
  switching    z_l = 1 off L^S; z binary on L^S; sum_{L^S} (1 - z_l) <= K
"""

import time

import gurobipy as gp
import numpy as np
import scipy.sparse as sp
from gurobipy import GRB

from .states import participation_factors

EMERG_FACTOR = 1.15     # F^em = 1.15 F^max (the MATPOWER data has rateB = rateC = rateA)
THETA_MAX = 0.6         # [rad], as in Hedman et al. (2009)

# MILP settings used in the K sweep (they change how Gurobi searches, not the model)
MILP_PARAMS = {"MIPGap": 1e-4, "MIPFocus": 1, "NoRelHeurTime": 300, "Cuts": 1}

STATUS_NAME = {GRB.OPTIMAL: "OPTIMAL", GRB.INFEASIBLE: "INFEASIBLE", GRB.TIME_LIMIT: "TIME_LIMIT",
               GRB.INTERRUPTED: "INTERRUPTED", GRB.INF_OR_UNBD: "INF_OR_UNBD",
               GRB.UNBOUNDED: "UNBOUNDED", GRB.SUBOPTIMAL: "SUBOPTIMAL"}


def _env(output):
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 1 if output else 0)
    env.start()
    return env


class OTSModel:
    def __init__(self, system, states, load_factor=1.0, emerg_factor=EMERG_FACTOR,
                 theta_max=THETA_MAX, output=False, name="OTS-SC-DCOPF", flow_slack=False):
        t0 = time.time()
        self.sys, self.states = system, states
        self.emerg_factor, self.theta_max = emerg_factor, theta_max
        s = system
        NB, NG, NL, NS = s.n_bus, s.n_gen, s.n_branch, len(states)
        self.alpha = participation_factors(s, states)
        self.big_m = (2 * theta_max) / s.x                       # M_l = (theta_max - theta_min) / x_l
        self.LS = s.switchable

        self.env = _env(output)
        m = self.m = gp.Model(name, env=self.env)

        # --- variables (generator limits, angle limits, reference bus and branch-out as bounds) ---
        p_lb = np.tile(s.pmin[:, None], (1, NS))
        p_ub = np.tile(s.pmax[:, None], (1, NS))
        f_fix = np.zeros((NL, NS), dtype=bool)                   # branch out of service in state c
        for st in states:
            if st.kind == "gen":
                p_lb[st.element, st.id] = p_ub[st.element, st.id] = 0.0
            elif st.kind == "line":
                f_fix[st.element, st.id] = True
        t_lb = np.full((NB, NS), -theta_max)
        t_ub = np.full((NB, NS), theta_max)
        t_lb[s.slack, :] = t_ub[s.slack, :] = 0.0
        f_lb = np.where(f_fix, 0.0, -GRB.INFINITY)
        f_ub = np.where(f_fix, 0.0, GRB.INFINITY)

        self.P = m.addMVar((NG, NS), lb=p_lb, ub=p_ub, name="p")
        self.F = m.addMVar((NL, NS), lb=f_lb, ub=f_ub, name="f")
        self.T = m.addMVar((NB, NS), lb=t_lb, ub=t_ub, name="theta")
        self.z = m.addMVar(NL, lb=1.0, ub=1.0, name="z")          # starts as the full topology (LP)
        self.lam = m.addMVar(1, lb=load_factor, ub=load_factor, name="lambda")
        # overload slack s_lc >= 0 on the flow limit of branch l in state c (both directions);
        # fixed at 0 except with the 'min_violation' objective (CS2: relaxed SC-DCOPF)
        self.S = m.addMVar((NL, NS), lb=0.0, ub=0.0, name="s") if flow_slack else None
        self.flow_relaxed = False

        # --- fixed matrices ---
        Cg = sp.csr_matrix((np.ones(NG), (s.gen_bus, np.arange(NG))), shape=(NB, NG))
        A = sp.csr_matrix((np.r_[-np.ones(NL), np.ones(NL)],
                           (np.r_[s.br_from, s.br_to], np.r_[np.arange(NL), np.arange(NL)])),
                          shape=(NB, NL))                         # -out + in
        pd_col = s.pd_nom[:, None]
        R0, Rem = sp.diags(s.rate), sp.diags(emerg_factor * s.rate)

        # --- constraints, one block per state ---
        self.c_bal, self.c_fmax, self.c_fmin = [], [], []
        for st in states:
            c = st.id
            Pc, Fc, Tc = self.P[:, c], self.F[:, c], self.T[:, c]
            R = R0 if c == 0 else Rem
            self.c_bal.append(m.addConstr(Cg @ Pc + A @ Fc - pd_col @ self.lam == 0, name=f"bal_{c}"))
            if flow_slack:                                        # |f| <= F z + s
                self.c_fmax.append(m.addConstr(Fc - R @ self.z - self.S[:, c] <= 0, name=f"fmax_{c}"))
                self.c_fmin.append(m.addConstr(Fc + R @ self.z + self.S[:, c] >= 0, name=f"fmin_{c}"))
            else:
                self.c_fmax.append(m.addConstr(Fc - R @ self.z <= 0, name=f"fmax_{c}"))
                self.c_fmin.append(m.addConstr(Fc + R @ self.z >= 0, name=f"fmin_{c}"))
            on = np.flatnonzero(~f_fix[:, c])                     # branches in service in state c
            Bc = sp.csr_matrix((np.r_[1 / s.x[on], -1 / s.x[on]],
                                (np.r_[np.arange(len(on)), np.arange(len(on))],
                                 np.r_[s.br_from[on], s.br_to[on]])), shape=(len(on), NB))
            Mc = sp.diags(self.big_m[on])
            dc = Fc[on] - Bc @ Tc                                 # f - (theta_i - theta_j) / x
            m.addConstr(dc - Mc @ self.z[on] >= -self.big_m[on], name=f"dclo_{c}")
            m.addConstr(dc + Mc @ self.z[on] <= self.big_m[on], name=f"dchi_{c}")
            if st.kind == "line":
                m.addConstr(Pc == self.P[:, 0], name=f"couple_{c}")
            elif st.kind == "gen":
                k = st.element
                g_on = np.array([g for g in range(NG) if g != k])
                S = sp.lil_matrix((len(g_on), NG))
                S[np.arange(len(g_on)), g_on] = 1.0
                S[:, k] = self.alpha[g_on, c][:, None]
                m.addConstr(Pc[g_on] - sp.csr_matrix(S) @ self.P[:, 0] == 0, name=f"resp_{c}")

        # sum_{L^S} z >= |L^S| - K  (at most K open) and  sum_{L^S} z <= |L^S| - min_open
        self.c_kmax = m.addConstr(self.z[self.LS].sum() >= 0, name="max_switched")        # inactive
        self.c_kmin = m.addConstr(self.z[self.LS].sum() <= len(self.LS), name="min_open")  # inactive
        self.cost_vec = s.cost * s.base_mva
        self.set_objective("cost")
        m.update()
        self.build_time = time.time() - t0

    # ------------------------------------------------------------------ settings
    def set_objective(self, kind):
        """'cost': min base-case cost [$/h] (lambda fixed).
        'max_load': max lambda (lambda becomes free; call set_load_factor to fix it again).
        'min_switching': min number of open lines, sum_{L^S} (1 - z) (MILP; lambda fixed).
        'min_violation': min total overload, sum_{l,c} s_lc [pu], equal weights (needs
        flow_slack=True; CS2). With the other objectives the slacks are fixed at 0."""
        self.objective = kind
        self._slack_bounds()
        if kind == "cost":
            self.m.setObjective(self.cost_vec @ self.P[:, 0], GRB.MINIMIZE)
        elif kind == "max_load":
            # written as min -lambda (same optimum): the duals keep the sign convention of the
            # cost LP (pi = d objective / d load > 0), so the heuristic criteria apply unchanged
            self.lam.lb, self.lam.ub = 0.0, GRB.INFINITY
            self.m.setObjective(-self.lam.sum(), GRB.MINIMIZE)
        elif kind == "min_switching":
            self.m.setObjective(len(self.LS) - self.z[self.LS].sum(), GRB.MINIMIZE)
        elif kind == "min_violation":
            if self.S is None:
                raise ValueError("build the model with flow_slack=True for 'min_violation'")
            self.m.setObjective(self.S.sum(), GRB.MINIMIZE)
        else:
            raise ValueError(f"unknown objective {kind!r}")

    def relax_flow_limits(self, relaxed=True):
        """Diagnostic: remove every flow limit (slacks free) with any objective; needs
        flow_slack=True. Used to see which constraint family holds the load (reference case)."""
        if self.S is None:
            raise ValueError("build the model with flow_slack=True to relax the flow limits")
        self.flow_relaxed = relaxed
        self._slack_bounds()
        self.m.update()

    def _slack_bounds(self):
        """Slacks free only with 'min_violation' or relax_flow_limits, and never on an open line:
        an open branch carries no flow, slack or not (otherwise the relaxed LP could route flow
        through it, paying a small slack, and understate the violation)."""
        if self.S is None:
            return
        free = self.objective == "min_violation" or self.flow_relaxed
        ub = np.full((self.sys.n_branch, len(self.states)), GRB.INFINITY if free else 0.0)
        if free:
            ub[np.asarray(self.z.ub) < 0.5, :] = 0.0         # branches fixed open
        self.S.ub = ub

    def set_min_open(self, min_open=0):
        """Cut sum_{L^S} (1 - z) >= min_open (e.g. a K proven infeasible + 1)."""
        self.c_kmin.rhs = len(self.LS) - min_open
        self.m.update()

    def set_load_factor(self, load_factor):
        self.lam.lb = self.lam.ub = load_factor

    def fix_topology(self, z):
        """LP on a fixed topology. z: 0/1 per branch (0 = open)."""
        z = np.asarray(z, dtype=float)
        if (z[~np.isin(np.arange(len(z)), self.LS)] < 1).any():
            raise ValueError("only switchable (non-radial) branches can be open")
        self.z.vtype = GRB.CONTINUOUS
        self.z.lb = self.z.ub = z
        self.m.update()
        self._slack_bounds()
        self.c_kmax.rhs = 0.0
        self.c_kmin.rhs = len(self.LS)
        self.K = 0 if z.min() == 1 else int((z[self.LS] < 0.5).sum())
        self.m.setParam("DualReductions", 0)       # infeasible LP reported as INFEASIBLE
        self.m.update()

    def open_lines(self, open_ids):
        z = np.ones(self.sys.n_branch)
        z[list(open_ids)] = 0.0
        self.fix_topology(z)

    def free_topology(self, K=None):
        """MILP: z binary on L^S, at most K open (K = None: no limit)."""
        vtype = np.full(self.sys.n_branch, GRB.CONTINUOUS)
        vtype[self.LS] = GRB.BINARY
        lb = np.ones(self.sys.n_branch)
        lb[self.LS] = 0.0
        self.z.vtype, self.z.lb, self.z.ub = vtype, lb, 1.0
        self.c_kmax.rhs = 0.0 if K is None else len(self.LS) - K
        self.K = K
        self.m.setParam("DualReductions", 1)       # Gurobi default (used in the K sweep)
        self.m.update()

    def warm_start(self, open_ids):
        start = np.ones(self.sys.n_branch)
        start[list(open_ids)] = 0.0
        self.z.Start = start

    def set_params(self, **params):
        for k, v in params.items():
            if v is not None:
                self.m.setParam(k, v)

    # ------------------------------------------------------------------ solve
    def solve(self, **params):
        self.set_params(**params)
        self.m.optimize()
        return self.m.Status

    @property
    def status_name(self):
        return STATUS_NAME.get(self.m.Status, str(self.m.Status))

    @property
    def has_solution(self):
        return self.m.SolCount > 0 and self.m.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT,
                                                         GRB.INTERRUPTED, GRB.SUBOPTIMAL)

    def size_lines(self):
        m = self.m
        return [f"model: {m.NumConstrs:,} rows, {m.NumVars:,} columns ({m.NumBinVars} binary), "
                f"{m.NumNZs:,} nonzeros | built in {self.build_time:.1f} s",
                f"theta in [-{self.theta_max}, {self.theta_max}] rad | M_l in "
                f"[{self.big_m.min():.1f}, {self.big_m.max():.1f}] pu | F^em = {self.emerg_factor} F^max"]

    def dispose(self):
        self.m.dispose()
        self.env.dispose()


def unconstrained_dispatch(system, load_factor=1.0):
    """Unconstrained dispatch (no network: single balance, generator limits, merit order).
    Returns (cost [$/h], renewable curtailment [MW]) or (None, None) if generation is short.
    Renewables have cost 0, so they come first; curtailment here is energy curtailment (more
    renewable than load), not caused by the network."""
    cost = unconstrained_dispatch_cost(system, load_factor)
    if cost is None:
        return None, None
    ren = system.is_renewable
    avail = system.pmax[ren].sum()
    load = load_factor * system.pd_nom.sum() - system.pmin[~ren].sum()
    return cost, max(avail - load, 0.0) * system.base_mva


def unconstrained_dispatch_cost(system, load_factor=1.0):
    """Unconstrained dispatch: cost of serving the load with no network constraints (single
    balance, generator limits only, merit order) [$/h]. DCOPF - this = base-case network cost."""
    order = np.argsort(system.cost)
    need = load_factor * system.pd_nom.sum() - system.pmin.sum()
    p = system.pmin.copy()
    for g in order:                                   # merit order (linear costs)
        add = min(system.pmax[g] - system.pmin[g], max(need, 0.0))
        p[g] += add
        need -= add
    if need > 1e-9:
        return None                                   # not enough generation
    return float(system.cost @ p * system.base_mva)
