import os, psycopg2, json, urllib.request

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("SELECT jwt FROM usuarios_gestta_jwt WHERE ativo = 1 LIMIT 1")
jwt = cur.fetchone()[0]

# Buscar TODAS as tarefas (abertas + concluidas recentes)
print("Buscando todas as tarefas do GESTTA...")
payload = json.dumps({
    "company_user": "679a775ef183530038cae49c",
    "status": ["OPEN", "IMPEDIMENT", "DONE"],
    "limit": 500
}).encode()
req = urllib.request.Request("https://api.gestta.com.br/core/customer/task/search",
    data=payload, headers={"Authorization":jwt,"Content-Type":"application/json","Accept":"application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())

docs = data.get("docs", [])
total_api = data.get("total", len(docs))
print(f"API retornou: {len(docs)} tarefas (total: {total_api})")

novas = 0
atualizadas = 0
baixadas = 0

for t in docs:
    gid = t.get("_id")
    status = t.get("status", "OPEN")
    nome = (t.get("name") or "")[:120]
    cliente = ((t.get("customer") or {}).get("name") or t.get("customerName") or "")[:120]
    due = str(t.get("dueDate") or t.get("due_date") or "")[:20]
    atrasada = "1" if t.get("overdue") else "0"
    
    if not gid: continue
    
    cur.execute("SELECT id, status_gestta FROM tarefas_gestta WHERE gestta_id = %s", (gid,))
    existe = cur.fetchone()
    
    if existe:
        if existe[1] != status:
            cur.execute("UPDATE tarefas_gestta SET status_gestta=%s, atrasada=%s WHERE gestta_id=%s",
                       (status, atrasada, gid))
            atualizadas += 1
            if status == "DONE": baixadas += 1
    else:
        cliente_norm = cliente.upper().strip()
        cur.execute("""INSERT INTO tarefas_gestta 
                      (gestta_id, tarefa_nome, cliente_nome, cliente_norm, status_gestta, atrasada, due_date)
                      VALUES (%s,%s,%s,%s,%s,%s,%s)
                      ON CONFLICT (gestta_id) DO NOTHING""",
                   (gid, nome, cliente, cliente_norm, status, atrasada, due or None))
        novas += 1

conn.commit()
print(f"Novas tarefas inseridas: {novas}")
print(f"Tarefas atualizadas: {atualizadas}")
print(f"Baixas automaticas (DONE): {baixadas}")

cur.execute("SELECT COUNT(*) FROM tarefas_gestta WHERE status_gestta IN ('OPEN','IMPEDIMENT')")
abertas_agora = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM tarefas_gestta WHERE status_gestta = 'DONE'")
done_agora = cur.fetchone()[0]
print(f"Estado atual banco: {abertas_agora} abertas | {done_agora} concluidas")

cur.close(); conn.close()
print("Sync concluido.")
