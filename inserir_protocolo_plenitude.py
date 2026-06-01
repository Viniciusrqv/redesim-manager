import os, psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

print("=== EMPRESAS PLENITUDE ===")
cur.execute("SELECT id, razao_social, cnpj FROM empresas WHERE cnpj = %s OR razao_social ILIKE %s", ("45407551000102", "%PLENITUDE%"))
rows = cur.fetchall()
print(rows if rows else "  NENHUMA")

print("\n=== PROTOCOLO SPM2630308582 ===")
cur.execute("SELECT id, empresa_id, numero_protocolo, tipo, status FROM protocolos_redesim WHERE numero_protocolo = %s", ("SPM2630308582",))
rows = cur.fetchall()
print(rows if rows else "  NENHUM")

print("\n=== JOIN ===")
cur.execute("""
    SELECT p.id, p.numero_protocolo, p.status, e.razao_social
    FROM protocolos_redesim p JOIN empresas e ON e.id = p.empresa_id
    WHERE p.numero_protocolo = 'SPM2630308582'
""")
rows = cur.fetchall()
print(rows if rows else "  NENHUM (JOIN falhou)")

# Se não existe, inserir agora
if not rows:
    print("\n=== INSERINDO AGORA ===")
    cur.execute("SELECT id FROM empresas WHERE cnpj = %s", ("45407551000102",))
    emp = cur.fetchone()
    if not emp:
        cur.execute("INSERT INTO empresas (razao_social, cnpj, municipio, uf) VALUES (%s,%s,%s,%s) RETURNING id",
                    ("PLENITUDE CONFECCOES DE ARTIGOS DO VESTUARIO LTDA","45407551000102","Cotia","SP"))
        emp_id = cur.fetchone()[0]
        print(f"  Empresa criada: id={emp_id}")
    else:
        emp_id = emp[0]
        print(f"  Empresa encontrada: id={emp_id}")
    cur.execute("SELECT id FROM protocolos_redesim WHERE numero_protocolo = %s", ("SPM2630308582",))
    prot = cur.fetchone()
    if not prot:
        cur.execute("""INSERT INTO protocolos_redesim (empresa_id,numero_protocolo,tipo,status,observacoes,data_solicitacao)
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (emp_id,"SPM2630308582","Viabilidade","Em analise",
                     "Viabilidade REDESIM SP 01/06/2026. Aguardando Prefeitura Cotia.","2026-06-01"))
        prot_id = cur.fetchone()[0]
        print(f"  Protocolo inserido: id={prot_id}")
    conn.commit()
    print("  Commit OK")
cur.close(); conn.close()
print("Done.")
