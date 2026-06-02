import os, psycopg2, json, urllib.request, csv, io

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# 1. Buscar JWT do Vinicius Rafael
cur.execute("SELECT jwt_token FROM usuarios_gestta_jwt WHERE email = %s", ("legal2@csm.com.br",))
row = cur.fetchone()
jwt = row[0] if row else None
print(f"JWT encontrado: {'SIM' if jwt else 'NAO'}")

tarefas = []

if jwt:
    # 2. Buscar tarefas via GESTTA API
    payload = json.dumps({
        "company_user": "679a775ef183530038cae49c",
        "status": ["OPEN", "IMPEDIMENT"],
        "date_type": "DUE_DATE",
        "overdue": True,
        "limit": 300
    }).encode()
    req = urllib.request.Request(
        "https://api.gestta.com.br/core/customer/task/search",
        data=payload,
        headers={"Authorization": jwt, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        docs = data.get("docs", [])
        print(f"Tarefas encontradas via API: {len(docs)} (total: {data.get('total','?')})")
        for t in docs:
            tarefas.append({
                "codigo": t.get("number") or t.get("code") or "",
                "cliente": (t.get("customer") or {}).get("name","") or t.get("customerName",""),
                "tarefa": t.get("name",""),
                "status": t.get("status",""),
                "vencimento": str(t.get("dueDate") or t.get("due_date") or ""),
                "atrasada": "SIM" if t.get("overdue") else "nao",
                "id": t.get("_id","")
            })
    except Exception as e:
        print(f"Erro API GESTTA: {e}")

# 3. Fallback: tarefas do banco local
if not tarefas:
    print("Usando tarefas do banco local...")
    cur.execute("""SELECT gestta_id, tarefa_nome, cliente_nome, status_gestta, due_date, atrasada
                   FROM tarefas_gestta
                   WHERE status_gestta IN ('OPEN','IMPEDIMENT')
                   AND atrasada = '1'
                   ORDER BY due_date ASC NULLS LAST
                   LIMIT 300""")
    for r in cur.fetchall():
        tarefas.append({
            "codigo": "", "cliente": r[2], "tarefa": r[1],
            "status": r[3], "vencimento": str(r[4] or ""), "atrasada": "SIM" if r[5]=="1" else "nao",
            "id": r[0]
        })
    print(f"Tarefas do banco: {len(tarefas)}")

# 4. Salvar como JSON para recuperar
with open("/tmp/tarefas_abertas.json", "w", encoding="utf-8") as f:
    json.dump(tarefas, f, ensure_ascii=False, indent=2)
print(f"Total final: {len(tarefas)} tarefas salvas em /tmp/tarefas_abertas.json")

# 5. Salvar em artefato do GitHub Actions
print("\n=== TAREFAS ABERTAS VINICIUS RAFAEL ===")
for t in tarefas[:50]:
    print(f"  [{t['codigo']}] {t['cliente'][:40]} | {t['tarefa'][:50]} | Venc: {t['vencimento'][:10]} | {t['atrasada']}")

cur.close(); conn.close()
print("\nConcluido.")
