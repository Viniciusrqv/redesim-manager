import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Corrigir status sem acento se necessario
cur.execute("UPDATE protocolos_redesim SET status = 'Em ánalise' WHERE numero_protocolo = %s AND status = 'Em analise'", ("SPM2630308582",))
print(f"Status corrigido: {cur.rowcount} linha(s)")

# Verificar resultado final
cur.execute("""
    SELECT p.id, p.numero_protocolo, p.tipo, p.status, p.data_solicitacao, e.razao_social
    FROM protocolos_redesim p JOIN empresas e ON e.id = p.empresa_id
    WHERE p.numero_protocolo = 'SPM2630308582'
""")
for r in cur.fetchall():
    print(f"OK: id={r[0]} | {r[1]} | {r[2]} | status={r[3]} | {r[4]} | {r[5]}")

conn.commit()
cur.close(); conn.close()
print("Done.")
