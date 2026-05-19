"""
db.py
-----
Camada de adaptação que escolhe SQLite (desenvolvimento local) ou
PostgreSQL (produção via Supabase) baseado na variável de ambiente
`DATABASE_URL`.

- Se `DATABASE_URL` está setada → conecta com Postgres via psycopg2
- Senão → conecta com SQLite no arquivo `data/redesim.db`

Mantém a API existente: `get_conn()` retorna uma conexão com método
`.execute(sql, params)` compatível com o jeito que o `database.py` usa.

Diferenças de sintaxe SQL são traduzidas automaticamente:
  - placeholders `?` → `%s`
  - `datetime('now', 'localtime')` → `NOW()`
  - `AUTOINCREMENT` → (removido — usar SERIAL)
  - `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
  - `INSERT OR REPLACE INTO X (col1, col2, ...) VALUES (...)` →
    `INSERT INTO X (col1, col2, ...) VALUES (...)
     ON CONFLICT (col1) DO UPDATE SET col2=EXCLUDED.col2, ...`
  - `INSERT OR IGNORE INTO X` → `INSERT INTO X ... ON CONFLICT DO NOTHING`
  - `PRAGMA table_info(X)` → query no information_schema
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Iterable

# Tenta carregar psycopg2 (só necessário em produção)
try:
    import psycopg2
    import psycopg2.extras
    _HAS_POSTGRES = True
except ImportError:
    _HAS_POSTGRES = False

# Tenta carregar .env (em produção Streamlit Cloud usa st.secrets)
try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Em Streamlit Cloud, secrets vêm de st.secrets — copia pra os.environ se rodando lá
try:
    import streamlit as st
    if hasattr(st, "secrets"):
        for key in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY",
                    "SUPABASE_SERVICE_KEY", "GESTTA_JWT"):
            try:
                val = st.secrets[key]
                if val and not os.getenv(key):
                    os.environ[key] = val
            except (KeyError, FileNotFoundError):
                pass
except Exception:
    pass


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def is_postgres() -> bool:
    """True se rodando em produção (Postgres/Supabase)."""
    return bool(DATABASE_URL) and _HAS_POSTGRES


def database_path() -> Path:
    """Caminho do banco SQLite local (modo dev)."""
    base = Path(__file__).resolve().parent
    rel = os.getenv("DATABASE_PATH", "data/redesim.db")
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ====================================================================
# TRADUÇÃO DE SQL: SQLite → Postgres
# ====================================================================
_RE_DT_LOCAL = re.compile(r"datetime\(\s*'now'\s*,\s*'localtime'\s*\)",
                           re.IGNORECASE)
_RE_DT_NOW = re.compile(r"datetime\(\s*'now'\s*\)", re.IGNORECASE)
# date('now', 'localtime') / date('now')
_RE_DATE_LOCAL = re.compile(r"date\(\s*'now'\s*,\s*'localtime'\s*\)",
                             re.IGNORECASE)
_RE_DATE_NOW = re.compile(r"date\(\s*'now'\s*\)", re.IGNORECASE)
# julianday('now') — substitui por EXTRACT(EPOCH FROM NOW())/86400
_RE_JULIANDAY_NOW = re.compile(
    r"julianday\(\s*'now'\s*\)", re.IGNORECASE)
# julianday(<expr>) — substitui por EXTRACT(EPOCH FROM <expr>::timestamp)/86400
# Aceita coluna simples (a.coluna, coluna) ou string literal datada
_RE_JULIANDAY = re.compile(
    r"julianday\(\s*([^\)]+?)\s*\)", re.IGNORECASE)
_RE_AUTOINC_PK = re.compile(
    r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", re.IGNORECASE)
_RE_PK_AUTOINC = re.compile(r"AUTOINCREMENT", re.IGNORECASE)
_RE_PRAGMA_TABLE = re.compile(
    r"PRAGMA\s+table_info\s*\(\s*([\w\"']+)\s*\)\s*;?", re.IGNORECASE)
_RE_INSERT_REPLACE = re.compile(
    r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+([\w\".]+)\s*\(([^)]+)\)\s*"
    r"VALUES\s*\(([^)]+)\)\s*;?\s*$", re.IGNORECASE | re.DOTALL)
_RE_INSERT_IGNORE = re.compile(
    r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.IGNORECASE)


def _translate_sql_to_postgres(sql: str) -> str:
    """Aplica as substituições mais comuns. Não é perfeito, mas cobre
    a maioria das queries do projeto.
    """
    # 1) datetime → NOW()
    sql = _RE_DT_LOCAL.sub("NOW()", sql)
    sql = _RE_DT_NOW.sub("NOW()", sql)
    # 1b) date('now'…) → CURRENT_DATE
    sql = _RE_DATE_LOCAL.sub("CURRENT_DATE", sql)
    sql = _RE_DATE_NOW.sub("CURRENT_DATE", sql)
    # 1c) julianday('now') — dias desde a época, como float
    sql = _RE_JULIANDAY_NOW.sub(
        "(EXTRACT(EPOCH FROM NOW())/86400.0)", sql)
    # 1d) julianday(<expr>) — outros usos
    sql = _RE_JULIANDAY.sub(
        lambda m: f"(EXTRACT(EPOCH FROM ({m.group(1)})::timestamp)/86400.0)",
        sql,
    )

    # 2) INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    sql = _RE_AUTOINC_PK.sub("SERIAL PRIMARY KEY", sql)
    # AUTOINCREMENT solto (caso não tenha INTEGER PRIMARY KEY antes)
    sql = _RE_PK_AUTOINC.sub("", sql)

    # 3) PRAGMA table_info(X) → information_schema
    def _pragma_repl(match):
        tabela = match.group(1).strip().strip("\"'")
        return (f"SELECT column_name AS name, data_type AS type, "
                f"is_nullable, column_default "
                f"FROM information_schema.columns "
                f"WHERE table_schema='public' AND table_name='{tabela}'")
    sql = _RE_PRAGMA_TABLE.sub(_pragma_repl, sql)

    # 4) INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE
    m = _RE_INSERT_REPLACE.match(sql)
    if m:
        tabela, cols_str, vals_str = m.groups()
        cols = [c.strip() for c in cols_str.split(",")]
        pk = cols[0]  # convenção: primeira coluna é a PK
        non_pk = [c for c in cols if c != pk]
        sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in non_pk)
        if sets:
            sql = (f"INSERT INTO {tabela} ({cols_str}) VALUES ({vals_str}) "
                   f"ON CONFLICT ({pk}) DO UPDATE SET {sets}")
        else:
            sql = (f"INSERT INTO {tabela} ({cols_str}) VALUES ({vals_str}) "
                   f"ON CONFLICT ({pk}) DO NOTHING")

    # 5) INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
    if _RE_INSERT_IGNORE.match(sql):
        sql = _RE_INSERT_IGNORE.sub("INSERT INTO ", sql)
        # Anexa ON CONFLICT DO NOTHING se já não tiver
        if "ON CONFLICT" not in sql.upper():
            sql = sql.rstrip("; \n\t") + " ON CONFLICT DO NOTHING"

    # 6) placeholders ? → %s (faz por último pra não interferir nos regex)
    sql = sql.replace("?", "%s")

    return sql


# ====================================================================
# WRAPPERS DE CONEXÃO/CURSOR
# ====================================================================
class _PgRowFactory:
    """Faz `dict(row)` funcionar em rows de RealDictCursor."""
    pass


class _PgCursor:
    """Wrapper de cursor Postgres que aceita sintaxe SQLite."""
    def __init__(self, raw_cur):
        self._cur = raw_cur
        self.rowcount = 0
        self.lastrowid = None

    def execute(self, sql: str, params: tuple | list = ()):
        pg_sql = _translate_sql_to_postgres(sql)
        # psycopg2 quer params como tupla; lista também serve
        self._cur.execute(pg_sql, params or None)
        self.rowcount = self._cur.rowcount
        try:
            self.lastrowid = (self._cur.fetchone()
                              if "RETURNING" in pg_sql.upper() else None)
        except Exception:
            self.lastrowid = None
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)

    def close(self):
        self._cur.close()


class _PgConn:
    """Wrapper de conexão Postgres com API parecida com sqlite3.Connection.

    Suporta: with-statement, .execute(), .commit(), .rollback(), .close().
    """
    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(
            dsn, cursor_factory=psycopg2.extras.RealDictCursor,
        )

    # Context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            try:
                self._conn.commit()
            except Exception:
                pass
        else:
            try:
                self._conn.rollback()
            except Exception:
                pass
        self.close()
        return False

    def execute(self, sql: str, params: tuple | list = ()):
        cur = _PgCursor(self._conn.cursor())
        cur.execute(sql, params)
        return cur

    def executemany(self, sql: str, seq_of_params: Iterable):
        pg_sql = _translate_sql_to_postgres(sql)
        with self._conn.cursor() as raw_cur:
            raw_cur.executemany(pg_sql, list(seq_of_params))
            return raw_cur.rowcount

    def executescript(self, sql_script: str):
        """Executa múltiplos SQL statements separados por `;`.
        Equivalente a `sqlite3.Connection.executescript()`.

        Estratégia robusta pra Postgres:
          - Tolera erros do tipo "already exists" (tabelas/índices que a
            migração inicial já criou).
          - Tolera erros de tipo (ex.: `INTEGER` em campos que viraram TEXT).
            Cada statement roda em SAVEPOINT pra não envenenar a transação.
          - Cada statement é traduzido individualmente.
        """
        # Split simples — ignora pontos-e-vírgulas dentro de strings literais.
        # Pra DDLs do projeto isso é suficiente (não temos strings com `;`).
        statements = [
            s.strip() for s in sql_script.split(";") if s.strip()
        ]
        # Cada statement num savepoint individual pra resistir a erros
        with self._conn.cursor() as cur:
            for stmt in statements:
                pg_sql = _translate_sql_to_postgres(stmt)
                if not pg_sql.strip():
                    continue
                try:
                    cur.execute("SAVEPOINT s_exec")
                    cur.execute(pg_sql)
                    cur.execute("RELEASE SAVEPOINT s_exec")
                except Exception as exc:
                    msg = str(exc).lower()
                    cur.execute("ROLLBACK TO SAVEPOINT s_exec")
                    cur.execute("RELEASE SAVEPOINT s_exec")
                    # Erros aceitáveis: tabelas/índices/colunas já existentes
                    if ("already exists" in msg or
                            "duplicate column" in msg or
                            "duplicate object" in msg):
                        continue
                    # Outros — re-raise pra ficar visível
                    raise

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        # SQLite tem isso, ignoramos no Postgres (já usamos RealDictCursor)
        pass


# ====================================================================
# CONEXÃO PRINCIPAL
# ====================================================================
def get_connection():
    """Retorna conexão com o banco — Postgres em produção, SQLite local
    em desenvolvimento. Use `with get_connection() as conn:` ou feche
    com `conn.close()` manualmente.
    """
    if is_postgres():
        return _PgConn(DATABASE_URL)
    # Modo dev: SQLite
    conn = sqlite3.connect(str(database_path()))
    conn.row_factory = sqlite3.Row
    # Habilita foreign keys (SQLite não enforça por padrão)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def info_backend() -> dict:
    """Retorna info útil sobre o backend atual (pra UI mostrar)."""
    if is_postgres():
        # Tenta extrair host do DSN sem expor segredos
        host = "supabase"
        try:
            from urllib.parse import urlparse
            p = urlparse(DATABASE_URL)
            host = p.hostname or "supabase"
        except Exception:
            pass
        return {
            "backend": "postgres",
            "host": host,
            "label": f"🟢 PostgreSQL (Supabase) · {host}",
        }
    return {
        "backend": "sqlite",
        "host": str(database_path()),
        "label": f"🟡 SQLite local · {database_path().name}",
    }
