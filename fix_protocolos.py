import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Ver status das normas
cur.execute("SELECT base, titulo, versao, ultima_atualizacao, registros FROM normas_atualizacao ORDER BY ultima_atualizacao DESC NULLS LAST")
rows = cur.fetchall()
print("=== STATUS NORMAS ===")
for r in rows:
    data = str(r[3])[:10] if r[3] else "NUNCA"
    print(f"  {r[0]:15} | {r[1][:30]:30} | v:{str(r[2] or '-')[:20]} | {data} | {r[4] or 0} reg")

# Ver dados reais nas tabelas principais
for t in ['cnae_risco','vigilancia_sanitaria','bombeiros_cnae','cnae_concla']:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {cur.fetchone()[0]} registros")
    except: print(f"  {t}: nao existe")

cur.close(); conn.close()
print("Concluido.")
