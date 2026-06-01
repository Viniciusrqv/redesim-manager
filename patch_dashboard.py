import os, base64, json, urllib.request

TOKEN = os.environ['GITHUB_TOKEN']
REPO = 'Viniciusrqv/redesim-manager'
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json', 'User-Agent': 'python'}

def gh(method, path, body=None):
    url = f'https://api.github.com/repos/{REPO}/{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read()), r.status

# Ler e aplicar patch
with open('app.py', encoding='utf-8') as f: content = f.read()
with open('new_bloco.py', encoding='utf-8') as f: new_bloco = f.read()

s = content.find('def _bloco_protocolos_redesim_dashboard():')
e = content.find('\ndef _bloco_documentos_dashboard():')
assert s != -1 and e != -1, f's={s} e={e}'
content = content[:s] + new_bloco + '\n' + content[e+1:]
print(f'Funcao substituida {s}->{e}')

old = '    # === Processos REDESIM (sistema antigo + filtros existentes) ==='
s2 = content.find(old)
if s2 != -1:
    end_sec = '\n# ---------------------------------------------------------\n# P'
    e2 = content.find(end_sec, s2)
    if e2 != -1:
        content = content[:s2] + content[e2:]
        print(f'Secao removida {s2}->{e2}')

import ast; ast.parse(content); print('Sintaxe OK')

# Atualizar via API (nao via git)
b64 = base64.b64encode(content.encode('utf-8')).decode()
current, _ = gh('GET', 'contents/app.py')
result, status = gh('PUT', 'contents/app.py', {
    'message': 'feat: pipeline Viabilidade->Licenciamento + remove processos antigos',
    'content': b64,
    'sha': current['sha']
})
print(f'API update: {status} | commit {result.get("commit",{}).get("sha","?")[:8]}')
