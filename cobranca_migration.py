import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Migration - adicionar colunas de cobranca
print('Adicionando colunas...')
cur.execute('ALTER TABLE protocolos_redesim ADD COLUMN IF NOT EXISTS cobranca_lancada BOOLEAN DEFAULT FALSE')
cur.execute('ALTER TABLE protocolos_redesim ADD COLUMN IF NOT EXISTS cobranca_valor DECIMAL(10,2)')
cur.execute('ALTER TABLE protocolos_redesim ADD COLUMN IF NOT EXISTS cobranca_data DATE')

# ASN BRASIL - SPM2630283391 Licenciamento - 08/06/2026 R$250
cur.execute("UPDATE protocolos_redesim SET cobranca_lancada=TRUE, cobranca_valor=250.00, cobranca_data='2026-06-08' WHERE numero_protocolo='SPM2630283391' AND tipo='Licenciamento'")
print('ASN:', cur.rowcount)

# PLENITUDE - SPM2630312354 Licenciamento - 03/06/2026 R$250
cur.execute("UPDATE protocolos_redesim SET cobranca_lancada=TRUE, cobranca_valor=250.00, cobranca_data='2026-06-03' WHERE numero_protocolo='SPM2630312354' AND tipo='Licenciamento'")
print('PLENITUDE:', cur.rowcount)

conn.commit()
cur.close()
conn.close()
print('OK!')
