"""
patch_scalability_experiments.py
──────────────────────────────────
Adds three new experiment modes to computational_time_analysis.py:

  --mode cap_sweep     Experiment A: 2-hour solver cap, same T×N grid
  --mode period_sweep  Experiment B: P=2,4,6,8 periods, subset T×N grid
  --mode weekly        Experiment C: 1-week horizon P=7, 4-hour cap

Run from repo root:
    python patch_scalability_experiments.py
"""
from pathlib import Path

target = Path('pipeline/computational_time_analysis.py')

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('\r\n', '\n')
applied = []

# ── Patch 1: Add experiment configurations after existing PA config ───────────
old1 = (
    '# Plan-Ahead model settings\n'
    'PA_NODE_CAPACITY   = 10.0   # capacity units per machine\n'
    'PA_ALWAYS_FRAC     = 0.5    # fraction of nodes that are always-on (M_a)\n'
    'PA_EXCL_FRAC       = 0.20   # fraction of tenants tagged as exclusive (T_e)\n'
    'PA_MIP_GAP         = 0.01   # Gurobi relative optimality gap target'
)
new1 = (
    '# Plan-Ahead model settings\n'
    'PA_NODE_CAPACITY   = 10.0   # capacity units per machine\n'
    'PA_ALWAYS_FRAC     = 0.5    # fraction of nodes that are always-on (M_a)\n'
    'PA_EXCL_FRAC       = 0.20   # fraction of tenants tagged as exclusive (T_e)\n'
    'PA_MIP_GAP         = 0.01   # Gurobi relative optimality gap target\n'
    '\n'
    '# ── Scalability experiments ────────────────────────────────────────────────\n'
    '# Experiment A — Solver cap comparison\n'
    'EXP_A_CAP_S        = 2 * 60 * 60   # 2 hours\n'
    'EXP_A_TENANTS      = [2, 8, 128, 256, 512]\n'
    'EXP_A_NODES        = [4, 16, 64, 256, 512, 1024]\n'
    'EXP_A_PERIODS      = 4\n'
    '\n'
    '# Experiment B — Period granularity sweep (subset grid, 5-min cap)\n'
    'EXP_B_PERIODS_LIST = [2, 4, 6, 8]  # number of planning slots\n'
    'EXP_B_TENANTS      = [2, 8, 128]   # subset only — larger T not needed\n'
    'EXP_B_NODES        = [64, 256, 1024]\n'
    'EXP_B_CAP_S        = 5 * 60        # 5 minutes (same as baseline)\n'
    '\n'
    '# Experiment C — Weekly horizon (P=7, one 24-hour slot per day, 4-hour cap)\n'
    'EXP_C_PERIODS      = 7             # 7 daily slots = 1 week\n'
    'EXP_C_SLOT_HOURS   = 24            # hours per slot\n'
    'EXP_C_CAP_S        = 4 * 60 * 60  # 4 hours\n'
    'EXP_C_TENANTS      = [2, 8, 128, 256, 512]\n'
    'EXP_C_NODES        = [4, 16, 64, 256, 512, 1024]'
)
if old1 in content:
    content = content.replace(old1, new1)
    applied.append('1: experiment configurations added')
else:
    print('FAILED Patch 1: PA model settings block not found')

# ── Patch 2: Add ExperimentResult dataclass after PAResult ────────────────────
old2 = (
    '# ═══════════════════════════════════════════════════════════════════════════════\n'
    '# § FEASIBILITY FILTERS'
)
new2 = (
    '@dataclass\n'
    'class ExperimentResult:\n'
    '    """Extended PAResult with experiment metadata."""\n'
    '    experiment:  str           # "cap_sweep" | "period_sweep" | "weekly"\n'
    '    n_tenants:   int\n'
    '    n_nodes:     int\n'
    '    n_periods:   int\n'
    '    slot_hours:  float         # hours per planning slot\n'
    '    solver_cap_s: int          # solver time limit used\n'
    '    n_vars:      int\n'
    '    n_bin_vars:  int\n'
    '    n_cont_vars: int\n'
    '    n_constrs:   int\n'
    '    build_s:     float\n'
    '    solve_s:     float\n'
    '    total_s:     float\n'
    '    obj_val:     float | None\n'
    '    mip_gap:     float | None\n'
    '    status:      str\n'
    '\n'
    '\n'
    '# ═══════════════════════════════════════════════════════════════════════════════\n'
    '# § FEASIBILITY FILTERS'
)
if old2 in content:
    content = content.replace(old2, new2)
    applied.append('2: ExperimentResult dataclass added')
