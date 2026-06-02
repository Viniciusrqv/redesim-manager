import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# 1. Listar todos os licenciamentos da ASN para entender
cur.execute("SELECT id, status, criado_em FROM protocolos_redesim WHERE numero_protocolo = %s AND tipo = 'Licenciamento' ORDER BY id", ("SPM2630283391",))
rows = cur.fetchall()
for r in rows:
    print(f"  Licenciamento id={r[0]} status={r[1]} criado={r[2]}")

# 2. Manter apenas o mais recente como Concluida, marcar outros como Inativa
if len(rows) > 1:
    # Manter o que esta Concluida, inativar os outros
    for r in rows:
        if r[1] != 'Concluida':
            cur.execute("UPDATE protocolos_redesim SET status = 'Inativa', observacoes = 'Duplicata removida - registro correto: Concluida' WHERE id = %s", (r[0],))
            print(f"  Inativado duplicado id={r[0]}")

# 3. Verificar status final da Viabilidade ASN (deve estar Aprovada)
cur.execute("SELECT id, status FROM protocolos_redesim WHERE numero_protocolo = %s AND tipo = 'Viabilidade'", ("SPM2630283391",))
v = cur.fetchone()
if v:
    print(f"Viabilidade ASN: id={v[0]} status={v[1]}")

conn.commit()
cur.close(); conn.close()
print("Concluido.")
