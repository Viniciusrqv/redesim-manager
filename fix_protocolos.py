import os, psycopg2, json, urllib.request
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Ver colunas da tabela de JWT
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'usuarios_gestta_jwt'")
cols = [r[0] for r in cur.fetchall()]
print("Colunas usuarios_gestta_jwt:", cols)

# Ver dados da tabela
cur.execute("SELECT * FROM usuarios_gestta_jwt LIMIT 3")
rows = cur.fetchall()
print(f"Linhas: {len(rows)}")
for r in rows:
    print([str(v)[:30] for v in r])

cur.close(); conn.close()
