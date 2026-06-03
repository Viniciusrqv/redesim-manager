import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Concluir Licenciamento
cur.execute("UPDATE protocolos_redesim SET status='Concluida', observacoes='CLI emitido 03/06/2026. Cobranca R$250 lancada no DOMINIO. Tarefa concluida no GESTTA.' WHERE numero_protocolo=%s AND tipo='Licenciamento'", ("SPM2630312354",))
print(f"Licenciamento concluido: {cur.rowcount}")

# Inativar Viabilidade antiga
cur.execute("UPDATE protocolos_redesim SET status='Inativa' WHERE numero_protocolo=%s AND tipo='Viabilidade' AND status!='Inativa'", ("SPM2630312354",))
print(f"Viabilidade inativada: {cur.rowcount}")

# Cobranca DOMINIO
cur.execute("SELECT id FROM empresas WHERE cnpj=%s", ("45407551000102",))
emp = cur.fetchone()
if emp:
    cur.execute("SELECT id,status FROM cobrancas_dominio WHERE empresa_id=%s AND tipo_servico='LICENCA_REDESIM' ORDER BY id DESC LIMIT 1", (emp[0],))
    cob = cur.fetchone()
    if cob:
        cur.execute("UPDATE cobrancas_dominio SET status='LANCADA',valor_lancado=250.00 WHERE id=%s", (cob[0],))
        print(f"Cobranca {cob[0]} -> LANCADA")
    else:
        cur.execute("INSERT INTO cobrancas_dominio (empresa_id,tipo_servico,valor_sugerido,valor_lancado,status,observacoes) VALUES (%s,'LICENCA_REDESIM',250,250,'LANCADA','CLI PLENITUDE 03/06/2026')", (emp[0],))
        print("Cobranca criada LANCADA")

conn.commit(); cur.close(); conn.close()
print("Concluido.")
