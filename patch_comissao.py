"""
patch_comissao.py — aplica campo comissão + tab Por Mês em database.py e app.py
Rodado pelo GitHub Actions workflow (aplicar_patch.yml).
"""
import subprocess
import sys

# ═══════════════════════════════════════════════════════
# DATABASE.PY
# ═══════════════════════════════════════════════════════
with open("database.py", "r", encoding="utf-8") as f:
    db = f.read()

db_changed = False

# 1. Migration — coluna comissao no banco existente
if "comissao REAL" not in db and "comissao        REAL" not in db:
    OLD_ANCHOR = "# DADOS MOCK PARA AS MATRIZES"
    NEW_INJECT = """    # ── cobrancas_dominio.comissao — migração para bancos existentes ──
    try:
        with get_conn() as conn:
            conn.execute(
                "ALTER TABLE cobrancas_dominio ADD COLUMN comissao REAL;"
            )
    except sqlite3.OperationalError:
        pass


# DADOS MOCK PARA AS MATRIZES"""
    if OLD_ANCHOR in db:
        db = db.replace(OLD_ANCHOR, NEW_INJECT, 1)
        db_changed = True
        print("DB: ALTER TABLE comissao adicionada ao init_db")
    else:
        print("DB: AVISO — âncora DADOS MOCK não encontrada")

# 1b. CREATE TABLE — adicionar coluna (para novos bancos)
if "comissao        REAL" not in db:
    OLD_CT = "        observacao      TEXT,\n        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE SET NULL,"
    NEW_CT = "        observacao      TEXT,\n        comissao        REAL,\n        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE SET NULL,"
    if OLD_CT in db:
        db = db.replace(OLD_CT, NEW_CT, 1)
        db_changed = True
        print("DB: CREATE TABLE cobrancas_dominio atualizado com comissao")

# 2. marcar_cobranca_lancada — adicionar param comissao
if "comissao: float | None = None" not in db:
    OLD = '''def marcar_cobranca_lancada(
    cobranca_id: int,
    *, valor_lancado: float | None = None,
    lancado_por: str | None = None,
    observacao: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE cobrancas_dominio SET
                 status = 'lancada',
                 valor_lancado = COALESCE(?, valor_sugerido),
                 lancado_em = datetime('now', 'localtime'),
                 lancado_por = ?,
                 observacao = COALESCE(?, observacao)
               WHERE id = ?""",
            (valor_lancado, lancado_por, observacao, cobranca_id),
        )'''
    NEW = '''def marcar_cobranca_lancada(
    cobranca_id: int,
    *, valor_lancado: float | None = None,
    lancado_por: str | None = None,
    observacao: str | None = None,
    comissao: float | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE cobrancas_dominio SET
                 status = 'lancada',
                 valor_lancado = COALESCE(?, valor_sugerido),
                 lancado_em = datetime('now', 'localtime'),
                 lancado_por = ?,
                 observacao = COALESCE(?, observacao),
                 comissao = ?
               WHERE id = ?""",
            (valor_lancado, lancado_por, observacao, comissao, cobranca_id),
        )'''
    if OLD in db:
        db = db.replace(OLD, NEW, 1)
        db_changed = True
        print("DB: marcar_cobranca_lancada atualizada")
    else:
        print("DB: AVISO — marcar_cobranca_lancada não encontrada, pulando")

# 3. listar_cobrancas_por_mes — nova função
if "listar_cobrancas_por_mes" not in db:
    ANCHOR = "def listar_cobrancas_pendentes("
    NEW_FUNC = '''def listar_cobrancas_por_mes() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                strftime('%m/%Y', lancado_em) AS mes,
                strftime('%Y%m', lancado_em)  AS mes_sort,
                COUNT(*)                       AS qtd,
                COALESCE(SUM(valor_lancado), 0) AS total_lancado,
                COALESCE(SUM(comissao), 0)      AS total_comissao
            FROM cobrancas_dominio
            WHERE status = 'lancada'
              AND lancado_em IS NOT NULL
            GROUP BY mes_sort
            ORDER BY mes_sort DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


'''
    if ANCHOR in db:
        db = db.replace(ANCHOR, NEW_FUNC + ANCHOR, 1)
        db_changed = True
        print("DB: listar_cobrancas_por_mes adicionada")
    else:
        print("DB: AVISO — âncora listar_cobrancas_pendentes não encontrada, pulando")

