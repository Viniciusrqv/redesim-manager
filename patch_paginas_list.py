import subprocess

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '    "\ud83d\udccc Pend\u00eancias Gerais",\n    "\ud83d\udd2c Consultor de CNAE",'
new_str = '    "\ud83d\udccc Pend\u00eancias Gerais",\n    "\ud83d\udcb0 Cobran\u00e7as DOM\u00cdNIO",\n    "\ud83d\udd2c Consultor de CNAE",'

updated = content.replace(old, new_str, 1)

if updated == content:
    print("ERROR: pattern not found!")
else:
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(updated)
    subprocess.run(['git', 'config', 'user.email', 'contabil@csm.com.br'], check=True)
    subprocess.run(['git', 'config', 'user.name', 'CSM Bot'], check=True)
    subprocess.run(['git', 'add', 'app.py'], check=True)
    subprocess.run(['git', 'commit', '-m', 'fix: adicionar Cobrancas DOMINIO no sidebar'], check=True)
    subprocess.run(['git', 'push'], check=True)
    print("Done! app.py updated.")
