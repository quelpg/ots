import numpy as np
import pandapower as pp
import pandapower.networks as pn

# Load the IEEE 118-bus system from pandapower
net = pn.case118()

# Extract bus and branch info
num_buses = len(net.bus)
num_lines = len(net.line)
num_trafos = len(net.trafo)
num_branches = num_lines + num_trafos

print("--------- IEEE 118-Bus Power System Data Summary ---------")
print("")
print(f"Buses: {num_buses}")
print(f"Branches: {num_branches}")
print(f"  - Transmission lines: {num_lines}")
print(f"  - Transformers: {num_trafos}")
print(f"Generators: {len(net.gen) + len(net.sgen)}")
print(f"Loads: {len(net.load)}")

# --- Build unified branch data ---
# For DC power flow we need: from_bus, to_bus, reactance (x in pu), rating

# Transmission lines: x is in ohm/km * length_km, convert to pu
base_mva = net.sn_mva  # system base MVA (typically 100)

branches_from = []
branches_to = []
branches_x = []
branches_rate = []

# Lines: pandapower stores x_ohm_per_km and length_km
for idx, line in net.line.iterrows():
    from_bus = line["from_bus"]
    to_bus = line["to_bus"]
    # Get base impedance for the line's voltage level
    vn_kv = net.bus.at[from_bus, "vn_kv"]
    z_base = (vn_kv ** 2) / base_mva
    # Total reactance in pu
    x_pu = (line["x_ohm_per_km"] * line["length_km"]) / z_base
    # Thermal limit (max_i_ka * vn_kv * sqrt(3) gives MVA rating)
    rate_mva = line["max_i_ka"] * vn_kv * np.sqrt(3)

    branches_from.append(from_bus)
    branches_to.append(to_bus)
    branches_x.append(x_pu)
    branches_rate.append(rate_mva)

# Transformers: pandapower stores vk_percent (short-circuit voltage %)
for idx, trafo in net.trafo.iterrows():
    from_bus = trafo["hv_bus"]
    to_bus = trafo["lv_bus"]
    # Reactance in pu (vk_percent / 100 is approximately x_pu for the trafo's rating)
    # Convert to system base: x_pu_system = x_pu_trafo * (base_mva / sn_mva_trafo)
    x_pu = (trafo["vk_percent"] / 100.0) * (base_mva / trafo["sn_mva"])
    rate_mva = trafo["sn_mva"]

    branches_from.append(from_bus)
    branches_to.append(to_bus)
    branches_x.append(x_pu)
    branches_rate.append(rate_mva)

branches_from = np.array(branches_from, dtype=int)
branches_to = np.array(branches_to, dtype=int)
branches_x = np.array(branches_x)
branches_rate = np.array(branches_rate)

# --- Pre-processing: DC power flow matrices ---

print("")
print("--------- Matrices Dimensions Summary ---------")
print("")
print(f"Dimension of Branch Susceptance Matrix (B): {num_branches}x{num_branches}")
print(f"Dimension of Incidence Matrix (A): {num_branches}x{num_buses-1}")
print(f"Dimension of Bus Susceptance Matrix (B'): {num_buses-1}x{num_buses-1}")
print(f"Dimension of Sensitivity Matrix (Phi): {num_branches}x{num_buses-1}")

# Choose the slack bus (pandapower uses ext_grid as the slack)
slack_bus = net.ext_grid.at[0, "bus"]
print(f"\nSlack bus: {slack_bus}")

# All bus indices
all_buses = net.bus.index.values
non_slack_buses = [b for b in all_buses if b != slack_bus]

# Mapping from bus index to column position in A and B'
bus_to_col = {bus: idx for idx, bus in enumerate(non_slack_buses)}

# Check for zero reactances
zero_x_mask = branches_x == 0
if zero_x_mask.any():
    print(f"\nWARNING: {zero_x_mask.sum()} branches have zero reactance. "
          f"Replacing with 1e-6 to avoid division by zero.")
    branches_x[zero_x_mask] = 1e-6

# B: Branch Susceptance Matrix (diagonal)
B = np.diag(1.0 / branches_x)

# A: Incidence Matrix (branches x non-slack buses)
A = np.zeros((num_branches, num_buses - 1))

for i in range(num_branches):
    f = branches_from[i]
    t = branches_to[i]
    if f in bus_to_col:
        A[i, bus_to_col[f]] = 1
    if t in bus_to_col:
        A[i, bus_to_col[t]] = -1

# B': Bus Susceptance Matrix
B_prime = A.T @ B @ A

# Phi: Sensitivity Matrix (PTDF)
print("\nComputing B' inverse...")
B_prime_inv = np.linalg.inv(B_prime)
Phi = B @ A @ B_prime_inv

print("")
print("--------- Pre-processing Completed ---------")
print(f"B shape: {B.shape}")
print(f"A shape: {A.shape}")
print(f"B' shape: {B_prime.shape}")
print(f"Phi shape: {Phi.shape}")

# Display first 10x10 of each matrix
np.set_printoptions(precision=3, suppress=True, linewidth=120)

print("")
print("B (Branch Susceptance Matrix, first 10x10):")
print(B[:10, :10])
print("")
print("A (Incidence Matrix, first 10x10):")
print(A[:10, :10])
print("")
print("B' (Bus Susceptance Matrix, first 10x10):")
print(B_prime[:10, :10])
print("")
print("Phi (Sensitivity Matrix / PTDF, first 10x10):")
print(Phi[:10, :10])
