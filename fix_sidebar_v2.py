import subprocess

TARGET = '❗❗ CHECK: already done'
NEW_LINE = '    "💰 Cobranças DOMÍNIO",\n'
AFTER_LINE = 'Pendências Gerais'
SKIP_IF = 'Cobranças DOMÍNIO'

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Check if already present
if any(SKIP_IF in line for line in lines):
    print("Already done! Cobrancas DOMINIO already in app.py")
    exit(0)

# Find the target line and insert after it
new_lines = []
inserted = False
for line in lines:
    new_lines.append(line)
    if AFTER_LINE in line and not inserted:
        new_lines.append(NEW_LINE)
        inserted = True

if not inserted:
    print("ERROR: target line not found in app.py")
    print("Lines containing PAGINAS_LIST:")
    for i, l in enumerate(lines):
        if 'PAGINAS' in l:
            print(f"  {i}: {repr(l)}")
    exit(1)

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

subprocess.run(['git', 'config', 'user.email', 'contabil@csm.com.br'], check=True)
subprocess.run(['git', 'config', 'user.name', 'CSM Bot'], check=True)
subprocess.run(['git', 'add', 'app.py'], check=True)
subprocess.run(['git', 'commit', '-m', 'fix: adicionar Cobrancas DOMINIO no sidebar'], check=True)
result = subprocess.run(['git', 'push'], capture_output=True, text=True)
if result.returncode != 0:
    print("Push stderr:", result.stderr)
    print("Push stdout:", result.stdout)
    # Try with upstream
    result2 = subprocess.run(['git', 'push', 'origin', 'HEAD:main'], capture_output=True, text=True)
    if result2.returncode != 0:
        print("Push2 stderr:", result2.stderr)
        exit(1)
    print("Pushed via origin HEAD:main")
else:
    print("Done! app.py updated and pushed.")
