import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM tarefas_gestta WHERE status_gestta IN ('OPEN','IMPEDIMENT')")
abertas = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM tarefas_gestta")
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM tarefas_gestta WHERE status_gestta = 'DONE'")
concluidas = cur.fetchone()[0]

cur.execute("SELECT MAX(atualizado_em) FROM tarefas_gestta")
ultima = cur.fetchone()[0]

print(f"=== TAREFAS NO BANCO LOCAL ===")
print(f"Total no banco: {total}")
print(f"Abertas (OPEN+IMPEDIMENT): {abertas}")
print(f"Concluidas (DONE): {concluidas}")
print(f"Ultima atualizacao: {ultima}")

cur.close(); conn.close()
print("Concluido.")
