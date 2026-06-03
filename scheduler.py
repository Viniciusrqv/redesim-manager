"""
scheduler.py
------------
Executa como um processo paralelo ao Streamlit.
Todo dia no horário configurado (HORARIO_LEMBRETE) verifica
processos parados e dispara alertas:
    - AMARELO: >= DIAS_AMARELO (3 dias)   → alerta preventivo
    - VERMELHO: >= DIAS_VERMELHO (4 dias) → atraso crítico (prazo REDESIM estourado)

Rode em um terminal separado:
    python scheduler.py

Ou, em Linux/macOS, em segundo plano:
    nohup python scheduler.py > scheduler.log 2>&1 &
"""
import logging
import time

import schedule

from datetime import datetime

from config import DIAS_AMARELO, DIAS_VERMELHO, HORARIO_LEMBRETE, HORARIOS_LEMBRETE
from database import (init_db, processos_atrasados,
                      documentos_proximos_vencimento,
                      alvaras_vencendo,
                      listar_todos_protocolos, get_conn,
                      STATUS_PROTOCOLO_OK, STATUS_PROTOCOLO_PROBLEMA,
                      pendencias_em_alerta,
                      cnaes_pendentes_verificacao,
                      listar_cobrancas_pendentes,
                      total_pendente_cobranca)
from utils.notifier import enviar_alerta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("scheduler")


def checar_documentos_vencendo():
    """Verifica documentos vigentes cujo vencimento está dentro do dias_alerta."""
    log.info("Verificando documentos com vencimento próximo...")
    docs = documentos_proximos_vencimento()
    if not docs:
        log.info("Nenhum documento a renovar. ✅")
        return

    vencidos = [d for d in docs if d["dias_para_vencer"] < 0]
    a_vencer = [d for d in docs if d["dias_para_vencer"] >= 0]

    linhas = ["📄 <b>Documentos a renovar</b>\n"]

    if vencidos:
        linhas.append(f"🔴 <b>{len(vencidos)}</b> documento(s) VENCIDO(S):")
        for d in vencidos:
            linhas.append(
                f"• <b>{d['razao_social']}</b> — {d['tipo']} "
                f"#{d.get('numero') or '?'} — venceu em {d['data_vencimento']} "
                f"({abs(d['dias_para_vencer'])}d atrás)"
            )
        linhas.append("")

    if a_vencer:
        linhas.append(f"🟡 <b>{len(a_vencer)}</b> documento(s) A VENCER:")
        for d in a_vencer:
            linhas.append(
                f"• <b>{d['razao_social']}</b> — {d['tipo']} "
                f"#{d.get('numero') or '?'} — vence em {d['data_vencimento']} "
                f"(faltam {d['dias_para_vencer']}d · alerta {d['dias_alerta']}d)"
            )

    enviar_alerta("\n".join(linhas))


def checar_avcb_vencendo():
    """Alerta consolidado dos AVCBs vencendo em até 60 dias."""
    log.info("Verificando alvarás de bombeiros...")
    try:
        alvs = alvaras_vencendo(dias=60)
    except Exception as exc:
        log.warning("Falha ao checar alvarás AVCB: %s", exc)
        return
    if not alvs:
        return

    linhas = [f"🚒 <b>{len(alvs)} alvará(s) AVCB/CLCB vencendo em até 60d</b>\n"]
    for a in alvs:
        dias = int(a.get("dias_para_vencer") or 0)
        linhas.append(
            f"• <b>{a['razao_social']}</b> — {a.get('tipo') or 'AVCB'} "
            f"#{a.get('numero') or '?'} — vence {a['data_vencimento']} "
            f"({dias}d)"
        )
    enviar_alerta("\n".join(linhas))


