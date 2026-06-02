import os, psycopg2, json, urllib.request
from collections import Counter

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("SELECT jwt FROM usuarios_gestta_jwt WHERE email = %s AND ativo = 1", ("legal2@csm.com.br",))
row = cur.fetchone()
cur.close(); conn.close()

jwt = row[0] if row else None
if not jwt:
    print("JWT nao encontrado")
    exit()

print("JWT encontrado, buscando tarefas...")

payload = json.dumps({
    "company_user": "679a775ef183530038cae49c",
    "status": ["OPEN", "IMPEDIMENT"],
    "limit": 300
}).encode()

req = urllib.request.Request(
    "https://api.gestta.com.br/core/customer/task/search",
    data=payload,
    headers={"Authorization": jwt, "Content-Type": "application/json", "Accept": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=20) as resp:
    data = json.loads(resp.read())

docs = data.get("docs", [])
total = data.get("total", len(docs))
atrasadas = sum(1 for t in docs if t.get("overdue"))
no_prazo = len(docs) - atrasadas
impediment = sum(1 for t in docs if t.get("status") == "IMPEDIMENT")

print(f"=== TAREFAS ABERTAS - VINICIUS RAFAEL ===")
print(f"Total: {total}")
print(f"Atrasadas: {atrasadas}")
print(f"No prazo: {no_prazo}")
print(f"Com impedimento: {impediment}")

tipos = Counter()
for t in docs:
    nome = (t.get("name") or "").lower()
    if "licen" in nome or "alvara" in nome or "alvará" in nome: tipos["Licenca/Alvara"] += 1
    elif "abertura" in nome: tipos["Abertura empresa"] += 1
    elif "altera" in nome: tipos["Alteracao contratual"] += 1
    elif "devolu" in nome: tipos["Devolucao cliente"] += 1
    elif "irpf" in nome or "imposto" in nome or "carne" in nome: tipos["IRPF/Fiscal"] += 1
    elif "bombeiro" in nome or "avcb" in nome: tipos["Bombeiros"] += 1
    elif "sanit" in nome or "visa" in nome: tipos["Vigilancia Sanitaria"] += 1
    elif "exclusao" in nome or "exclusão" in nome: tipos["Exclusao contabilista"] += 1
    else: tipos["Outros"] += 1

print("\nPor tipo:")
for k, v in tipos.most_common():
    print(f"  {k}: {v}")
print("\nConcluido.")
