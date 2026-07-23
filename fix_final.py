with open('pipeline/computational_time_analysis.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Normalize line endings first
content = content.replace('\r\n', '\n')

# Fix 1 — main() signature
content = content.replace(
    'def main() -> None:',
    'def main(skip_rt: bool = False) -> None:'
)
print('Fix 1 done: main() signature')

# Fix 2 — wrap RT section
old_rt = (
    '    rt_all_cells   = [(j, n) for j in RT_JOBS_LIST for n in RT_NODES_LIST]\n'
    '    rt_valid_cells = [(j, n) for j, n in rt_all_cells if _rt_is_valid(j, n)]\n'
    '    rt_skip_cells  = [(j, n) for j, n in rt_all_cells if not _rt_is_valid(j, n)]\n'
    '    n_rt_threads   = len(rt_valid_cells) * len(RT_SOLVERS)'
)
new_rt = (
    '    if skip_rt:\n'
    '        rt_by_solver = {s: {} for s in RT_SOLVERS}\n'
    '    else:\n'
    '        rt_all_cells   = [(j, n) for j in RT_JOBS_LIST for n in RT_NODES_LIST]\n'
    '        rt_valid_cells = [(j, n) for j, n in rt_all_cells if _rt_is_valid(j, n)]\n'
    '        rt_skip_cells  = [(j, n) for j, n in rt_all_cells if not _rt_is_valid(j, n)]\n'
    '        n_rt_threads   = len(rt_valid_cells) * len(RT_SOLVERS)'
)
if old_rt in content:
    content = content.replace(old_rt, new_rt)
    print('Fix 2 done: RT section wrapped')
else:
    print('Fix 2 FAILED: RT block not found')

# Fix 3 — add --skip-rt to argparse
old_args = '    _args = _parser.parse_args()\n\n    if _args.graphs_only:'
new_args = (
    '    _parser.add_argument(\n'
    '        "--skip-rt", action="store_true",\n'
    '        help="Skip Real-Time analysis, run Plan-Ahead only",\n'
    '    )\n'
    '    _args = _parser.parse_args()\n\n'
    '    if _args.graphs_only:'
)
if old_args in content:
    content = content.replace(old_args, new_args)
    print('Fix 3 done: --skip-rt argument added')
else:
    print('Fix 3 FAILED: argparse block not found')

# Fix 4 — update main() call
old_call = '        main()\n'
new_call = '        main(skip_rt=_args.skip_rt)\n'
if old_call in content:
    content = content.replace(old_call, new_call)
    print('Fix 4 done: main() call updated')
else:
    print('Fix 4 FAILED: main() call not found')

with open('pipeline/computational_time_analysis.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print('All done')