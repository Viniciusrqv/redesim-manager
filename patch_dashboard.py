with open('app.py', encoding='utf-8') as f: content = f.read()
with open('new_bloco.py', encoding='utf-8') as f: new_bloco = f.read()
s = content.find('def _bloco_protocolos_redesim_dashboard():')
e = content.find('\ndef _bloco_documentos_dashboard():')
assert s != -1 and e != -1, f'Marcadores nao encontrados s={s} e={e}'
content = content[:s] + new_bloco + '\n' + content[e+1:]
print(f'Funcao substituida {s}->{e}')
old = '    # === Processos REDESIM (sistema antigo + filtros existentes) ==='
s2 = content.find(old)
if s2 != -1:
    end_marker = '\n# ---------------------------------------------------------'
    e2 = content.find(end_marker, s2)
    if e2 != -1: content = content[:s2] + content[e2:]; print(f'Secao removida {s2}->{e2}')
    else: print('Fim da secao nao encontrado')
else: print('Secao antiga ja removida')
import ast; ast.parse(content); print('Sintaxe OK')
open('app.py','w',encoding='utf-8').write(content); print('Salvo.')