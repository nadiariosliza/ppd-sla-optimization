"""
fix_nodes_order.py
Fixes the UnboundLocalError in plan_ahead_iterative.py by moving
all_nodes_used initialization to before the seed active window block.
"""
from pathlib import Path

target = Path('models/plan_ahead_iterative.py')

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

# The problem: all_nodes_used is initialized after the line that uses it.
# Fix: move it to before the seed active window block.

old = (
    '    tenant_queue  = _make_tenants(total_tenants, seed)\n'
    '    next_node_id  = 0\n'
    '\n'
    '    # Seed active window\n'
    '    active_tenants: list[IterTenant] = []\n'
    '    while tenant_queue and len(active_tenants) < UNIT_TENANTS:\n'
    '        active_tenants.append(tenant_queue.popleft())\n'
    '\n'
    '    active_nodes: list[IterNode] = [_fresh_node(i) for i in range(UNIT_NODES)]\n'
    '    all_nodes_used.extend(active_nodes)\n'
    '    next_node_id = UNIT_NODES\n'
    '\n'
    '    completed:  list[IterTenant] = []\n'
    '    stats_log:  list[IterStats]  = []\n'
    '    all_nodes_used: list[IterNode] = []   # tracks every node ever activated'
)

new = (
    '    tenant_queue  = _make_tenants(total_tenants, seed)\n'
    '    next_node_id  = 0\n'
    '\n'
    '    # Seed active window\n'
    '    active_tenants: list[IterTenant] = []\n'
    '    while tenant_queue and len(active_tenants) < UNIT_TENANTS:\n'
    '        active_tenants.append(tenant_queue.popleft())\n'
    '\n'
    '    completed:  list[IterTenant] = []\n'
    '    stats_log:  list[IterStats]  = []\n'
    '    all_nodes_used: list[IterNode] = []   # tracks every node ever activated\n'
    '\n'
    '    active_nodes: list[IterNode] = [_fresh_node(i) for i in range(UNIT_NODES)]\n'
    '    all_nodes_used.extend(active_nodes)\n'
    '    next_node_id = UNIT_NODES'
)

if old in content:
    content = content.replace(old, new)
    print('Fix applied: all_nodes_used now initialized before use')
else:
    print('FAILED: block not found — trying alternative...')
    # Try normalizing line endings
    content_n = content.replace('\r\n', '\n')
    old_n = old.replace('\r\n', '\n')
    if old_n in content_n:
        content_n = content_n.replace(old_n, new)
        content = content_n
        print('Fix applied (after normalizing line endings)')
    else:
        print('Still failed — check manually')
        exit(1)

with open(target, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print('Done')