if db_changed:
    with open("database.py", "w", encoding="utf-8") as f:
        f.write(db)
    print("DB: database.py salvo ✓")
else:
    print("DB: nenhuma mudança necessária em database.py")

# ═══════════════════════════════════════════════════════
# APP.PY
# ═══════════════════════════════════════════════════════
with open("app.py", "r", encoding="utf-8") as f:
    app = f.read()

app_changed = False

# 1. Import listar_cobrancas_por_mes
if "listar_cobrancas_por_mes" not in app:
    OLD = "        contar_cobrancas_pendentes,\n        total_pendente_cobranca,"
    NEW = "        contar_cobrancas_pendentes,\n        total_pendente_cobranca,\n        listar_cobrancas_por_mes,"
    if OLD in app:
        app = app.replace(OLD, NEW, 1)
        app_changed = True
        print("APP: import listar_cobrancas_por_mes adicionado")
    else:
        print("APP: AVISO — bloco import não encontrado")

# 2. Campo comissao_val no formulário Pendentes
if "cob_com_" not in app:
    OLD = '''                        obs_lanc = st.text_input(
                            "Obs (opcional)",
                            key=f"cob_obs_{cb['id']}",
                            placeholder="Ex.: parcelado em 2x",
                        )'''
    NEW = '''                        comissao_val = st.number_input(
                            "Minha comissão (R$)",
                            min_value=0.0,
                            value=0.0,
                            step=5.0, format="%.2f",
                            key=f"cob_com_{cb['id']}",
                            help="Quanto ficou pra você desse lançamento.",
                        )
                        obs_lanc = st.text_input(
                            "Obs (opcional)",
                            key=f"cob_obs_{cb['id']}",
                            placeholder="Ex.: parcelado em 2x",
                        )'''
    if OLD in app:
        app = app.replace(OLD, NEW, 1)
        app_changed = True
        print("APP: campo comissao_val adicionado")
    else:
        print("APP: AVISO — obs_lanc input não encontrado")

# 3. Passar comissao para marcar_cobranca_lancada
if "comissao=comissao_val" not in app:
    OLD = '''                                marcar_cobranca_lancada(
                                    cb["id"],
                                    valor_lancado=valor_real,
                                    lancado_por=quem,
                                    observacao=obs_lanc or None,
                                )'''
    NEW = '''                                marcar_cobranca_lancada(
                                    cb["id"],
                                    valor_lancado=valor_real,
                                    lancado_por=quem,
                                    observacao=obs_lanc or None,
                                    comissao=comissao_val if comissao_val > 0 else None,
                                )'''
    if OLD in app:
        app = app.replace(OLD, NEW, 1)
        app_changed = True
        print("APP: comissao passada para marcar_cobranca_lancada")
    else:
        print("APP: AVISO — chamada marcar_cobranca_lancada não encontrada")

# 4. Tabs — adicionar 📊 Por Mês
if '"📊 Por Mês"' not in app:
    OLD = '''    tab_pend, tab_lanc, tab_val, tab_manual = st.tabs([
        f"📌 Pendentes ({qtd})",
        "✅ Lançadas",
        "⚙️ Valores sugeridos",
        "➕ Criar manual",
    ])'''
    NEW = '''    tab_pend, tab_lanc, tab_mes, tab_val, tab_manual = st.tabs([
        f"📌 Pendentes ({qtd})",
        "✅ Lançadas",
        "📊 Por Mês",
        "⚙️ Valores sugeridos",
        "➕ Criar manual",
    ])'''
    if OLD in app:
        app = app.replace(OLD, NEW, 1)
        app_changed = True
        print("APP: tab Por Mês adicionada na definição")
    else:
        print("APP: AVISO — definição de tabs não encontrada")

