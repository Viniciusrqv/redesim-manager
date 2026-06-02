import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

CNPJ = "45407551000102"
NOVO_PROTO = "SPM2630312354"
OLD_PROTO = "SPM2630308582"

# 1. Buscar empresa
cur.execute("SELECT id FROM empresas WHERE cnpj = %s", (CNPJ,))
row = cur.fetchone()
if not row:
    print("Empresa nao encontrada!")
else:
    empresa_id = row[0]
    print(f"Empresa id={empresa_id}")

    # 2. Marcar protocolo antigo como Inativa
    cur.execute("UPDATE protocolos_redesim SET status = 'Inativa', observacoes = 'Substituido por novo protocolo apos reconsideracao: ' || %s WHERE numero_protocolo = %s AND status != 'Inativa'",
                (NOVO_PROTO, OLD_PROTO))
    print(f"Antigo inativado: {cur.rowcount} linha(s)")

    # 3. Criar novo protocolo de viabilidade
    cur.execute("SELECT id FROM protocolos_redesim WHERE numero_protocolo = %s", (NOVO_PROTO,))
    if cur.fetchone():
        print(f"Protocolo {NOVO_PROTO} ja existe")
    else:
        cur.execute("""INSERT INTO protocolos_redesim
                       (empresa_id, numero_protocolo, tipo, status, observacoes, data_solicitacao)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (empresa_id, NOVO_PROTO, "Viabilidade", "Em analise",
                     "Nova viabilidade apos reconsideracao aprovada pela Prefeitura de Cotia.", "2026-06-02"))
        new_id = cur.fetchone()[0]
        print(f"Novo protocolo criado: id={new_id}")

conn.commit()
cur.close(); conn.close()
print("Concluido.")
