with open('pipeline/computational_time_analysis.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Edit 1 — fix main() signature
old1 = 'def main() -> None:'
new1 = 'def main(skip_rt: bool = False) -> None:'
if old1 in content:
    content = content.replace(old1, new1)
    print('Edit 1 applied: main() signature updated')
else:
    print('Edit 1 FAILED: could not find main() signature')

# Edit 2 — add --skip-rt to argparse
old2 = '    _args = _parser.parse_args()'
new2 = ('    _parser.add_argument(\n'
        '        "--skip-rt", action="store_true",\n'
        '        help="Skip Real-Time analysis, run Plan-Ahead only",\n'
        '    )\n'
        '    _args = _parser.parse_args()')
if old2 in content:
    content = content.replace(old2, new2, 1)
    print('Edit 2 applied: --skip-rt argument added')
else:
    print('Edit 2 FAILED: could not find _args = _parser.parse_args()')

# Edit 3 — pass skip_rt to main() call
old3 = '        main()'
new3 = '        main(skip_rt=_args.skip_rt)'
if old3 in content:
    content = content.replace(old3, new3)
    print('Edit 3 applied: main() call updated')
else:
    print('Edit 3 FAILED: could not find main() call')

# Edit 4 — wrap RT section with if not skip_rt
old4 = ('    # ── Real-Time ──────────────────────────────────────────────────────────────\n'
        '\n'
        '    rt_all_cells   = [(j, n) for j in RT_JOBS_LIST for n in RT_NODES_LIST]\n'
        '    rt_valid_cells = [(j, n) for j, n in rt_all_cells if _rt_is_valid(j, n)]\n'
        '    rt_skip_cells  = [(j, n) for j, n in rt_all_cells if not _rt_is_valid(j, n)]\n'
        '    n_rt_threads   = len(rt_valid_cells) * len(RT_SOLVERS)')
new4 = ('    # ── Real-Time ──────────────────────────────────────────────────────────────\n'
        '\n'
        '    if not skip_rt:\n'
        '        rt_all_cells   = [(j, n) for j in RT_JOBS_LIST for n in RT_NODES_LIST]\n'
        '        rt_valid_cells = [(j, n) for j, n in rt_all_cells if _rt_is_valid(j, n)]\n'
        '        rt_skip_cells  = [(j, n) for j, n in rt_all_cells if not _rt_is_valid(j, n)]\n'
        '        n_rt_threads   = len(rt_valid_cells) * len(RT_SOLVERS)')
if old4 in content:
    content = content.replace(old4, new4)
    print('Edit 4 applied: RT section wrapped with if not skip_rt')
else:
    print('Edit 4 FAILED: could not find RT section header')

with open('pipeline/computational_time_analysis.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print('Script complete')