import pandas as pd
import numpy as np
import os

# get the directory of the current script
data_dir = os.path.dirname(os.path.abspath(__file__))

# load the bus and branch datasets
bus_data = pd.read_csv(os.path.join(data_dir, "bus_data_118-bus.csv"))
branch_data = pd.read_csv(os.path.join(data_dir, "branch_data_118-bus.csv"))

# count the number of buses and branches
num_buses = len(bus_data)
num_branches = len(branch_data)

print("--------- Power System Data Summary ---------")
print("")
print(f"Amount of buses: {num_buses}")
print(f"Amount of branches: {num_branches}")

print("")
print("--------- Matrices Dimensions Summary ---------")
print("")
print(f"Dimension of Branch Susceptance Matrix (B): {num_branches}X{num_branches}")
print(f"Dimension of Incidence Matrix (A): {num_branches}X{num_buses-1}")
print(f"Dimension of Bus Susceptance Matrix (B'): {num_buses-1}X{num_buses-1}")
print(f"Dimension of Sensitivity Matrix (Phi): {num_branches}X{num_buses-1}")

# Pre-processing calculations

# Choose the reference/slack bus (can be any bus number from 1 to num_buses)
slack_bus = 1

# List of non-slack buses (all buses except slack)
non_slack_buses = [i for i in range(1, num_buses + 1) if i != slack_bus]

# Mapping from bus number to column index in A and B'
bus_to_col = {bus: idx for idx, bus in enumerate(non_slack_buses)}

# Extract branch reactances
x = branch_data['x'].values

# B: Branch Susceptance Matrix (diagonal, 1/x for each branch)
B = np.diag(1.0 / x)

# A: Incidence Matrix (branches x non-slack buses)
A = np.zeros((num_branches, num_buses-1))

fbus = branch_data['fbus'].values.astype(int)
tbus = branch_data['tbus'].values.astype(int)

for i in range(num_branches):
    f = fbus[i]
    t = tbus[i]
    if f in bus_to_col:
        A[i, bus_to_col[f]] = 1  # positive direction for from bus
    if t in bus_to_col:
        A[i, bus_to_col[t]] = -1  # negative direction for to bus

# B': Bus Susceptance Matrix
B_prime = A.T @ B @ A

# Phi: Sensitivity Matrix
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

# Save matrices to CSV files
output_dir = os.path.join(data_dir, "matrices")
os.makedirs(output_dir, exist_ok=True)

# Use branch labels (fbus-tbus) as row index for B, A, and Phi
branch_labels = [f"{fbus[i]}-{tbus[i]}" for i in range(num_branches)]
bus_labels = [str(b) for b in non_slack_buses]

pd.DataFrame(B, index=branch_labels, columns=branch_labels).to_csv(
    os.path.join(output_dir, "B_branch_susceptance.csv"))

pd.DataFrame(A, index=branch_labels, columns=bus_labels).to_csv(
    os.path.join(output_dir, "A_incidence.csv"))

pd.DataFrame(B_prime, index=bus_labels, columns=bus_labels).to_csv(
    os.path.join(output_dir, "B_prime_bus_susceptance.csv"))

pd.DataFrame(Phi, index=branch_labels, columns=bus_labels).to_csv(
    os.path.join(output_dir, "Phi_sensitivity.csv"))

print("")
print(f"Matrices saved to: {output_dir}")
print("  - B_branch_susceptance.csv")
print("  - A_incidence.csv")
print("  - B_prime_bus_susceptance.csv")
print("  - Phi_sensitivity.csv")