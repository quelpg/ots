import pandas as pd
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

# What is Missing of the pre-processing for the shift-factors SCED?
    # Actually calculate the matrices B, A, B', and Phi based on the bus and branch data. This involves:
    # - For B: Using the branch data to calculate the susceptance values for each branch
    # - For A: Constructing the incidence matrix based on the connections between buses and branches
    # - For B': Calculating the bus susceptance matrix based on the bus data and
    # - For Phi: Calculate BAB'^(-1) based on the previously calculated matrices B, A, and B'.

# What is Missing of the pre-processing for the B-Theta SCED?
    # I think we only need to calculate the B matrix (Which is already mentioned previously)