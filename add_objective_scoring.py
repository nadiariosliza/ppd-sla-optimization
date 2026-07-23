"""
add_objective_scoring.py
─────────────────────────
Adds objective value computation to plan_ahead_iterative.py so that
the iterative approach can be compared to Gurobi on the same metric.

Run from repo root:
    python add_objective_scoring.py

What this adds:
1. Tracks which tenants are assigned to which nodes during allocation
2. Computes InfraCost, Fairness (sigma), and MixBonus from placement
3. Returns objective value = lam0*InfraCost - lam1*sigma - lam2*MixBonus
4. Adds obj_val to the run_iterative() return value
"""

from pathlib import Path

target = Path('models/plan_ahead_iterative.py')

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

# ── Patch 1: Add node assignment tracking to IterNode dataclass ───────────────
old_iternode = '''@dataclass
class IterNode:
    node_id:   int
    remaining: dict[int, float]   # period h → remaining capacity

    def max_remaining(self) -> float:
        return max(self.remaining.values()) if self.remaining else 0.0

    def is_full(self) -> bool:
        return self.max_remaining() < EVICT_THRESH * NODE_CAPACITY

    def total_used(self) -> float:
        return sum(
            NODE_CAPACITY - self.remaining.get(h, NODE_CAPACITY)
            for h in self.remaining
        )'''

new_iternode = '''@dataclass
class IterNode:
    node_id:   int
    remaining: dict[int, float]   # period h → remaining capacity
    tenants_assigned: set = field(default_factory=set)  # tenant_ids assigned to this node

    def max_remaining(self) -> float:
        return max(self.remaining.values()) if self.remaining else 0.0

    def is_full(self) -> bool:
        return self.max_remaining() < EVICT_THRESH * NODE_CAPACITY

    def total_used(self) -> float:
        return sum(
            NODE_CAPACITY - self.remaining.get(h, NODE_CAPACITY)
            for h in self.remaining
        )'''

if old_iternode in content:
    content = content.replace(old_iternode, new_iternode)
    print('Patch 1 done: IterNode tracking added')
else:
    print('Patch 1 FAILED: IterNode not found')

# ── Patch 2: Track node assignment in _allocate_greedy ───────────────────────
old_alloc = '''            alloc = min(rem, avail)
            tenant.placed[h] = tenant.placed.get(h, 0.0) + alloc
            best_node.remaining[h] -= alloc
            placed_total += alloc'''

new_alloc = '''            alloc = min(rem, avail)
            tenant.placed[h] = tenant.placed.get(h, 0.0) + alloc
            best_node.remaining[h] -= alloc
            best_node.tenants_assigned.add(tenant.tenant_id)
            placed_total += alloc'''

if old_alloc in content:
    content = content.replace(old_alloc, new_alloc)
    print('Patch 2 done: assignment tracking in allocate_greedy added')
else:
    print('Patch 2 FAILED: allocate_greedy block not found')

# ── Patch 3: Track all_nodes_used in run_iterative ───────────────────────────
old_run_init = '''    completed:  list[IterTenant] = []
    stats_log:  list[IterStats]  = []
    stall_count = 0
    t_wall = time.perf_counter()'''

new_run_init = '''    completed:  list[IterTenant] = []
    stats_log:  list[IterStats]  = []
    all_nodes_used: list[IterNode] = []   # tracks every node ever activated
    stall_count = 0
    t_wall = time.perf_counter()'''

if old_run_init in content:
    content = content.replace(old_run_init, new_run_init)
    print('Patch 3a done: all_nodes_used tracker added')
else:
    print('Patch 3a FAILED')

# Track initial nodes
old_seed_nodes = '''    active_nodes: list[IterNode] = [_fresh_node(i) for i in range(UNIT_NODES)]
    next_node_id = UNIT_NODES'''

new_seed_nodes = '''    active_nodes: list[IterNode] = [_fresh_node(i) for i in range(UNIT_NODES)]
    all_nodes_used.extend(active_nodes)
    next_node_id = UNIT_NODES'''

if old_seed_nodes in content:
    content = content.replace(old_seed_nodes, new_seed_nodes)
    print('Patch 3b done: initial nodes tracked')
else:
    print('Patch 3b FAILED')

# Track fresh nodes when provisioned
old_fresh = '''                fresh = _fresh_node(next_node_id)
                next_node_id += 1
                new_nodes.append(fresh)
                nodes_provisioned += 1'''

new_fresh = '''                fresh = _fresh_node(next_node_id)
                next_node_id += 1
                new_nodes.append(fresh)
                all_nodes_used.append(fresh)
                nodes_provisioned += 1'''

if old_fresh in content:
    content = content.replace(old_fresh, new_fresh, 1)  # only first occurrence
    print('Patch 3c done: fresh node tracking added')
else:
    print('Patch 3c FAILED')

# Track stall-eviction fresh node
old_stall_fresh = '''                fresh = _fresh_node(next_node_id)
                next_node_id += 1
                active_nodes.append(fresh)
                nodes_evicted    += 1
                nodes_provisioned += 1'''

