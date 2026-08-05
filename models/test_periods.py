import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'realtime')
from plan_ahead_iterative import run_iterative

stats, completed, obj = run_iterative(total_tenants=8, seed=42, verbose=False, n_periods=7)
print('P=7 obj:', obj)

stats, completed, obj = run_iterative(total_tenants=8, seed=42, verbose=False, n_periods=2)
print('P=2 obj:', obj)