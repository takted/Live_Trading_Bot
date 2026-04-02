#!/usr/bin/env python3
"""Fix indentation issues in run_forex_live.py"""

with open('itrading/scripts/run_forex_live.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix all lines with incorrect indentation - replace extra spaces at beginning
fixed_lines = []
for i, line in enumerate(lines):
    # For problem lines (614-680), fix excessive leading spaces
    if i >= 613 and i <= 680:
        # If line starts with 5+ spaces, reduce by one indent level (4 spaces)
        if line.startswith('     ') and not line.lstrip().startswith('#'):  # At least 5 spaces
            stripped = line.lstrip()
            leading_spaces = len(line) - len(stripped)
            if leading_spaces >= 5:
                # Reduce to 1 less indent
                line = '    ' + ' ' * (leading_spaces - 8) + stripped
        fixed_lines.append(line)
    else:
        fixed_lines.append(line)

with open('itrading/scripts/run_forex_live.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print('Fixed indentation in run_forex_live.py')



