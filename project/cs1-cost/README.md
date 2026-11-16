# CS1 – Cost reduction under N-1 security (λ ≤ λ_max)

**Question:** at load levels where the original topology is N-1 secure (λ ≤ λ_max = 0.850, full
contingency list), how much does preventive switching reduce the operating cost, and with how
many open lines (K)?

Plan:

1. Reference grid (in `../reference/`): SC-DCOPF and DCOPF cost per λ (0.50 … 0.85), to see where
   the security premium is relevant.
2. Heuristic (4 criteria) at every λ of the grid (cheap: a few LPs per opening).
3. MILP with warm start from the heuristic (30 min per K) at 2–3 values of λ, chosen from step 1;
   report cost, best bound and gap per K.

Results and commands will be listed here when the `model/` package and the scripts are ready.
