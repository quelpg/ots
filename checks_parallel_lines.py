import pandas as pd

# Load the branch dataset
# Ensure the file path matches your local directory
path = 'C:\\Users\\user\\Documents\\Documentos\\Faculdade\\TCC\\code\\ots\\branch_data_118-bus.csv'
filename = 'branch_data_118-bus.csv'
df = pd.read_csv(path)

# Define the columns that identify a connection between two nodes
connection_columns = ['fbus', 'tbus']

# Identify all parallel lines
# keep=False ensures all instances of the duplicates are returned
parallel_lines = df[df.duplicated(subset=connection_columns, keep=False)]

if not parallel_lines.empty:
    print(f"--- Parallel Lines Detected in {filename} ---")
    
    # Create a summary showing the pairs of buses and the number of circuits
    summary = parallel_lines.groupby(connection_columns).size().reset_index(name='circuit_count')
    print("\nSummary of parallel connections:")
    print(summary.to_string(index=False))
    
    # Detailed view of the specific parameters for these lines
    print("\nDetailed parameters for parallel branches:")
    # Selecting relevant columns for power flow analysis
    detailed_view = parallel_lines[connection_columns + ['r', 'x', 'rateA']]
    print(detailed_view.sort_values(by='fbus').to_string(index=False))
else:
    print(f"No parallel lines were found in {filename}.")