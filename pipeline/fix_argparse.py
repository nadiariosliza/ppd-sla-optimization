with open('pipeline/computational_time_analysis.py', 'r', encoding='utf-8') as f:
    content = f.read().replace('\r\n', '\n')

# Add --skip-rt after the --graphs-only block
old = '    )\n    _args = _parser.parse_args()'
new = ('    )\n'
       '    _parser.add_argument(\n'
       '        "--skip-rt", action="store_true",\n'
       '        help="Skip Real-Time analysis, run Plan-Ahead only",\n'
       '    )\n'
       '    _args = _parser.parse_args()')

if old in content:
    content = content.replace(old, new)
    print('Fix 1 done: --skip-rt added')
else:
    print('Fix 1 FAILED')

# Update main() call
old2 = '        main()\n'
new2 = '        main(skip_rt=_args.skip_rt)\n'
if old2 in content:
    content = content.replace(old2, new2)
    print('Fix 2 done: main() call updated')
else:
    print('Fix 2 FAILED')

with open('pipeline/computational_time_analysis.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)
print('Done')