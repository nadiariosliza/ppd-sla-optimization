"""
patch_iter_analysis.py
───────────────────────
Adds obj_val field to PAIterResult and PAIterGridResult dataclasses,
updates run_iterative() calls to unpack 3 return values, and adds
obj_val to both CSV outputs and load functions.

Run from repo root:
    python patch_iter_analysis.py
"""
from pathlib import Path

target = Path('pipeline/computational_time_analysis_iterative.py')

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('\r\n', '\n')
patches_applied = []

# ── Patch 1: Add obj_val to PAIterResult ─────────────────────────────────────
old1 = (
    '@dataclass\n'
    'class PAIterResult:\n'
    '    n_tenants:    int\n'
    '    iterations:   int\n'
    '    satisfaction: float   # 0–1\n'
    '    nodes_used:   int\n'
    '    elapsed_s:    float'
)
new1 = (
    '@dataclass\n'
    'class PAIterResult:\n'
    '    n_tenants:    int\n'
    '    iterations:   int\n'
    '    satisfaction: float        # 0–1\n'
    '    nodes_used:   int\n'
    '    elapsed_s:    float\n'
    '    obj_val:      float | None  # iterative objective value (lam0*cost - lam1*sigma - lam2*mix)'
)
if old1 in content:
    content = content.replace(old1, new1)
    patches_applied.append('1: PAIterResult.obj_val added')
else:
    print('FAILED Patch 1: PAIterResult not found')

# ── Patch 2: Add obj_val to PAIterGridResult ──────────────────────────────────
old2 = (
    '@dataclass\n'
    'class PAIterGridResult:\n'
    '    """One (tenants, machines) cell of the PA-iterative T × N wall-time sweep."""\n'
    '    n_tenants:    int\n'
    '    n_nodes:      int      # active node-pool size (UNIT_NODES) for this run\n'
    '    iterations:   int\n'
    '    satisfaction: float    # 0–1\n'
    '    nodes_used:   int\n'
    '    elapsed_s:    float'
)
new2 = (
    '@dataclass\n'
    'class PAIterGridResult:\n'
    '    """One (tenants, machines) cell of the PA-iterative T × N wall-time sweep."""\n'
    '    n_tenants:    int\n'
    '    n_nodes:      int      # active node-pool size (UNIT_NODES) for this run\n'
    '    iterations:   int\n'
    '    satisfaction: float        # 0–1\n'
    '    nodes_used:   int\n'
    '    elapsed_s:    float\n'
    '    obj_val:      float | None  # iterative objective value'
)
if old2 in content:
    content = content.replace(old2, new2)
    patches_applied.append('2: PAIterGridResult.obj_val added')
else:
    print('FAILED Patch 2: PAIterGridResult not found')

# ── Patch 3: Update time_pa_iter() to unpack 3 values and capture obj_val ────
old3 = (
    'def time_pa_iter(n_tenants: int) -> PAIterResult:\n'
    '    t0 = time.perf_counter()\n'
    '    try:\n'
    '        stats, completed = run_iterative(\n'
    '            total_tenants=n_tenants, seed=PA_SEED, verbose=False,\n'
    '        )\n'
    '    except Exception as exc:\n'
    '        _pr(f"PA-iter T={n_tenants} ERR: {exc}")\n'
    '        return PAIterResult(n_tenants=n_tenants, iterations=0,\n'
    '                            satisfaction=0.0, nodes_used=0, elapsed_s=0.0)\n'
    '\n'
    '    elapsed_s = time.perf_counter() - t0\n'
    '    iters     = len(stats)\n'
    '    nodes_used = stats[-1].active_nodes + sum(s.nodes_evicted for s in stats) if stats else 0\n'
    '    satisfaction = (\n'
    '        sum(c.satisfaction_frac() for c in completed) / max(1, len(completed))\n'
    '        if completed else 0.0\n'
    '    )\n'
    '    _pr(f"PA-iter T={n_tenants:<5} → {elapsed_s:.4f}s  "\n'
    '        f"iters={iters}  sat={satisfaction:.1%}  nodes={nodes_used}")\n'
    '    return PAIterResult(n_tenants=n_tenants, iterations=iters,\n'
    '                        satisfaction=satisfaction, nodes_used=nodes_used,\n'
    '                        elapsed_s=elapsed_s)'
)
new3 = (
    'def time_pa_iter(n_tenants: int) -> PAIterResult:\n'
    '    t0 = time.perf_counter()\n'
    '    try:\n'
    '        stats, completed, obj_metrics = run_iterative(\n'
    '            total_tenants=n_tenants, seed=PA_SEED, verbose=False,\n'
    '        )\n'
    '    except Exception as exc:\n'
    '        _pr(f"PA-iter T={n_tenants} ERR: {exc}")\n'
    '        return PAIterResult(n_tenants=n_tenants, iterations=0,\n'
    '                            satisfaction=0.0, nodes_used=0, elapsed_s=0.0,\n'
    '                            obj_val=None)\n'
    '\n'
    '    elapsed_s = time.perf_counter() - t0\n'
    '    iters     = len(stats)\n'
    '    nodes_used = stats[-1].active_nodes + sum(s.nodes_evicted for s in stats) if stats else 0\n'
    '    satisfaction = (\n'
    '        sum(c.satisfaction_frac() for c in completed) / max(1, len(completed))\n'
    '        if completed else 0.0\n'
    '    )\n'
    '    obj_val = obj_metrics.get("obj_val") if obj_metrics else None\n'
    '    _pr(f"PA-iter T={n_tenants:<5} → {elapsed_s:.4f}s  "\n'
    '        f"iters={iters}  sat={satisfaction:.1%}  nodes={nodes_used}  obj={obj_val}")\n'
    '    return PAIterResult(n_tenants=n_tenants, iterations=iters,\n'
    '                        satisfaction=satisfaction, nodes_used=nodes_used,\n'
    '                        elapsed_s=elapsed_s, obj_val=obj_val)'
)
if old3 in content:
    content = content.replace(old3, new3)
    patches_applied.append('3: time_pa_iter() updated')
