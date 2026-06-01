import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Corrigir qualquer status errado
cur.execute("UPDATE protocolos_redesim SET status = 'Em an\u00e1lise' WHERE numero_protocolo = %s AND status NOT IN ('Em an\u00e1lise','Aprovada','Conclu\u00edda','Indeferida','Cancelada','Inativa')", ("SPM2630308582",))
print(f"Rows fixadas: {cur.rowcount}")

# Mostrar resultado
cur.execute("SELECT p.id, p.numero_protocolo, p.status, e.razao_social FROM protocolos_redesim p JOIN empresas e ON e.id=p.empresa_id WHERE p.numero_protocolo='SPM2630308582'")
for r in cur.fetchall(): print(f"  {r}")

conn.commit()
cur.close(); conn.close()
print("Done.")
