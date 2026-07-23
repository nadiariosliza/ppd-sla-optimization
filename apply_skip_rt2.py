with open('pipeline/computational_time_analysis.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with _hdr("TABLE 1 — Real-Time MILP
rt_hdr_idx = None
pa_hdr_idx = None

for i, line in enumerate(lines):
    if '_hdr("TABLE 1' in line and 'Real-Time' in line:
        rt_hdr_idx = i
    if '# ── Plan-Ahead' in line and 'pa_all_cells' in lines[i+2] if i+2 < len(lines) else False:
        pa_hdr_idx = i

if rt_hdr_idx is None:
    print('ERROR: could not find RT header line')
    exit(1)

# Find the PA section start — look for the comment line before pa_all_cells
for i, line in enumerate(lines):
    if '# ── Plan-Ahead' in line and i > rt_hdr_idx:
        pa_hdr_idx = i
        break

if pa_hdr_idx is None:
    print('ERROR: could not find PA section')
    exit(1)

print(f'RT header at line {rt_hdr_idx + 1}')
print(f'PA section at line {pa_hdr_idx + 1}')

# Find the if not skip_rt: line we added (should be just before rt_hdr_idx)
skip_rt_idx = None
for i in range(rt_hdr_idx - 5, rt_hdr_idx + 1):
    if 'if not skip_rt:' in lines[i]:
        skip_rt_idx = i
        break

if skip_rt_idx is None:
    print('ERROR: could not find if not skip_rt: line')
    exit(1)

print(f'if not skip_rt: at line {skip_rt_idx + 1}')

# Indent all lines from skip_rt_idx+1 up to pa_hdr_idx with 4 extra spaces
new_lines = lines[:skip_rt_idx + 1]
for i in range(skip_rt_idx + 1, pa_hdr_idx):
    line = lines[i]
    if line.strip() == '':
        new_lines.append(line)
    else:
        new_lines.append('    ' + line)
new_lines.extend(lines[pa_hdr_idx:])

with open('pipeline/computational_time_analysis.py', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(new_lines)

print(f'Indented lines {skip_rt_idx + 2} to {pa_hdr_idx} — RT section now fully wrapped')
print('Done')