else:
    print('FAILED Patch 3: time_pa_iter() not found')

# ── Patch 4: Update time_pa_iter_grid() to unpack 3 values ───────────────────
old4 = (
    '        stats, completed = _pai.run_iterative(\n'
    '            total_tenants=n_tenants, seed=PA_SEED, verbose=False,\n'
    '        )\n'
    '        elapsed_s = time.perf_counter() - t0\n'
    '    except Exception as exc:\n'
    '        _pr(f"PA-grid T={n_tenants:<5} N={n_nodes:<5} ERR: {exc}")\n'
    '        return PAIterGridResult(n_tenants=n_tenants, n_nodes=n_nodes,\n'
    '                                iterations=0, satisfaction=0.0,\n'
    '                                nodes_used=0, elapsed_s=0.0)\n'
    '    finally:\n'
    '        _pai.UNIT_NODES = old_units\n'
    '\n'
    '    iters      = len(stats)\n'
    '    nodes_used = (stats[-1].active_nodes + sum(s.nodes_evicted for s in stats)) if stats else 0\n'
    '    satisfaction = (\n'
    '        sum(c.satisfaction_frac() for c in completed) / max(1, len(completed))\n'
    '        if completed else 0.0\n'
    '    )\n'
    '    _pr(f"PA-grid T={n_tenants:<5} N={n_nodes:<5} → {elapsed_s*1000:>9.1f} ms  "\n'
    '        f"iters={iters}  sat={satisfaction:.1%}")\n'
    '    return PAIterGridResult(n_tenants=n_tenants, n_nodes=n_nodes,\n'
    '                            iterations=iters, satisfaction=satisfaction,\n'
    '                            nodes_used=nodes_used, elapsed_s=elapsed_s)'
)
new4 = (
    '        stats, completed, obj_metrics = _pai.run_iterative(\n'
    '            total_tenants=n_tenants, seed=PA_SEED, verbose=False,\n'
    '        )\n'
    '        elapsed_s = time.perf_counter() - t0\n'
    '    except Exception as exc:\n'
    '        _pr(f"PA-grid T={n_tenants:<5} N={n_nodes:<5} ERR: {exc}")\n'
    '        return PAIterGridResult(n_tenants=n_tenants, n_nodes=n_nodes,\n'
    '                                iterations=0, satisfaction=0.0,\n'
    '                                nodes_used=0, elapsed_s=0.0, obj_val=None)\n'
    '    finally:\n'
    '        _pai.UNIT_NODES = old_units\n'
    '\n'
    '    iters      = len(stats)\n'
    '    nodes_used = (stats[-1].active_nodes + sum(s.nodes_evicted for s in stats)) if stats else 0\n'
    '    satisfaction = (\n'
    '        sum(c.satisfaction_frac() for c in completed) / max(1, len(completed))\n'
    '        if completed else 0.0\n'
    '    )\n'
    '    obj_val = obj_metrics.get("obj_val") if obj_metrics else None\n'
    '    _pr(f"PA-grid T={n_tenants:<5} N={n_nodes:<5} → {elapsed_s*1000:>9.1f} ms  "\n'
    '        f"iters={iters}  sat={satisfaction:.1%}  obj={obj_val}")\n'
    '    return PAIterGridResult(n_tenants=n_tenants, n_nodes=n_nodes,\n'
    '                            iterations=iters, satisfaction=satisfaction,\n'
    '                            nodes_used=nodes_used, elapsed_s=elapsed_s, obj_val=obj_val)'
)
if old4 in content:
    content = content.replace(old4, new4)
    patches_applied.append('4: time_pa_iter_grid() updated')
else:
    print('FAILED Patch 4: time_pa_iter_grid() not found')

