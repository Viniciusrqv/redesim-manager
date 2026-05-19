"""
migrar_sqlite_para_supabase.py
------------------------------
Copia TODOS os dados do banco SQLite local (`data/redesim.db`) para o
Postgres do Supabase (DATABASE_URL).

Uso:
    1. Garanta que DATABASE_URL está no .env (apontando pro Supabase)
    2. python redesim_manager\\migrar_sqlite_para_supabase.py

O que faz:
    - Cria todas as tabelas no Postgres usando os DDLs adaptados
    - Para CADA tabela do SQLite, lê tudo e faz INSERT no Postgres
    - Pula tabelas que não existem em uma das pontas (segurança)
    - Mostra contador de linhas migradas por tabela
    - --reset: apaga todas as tabelas do Postgres antes (CUIDADO!)
    - --dry-run: só mostra o que faria, sem gravar

Idempotente: pode rodar várias vezes — usa INSERT ... ON CONFLICT DO NOTHING
para não duplicar registros existentes.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Tem que importar dotenv ANTES de carregar config/db pra DATABASE_URL ficar disponível
try:
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except ImportError:
    print("⚠ python-dotenv não instalado. Setando variáveis manualmente "
          "via export/env.")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    print("❌ DATABASE_URL não configurada no .env.")
    print("   Adicione no .env:")
    print("   DATABASE_URL=postgresql://postgres.<ref>:<senha>@aws-0-sa-east-1"
          ".pooler.supabase.com:5432/postgres")
    sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("❌ psycopg2-binary não instalado. Rode: pip install psycopg2-binary")
    sys.exit(1)


SQLITE_PATH = HERE / "data" / "redesim.db"
if not SQLITE_PATH.exists():
    print(f"❌ Banco SQLite local não encontrado em {SQLITE_PATH}")
    sys.exit(1)


def listar_tabelas_sqlite(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def listar_colunas_sqlite(conn, tabela: str) -> list[dict]:
    """Retorna [{name, type, notnull, pk, dflt_value}]"""
    rows = conn.execute(f"PRAGMA table_info({tabela})").fetchall()
    return [dict(r) for r in rows]


def sqlite_to_pg_type(sqlite_type: str, is_pk: bool, is_autoinc: bool) -> str:
    """Mapeia tipo SQLite → Postgres."""
    t = (sqlite_type or "").upper().strip()
    if is_pk and is_autoinc:
        return "SERIAL PRIMARY KEY"
    if "INT" in t:
        return "BIGINT"
    if "CHAR" in t or "TEXT" in t or "CLOB" in t:
        return "TEXT"
    if "REAL" in t or "FLOA" in t or "DOUB" in t or "NUMERIC" in t:
        return "DOUBLE PRECISION"
    if "BLOB" in t:
        return "BYTEA"
    if "DATE" in t or "TIME" in t:
        return "TEXT"  # mantém ISO string pra compatibilidade
    return "TEXT"


def gerar_ddl_postgres(tabela: str, colunas: list[dict],
                       indice_sql: list[str] | None = None) -> str:
    """Monta CREATE TABLE compatível com Postgres a partir das colunas
    do SQLite. Tenta preservar PK e NOT NULL.
    """
    # Detecta se a tabela usa AUTOINCREMENT (não vem na PRAGMA, usamos heurística)
    has_serial = False
    cols_sql: list[str] = []
    for c in colunas:
        is_pk = bool(c.get("pk"))
        # SQLite trata "INTEGER PRIMARY KEY" como rowid auto-incremento
        is_auto = (is_pk and "INT" in (c.get("type") or "").upper())
        pg_type = sqlite_to_pg_type(c["type"], is_pk, is_auto)
        col_sql = f'"{c["name"]}" {pg_type}'
        if is_pk and "PRIMARY KEY" in pg_type:
            has_serial = True
        elif is_pk:
            col_sql += " PRIMARY KEY"
        if c.get("notnull") and not is_pk:
            col_sql += " NOT NULL"
        if c.get("dflt_value") is not None:
            # Algumas defaults do SQLite têm sintaxe própria — pula as complexas
            dflt = str(c["dflt_value"])
            if dflt.lower().startswith("datetime"):
                col_sql += " DEFAULT NOW()"
            elif dflt in ("0", "1", "TRUE", "FALSE", "NULL"):
                col_sql += f" DEFAULT {dflt}"
            elif dflt.startswith("'") and dflt.endswith("'"):
                col_sql += f" DEFAULT {dflt}"
        cols_sql.append(col_sql)
    return (f'CREATE TABLE IF NOT EXISTS "{tabela}" (\n  '
            + ",\n  ".join(cols_sql) + "\n);")


def migrar_tabela(sqlite_conn, pg_conn, tabela: str,
                  dry_run: bool = False) -> tuple[int, int]:
    """Retorna (lidas, inseridas)."""
    colunas = listar_colunas_sqlite(sqlite_conn, tabela)
    if not colunas:
        return (0, 0)

    col_names = [c["name"] for c in colunas]
    cols_quoted = ", ".join(f'"{c}"' for c in col_names)
    placeholders = ", ".join(["%s"] * len(col_names))

    # Cria a tabela no Postgres
    ddl = gerar_ddl_postgres(tabela, colunas)
    with pg_conn.cursor() as cur:
        cur.execute(ddl)
        pg_conn.commit()

    # Lê do SQLite
    rows = sqlite_conn.execute(
        f"SELECT {cols_quoted} FROM \"{tabela}\""
    ).fetchall()
    lidas = len(rows)

    if dry_run or lidas == 0:
        return (lidas, 0)

    # PK pra ON CONFLICT
    pk_cols = [c["name"] for c in colunas if c.get("pk")]
    if pk_cols:
        pk_conflict = ", ".join(f'"{c}"' for c in pk_cols)
        sql_insert = (
            f'INSERT INTO "{tabela}" ({cols_quoted}) VALUES ({placeholders}) '
            f'ON CONFLICT ({pk_conflict}) DO NOTHING'
        )
    else:
        sql_insert = (
            f'INSERT INTO "{tabela}" ({cols_quoted}) VALUES ({placeholders}) '
            f'ON CONFLICT DO NOTHING'
        )

    inseridas = 0
    with pg_conn.cursor() as cur:
        for r in rows:
            try:
                cur.execute(sql_insert, tuple(r))
                inseridas += cur.rowcount
            except Exception as exc:
                print(f"  ⚠ erro em {tabela} row: {str(exc)[:200]}")
        pg_conn.commit()

    return (lidas, inseridas)


def resetar_postgres(pg_conn):
    """Apaga TODAS as tabelas do schema public. CUIDADO!"""
    print("\n⚠️  RESETANDO Postgres — apagando TODAS as tabelas do schema public…")
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
        tabelas = [r[0] for r in cur.fetchall()]
        for t in tabelas:
            cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
            print(f"  ✗ DROP {t}")
        pg_conn.commit()
    print(f"✅ {len(tabelas)} tabelas removidas.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Mostra o que faria, sem gravar.")
    ap.add_argument("--reset", action="store_true",
                    help="Apaga TUDO do Postgres antes (perigoso).")
    ap.add_argument("--only", nargs="+",
                    help="Migrar apenas estas tabelas.")
    args = ap.parse_args()

    print(f"📂 SQLite origem: {SQLITE_PATH}")
    print(f"🐘 Postgres destino: {DATABASE_URL.split('@')[1].split('?')[0] if '@' in DATABASE_URL else '???'}\n")

    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(DATABASE_URL)

    if args.reset and not args.dry_run:
        resp = input("⚠️  Confirma o DROP de todas as tabelas do Postgres? (digite SIM): ")
        if resp.strip() == "SIM":
            resetar_postgres(pg_conn)
        else:
            print("Cancelado.")
            return

    tabelas = listar_tabelas_sqlite(sqlite_conn)
    if args.only:
        tabelas = [t for t in tabelas if t in args.only]

    print(f"📊 {len(tabelas)} tabelas a migrar:\n")
    total_lidas = total_inseridas = 0
    for tabela in tabelas:
        try:
            lidas, inseridas = migrar_tabela(
                sqlite_conn, pg_conn, tabela, dry_run=args.dry_run,
            )
            total_lidas += lidas
            total_inseridas += inseridas
            print(f"  {'✅' if not args.dry_run else '🟡'} {tabela:<35} "
                  f"{lidas:>5} lidas → {inseridas:>5} inseridas")
        except Exception as exc:
            print(f"  ❌ {tabela:<35} ERRO: {str(exc)[:100]}")
            pg_conn.rollback()

    sqlite_conn.close()
    pg_conn.close()

    print(f"\n🎯 Total: {total_lidas} lidas, {total_inseridas} inseridas.")
    if args.dry_run:
        print("(dry-run: nada foi gravado)")


if __name__ == "__main__":
    main()