else:
    print('FAILED Patch 2: FEASIBILITY FILTERS section not found')

# ── Patch 3: Add time_pa_experiment function after time_pa ───────────────────
old3 = 'def _pa_var_estimate(n_tenants: int, n_nodes: int, n_periods: int, n_excl: int) -> int:'

new3 = (
    'def time_pa_experiment(\n'
    '    experiment: str,\n'
    '    n_tenants: int,\n'
    '    n_nodes: int,\n'
    '    n_periods: int,\n'
    '    slot_hours: float,\n'
    '    solver_cap_s: int,\n'
    ') -> ExperimentResult:\n'
    '    """Run one PA MISOCP cell with custom periods and solver cap.\n'
    '    Mirrors time_pa() but accepts experiment-specific parameters.\n'
    '    """\n'
    '    n_always = max(1, int(n_nodes * PA_ALWAYS_FRAC))\n'
    '    n_excl   = min(max(1, int(n_tenants * PA_EXCL_FRAC)), n_tenants - 1)\n'
    '\n'
    '    min_cap = (n_tenants * PA_USAGE_MAX) / max(1, n_nodes) * 1.3\n'
    '    cap     = max(PA_NODE_CAPACITY, min_cap)\n'
    '    cap     = min(cap, 500.0)\n'
    '    usage_max = min(PA_USAGE_MAX, cap * 0.70)\n'
    '    usage_min = min(PA_USAGE_MIN, usage_max * 0.50)\n'
    '\n'
    '    P = build_synthetic_data(\n'
    '        seed=SEED, n_tenants=n_tenants, n_nodes=n_nodes, n_intervals=n_periods,\n'
    '        node_capacity=cap, n_always_available=n_always, n_exclusive=n_excl,\n'
    '        tenant_usage_min=usage_min, tenant_usage_max=usage_max,\n'
    '        sigma_frac=0.20, epsilon=0.10, min_machines_per_tenant=1,\n'
    '    )\n'
    '\n'
    '    env = make_gurobi_env()\n'
    '    try:\n'
    '        t_build = time.perf_counter()\n'
    '        model, _ = build_model(P, env, use_socp=True)\n'
    '        build_s = time.perf_counter() - t_build\n'
    '\n'
    '        model.Params.LogToConsole = 0\n'
    '        model.Params.OutputFlag   = 0\n'
    '        model.Params.TimeLimit    = solver_cap_s\n'
    '        model.Params.MIPGap       = PA_MIP_GAP\n'
    '        model.Params.Threads      = max(1, (os.cpu_count() or 4) // 4)\n'
    '\n'
    '        n_vars = model.NumVars\n'
    '        model.optimize()\n'
    '        solve_s = model.Runtime\n'
    '\n'
    '        n_bin_vars  = model.NumBinVars\n'
    '        n_cont_vars = model.NumVars - model.NumBinVars\n'
    '        n_constrs   = model.NumConstrs + model.NumQConstrs + model.NumGenConstrs\n'
    '        try:    obj_val = model.ObjVal\n'
    '        except: obj_val = None\n'
    '\n'
    '        sc = model.Status\n'
    '        if sc == GRB.OPTIMAL:\n'
    '            status, gap = "OPT", model.MIPGap\n'
    '        elif sc == GRB.TIME_LIMIT:\n'
    '            status = "TLim"\n'
    '            try:    gap = model.MIPGap\n'
    '            except: gap = None\n'
    '        elif sc in (GRB.INFEASIBLE, GRB.INF_OR_UNBD):\n'
    '            status, gap = "INF", None\n'
    '        else:\n'
    '            status, gap = f"S{sc}", None\n'
    '\n'
    '        model.dispose()\n'
    '        env.dispose()\n'
    '\n'
    '    except Exception as exc:\n'
    '        _pr(f"EXP-{experiment}  T={n_tenants:<5} N={n_nodes:<5} P={n_periods} ERR: {exc}")\n'
    '        try: env.dispose()\n'
    '        except: pass\n'
    '        n_excl_est = min(max(1, int(n_tenants * PA_EXCL_FRAC)), n_tenants - 1)\n'
    '        n_v = _pa_var_estimate(n_tenants, n_nodes, n_periods, n_excl_est)\n'
    '        return ExperimentResult(\n'
    '            experiment=experiment, n_tenants=n_tenants, n_nodes=n_nodes,\n'
    '            n_periods=n_periods, slot_hours=slot_hours, solver_cap_s=solver_cap_s,\n'
    '            n_vars=n_v, n_bin_vars=0, n_cont_vars=0, n_constrs=0,\n'
    '            build_s=0.0, solve_s=0.0, total_s=0.0,\n'
    '            obj_val=None, mip_gap=None, status="ERR",\n'
    '        )\n'
    '\n'
    '    total_s = build_s + solve_s\n'
    '    labels  = {"OPT": "OPTIMAL", "TLim": "CAPPED", "INF": "INFEASIBLE"}\n'
    '    _pr(f"EXP-{experiment}  T={n_tenants:<5} N={n_nodes:<5} P={n_periods} "\n'
    '        f"→ {total_s:>10.2f} s  vars={n_vars:,}  [{labels.get(status, status)}]")\n'
    '\n'
    '    return ExperimentResult(\n'
    '        experiment=experiment, n_tenants=n_tenants, n_nodes=n_nodes,\n'
    '        n_periods=n_periods, slot_hours=slot_hours, solver_cap_s=solver_cap_s,\n'
    '        n_vars=n_vars, n_bin_vars=n_bin_vars, n_cont_vars=n_cont_vars,\n'
    '        n_constrs=n_constrs,\n'
    '        build_s=build_s, solve_s=solve_s, total_s=total_s,\n'
    '        obj_val=obj_val, mip_gap=gap, status=status,\n'
    '    )\n'
    '\n'
    '\n'
    'def _run_experiment(\n'
    '    experiment: str,\n'
    '    tenants_list: list,\n'
    '    nodes_list: list,\n'
    '    periods_list: list,\n'
    '    slot_hours: float,\n'
    '    solver_cap_s: int,\n'
    '    csv_name: str,\n'
    ') -> list:\n'
    '    """Run a grid of (T, N, P) cells concurrently and save to CSV."""\n'
    '    valid_cells = [\n'
    '        (t, n, p) for t in tenants_list for n in nodes_list for p in periods_list\n'
    '        if n >= t\n'
    '    ]\n'
    '    skip_cells = [\n'
    '        (t, n, p) for t in tenants_list for n in nodes_list for p in periods_list\n'
    '        if n < t\n'
    '    ]\n'
    '\n'
    '    cap_label = f"{solver_cap_s//3600}h" if solver_cap_s >= 3600 else f"{solver_cap_s//60}min"\n'
    '    _hdr(f"EXPERIMENT {experiment.upper()} — cap={cap_label}  P={periods_list}  "\n'
    '         f"horizon={int(max(periods_list)*slot_hours)}h")\n'
    '    print(f"  Grid   : T={tenants_list}  N={nodes_list}  P={periods_list}")\n'
    '    print(f"  Cap    : {cap_label} per cell")\n'
    '    print(f"  Slot   : {slot_hours}h per period  "\n'
    '          f"(horizon = {int(max(periods_list)*slot_hours)}h)")\n'
    '    print(f"  Cells  : {len(valid_cells)} active, {len(skip_cells)} skipped (N < T)")\n'
    '    print()\n'
    '\n'
    '    # Skip rows\n'
    '    results = []\n'
    '    for t, n, p in skip_cells:\n'
    '        n_excl_est = min(max(1, int(t * PA_EXCL_FRAC)), t - 1)\n'
    '        n_v = _pa_var_estimate(t, n, p, n_excl_est)\n'
    '        results.append(ExperimentResult(\n'
    '            experiment=experiment, n_tenants=t, n_nodes=n,\n'
    '            n_periods=p, slot_hours=slot_hours, solver_cap_s=solver_cap_s,\n'
    '            n_vars=n_v, n_bin_vars=0, n_cont_vars=0, n_constrs=0,\n'
    '            build_s=0.0, solve_s=0.0, total_s=0.0,\n'
    '            obj_val=None, mip_gap=None, status="SKIP",\n'
    '        ))\n'
    '\n'
    '    # Run valid cells concurrently\n'
    '    with ThreadPoolExecutor(max_workers=max(1, len(valid_cells))) as pool:\n'
    '        futures = {\n'
    '            pool.submit(\n'
    '                time_pa_experiment, experiment, t, n, p, slot_hours, solver_cap_s\n'
    '            ): (t, n, p)\n'
    '            for t, n, p in valid_cells\n'
    '        }\n'
    '        for fut in as_completed(futures):\n'
    '            results.append(fut.result())\n'
    '\n'
    '    # Save CSV\n'
    '    _save_csv(csv_name,\n'
    '              ["experiment", "n_tenants", "n_nodes", "n_periods", "slot_hours",\n'
    '               "solver_cap_s", "n_vars", "n_bin_vars", "n_cont_vars", "n_constrs",\n'
    '               "build_s", "solve_s", "total_s", "obj_val", "mip_gap", "status"],\n'
    '              [[r.experiment, r.n_tenants, r.n_nodes, r.n_periods, r.slot_hours,\n'
    '                r.solver_cap_s, r.n_vars, r.n_bin_vars, r.n_cont_vars, r.n_constrs,\n'
    '                round(r.build_s, 4), round(r.solve_s, 4), round(r.total_s, 4),\n'
    '                round(r.obj_val, 4) if r.obj_val is not None else "",\n'
    '                round(r.mip_gap, 6) if r.mip_gap is not None else "",\n'
    '                r.status]\n'
    '               for r in sorted(results, key=lambda x: (x.n_tenants, x.n_nodes, x.n_periods))])\n'
    '    return results\n'
    '\n'
    '\n'
    'def run_exp_a() -> list:\n'
    '    """Experiment A: 2-hour cap, same grid as baseline."""\n'
    '    return _run_experiment(\n'
    '        experiment="cap_sweep",\n'
    '        tenants_list=EXP_A_TENANTS, nodes_list=EXP_A_NODES,\n'
    '        periods_list=[EXP_A_PERIODS], slot_hours=6.0,\n'
    '        solver_cap_s=EXP_A_CAP_S, csv_name="pa_cap_sweep.csv",\n'
    '    )\n'
    '\n'
    '\n'
    'def run_exp_b() -> list:\n'
    '    """Experiment B: period granularity sweep, 24h horizon."""\n'
    '    return _run_experiment(\n'
    '        experiment="period_sweep",\n'
    '        tenants_list=EXP_B_TENANTS, nodes_list=EXP_B_NODES,\n'
    '        periods_list=EXP_B_PERIODS_LIST,\n'
    '        slot_hours=6.0,   # 24h / 4 periods = 6h per slot (varies with P)\n'
    '        solver_cap_s=EXP_B_CAP_S, csv_name="pa_period_sweep.csv",\n'
    '    )\n'
    '\n'
    '\n'
    'def run_exp_c() -> list:\n'
    '    """Experiment C: weekly horizon P=7, 4-hour cap."""\n'
    '    return _run_experiment(\n'
    '        experiment="weekly",\n'
    '        tenants_list=EXP_C_TENANTS, nodes_list=EXP_C_NODES,\n'
    '        periods_list=[EXP_C_PERIODS], slot_hours=float(EXP_C_SLOT_HOURS),\n'
    '        solver_cap_s=EXP_C_CAP_S, csv_name="pa_weekly.csv",\n'
    '    )\n'
    '\n'
    '\n'
    'def _pa_var_estimate(n_tenants: int, n_nodes: int, n_periods: int, n_excl: int) -> int:'
)