# ── Patch 5: Add obj_val to pa_iter_timing.csv save ──────────────────────────
old5 = (
    '    _save_csv("pa_iter_timing.csv",\n'
    '              ["n_tenants", "iterations", "satisfaction", "nodes_used", "elapsed_s"],\n'
    '              [[r.n_tenants, r.iterations, round(r.satisfaction, 6),\n'
    '                r.nodes_used, round(r.elapsed_s, 6)]\n'
    '               for r in pa_results])'
)
new5 = (
    '    _save_csv("pa_iter_timing.csv",\n'
    '              ["n_tenants", "iterations", "satisfaction", "nodes_used", "elapsed_s", "obj_val"],\n'
    '              [[r.n_tenants, r.iterations, round(r.satisfaction, 6),\n'
    '                r.nodes_used, round(r.elapsed_s, 6),\n'
    '                round(r.obj_val, 4) if r.obj_val is not None else ""]\n'
    '               for r in pa_results])'
)
if old5 in content:
    content = content.replace(old5, new5)
    patches_applied.append('5: pa_iter_timing.csv save updated')
else:
    print('FAILED Patch 5: pa_iter_timing.csv save not found')

# ── Patch 6: Add obj_val to pa_iter_grid.csv save ────────────────────────────
old6 = (
    '    _save_csv(csv_name,\n'
    '              ["n_tenants", "n_nodes", "iterations", "satisfaction",\n'
    '               "nodes_used", "elapsed_s"],\n'
    '              [[r.n_tenants, r.n_nodes, r.iterations, round(r.satisfaction, 6),\n'
    '                r.nodes_used, round(r.elapsed_s, 6)]\n'
    '               for r in grid.values() if r is not None])'
)
new6 = (
    '    _save_csv(csv_name,\n'
    '              ["n_tenants", "n_nodes", "iterations", "satisfaction",\n'
    '               "nodes_used", "elapsed_s", "obj_val"],\n'
    '              [[r.n_tenants, r.n_nodes, r.iterations, round(r.satisfaction, 6),\n'
    '                r.nodes_used, round(r.elapsed_s, 6),\n'
    '                round(r.obj_val, 4) if r.obj_val is not None else ""]\n'
    '               for r in grid.values() if r is not None])'
)
if old6 in content:
    content = content.replace(old6, new6)
    patches_applied.append('6: pa_iter_grid.csv save updated')
else:
    print('FAILED Patch 6: pa_iter_grid.csv save not found')

# ── Patch 7: Update _load_pa_iter_csv() to read obj_val ──────────────────────
old7 = (
    '            results.append(PAIterResult(\n'
    '                n_tenants=int(row["n_tenants"]),\n'
    '                iterations=int(row["iterations"]),\n'
    '                satisfaction=float(row["satisfaction"]),\n'
    '                nodes_used=int(row["nodes_used"]),\n'
    '                elapsed_s=float(row["elapsed_s"]),\n'
    '            ))'
)
new7 = (
    '            results.append(PAIterResult(\n'
    '                n_tenants=int(row["n_tenants"]),\n'
    '                iterations=int(row["iterations"]),\n'
    '                satisfaction=float(row["satisfaction"]),\n'
    '                nodes_used=int(row["nodes_used"]),\n'
    '                elapsed_s=float(row["elapsed_s"]),\n'
    '                obj_val=float(row["obj_val"]) if row.get("obj_val") else None,\n'
    '            ))'
)
if old7 in content:
    content = content.replace(old7, new7)
    patches_applied.append('7: _load_pa_iter_csv() updated')
else:
    print('FAILED Patch 7: _load_pa_iter_csv() not found')

# ── Patch 8: Update _load_pa_iter_grid_csv() to read obj_val ─────────────────
old8 = (
    '                grid[(t, n)] = PAIterGridResult(\n'
    '                    n_tenants=t, n_nodes=n,\n'
    '                    iterations=int(row["iterations"]),\n'
    '                    satisfaction=float(row["satisfaction"]),\n'
    '                    nodes_used=int(row["nodes_used"]),\n'
    '                    elapsed_s=float(row["elapsed_s"]),\n'
    '                )'
)
new8 = (
    '                grid[(t, n)] = PAIterGridResult(\n'
    '                    n_tenants=t, n_nodes=n,\n'
    '                    iterations=int(row["iterations"]),\n'
    '                    satisfaction=float(row["satisfaction"]),\n'
    '                    nodes_used=int(row["nodes_used"]),\n'
    '                    elapsed_s=float(row["elapsed_s"]),\n'
    '                    obj_val=float(row["obj_val"]) if row.get("obj_val") else None,\n'
    '                )'
)
if old8 in content:
    content = content.replace(old8, new8)
    patches_applied.append('8: _load_pa_iter_grid_csv() updated')
else:
    print('FAILED Patch 8: _load_pa_iter_grid_csv() not found')

# ── Write output ──────────────────────────────────────────────────────────────
with open(target, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print(f'\n{len(patches_applied)}/8 patches applied:')
for p in patches_applied:
    print(f'  ✅ Patch {p}')

print('\nVerify with:')
print('  python -c "import ast; ast.parse(open(\'pipeline/computational_time_analysis_iterative.py\', encoding=\'utf-8\').read()); print(\'Syntax OK\')"')
print('\nThen test with:')
print('  cd pipeline')
print('  python computational_time_analysis_iterative.py --skip-rt')
