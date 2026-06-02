import os, psycopg2, json, urllib.request

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Buscar JWT
cur.execute("SELECT jwt_token FROM usuarios_gestta_jwt WHERE email = %s", ("legal2@csm.com.br",))
row = cur.fetchone()
jwt = row[0] if row else None

if not jwt:
    print("JWT nao encontrado no banco")
    cur.close(); conn.close()
    exit()

# Buscar tarefas via GESTTA API - sem filtro overdue para pegar todas abertas
payload = json.dumps({
    "company_user": "679a775ef183530038cae49c",
    "status": ["OPEN", "IMPEDIMENT"],
    "limit": 1
}).encode()

req = urllib.request.Request(
    "https://api.gestta.com.br/core/customer/task/search",
    data=payload,
    headers={"Authorization": jwt, "Content-Type": "application/json", "Accept": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    total = data.get("total", 0)
    docs_count = len(data.get("docs", []))
    print(f"Total tarefas abertas (OPEN+IMPEDIMENT): {total}")
    print(f"Docs retornados: {docs_count}")
    
    # Agora buscar com todos e contar por tipo/status
    payload2 = json.dumps({
        "company_user": "679a775ef183530038cae49c",
        "status": ["OPEN", "IMPEDIMENT"],
        "limit": 300,
        "date_type": "DUE_DATE"
    }).encode()
    req2 = urllib.request.Request(
        "https://api.gestta.com.br/core/customer/task/search",
        data=payload2,
        headers={"Authorization": jwt, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req2, timeout=20) as resp2:
        data2 = json.loads(resp2.read())
    
    docs = data2.get("docs", [])
    atrasadas = sum(1 for t in docs if t.get("overdue"))
    no_prazo  = sum(1 for t in docs if not t.get("overdue"))
    impediment = sum(1 for t in docs if t.get("status") == "IMPEDIMENT")
    
    print(f"\n=== RESUMO VINICIUS RAFAEL ===")
    print(f"Total abertas: {data2.get('total', len(docs))}")
    print(f"  Atrasadas:  {atrasadas}")
    print(f"  No prazo:   {no_prazo}")
    print(f"  Com impedimento: {impediment}")
    
    # Contar por tipo de tarefa
    from collections import Counter
    tipos = Counter()
    for t in docs:
        nome = t.get("name","").lower()
        if "licen" in nome: tipos["Licença/Alvará"] += 1
        elif "abertura" in nome: tipos["Abertura empresa"] += 1
        elif "alteração" in nome or "alteracao" in nome: tipos["Alteração"] += 1
        elif "devolução" in nome or "devolucao" in nome: tipos["Devolução"] += 1
        elif "irpf" in nome or "imposto" in nome: tipos["IRPF/Fiscal"] += 1
        elif "bombeiro" in nome or "avcb" in nome: tipos["Bombeiros"] += 1
        elif "visa" in nome or "sanitário" in nome: tipos["Vigilância Sanitária"] += 1
        else: tipos["Outros"] += 1
    
    print("\nPor tipo:")
    for k, v in tipos.most_common():
        print(f"  {k}: {v}")
        
except Exception as e:
    print(f"Erro: {e}")

cur.close(); conn.close()
print("Concluido.")
