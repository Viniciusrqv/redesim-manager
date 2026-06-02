import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# 1. Corrigir PLENITUDE — voltar para Em analise
cur.execute("UPDATE protocolos_redesim SET status = 'Em analise' WHERE numero_protocolo = %s AND status = 'Aprovada'", ("SPM2630308582",))
print(f"PLENITUDE corrigida: {cur.rowcount} linha(s)")

# 2. Buscar empresa_id da ASN BRASIL pelo protocolo
cur.execute("SELECT p.empresa_id, p.id FROM protocolos_redesim p WHERE p.numero_protocolo = %s", ("SPM2630283391",))
row = cur.fetchone()
if row:
    empresa_id, via_id = row
    print(f"ASN BRASIL: empresa_id={empresa_id} via_id={via_id}")
    
    # 3. Criar registro de Licenciamento ja concluido
    cur.execute("""INSERT INTO protocolos_redesim (empresa_id, numero_protocolo, tipo, status, observacoes, data_solicitacao)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (empresa_id, "SPM2630283391", "Licenciamento", "Concluida",
                 "CLI emitido. Licenca enviada ao cliente. Concluido manualmente.\n_(mensagem gerada pelo Claude)_",
                 "2026-05-19"))
    lic_id = cur.fetchone()[0]
    print(f"Licenciamento ASN criado: id={lic_id}")
    
    # 4. Marcar viabilidade ASN como Aprovada (manter) - ja esta assim
    print(f"Viabilidade ASN permanece Aprovada")
else:
    print("ASN BRASIL protocolo nao encontrado!")

conn.commit()
cur.close(); conn.close()
print("Concluido.")
