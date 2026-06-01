"""
Insere protocolo PLENITUDE no Supabase e vincula à tarefa GESTTA.
"""
import os
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL nao configurado")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

NUMERO_PROTOCOLO = "SPM2630308582"
CNPJ             = "45407551000102"
RAZAO_SOCIAL     = "PLENITUDE CONFECCOES DE ARTIGOS DO VESTUARIO LTDA"
GESTTA_TASK_ID   = "62471971a1ddd70007968f8e"
OBS              = "Viabilidade protocolada via REDESIM SP em 01/06/2026. Aguardando analise Prefeitura Cotia."

print("=== Inserindo protocolo PLENITUDE ===")

# 1. Buscar ou criar empresa
cur.execute("SELECT id FROM empresas WHERE cnpj = %s", (CNPJ,))
row = cur.fetchone()
if row:
    empresa_id = row[0]
    print(f"  Empresa encontrada: id={empresa_id}")
else:
    cur.execute("""
        INSERT INTO empresas (razao_social, cnpj, municipio, uf)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (RAZAO_SOCIAL, CNPJ, "Cotia", "SP"))
    empresa_id = cur.fetchone()[0]
    print(f"  Empresa criada: id={empresa_id}")

# 2. Inserir protocolo (sem ON CONFLICT, verifica antes)
cur.execute("SELECT id FROM protocolos_redesim WHERE numero_protocolo = %s", (NUMERO_PROTOCOLO,))
existing = cur.fetchone()
if existing:
    protocolo_id = existing[0]
    cur.execute("""
        UPDATE protocolos_redesim SET status = %s, observacoes = %s WHERE id = %s
    """, ("Em análise", OBS, protocolo_id))
    print(f"  Protocolo já existe, atualizado: id={protocolo_id}")
else:
    cur.execute("""
        INSERT INTO protocolos_redesim
            (empresa_id, numero_protocolo, tipo, status, observacoes, data_solicitacao)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    """, (empresa_id, NUMERO_PROTOCOLO, "Viabilidade", "Em análise", OBS, "2026-06-01"))
    protocolo_id = cur.fetchone()[0]
    print(f"  Protocolo inserido: id={protocolo_id}")

# 3. Vincular à tarefa GESTTA
cur.execute("""
    UPDATE tarefas_gestta SET protocolo_id = %s WHERE gestta_id = %s
""", (protocolo_id, GESTTA_TASK_ID))
print(f"  tarefas_gestta: {cur.rowcount} linha(s) vinculada(s)")

conn.commit()
cur.close()
conn.close()
print("Concluido.")
