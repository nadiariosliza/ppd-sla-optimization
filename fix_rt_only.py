with open('pipeline/computational_time_analysis.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the exact line numbers
rt_start = None
rt_end   = None
main_call = None

for i, line in enumerate(lines):
    stripped = line.rstrip()
    if stripped == '    rt_all_cells   = [(j, n) for j in RT_JOBS_LIST for n in RT_NODES_LIST]':
        rt_start = i
    if stripped == '    n_rt_threads   = len(rt_valid_cells) * len(RT_SOLVERS)':
        rt_end = i
    if stripped == '        main()':
        main_call = i

print(f'rt_start={rt_start}, rt_end={rt_end}, main_call={main_call}')

if rt_start is None or rt_end is None:
    print('ERROR: could not find RT block lines')
    exit(1)

# Replace those 4 lines with the wrapped version
new_block = [
    '    if skip_rt:\n',
    '        rt_by_solver = {s: {} for s in RT_SOLVERS}\n',
    '    else:\n',
    '        rt_all_cells   = [(j, n) for j in RT_JOBS_LIST for n in RT_NODES_LIST]\n',
    '        rt_valid_cells = [(j, n) for j, n in rt_all_cells if _rt_is_valid(j, n)]\n',
    '        rt_skip_cells  = [(j, n) for j, n in rt_all_cells if not _rt_is_valid(j, n)]\n',
    '        n_rt_threads   = len(rt_valid_cells) * len(RT_SOLVERS)\n',
]

lines = lines[:rt_start] + new_block + lines[rt_end+1:]
print('Fix 2 done: RT block wrapped')

# Fix main() call
if main_call is not None:
    # Recalculate index after insertion
    offset = len(new_block) - (rt_end - rt_start + 1)
    main_call += offset
    lines[main_call] = lines[main_call].replace('        main()\n', '        main(skip_rt=_args.skip_rt)\n')
    print('Fix 4 done: main() call updated')
else:
    print('Fix 4 FAILED: main() call not found')

with open('pipeline/computational_time_analysis.py', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(lines)

print('All done')