def checar_atrasos():
    """Verifica processos parados e envia alertas separados por nível."""
    log.info(
        "Verificando processos (amarelo >= %s / vermelho >= %s dias)...",
        DIAS_AMARELO, DIAS_VERMELHO
    )

    # Busca tudo acima do limiar amarelo (3 dias)
    todos = processos_atrasados(DIAS_AMARELO)
    if not todos:
        log.info("Nenhum processo em alerta. ✅")
        return

    # Separa por nível de severidade
    vermelhos = [p for p in todos if p["dias_parado"] >= DIAS_VERMELHO]
    amarelos = [p for p in todos
                if DIAS_AMARELO <= p["dias_parado"] < DIAS_VERMELHO]

    # 1) Resumo diário consolidado
    linhas = ["🚨 <b>Lembrete diário REDESIM</b>\n"]

    if vermelhos:
        linhas.append(
            f"🔴 <b>{len(vermelhos)}</b> processo(s) com prazo REDESIM "
            f"ESTOURADO (>= {DIAS_VERMELHO} dias):"
        )
        for p in vermelhos:
            linhas.append(
                f"• <b>{p['razao_social']}</b> (ID {p['id']}) — "
                f"<i>{p['status']}</i> — {p['dias_parado']} dia(s) parado"
            )
        linhas.append("")

    if amarelos:
        linhas.append(
            f"🟡 <b>{len(amarelos)}</b> processo(s) em alerta preventivo "
            f"(>= {DIAS_AMARELO} dias):"
        )
        for p in amarelos:
            linhas.append(
                f"• <b>{p['razao_social']}</b> (ID {p['id']}) — "
                f"<i>{p['status']}</i> — {p['dias_parado']} dia(s) parado"
            )

    enviar_alerta("\n".join(linhas))

    # 2) Alerta individual (só para vermelhos — os críticos)
    for p in vermelhos:
        msg = (f"🔴 <b>ATRASO CRÍTICO</b> — Processo "
               f"<b>{p['razao_social']}</b> (ID:{p['id']}) parado há "
               f"{p['dias_parado']} dias. O prazo REDESIM de "
               f"{DIAS_VERMELHO} dias foi estourado! "
               f"Status atual: {p['status']}.")
        enviar_alerta(msg, processo_id=p["id"])


