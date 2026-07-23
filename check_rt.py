with open('pipeline/computational_time_analysis.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines[1015:1055], start=1016):
    print(f'{i}: {repr(line)}')