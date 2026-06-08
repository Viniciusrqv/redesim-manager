import subprocess

AFTER_LINE = 'Pendências Gerais'
NEW_LINE = '    "💰 Cobranças DOMÍNIO",\n'
TARGET_ITEM = 'Cobranças DOMÍNIO'

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find PAGINAS_LIST block boundaries
list_start = None
list_end = None
for i, line in enumerate(lines):
    if 'PAGINAS_LIST = [' in line:
        list_start = i
    if list_start is not None and list_end is None and i > list_start and line.strip() == ']':
        list_end = i
        break

if list_start is None or list_end is None:
    print(f"ERROR: PAGINAS_LIST block not found (start={list_start}, end={list_end})")
    exit(1)

print(f"PAGINAS_LIST found at lines {list_start}-{list_end}")

# Check if already in PAGINAS_LIST specifically
paginas_list_block = lines[list_start:list_end+1]
if any(TARGET_ITEM in line for line in paginas_list_block):
    print("Already in PAGINAS_LIST — nothing to do")
    exit(0)

# Insert after AFTER_LINE within the block
new_lines = []
inserted = False
for i, line in enumerate(lines):
    new_lines.append(line)
    if list_start <= i <= list_end and AFTER_LINE in line and not inserted:
        new_lines.append(NEW_LINE)
        inserted = True

if not inserted:
    print(f"ERROR: '{AFTER_LINE}' not found in PAGINAS_LIST block")
    for l in paginas_list_block:
        print(repr(l))
    exit(1)

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Inserted. Now committing...")

subprocess.run(['git', 'config', 'user.email', 'contabil@csm.com.br'], check=True)
subprocess.run(['git', 'config', 'user.name', 'CSM Bot'], check=True)
subprocess.run(['git', 'add', 'app.py'], check=True)
subprocess.run(['git', 'commit', '-m', 'fix: adicionar Cobrancas DOMINIO no PAGINAS_LIST'], check=True)
result = subprocess.run(['git', 'push'], capture_output=True, text=True)
print("Push stdout:", result.stdout)
print("Push stderr:", result.stderr)
if result.returncode != 0:
    result2 = subprocess.run(['git', 'push', 'origin', 'HEAD:main'], capture_output=True, text=True)
    if result2.returncode != 0:
        print("PUSH FAILED:", result2.stderr)
        exit(1)
print("Done!")