def checar_protocolos_redesim():
    """Verifica protocolos REDESIM em andamento e dispara alertas
    pelo número de dias desde data_solicitacao.

    Régua igual aos processos:
        AMARELO  >= DIAS_AMARELO  (default 3) e < DIAS_VERMELHO
        VERMELHO >= DIAS_VERMELHO (default 4)

    Considera apenas protocolos cujo status NÃO está em
    STATUS_PROTOCOLO_OK | STATUS_PROTOCOLO_PROBLEMA e que NÃO foram
    substituídos (substituido_por_id IS NULL).

    SILENCIA alerta se a empresa teve um PROCESSO ANTIGO finalizado
    nos últimos 14 dias — provavelmente o usuário finalizou no
    Dashboard/Kanban e esqueceu de fechar o protocolo REDESIM.
    """
    log.info("Verificando protocolos REDESIM em andamento...")
    todos = listar_todos_protocolos()
    em_andamento = [
        p for p in todos
        if p["status"] not in (STATUS_PROTOCOLO_OK | STATUS_PROTOCOLO_PROBLEMA)
        and not p.get("substituido_por_id")
    ]
    if not em_andamento:
        log.info("Nenhum protocolo REDESIM em andamento. ✅")
        return

    # Filtro de "empresas com processo recente finalizado": evita
    # alertar de protocolo REDESIM cuja empresa o usuário já marcou
    # como Deferido/Indeferido/Arquivado no sistema antigo (Dashboard).
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT empresa_id FROM processos
               WHERE status IN ('Deferido','Indeferido','Arquivado')
                 AND julianday('now') -
                     julianday(ultima_movimentacao) <= 14"""
        ).fetchall()
        empresas_recem_fechadas = {
            dict(r)["empresa_id"] for r in rows
        }

    if empresas_recem_fechadas:
        antes = len(em_andamento)
        em_andamento = [
            p for p in em_andamento
            if p.get("empresa_id") not in empresas_recem_fechadas
        ]
        silenciados = antes - len(em_andamento)
        if silenciados:
            log.info(
                "Silenciados %d protocolo(s) de empresas com processo "
                "antigo finalizado nos ultimos 14 dias.",
                silenciados,
            )

    if not em_andamento:
        log.info(
            "Nenhum protocolo REDESIM em andamento "
            "(apos filtro de processos recem fechados). ✅"
        )
        return

    hoje = datetime.now()
    amarelos: list[dict] = []
    vermelhos: list[dict] = []

    # cache de razões sociais
    with get_conn() as conn:
        emp_map = {
            r["id"]: r["razao_social"] for r in conn.execute(
                "SELECT id, razao_social FROM empresas"
            ).fetchall()
        }

    for p in em_andamento:
        ds = p.get("data_solicitacao")
        if not ds:
            continue
        try:
            d0 = datetime.strptime(ds, "%Y-%m-%d")
        except ValueError:
            continue
        dias = (hoje - d0).days
        p["_dias"] = dias
        p["_razao_social"] = emp_map.get(p["empresa_id"], "?")
        if dias >= DIAS_VERMELHO:
            vermelhos.append(p)
        elif dias >= DIAS_AMARELO:
            amarelos.append(p)

    if not amarelos and not vermelhos:
        log.info("Nenhum protocolo REDESIM em alerta. ✅")
        return

    linhas = ["📜 <b>Protocolos REDESIM em alerta</b>\n"]
    if vermelhos:
        linhas.append(
            f"🔴 <b>{len(vermelhos)}</b> protocolo(s) com prazo REDESIM "
            f"ESTOURADO (>= {DIAS_VERMELHO} dias):"
        )
        for p in vermelhos:
            linhas.append(
                f"• <b>{p['_razao_social']}</b> — "
                f"{p['numero_protocolo']} ({p['tipo']}) — "
                f"<i>{p['status']}</i> — {p['_dias']} dia(s)"
            )
        linhas.append("")
    if amarelos:
        linhas.append(
            f"🟡 <b>{len(amarelos)}</b> protocolo(s) em alerta preventivo "
            f"(>= {DIAS_AMARELO} dias):"
        )
        for p in amarelos:
            linhas.append(
                f"• <b>{p['_razao_social']}</b> — "
                f"{p['numero_protocolo']} ({p['tipo']}) — "
                f"<i>{p['status']}</i> — {p['_dias']} dia(s)"
            )
    enviar_alerta("\n".join(linhas))

    # Alerta individual para os vermelhos
    for p in vermelhos:
        msg = (f"🔴 <b>ATRASO CRÍTICO</b> — Protocolo "
               f"<b>{p['numero_protocolo']}</b> ({p['tipo']}) da empresa "
               f"<b>{p['_razao_social']}</b> está há {p['_dias']} dia(s) "
               f"como <i>{p['status']}</i>. Prazo REDESIM de "
               f"{DIAS_VERMELHO} dias estourado.")
        enviar_alerta(msg)


def checar_pendencias_gerais():
    """Alerta consolidado das pendências gerais (malha fina, follow-up
    com cliente, etc.) que estão paradas há mais que `dias_alerta` ou
    que tiveram o prazo vencido."""
    log.info("Verificando pendências gerais...")
    try:
        pendentes = pendencias_em_alerta()
    except Exception as exc:
        log.warning("Falha ao checar pendências: %s", exc)
        return
    if not pendentes:
        return

    vencidas = [p for p in pendentes if p["alerta"] == "🔴"]
    paradas = [p for p in pendentes if p["alerta"] == "🟡"]

    linhas = [f"📌 <b>Pendências gerais em alerta</b>\n"]

    if vencidas:
        linhas.append(
            f"🔴 <b>{len(vencidas)}</b> pendência(s) com PRAZO VENCIDO:"
        )
        for p in vencidas:
            atraso = abs(p["dias_para_prazo"] or 0)
            linhas.append(
                f"• <b>{p['razao_social']}</b> — {p['assunto']} "
                f"(<i>{p['prioridade']}</i>) — venceu há {atraso}d"
            )
        linhas.append("")

    if paradas:
        linhas.append(
            f"🟡 <b>{len(paradas)}</b> pendência(s) PARADA(S) "
            f"sem movimentação:"
        )
        for p in paradas:
            linhas.append(
                f"• <b>{p['razao_social']}</b> — {p['assunto']} "
                f"(<i>{p['prioridade']}</i>) — {p['dias_parado']}d sem mexer"
            )
    enviar_alerta("\n".join(linhas))


def checar_cobrancas_dominio():
    """Avisa por Telegram as cobranças pendentes de lançar no DOMÍNIO.
    Roda junto com os outros lembretes 2x ao dia. Não bombardeia: só
    manda se tiver alguma pendente.
    """
    log.info("Verificando cobranças DOMÍNIO pendentes...")
    try:
        pends = listar_cobrancas_pendentes(status="pendente")
    except Exception as exc:
        log.warning("Falha ao listar cobranças: %s", exc)
        return
    if not pends:
        log.info("Sem cobranças pendentes ✅")
        return

    try:
        total = total_pendente_cobranca()
    except Exception:
        total = sum(float(p.get("valor_sugerido") or 0) for p in pends)

    linhas = [
        f"💰 <b>{len(pends)} cobrança(s) pendente(s) no DOMÍNIO</b>\n",
        f"💵 Total a lançar: <b>R$ {total:,.2f}</b>".replace(
            ",","X").replace(".",",").replace("X","."),
        "",
    ]
    tipo_label = {
        "LICENCA_REDESIM": "📋 Licença REDESIM",
        "VISA":            "🏥 Vigilância Sanitária",
        "AVCB":            "🚒 AVCB Bombeiros",
        "OUTRO":           "📌 Outro",
    }
    # Top 10 mais antigas
    for p in pends[:10]:
        valor = f"R$ {(p.get('valor_sugerido') or 0):.2f}".replace(".",",")
        criado = (p.get("criado_em") or "")[:10]
        lbl = tipo_label.get(p.get("tipo_servico"), p.get("tipo_servico", "?"))
        linhas.append(
            f"• <b>{p.get('cliente_nome','—')}</b> — {lbl} — "
            f"{valor} — desde {criado}"
        )
    if len(pends) > 10:
        linhas.append(f"... e mais {len(pends) - 10} cobrança(s).")
    linhas.append("")
    linhas.append("👉 Entre no app e marque como 'Lancei' depois de "
                  "registrar no DOMÍNIO.")
    enviar_alerta("\n".join(linhas))


def checar_cnaes_desatualizados():
    """Job SEMANAL: alerta CNAEs consultados recentemente mas com
    verificação > 90 dias OU nunca verificados pelo sub-agente Cowork.
    """
    log.info("Verificando CNAEs com necessidade de revalidação...")
    try:
        pendentes = cnaes_pendentes_verificacao(dias_max=90, top_n=20)
    except Exception as exc:
        log.warning("Falha ao listar CNAEs pendentes: %s", exc)
        return
    if not pendentes:
        log.info("Nenhum CNAE pendente de revalidação.")
        return

    nunca = [p for p in pendentes if not p.get("ultima_verificacao")]
    antigos = [p for p in pendentes if p.get("ultima_verificacao")]

    linhas = ["📚 <b>Revalidação semanal de CNAEs</b>\n"]
    if nunca:
        linhas.append(
            f"🛑 <b>{len(nunca)}</b> CNAE(s) consultado(s) recentemente "
            "<b>nunca verificados</b> pelo sub-agente:"
        )
        for p in nunca[:10]:
            linhas.append(f"• <code>{p['cnae']}</code> — {p['consultas_30d']} consulta(s) em 30d")
        linhas.append("")
    if antigos:
        linhas.append(
            f"⚠️ <b>{len(antigos)}</b> CNAE(s) com verificação antiga (≥ 90d):"
        )
        for p in antigos[:10]:
            linhas.append(
                f"• <code>{p['cnae']}</code> — {p['consultas_30d']} consultas, "
                f"última verificação há {p.get('dias_desde_verif', '?')}d"
            )
    linhas.append("")
    linhas.append(
        "👉 Abra o <b>🔬 Consultor de CNAE</b>, consulte cada um e cole o "
        "payload no Cowork pedindo verificação."
    )
    enviar_alerta("\n".join(linhas))


def sincronizar_tarefas_gestta():
    """Sincroniza tarefas do GESTTA com o banco local (status, novas tarefas)."""
    import urllib.request, json, datetime
    try:
        with get_conn() as conn:
            # Buscar JWTs salvos de todos os usuários
            rows = conn.execute("SELECT email, jwt_token FROM usuarios_gestta_jwt").fetchall()
    except Exception as e:
        log.warning("sincronizar_tarefas_gestta: erro ao buscar JWTs: %s", e)
        return

    if not rows:
        log.info("sincronizar_tarefas_gestta: nenhum JWT configurado")
        return

    for email, jwt in rows:
        if not jwt:
            continue
        try:
            # Buscar tarefas abertas + concluídas recentes do GESTTA
            payload = json.dumps({
                "status": ["OPEN", "IMPEDIMENT", "DONE"],
                "limit": 200,
                "date_type": "DUE_DATE",
            }).encode()
            req = urllib.request.Request(
                "https://api.gestta.com.br/core/customer/task/search",
                data=payload,
                headers={"Authorization": jwt, "Content-Type": "application/json",
                         "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            tarefas = data.get("docs", [])

            atualizadas = 0
            with get_conn() as conn:
                for t in tarefas:
                    gid = t.get("_id")
                    status = t.get("status", "OPEN")
                    nome = (t.get("name") or t.get("tarefa_nome") or "")[:120]
                    cliente = (t.get("customer", {}) or {}).get("name", "")[:120]
                    due = t.get("dueDate") or t.get("due_date") or ""
                    if not gid:
                        continue
                    # Verificar se já existe
                    exists = conn.execute(
                        "SELECT id, status_gestta FROM tarefas_gestta WHERE gestta_id = ?", (gid,)
                    ).fetchone()
                    if exists:
                        if exists[1] != status:
                            conn.execute(
                                "UPDATE tarefas_gestta SET status_gestta = ?, atrasada = ? WHERE gestta_id = ?",
                                (status, "1" if status in ("OPEN", "IMPEDIMENT") else "0", gid),
                            )
                            atualizadas += 1
                    else:
                        # Nova tarefa — inserir
                        cliente_norm = cliente.upper().strip()
                        conn.execute(
                            """INSERT OR IGNORE INTO tarefas_gestta
                               (gestta_id, tarefa_nome, cliente_nome, cliente_norm,
                                status_gestta, atrasada, due_date)
                               VALUES (?,?,?,?,?,?,?)""",
                            (gid, nome, cliente, cliente_norm, status,
                             "1" if status in ("OPEN", "IMPEDIMENT") else "0", due),
                        )
                        atualizadas += 1

            log.info("sincronizar_tarefas_gestta [%s]: %d tarefa(s) atualizadas", email, atualizadas)

        except Exception as e:
            log.warning("sincronizar_tarefas_gestta [%s]: erro: %s", email, e)


def checar_normas_vencendo():
    """Alerta quando bases legais precisam de atualizacao (> 180 dias)."""
    try:
        from database import get_conn
        import datetime
        hoje = datetime.date.today()
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT base, titulo, ultima_atualizacao, versao FROM normas_atualizacao"
            ).fetchall()
        alertas = []
        for r in rows:
            base, titulo, ultima, versao = r[0], r[1], r[2], r[3]
            if not ultima:
                alertas.append(f"⚪ {titulo[:35]} — NUNCA atualizada")
            else:
                try:
                    data_ult = datetime.date.fromisoformat(str(ultima)[:10])
                    dias = (hoje - data_ult).days
                    if dias > 180:
                        alertas.append(f"🔴 {titulo[:35]} — {dias}d sem atualizar")
                    elif dias > 90:
                        alertas.append(f"🟡 {titulo[:35]} — {dias}d (revisar em breve)")
                except Exception:
                    pass
        if not alertas:
            return
        msg = "📋 *Bases legais que precisam de atençao:*\n" + "\n".join(f"• {a}" for a in alertas)
        msg += "\n\nAcesse: *Atualizar Normas* no REDESIM Manager."
        for uid in _get_telegram_users():
            send_telegram(uid, msg)
        log.info("checar_normas_vencendo: %d alerta(s)", len(alertas))
    except Exception as e:
        log.warning("checar_normas_vencendo erro: %s", e)


def rodar_todos():
    """Executa os checks em sequência."""
    checar_atrasos()
    checar_protocolos_redesim()
    checar_documentos_vencendo()
    checar_avcb_vencendo()
    checar_pendencias_gerais()
    sincronizar_tarefas_gestta()
    checar_normas_vencendo()


def main():
    init_db()
    horarios_str = ", ".join(HORARIOS_LEMBRETE) or HORARIO_LEMBRETE
    log.info(
        "Scheduler iniciado. Lembretes DIÁRIOS às %s "
        "(amarelo %sd / vermelho %sd + protocolos REDESIM + "
        "documentos a vencer + AVCBs 60d).",
        horarios_str, DIAS_AMARELO, DIAS_VERMELHO,
    )
    for horario in HORARIOS_LEMBRETE:
        try:
            schedule.every().day.at(horario).do(rodar_todos)
            log.info("  ↳ agendado para %s", horario)
        except Exception as exc:  # noqa: BLE001
            log.error("  ✗ horário inválido '%s': %s", horario, exc)

    # SEMANAL: revalidação de CNAEs pendentes — toda segunda 06:00
    try:
        schedule.every().monday.at("06:00").do(checar_cnaes_desatualizados)
        log.info("  ↳ agendado SEMANAL: segunda 06:00 (revalidação CNAE)")
    except Exception as exc:  # noqa: BLE001
        log.error("  ✗ falha agendamento semanal CNAE: %s", exc)

    # Executa uma vez na inicialização, para feedback imediato
    rodar_todos()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