# 5. Tab Lançadas — adicionar comissão + totais separados
if '"Comissão"' not in app:
    OLD = '''            df = _pd.DataFrame([{
                "Cliente": l.get("cliente_nome"),
                "Tipo": l.get("tipo_servico"),
                "Valor lançado": f"R$ {(l.get('valor_lancado') or 0):.2f}",
                "Lançada em": (l.get("lancado_em") or "")[:16],
                "Por": l.get("lancado_por"),
                "Obs": l.get("observacao") or "",
            } for l in lancadas])
            st.dataframe(df, use_container_width=True, hide_index=True)
            total_lanc = sum(
                float(l.get("valor_lancado") or 0) for l in lancadas
            )
            st.success(
                f"💵 **Total já lançado:** "
                f"R$ {total_lanc:,.2f}".replace(",","X").replace(".",",").replace("X",".")
                + f" em {len(lancadas)} cobrança(s)"
            )'''
    NEW = '''            df = _pd.DataFrame([{
                "Cliente": l.get("cliente_nome"),
                "Tipo": l.get("tipo_servico"),
                "Valor lançado": f"R$ {(l.get('valor_lancado') or 0):.2f}",
                "Comissão": f"R$ {(l.get('comissao') or 0):.2f}",
                "Lançada em": (l.get("lancado_em") or "")[:16],
                "Por": l.get("lancado_por"),
                "Obs": l.get("observacao") or "",
            } for l in lancadas])
            st.dataframe(df, use_container_width=True, hide_index=True)
            total_lanc = sum(float(l.get("valor_lancado") or 0) for l in lancadas)
            total_com  = sum(float(l.get("comissao") or 0) for l in lancadas)
            def _brl(v): return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
            col_tl, col_tc = st.columns(2)
            col_tl.success(f"💵 **Total lançado:** {_brl(total_lanc)} em {len(lancadas)} cobrança(s)")
            col_tc.info(f"💰 **Minha comissão total:** {_brl(total_com)}")'''
    if OLD in app:
        app = app.replace(OLD, NEW, 1)
        app_changed = True
        print("APP: tab Lançadas atualizada com comissão")
    else:
        print("APP: AVISO — bloco dataframe Lançadas não encontrado")

# 6. Tab Por Mês — nova tab após Lançadas
if "with tab_mes:" not in app:
    OLD = "    # ============== TAB 3: Valores sugeridos =============="
    NEW = '''    # ============== TAB 3: Por Mês ==============
    with tab_mes:
        meses = listar_cobrancas_por_mes()
        if not meses:
            st.info("Nenhuma cobrança lançada ainda para mostrar por mês.")
        else:
            import pandas as _pd
            df_mes = _pd.DataFrame([{
                "Mês": m["mes"],
                "Qtd": m["qtd"],
                "Total lançado": f"R$ {m['total_lancado']:,.2f}".replace(",","X").replace(".",",").replace("X","."),
                "Minha comissão": f"R$ {m['total_comissao']:,.2f}".replace(",","X").replace(".",",").replace("X","."),
            } for m in meses])
            st.dataframe(df_mes, use_container_width=True, hide_index=True)
            grand_total  = sum(m["total_lancado"] for m in meses)
            grand_comiss = sum(m["total_comissao"] for m in meses)
            def _brl2(v): return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
            col_gt, col_gc = st.columns(2)
            col_gt.success(f"💵 **Total geral:** {_brl2(grand_total)}")
            col_gc.info(f"💰 **Comissão acumulada:** {_brl2(grand_comiss)}")

    # ============== TAB 4: Valores sugeridos =============='''
    if "    # ============== TAB 3: Valores sugeridos ==============" in app:
        app = app.replace(OLD, NEW, 1)
        app_changed = True
        print("APP: tab Por Mês adicionada")
    else:
        print("APP: AVISO — âncora TAB 3 não encontrada")

if app_changed:
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(app)
    print("APP: app.py salvo ✓")
else:
    print("APP: nenhuma mudança necessária em app.py")

# ═══════════════════════════════════════════════════════
# GIT COMMIT E PUSH
# ═══════════════════════════════════════════════════════
if db_changed or app_changed:
    import os
    token = os.environ.get("GITHUB_TOKEN", "")
    remote = f"https://x-access-token:{token}@github.com/Viniciusrqv/redesim-manager.git"
    subprocess.run(["git", "config", "user.email", "contabil@csm.com.br"], check=True)
    subprocess.run(["git", "config", "user.name", "CSM Bot"], check=True)
    files = []
    if db_changed:
        files.append("database.py")
    if app_changed:
        files.append("app.py")
    subprocess.run(["git", "add"] + files, check=True)
    subprocess.run(["git", "commit", "-m", "fix: migration comissao REAL + CREATE TABLE atualizado"], check=True)
    subprocess.run(["git", "push", remote, "main"], check=True)
    print("GIT: push realizado ✓")
else:
    print("GIT: nada a commitar")
