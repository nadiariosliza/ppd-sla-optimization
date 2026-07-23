with open('pipeline/computational_time_analysis.py', 'r', encoding='utf-8') as f:
    content = f.read().replace('\r\n', '\n')

old = 'def main() -> None:'
new = 'def main(skip_rt: bool = False) -> None:'

if old in content:
    content = content.replace(old, new)
    print('Done')
else:
    print('FAILED - already fixed or not found')

with open('pipeline/computational_time_analysis.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)