"""
fix_pmes_comissao.py — corrige listar_cobrancas_por_mes (strftime → Python)
                        e adiciona atualizar_comissao + UI de edição nas Lançadas.
Rodado pelo GitHub Actions workflow (fix_pmes.yml).
"""
import subprocess
import sys

# ═══════════════════════════════════════════════════════
# DATABASE.PY
# ═══════════════════════════════════════════════════════
with open("database.py", "r", encoding="utf-8") as f:
    db = f.read()

db_changed = False

# 1. Substituir listar_cobrancas_por_mes (strftime → Python puro)
OLD_FUNC = '''def listar_cobrancas_por_mes() -> list[dict]:
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
        return [dict(r) for r in rows]'''

NEW_FUNC = '''def listar_cobrancas_por_mes() -> list[dict]:
    """Agrupa cobranças lançadas por mês em Python (compatível SQLite + PostgreSQL)."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT lancado_em, valor_lancado, comissao
            FROM cobrancas_dominio
            WHERE status = 'lancada' AND lancado_em IS NOT NULL
            ORDER BY lancado_em DESC
            """
        ).fetchall()
    groups: dict = {}
    for r in rows:
        d = dict(r)
        em = str(d.get("lancado_em") or "")
        if len(em) < 7:
            continue
        mes_sort = em[:4] + em[5:7]
        mes_label = em[5:7] + "/" + em[:4]
        if mes_sort not in groups:
            groups[mes_sort] = {
                "mes": mes_label,
                "mes_sort": mes_sort,
                "qtd": 0,
                "total_lancado": 0.0,
                "total_comissao": 0.0,
            }
        groups[mes_sort]["qtd"] += 1
        groups[mes_sort]["total_lancado"] += float(d.get("valor_lancado") or 0)
        groups[mes_sort]["total_comissao"] += float(d.get("comissao") or 0)
    return sorted(groups.values(), key=lambda x: x["mes_sort"], reverse=True)'''

if OLD_FUNC in db:
    db = db.replace(OLD_FUNC, NEW_FUNC, 1)
    db_changed = True
    print("DB: listar_cobrancas_por_mes corrigida (Python puro)")
else:
    print("DB: AVISO — listar_cobrancas_por_mes antiga não encontrada, pulando")

# 2. Adicionar atualizar_comissao (função nova)
if "def atualizar_comissao(" not in db:
    ANCHOR = "def listar_cobrancas_pendentes("
    NEW_FN = '''def atualizar_comissao(cobranca_id: int, comissao: float | None) -> None:
    """Atualiza somente a comissão de uma cobrança já lançada."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE cobrancas_dominio SET comissao = ? WHERE id = ?",
            (comissao, cobranca_id),
        )


'''
    if ANCHOR in db:
        db = db.replace(ANCHOR, NEW_FN + ANCHOR, 1)
        db_changed = True
        print("DB: atualizar_comissao adicionada")
    else:
        print("DB: AVISO — âncora listar_cobrancas_pendentes não encontrada")

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

# 1. Importar atualizar_comissao
if "atualizar_comissao," not in app and "atualizar_comissao\n" not in app:
    OLD_IMP = "        listar_cobrancas_por_mes,"
    NEW_IMP = "        listar_cobrancas_por_mes,\n        atualizar_comissao,"
    if OLD_IMP in app:
        app = app.replace(OLD_IMP, NEW_IMP, 1)
        app_changed = True
        print("APP: atualizar_comissao importada")
    else:
        print("APP: AVISO — import listar_cobrancas_por_mes não encontrado")

# 2. UI de edição de comissão na tab Lançadas
if "edit_com_" not in app:
    OLD_LANCADAS = '            col_tl.success(f"💵 **Total lançado:** {_brl(total_lanc)} em {len(lancadas)} cobrança(s)")\n            col_tc.info(f"💰 **Minha comissão total:** {_brl(total_com)}")'
    NEW_LANCADAS = '''            col_tl.success(f"💵 **Total lançado:** {_brl(total_lanc)} em {len(lancadas)} cobrança(s)")
            col_tc.info(f"💰 **Minha comissão total:** {_brl(total_com)}")

            with st.expander("✏️ Editar comissão de uma cobrança"):
                nomes = {l["id"]: f"{l.get('cliente_nome')} — {(l.get('lancado_em') or '')[:10]}" for l in lancadas}
                sel_id = st.selectbox(
                    "Cobrança",
                    options=list(nomes.keys()),
                    format_func=lambda i: nomes[i],
                    key="edit_com_sel",
                )
                sel_reg = next((l for l in lancadas if l["id"] == sel_id), None)
                cur_com = float(sel_reg.get("comissao") or 0) if sel_reg else 0.0
                new_com = st.number_input(
                    "Comissão (R$)",
                    min_value=0.0,
                    value=cur_com,
                    step=5.0,
                    format="%.2f",
                    key="edit_com_val",
                )
                if st.button("💾 Salvar comissão", key="edit_com_btn"):
                    atualizar_comissao(sel_id, new_com if new_com > 0 else None)
                    st.success("Comissão atualizada!")
                    st.rerun()'''
    if OLD_LANCADAS in app:
        app = app.replace(OLD_LANCADAS, NEW_LANCADAS, 1)
        app_changed = True
        print("APP: UI de edição de comissão adicionada")
    else:
        print("APP: AVISO — âncora col_tc.info não encontrada")

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
    subprocess.run(["git", "commit", "-m", "fix: listar_cobrancas_por_mes sem strftime + editar comissão"], check=True)
    subprocess.run(["git", "push", remote, "main"], check=True)
    print("GIT: push realizado ✓")
else:
    print("GIT: nada a commitar")
