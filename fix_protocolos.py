import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name LIKE '%norm%' OR table_name LIKE '%atuali%')")
tabelas = [r[0] for r in cur.fetchall()]
print('Tabelas:', tabelas)
for t in tabelas:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print(f'  {t}: {cur.fetchone()[0]}')
cur.close(); conn.close()
print('Concluido.')
