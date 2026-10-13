import pandas as pd
import numpy as np
import os
from collections import deque

# get the directory of the current script
data_dir = os.path.dirname(os.path.abspath(__file__))
# get the directory of the current script (CSV files are in the same folder)
data_dir = os.path.dirname(os.path.abspath(__file__))

# load the bus dataset
bus_data = pd.read_csv(os.path.join(data_dir, "bus.csv"))

# load transmission lines and transformers (both are branches in DC power flow)
tl_data = pd.read_csv(os.path.join(data_dir, "transmission_line.csv"))
trafo_data = pd.read_csv(os.path.join(data_dir, "transformer.csv"))

# --- Parse branch data into a unified format ---


def parse_to_bus(to_circ_col):
    """Extract the bus number from the 'To# - Circ#' column (e.g., '46206    # 01' -> 46206)."""
    return to_circ_col.str.split("#").str[0].str.strip().astype(int)


def parse_circuit(to_circ_col):
    """Extract the circuit number from the 'To# - Circ#' column."""
    return to_circ_col.str.split("#").str[1].str.strip().astype(int)


# Build unified branch dataframe from transmission lines
tl_branches = pd.DataFrame({
    "fbus": tl_data["From#"].values,
    "tbus": parse_to_bus(tl_data["To# - Circ#"]).values,
    "circuit": parse_circuit(tl_data["To# - Circ#"]).values,
    "x": tl_data["Reactance (pu)"].values,
    "rate": tl_data["Normal Rat.(MVA)"].values,
    "type": "TL"
})

# Build unified branch dataframe from transformers
trafo_branches = pd.DataFrame({
    "fbus": trafo_data["From#"].values,
    "tbus": parse_to_bus(trafo_data["To# - Circ#"]).values,
    "circuit": parse_circuit(trafo_data["To# - Circ#"]).values,
    "x": trafo_data["Reactance (pu)"].values,
    "rate": trafo_data["Normal Rat.(MVA)"].values,
    "type": "Trafo"
})

# Combine all branches
branch_data = pd.concat([tl_branches, trafo_branches], ignore_index=True)

print("--------- SIN Power System Data Summary ---------")
print("")
print(f"Total buses in dataset: {len(bus_data)}")
print(f"Total branches in dataset: {len(branch_data)}")
print(f"  - Transmission lines: {len(tl_branches)}")
print(f"  - Transformers: {len(trafo_branches)}")

# --- Connectivity analysis: find the main island ---
# The SIN has small sub-networks connected via HVDC (not modeled as AC branches).
# We work with the main connected component for the DC power flow matrices.

all_buses_original = bus_data["Bus"].values.astype(int)
bus_set = set(all_buses_original)

# Build adjacency list
adj = {b: set() for b in all_buses_original}
for f, t in zip(branch_data["fbus"].values, branch_data["tbus"].values):
    f, t = int(f), int(t)
    if f in bus_set and t in bus_set:
        adj[f].add(t)
        adj[t].add(f)

# BFS to find connected components
visited = set()
components = []

for bus in all_buses_original:
    if bus not in visited:
        component = []
        queue = deque([bus])
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adj[node]:
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)

# Sort components by size (largest first)
components.sort(key=len, reverse=True)

print(f"\nConnected components found: {len(components)}")
for i, comp in enumerate(components):
    print(f"  Component {i+1}: {len(comp)} buses")

# Use only the main island
main_island_buses = set(components[0])

print(f"\nUsing main island ({len(main_island_buses)} buses) for pre-processing.")
if len(components) > 1:
    excluded = sum(len(c) for c in components[1:])
    print(f"Excluded {excluded} buses in {len(components)-1} smaller island(s) "
          f"(likely connected via HVDC).")

# Filter buses and branches to main island only
all_buses = np.array([b for b in all_buses_original if b in main_island_buses])
branch_mask = branch_data["fbus"].isin(main_island_buses) & branch_data["tbus"].isin(main_island_buses)
branch_data = branch_data[branch_mask].reset_index(drop=True)

num_buses = len(all_buses)
num_branches = len(branch_data)

print("")
print("--------- Matrices Dimensions Summary ---------")
print("")
print(f"Dimension of Branch Susceptance Matrix (B): {num_branches}x{num_branches}")
print(f"Dimension of Incidence Matrix (A): {num_branches}x{num_buses-1}")
print(f"Dimension of Bus Susceptance Matrix (B'): {num_buses-1}x{num_buses-1}")
print(f"Dimension of Sensitivity Matrix (Phi): {num_branches}x{num_buses-1}")

# --- Pre-processing calculations ---

# Choose the reference/slack bus (first bus in the main island)
slack_bus = all_buses[0]
print(f"\nSlack bus selected: {slack_bus}")

# List of non-slack buses
non_slack_buses = [b for b in all_buses if b != slack_bus]

# Mapping from bus number to column index in A and B'
bus_to_col = {bus: idx for idx, bus in enumerate(non_slack_buses)}

# Extract branch reactances
x = branch_data["x"].values.copy()

# Check for zero reactances (would cause division by zero)
zero_x_mask = x == 0
if zero_x_mask.any():
    print(f"\nWARNING: {zero_x_mask.sum()} branches have zero reactance. "
          f"Replacing with a small value (1e-6) to avoid division by zero.")
    x[zero_x_mask] = 1e-6

# B: Branch Susceptance Matrix (diagonal, 1/x for each branch)
B = np.diag(1.0 / x)

# A: Incidence Matrix (branches x non-slack buses)
A = np.zeros((num_branches, num_buses - 1))

fbus = branch_data["fbus"].values.astype(int)
tbus = branch_data["tbus"].values.astype(int)

for i in range(num_branches):
    f = fbus[i]
    t = tbus[i]
    if f in bus_to_col:
        A[i, bus_to_col[f]] = 1  # positive direction for from bus
    if t in bus_to_col:
        A[i, bus_to_col[t]] = -1  # negative direction for to bus

# B': Bus Susceptance Matrix
B_prime = A.T @ B @ A

# Phi: Sensitivity Matrix (PTDF)
print("\nComputing B' inverse (this may take a moment for large systems)...")
B_prime_inv = np.linalg.inv(B_prime)
Phi = B @ A @ B_prime_inv

print("")
print("--------- Pre-processing Completed ---------")
print("Matrices B, A, B', and Phi have been calculated.")
print(f"B shape: {B.shape}")
print(f"A shape: {A.shape}")
print(f"B' shape: {B_prime.shape}")
print(f"Phi shape: {Phi.shape}")

# Set print options for better readability
np.set_printoptions(precision=3, suppress=True, linewidth=120)

print("")
print("Viewing matrices (first 10x10):")
print("B (Branch Susceptance Matrix, diagonal):")
print(B[:10, :10])
print("")
print("A (Incidence Matrix):")
print(A[:10, :10])
print("")
print("B' (Bus Susceptance Matrix):")
print(B_prime[:10, :10])
print("")
print("Phi (Sensitivity Matrix / PTDF):")
print(Phi[:10, :10])
