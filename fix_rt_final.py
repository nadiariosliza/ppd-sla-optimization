with open('pipeline/computational_time_analysis.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the _hdr TABLE 1 line and the PA section start
hdr_idx = None
pa_idx  = None

for i, line in enumerate(lines):
    if '_hdr("TABLE 1' in line and 'Real-Time' in line:
        hdr_idx = i
    if '# ── Plan-Ahead' in line and hdr_idx is not None:
        pa_idx = i
        break

print(f'_hdr TABLE 1 at line {hdr_idx + 1}')
print(f'PA section at line {pa_idx + 1}')

if hdr_idx is None or pa_idx is None:
    print('ERROR: could not find section boundaries')
    exit(1)

# Add 4 spaces of indentation to every non-empty line from hdr_idx to pa_idx
new_lines = lines[:hdr_idx]
for i in range(hdr_idx, pa_idx):
    line = lines[i]
    if line.strip() == '':
        new_lines.append(line)
    else:
        new_lines.append('    ' + line)
new_lines.extend(lines[pa_idx:])

with open('pipeline/computational_time_analysis.py', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(new_lines)

print(f'Indented lines {hdr_idx + 1} to {pa_idx} — done')