if old3 in content:
    content = content.replace(old3, new3)
    applied.append('3: time_pa_experiment + _run_experiment + run_exp_a/b/c added')
else:
    print('FAILED Patch 3: _pa_var_estimate marker not found')

# ── Patch 4: Update argparse to add --mode flag ───────────────────────────────
old4 = (
    'if __name__ == "__main__":\n'
    '    import argparse as _ap\n'
    '    _parser = _ap.ArgumentParser(description="Computational time analysis")\n'
    '    _parser.add_argument(\n'
    '        "--graphs-only", action="store_true",\n'
    '        help="Skip timing; regenerate all plots from saved rt_timing.csv / pa_timing_grid.csv",\n'
    '    )\n'
    '    _parser.add_argument(\n'
    '        "--skip-rt", action="store_true",\n'
    '        help="Skip Real-Time analysis, run Plan-Ahead only",\n'
    '    )\n'
    '    _args = _parser.parse_args()\n'
    '\n'
    '    if _args.graphs_only:\n'
    '        print("  Regenerating plots from saved CSVs ...")\n'
    '        _rt, _pa = load_results_from_csv()\n'
    '        if not _rt and not _pa:\n'
    '            print("  No saved data found. Run without --graphs-only first.")\n'
    '        else:\n'
    '            _generate_plots(_rt, _pa)\n'
    '            print("  Done.")\n'
    '    else:\n'
    '        main(skip_rt=_args.skip_rt)'
)
new4 = (
    'if __name__ == "__main__":\n'
    '    import argparse as _ap\n'
    '    _parser = _ap.ArgumentParser(description="Computational time analysis")\n'
    '    _parser.add_argument(\n'
    '        "--graphs-only", action="store_true",\n'
    '        help="Skip timing; regenerate all plots from saved rt_timing.csv / pa_timing_grid.csv",\n'
    '    )\n'
    '    _parser.add_argument(\n'
    '        "--skip-rt", action="store_true",\n'
    '        help="Skip Real-Time analysis, run Plan-Ahead only",\n'
    '    )\n'
    '    _parser.add_argument(\n'
    '        "--mode", choices=["cap_sweep", "period_sweep", "weekly"],\n'
    '        default=None,\n'
    '        help="Run a specific scalability experiment instead of the baseline",\n'
    '    )\n'
    '    _args = _parser.parse_args()\n'
    '\n'
    '    if _args.graphs_only:\n'
    '        print("  Regenerating plots from saved CSVs ...")\n'
    '        _rt, _pa = load_results_from_csv()\n'
    '        if not _rt and not _pa:\n'
    '            print("  No saved data found. Run without --graphs-only first.")\n'
    '        else:\n'
    '            _generate_plots(_rt, _pa)\n'
    '            print("  Done.")\n'
    '    elif _args.mode == "cap_sweep":\n'
    '        _T0 = time.perf_counter()\n'
    '        run_exp_a()\n'
    '    elif _args.mode == "period_sweep":\n'
    '        _T0 = time.perf_counter()\n'
    '        run_exp_b()\n'
    '    elif _args.mode == "weekly":\n'
    '        _T0 = time.perf_counter()\n'
    '        run_exp_c()\n'
    '    else:\n'
    '        main(skip_rt=_args.skip_rt)'
)
if old4 in content:
    content = content.replace(old4, new4)
    applied.append('4: argparse --mode flag added')
else:
    print('FAILED Patch 4: argparse block not found')

# ── Write output ──────────────────────────────────────────────────────────────
with open(target, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print(f'\n{len(applied)}/4 patches applied:')
for a in applied:
    print(f'  ✅ {a}')

print('\nVerify with:')
print('  python -c "import ast; ast.parse(open(\'pipeline/computational_time_analysis.py\', encoding=\'utf-8\').read()); print(\'Syntax OK\')"')
print('\nTest each mode:')
print('  cd pipeline')
print('  python computational_time_analysis.py --mode period_sweep')