new_stall_fresh = '''                fresh = _fresh_node(next_node_id)
                next_node_id += 1
                active_nodes.append(fresh)
                all_nodes_used.append(fresh)
                nodes_evicted    += 1
                nodes_provisioned += 1'''

if old_stall_fresh in content:
    content = content.replace(old_stall_fresh, new_stall_fresh)
    print('Patch 3d done: stall fresh node tracking added')
else:
    print('Patch 3d FAILED')

# ── Patch 4: Add objective scoring function before run_iterative ──────────────
objective_fn = '''
# ═══════════════════════════════════════════════════════════════════════════════
# § OBJECTIVE SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def compute_objective(
    completed: list,
    all_nodes: list,
    lam: dict | None = None,
    n_periods: int = N_PERIODS,
) -> dict:
    """
    Compute the MISOCP objective value from the iterative solution placement.

    Objective = lam[0]*InfraCost - lam[1]*sigma - lam[2]*MixBonus

    Components:
      InfraCost : number of nodes actually used (activated)
      sigma     : minimum demand-satisfaction fraction across all tenants
      MixBonus  : number of nodes that have both heavy and light tenants assigned

    Returns dict with all components and the final objective value.
    """
    if lam is None:
        lam = {0: 1.0, 1: 5.0, 2: 2.0}

    # ── InfraCost: count nodes that were actually used ─────────────────────────
    nodes_used = [n for n in all_nodes if len(n.tenants_assigned) > 0]
    infra_cost = float(len(nodes_used))

    # ── Fairness sigma: minimum satisfaction across all tenants ───────────────
    satisfactions = [t.satisfaction_frac() for t in completed]
    sigma = min(satisfactions) if satisfactions else 0.0

    # ── Mix Bonus: nodes with both heavy and light tenants ────────────────────
    # Classify tenants by average demand
    if completed:
        avg_demands = {t.tenant_id: t.total_demand() / max(1, n_periods)
                       for t in completed}
        median_demand = sorted(avg_demands.values())[len(avg_demands) // 2]
        heavy_ids = {tid for tid, d in avg_demands.items() if d >= median_demand}
        light_ids = {tid for tid, d in avg_demands.items() if d < median_demand}

        mix_bonus = sum(
            1 for n in nodes_used
            if (n.tenants_assigned & heavy_ids) and (n.tenants_assigned & light_ids)
        )
    else:
        mix_bonus = 0

    # ── Final objective ────────────────────────────────────────────────────────
    obj_val = lam[0] * infra_cost - lam[1] * sigma - lam[2] * mix_bonus

    return {
        "obj_val":    round(obj_val, 4),
        "infra_cost": round(infra_cost, 4),
        "sigma":      round(sigma, 4),
        "mix_bonus":  round(float(mix_bonus), 4),
        "nodes_used": len(nodes_used),
        "n_tenants":  len(completed),
    }

'''

# Insert before run_iterative
old_run_marker = '''def run_iterative(
    total_tenants: int = TOTAL_TENANTS,'''

if old_run_marker in content:
    content = content.replace(old_run_marker, objective_fn + old_run_marker)
    print('Patch 4 done: compute_objective() function added')
else:
    print('Patch 4 FAILED: run_iterative marker not found')

# ── Patch 5: Return all_nodes_used and obj_val from run_iterative ─────────────
old_return = '''    return stats_log, completed'''

new_return = '''    obj_metrics = compute_objective(completed, all_nodes_used)
    return stats_log, completed, obj_metrics'''

if old_return in content:
    content = content.replace(old_return, new_return)
    print('Patch 5 done: run_iterative now returns obj_metrics')
else:
    print('Patch 5 FAILED: return statement not found')

# ── Patch 6: Update _report call in main() to handle new return value ─────────
old_main_call = '''    stats, completed = run_iterative(
        total_tenants=args.tenants,
        seed=args.seed,
        verbose=True,
    )
    _report(stats, completed, args.tenants)'''

new_main_call = '''    stats, completed, obj_metrics = run_iterative(
        total_tenants=args.tenants,
        seed=args.seed,
        verbose=True,
    )
    _report(stats, completed, args.tenants)
    print(f"\\n  Objective value  : {obj_metrics['obj_val']}")
    print(f"  InfraCost        : {obj_metrics['infra_cost']} nodes activated")
    print(f"  Fairness sigma   : {obj_metrics['sigma']:.4f}")
    print(f"  Mix bonus        : {obj_metrics['mix_bonus']} nodes with heavy+light mix")'''

if old_main_call in content:
    content = content.replace(old_main_call, new_main_call)
    print('Patch 6 done: main() updated to print objective')
else:
    print('Patch 6 FAILED: main() call block not found')

# ── Write output ──────────────────────────────────────────────────────────────
with open(target, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print()
print('Done. Verify with:')
print('  cd models')
print('  python plan_ahead_iterative.py --tenants 8')
