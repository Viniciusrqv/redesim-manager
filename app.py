"""
app.py
------
Interface principal do REDESIM MANAGER.
Rode com:
    streamlit run app.py
"""
from __future__ import annotations

import io
import os
from datetime import date

import pandas as pd
import streamlit as st

from config import (DIAS_AMARELO, DIAS_VERMELHO, DIAS_ALERTA,
                    HORARIO_LEMBRETE,
                    telegram_configurado, twilio_configurado,
                    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                    RESPONSAVEL_PADRAO,
                    GESTTA_JWT, gestta_configurado)
from database import (init_db, listar_empresas, criar_empresa,
                      listar_processos, criar_processo, atualizar_status,
                      cnaes_do_processo, STATUS_VALIDOS,
                      upsert_cnae_risco, upsert_vigilancia,
                      excluir_vigilancia, excluir_varios_vigilancia,
                      importar_cnae_risco_em_massa,
                      processos_atrasados,
                      criar_alvara_bombeiros, listar_alvaras_bombeiros,
                      alvaras_vencendo, excluir_alvara_bombeiros,
                      buscar_bombeiros_cnae, listar_bombeiros_cnae,
                      upsert_bombeiros_cnae, excluir_bombeiros_cnae,
                      excluir_varios_bombeiros_cnae,
                      TIPOS_DOCUMENTO_VENCIMENTO,
                      criar_documento_vencimento, listar_documentos_vencimento,
                      documentos_proximos_vencimento,
                      atualizar_documento_vencimento,
                      excluir_documento_vencimento, renovar_documento,
                      NORMAS_META, registrar_atualizacao_norma,
                      ultima_atualizacao, historico_atualizacoes,
                      dias_desde_atualizacao, status_normas,
                      # Anotações de protocolo (log do que foi feito)
                      criar_anotacao_protocolo, listar_anotacoes_protocolo,
                      # Protocolos REDESIM
                      TIPOS_PROTOCOLO_REDESIM, TIPO_PROTOCOLO_VIABILIDADE,
                      TIPO_PROTOCOLO_LICENCIAMENTO,
                      STATUS_PROTOCOLO_VIABILIDADE,
                      STATUS_PROTOCOLO_LICENCIAMENTO,
                      STATUS_PROTOCOLO_PROBLEMA, STATUS_PROTOCOLO_OK,
                      STATUS_PROTOCOLO_EM_ANDAMENTO,
                      buscar_empresa_por_cnpj, criar_protocolo_redesim,
                      listar_protocolos_empresa, listar_todos_protocolos,
                      buscar_protocolo_redesim, atualizar_status_protocolo,
                      excluir_protocolo_redesim, atualizar_empresa,
                      protocolos_problematicos_ativos, substituir_protocolos,
                      # GESTTA
                      RISCOS_GESTTA, classificar_risco_tarefa_gestta,
                      TIPOS_TAREFA_GESTTA, TIPO_TAREFA_LABELS,
                      TIPO_TAREFA_LICENCA_FUNC, TIPO_TAREFA_ALVARA_SANIT,
                      TIPO_TAREFA_BOMBEIROS, TIPO_TAREFA_DEVOLUCAO,
                      classificar_tipo_tarefa_gestta,
                      contar_tarefas_por_tipo,
                      reclassificar_tipos_tarefas,
                      pular_tarefa_gestta, despular_tarefa_gestta,
                      fila_renovacao_licencas,
                      iniciar_protocolo_da_tarefa,
                      normalizar_nome_cliente, match_empresa_por_nome,
                      importar_tarefas_gestta, listar_tarefas_gestta,
                      atualizar_tarefa_gestta, marcar_tarefa_resolvida,
                      excluir_tarefa_gestta, estatisticas_tarefas_gestta,
                      listar_responsaveis_gestta, buscar_tarefa_gestta,
                      rematch_empresas_gestta,
                      adicionar_anotacao_local_gestta,
                      marcar_anotacao_replicada,
                      listar_anotacoes_locais_gestta,
                      sugerir_proximo_passo,
                      # Pendências gerais
                      STATUS_PENDENCIA, PRIORIDADES_PENDENCIA,
                      criar_pendencia, listar_pendencias, buscar_pendencia,
                      atualizar_pendencia, atualizar_status_pendencia,
                      resolver_pendencia, excluir_pendencia,
                      adicionar_movimento_pendencia,
                      listar_movimentos_pendencia,
                      estatisticas_pendencias,
                      # CNAE Consultor
                      analisar_cnae,
                      upsert_cnae_conselho, listar_conselhos_cnae,
                      upsert_cnae_ambiental, buscar_cnae_ambiental,
                      upsert_cnae_anvisa, buscar_cnae_anvisa,
                      registrar_consulta_cnae,
                      upsert_cnae_outro_registro,
                      listar_outros_registros_cnae,
                      upsert_cnae_habilitacao_profissional,
                      listar_habilitacoes_cnae)
from utils.cnae_tools import (classificar_cnae, consolidar, normalizar_cnae,
                              extrair_dados_cartao_cnpj,
                              extrair_tabela_nr04_pdf, classe_do_cnae,
                              extrair_dados_documento, extrair_dados_auto,
                              extrair_dados_avcb)
from utils.notifier import enviar_alerta, enviar_telegram

# ---------------------------------------------------------
# SETUP INICIAL
# ---------------------------------------------------------
st.set_page_config(
    page_title="REDESIM Manager · CSM Contabilidade",
    page_icon="🔷",
    layout="wide",
    # "auto" = sidebar aberta no desktop, fechada no mobile.
    # Sem isso a sidebar ocupa metade da tela no celular e fica ruim.
    initial_sidebar_state="auto",
)

# ====================================================================
# AUTENTICAÇÃO — bloqueia tudo até logar (em produção)
# Em dev local (sem SUPABASE_URL setada), auth.exigir_login() retorna
# um usuário fake e o app abre normalmente.
# ====================================================================
from auth import exigir_login, renderizar_widget_sidebar
_user = exigir_login()

# Init do banco só uma vez por sessão (sem essa cache, init_db roda
# em CADA reload e adiciona ~2s de latência por click no Postgres).
@st.cache_resource(show_spinner=False)
def _ensure_db_initialized():
    init_db()
    return True
_ensure_db_initialized()

# =====================================================================
# DESIGN SYSTEM — REDESIM Manager
# Paleta B2 (Azul royal) — corporativo moderno
# Brand:    #1F4FD3  →  primary, links, destaques
# Hover:    #1A41B3
# Light bg: #E8EFFE  →  highlights / item ativo
# Body:     #F6F8FC
# Surface:  #FFFFFF  →  cards
# Border:   #E5E9F2
# Texto 1:  #1A2A4A  →  títulos / valor
# Texto 2:  #4B5563  →  labels / body
# Texto 3:  #6B7280  →  hints
# Danger:   #DC2626 / bg #FEF2F2
# Warning:  #D97706 / bg #FFFBEB
# Success:  #047857 / bg #F0FDF5
# =====================================================================
# Injeta a fonte via tag link (mais confiável que @import dentro de <style>)
st.markdown(
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">',
    unsafe_allow_html=True,
)

# IMPORTANTE: o CSS vive em static/style.css e é lido em runtime.
# Motivo: quando o CSS era inline aqui dentro de st.markdown, os
# comentários "/* ===== Título ===== */" tinham "=====" que o parser
# Markdown do Streamlit interpreta como sublinhado de heading setext
# H1, e isso quebrava o <style> no meio, vazando o restante do CSS
# como texto na tela. Lendo o arquivo direto do disco e injetando o
# conteúdo bruto numa única chamada st.markdown evita esse problema.
from pathlib import Path as _Path

@st.cache_resource(show_spinner=False)
def _carregar_css() -> str:
    css_path = _Path(__file__).parent / "static" / "style.css"
    try:
        return css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""

_css_body = _carregar_css()
if _css_body:
    st.markdown(f"<style>{_css_body}</style>", unsafe_allow_html=True)


# =====================================================================
# CACHE DE QUERIES — performance
# ---------------------------------------------------------------------
# O app online (Streamlit Cloud + Supabase) era lento porque cada
# clique re-executava as mesmas queries grandes (listar_empresas,
# listar_processos, listar_pendencias, listar_documentos_vencimento,
# etc.) e cada round-trip pro Postgres custa ~50-150ms.
#
# Com @st.cache_data(ttl=N) o resultado fica em memória por N segundos
# e os cliques entre páginas usam o cache. TTL curto pra mudanças
# da equipe aparecerem rapidinho.
#
# Para invalidar o cache imediatamente após gravar (ex.: depois de
# criar/editar/excluir), use a função `_invalidar_cache_db()` abaixo.
# =====================================================================
@st.cache_data(ttl=45, show_spinner=False)
def _cache_empresas():
    return listar_empresas()


@st.cache_data(ttl=20, show_spinner=False)
def _cache_processos():
    return listar_processos()


@st.cache_data(ttl=30, show_spinner=False)
def _cache_pendencias_abertas():
    return listar_pendencias(apenas_abertas=True)


@st.cache_data(ttl=30, show_spinner=False)
def _cache_documentos_vigentes():
    return listar_documentos_vencimento(apenas_vigentes=True)


@st.cache_data(ttl=30, show_spinner=False)
def _cache_alvaras_bombeiros():
    return listar_alvaras_bombeiros()


@st.cache_data(ttl=30, show_spinner=False)
def _cache_tarefas_gestta_pendentes():
    return listar_tarefas_gestta(apenas_pendentes=True)


def _invalidar_cache_db():
    """Limpa TODOS os caches de query. Chame depois de criar/editar/
    excluir qualquer registro pra forçar releitura do banco."""
    _cache_empresas.clear()
    _cache_processos.clear()
    _cache_pendencias_abertas.clear()
    _cache_documentos_vigentes.clear()
    _cache_alvaras_bombeiros.clear()
    _cache_tarefas_gestta_pendentes.clear()


# =====================================================================
# Wrapper: atualizar_status_protocolo + replicar no GESTTA
# ---------------------------------------------------------------------
# Eduardo pediu que TODA mudança de status de protocolo REDESIM seja
# automaticamente registrada como ANOTAÇÃO na tarefa GESTTA vinculada,
# usando o JWT do USUÁRIO LOGADO (não o global). Quando o status é
# terminal (Aprovada/Concluída), também aparece um aviso visível
# orientando o usuário a CONCLUIR a tarefa diretamente no GESTTA.
# =====================================================================
def _replicar_status_no_gestta(
    protocolo: dict, novo_status: str,
    observacoes: str | None = None,
) -> dict:
    """Envia anotação no GESTTA da tarefa vinculada ao protocolo.

    - Usa o JWT do usuário LOGADO (obter_jwt_gestta_efetivo).
    - Se o protocolo não tem tarefa vinculada → não faz nada.
    - Retorna {ok, mensagem, finalizou}.

    finalizou=True quando o status é Aprovada/Concluída — sinal pra UI
    mostrar o aviso "✋ conclua a tarefa no GESTTA".
    """
    from database import (
        obter_jwt_gestta_efetivo,
        STATUS_PROTOCOLO_OK,
    )
    from auth import usuario_atual as _u_at

    out = {"ok": False, "mensagem": "", "finalizou": False, "tarefa": None}

    # Acha tarefa vinculada
    try:
        from database import get_conn as _gc
        with _gc() as conn:
            r = conn.execute(
                """SELECT id, gestta_id, tarefa_nome, cliente_nome,
                          responsavel
                   FROM tarefas_gestta
                   WHERE protocolo_id = ? AND resolvida = 0
                   ORDER BY id DESC LIMIT 1""",
                (protocolo["id"],),
            ).fetchone()
        if not r:
            out["mensagem"] = "Sem tarefa GESTTA vinculada"
            return out
        tarefa = dict(r)
    except Exception as exc:
        out["mensagem"] = f"Erro buscando tarefa: {exc}"
        return out

    out["tarefa"] = tarefa
    gid = tarefa.get("gestta_id")
    if not gid:
        out["mensagem"] = (
            "Tarefa vinculada mas sem gestta_id "
            "(provavelmente vinda de XLSX antigo, não da API)"
        )
        return out

    # JWT do usuário logado
    _u = _u_at() or {}
    jwt = obter_jwt_gestta_efetivo(_u.get("email"))
    if not jwt:
        out["mensagem"] = (
            "Sem JWT GESTTA configurado pro usuário logado — "
            "cadastre em ⚙️ Configurações → Meu GESTTA"
        )
        return out

    # Monta mensagem
    bolinha = {
        "Em análise": "🟡",
        "Pendente de avaliação do risco": "🟡",
        "Aprovada": "🟢",
        "Concluída": "🟢",
        "Indeferida": "🔴",
        "Cancelada": "🔴",
        "Inativa": "🔴",
    }.get(novo_status, "🔵")

    autor = _u.get("nome") or _u.get("email") or "Equipe CSM"
    texto = (
        f"[REDESIM Manager] {bolinha} Status atualizado para "
        f"{novo_status} — Protocolo "
        f"{protocolo.get('numero_protocolo') or '?'} "
        f"({protocolo.get('tipo') or '?'})."
    )
    if observacoes:
        texto += f"\n\nObservações: {observacoes}"
    texto += f"\n\n— {autor}"

    # Envia via API GESTTA
    try:
        from utils.gestta_api import GesttaClient
        cli = GesttaClient(jwt)
        cli.adicionar_comentario_tarefa(gid, texto, external=False)
        out["ok"] = True
        out["mensagem"] = "Anotação enviada ao GESTTA ✅"
    except Exception as exc:
        out["mensagem"] = f"Falha ao enviar anotação: {exc}"
        return out

    # Sinal de "concluir a tarefa" quando o protocolo finaliza
    if novo_status in STATUS_PROTOCOLO_OK:
        out["finalizou"] = True

    return out


def _anotar_criacao_modo_rapido(emp_id, proto_rdm_id, numero, tipo,
                                status="Em análise"):
    """MODO RÁPIDO: se a empresa tem UMA tarefa GESTTA pendente sem
    protocolo, vincula ao protocolo recém-criado e anota a criação.
    Reusa _replicar_status_no_gestta pro post em si."""
    out = {"ok": False, "mensagem": ""}
    if not proto_rdm_id or not emp_id:
        out["mensagem"] = "Sem protocolo/empresa pra vincular"
        return out
    try:
        from database import get_conn as _gc
        with _gc() as conn:
            rows = conn.execute(
                "SELECT id FROM tarefas_gestta WHERE empresa_id = ? "
                "AND resolvida = 0 AND gestta_id IS NOT NULL "
                "AND protocolo_id IS NULL ORDER BY id DESC",
                (emp_id,),
            ).fetchall()
        cand = [dict(r) for r in rows]
    except Exception as exc:
        out["mensagem"] = f"Erro buscando tarefa GESTTA: {exc}"
        return out
    if not cand:
        out["mensagem"] = "Empresa sem tarefa GESTTA pendente — nada a anotar"
        return out
    if len(cand) > 1:
        out["mensagem"] = (
            f"{len(cand)} tarefas GESTTA pra esta empresa — "
            "vincule manualmente pra anotar"
        )
        return out
    tarefa_id = cand[0]["id"]
    try:
        from database import get_conn as _gc2
        with _gc2() as conn:
            conn.execute(
                "UPDATE tarefas_gestta SET protocolo_id = ? WHERE id = ?",
                (proto_rdm_id, tarefa_id),
            )
    except Exception as exc:
        out["mensagem"] = f"Erro vinculando tarefa: {exc}"
        return out
    return _replicar_status_no_gestta(
        {"id": proto_rdm_id, "numero_protocolo": numero, "tipo": tipo},
        status or "Em análise",
        observacoes="Protocolo criado via MODO RÁPIDO (Cartão CNPJ).",
    )


def _postar_anotacao_gestta(protocolo_id, texto, autor):
    """Posta uma anotação livre no chat da tarefa GESTTA vinculada."""
    out = {"ok": False, "mensagem": ""}
    try:
        from database import get_conn as _gc
        with _gc() as conn:
            r = conn.execute(
                "SELECT gestta_id FROM tarefas_gestta WHERE protocolo_id = ? "
                "AND resolvida = 0 AND gestta_id IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (protocolo_id,),
            ).fetchone()
        gid = dict(r).get("gestta_id") if r else None
    except Exception as exc:
        out["mensagem"] = f"GESTTA: erro buscando tarefa ({exc})"
        return out
    if not gid:
        out["mensagem"] = "Sem tarefa GESTTA vinculada — salvo só no sistema"
        return out
    from auth import usuario_atual as _u_at
    _u = _u_at() or {}
    jwt = obter_jwt_gestta_efetivo(_u.get("email"))
    if not jwt:
        out["mensagem"] = "Sem JWT GESTTA — salvo só no sistema"
        return out
    texto_g = f"[REDESIM Manager] 🗒️ Anotação: {texto}\n\n— {autor}"
    try:
        from utils.gestta_api import GesttaClient
        GesttaClient(jwt).adicionar_comentario_tarefa(gid, texto_g, external=False)
        out["ok"] = True
        out["mensagem"] = "Anotação enviada ao GESTTA ✅"
    except Exception as exc:
        out["mensagem"] = f"Falha GESTTA: {exc}"
    return out


def _bloco_anotacoes_protocolo(protocolo_id, *, key_prefix=""):
    """Histórico de anotações + form. Ao adicionar, grava e (se vinculado
    a tarefa GESTTA) posta no chat."""
    kp = f"{key_prefix}_{protocolo_id}"
    try:
        anots = listar_anotacoes_protocolo(protocolo_id)
    except Exception as exc:
        anots = []
        st.caption(f"Erro lendo anotações: {exc}")
    if anots:
        for a in anots:
            quando = (str(a.get("criado_em") or ""))[:16]
            autor_a = a.get("autor") or "—"
            st.markdown(f"**{quando}** · _{autor_a}_")
            st.markdown(a.get("texto") or "")
            st.divider()
    else:
        st.caption("Nenhuma anotação ainda.")
    txt = st.text_area(
        "Nova anotação (o que foi feito)",
        key=f"anot_txt_{kp}",
        placeholder="Ex.: Protocolo enviado na prefeitura, aguardando análise.",
    )
    manda_g = st.checkbox(
        "Postar também no GESTTA", value=True, key=f"anot_g_{kp}",
    )
    if st.button("➕ Adicionar anotação", key=f"anot_add_{kp}", type="primary"):
        if not (txt or "").strip():
            st.warning("Escreva a anotação primeiro.")
        else:
            from auth import usuario_atual as _u_at
            _u = _u_at() or {}
            autor = _u.get("nome") or _u.get("email") or "Equipe CSM"
            try:
                criar_anotacao_protocolo(protocolo_id, txt.strip(), autor)
            except Exception as exc:
                st.error(f"Falha ao salvar: {exc}")
                return
            extra = ""
            if manda_g:
                try:
                    extra = _postar_anotacao_gestta(
                        protocolo_id, txt.strip(), autor,
                    ).get("mensagem", "")
                except Exception as exc:
                    extra = f"GESTTA: {exc}"
            st.success("Anotação salva. " + (extra or ""))
            st.rerun()


def atualizar_status_protocolo_com_gestta(
    protocolo_id: int, novo_status: str,
    observacoes: str | None = None,
) -> tuple[dict | None, dict]:
    """Atualiza status no banco + replica anotação no GESTTA do
    usuário logado + cria cobrança DOMÍNIO pendente se terminal.
    Retorna (protocolo_atualizado, info_replicacao). A info pode ter
    'cobranca_criada_id' (int) se uma cobrança foi gerada.
    """
    from database import (
        STATUS_PROTOCOLO_OK,
        _classificar_tipo_cobranca,
        criar_cobranca_pendente,
        garantir_valores_cobranca_padrao,
    )
    from auth import usuario_atual as _u_at

    atualizado = atualizar_status_protocolo(
        protocolo_id, novo_status, observacoes=observacoes,
    )
    info = {"ok": False}
    if atualizado:
        try:
            info = _replicar_status_no_gestta(
                atualizado, novo_status, observacoes,
            )
        except Exception as exc:
            info = {"ok": False, "mensagem": str(exc)}

        # GANCHO COBRANÇA DOMÍNIO: dispara SÓ no fim da jornada — quando
        # o CLI é emitido (Licenciamento Concluído), NÃO na viabilidade.
        # Regra do Eduardo: "só cobro depois que sair o CLI / documento
        # final, tanto vigilância sanitária quanto licença de
        # funcionamento."
        tipo_prot = (atualizado.get("tipo") or "").upper()
        # Considera "fim de jornada" se:
        #   - Status virou Concluída (CLI emitido — licenciamento)
        #   - Tipo é "Licenciamento" OU tarefa GESTTA cita VISA/Sanit
        # Status "Aprovada" sozinho (viabilidade) NÃO dispara cobrança.
        is_cli_emitido = (
            novo_status == "Concluída"
            and ("LICENCIAMENTO" in tipo_prot or "LICENÇA" in tipo_prot
                 or "LICENCA" in tipo_prot)
        )
        # Pra VISA, qualquer status "Aprovada" ou "Concluída" no protocolo
        # de licenciamento sanitário também dispara
        tarefa_gestta = info.get("tarefa") or {}
        nome_tarefa = (tarefa_gestta.get("tarefa_nome") or "").upper()
        is_visa_emitida = (
            novo_status in ("Aprovada", "Concluída")
            and ("SANIT" in nome_tarefa or "VISA" in nome_tarefa
                 or "VIGILANCIA" in nome_tarefa)
        )

        if is_cli_emitido or is_visa_emitida:
            try:
                garantir_valores_cobranca_padrao()
                tipo_cob = _classificar_tipo_cobranca(
                    atualizado,
                    tarefa_gestta.get("tarefa_nome"),
                )
                _u = _u_at() or {}
                cob_id = criar_cobranca_pendente(
                    cliente_nome=atualizado.get("razao_social", "—"),
                    cliente_cnpj=atualizado.get("cnpj"),
                    empresa_id=atualizado.get("empresa_id"),
                    protocolo_id=atualizado.get("id"),
                    gestta_task_id=tarefa_gestta.get("gestta_id"),
                    tipo_servico=tipo_cob,
                    descricao=(
                        f"CLI emitido — Protocolo "
                        f"{atualizado.get('numero_protocolo', '?')} "
                        f"({atualizado.get('tipo', '?')})"
                    ),
                    responsavel=(
                        _u.get("nome") or _u.get("email") or
                        atualizado.get("responsavel")
                    ),
                )
                info["cobranca_criada_id"] = cob_id
                info["cobranca_tipo"] = tipo_cob
            except Exception as exc:
                info["cobranca_erro"] = str(exc)
        elif novo_status == "Aprovada":
            # Viabilidade aprovada: NÃO cria cobrança, mas avisa
            # que o próximo passo é o licenciamento
            info["proximo_passo"] = (
                "viabilidade_aprovada_seguir_licenciamento"
            )

    return atualizado, info


def _mostrar_feedback_gestta(info: dict, novo_status: str):
    """Mostra mensagem de sucesso/aviso após replicar pro GESTTA."""
    if info.get("ok"):
        st.info(f"📝 {info.get('mensagem', 'Anotação enviada')}")
        if info.get("finalizou"):
            tarefa = info.get("tarefa") or {}
            st.warning(
                f"✋ **PRÓXIMO PASSO:** Conclua manualmente a tarefa "
                f"**{tarefa.get('tarefa_nome', '—')}** "
                f"no GESTTA. A anotação já foi postada lá. "
                f"[Abrir GESTTA](https://app.gestta.com.br)"
            )
    elif info.get("mensagem"):
        # Avisa o motivo, mas não bloqueia o fluxo
        pass

    # Feedback de cobrança automática (só quando CLI emitido)
    if info.get("cobranca_criada_id"):
        tipo_cob = info.get("cobranca_tipo", "OUTRO")
        from database import VALORES_COBRANCA_PADRAO
        _, valor_def = VALORES_COBRANCA_PADRAO.get(tipo_cob, ("", 0))
        st.success(
            f"💰 **COBRANÇA DOMÍNIO criada — CLI emitido** "
            f"(R$ {valor_def:.2f}). Lembrete vai pro seu Telegram. "
            f"Veja em **💰 Cobranças DOMÍNIO** no menu."
        )
    if info.get("cobranca_erro"):
        st.caption(f"⚠️ Falha ao criar cobrança: {info['cobranca_erro']}")
    # Quando viabilidade aprovada, orientação pro próximo passo
    if info.get("proximo_passo") == "viabilidade_aprovada_seguir_licenciamento":
        st.info(
            "➡️ **Viabilidade aprovada!** Próximo passo: vá no "
            "Facilita-SP em **Licenciamento**, digite só o CNPJ e ele "
            "vai reaproveitar este mesmo protocolo. A cobrança DOMÍNIO "
            "será criada automaticamente apenas quando o CLI for "
            "emitido."
        )
    if info.get("mensagem") and not info.get("ok"):
        st.caption(f"ℹ️ GESTTA: {info['mensagem']}")


# Habilita o corretor ortográfico do navegador (em pt-BR) em todos os
# campos de texto e textareas. O Streamlit não seta `spellcheck` por
# padrão, então injetamos um pequeno script com MutationObserver que
# percorre os widgets re-renderizados e força os atributos.
import streamlit.components.v1 as _components
_components.html(
    """
    <script>
      (function () {
        const root = window.parent ? window.parent.document : document;
        function aplicar() {
          root.querySelectorAll(
            'textarea, input[type="text"], input:not([type])'
          ).forEach(function (el) {
            el.setAttribute('spellcheck', 'true');
            el.setAttribute('lang', 'pt-BR');
            el.setAttribute('autocapitalize', 'sentences');
          });
          // Garante que o <html> tem lang pt-BR p/ usar o dicionário brasileiro
          if (root.documentElement && root.documentElement.lang !== 'pt-BR') {
            root.documentElement.lang = 'pt-BR';
          }
        }
        aplicar();
        try {
          new MutationObserver(aplicar).observe(root.body, {
            childList: true, subtree: true,
          });
        } catch (e) {}
      })();
    </script>
    """,
    height=0,
)

# ---------------------------------------------------------
# SIDEBAR — Navegação + Status de configuração
# ---------------------------------------------------------
st.sidebar.markdown(
    "<div style='display:flex; align-items:center; gap:10px; "
    "margin-bottom:6px;'>"
    "<div style='background:#1F4FD3; color:#FFF; width:34px; height:34px; "
    "border-radius:8px; text-align:center; line-height:34px; "
    "font-weight:600; font-size:16px;'>R</div>"
    "<div style='font-weight:600; font-size:16px; color:#1A2A4A;'>"
    "REDESIM Manager</div>"
    "</div>",
    unsafe_allow_html=True,
)
_horarios_str = HORARIO_LEMBRETE.replace(",", " e ")
st.sidebar.caption(
    f"🟡 {DIAS_AMARELO}d · 🔴 {DIAS_VERMELHO}d · "
    f"Lembrete diário às {_horarios_str}"
)

# Lista de páginas (source of truth)
PAGINAS_LIST = [
    "📊 Dashboard/Kanban",
    "📋 Fila do dia",
    "➕ Novo Processo",
    "📄 Documentos",
    "🏢 Empresas / REDESIM",
    "📋 Tarefas GESTTA",
    "📋 Licenças / Renovações",
    "📌 Pendências Gerais",
    "💰 Cobranças DOMÍNIO",
    "🔬 Consultor de CNAE",
    "🏷️ Classificador CNAE",
    "📋 Matriz de Risco CNAE",
    "🏥 Portaria CVS-SP (Vigilância)",
    "🚒 Matriz IT-01 Bombeiros",
    "📥 Atualizar Normas",
    "📲 Configurar Telegram",
    "⏰ Lembretes / Testes",
    "⚙️ Configurações",
]

# Source of truth da página atual (independente do widget)
if "pagina_atual" not in st.session_state:
    st.session_state["pagina_atual"] = PAGINAS_LIST[0]

# Navegação cruzada — quando o Dashboard pediu pra abrir outra página,
# atualizamos a fonte da verdade ANTES do widget renderizar. Como
# `pagina_atual` não é a key do widget, o Streamlit aceita.
if "nav_target" in st.session_state:
    target = st.session_state.pop("nav_target")
    if target in PAGINAS_LIST:
        st.session_state["pagina_atual"] = target

# Callback que mantém pagina_atual sincronizada com o radio
def _radio_changed():
    val = st.session_state.get("_sidebar_radio_widget")
    if val and val in PAGINAS_LIST:
        st.session_state["pagina_atual"] = val

# Index inicial = posição da pagina_atual na lista
_idx = PAGINAS_LIST.index(st.session_state["pagina_atual"])

st.sidebar.radio(
    "Navegação",
    PAGINAS_LIST,
    index=_idx,
    key="_sidebar_radio_widget",
    on_change=_radio_changed,
)
pagina = st.session_state["pagina_atual"]


def _navegar_para(pagina_nome: str, **focus) -> None:
    """Helper para botões de cross-link do Dashboard.
    Atualiza nav_target + chaves focus_* e força rerun. No próximo run,
    a navegação é aplicada via `pagina_atual`.
    """
    st.session_state["nav_target"] = pagina_nome
    for k, v in focus.items():
        if v is not None:
            st.session_state[k] = v
    st.toast(f"Abrindo {pagina_nome}…", icon="🔗")
    st.rerun()
st.sidebar.caption(
    "📄 **Documentos** é o ponto único para subir AVCBs, alvarás, CNDs etc. "
    "As páginas 🏥 CVS-SP e 🚒 IT-01 são só para consulta e atualização "
    "das portarias/normas de referência."
)

# Botão de recarregar — útil após atualização do código
st.sidebar.markdown("---")
if st.sidebar.button("🔄 Recarregar app", width="stretch",
                     help="Aperte aqui depois de qualquer atualização do "
                          "Claude. Limpa cache e recarrega a tela."):
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    st.rerun()
st.sidebar.caption("Aperte **R** no teclado também recarrega.")

# Indicadores de canal
st.sidebar.markdown("---")
st.sidebar.markdown("**Canais de notificação:**")
st.sidebar.write(
    ("✅ Telegram" if telegram_configurado() else "⚪ Telegram (não configurado)")
)
st.sidebar.write(
    ("✅ SMS/Twilio" if twilio_configurado() else "⚪ SMS (opcional)")
)

# Alerta de normas desatualizadas no sidebar
try:
    _normas_status = status_normas(limite_dias=180)
    _desatualizadas = [s for s in _normas_status
                       if s["status"] in ("atrasado", "nunca")]
    if _desatualizadas:
        st.sidebar.markdown("---")
        st.sidebar.warning(
            f"⚠️ {len(_desatualizadas)} norma(s) desatualizada(s). "
            "Acesse **📥 Atualizar Normas**."
        )
except Exception:
    pass


# ---------------------------------------------------------
# PÁGINA 1 — DASHBOARD / KANBAN
# ---------------------------------------------------------
def _kpi_card_html(icon: str, label: str, valor, sub: str | None,
                   accent: str, bg_from: str, bg_to: str,
                   border: str) -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
      <div class="kpi-card" style="
        --bg-from: {bg_from};
        --bg-to: {bg_to};
        --border-c: {border};
        --accent-c: {accent};">
        <div class="kpi-icon">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value accent">{valor}</div>
        {sub_html}
      </div>
    """


def _mini_card_html(icon: str, label: str, valor: int,
                    crit: int = 0, warn: int = 0) -> str:
    if crit > 0:
        cls = "mini-card crit"
        sub = f"🔴 {crit} crítico"
    elif warn > 0:
        cls = "mini-card warn"
        sub = f"🟡 {warn} alerta"
    else:
        cls = "mini-card"
        sub = "🟢 tudo no prazo"
    return f"""
      <div class="{cls}">
        <div class="mc-icon">{icon}</div>
        <div class="mc-label">{label}</div>
        <div class="mc-value">{valor}</div>
        <div class="mc-sub">{sub}</div>
      </div>
    """


def _health_bar_html(r: int, y: int, g: int) -> str:
    total = max(r + y + g, 1)
    pr = round(r * 100 / total, 1)
    py = round(y * 100 / total, 1)
    pg = round(g * 100 / total, 1)
    return f"""
      <div class="health-bar">
        <div class="health-r" style="width:{pr}%"></div>
        <div class="health-y" style="width:{py}%"></div>
        <div class="health-g" style="width:{pg}%"></div>
      </div>
      <div class="health-legend">
        <span>🔴 {r} crítico ({pr:.0f}%)</span>
        <span>🟡 {y} alerta ({py:.0f}%)</span>
        <span>🟢 {g} ok ({pg:.0f}%)</span>
      </div>
    """


def _resumo_consolidado_dashboard():
    """Header visual do dashboard: KPI cards + barra de saúde global."""
    # Coleta dados (cache de 30s — aceitável pro KPI)
    pends = _cache_pendencias_abertas()
    pend_r = sum(1 for p in pends if p["alerta"] == "🔴")
    pend_y = sum(1 for p in pends if p["alerta"] == "🟡")
    pend_g = sum(1 for p in pends if p["alerta"] == "🟢")

    todos_prot = listar_todos_protocolos()
    em_and_prot = [p for p in todos_prot
                   if p["status"] not in (STATUS_PROTOCOLO_OK | STATUS_PROTOCOLO_PROBLEMA)
                   and not p.get("substituido_por_id")]
    from datetime import datetime as _dt
    hoje_dt = _dt.now()
    prot_r = prot_y = prot_g = 0
    for p in em_and_prot:
        ds = p.get("data_solicitacao")
        if not ds:
            prot_g += 1
            continue
        try:
            d = (hoje_dt - _dt.strptime(ds, "%Y-%m-%d")).days
            if d >= DIAS_VERMELHO:
                prot_r += 1
            elif d >= DIAS_AMARELO:
                prot_y += 1
            else:
                prot_g += 1
        except ValueError:
            prot_g += 1

    try:
        docs = documentos_proximos_vencimento()
    except Exception:
        docs = []
    doc_r = sum(1 for d in docs
                if (d.get("dias_para_vencer") or 0) < 0)
    doc_y = sum(1 for d in docs
                if 0 <= (d.get("dias_para_vencer") or 999) <= 15)
    doc_g = max(len(docs) - doc_r - doc_y, 0)

    try:
        avcbs = alvaras_vencendo(dias=60)
    except Exception:
        avcbs = []
    avcb_r = sum(1 for a in avcbs if (a.get("dias_para_vencer") or 0) < 0)
    avcb_y = sum(1 for a in avcbs
                 if 0 <= (a.get("dias_para_vencer") or 999) <= 30)
    avcb_g = max(len(avcbs) - avcb_r - avcb_y, 0)

    try:
        gestta_stats = estatisticas_tarefas_gestta()
        gestta_pend = gestta_stats["total_pendentes"]
        g_alto = gestta_stats["por_risco"].get("ALTO", 0)
        g_medio = gestta_stats["por_risco"].get("MÉDIO", 0)
        g_baixo = gestta_stats["por_risco"].get("BAIXO", 0)
    except Exception:
        gestta_pend = g_alto = g_medio = g_baixo = 0

    try:
        procs_at = processos_atrasados(DIAS_AMARELO)
    except Exception:
        procs_at = []
    proc_r = sum(1 for p in procs_at if p["dias_parado"] >= DIAS_VERMELHO)
    proc_y = sum(1 for p in procs_at if DIAS_AMARELO <= p["dias_parado"] < DIAS_VERMELHO)

    total_itens = (len(pends) + len(em_and_prot) + len(docs) + len(avcbs)
                   + gestta_pend + len(procs_at))
    if total_itens == 0:
        return

    total_r = pend_r + prot_r + doc_r + avcb_r + g_alto + proc_r
    total_y = pend_y + prot_y + doc_y + avcb_y + g_medio + proc_y
    total_g = pend_g + prot_g + doc_g + avcb_g + g_baixo

    # Linha 1: 4 KPI cards grandes
    st.markdown("#### 🎯 Visão geral")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_kpi_card_html(
            "", "Crítico", total_r,
            "prazo vencido ou estourado",
            accent="#DC2626", bg_from="#FFFFFF", bg_to="#FFFFFF",
            border="#DC2626",
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi_card_html(
            "", "Em alerta", total_y,
            "perto do limite",
            accent="#D97706", bg_from="#FFFFFF", bg_to="#FFFFFF",
            border="#D97706",
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(_kpi_card_html(
            "", "No prazo", total_g,
            "dentro do prazo",
            accent="#047857", bg_from="#FFFFFF", bg_to="#FFFFFF",
            border="#047857",
        ), unsafe_allow_html=True)
    with c4:
        st.markdown(_kpi_card_html(
            "", "Total aberto", total_itens,
            "fontes monitoradas: 6",
            accent="#1F4FD3", bg_from="#FFFFFF", bg_to="#FFFFFF",
            border="#1F4FD3",
        ), unsafe_allow_html=True)

    # Linha 2: barra de saúde + 6 mini-cards por categoria
    st.markdown("")
    with st.container(border=True):
        st.markdown(
            "<div class='bloco-header'>📈 Saúde geral do escritório</div>",
            unsafe_allow_html=True,
        )
        st.markdown(_health_bar_html(total_r, total_y, total_g),
                    unsafe_allow_html=True)
        st.markdown("")
        cols = st.columns(6)
        especs = [
            ("📌", "Pendências", len(pends), pend_r, pend_y),
            ("📜", "Protocolos", len(em_and_prot), prot_r, prot_y),
            ("📄", "Documentos", len(docs), doc_r, doc_y),
            ("🚒", "Bombeiros", len(avcbs), avcb_r, avcb_y),
            ("📋", "GESTTA", gestta_pend, g_alto, g_medio),
            ("🔄", "Processos", len(procs_at), proc_r, proc_y),
        ]
        for col, (ic, lab, total_i, ri, yi) in zip(cols, especs):
            col.markdown(
                _mini_card_html(ic, lab, total_i, crit=ri, warn=yi),
                unsafe_allow_html=True,
            )

    # Linha 3: GRÁFICOS (donut + barras horizontais)
    st.markdown("")
    import altair as alt

    g_col1, g_col2 = st.columns(2)

    # ---- Gráfico 1: Donut de saúde geral ----
    with g_col1:
        st.markdown("##### 🍩 Saúde geral (todos os itens)")
        df_donut = pd.DataFrame([
            {"Status": "🔴 Crítico", "Qtd": total_r, "ord": 0},
            {"Status": "🟡 Em alerta", "Qtd": total_y, "ord": 1},
            {"Status": "🟢 Tudo ok", "Qtd": total_g, "ord": 2},
        ])
        df_donut = df_donut[df_donut["Qtd"] > 0]
        if not df_donut.empty:
            cor_scale = alt.Scale(
                domain=["🔴 Crítico", "🟡 Em alerta", "🟢 Tudo ok"],
                range=["#DC2626", "#D97706", "#047857"],
            )
            donut = (
                alt.Chart(df_donut)
                .mark_arc(innerRadius=60, outerRadius=110, stroke="#fff",
                          strokeWidth=2)
                .encode(
                    theta=alt.Theta("Qtd:Q", stack=True),
                    color=alt.Color(
                        "Status:N", scale=cor_scale,
                        legend=alt.Legend(
                            title=None, orient="bottom",
                            labelFontSize=14, labelFontWeight="bold",
                            symbolSize=180,
                        ),
                    ),
                    order=alt.Order("ord:Q"),
                    tooltip=["Status", "Qtd"],
                )
                .properties(height=300)
            )
            # Texto central com total — preto sólido (sem mais "vazado")
            total_txt = alt.Chart(pd.DataFrame({"v": [total_itens]})).mark_text(
                fontSize=42, fontWeight="bold", color="#000000",
            ).encode(text="v:Q")
            sub_txt = alt.Chart(pd.DataFrame({"v": ["itens abertos"]})).mark_text(
                fontSize=14, fontWeight="bold", color="#000000", dy=28,
            ).encode(text="v:N")
            st.altair_chart(donut + total_txt + sub_txt, width="stretch")
        else:
            st.info("Sem itens abertos.")

    # ---- Gráfico 2: Barras horizontais por categoria ----
    with g_col2:
        st.markdown("##### 📊 Itens por categoria")
        df_bar = pd.DataFrame([
            {"Categoria": "📌 Pendências",   "Crítico": pend_r, "Alerta": pend_y, "OK": pend_g},
            {"Categoria": "📜 Protocolos",   "Crítico": prot_r, "Alerta": prot_y, "OK": prot_g},
            {"Categoria": "📄 Documentos",   "Crítico": doc_r,  "Alerta": doc_y,  "OK": doc_g},
            {"Categoria": "🚒 Bombeiros",    "Crítico": avcb_r, "Alerta": avcb_y, "OK": avcb_g},
            {"Categoria": "📋 GESTTA",        "Crítico": g_alto, "Alerta": g_medio,"OK": g_baixo},
            {"Categoria": "🔄 Processos",     "Crítico": proc_r, "Alerta": proc_y, "OK": 0},
        ])
        df_long = df_bar.melt(id_vars="Categoria",
                              value_vars=["Crítico", "Alerta", "OK"],
                              var_name="Status", value_name="Qtd")
        cor_scale_b = alt.Scale(
            domain=["Crítico", "Alerta", "OK"],
            range=["#DC2626", "#D97706", "#047857"],
        )
        bar = (
            alt.Chart(df_long)
            .mark_bar(stroke="#FFFFFF", strokeWidth=1)
            .encode(
                y=alt.Y(
                    "Categoria:N", sort="-x",
                    axis=alt.Axis(
                        title=None,
                        labelFontSize=15,
                        labelFontWeight="bold",
                        labelLimit=200,
                        labelPadding=8,
                    ),
                ),
                x=alt.X(
                    "Qtd:Q", stack="zero",
                    axis=alt.Axis(
                        title=None,
                        labelFontSize=13,
                        labelFontWeight="normal",
                        tickCount=8,
                    ),
                ),
                color=alt.Color(
                    "Status:N", scale=cor_scale_b,
                    legend=alt.Legend(
                        title=None, orient="bottom",
                        labelFontSize=14, labelFontWeight="bold",
                        symbolSize=180,
                    ),
                ),
                order=alt.Order("Status:N", sort="ascending"),
                tooltip=["Categoria", "Status", "Qtd"],
            )
            .properties(height=320)
        )
        st.altair_chart(bar, width="stretch")


def _bloco_pendencias_dashboard():
    """Bloco de pendências gerais com filtros e ações inline."""
    stats_p = estatisticas_pendencias()
    pendencias_todas = listar_pendencias(apenas_abertas=True)
    if stats_p["abertas"] == 0:
        return

    with st.container(border=True):
        st.markdown(
            "<div class='bloco-header'>📌 Pendências Gerais</div>",
            unsafe_allow_html=True,
        )
        # Barra de saúde do bloco
        _r = sum(1 for p in pendencias_todas if p["alerta"] == "🔴")
        _y = sum(1 for p in pendencias_todas if p["alerta"] == "🟡")
        _g = sum(1 for p in pendencias_todas if p["alerta"] == "🟢")
        st.markdown(_health_bar_html(_r, _y, _g), unsafe_allow_html=True)

        # Filtros
        with st.expander("🔎 Filtros", expanded=False):
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                f_alerta = st.multiselect(
                    "Alerta",
                    ["🔴", "🟡", "🟢"],
                    default=["🔴", "🟡", "🟢"],
                    key="pend_dash_alerta",
                )
            with f2:
                f_prio = st.multiselect(
                    "Prioridade",
                    PRIORIDADES_PENDENCIA,
                    default=PRIORIDADES_PENDENCIA,
                    key="pend_dash_prio",
                )
            with f3:
                stats_abertos = sorted({p["status"] for p in pendencias_todas})
                f_status = st.multiselect(
                    "Status",
                    stats_abertos,
                    default=stats_abertos,
                    key="pend_dash_stat",
                )
            with f4:
                empresas_disp = sorted({p["razao_social"] for p in pendencias_todas
                                        if p.get("razao_social")})
                f_emp = st.selectbox(
                    "Empresa/Cliente",
                    ["Todas"] + empresas_disp,
                    key="pend_dash_emp",
                )

        # Aplica filtros
        filtradas = [
            p for p in pendencias_todas
            if p["alerta"] in f_alerta
            and p["prioridade"] in f_prio
            and p["status"] in f_status
            and (f_emp == "Todas" or p["razao_social"] == f_emp)
        ]
        # ordena: vermelho > amarelo > verde
        ordem = {"🔴": 0, "🟡": 1, "🟢": 2}
        filtradas.sort(key=lambda p: (ordem.get(p["alerta"], 9),
                                       PRIORIDADES_PENDENCIA.index(p["prioridade"])
                                       if p["prioridade"] in PRIORIDADES_PENDENCIA else 9))

        # Métricas (baseadas no filtro)
        cp1, cp2, cp3, cp4 = st.columns(4)
        cp1.metric("Filtradas", len(filtradas))
        cp2.metric("🔴 Vencidas",
                   sum(1 for p in filtradas if p["alerta"] == "🔴"))
        cp3.metric("🟡 Paradas",
                   sum(1 for p in filtradas if p["alerta"] == "🟡"))
        cp4.metric("🟢 No prazo",
                   sum(1 for p in filtradas if p["alerta"] == "🟢"))

        if filtradas:
            df_p = pd.DataFrame([{
                "": p["alerta"],
                "Empresa/Cliente": p["razao_social"],
                "Assunto": p["assunto"],
                "Prio.": p["prioridade"],
                "Status": p["status"],
                "Parada": f"{p['dias_parado']}d",
                "Prazo": (
                    f"venceu há {abs(p['dias_para_prazo'])}d"
                    if p["dias_para_prazo"] is not None and p["dias_para_prazo"] < 0
                    else (f"{p['dias_para_prazo']}d"
                          if p["dias_para_prazo"] is not None else "—")
                ),
            } for p in filtradas])
            sel = st.dataframe(
                df_p, width="stretch", hide_index=True,
                on_select="rerun", selection_mode="single-row",
                key="pend_dash_df",
            )
            if sel and getattr(sel, "selection", None) and sel.selection.rows:
                idx = sel.selection.rows[0]
                p_sel = filtradas[idx]
                with st.container(border=True):
                    st.markdown(
                        f"**Selecionado:** {p_sel['alerta']} "
                        f"_{p_sel['assunto']}_ — {p_sel['razao_social']}"
                    )
                    a1, a2, a3, a4 = st.columns(4)
                    with a1:
                        nota = st.text_input(
                            "Nova nota (opcional)",
                            key=f"pend_dash_nota_{p_sel['id']}",
                            placeholder="ex.: liguei na Receita",
                        )
                    with a2:
                        if st.button("💬 Adicionar nota",
                                     key=f"pend_dash_addnota_{p_sel['id']}",
                                     width="stretch"):
                            if nota.strip():
                                adicionar_movimento_pendencia(
                                    p_sel["id"], nota, tipo="nota",
                                )
                                st.toast("Nota registrada — contador resetado.")
                                st.rerun()
                            else:
                                st.warning("Escreva a nota antes.")
                    with a3:
                        if st.button("✅ Resolver",
                                     key=f"pend_dash_resolv_{p_sel['id']}",
                                     width="stretch",
                                     type="primary"):
                            resolver_pendencia(p_sel["id"])
                            st.toast("Pendência resolvida — saiu do dashboard.")
                            st.rerun()
                    with a4:
                        if st.button("🗑 Excluir",
                                     key=f"pend_dash_del_{p_sel['id']}",
                                     width="stretch"):
                            excluir_pendencia(p_sel["id"])
                            st.toast("Pendência excluída.")
                            st.rerun()

                    if st.button(
                        "📂 Abrir essa pendência na página completa →",
                        key=f"pend_dash_navigate_{p_sel['id']}",
                        width="stretch",
                    ):
                        _navegar_para(
                            "📌 Pendências Gerais",
                            focus_pendencia_id=p_sel["id"],
                        )
        else:
            st.info("Nenhuma pendência com esses filtros.")
        st.caption(
            "🔴 prazo vencido · 🟡 parada (sem nota há > N dias) · 🟢 ok. "
            "**Clique em uma linha** para ver ações rápidas. Detalhes "
            "completos em **📌 Pendências Gerais** no menu."
        )


def _bloco_protocolos_redesim_dashboard():
    """Pipeline Viabilidade → Licenciamento com botões de ação direta."""
    from datetime import datetime as _dt
    todos = listar_todos_protocolos()

    via_andamento = [p for p in todos
                     if p["tipo"] == TIPO_PROTOCOLO_VIABILIDADE
                     and p["status"] not in (STATUS_PROTOCOLO_OK | STATUS_PROTOCOLO_PROBLEMA)
                     and p["status"] != "Aguardando Reconsideração"
                     and not p.get("substituido_por_id")]
    via_reconsideracao = [p for p in todos
                          if p["tipo"] == TIPO_PROTOCOLO_VIABILIDADE
                          and p["status"] == "Aguardando Reconsideração"
                          and not p.get("substituido_por_id")]
    numeros_com_lic = {p["numero_protocolo"] for p in todos
                     if p["tipo"] == TIPO_PROTOCOLO_LICENCIAMENTO}
    via_aprovadas = [p for p in todos
                     if p["tipo"] == TIPO_PROTOCOLO_VIABILIDADE
                     and p["status"] == "Aprovada"
                     and p["numero_protocolo"] not in numeros_com_lic
                     and not p.get("substituido_por_id")]
    lic_andamento = [p for p in todos
                     if p["tipo"] == TIPO_PROTOCOLO_LICENCIAMENTO
                     and p["status"] not in (STATUS_PROTOCOLO_OK | STATUS_PROTOCOLO_PROBLEMA)
                     and not p.get("substituido_por_id")]

    todos_ativos = via_andamento + via_aprovadas + via_reconsideracao + lic_andamento
    if not todos_ativos:
        return

    hoje = _dt.now()

    def _dias(p):
        ds = p.get("data_solicitacao")
        if not ds:
            return 0
        try:
            return (hoje - _dt.strptime(ds, "%Y-%m-%d")).days
        except Exception:
            return 0

    def _cor(dias):
        if dias >= DIAS_VERMELHO:
            return "🔴"
        if dias >= DIAS_AMARELO:
            return "🟡"
        return "🟢"

    with st.container(border=True):
        st.markdown(
            "<div class='bloco-header'>📜 Protocolos REDESIM em andamento</div>",
            unsafe_allow_html=True,
        )
        all_dias = [_dias(p) for p in todos_ativos]
        _r = sum(1 for d in all_dias if d >= DIAS_VERMELHO)
        _y = sum(1 for d in all_dias if DIAS_AMARELO <= d < DIAS_VERMELHO)
        _g = sum(1 for d in all_dias if d < DIAS_AMARELO)
        st.markdown(_health_bar_html(_r, _y, _g), unsafe_allow_html=True)

        col_via, col_arrow, col_lic = st.columns([5, 1, 5])

        with col_via:
            st.markdown("#### 📋 Etapa 1 — Viabilidade")
            st.caption(
                f"{len(via_andamento)} em análise · "
                f"{len(via_aprovadas)} aprovada(s) · "
                f"{len(via_reconsideracao)} aguardando reconsideração"
            )
            for p in via_andamento + via_aprovadas:
                dias = _dias(p)
                cor = _cor(dias)
                razao = p.get("razao_social", "?")
                with st.container(border=True):
                    ca, cb = st.columns([3, 1])
                    with ca:
                        st.markdown(f"{cor} **{razao}**")
                        st.caption(
                            f"`{p['numero_protocolo']}` · {p['status']} · {dias}d"
                        )
                    with cb:
                        st.caption(p.get("data_solicitacao") or "—")

                    with st.expander("🗒️ Anotações do que foi feito"):
                        _bloco_anotacoes_protocolo(p["id"], key_prefix="dash")
                    if p["status"] == "Aprovada":
                        st.success("✅ Viabilidade deferida — pronto para Licenciamento")
                        if st.button(
                            "▶️ Iniciar Licenciamento",
                            key=f"ini_lic_{p['id']}",
                            width="stretch",
                            type="primary",
                        ):
                            lic_dup = next((x for x in todos if x["tipo"] == TIPO_PROTOCOLO_LICENCIAMENTO and x["numero_protocolo"] == p["numero_protocolo"]), None)
                            if lic_dup:
                                st.warning(f"Licenciamento já existe (status: {lic_dup['status']}). Veja na Etapa 2.")
                            else:
                                novo_id = criar_protocolo_redesim(
                                    empresa_id=p["empresa_id"],
                                    tipo=TIPO_PROTOCOLO_LICENCIAMENTO,
                                    numero_protocolo=p["numero_protocolo"],
                                    data_solicitacao=p.get("data_solicitacao"),
                                    status="Em análise",
                                    observacoes=(
                                        "Licenciamento iniciado após viabilidade aprovada.\n"
                                        "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                    ),
                                )
                                st.toast(f"Licenciamento registrado (ID {novo_id}).")
                            _invalidar_cache_db()
                            import time as _t
                            _t.sleep(0.8)
                            st.rerun()
                    else:
                        b1, b2, b3 = st.columns(3)
                        with b1:
                            if st.button(
                                "✅ Deferida",
                                key=f"def_{p['id']}",
                                width="stretch",
                                type="primary",
                            ):
                                _, info_g = atualizar_status_protocolo_com_gestta(
                                    p["id"], "Aprovada",
                                    observacoes=(
                                        "Viabilidade deferida pela Prefeitura.\n"
                                        "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                    ),
                                )
                                st.toast("Viabilidade aprovada!")
                                _mostrar_feedback_gestta(info_g, "Aprovada")
                                _invalidar_cache_db()
                                import time as _t
                                _t.sleep(0.8)
                                st.rerun()
                        with b2:
                            _k_recon = f"recon_{p['id']}"
                            if not st.session_state.get(_k_recon):
                                if st.button(
                                    "❌ Indeferida",
                                    key=f"ind_{p['id']}",
                                    width="stretch",
                                ):
                                    st.session_state[_k_recon] = True
                                    st.rerun()
                            else:
                                st.error("⚠️ Viabilidade Não Aprovada")
                                st.caption("Motivo: análise automática VRE/JUCESP — atividade Não Passível no endereço.")
                                _r1c, _r2c = st.columns(2)
                                with _r1c:
                                    if st.button("📧 Solicitar Reconsideração", key=f"send_rc_{p['id']}", width="stretch", type="primary"):
                                        import urllib.parse as _up
                                        _em = "diretrizes.shdu@cotia.sp.gov.br"
                                        _pr = p["numero_protocolo"]
                                        _razao = p.get("razao_social", "")
                                        _cnpj_raw = p.get("cnpj", "")
                                        _cnpj_fmt = f"{_cnpj_raw[:2]}.{_cnpj_raw[2:5]}.{_cnpj_raw[5:8]}/{_cnpj_raw[8:12]}-{_cnpj_raw[12:]}" if len(_cnpj_raw) == 14 else _cnpj_raw
                                        _subj = _up.quote(f"Solicitacao de Nova Analise - Protocolo {_pr}")
                                        _body = _up.quote(
                                            f"Prezados,\n\n"
                                            f"Solicito nova analise do protocolo abaixo, que consta como Viabilidade Nao Aprovada:\n\n"
                                            f"Protocolo: {_pr}\n"
                                            f"Empresa: {_razao}\n"
                                            f"CNPJ: {_cnpj_fmt}\n\n"
                                            f"Aguardo retorno."
                                        )
                                        _obs = f"Viabilidade Nao Aprovada (VRE/JUCESP).\nPedido de reconsideracao enviado para {_em}.\nProtocolo: {_pr}\n_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                        _, info_g = atualizar_status_protocolo_com_gestta(p["id"], "Aguardando Reconsideração", observacoes=_obs)
                                        st.session_state.pop(_k_recon, None)
                                        st.toast("Reconsideração registrada! GESTTA anotado.")
                                        _mostrar_feedback_gestta(info_g, "Aguardando Reconsideração")
                                        _invalidar_cache_db()
                                        import time as _t; _t.sleep(1.0); st.rerun()
                                with _r2c:
                                    if st.button("← Cancelar", key=f"cancel_rc_{p['id']}", width="stretch"):
                                        st.session_state.pop(_k_recon, None)
                                        st.rerun()
                        with b3:
                            if st.button(
                                "🚫 Cancelar",
                                key=f"can_{p['id']}",
                                width="stretch",
                            ):
                                _, info_g = atualizar_status_protocolo_com_gestta(
                                    p["id"], "Cancelada",
                                    observacoes=(
                                        "Protocolo cancelado.\n"
                                        "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                    ),
                                )
                                st.toast("Cancelado.")
                                _mostrar_feedback_gestta(info_g, "Cancelada")
                                _invalidar_cache_db()
                                import time as _t
                                _t.sleep(0.8)
                                st.rerun()

            # ── Protocolos aguardando reconsideração ──────────────────────
            if via_reconsideracao:
                st.markdown("---")
                st.markdown("##### 🔄 Aguardando Reconsideração")
            for p in via_reconsideracao:
                dias = _dias(p)
                razao = p.get("razao_social", "?")
                with st.container(border=True):
                    ca, cb = st.columns([3, 1])
                    with ca:
                        st.markdown(f"🔄 **{razao}**")
                        st.caption(f"`{p['numero_protocolo']}` · Aguardando Reconsideração · {dias}d")
                    with cb:
                        st.caption(p.get("data_solicitacao") or "—")
                    import urllib.parse as _up2
                    _em2 = "diretrizes.shdu@cotia.sp.gov.br"
                    _pr2 = p["numero_protocolo"]
                    _s2 = _up2.quote(f"Solicitacao de Nova Analise - Protocolo {_pr2}")
                    _b2 = _up2.quote(f"Prezados,\n\nSolicito nova analise do protocolo {_pr2} que consta como Viabilidade Nao Aprovada.\n\nAguardo retorno.")
                    st.link_button("📧 Abrir e-mail no Outlook", f"mailto:{_em2}?subject={_s2}&body={_b2}", width="stretch")
                    st.caption("Clique para abrir o Outlook com e-mail pré-preenchido para a Prefeitura de Cotia. Depois de enviar, informe o novo protocolo abaixo.")
                    _new_proto = st.text_input(
                        "Novo protocolo recebido",
                        placeholder="Ex: SPM2630312354",
                        key=f"new_proto_num_{p['id']}",
                        label_visibility="collapsed",
                    )
                    if st.button("✅ Registrar novo protocolo e retomar fluxo", key=f"new_proto_{p['id']}", width="stretch", type="primary", disabled=not _new_proto.strip()):
                        if _new_proto.strip():
                            _obs_nova = (
                                f"Reconsideração aprovada pela Prefeitura.\n"
                                f"Novo protocolo de viabilidade: {_new_proto.strip()}\n"
                                "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                            )
                            novo_via_id = criar_protocolo_redesim(
                                empresa_id=p["empresa_id"],
                                tipo=TIPO_PROTOCOLO_VIABILIDADE,
                                numero_protocolo=_new_proto.strip(),
                                data_solicitacao=_dt.now().strftime("%Y-%m-%d"),
                                status="Em análise",
                                observacoes=_obs_nova,
                            )
                            _, info_g = atualizar_status_protocolo_com_gestta(
                                p["id"], "Inativa",
                                observacoes=_obs_nova,
                            )
                            st.toast(f"Novo protocolo {_new_proto.strip()} registrado! Retomando fluxo de viabilidade.")
                            _mostrar_feedback_gestta(info_g, "Inativa")
                            _invalidar_cache_db()
                            import time as _t; _t.sleep(0.8); st.rerun()

        with col_arrow:
            st.markdown(
                "<div style='text-align:center;font-size:2rem;padding-top:3rem;'>→</div>",
                unsafe_allow_html=True,
            )

        with col_lic:
            st.markdown("#### 📄 Etapa 2 — Licenciamento (CLI)")
            st.caption(f"{len(lic_andamento)} em andamento")
            if not lic_andamento:
                st.info("Nenhum licenciamento em andamento ainda.")
            for p in lic_andamento:
                dias = _dias(p)
                cor = _cor(dias)
                razao = p.get("razao_social", "?")
                with st.container(border=True):
                    ca, cb = st.columns([3, 1])
                    with ca:
                        st.markdown(f"{cor} **{razao}**")
                        st.caption(
                            f"`{p['numero_protocolo']}` · {p['status']} · {dias}d"
                        )
                    with cb:
                        st.caption(p.get("data_solicitacao") or "—")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button(
                            "✅ CLI Emitido",
                            key=f"cli_{p['id']}",
                            width="stretch",
                            type="primary",
                        ):
                            _, info_g = atualizar_status_protocolo_com_gestta(
                                p["id"], "Concluída",
                                observacoes=(
                                    "CLI emitido. Licença de Funcionamento concluída.\n"
                                    "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                ),
                            )
                            st.toast("CLI emitido! Cobrança DOMÍNIO gerada automaticamente.")
                            _mostrar_feedback_gestta(info_g, "Concluída")
                            _invalidar_cache_db()
                            import time as _t
                            _t.sleep(0.8)
                            st.rerun()
                    with b2:
                        if st.button(
                            "❌ Indeferida",
                            key=f"lic_ind_{p['id']}",
                            width="stretch",
                        ):
                            _, info_g = atualizar_status_protocolo_com_gestta(
                                p["id"], "Indeferida",
                                observacoes=(
                                    "Licenciamento indeferido.\n"
                                    "_(mensagem gerada pelo Claude — REDESIM Manager CSM)_"
                                ),
                            )
                            st.toast("Indeferido.")
                            _mostrar_feedback_gestta(info_g, "Indeferida")
                            _invalidar_cache_db()
                            import time as _t
                            _t.sleep(0.8)
                            st.rerun()

        st.caption(
            f"🔴 ≥ {DIAS_VERMELHO}d · 🟡 ≥ {DIAS_AMARELO}d · 🟢 ok. "
            "Histórico completo em **🏢 Empresas / REDESIM**."
        )


def _bloco_documentos_dashboard():
    """Bloco de documentos com vencimento próximo, com filtros."""
    try:
        docs = documentos_proximos_vencimento()
    except Exception:
        return
    if not docs:
        return

    enriquecidos = []
    for d in docs:
        dias = d.get("dias_para_vencer")
        if dias is None:
            cor = "🟢"
        elif dias < 0:
            cor = "🔴"
        elif dias <= 15:
            cor = "🟡"
        else:
            cor = "🟢"
        enriquecidos.append({**d, "_cor": cor, "_dias": dias})

    with st.container(border=True):
        st.markdown(
            "<div class='bloco-header'>📄 Documentos com vencimento</div>",
            unsafe_allow_html=True,
        )
        _r = sum(1 for d in enriquecidos if d["_cor"] == "🔴")
        _y = sum(1 for d in enriquecidos if d["_cor"] == "🟡")
        _g = sum(1 for d in enriquecidos if d["_cor"] == "🟢")
        st.markdown(_health_bar_html(_r, _y, _g), unsafe_allow_html=True)

        with st.expander("🔎 Filtros", expanded=False):
            f1, f2, f3 = st.columns(3)
            with f1:
                f_alerta = st.multiselect(
                    "Alerta",
                    ["🔴", "🟡", "🟢"],
                    default=["🔴", "🟡", "🟢"],
                    key="doc_dash_alerta",
                )
            with f2:
                tipos_disp = sorted({d.get("tipo", "?") for d in enriquecidos})
                f_tipo = st.multiselect(
                    "Tipo",
                    tipos_disp,
                    default=tipos_disp,
                    key="doc_dash_tipo",
                )
            with f3:
                emps_disp = sorted({d.get("razao_social", "?") for d in enriquecidos})
                f_emp = st.selectbox(
                    "Empresa",
                    ["Todas"] + emps_disp,
                    key="doc_dash_emp",
                )

        filtrados = [
            d for d in enriquecidos
            if d["_cor"] in f_alerta
            and d.get("tipo") in f_tipo
            and (f_emp == "Todas" or d.get("razao_social") == f_emp)
        ]
        ordem = {"🔴": 0, "🟡": 1, "🟢": 2}
        filtrados.sort(key=lambda r: (ordem.get(r["_cor"], 9),
                                       (r["_dias"] if r["_dias"] is not None else 999)))

        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Filtrados", len(filtrados))
        cm2.metric("🔴 Vencidos", sum(1 for r in filtrados if r["_cor"] == "🔴"))
        cm3.metric("🟡 ≤ 15 dias", sum(1 for r in filtrados if r["_cor"] == "🟡"))
        cm4.metric("🟢 > 15 dias", sum(1 for r in filtrados if r["_cor"] == "🟢"))

        if filtrados:
            linhas = [{
                "": d["_cor"],
                "Empresa": d.get("razao_social", "?"),
                "Tipo": d.get("tipo", "?"),
                "Nº": d.get("numero") or "—",
                "Vence em": d.get("data_vencimento", "—"),
                "Status": (
                    f"vencido há {abs(d['_dias'])}d"
                    if d["_dias"] is not None and d["_dias"] < 0
                    else (f"{d['_dias']}d" if d["_dias"] is not None else "—")
                ),
            } for d in filtrados]
            sel = st.dataframe(
                pd.DataFrame(linhas), width="stretch", hide_index=True,
                on_select="rerun", selection_mode="single-row",
                key="doc_dash_df",
            )
            if sel and getattr(sel, "selection", None) and sel.selection.rows:
                idx = sel.selection.rows[0]
                d_sel = filtrados[idx]
                with st.container(border=True):
                    st.markdown(
                        f"**Selecionado:** {d_sel['_cor']} "
                        f"_{d_sel.get('tipo', '?')}_ #{d_sel.get('numero') or '?'} "
                        f"— {d_sel.get('razao_social', '?')}"
                    )
                    a1, a2, a3 = st.columns(3)
                    with a1:
                        nova_data = st.date_input(
                            "Renovar até",
                            value=date.today(),
                            key=f"doc_dash_renov_{d_sel['id']}",
                        )
                    with a2:
                        if st.button(
                            "🔄 Renovar (cria novo)",
                            key=f"doc_dash_renovbt_{d_sel['id']}",
                            width="stretch", type="primary",
                        ):
                            renovar_documento(
                                d_sel["id"],
                                nova_data.strftime("%Y-%m-%d"),
                            )
                            st.toast("Documento renovado.")
                            st.rerun()
                    with a3:
                        if st.button(
                            "🗑 Excluir",
                            key=f"doc_dash_del_{d_sel['id']}",
                            width="stretch",
                        ):
                            excluir_documento_vencimento(d_sel["id"])
                            st.toast("Documento excluído.")
                            st.rerun()

                    if st.button(
                        "📂 Abrir esse documento em Documentos →",
                        key=f"doc_dash_navigate_{d_sel['id']}",
                        width="stretch",
                    ):
                        _navegar_para(
                            "📄 Documentos",
                            focus_documento_id=d_sel["id"],
                            focus_documento_tipo=d_sel.get("tipo"),
                        )
        else:
            st.info("Nenhum documento com esses filtros.")
        st.caption(
            "Inclui CNDs, FGTS, CNDT, alvarás de funcionamento, sanitários, "
            "ambientais, certificado digital e contratos. "
            "**Clique numa linha** pra renovar rapidinho. Detalhes em "
            "**📄 Documentos** no menu."
        )


def _bloco_avcb_dashboard():
    """Bloco dos alvarás de bombeiros, com filtros."""
    try:
        alvs = alvaras_vencendo(dias=60)
    except Exception:
        return
    if not alvs:
        return

    enriquecidos = []
    for a in alvs:
        dias = int(a.get("dias_para_vencer") or 0)
        if dias < 0:
            cor = "🔴"
        elif dias <= 30:
            cor = "🟡"
        else:
            cor = "🟢"
        enriquecidos.append({**a, "_cor": cor, "_dias": dias})

    with st.container(border=True):
        st.markdown(
            "<div class='bloco-header'>🚒 Alvarás de Bombeiros (AVCB/CLCB)</div>",
            unsafe_allow_html=True,
        )
        _r = sum(1 for a in enriquecidos if a["_cor"] == "🔴")
        _y = sum(1 for a in enriquecidos if a["_cor"] == "🟡")
        _g = sum(1 for a in enriquecidos if a["_cor"] == "🟢")
        st.markdown(_health_bar_html(_r, _y, _g), unsafe_allow_html=True)

        with st.expander("🔎 Filtros", expanded=False):
            f1, f2, f3 = st.columns(3)
            with f1:
                f_alerta = st.multiselect(
                    "Alerta",
                    ["🔴", "🟡", "🟢"],
                    default=["🔴", "🟡", "🟢"],
                    key="avcb_dash_alerta",
                )
            with f2:
                tipos_disp = sorted({a.get("tipo") or "AVCB" for a in enriquecidos})
                f_tipo = st.multiselect(
                    "Tipo",
                    tipos_disp,
                    default=tipos_disp,
                    key="avcb_dash_tipo",
                )
            with f3:
                emps_disp = sorted({a.get("razao_social", "?") for a in enriquecidos})
                f_emp = st.selectbox(
                    "Empresa",
                    ["Todas"] + emps_disp,
                    key="avcb_dash_emp",
                )

        filtrados = [
            a for a in enriquecidos
            if a["_cor"] in f_alerta
            and (a.get("tipo") or "AVCB") in f_tipo
            and (f_emp == "Todas" or a.get("razao_social") == f_emp)
        ]
        ordem = {"🔴": 0, "🟡": 1, "🟢": 2}
        filtrados.sort(key=lambda r: (ordem.get(r["_cor"], 9), r["_dias"]))

        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Filtrados", len(filtrados))
        cm2.metric("🔴 Vencidos", sum(1 for r in filtrados if r["_cor"] == "🔴"))
        cm3.metric("🟡 ≤ 30 dias", sum(1 for r in filtrados if r["_cor"] == "🟡"))
        cm4.metric("🟢 > 30 dias", sum(1 for r in filtrados if r["_cor"] == "🟢"))

        if filtrados:
            linhas = [{
                "": a["_cor"],
                "Empresa": a.get("razao_social", "?"),
                "Tipo": a.get("tipo") or "AVCB",
                "Nº": a.get("numero") or "—",
                "Vence em": a.get("data_vencimento", "—"),
                "Status": (
                    f"vencido há {abs(a['_dias'])}d" if a["_dias"] < 0
                    else f"{a['_dias']}d"
                ),
            } for a in filtrados]
            sel = st.dataframe(
                pd.DataFrame(linhas), width="stretch", hide_index=True,
                on_select="rerun", selection_mode="single-row",
                key="avcb_dash_df",
            )
            if sel and getattr(sel, "selection", None) and sel.selection.rows:
                idx = sel.selection.rows[0]
                a_sel = filtrados[idx]
                with st.container(border=True):
                    st.markdown(
                        f"**Selecionado:** {a_sel['_cor']} "
                        f"_{a_sel.get('tipo') or 'AVCB'}_ "
                        f"#{a_sel.get('numero') or '?'} — "
                        f"{a_sel.get('razao_social', '?')}"
                    )
                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button(
                            "🗑 Excluir AVCB",
                            key=f"avcb_dash_del_{a_sel['id']}",
                            width="stretch",
                        ):
                            excluir_alvara_bombeiros(a_sel["id"])
                            st.toast("Alvará excluído.")
                            st.rerun()
                    with a2:
                        if st.button(
                            "📂 Abrir em Documentos → Bombeiros →",
                            key=f"avcb_dash_navigate_{a_sel['id']}",
                            width="stretch",
                            type="primary",
                        ):
                            _navegar_para(
                                "📄 Documentos",
                                focus_avcb_id=a_sel["id"],
                                focus_documento_tipo="🚒 Bombeiros",
                            )
                    st.caption(
                        "Para **renovar** ou **substituir** o AVCB, suba o "
                        "PDF novo em **📄 Documentos → 📤 Upload Central**."
                    )
        else:
            st.info("Nenhum alvará com esses filtros.")
        st.caption(
            "Janela: 60 dias antes do vencimento + já vencidos. "
            "**Clique na linha** para ações. Detalhes em "
            "**📄 Documentos → 🚒 Bombeiros**."
        )


def _bloco_gestta_dashboard():
    """Bloco das tarefas atrasadas importadas do GESTTA."""
    try:
        gestta = listar_tarefas_gestta(apenas_pendentes=True)
        stats_g = estatisticas_tarefas_gestta()
    except Exception:
        return
    if not gestta:
        return

    _ICONE_RISCO = {"ALTO": "🔴", "MÉDIO": "🟡", "BAIXO": "🟢"}

    with st.container(border=True):
        st.markdown(
            "<div class='bloco-header'>📋 Tarefas GESTTA</div>",
            unsafe_allow_html=True,
        )
        _r = sum(1 for t in gestta if t["risco"] == "ALTO")
        _y = sum(1 for t in gestta if t["risco"] == "MÉDIO")
        _g = sum(1 for t in gestta if t["risco"] == "BAIXO")
        st.markdown(_health_bar_html(_r, _y, _g), unsafe_allow_html=True)

        with st.expander("🔎 Filtros", expanded=False):
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                f_risco = st.multiselect(
                    "Risco",
                    RISCOS_GESTTA,
                    default=RISCOS_GESTTA,
                    key="gestta_dash_risco",
                )
            with f2:
                resps_disp = sorted({(t["responsavel"] or "—") for t in gestta})
                f_resp = st.multiselect(
                    "Responsável",
                    resps_disp,
                    default=resps_disp,
                    key="gestta_dash_resp",
                )
            with f3:
                so_sem_emp = st.checkbox(
                    "Só sem empresa",
                    key="gestta_dash_semempresa",
                )
            with f4:
                so_sem_prot = st.checkbox(
                    "Só sem protocolo",
                    key="gestta_dash_semprot",
                )

        filtradas = [
            t for t in gestta
            if t["risco"] in f_risco
            and (t["responsavel"] or "—") in f_resp
            and (not so_sem_emp or t["empresa_id"] is None)
            and (not so_sem_prot or t["protocolo_id"] is None)
        ]
        ordem = {"ALTO": 0, "MÉDIO": 1, "BAIXO": 2}
        filtradas.sort(key=lambda t: (ordem.get(t["risco"], 9),
                                       t.get("responsavel") or ""))

        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Filtradas", len(filtradas))
        cm2.metric("🔴 ALTO", sum(1 for t in filtradas if t["risco"] == "ALTO"))
        cm3.metric("🟡 MÉDIO", sum(1 for t in filtradas if t["risco"] == "MÉDIO"))
        cm4.metric("🔗 Sem empresa",
                   sum(1 for t in filtradas if t["empresa_id"] is None))

        if filtradas:
            linhas = [{
                "": _ICONE_RISCO.get(t["risco"], "⚪"),
                "Cliente": t["cliente_nome"],
                "Tarefa": t["tarefa_nome"],
                "Resp.": t["responsavel"] or "—",
                "Empresa vinc.": ("✅" if t["empresa_id"] else "❌"),
                "Protocolo": t["protocolo_numero"] or "—",
            } for t in filtradas]
            sel = st.dataframe(
                pd.DataFrame(linhas), width="stretch", hide_index=True,
                on_select="rerun", selection_mode="single-row",
                key="gestta_dash_df",
            )
            if sel and getattr(sel, "selection", None) and sel.selection.rows:
                idx = sel.selection.rows[0]
                t_sel = filtradas[idx]
                with st.container(border=True):
                    st.markdown(
                        f"**Selecionada:** {_ICONE_RISCO.get(t_sel['risco'])} "
                        f"_{t_sel['tarefa_nome']}_ — {t_sel['cliente_nome']}"
                    )
                    st.caption(t_sel["motivo_risco"] or "")
                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button(
                            "✅ Marcar como resolvida",
                            key=f"gestta_dash_res_{t_sel['id']}",
                            width="stretch", type="primary",
                        ):
                            marcar_tarefa_resolvida(t_sel["id"], True)
                            st.toast("Tarefa GESTTA resolvida.")
                            st.rerun()
                    with a2:
                        if st.button(
                            "🗑 Excluir",
                            key=f"gestta_dash_del_{t_sel['id']}",
                            width="stretch",
                        ):
                            excluir_tarefa_gestta(t_sel["id"])
                            st.toast("Tarefa GESTTA excluída.")
                            st.rerun()

                    if st.button(
                        "📂 Abrir essa tarefa em Tarefas GESTTA →",
                        key=f"gestta_dash_navigate_{t_sel['id']}",
                        width="stretch",
                    ):
                        _navegar_para(
                            "📋 Tarefas GESTTA",
                            focus_tarefa_id=t_sel["id"],
                        )
        else:
            st.info("Nenhuma tarefa GESTTA com esses filtros.")
        st.caption(
            "Para vincular tarefa a empresa/protocolo ou para subir um novo "
            "relatório do GESTTA, vá em **📋 Tarefas GESTTA** no menu."
        )


def pagina_dashboard():
    st.header("📊 Dashboard")
    st.caption(
        "Visão consolidada de TUDO que precisa de atenção. Quando você "
        "resolver / dar baixa em um item, ele sai automaticamente daqui."
    )

    # Botão de sync manual GESTTA
    _sc1, _sc2, _sc3 = st.columns([6, 2, 2])
    with _sc2:
        if st.button("🔄 Sync GESTTA", width="stretch", help="Atualiza tarefas do GESTTA agora (sincroniza status e novas tarefas)"):
            with st.spinner("Sincronizando com GESTTA..."):
                try:
                    from scheduler import sincronizar_tarefas_gestta
                    sincronizar_tarefas_gestta()
                    _invalidar_cache_db()
                    st.toast("✅ GESTTA sincronizado!")
                    import time as _t; _t.sleep(0.5); st.rerun()
                except Exception as _e:
                    st.error(f"Erro ao sincronizar: {_e}")
    with _sc3:
        if st.button("⟳ Recarregar", width="stretch", help="Recarrega os dados do dashboard"):
            _invalidar_cache_db()
            st.rerun()

    # === Resumo super-consolidado no topo ===
    _resumo_consolidado_dashboard()

    # === Blocos detalhados (cada um com filtros + tabela clicável) ===
    _bloco_pendencias_dashboard()
    _bloco_protocolos_redesim_dashboard()
    _bloco_documentos_dashboard()
    _bloco_avcb_dashboard()
    _bloco_gestta_dashboard()


# ---------------------------------------------------------
# PÁGINA 2 — NOVO PROCESSO
# ---------------------------------------------------------
def _buscar_empresa_por_cnpj(cnpj: str):
    from database import get_conn
    if not cnpj:
        return None
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM empresas WHERE cnpj = ?", (cnpj,)).fetchone()
        return dict(r) if r else None


def _painel_protocolos_empresa(empresa_id: int) -> dict:
    """Renderiza um painel com os protocolos REDESIM da empresa (usado no
    Novo Processo quando a empresa já existe). Retorna um dict com:
      - 'problematicos': lista de protocolos ainda ativos com status ruim
                         (podem ser substituídos pelo novo)
      - 'ok': lista de protocolos com status Aprovada/Concluída
      - 'andamento': lista em andamento
    """
    from database import STATUS_PROTOCOLO_OK as _OK
    from database import STATUS_PROTOCOLO_PROBLEMA as _PROB
    from database import STATUS_PROTOCOLO_EM_ANDAMENTO as _AND

    protos = listar_protocolos_empresa(empresa_id)
    ok = [p for p in protos if p["status"] in _OK]
    prob = [p for p in protos
            if p["status"] in _PROB
            and not p.get("substituido_por_id")]
    andamento = [p for p in protos if p["status"] in _AND]

    if not protos:
        st.caption("📭 Esta empresa ainda não tem nenhum protocolo REDESIM.")
        return {"problematicos": [], "ok": [], "andamento": []}

    cA, cB, cC = st.columns(3)
    cA.metric("🟢 Aprovados/Concluídos", len(ok))
    cB.metric("🟡 Em andamento", len(andamento))
    cC.metric("🔴 Pendentes de substituição", len(prob))

    if prob:
        linhas = []
        for p in prob:
            linhas.append(
                f"- 🔴 **{p['tipo']}** · `{p['numero_protocolo']}` · "
                f"{p.get('data_solicitacao') or '—'} · **{p['status']}**"
            )
        st.warning(
            "⚠️ **A empresa tem protocolo(s) com status problemático ainda ativos.**\n\n"
            + "\n".join(linhas)
            + "\n\n👉 Se este novo protocolo for uma **nova tentativa** no lugar "
              "dos acima, marque a caixa **«Este protocolo substitui os anteriores»** "
              "abaixo — eles serão mantidos no histórico, mas marcados como "
              "substituídos por este."
        )
    if ok:
        with st.expander(f"📜 Protocolos anteriores ({len(protos)} no total) — "
                         "histórico completo"):
            for p in protos:
                bol = _bolinha_status_protocolo(p["status"])
                sub = ""
                if p.get("substituido_por_id"):
                    sub = f" · _(substituído pelo #{p['substituido_por_id']})_"
                st.markdown(
                    f"- {bol} **{p['tipo']}** · `{p['numero_protocolo']}` · "
                    f"{p.get('data_solicitacao') or '—'} · **{p['status']}**{sub}"
                )

    return {"problematicos": prob, "ok": ok, "andamento": andamento}


def _inferir_tipo_redesim_por_tipo_processo(tipo_processo: str) -> str:
    """Heurística: 'Baixa' → Licenciamento (já tem empresa); caso contrário
    começa em Viabilidade. Serve só como default do selectbox — Eduardo
    pode trocar."""
    if tipo_processo in ("Baixa",):
        return TIPO_PROTOCOLO_LICENCIAMENTO
    return TIPO_PROTOCOLO_VIABILIDADE


def pagina_novo_processo():
    st.header("➕ Novo Processo REDESIM")

    empresas = _cache_empresas()
    empresa_opts = {f"{e['razao_social']} ({e['cnpj'] or 's/ CNPJ'})": e["id"]
                    for e in empresas}

    # =====================================================
    # MODO RÁPIDO: CRIA EMPRESA + PROCESSO A PARTIR DO PDF
    # =====================================================
    with st.expander("📄 **MODO RÁPIDO** — Subir Cartão CNPJ e criar tudo automaticamente",
                     expanded=True):
        st.caption("Envie o PDF do Cartão CNPJ da Receita Federal. "
                   "O sistema extrai razão social, CNPJ, endereço, CNAEs e "
                   "classifica risco + vigilância sanitária automaticamente.")

        pdf_cnpj = st.file_uploader("Cartão CNPJ (PDF)", type=["pdf"],
                                    key="pdf_rapido")
        if pdf_cnpj:
            import tempfile, os as _os
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.write(pdf_cnpj.read())
            tmp.close()
            try:
                info = extrair_dados_cartao_cnpj(tmp.name)
            finally:
                try:
                    _os.unlink(tmp.name)
                except Exception:
                    pass

            # Avisos sobre qualidade da extração
            if info.get("usou_ocr"):
                if info.get("idioma_ocr") == "por":
                    st.info("🔍 Este PDF usou **OCR em português** porque a "
                            "Receita Federal gerou o cartão com fonte embarcada "
                            "sem Unicode. Confira os dados abaixo — podem ter "
                            "pequenas imperfeições de reconhecimento.")
                elif info.get("idioma_ocr") == "eng":
                    st.warning(
                        "⚠️ Este PDF usou OCR mas caiu para inglês — o "
                        "pacote de português (tesseract-ocr-por) pode não "
                        "ter subido no servidor ainda. Números (CNPJ, CEP, "
                        "datas) saem certos; acentos podem ficar imperfeitos. "
                        "Se persistir, dê um Reboot no app pra reinstalar os "
                        "pacotes do servidor."
                    )
                else:
                    st.info("🔍 Este PDF usou OCR. Confira os dados abaixo.")
            elif not info.get("razao_social") and not info.get("cnaes"):
                st.error(
                    "❌ Não consegui extrair dados deste PDF.\n\n"
                    "**Causa provável:** o cartão foi salvo com fonte sem "
                    "Unicode (comum ao 'imprimir como PDF' pelo navegador) "
                    "e o OCR não rodou no servidor.\n\n"
                    "**O que fazer:** preencha os campos abaixo manualmente "
                    "por enquanto. Se acontecer com vários cartões, avise — "
                    "o OCR (tesseract-ocr) precisa estar instalado no "
                    "servidor; um Reboot do app reinstala os pacotes."
                )

            # Verifica se a empresa já existe (usa normalização de CNPJ)
            ja_existe = buscar_empresa_por_cnpj(info.get("cnpj"))
            painel_protos: dict = {"problematicos": [], "ok": [], "andamento": []}
            if ja_existe:
                st.info(f"ℹ️ Empresa já cadastrada (ID {ja_existe['id']}). "
                        "O processo será vinculado a ela.")
                with st.container(border=True):
                    st.markdown("##### 📜 Protocolos REDESIM já registrados")
                    painel_protos = _painel_protocolos_empresa(ja_existe["id"])

            st.markdown("#### 📋 Dados extraídos (edite se precisar)")
            c1, c2 = st.columns(2)
            with c1:
                razao_ed = st.text_input("Razão Social *",
                                          value=info.get("razao_social") or "",
                                          key="rap_razao")
                cnpj_ed = st.text_input("CNPJ",
                                         value=info.get("cnpj") or "",
                                         key="rap_cnpj")
                fantasia_ed = st.text_input("Nome Fantasia",
                                             value=info.get("nome_fantasia") or "",
                                             key="rap_fant")
            with c2:
                end_ed = st.text_input("Endereço",
                                        value=info.get("endereco") or "",
                                        key="rap_end")
                mun_ed = st.text_input("Município",
                                        value=info.get("municipio") or "",
                                        key="rap_mun")
                cc1, cc2 = st.columns(2)
                uf_ed = cc1.text_input("UF",
                                       value=info.get("uf") or "",
                                       key="rap_uf")
                resp_ed = cc2.text_input("Responsável",
                                          value=RESPONSAVEL_PADRAO,
                                          key="rap_resp")

            st.markdown("#### 🏷️ CNAEs detectados")
            cnaes_det = info.get("cnaes", [])
            if not cnaes_det:
                st.warning("Nenhum CNAE foi encontrado no PDF. "
                           "Verifique o arquivo ou adicione manualmente abaixo.")
            else:
                consol = consolidar(cnaes_det)
                df_cnaes = pd.DataFrame(consol["detalhes"])
                st.dataframe(df_cnaes, width="stretch", hide_index=True)

                # 🚨 Banner de Risco ALTO por Vigilância Sanitária
                if consol["exige_sanitaria"]:
                    cnaes_visa = [
                        d["cnae"] for d in consol["detalhes"]
                        if d.get("exige_sanitaria")
                    ]
                    st.error(
                        "🚨 **RISCO ALTO OBRIGATÓRIO — Vigilância Sanitária** 🚨\n\n"
                        f"Os seguintes CNAE(s) exigem licença da Vig. Sanitária: "
                        f"**{', '.join(cnaes_visa)}**.\n\n"
                        "Pela regra do escritório, qualquer empresa com CNAE "
                        "de VISA cai automaticamente em **Risco Alto** — "
                        "não segue o REDESIM simplificado."
                    )

                cA, cB, cC = st.columns(3)
                cA.metric("Risco consolidado", consol["risco_final"])
                cB.metric("Exige Vig. Sanitária?",
                          "SIM ⚠️" if consol["exige_sanitaria"] else "NÃO")
                avcb_label = "NÃO"
                if consol.get("exige_avcb"):
                    avcb_label = f"SIM · {consol.get('grau_avcb') or '—'}"
                cC.metric("Exige AVCB/CLCB?", avcb_label)

            st.markdown("#### 📝 Dados do processo")
            rp1, rp2, rp3 = st.columns(3)
            proto_ed = rp1.text_input(
                "Protocolo REDESIM *",
                key="rap_proto",
                placeholder="Ex: SPM2630216399",
            )
            tipo_ed = rp2.selectbox("Tipo do processo",
                                     ["Abertura", "Alteração", "Baixa", "Renovação"],
                                     key="rap_tipo")
            status_ed = rp3.selectbox("Status do processo", STATUS_VALIDOS,
                                       key="rap_status")
            rp4, rp5 = st.columns([1, 2])
            canal_ed = rp4.selectbox(
                "Canal de solicitação",
                ["Online (REDESIM)", "Presencial", "Híbrido"],
                key="rap_canal",
                help="Se o município não tiver integração REDESIM, "
                     "ou exigir documentação física, marque Presencial.",
            )
            motivo_ed = rp5.text_input(
                "Motivo (se Presencial/Híbrido)",
                key="rap_motivo",
                placeholder="Ex: Município não integrado / Exige doc. original",
            )

            # ----- Seção REDESIM (protocolo estruturado) -----
            st.markdown("##### 🔄 Dados do protocolo REDESIM")
            st.caption(
                "Esses campos alimentam a **Timeline por empresa**. "
                "Viabilidade = 1º passo (Junta Comercial); "
                "Licenciamento = depois da viabilidade aprovada."
            )
            rr1, rr2, rr3 = st.columns(3)
            default_tipo_rdm = _inferir_tipo_redesim_por_tipo_processo(tipo_ed)
            redesim_tipo = rr1.selectbox(
                "Tipo do protocolo REDESIM *",
                options=TIPOS_PROTOCOLO_REDESIM,
                index=TIPOS_PROTOCOLO_REDESIM.index(default_tipo_rdm),
                key="rap_rdm_tipo",
            )
            status_opts_rdm = (
                STATUS_PROTOCOLO_VIABILIDADE
                if redesim_tipo == TIPO_PROTOCOLO_VIABILIDADE
                else STATUS_PROTOCOLO_LICENCIAMENTO
            )
            redesim_status = rr2.selectbox(
                "Status do protocolo *",
                options=status_opts_rdm,
                key="rap_rdm_status",
            )
            redesim_data = rr3.date_input(
                "Data de solicitação *",
                value=date.today(),
                format="DD/MM/YYYY",
                key="rap_rdm_data",
            )

            # ----- Substituição automática -----
            substituir_flag = False
            if ja_existe and painel_protos.get("problematicos"):
                n_prob = len(painel_protos["problematicos"])
                substituir_flag = st.checkbox(
                    f"🔁 Este protocolo substitui os {n_prob} anterior(es) "
                    f"com status 🔴 (Indeferida / Cancelada / Inativa)",
                    value=True,
                    key="rap_substituir",
                    help="Mantém o histórico dos anteriores, mas marca-os "
                         "como substituídos por este novo. Desmarque se "
                         "for um protocolo paralelo que não substitui.",
                )

            obs_ed = st.text_area("Observações", key="rap_obs")

            # --- Diagnóstico: mostrar texto OCR bruto ---
            with st.expander("🔧 Diagnóstico — ver texto bruto extraído (OCR)"):
                st.caption(
                    "Se algum campo ficou vazio ou errado, copie este texto "
                    "e mande pro suporte pra ajustar o parser."
                )
                st.text_area(
                    "Texto extraído do PDF",
                    value=info.get("texto", "")[:5000],
                    height=300,
                    key="rap_diag",
                )

            if st.button("🚀 Criar empresa + processo + protocolo REDESIM",
                         type="primary", key="btn_rapido"):
                obs_problematica = (
                    redesim_status in STATUS_PROTOCOLO_PROBLEMA
                    and not (obs_ed or "").strip()
                )
                if not razao_ed:
                    st.error("Razão social é obrigatória.")
                elif not cnaes_det:
                    st.error("É preciso ter pelo menos um CNAE.")
                elif not (proto_ed or "").strip():
                    st.error("Número do protocolo REDESIM é obrigatório.")
                elif obs_problematica:
                    st.error(
                        f"⚠️ Como o status do protocolo é **{redesim_status}**, "
                        "é obrigatório preencher **Observações** com o motivo "
                        "e como está resolvendo (erro no REDESIM → refazer; "
                        "ou vai direto no órgão)."
                    )
                else:
                    # Reusa a empresa se o CNPJ já existir
                    if ja_existe:
                        emp_id = ja_existe["id"]
                    else:
                        emp_id = criar_empresa(
                            razao_social=razao_ed,
                            cnpj=cnpj_ed or None,
                            endereco=end_ed or None,
                            municipio=mun_ed or None,
                            uf=uf_ed or None,
                            responsavel=resp_ed or None,
                        )
                    consol = consolidar(cnaes_det)
                    cnaes_input = [
                        {"cnae": c, "principal": 1 if i == 0 else 0}
                        for i, c in enumerate(cnaes_det)
                    ]
                    proc_id = criar_processo(
                        empresa_id=emp_id,
                        protocolo=proto_ed,
                        tipo=tipo_ed,
                        status=status_ed,
                        risco=consol["risco_final"],
                        exige_sanitaria=1 if consol["exige_sanitaria"] else 0,
                        observacoes=obs_ed,
                        canal_redesim=canal_ed.split(" (")[0],  # "Online"/"Presencial"/"Híbrido"
                        motivo_presencial=motivo_ed or None,
                        cnaes=cnaes_input,
                    )

                    # Cria o protocolo REDESIM (alimenta Timeline por empresa)
                    try:
                        proto_rdm_id = criar_protocolo_redesim(
                            emp_id,
                            redesim_tipo,
                            proto_ed.strip(),
                            data_solicitacao=redesim_data.isoformat(),
                            status=redesim_status,
                            observacoes=(obs_ed.strip() or None),
                        )
                    except Exception as exc:  # noqa: BLE001
                        proto_rdm_id = None
                        st.warning(
                            f"⚠️ Processo criado, mas falhei ao registrar o "
                            f"protocolo na Timeline: {exc}"
                        )
                    # MODO RÁPIDO: anota a criação no GESTTA se a empresa
                    # tiver UMA tarefa pendente vinculável (senão, ignora).
                    if proto_rdm_id:
                        try:
                            _r_mr = _anotar_criacao_modo_rapido(
                                emp_id, proto_rdm_id, proto_ed.strip(),
                                redesim_tipo, redesim_status,
                            )
                            if _r_mr.get("ok"):
                                st.info("📝 Anotação de criação enviada ao GESTTA.")
                            else:
                                st.caption(f"GESTTA: {_r_mr.get('mensagem')}")
                        except Exception as _e_mr:
                            st.caption(f"GESTTA: não anotou ({_e_mr}).")


                    # Substituição automática dos problemáticos anteriores
                    n_subs = 0
                    if (proto_rdm_id and substituir_flag
                            and painel_protos.get("problematicos")):
                        try:
                            n_subs = substituir_protocolos(
                                emp_id, proto_rdm_id,
                            )
                        except Exception as exc:  # noqa: BLE001
                            st.warning(
                                f"⚠️ Novo protocolo criado, mas falhei ao "
                                f"marcar substituições: {exc}"
                            )

                    msg = (
                        f"✅ Empresa {'reutilizada' if ja_existe else 'criada'} "
                        f"(ID {emp_id}) · processo ID {proc_id} · "
                        f"Risco **{consol['risco_final']}** · "
                        f"Sanitária **{'SIM' if consol['exige_sanitaria'] else 'NÃO'}**"
                    )
                    if proto_rdm_id:
                        msg += (
                            f"\n\n📜 Protocolo **{proto_ed}** "
                            f"({_bolinha_status_protocolo(redesim_status)} "
                            f"{redesim_status}) adicionado à Timeline."
                        )
                    if n_subs:
                        msg += (
                            f"\n\n🔁 **{n_subs}** protocolo(s) anterior(es) "
                            f"com status 🔴 marcados como substituídos por este."
                        )
                    st.success(msg)
                    st.balloons()

    st.divider()
    st.markdown("#### Ou faça manualmente:")

    with st.expander("Cadastrar nova empresa"):
        with st.form("form_empresa"):
            c1, c2 = st.columns(2)
            razao = c1.text_input("Razão Social *")
            cnpj = c2.text_input("CNPJ")
            end = st.text_input("Endereço")
            c3, c4, c5 = st.columns(3)
            mun = c3.text_input("Município")
            uf = c4.text_input("UF")
            resp = c5.text_input("Responsável")
            if st.form_submit_button("Salvar empresa"):
                if not razao:
                    st.error("Razão social é obrigatória")
                else:
                    criar_empresa(razao, cnpj, end, mun, uf, resp)
                    st.success(f"Empresa {razao} cadastrada!")
                    st.rerun()

    st.divider()
    if not empresa_opts:
        st.warning("Cadastre uma empresa acima antes de criar um processo.")
        return

    # Seletor de empresa FORA do form, para o painel reagir ao seletor
    emp_label = st.selectbox(
        "Empresa",
        list(empresa_opts.keys()),
        key="fp_empresa_sel",
    )
    emp_id_sel = empresa_opts[emp_label]

    # Painel de protocolos já existentes (com alerta de substituição)
    with st.container(border=True):
        st.markdown("##### 📜 Protocolos REDESIM já registrados para essa empresa")
        painel_m = _painel_protocolos_empresa(emp_id_sel)

    with st.form("form_processo"):
        c1, c2, c3 = st.columns(3)
        protocolo = c1.text_input(
            "Protocolo REDESIM *",
            placeholder="Ex: SPM2630216399",
        )
        tipo = c2.selectbox("Tipo do processo",
                            ["Abertura", "Alteração", "Baixa", "Renovação"])
        status = c3.selectbox("Status do processo", STATUS_VALIDOS)

        c4, c5 = st.columns([1, 2])
        canal_opts = ["Online (REDESIM)", "Presencial", "Híbrido"]
        canal_sel = c4.selectbox(
            "Canal de solicitação",
            canal_opts,
            help="Se o município não tiver integração REDESIM ou exigir "
                 "documentação física, marque Presencial.",
        )
        motivo_sel = c5.text_input(
            "Motivo (se Presencial/Híbrido)",
            placeholder="Ex: Município não integrado / Exige doc. original",
        )

        # ----- Seção REDESIM (protocolo estruturado) -----
        st.markdown("##### 🔄 Dados do protocolo REDESIM")
        st.caption(
            "Esses campos alimentam a **Timeline por empresa**. "
            "Viabilidade = 1º passo (Junta Comercial); "
            "Licenciamento = depois da viabilidade aprovada."
        )
        rr1, rr2, rr3 = st.columns(3)
        redesim_tipo_m = rr1.selectbox(
            "Tipo do protocolo REDESIM *",
            options=TIPOS_PROTOCOLO_REDESIM,
            key="fp_rdm_tipo",
        )
        status_opts_rdm_m = (
            STATUS_PROTOCOLO_VIABILIDADE
            if redesim_tipo_m == TIPO_PROTOCOLO_VIABILIDADE
            else STATUS_PROTOCOLO_LICENCIAMENTO
        )
        redesim_status_m = rr2.selectbox(
            "Status do protocolo *",
            options=status_opts_rdm_m,
            key="fp_rdm_status",
        )
        redesim_data_m = rr3.date_input(
            "Data de solicitação *",
            value=date.today(),
            format="DD/MM/YYYY",
            key="fp_rdm_data",
        )

        # Checkbox de substituição — só se houver problemáticos pendentes
        substituir_flag_m = False
        if painel_m.get("problematicos"):
            n_prob_m = len(painel_m["problematicos"])
            substituir_flag_m = st.checkbox(
                f"🔁 Este protocolo substitui os {n_prob_m} anterior(es) "
                f"com status 🔴 (Indeferida / Cancelada / Inativa)",
                value=True,
                key="fp_substituir",
                help="Mantém o histórico, mas marca os anteriores como "
                     "substituídos por este.",
            )

        st.markdown("##### CNAEs do processo")
        modo = st.radio("Como informar os CNAEs?",
                        ["Digitar manualmente", "Upload de Cartão CNPJ (PDF)"],
                        horizontal=True)

        cnaes_input: list[dict] = []
        if modo == "Digitar manualmente":
            txt = st.text_area(
                "Cole um CNAE por linha (ex: 4711-3/02)",
                height=120,
            )
            if txt:
                for linha in txt.splitlines():
                    linha = linha.strip()
                    if linha:
                        cnaes_input.append(
                            {"cnae": normalizar_cnae(linha), "principal": 0}
                        )
                if cnaes_input:
                    cnaes_input[0]["principal"] = 1
        else:
            pdf = st.file_uploader("Envie o Cartão CNPJ em PDF", type=["pdf"])
            if pdf:
                with open("/tmp/_cartao.pdf", "wb") as f:
                    f.write(pdf.read())
                info = extrair_dados_cartao_cnpj("/tmp/_cartao.pdf")
                st.info(f"CNPJ detectado: {info.get('cnpj') or '—'} | "
                        f"Razão: {info.get('razao_social') or '—'}")
                for i, c in enumerate(info.get("cnaes", [])):
                    cnaes_input.append({"cnae": c, "principal": 1 if i == 0 else 0})
                st.write("CNAEs extraídos:", info.get("cnaes", []))

        # Preview do consolidado com alerta sanitária ANTES de salvar
        if cnaes_input:
            consol_preview = consolidar([c["cnae"] for c in cnaes_input])
            if consol_preview["exige_sanitaria"]:
                cnaes_visa = [
                    d["cnae"] for d in consol_preview["detalhes"]
                    if d.get("exige_sanitaria")
                ]
                st.error(
                    "🚨 **RISCO ALTO OBRIGATÓRIO — Vigilância Sanitária** 🚨\n\n"
                    f"CNAE(s) com VISA: **{', '.join(cnaes_visa)}**.\n\n"
                    "Não segue o REDESIM simplificado — empresa entra em Risco Alto."
                )
            mA, mB = st.columns(2)
            mA.metric("Risco prévio", consol_preview["risco_final"])
            mB.metric("Sanitária?",
                      "SIM ⚠️" if consol_preview["exige_sanitaria"] else "NÃO")

        obs = st.text_area(
            "Observações",
            help="Obrigatório quando status do protocolo = "
                 "Indeferida / Cancelada / Inativa — anote o motivo e "
                 "como está resolvendo.",
        )

        submit_manual = st.form_submit_button(
            "🚀 Criar processo + protocolo REDESIM"
        )

    if submit_manual:
        if not (protocolo or "").strip():
            st.error("Número do protocolo REDESIM é obrigatório.")
        elif not cnaes_input:
            st.error("É preciso ter pelo menos um CNAE.")
        elif (redesim_status_m in STATUS_PROTOCOLO_PROBLEMA
                and not (obs or "").strip()):
            st.error(
                f"⚠️ Como o status do protocolo é **{redesim_status_m}**, "
                "é obrigatório preencher **Observações** com o motivo e "
                "como está resolvendo."
            )
        else:
            consol = consolidar([c["cnae"] for c in cnaes_input])
            proc_id = criar_processo(
                empresa_id=emp_id_sel,
                protocolo=protocolo,
                tipo=tipo,
                status=status,
                risco=consol["risco_final"],
                exige_sanitaria=1 if consol["exige_sanitaria"] else 0,
                observacoes=obs,
                canal_redesim=canal_sel.split(" (")[0],
                motivo_presencial=motivo_sel or None,
                cnaes=cnaes_input,
            )

            # Cria o protocolo REDESIM (alimenta Timeline)
            try:
                proto_rdm_id_m = criar_protocolo_redesim(
                    emp_id_sel,
                    redesim_tipo_m,
                    protocolo.strip(),
                    data_solicitacao=redesim_data_m.isoformat(),
                    status=redesim_status_m,
                    observacoes=(obs.strip() or None),
                )
            except Exception as exc:  # noqa: BLE001
                proto_rdm_id_m = None
                st.warning(
                    f"⚠️ Processo criado, mas falhei ao registrar o "
                    f"protocolo na Timeline: {exc}"
                )

            # Substitui problemáticos anteriores se marcado
            n_subs_m = 0
            if (proto_rdm_id_m and substituir_flag_m
                    and painel_m.get("problematicos")):
                try:
                    n_subs_m = substituir_protocolos(
                        emp_id_sel, proto_rdm_id_m,
                    )
                except Exception as exc:  # noqa: BLE001
                    st.warning(
                        f"⚠️ Novo protocolo criado, mas falhei ao marcar "
                        f"substituições: {exc}"
                    )

            msg = (
                f"✅ Processo ID {proc_id} criado. "
                f"Risco: **{consol['risco_final']}** · "
                f"Sanitária: **{'SIM' if consol['exige_sanitaria'] else 'NÃO'}** · "
                f"Canal: **{canal_sel}**"
            )
            if proto_rdm_id_m:
                msg += (
                    f"\n\n📜 Protocolo **{protocolo}** "
                    f"({_bolinha_status_protocolo(redesim_status_m)} "
                    f"{redesim_status_m}) adicionado à Timeline."
                )
            if n_subs_m:
                msg += (
                    f"\n\n🔁 **{n_subs_m}** protocolo(s) anterior(es) "
                    f"com status 🔴 marcados como substituídos por este."
                )
            st.success(msg)


# ---------------------------------------------------------
# PÁGINA 3 — CLASSIFICADOR CNAE
# ---------------------------------------------------------
def pagina_classificador():
    st.header("🏷️ Classificador de Risco de CNAE")
    st.caption("Insira os CNAEs ou envie um Cartão CNPJ em PDF.")

    tab1, tab2 = st.tabs(["Digitar CNAEs", "Upload de PDF"])

    cnaes_input: list[str] = []
    with tab1:
        txt = st.text_area("Um CNAE por linha", height=150,
                           placeholder="4711-3/02\n5611-2/01")
        if txt:
            cnaes_input = [normalizar_cnae(l) for l in txt.splitlines() if l.strip()]

    with tab2:
        pdf = st.file_uploader("Cartão CNPJ (PDF)", type=["pdf"], key="pdf_class")
        if pdf:
            with open("/tmp/_class.pdf", "wb") as f:
                f.write(pdf.read())
            info = extrair_dados_cartao_cnpj("/tmp/_class.pdf")
            cnaes_input = info.get("cnaes", [])
            st.info(f"CNPJ: {info.get('cnpj') or '—'} | "
                    f"Razão: {info.get('razao_social') or '—'}")

    if cnaes_input:
        consol = consolidar(cnaes_input)
        df = pd.DataFrame(consol["detalhes"])

        col1, col2, col3 = st.columns(3)
        col1.metric("Risco consolidado", consol["risco_final"])
        col2.metric("Exige Vig. Sanitária?",
                    "SIM" if consol["exige_sanitaria"] else "NÃO")
        avcb_label = "NÃO"
        if consol.get("exige_avcb"):
            avcb_label = f"SIM · {consol.get('grau_avcb') or '—'}"
        col3.metric("Exige AVCB/CLCB?", avcb_label)

        st.dataframe(df, width="stretch", hide_index=True)


# ---------------------------------------------------------
# PÁGINA 4 — VIGILÂNCIA SANITÁRIA
# ---------------------------------------------------------
def pagina_vigilancia():
    from utils.cnae_tools import extrair_tabela_vigilancia_pdf
    from database import get_conn

    st.header("🏥 Portaria CVS-SP — Base de Vigilância Sanitária")
    st.caption(
        "Página de **referência normativa**. Aqui você sobe o PDF da "
        "Portaria CVS-SP (ou similar municipal/federal) para que o sistema "
        "carregue a lista oficial de CNAEs sujeitos à Vigilância Sanitária "
        "com seus respectivos riscos. "
        "ℹ️ Para cadastrar o **Alvará Sanitário de uma empresa**, "
        "vá em **📄 Documentos → 📤 Upload Central**."
    )

    tabs = st.tabs(["📄 Upload de PDF (Portaria CVS-SP ou similar)",
                    "📊 Upload de CSV/Excel",
                    "🔎 Consultar CNAE",
                    "📋 Ver tabela atual"])

    # ==========================================================
    # ABA 1 — PDF DA PORTARIA
    # ==========================================================
    with tabs[0]:
        st.caption("Envie um PDF de Portaria da Vigilância Sanitária "
                   "(ex: **Portaria CVS nº 1/2024 de São Paulo**). "
                   "O sistema extrai automaticamente a lista de CNAEs e o "
                   "risco sanitário (Alto / Médio / Baixo) de cada um.")

        up_pdf = st.file_uploader("PDF da Portaria", type=["pdf"], key="pdf_visa")
        nivel_opt = st.selectbox("Nível de abrangência desta portaria",
                                  ["Estadual", "Municipal", "Federal"],
                                  key="visa_nivel")
        fonte_opt = st.text_input("Fonte (ex: Portaria CVS nº 1/2024 SP)",
                                   value="Portaria CVS nº 1/2024 - SP",
                                   key="visa_fonte")

        if up_pdf:
            import tempfile, os as _os
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.write(up_pdf.read())
            tmp.close()
            try:
                with st.spinner("Processando PDF, aguarde (pode levar 10-30s para portarias grandes)..."):
                    extraidos = extrair_tabela_vigilancia_pdf(tmp.name)
            finally:
                try:
                    _os.unlink(tmp.name)
                except Exception:
                    pass

            if not extraidos:
                st.error("Nenhum CNAE foi identificado no PDF. "
                         "Verifique se o arquivo contém a tabela com códigos CNAE.")
            else:
                st.success(f"✅ {len(extraidos)} CNAEs extraídos do PDF")
                # Prévia
                import pandas as _pd
                df_preview = _pd.DataFrame(extraidos)
                df_preview["exige_licenca"] = df_preview["exige_licenca"].map(
                    {1: "SIM", 0: "NÃO"}
                )

                # Filtros rápidos
                col1, col2, col3 = st.columns(3)
                col1.metric("Total", len(extraidos))
                col2.metric("Alto risco",
                            sum(1 for x in extraidos if x["risco_sanitario"] == "Alto"))
                col3.metric("Médio + Baixo",
                            sum(1 for x in extraidos
                                if x["risco_sanitario"] in ("Médio", "Baixo")))

                st.dataframe(df_preview[["cnae", "descricao",
                                          "risco_sanitario", "exige_licenca"]],
                             width="stretch", hide_index=True)

                if st.button("💾 Importar para o banco", type="primary",
                             key="btn_imp_pdf"):
                    progress = st.progress(0)
                    for i, item in enumerate(extraidos):
                        upsert_vigilancia(
                            cnae=item["cnae"],
                            descricao=item["descricao"],
                            exige_licenca=item["exige_licenca"],
                            nivel=nivel_opt,
                            fonte=fonte_opt,
                            risco_sanitario=item["risco_sanitario"],
                        )
                        progress.progress((i + 1) / len(extraidos))
                    st.success(f"✅ {len(extraidos)} CNAEs importados/atualizados!")
                    st.balloons()

    # ==========================================================
    # ABA 2 — CSV/EXCEL
    # ==========================================================
    with tabs[1]:
        st.caption("Se você já tem a tabela em CSV ou Excel. Colunas esperadas: "
                   "`cnae`, `descricao`, `exige_licenca` (SIM/NÃO ou 1/0), "
                   "`risco_sanitario` (Alto/Médio/Baixo), `nivel`, `fonte`")
        up = st.file_uploader("CSV ou Excel", type=["csv", "xlsx", "xls"],
                              key="visa_planilha")
        if up:
            try:
                if up.name.endswith(".csv"):
                    df = pd.read_csv(up, dtype=str).fillna("")
                else:
                    df = pd.read_excel(up, dtype=str).fillna("")

                df.columns = [c.strip().lower() for c in df.columns]
                if "cnae" not in df.columns or "exige_licenca" not in df.columns:
                    st.error("Arquivo precisa ter colunas `cnae` e `exige_licenca`.")
                else:
                    def para_bool(v):
                        s = str(v).strip().lower()
                        return 1 if s in ("1", "sim", "s", "true", "x") else 0

                    atualizados = 0
                    for _, row in df.iterrows():
                        cnae = normalizar_cnae(row.get("cnae", ""))
                        if not cnae:
                            continue
                        upsert_vigilancia(
                            cnae=cnae,
                            descricao=row.get("descricao") or None,
                            exige_licenca=para_bool(row.get("exige_licenca")),
                            nivel=row.get("nivel") or None,
                            fonte=row.get("fonte") or None,
                            risco_sanitario=row.get("risco_sanitario") or None,
                        )
                        atualizados += 1
                    st.success(f"{atualizados} CNAEs atualizados.")
            except Exception as exc:
                st.error(f"Falha: {exc}")

    # ==========================================================
    # ABA 3 — CONSULTA
    # ==========================================================
    with tabs[2]:
        cnae = st.text_input("CNAE", placeholder="5611-2/01", key="consulta_cnae")
        if cnae:
            resultado = classificar_cnae(cnae)
            with get_conn() as conn:
                r = conn.execute(
                    "SELECT * FROM vigilancia_sanitaria WHERE cnae = ?",
                    (normalizar_cnae(cnae),)
                ).fetchone()
                dados_visa = dict(r) if r else {}

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Risco CGSIM", resultado["risco"])
            col2.metric("Vigilância?",
                        "SIM" if resultado["exige_sanitaria"] else "NÃO")
            col3.metric("Risco Sanitário",
                        dados_visa.get("risco_sanitario") or "—")
            col4.metric("Nível", resultado.get("nivel_sanitaria") or "—")

            if dados_visa.get("risco_sanitario") == "Alto":
                st.warning("⚠️ **Alto risco sanitário** — exigirá "
                           "**Vigilância Sanitária PRIMEIRO**, depois a Licença de Funcionamento.")
            st.json({**resultado, **dados_visa})

    # ==========================================================
    # ABA 4 — VER / EDITAR / EXCLUIR TABELA
    # ==========================================================
    with tabs[3]:
        with get_conn() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT cnae, descricao, risco_sanitario, exige_licenca, nivel, fonte "
                "FROM vigilancia_sanitaria ORDER BY cnae"
            )]

        if not rows:
            st.info("Nenhum registro na tabela ainda. "
                    "Faça upload de um PDF/CSV nas abas ao lado.")
        else:
            df_all = pd.DataFrame(rows)
            df_all["exige_licenca_str"] = df_all["exige_licenca"].map(
                {1: "SIM", 0: "NÃO"}
            )

            c1, c2, c3 = st.columns(3)
            c1.metric("Total", len(df_all))
            c2.metric("Exige licença",
                      int((df_all["exige_licenca_str"] == "SIM").sum()))
            c3.metric("Alto risco",
                      int((df_all["risco_sanitario"] == "Alto").sum()))

            st.markdown("---")

            # ---------- Filtros ----------
            fcol1, fcol2, fcol3 = st.columns([2, 1, 1])
            filtro_cnae = fcol1.text_input(
                "🔎 Filtrar por CNAE ou descrição",
                key="vis_filtro_texto",
                placeholder="Ex: 6203 ou software"
            )
            filtro_risco = fcol2.selectbox(
                "Risco sanitário",
                ["(todos)", "Alto", "Médio", "Baixo"],
                key="vis_filtro_risco"
            )
            filtro_exige = fcol3.selectbox(
                "Exige licença",
                ["(todos)", "SIM", "NÃO"],
                key="vis_filtro_exige"
            )

            df_f = df_all.copy()
            if filtro_cnae:
                alvo = filtro_cnae.strip().lower()
                df_f = df_f[
                    df_f["cnae"].str.lower().str.contains(alvo, na=False) |
                    df_f["descricao"].fillna("").str.lower().str.contains(alvo, na=False)
                ]
            if filtro_risco != "(todos)":
                df_f = df_f[df_f["risco_sanitario"] == filtro_risco]
            if filtro_exige != "(todos)":
                df_f = df_f[df_f["exige_licenca_str"] == filtro_exige]

            st.caption(f"Exibindo **{len(df_f)}** de {len(df_all)} registros")

            # ---------- Editor inline ----------
            st.markdown("### ✏️ Editar registros")
            st.caption("Altere valores diretamente na tabela e clique em "
                       "**💾 Salvar alterações**. Para remover registros, "
                       "marque a coluna **excluir** e clique em **🗑️ Excluir selecionados**.")

            df_edit = df_f[["cnae", "descricao", "risco_sanitario",
                            "exige_licenca_str", "nivel", "fonte"]].copy()
            df_edit = df_edit.rename(columns={"exige_licenca_str": "exige_licenca"})
            df_edit.insert(0, "excluir", False)

            edited = st.data_editor(
                df_edit,
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                key="vis_editor",
                column_config={
                    "excluir": st.column_config.CheckboxColumn(
                        "🗑️", width="small",
                        help="Marque para excluir este CNAE"
                    ),
                    "cnae": st.column_config.TextColumn(
                        "CNAE", disabled=True, width="small"
                    ),
                    "descricao": st.column_config.TextColumn(
                        "Descrição", width="large"
                    ),
                    "risco_sanitario": st.column_config.SelectboxColumn(
                        "Risco sanitário",
                        options=["Alto", "Médio", "Baixo", None],
                        width="small",
                    ),
                    "exige_licenca": st.column_config.SelectboxColumn(
                        "Exige licença",
                        options=["SIM", "NÃO"],
                        width="small",
                    ),
                    "nivel": st.column_config.SelectboxColumn(
                        "Nível",
                        options=["Estadual", "Municipal", "Federal", None],
                        width="small",
                    ),
                    "fonte": st.column_config.TextColumn(
                        "Fonte", width="medium"
                    ),
                },
            )

            bc1, bc2, bc3 = st.columns([1, 1, 2])

            if bc1.button("💾 Salvar alterações", type="primary",
                          key="btn_vis_salvar"):
                # indexa original por CNAE
                originais = {r["cnae"]: r for r in rows}
                alterados = 0
                for _, linha in edited.iterrows():
                    if bool(linha.get("excluir")):
                        continue
                    cnae = linha["cnae"]
                    base = originais.get(cnae, {})
                    novo_exige = 1 if str(linha["exige_licenca"]).upper() == "SIM" else 0
                    mudou = (
                        (base.get("descricao") or "") != (linha.get("descricao") or "") or
                        (base.get("risco_sanitario") or None) != (linha.get("risco_sanitario") or None) or
                        int(base.get("exige_licenca") or 0) != novo_exige or
                        (base.get("nivel") or None) != (linha.get("nivel") or None) or
                        (base.get("fonte") or None) != (linha.get("fonte") or None)
                    )
                    if mudou:
                        upsert_vigilancia(
                            cnae=cnae,
                            descricao=linha.get("descricao") or None,
                            exige_licenca=novo_exige,
                            nivel=linha.get("nivel") or None,
                            fonte=linha.get("fonte") or None,
                            risco_sanitario=linha.get("risco_sanitario") or None,
                        )
                        alterados += 1
                if alterados:
                    st.success(f"✅ {alterados} registro(s) atualizado(s).")
                    st.rerun()
                else:
                    st.info("Nenhuma alteração detectada.")

            if bc2.button("🗑️ Excluir selecionados", key="btn_vis_excluir"):
                alvos = [l["cnae"] for _, l in edited.iterrows() if bool(l.get("excluir"))]
                if not alvos:
                    st.warning("Nenhum CNAE marcado para exclusão.")
                else:
                    n = excluir_varios_vigilancia(alvos)
                    st.success(f"✅ {n} CNAE(s) removido(s): {', '.join(alvos)}")
                    st.rerun()

            # ---------- Ação rápida: limpar "exclusões indevidas" ----------
            with st.expander("🧹 Ação rápida — remover falsos positivos comuns"):
                st.caption("Alguns CNAEs são frequentemente incluídos por engano "
                           "no parser de portarias (ex: a seção **'NÃO COMPREENDE'** "
                           "da CVS-SP). Use esta lista para remover em massa:")

                falsos_positivos_sugeridos = [
                    "6203-1/00",  # Desenvolvimento de software não-customizável
                    "6201-5/01",  # Desenvolvimento sob encomenda
                    "6202-3/00",  # Desenvolvimento e licenciamento customizável
                    "6204-0/00",  # Consultoria em TI
                    "6920-6/01",  # Contabilidade
                    "6920-6/02",  # Auditoria contábil
                    "6911-7/01",  # Serviços advocatícios
                    "6911-7/03",  # Consultoria jurídica
                    "7020-4/00",  # Consultoria em gestão empresarial
                    "8230-0/01",  # Casas de festas e eventos
                    "8599-6/04",  # Treinamento em desenvolvimento profissional
                    "4761-0/01",  # Comércio varejista de livros
                    "4761-0/02",  # Comércio varejista de jornais e revistas
                    "5811-5/00",  # Edição de livros
                ]
                existentes = set(df_all["cnae"].tolist())
                candidatos = [c for c in falsos_positivos_sugeridos if c in existentes]

                if not candidatos:
                    st.success("✅ Nenhum CNAE da lista de falsos positivos está "
                               "presente na sua tabela.")
                else:
                    selecionados = st.multiselect(
                        "Marque os CNAEs a remover",
                        options=candidatos,
                        default=candidatos,
                        key="vis_falsos_positivos",
                    )
                    if st.button("🗑️ Remover selecionados da Vigilância",
                                 key="btn_remover_falsos"):
                        if selecionados:
                            n = excluir_varios_vigilancia(selecionados)
                            st.success(f"✅ {n} CNAE(s) removido(s) da vigilância "
                                       f"sanitária: {', '.join(selecionados)}")
                            st.rerun()
                        else:
                            st.warning("Nenhum CNAE selecionado.")


# ---------------------------------------------------------
# PÁGINA 5 — MATRIZ DE RISCO CNAE
# ---------------------------------------------------------
def pagina_matriz_risco():
    st.header("📋 Matriz de Risco CNAE")
    st.caption(
        "Fontes principais: **NR-04** (Grau de Risco 1-4), "
        "**CGSIM nº 51/2019** (Baixo/Alto Risco REDESIM) e listas municipais."
    )

    tab_nr04, tab_csv, tab_manual, tab_consulta = st.tabs([
        "📄 Upload NR-04 (PDF)",
        "📊 Upload CSV/Excel",
        "✏️ Editar manualmente",
        "🔍 Consultar tabela atual",
    ])

    # ================ NR-04 PDF ================
    with tab_nr04:
        st.markdown(
            "Envie o **PDF da NR-04** (Portaria SIT/DSST nº 76/2008 e "
            "atualizações) — o sistema extrai as **607 Classes CNAE** "
            "com Grau de Risco de **1 a 4** e classifica automaticamente:\n\n"
            "- **GR 1 ou 2** → risco **Baixo**\n"
            "- **GR 3** → risco **Médio**\n"
            "- **GR 4** → risco **Alto**\n\n"
            "A NR-04 classifica por **Classe CNAE (5 dígitos)**, e o sistema "
            "faz fallback automático quando você consulta uma subclasse "
            "(7 dígitos)."
        )
        pdf_nr04 = st.file_uploader("Arquivo NR-04 ou Portaria 76/2008",
                                    type=["pdf"], key="pdf_nr04")
        if pdf_nr04:
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_nr04.read())
                caminho_tmp = tmp.name
            try:
                with st.spinner("Extraindo classes da NR-04..."):
                    dados = extrair_tabela_nr04_pdf(caminho_tmp)
                if not dados:
                    st.error(
                        "Não encontrei nenhuma Classe CNAE no PDF. "
                        "Verifique se é mesmo o Quadro I da NR-04 "
                        "(tabela com CNAE, descrição e GR de 1-4)."
                    )
                else:
                    st.success(f"✅ {len(dados)} classes CNAE extraídas.")
                    # Mostra distribuição
                    from collections import Counter
                    dist = Counter(d["grau_risco"] for d in dados)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("GR 1 (Baixo)", dist.get(1, 0))
                    c2.metric("GR 2 (Baixo)", dist.get(2, 0))
                    c3.metric("GR 3 (Médio)", dist.get(3, 0))
                    c4.metric("GR 4 (Alto)", dist.get(4, 0))
                    # Preview
                    df_preview = pd.DataFrame(dados).head(20)
                    st.dataframe(df_preview, width="stretch")
                    if st.button("💾 Importar para a matriz de risco",
                                 type="primary", key="btn_imp_nr04"):
                        res = importar_cnae_risco_em_massa(dados)
                        st.success(
                            f"🎉 Importação concluída: "
                            f"{res['inseridos']} novas + "
                            f"{res['atualizados']} atualizadas = "
                            f"{res['total']} total."
                        )
            finally:
                import os as _os
                try: _os.unlink(caminho_tmp)
                except Exception: pass

    # ================ CSV/Excel ================
    with tab_csv:
        st.markdown(
            "Faça upload de um **CSV/Excel** com as colunas:\n\n"
            "`cnae`, `descricao`, `risco` (Baixo/Médio/Alto), `observacoes`, "
            "`fonte` (opcional — ex: CGSIM-51, Municipal)"
        )
        up = st.file_uploader("Arquivo", type=["csv", "xlsx", "xls"],
                               key="upl_risco")
        if up:
            try:
                if up.name.endswith(".csv"):
                    df = pd.read_csv(up, dtype=str).fillna("")
                else:
                    df = pd.read_excel(up, dtype=str).fillna("")
                df.columns = [c.strip().lower() for c in df.columns]
                if "cnae" not in df.columns or "risco" not in df.columns:
                    st.error("Arquivo precisa ter colunas `cnae` e `risco`.")
                else:
                    atualizados = 0
                    for _, row in df.iterrows():
                        cnae = normalizar_cnae(row.get("cnae", ""))
                        risco = (row.get("risco") or "").strip().title()
                        if not cnae or risco not in ("Baixo", "Médio", "Alto"):
                            continue
                        upsert_cnae_risco(
                            cnae=cnae,
                            descricao=row.get("descricao") or None,
                            risco=risco,
                            observacoes=row.get("observacoes") or None,
                            fonte=row.get("fonte") or "CSV",
                        )
                        atualizados += 1
                    st.success(f"{atualizados} CNAEs atualizados na matriz.")
            except Exception as exc:
                st.error(f"Falha: {exc}")

    # ================ Manual ================
    with tab_manual:
        st.subheader("Adicionar / editar manualmente")
        with st.form("form_add_risco"):
            c1, c2, c3 = st.columns([2, 3, 1])
            cnae = c1.text_input(
                "CNAE *",
                help="Aceita subclasse '9999-9/99' ou classe '99.99-9'",
            )
            desc = c2.text_input("Descrição")
            risco = c3.selectbox("Risco *", ["Baixo", "Médio", "Alto"])
            cc1, cc2 = st.columns(2)
            gr = cc1.selectbox("Grau de Risco (NR-04)",
                                ["", "1", "2", "3", "4"])
            fonte = cc2.text_input("Fonte", value="Manual")
            obs = st.text_input("Observações")
            if st.form_submit_button("Salvar"):
                upsert_cnae_risco(
                    cnae=normalizar_cnae(cnae) if "/" in cnae else cnae,
                    descricao=desc, risco=risco, observacoes=obs,
                    grau_risco=int(gr) if gr else None,
                    fonte=fonte or None,
                )
                st.success("Registro salvo.")

    # ================ Consulta ================
    with tab_consulta:
        st.subheader("Consultar tabela atual")
        from database import get_conn
        with get_conn() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT cnae, descricao, risco, grau_risco, fonte "
                "FROM cnae_risco ORDER BY cnae"
            )]
        if not rows:
            st.info("Matriz de risco vazia. Suba a NR-04 na primeira aba.")
        else:
            df = pd.DataFrame(rows)
            busca = st.text_input("Buscar (CNAE ou descrição)", "")
            if busca:
                df = df[df.apply(lambda r: busca.lower() in str(r).lower(),
                                  axis=1)]
            st.caption(f"Total: **{len(df)}** CNAEs cadastrados")
            st.dataframe(df, width="stretch", height=500)


# ---------------------------------------------------------
# PÁGINA 6 — ALVARÁ DE BOMBEIROS (AVCB/CLCB)
# ---------------------------------------------------------
def pagina_bombeiros():
    st.header("🚒 Matriz IT-01 Bombeiros (CBPMESP)")
    st.caption(
        "Página de **referência e consulta** da tabela CNAE × Bombeiros "
        "(IT-01 do CBPMESP). Aqui você pesquisa se um CNAE exige AVCB/CLCB, "
        "consulta o grau de risco e edita a própria tabela IT-01. "
        "ℹ️ Para subir um PDF do AVCB/CLCB de uma empresa, "
        "vá em **📄 Documentos → 📤 Upload Central**."
    )

    tab_class, tab_tabela = st.tabs([
        "🔍 Classificador CNAE",
        "📑 Tabela IT-01 (CBPMESP)",
    ])

    # ============ (removido) Cadastro de AVCB — agora em 📄 Documentos ============
    with st.expander("ℹ️ Onde cadastrar / ver AVCB e CLCB das empresas?",
                     expanded=False):
        st.info(
            "O upload e a listagem de AVCB/CLCB das empresas foram "
            "movidos para **📄 Documentos**:\n"
            "- Upload automático de PDF: **📄 Documentos → 📤 Upload Central**\n"
            "- Listagem/renovação/exclusão: **📄 Documentos → 🚒 Bombeiros (AVCB/CLCB)**\n\n"
            "Aqui você cuida apenas da **matriz IT-01** (quem exige, qual "
            "risco, ocupação, área-limite para CLCB)."
        )

    # ============ Classificador CNAE (IT-01) ============
    with tab_class:
        st.subheader("🔍 Consulta por CNAE")
        st.caption(
            "Descobre se um CNAE exige AVCB/CLCB e qual o grau de risco "
            "de incêndio segundo a IT-01 do Corpo de Bombeiros de SP."
        )
        cnae_in = st.text_input(
            "Digite o CNAE (9999-9/99)",
            key="bomb_consulta_cnae",
            placeholder="Ex: 5611-2/01",
        )
        if cnae_in:
            cnae_norm = normalizar_cnae(cnae_in)
            r = buscar_bombeiros_cnae(cnae_norm)
            if r:
                cor = {"Alto": "🔴", "Médio": "🟡", "Baixo": "🟢"}.get(
                    r.get("grau_risco"), "⚪"
                )
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "Exige AVCB?",
                    "SIM" if r["exige_avcb"] else "NÃO",
                )
                c2.metric(
                    "Grau de risco",
                    f"{cor} {r.get('grau_risco') or '—'}",
                )
                c3.metric(
                    "Ocupação IT-01",
                    r.get("ocupacao_it01") or "—",
                )
                st.write(f"**Descrição:** {r.get('descricao') or '—'}")
                if r.get("area_limite_m2"):
                    st.info(
                        f"📐 Até **{r['area_limite_m2']:.0f} m²** "
                        "pode usar CLCB (Certificado simplificado). "
                        "Acima disso, AVCB é obrigatório."
                    )
                if r.get("observacao"):
                    st.warning(f"⚠️ {r['observacao']}")
                st.caption(f"Fonte: {r.get('fonte') or '—'}")
            else:
                st.warning(
                    f"CNAE **{cnae_norm}** não está na base. "
                    "Cadastre-o manualmente na aba **Tabela IT-01** ou "
                    "importe um CSV oficial."
                )

        st.divider()
        st.subheader("🏢 Calculadora para empresa")
        st.caption(
            "Dados a partir de um CNAE + área construída, considerando as "
            "regras do Decreto SP 63.911/2018."
        )
        cc1, cc2 = st.columns(2)
        cnae_emp = cc1.text_input(
            "CNAE da empresa", key="bomb_calc_cnae",
            placeholder="Ex: 6920-6/01",
        )
        area_emp = cc2.number_input(
            "Área construída (m²)",
            min_value=0.0, step=10.0, value=0.0, key="bomb_calc_area",
        )
        if cnae_emp and area_emp > 0:
            cnae_n = normalizar_cnae(cnae_emp)
            r = buscar_bombeiros_cnae(cnae_n)
            if not r:
                st.error(f"CNAE {cnae_n} não cadastrado.")
            else:
                limite = r.get("area_limite_m2")
                if not r["exige_avcb"]:
                    st.success(
                        "✅ Atividade **não exige AVCB/CLCB** pelo CBPMESP."
                    )
                elif limite and area_emp <= limite:
                    st.info(
                        f"📄 Pode usar **CLCB** (Certificado de Licença do "
                        f"CB). Área {area_emp:.0f} m² ≤ limite {limite:.0f} m²."
                    )
                else:
                    st.warning(
                        f"🚨 **AVCB obrigatório** — Grau: "
                        f"{r.get('grau_risco') or '—'} "
                        f"(Ocupação {r.get('ocupacao_it01') or '—'})."
                    )

    # ============ Tabela editável IT-01 ============
    with tab_tabela:
        st.subheader("📑 Tabela CNAE × Bombeiros (IT-01 / CBPMESP)")
        regs = listar_bombeiros_cnae()
        if not regs:
            st.info(
                "Nenhum CNAE cadastrado. Ele é populado automaticamente "
                "na 1ª execução; se o banco é antigo, importe um CSV."
            )
        else:
            df_b = pd.DataFrame(regs)
            # Filtros
            fc1, fc2, fc3 = st.columns(3)
            filtro_cnae = fc1.text_input(
                "Filtrar CNAE/descrição", key="bomb_filtro_cnae"
            )
            filtro_risco = fc2.selectbox(
                "Grau de risco",
                ["Todos", "Alto", "Médio", "Baixo"],
                key="bomb_filtro_risco",
            )
            filtro_exige = fc3.selectbox(
                "Exige AVCB?",
                ["Todos", "Sim", "Não"],
                key="bomb_filtro_exige",
            )
            df_f = df_b.copy()
            if filtro_cnae:
                mask = (
                    df_f["cnae"].str.contains(filtro_cnae, case=False, na=False)
                    | df_f["descricao"].fillna("").str.contains(
                        filtro_cnae, case=False, na=False
                    )
                )
                df_f = df_f[mask]
            if filtro_risco != "Todos":
                df_f = df_f[df_f["grau_risco"] == filtro_risco]
            if filtro_exige != "Todos":
                df_f = df_f[df_f["exige_avcb"] == (1 if filtro_exige == "Sim" else 0)]

            st.caption(f"Mostrando {len(df_f)} de {len(df_b)} registros")

            # Prepara colunas para edição (bool, selectbox)
            df_edit = df_f.copy()
            df_edit["exige_avcb"] = df_edit["exige_avcb"].astype(bool)
            df_edit["excluir"] = False
            cols_edit = [
                "excluir", "cnae", "descricao", "exige_avcb",
                "grau_risco", "ocupacao_it01", "area_limite_m2",
                "observacao", "fonte",
            ]
            df_edit = df_edit[cols_edit]
            edited = st.data_editor(
                df_edit,
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                column_config={
                    "excluir": st.column_config.CheckboxColumn(
                        "🗑️", help="Marcar para excluir", default=False,
                    ),
                    "cnae": st.column_config.TextColumn("CNAE", disabled=True),
                    "descricao": st.column_config.TextColumn("Descrição"),
                    "exige_avcb": st.column_config.CheckboxColumn(
                        "Exige AVCB?"
                    ),
                    "grau_risco": st.column_config.SelectboxColumn(
                        "Grau", options=["Baixo", "Médio", "Alto", "—"],
                    ),
                    "ocupacao_it01": st.column_config.TextColumn(
                        "Ocupação", help="Ex: F-3, A-2, D-1",
                    ),
                    "area_limite_m2": st.column_config.NumberColumn(
                        "Limite m² (CLCB)", min_value=0.0, step=10.0,
                    ),
                    "observacao": st.column_config.TextColumn("Observação"),
                    "fonte": st.column_config.TextColumn("Fonte"),
                },
                key="bomb_editor",
            )

            cb1, cb2 = st.columns(2)
            if cb1.button("💾 Salvar alterações", key="bomb_save",
                          type="primary"):
                n = 0
                for _, row in edited.iterrows():
                    if row.get("excluir"):
                        continue
                    upsert_bombeiros_cnae(
                        cnae=row["cnae"],
                        descricao=row.get("descricao"),
                        exige_avcb=int(bool(row.get("exige_avcb"))),
                        grau_risco=row.get("grau_risco"),
                        ocupacao_it01=row.get("ocupacao_it01"),
                        area_limite_m2=(
                            float(row["area_limite_m2"])
                            if row.get("area_limite_m2") else None
                        ),
                        observacao=row.get("observacao"),
                        fonte=row.get("fonte") or "IT-01/CBPMESP",
                    )
                    n += 1
                st.success(f"✅ {n} registros salvos.")
                st.rerun()

            marcados = [
                row["cnae"] for _, row in edited.iterrows() if row.get("excluir")
            ]
            if cb2.button(
                f"🗑️ Excluir selecionados ({len(marcados)})",
                key="bomb_del",
                disabled=not marcados,
            ):
                n = excluir_varios_bombeiros_cnae(marcados)
                st.success(f"✅ {n} registros removidos.")
                st.rerun()

        st.divider()
        with st.expander("➕ Adicionar CNAE manualmente"):
            with st.form("add_bomb_cnae"):
                cc1, cc2 = st.columns(2)
                novo_cnae = cc1.text_input("CNAE (9999-9/99) *")
                nova_desc = cc2.text_input("Descrição")
                cc3, cc4, cc5 = st.columns(3)
                novo_exige = cc3.checkbox("Exige AVCB?", value=True)
                novo_risco = cc4.selectbox(
                    "Grau de risco", ["Baixo", "Médio", "Alto"]
                )
                nova_ocup = cc5.text_input("Ocupação IT-01", placeholder="D-1")
                cc6, cc7 = st.columns(2)
                novo_limite = cc6.number_input(
                    "Limite m² (CLCB)", min_value=0.0, step=10.0, value=0.0
                )
                nova_fonte = cc7.text_input(
                    "Fonte", value="IT-01/CBPMESP"
                )
                nova_obs = st.text_area("Observação")
                if st.form_submit_button("Adicionar"):
                    cnae_n = normalizar_cnae(novo_cnae)
                    if not cnae_n:
                        st.error("CNAE inválido.")
                    else:
                        upsert_bombeiros_cnae(
                            cnae=cnae_n,
                            descricao=nova_desc or None,
                            exige_avcb=int(novo_exige),
                            grau_risco=novo_risco,
                            ocupacao_it01=nova_ocup or None,
                            area_limite_m2=novo_limite or None,
                            observacao=nova_obs or None,
                            fonte=nova_fonte or "IT-01/CBPMESP",
                        )
                        st.success(f"✅ {cnae_n} cadastrado.")
                        st.rerun()


# ---------------------------------------------------------
# PÁGINA 7 — CONFIGURAR TELEGRAM
# ---------------------------------------------------------
def pagina_telegram():
    st.header("📲 Configurar Telegram Bot")

    st.markdown(
        """
        **Passo a passo:**
        1. No Telegram, procure por **@BotFather** e envie `/newbot`.
        2. Escolha um nome e um username para o seu bot.
        3. O BotFather retornará um **TOKEN**. Copie.
        4. Abra **@userinfobot** e envie `/start` para descobrir seu **Chat ID**.
        5. Cole ambos no arquivo `.env` na raiz do projeto.
        6. Reinicie o Streamlit (`Ctrl+C` e rode novamente).

        Exemplo do `.env`:
        ```
        TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
        TELEGRAM_CHAT_ID=987654321
        ```
        """
    )

    st.info(
        f"**TOKEN atual:** `{(TELEGRAM_BOT_TOKEN[:10] + '…') if TELEGRAM_BOT_TOKEN else 'NÃO CONFIGURADO'}`"
        f"\n\n**CHAT ID atual:** `{TELEGRAM_CHAT_ID or 'NÃO CONFIGURADO'}`"
    )

    if st.button("Enviar mensagem de teste"):
        ok, err = enviar_telegram(
            "✅ Funcionou! Seu REDESIM Manager está conectado ao Telegram."
        )
        if ok:
            st.success("Mensagem enviada, confira seu Telegram.")
        else:
            st.error(f"Falha ao enviar: {err}")


# ---------------------------------------------------------
# PÁGINA 7 — LEMBRETES / TESTES
# ---------------------------------------------------------
def pagina_lembretes():
    st.header("⏰ Lembretes e Testes")
    horarios_str = HORARIO_LEMBRETE.replace(",", " e ")
    st.caption(
        f"Regra REDESIM: o CLI deve sair em até **{DIAS_VERMELHO} dias úteis**. "
        f"O scheduler envia lembretes **DIÁRIOS** às {horarios_str}.\n\n"
        f"🟡 **Alerta amarelo** a partir de {DIAS_AMARELO} dia(s) parado · "
        f"🔴 **Alerta vermelho** a partir de {DIAS_VERMELHO} dia(s) parado "
        f"(prazo estourado)."
    )

    # Busca todos a partir do limiar amarelo
    todos = processos_atrasados(DIAS_AMARELO)
    vermelhos = [p for p in todos if p["dias_parado"] >= DIAS_VERMELHO]
    amarelos = [p for p in todos
                if DIAS_AMARELO <= p["dias_parado"] < DIAS_VERMELHO]

    c1, c2 = st.columns(2)
    c1.metric(f"🟡 Em alerta (≥ {DIAS_AMARELO}d)", len(amarelos))
    c2.metric(f"🔴 Prazo estourado (≥ {DIAS_VERMELHO}d)", len(vermelhos))

    if vermelhos:
        st.error(
            f"🔴 {len(vermelhos)} processo(s) com prazo REDESIM estourado "
            f"(≥ {DIAS_VERMELHO} dias parado)."
        )
        st.dataframe(pd.DataFrame(vermelhos)[
            ["id", "razao_social", "status", "dias_parado", "ultima_movimentacao"]
        ], width="stretch", hide_index=True)

    if amarelos:
        st.warning(
            f"🟡 {len(amarelos)} processo(s) em alerta preventivo "
            f"(≥ {DIAS_AMARELO} dias parado)."
        )
        st.dataframe(pd.DataFrame(amarelos)[
            ["id", "razao_social", "status", "dias_parado", "ultima_movimentacao"]
        ], width="stretch", hide_index=True)

    if not todos:
        st.success("Nenhum processo em alerta ✅")

    st.divider()
    st.subheader("🧪 Testar envio manual")
    msg = st.text_input(
        "Mensagem",
        "⚠️ Teste manual do REDESIM Manager."
    )
    if st.button("Disparar alerta agora"):
        resultado = enviar_alerta(msg)
        if not resultado:
            st.error("Nenhum canal configurado. Configure em 'Configurar Telegram'.")
        for canal, r in resultado.items():
            if r["ok"]:
                st.success(f"{canal.upper()}: enviado ✔")
            else:
                st.error(f"{canal.upper()}: {r['erro']}")

    st.divider()
    st.subheader("⚙️ Rodar o scheduler (lembretes automáticos)")
    st.code("python scheduler.py", language="bash")
    st.caption("Abra um terminal separado nessa pasta e rode o comando acima. "
               "Ele fica em background verificando atrasos e enviando lembretes "
               f"todos os dias às {horarios_str}.")


# ---------------------------------------------------------
# PÁGINA 8 — DOCUMENTOS COM VENCIMENTO
# ---------------------------------------------------------
def _iter_todos_documentos():
    """
    Une documentos_vencimento + alvaras_bombeiros num único iterador
    com chaves padronizadas pra exibição.
    """
    linhas = []
    for d in listar_documentos_vencimento(apenas_vigentes=True):
        linhas.append({
            "id": d["id"],
            "origem": "documentos_vencimento",
            "empresa_id": d["empresa_id"],
            "razao_social": d["razao_social"],
            "cnpj": d.get("cnpj"),
            "tipo": d["tipo"],
            "numero": d.get("numero"),
            "data_emissao": d.get("data_emissao"),
            "data_vencimento": d["data_vencimento"],
            "dias_para_vencer": int(d["dias_para_vencer"]),
            "dias_alerta": d["dias_alerta"],
            "arquivo_pdf": d.get("arquivo_pdf"),
            "observacoes": d.get("observacoes"),
        })
    for a in listar_alvaras_bombeiros():
        dias = a.get("dias_para_vencer")
        linhas.append({
            "id": a["id"],
            "origem": "alvaras_bombeiros",
            "empresa_id": a["empresa_id"],
            "razao_social": a["razao_social"],
            "cnpj": a.get("cnpj"),
            "tipo": a.get("tipo") or "AVCB",
            "numero": a.get("numero"),
            "data_emissao": a.get("data_emissao"),
            "data_vencimento": a["data_vencimento"],
            "dias_para_vencer": int(dias) if dias is not None else 99999,
            "dias_alerta": 45,
            "arquivo_pdf": a.get("arquivo_pdf"),
            "observacoes": a.get("observacoes"),
            "ocupacao": a.get("ocupacao"),
            "area_construida": a.get("area_construida"),
        })
    return linhas


def _render_aba_tipo(titulo, tipos_incluidos, empresa_opts, mostrar_campos_avcb=False):
    """
    Renderiza uma aba que mostra APENAS documentos de determinados tipos.
    `tipos_incluidos` é uma tupla/lista (ex: ("Alvará Sanitário",) ou
    ("AVCB", "CLCB")).
    """
    st.subheader(titulo)
    todos = _iter_todos_documentos()
    docs = [d for d in todos if d["tipo"] in tipos_incluidos]

    if not docs:
        st.info(
            "Nenhum documento desse tipo cadastrado. Use a aba "
            "**📤 Upload Central** para enviar um PDF — o sistema "
            "identifica automaticamente e traz pra cá."
        )
        return

    # Resumo
    vencidos = [d for d in docs if d["dias_para_vencer"] < 0]
    atencao = [d for d in docs
               if 0 <= d["dias_para_vencer"] <= d["dias_alerta"]]
    ok = [d for d in docs if d["dias_para_vencer"] > d["dias_alerta"]]
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total", len(docs))
    mc2.metric("🔴 Vencidos", len(vencidos))
    mc3.metric("🟡 A vencer", len(atencao))
    mc4.metric("🟢 Em dia", len(ok))

    docs.sort(key=lambda x: x["dias_para_vencer"])
    for d in docs:
        dias = d["dias_para_vencer"]
        if dias < 0:
            icon = "🔴"
            rotulo = f"VENCIDO há {abs(dias)}d"
        elif dias <= d["dias_alerta"]:
            icon = "🟡"
            rotulo = f"vence em {dias}d"
        else:
            icon = "🟢"
            rotulo = f"vence em {dias}d"

        with st.expander(
            f"{icon} {d['razao_social']} — {d['tipo']} "
            f"#{d.get('numero') or '?'} · {d['data_vencimento']} ({rotulo})"
        ):
            c1, c2 = st.columns(2)
            c1.write(f"**CNPJ:** {d.get('cnpj') or '—'}")
            c1.write(f"**Emissão:** {d.get('data_emissao') or '—'}")
            c1.write(f"**Vencimento:** {d['data_vencimento']}")
            c2.write(f"**Nº/Protocolo:** {d.get('numero') or '—'}")
            c2.write(f"**Alerta:** {d['dias_alerta']} dias antes")
            if mostrar_campos_avcb:
                c2.write(f"**Ocupação IT-01:** {d.get('ocupacao') or '—'}")
                if d.get("area_construida"):
                    c2.write(f"**Área:** {d['area_construida']} m²")
            if d.get("arquivo_pdf"):
                st.caption(f"📎 PDF: `{d['arquivo_pdf']}`")
            if d.get("observacoes"):
                st.caption(f"📝 {d['observacoes']}")

            del_key = f"del_{d['origem']}_{d['id']}"
            if st.button("🗑️ Excluir", key=del_key):
                if d["origem"] == "alvaras_bombeiros":
                    excluir_alvara_bombeiros(d["id"])
                else:
                    excluir_documento_vencimento(d["id"])
                st.rerun()


def pagina_documentos_vencimento():
    st.header("📄 Documentos")
    st.caption(
        "Ponto único de gestão de documentos com vencimento. "
        "Suba o PDF em **📤 Upload Central**; o sistema identifica o tipo "
        "(AVCB, Alvará Sanitário, CND, FGTS, CNDT, Licença Ambiental, "
        "Contrato Social, etc.) e joga cada documento na sua aba específica. "
        "O scheduler alerta quando faltarem ≤ dias configurados."
    )

    # Cross-link do dashboard
    focus_did = st.session_state.pop("focus_documento_id", None)
    focus_aid = st.session_state.pop("focus_avcb_id", None)
    focus_dtipo = st.session_state.pop("focus_documento_tipo", None)
    if focus_did:
        st.success(
            f"🔎 Você veio do Dashboard. Documento em destaque: ID #{focus_did}"
            + (f" — abra a aba **{focus_dtipo}**." if focus_dtipo else "")
        )
    elif focus_aid:
        st.success(
            f"🔎 Você veio do Dashboard. AVCB em destaque: ID #{focus_aid} "
            "— abra a aba **🚒 Bombeiros** abaixo."
        )

    empresas = _cache_empresas()
    if not empresas:
        st.info("Cadastre uma empresa na página **Novo Processo** antes.")
        return
    empresa_opts = {f"{e['razao_social']} ({e['cnpj'] or 's/ CNPJ'})": e["id"]
                    for e in empresas}

    tabs = st.tabs([
        "📤 Upload Central",
        "📊 Painel geral",
        "🏥 Vigilância Sanitária",
        "🏢 Licença de Funcionamento",
        "🚒 Bombeiros (AVCB/CLCB)",
        "🌱 Licenças Ambientais",
        "📜 Certidões Negativas",
        "🔐 Certificado Digital",
        "📝 Contratos Sociais",
        "➕ Cadastrar manual",
    ])
    (tab_upload, tab_painel, tab_visa, tab_func, tab_bomb,
     tab_amb, tab_cnd, tab_cert, tab_contr, tab_novo) = tabs

    # =============== UPLOAD CENTRAL ===============
    with tab_upload:
        st.markdown(
            "**Ponto único de entrada.** Jogue aqui qualquer PDF "
            "(AVCB/CLCB, Alvará Sanitário, Alvará de Funcionamento, "
            "Licença Ambiental, CND Federal/Estadual/Municipal, FGTS, "
            "CNDT, Contrato Social, Certificado Digital). O sistema:\n"
            "1. Detecta o **tipo** automaticamente;\n"
            "2. Extrai **CNPJ, número, data de emissão e vencimento**;\n"
            "3. Identifica a **empresa** pelo CNPJ;\n"
            "4. Roteia o documento pra **aba específica** correspondente.\n\n"
            "AVCB/CLCB são gravados na tabela de **bombeiros** (com ocupação "
            "IT-01 e área construída). Os demais vão para **documentos com "
            "vencimento**. Em ambos, o scheduler dispara alerta."
        )
        up_doc = st.file_uploader(
            "PDF do documento",
            type=["pdf"],
            key="up_doc_central",
            accept_multiple_files=False,
        )
        if up_doc:
            import os as _os
            import tempfile
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".pdf"
            ) as tmp:
                tmp.write(up_doc.read())
                caminho_tmp = tmp.name
            try:
                with st.spinner("Lendo PDF e identificando o tipo..."):
                    info = extrair_dados_auto(caminho_tmp)

                if info.get("usou_ocr"):
                    st.info(
                        f"🔍 Usei OCR pra extrair o texto "
                        f"(idioma: {info.get('idioma_ocr') or '?'})."
                    )

                destino = info.get("destino") or "documentos_vencimento"
                tipo_detectado = info.get("tipo") or "—"

                if destino == "alvaras_bombeiros":
                    st.success(
                        f"🚒 Identificado como **{tipo_detectado}** — "
                        "vai pra aba **Bombeiros (AVCB/CLCB)**."
                    )
                else:
                    mapa_destino = {
                        "Alvará Sanitário": "🏥 Vigilância Sanitária",
                        "Alvará de Funcionamento": "🏢 Licença de Funcionamento",
                        "Licença Ambiental": "🌱 Licenças Ambientais",
                        "CND Federal": "📜 Certidões Negativas",
                        "CND Estadual": "📜 Certidões Negativas",
                        "CND Municipal": "📜 Certidões Negativas",
                        "CND FGTS": "📜 Certidões Negativas",
                        "CNDT (Trabalhista)": "📜 Certidões Negativas",
                        "Certificado Digital": "🔐 Certificado Digital",
                        "Contrato Social": "📝 Contratos Sociais",
                    }
                    aba_destino = mapa_destino.get(tipo_detectado, "📊 Painel geral")
                    st.success(
                        f"📄 Identificado como **{tipo_detectado}** — "
                        f"vai pra aba **{aba_destino}**."
                    )

                empresa_existente = _buscar_empresa_por_cnpj(info.get("cnpj"))

                st.markdown("#### 📋 Dados extraídos")
                cp1, cp2, cp3 = st.columns(3)
                cp1.metric("Tipo", tipo_detectado)
                cp2.metric("CNPJ", info.get("cnpj") or "—")
                cp3.metric("Número", info.get("numero") or "—")
                cp4, cp5 = st.columns(2)
                cp4.metric("Emissão", info.get("data_emissao") or "—")
                cp5.metric("Vencimento", info.get("data_vencimento") or "—")
                st.caption(f"Razão social no PDF: **{info.get('razao_social') or '—'}**")

                if destino == "alvaras_bombeiros":
                    cpa, cpb, cpc = st.columns(3)
                    cpa.metric("Divisão IT-01", info.get("divisao") or "—")
                    cpb.metric("Ocupação", info.get("ocupacao") or "—")
                    cpc.metric(
                        "Área (m²)",
                        f"{info.get('area_construida') or 0:.0f}"
                        if info.get("area_construida") else "—",
                    )

                if empresa_existente:
                    st.success(
                        f"✅ Empresa identificada: "
                        f"**{empresa_existente['razao_social']}** "
                        f"(ID {empresa_existente['id']})"
                    )
                elif info.get("cnpj"):
                    st.warning(
                        f"⚠️ CNPJ **{info['cnpj']}** não cadastrado. "
                        "Selecione abaixo ou cadastre a empresa em **Novo Processo**."
                    )
                else:
                    st.warning(
                        "⚠️ Não consegui extrair o CNPJ. Selecione a empresa manualmente."
                    )

                # Form de confirmação (pré-preenchido)
                st.markdown("#### ✏️ Confira e salve")
                with st.form("form_upload_central", clear_on_submit=False):
                    if empresa_existente:
                        label_empresa = (
                            f"{empresa_existente['razao_social']} "
                            f"({empresa_existente['cnpj'] or 's/ CNPJ'})"
                        )
                        idx_emp = (
                            list(empresa_opts.keys()).index(label_empresa)
                            if label_empresa in empresa_opts else 0
                        )
                    else:
                        idx_emp = 0
                    nome_empresa = st.selectbox(
                        "Empresa *",
                        list(empresa_opts.keys()),
                        index=idx_emp,
                    )

                    from datetime import datetime
                    def _para_date(s):
                        if not s:
                            return None
                        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                            try:
                                return datetime.strptime(s, fmt).date()
                            except Exception:
                                continue
                        return None

                    if destino == "alvaras_bombeiros":
                        _tipos_bomb = ["AVCB", "CLCB", "Projeto Técnico", "Outro"]
                        tipo_idx = (_tipos_bomb.index(tipo_detectado)
                                    if tipo_detectado in _tipos_bomb else 0)
                        c1, c2, c3 = st.columns(3)
                        tipo_sel = c1.selectbox("Tipo *", _tipos_bomb, index=tipo_idx)
                        numero_sel = c2.text_input(
                            "Número", value=info.get("numero") or ""
                        )
                        ocup_sel = c3.text_input(
                            "Ocupação/Divisão",
                            value=info.get("divisao") or "",
                            help="Ex: D-3, F-6, A-2",
                        )
                        c4, c5 = st.columns(2)
                        data_emi_sel = c4.date_input(
                            "Emissão",
                            value=_para_date(info.get("data_emissao")),
                            format="DD/MM/YYYY",
                        )
                        data_venc_sel = c5.date_input(
                            "Vencimento *",
                            value=_para_date(info.get("data_vencimento")),
                            format="DD/MM/YYYY",
                        )
                        area_sel = st.number_input(
                            "Área construída (m²)",
                            min_value=0.0, step=10.0,
                            value=float(info.get("area_construida") or 0.0),
                        )
                        obs_sel = st.text_area(
                            "Observações",
                            value=info.get("descricao_ocupacao") or "",
                        )

                        if st.form_submit_button("💾 Salvar AVCB/CLCB",
                                                 type="primary"):
                            if not data_venc_sel:
                                st.error("Vencimento é obrigatório.")
                            else:
                                empresa_id_sel = empresa_opts[nome_empresa]
                                pasta = _os.path.join(
                                    _os.path.dirname(__file__),
                                    "data", "alvaras_bombeiros"
                                )
                                _os.makedirs(pasta, exist_ok=True)
                                nome_arq = (
                                    f"empresa{empresa_id_sel}_"
                                    f"{data_venc_sel}_{up_doc.name}"
                                )
                                caminho_pdf_final = _os.path.join(pasta, nome_arq)
                                with open(caminho_tmp, "rb") as src, \
                                        open(caminho_pdf_final, "wb") as dst:
                                    dst.write(src.read())
                                alvara_id = criar_alvara_bombeiros(
                                    empresa_id=empresa_id_sel,
                                    tipo=tipo_sel,
                                    numero=numero_sel or None,
                                    data_emissao=(
                                        str(data_emi_sel) if data_emi_sel else None
                                    ),
                                    data_vencimento=str(data_venc_sel),
                                    arquivo_pdf=caminho_pdf_final,
                                    ocupacao=ocup_sel or None,
                                    area_construida=area_sel or None,
                                    observacoes=obs_sel or None,
                                )
                                st.success(
                                    f"✅ AVCB/CLCB #{alvara_id} cadastrado "
                                    "na aba **Bombeiros (AVCB/CLCB)**."
                                )
                                st.balloons()
                    else:
                        c1, c2, c3 = st.columns(3)
                        tipo_idx = (
                            TIPOS_DOCUMENTO_VENCIMENTO.index(tipo_detectado)
                            if tipo_detectado in TIPOS_DOCUMENTO_VENCIMENTO
                            else len(TIPOS_DOCUMENTO_VENCIMENTO) - 1
                        )
                        tipo_sel = c1.selectbox(
                            "Tipo *",
                            TIPOS_DOCUMENTO_VENCIMENTO,
                            index=tipo_idx,
                        )
                        numero_sel = c2.text_input(
                            "Número",
                            value=info.get("numero") or "",
                        )
                        dias_alerta_sel = c3.number_input(
                            "Alertar X dias antes",
                            min_value=1, max_value=365, value=45, step=1,
                        )
                        c4, c5 = st.columns(2)
                        data_emi_sel = c4.date_input(
                            "Emissão",
                            value=_para_date(info.get("data_emissao")),
                            format="DD/MM/YYYY",
                        )
                        data_venc_sel = c5.date_input(
                            "Vencimento *",
                            value=_para_date(info.get("data_vencimento")),
                            format="DD/MM/YYYY",
                        )
                        desc_sel = st.text_input(
                            "Descrição / Órgão emissor",
                            value="",
                            placeholder="Ex: Receita Federal / Prefeitura de SP",
                        )
                        obs_sel = st.text_area(
                            "Observações",
                            value=(
                                f"Razão social no PDF: "
                                f"{info.get('razao_social') or '—'}"
                            ),
                        )
                        if st.form_submit_button("💾 Salvar documento",
                                                 type="primary"):
                            if not data_venc_sel:
                                st.error("Vencimento é obrigatório.")
                            else:
                                empresa_id_sel = empresa_opts[nome_empresa]
                                pasta = _os.path.join(
                                    _os.path.dirname(__file__),
                                    "data", "documentos_vencimento"
                                )
                                _os.makedirs(pasta, exist_ok=True)
                                nome_arq = (
                                    f"empresa{empresa_id_sel}_"
                                    f"{data_venc_sel}_{up_doc.name}"
                                )
                                caminho_pdf_final = _os.path.join(pasta, nome_arq)
                                with open(caminho_tmp, "rb") as src, \
                                        open(caminho_pdf_final, "wb") as dst:
                                    dst.write(src.read())
                                doc_id = criar_documento_vencimento(
                                    empresa_id=empresa_id_sel,
                                    tipo=tipo_sel,
                                    data_vencimento=str(data_venc_sel),
                                    numero=numero_sel or None,
                                    descricao=desc_sel or None,
                                    data_emissao=(
                                        str(data_emi_sel) if data_emi_sel else None
                                    ),
                                    dias_alerta=int(dias_alerta_sel),
                                    arquivo_pdf=caminho_pdf_final,
                                    observacoes=obs_sel or None,
                                )
                                st.success(
                                    f"✅ Documento #{doc_id} roteado pra aba específica!"
                                )
                                st.balloons()
            finally:
                try:
                    _os.unlink(caminho_tmp)
                except Exception:
                    pass

    # =============== PAINEL GERAL (todos os tipos) ===============
    with tab_painel:
        docs = _iter_todos_documentos()
        if not docs:
            st.success(
                "Nenhum documento cadastrado. Use **📤 Upload Central** "
                "ou **➕ Cadastrar manual**."
            )
        else:
            df = pd.DataFrame(docs)
            df["dias_para_vencer"] = df["dias_para_vencer"].astype(int)

            vencidos = df[df["dias_para_vencer"] < 0]
            atencao = df[(df["dias_para_vencer"] >= 0)
                         & (df["dias_para_vencer"] <= df["dias_alerta"])]
            ok_ = df[df["dias_para_vencer"] > df["dias_alerta"]]

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Total vigentes", len(df))
            mc2.metric("🔴 Vencidos", len(vencidos))
            mc3.metric("🟡 A vencer (dentro do alerta)", len(atencao))
            mc4.metric("🟢 Em dia", len(ok_))

            st.subheader("Documentos a renovar (todos os tipos)")
            criticos = pd.concat([vencidos, atencao]).sort_values("dias_para_vencer")
            if criticos.empty:
                st.success("Tudo em dia ✅")
            else:
                def _estilo(row):
                    if row["dias_para_vencer"] < 0:
                        return ["background-color:#ffcccc; color:#8B0000;"] * len(row)
                    return ["background-color:#fff3cd; color:#7a5c00;"] * len(row)

                cols_view = ["razao_social", "tipo", "numero",
                             "data_vencimento", "dias_para_vencer",
                             "dias_alerta"]
                view = criticos[cols_view].rename(columns={
                    "razao_social": "Empresa",
                    "tipo": "Tipo",
                    "numero": "Número",
                    "data_vencimento": "Vencimento",
                    "dias_para_vencer": "Dias p/ vencer",
                    "dias_alerta": "Alerta (d)",
                })
                st.dataframe(view.style.apply(_estilo, axis=1),
                             width="stretch", hide_index=True)

    # =============== 🏥 VIGILÂNCIA SANITÁRIA ===============
    with tab_visa:
        _render_aba_tipo(
            "🏥 Alvarás Sanitários / Vigilância Sanitária",
            ("Alvará Sanitário",),
            empresa_opts,
        )

    # =============== 🏢 LICENÇA DE FUNCIONAMENTO ===============
    with tab_func:
        _render_aba_tipo(
            "🏢 Alvarás de Funcionamento",
            ("Alvará de Funcionamento",),
            empresa_opts,
        )

    # =============== 🚒 BOMBEIROS (AVCB/CLCB) ===============
    with tab_bomb:
        _render_aba_tipo(
            "🚒 AVCB / CLCB — Corpo de Bombeiros",
            ("AVCB", "CLCB"),
            empresa_opts,
            mostrar_campos_avcb=True,
        )

    # =============== 🌱 LICENÇAS AMBIENTAIS ===============
    with tab_amb:
        _render_aba_tipo(
            "🌱 Licenças Ambientais",
            ("Licença Ambiental",),
            empresa_opts,
        )

    # =============== 📜 CERTIDÕES NEGATIVAS ===============
    with tab_cnd:
        _render_aba_tipo(
            "📜 Certidões Negativas (CND / FGTS / CNDT)",
            ("CND Federal", "CND Estadual", "CND Municipal",
             "CND FGTS", "CNDT (Trabalhista)"),
            empresa_opts,
        )

    # =============== 🔐 CERTIFICADO DIGITAL ===============
    with tab_cert:
        _render_aba_tipo(
            "🔐 Certificados Digitais",
            ("Certificado Digital",),
            empresa_opts,
        )

    # =============== 📝 CONTRATOS SOCIAIS ===============
    with tab_contr:
        _render_aba_tipo(
            "📝 Contratos Sociais",
            ("Contrato Social",),
            empresa_opts,
        )

    # =============== ➕ CADASTRO MANUAL ===============
    with tab_novo:
        st.caption(
            "Use este formulário se preferir digitar manualmente "
            "(sem upload de PDF)."
        )
        with st.form("form_doc_venc"):
            nome = st.selectbox("Empresa *", list(empresa_opts.keys()),
                                key="man_emp")
            c1, c2, c3 = st.columns(3)
            tipo = c1.selectbox("Tipo *", TIPOS_DOCUMENTO_VENCIMENTO, key="man_tipo")
            numero = c2.text_input("Número do documento", key="man_num")
            dias_alerta = c3.number_input(
                "Alertar X dias antes",
                min_value=1, max_value=365, value=45, step=1,
                help="Padrão: 45 dias antes do vencimento",
                key="man_dias",
            )
            c4, c5 = st.columns(2)
            data_emi = c4.date_input("Data de emissão", value=None, key="man_emi")
            data_venc = c5.date_input("Data de vencimento *", value=None,
                                      key="man_venc")
            descricao = st.text_input(
                "Descrição / Órgão emissor",
                placeholder="Ex: Receita Federal / Prefeitura de São Paulo",
                key="man_desc",
            )
            obs = st.text_area("Observações", key="man_obs")
            arq = st.file_uploader("Anexar PDF (opcional)", type=["pdf"],
                                    key="man_arq")

            if st.form_submit_button("Salvar documento", type="primary"):
                if not data_venc:
                    st.error("Data de vencimento é obrigatória.")
                else:
                    caminho_pdf = None
                    if arq:
                        import os as _os
                        pasta = _os.path.join(
                            _os.path.dirname(__file__),
                            "data", "documentos_vencimento"
                        )
                        _os.makedirs(pasta, exist_ok=True)
                        empresa_id = empresa_opts[nome]
                        nome_arq = (
                            f"empresa{empresa_id}_{data_venc}_{arq.name}"
                        )
                        caminho_pdf = _os.path.join(pasta, nome_arq)
                        with open(caminho_pdf, "wb") as f:
                            f.write(arq.getvalue())
                    doc_id = criar_documento_vencimento(
                        empresa_id=empresa_opts[nome],
                        tipo=tipo,
                        data_vencimento=str(data_venc),
                        numero=numero or None,
                        descricao=descricao or None,
                        data_emissao=str(data_emi) if data_emi else None,
                        dias_alerta=int(dias_alerta),
                        arquivo_pdf=caminho_pdf,
                        observacoes=obs or None,
                    )
                    st.success(f"✅ Documento #{doc_id} cadastrado.")


# ---------------------------------------------------------
# PÁGINA 9 — ATUALIZAR NORMAS
# ---------------------------------------------------------
def _badge_status_norma(status: str, dias) -> str:
    if status == "nunca":
        return "⚪ Nunca atualizado"
    if status == "atrasado":
        return f"🔴 Desatualizado ({dias}d)"
    if status == "atencao":
        return f"🟡 Revisar ({dias}d)"
    return f"🟢 Atualizado ({dias}d)"


def pagina_atualizar_normas():
    st.header("📥 Atualizar Normas")
    st.caption(
        "Centraliza o controle de atualização das bases oficiais usadas "
        "pelo sistema. Cada órgão publica mudanças em momentos diferentes "
        "— aqui você sobe o arquivo novo, registra a versão e mantém "
        "tudo rastreado."
    )

    # ============ PAINEL DE STATUS ============
    st.subheader("📊 Status das bases")
    status = status_normas(limite_dias=180)

    # Métricas resumo
    total = len(status)
    ok = sum(1 for s in status if s["status"] == "ok")
    atencao = sum(1 for s in status if s["status"] == "atencao")
    atrasado = sum(1 for s in status if s["status"] == "atrasado")
    nunca = sum(1 for s in status if s["status"] == "nunca")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total de bases", total)
    c2.metric("🟢 Atualizadas", ok)
    c3.metric("🟡 Atenção", atencao)
    c4.metric("🔴 Desatualizadas", atrasado)
    c5.metric("⚪ Nunca importadas", nunca)

    if atrasado or nunca:
        st.warning(
            f"⚠️ {atrasado + nunca} base(s) precisam de atenção. "
            "Revise a aba correspondente abaixo."
        )

    # Tabela do status
    df_status = pd.DataFrame([
        {
            "Base": s["titulo"],
            "Órgão": s["orgao"],
            "Última atualização": s["ultima_data"] or "—",
            "Dias": s["dias"] if s["dias"] is not None else "—",
            "Versão": s["versao"] or "—",
            "Status": _badge_status_norma(s["status"], s["dias"]),
        }
        for s in status
    ])
    st.dataframe(df_status, width="stretch", hide_index=True)

    st.markdown("---")

    # ============ TABS POR BASE ============
    st.subheader("🛠️ Atualizar uma base")
    abas_titulos = [
        "📋 NR-04",
        "🏥 Vigilância CVS-SP",
        "🚒 IT-01 Bombeiros",
        "🏛️ CGSIM",
        "🧾 CONCLA / CNAE",
        "📜 Histórico",
    ]
    tab_nr04, tab_cvs, tab_it01, tab_cgsim, tab_concla, tab_hist = (
        st.tabs(abas_titulos)
    )

    # --------- NR-04 ---------
    with tab_nr04:
        _render_card_norma("nr04")
        st.markdown(
            "**Como atualizar:** use a página **📋 Matriz de Risco CNAE** "
            "para subir o PDF oficial (Quadro I da NR-04). Depois, volte "
            "aqui e registre a versão para manter o histórico."
        )
        with st.form("form_reg_nr04", clear_on_submit=True):
            st.markdown("#### 📝 Registrar atualização")
            versao = st.text_input(
                "Versão / Portaria",
                placeholder="Ex: NR-04 — Portaria 4219/2022",
                key="reg_nr04_versao",
            )
            arquivo = st.text_input(
                "Arquivo de origem",
                placeholder="Ex: nr-04-atualizada-2022.pdf",
                key="reg_nr04_arq",
            )
            registros = st.number_input(
                "Qtd. de registros importados (opcional)",
                min_value=0, value=0, step=1, key="reg_nr04_reg",
            )
            obs = st.text_area("Observações", key="reg_nr04_obs")
            if st.form_submit_button("💾 Registrar atualização",
                                     type="primary"):
                registrar_atualizacao_norma(
                    "nr04",
                    orgao=NORMAS_META["nr04"]["orgao"],
                    versao=versao or None,
                    arquivo_origem=arquivo or None,
                    registros=int(registros) if registros else None,
                    observacoes=obs or None,
                    atualizado_por="Eduardo",
                )
                st.success("✅ Registro gravado!")
                st.rerun()

    # --------- CVS-SP ---------
    with tab_cvs:
        _render_card_norma("cvs_sp")
        st.markdown(
            "**Como atualizar:** use a página **🏥 Vigilância Sanitária** "
            "para subir a nova Portaria CVS-SP. O parser extrai os CNAEs "
            "e aplica ressalvas automáticas. Depois, registre aqui."
        )
        with st.form("form_reg_cvs", clear_on_submit=True):
            st.markdown("#### 📝 Registrar atualização")
            versao = st.text_input(
                "Versão / Portaria",
                placeholder="Ex: Portaria CVS-SP 1/2024",
                key="reg_cvs_versao",
            )
            arquivo = st.text_input(
                "Arquivo de origem",
                placeholder="Ex: portaria-cvs-01-de-10-01-2024.pdf",
                key="reg_cvs_arq",
            )
            registros = st.number_input(
                "Qtd. de CNAEs importados",
                min_value=0, value=0, step=1, key="reg_cvs_reg",
            )
            obs = st.text_area("Observações", key="reg_cvs_obs")
            if st.form_submit_button("💾 Registrar atualização",
                                     type="primary"):
                registrar_atualizacao_norma(
                    "cvs_sp",
                    orgao=NORMAS_META["cvs_sp"]["orgao"],
                    versao=versao or None,
                    arquivo_origem=arquivo or None,
                    registros=int(registros) if registros else None,
                    observacoes=obs or None,
                    atualizado_por="Eduardo",
                )
                st.success("✅ Registro gravado!")
                st.rerun()

    # --------- IT-01 ---------
    with tab_it01:
        _render_card_norma("it01_cbpmesp")
        st.markdown(
            "**Como atualizar:** a IT-01 é mantida via a página "
            "**🚒 Alvará de Bombeiros → Tabela IT-01 CBPMESP**. Quando "
            "o CBPMESP publicar nova versão da Instrução Técnica, "
            "atualize os CNAEs por lá e registre aqui."
        )
        with st.form("form_reg_it01", clear_on_submit=True):
            st.markdown("#### 📝 Registrar atualização")
            versao = st.text_input(
                "Versão / Instrução",
                placeholder="Ex: IT-01 / CBPMESP 2024",
                key="reg_it01_versao",
            )
            arquivo = st.text_input(
                "Arquivo de origem",
                placeholder="Ex: IT-01-2024.pdf",
                key="reg_it01_arq",
            )
            registros = st.number_input(
                "Qtd. de CNAEs mapeados",
                min_value=0, value=0, step=1, key="reg_it01_reg",
            )
            obs = st.text_area("Observações", key="reg_it01_obs")
            if st.form_submit_button("💾 Registrar atualização",
                                     type="primary"):
                registrar_atualizacao_norma(
                    "it01_cbpmesp",
                    orgao=NORMAS_META["it01_cbpmesp"]["orgao"],
                    versao=versao or None,
                    arquivo_origem=arquivo or None,
                    registros=int(registros) if registros else None,
                    observacoes=obs or None,
                    atualizado_por="Eduardo",
                )
                st.success("✅ Registro gravado!")
                st.rerun()

    # --------- CGSIM ---------
    with tab_cgsim:
        _render_card_norma("cgsim")
        st.markdown(
            "**CGSIM:** Resoluções 59/2020 e 61/2020 definem o "
            "enquadramento de baixo risco para dispensa de licenciamento. "
            "Atualize o CSV oficial abaixo para alimentar a matriz de "
            "risco."
        )
        st.info(
            "⚙️ O importador completo (CSV CGSIM → `cnae_risco`) está "
            "no backlog. Por ora, registre a versão aqui e suba os "
            "CNAEs manualmente via **Matriz de Risco CNAE → CSV/Excel**."
        )
        with st.form("form_reg_cgsim", clear_on_submit=True):
            st.markdown("#### 📝 Registrar atualização")
            versao = st.text_input(
                "Versão / Resolução",
                placeholder="Ex: Resolução CGSIM 61/2020",
                key="reg_cgsim_versao",
            )
            arquivo = st.text_input(
                "Arquivo de origem",
                placeholder="Ex: cgsim_61_2020.csv",
                key="reg_cgsim_arq",
            )
            registros = st.number_input(
                "Qtd. de CNAEs mapeados",
                min_value=0, value=0, step=1, key="reg_cgsim_reg",
            )
            obs = st.text_area("Observações", key="reg_cgsim_obs")
            if st.form_submit_button("💾 Registrar atualização",
                                     type="primary"):
                registrar_atualizacao_norma(
                    "cgsim",
                    orgao=NORMAS_META["cgsim"]["orgao"],
                    versao=versao or None,
                    arquivo_origem=arquivo or None,
                    registros=int(registros) if registros else None,
                    observacoes=obs or None,
                    atualizado_por="Eduardo",
                )
                st.success("✅ Registro gravado!")
                st.rerun()

    # --------- CONCLA ---------
    with tab_concla:
        _render_card_norma("concla")
        st.markdown(
            "**CONCLA / IBGE:** lista mestra de subclasses CNAE. "
            "Atualizar quando o IBGE publicar nova tabela (raro — "
            "costuma ser a cada 2+ anos)."
        )
        st.info(
            "⚙️ O importador de CNAE completo (CONCLA) está no backlog. "
            "Por ora, registre a versão publicada pelo IBGE."
        )
        with st.form("form_reg_concla", clear_on_submit=True):
            st.markdown("#### 📝 Registrar atualização")
            versao = st.text_input(
                "Versão",
                placeholder="Ex: CNAE 2.3 — CONCLA 2022",
                key="reg_concla_versao",
            )
            arquivo = st.text_input(
                "Arquivo de origem",
                placeholder="Ex: cnae_subclasses_2_3.xlsx",
                key="reg_concla_arq",
            )
            registros = st.number_input(
                "Qtd. de CNAEs importados",
                min_value=0, value=0, step=1, key="reg_concla_reg",
            )
            obs = st.text_area("Observações", key="reg_concla_obs")
            if st.form_submit_button("💾 Registrar atualização",
                                     type="primary"):
                registrar_atualizacao_norma(
                    "concla",
                    orgao=NORMAS_META["concla"]["orgao"],
                    versao=versao or None,
                    arquivo_origem=arquivo or None,
                    registros=int(registros) if registros else None,
                    observacoes=obs or None,
                    atualizado_por="Eduardo",
                )
                st.success("✅ Registro gravado!")
                st.rerun()

    # --------- HISTÓRICO ---------
    with tab_hist:
        st.markdown("### 📜 Histórico de atualizações")
        filtro_base = st.selectbox(
            "Filtrar por base",
            ["(todas)"] + list(NORMAS_META.keys()),
            format_func=lambda k: (
                "Todas" if k == "(todas)" else NORMAS_META[k]["titulo"]
            ),
            key="hist_base_filter",
        )
        base_sel = None if filtro_base == "(todas)" else filtro_base
        hist = historico_atualizacoes(base_sel, limite=100)
        if not hist:
            st.info("Nenhuma atualização registrada ainda.")
        else:
            df_h = pd.DataFrame([
                {
                    "Data": h["criado_em"],
                    "Base": NORMAS_META.get(h["base"], {}).get(
                        "titulo", h["base"]
                    ),
                    "Versão": h.get("versao") or "—",
                    "Arquivo": h.get("arquivo_origem") or "—",
                    "Registros": h.get("registros") or 0,
                    "Por": h.get("atualizado_por") or "—",
                    "Observações": h.get("observacoes") or "",
                }
                for h in hist
            ])
            st.dataframe(df_h, width="stretch", hide_index=True)


def _render_card_norma(base: str):
    """Renderiza o card com status da base no topo de cada aba."""
    meta = NORMAS_META[base]
    ult = ultima_atualizacao(base)
    dias = dias_desde_atualizacao(base)

    st.markdown(f"### {meta['titulo']}")
    st.caption(f"**Órgão:** {meta['orgao']}")
    st.write(meta["descricao"])
    st.markdown(
        f"🔗 [Fonte oficial]({meta['url']})"
    )

    c1, c2, c3 = st.columns(3)
    if ult:
        c1.metric("Última atualização", ult.get("criado_em", "—"))
        c2.metric("Dias atrás", dias if dias is not None else "—")
        c3.metric("Versão", ult.get("versao") or "—")
    else:
        c1.metric("Última atualização", "Nunca")
        c2.metric("Dias atrás", "—")
        c3.metric("Versão", "—")


# ---------------------------------------------------------
# PÁGINA — EMPRESAS / REDESIM (timeline de protocolos)
# ---------------------------------------------------------
def _bolinha_status_protocolo(status: str) -> str:
    """Bolinha colorida para cada status de protocolo."""
    if status in STATUS_PROTOCOLO_OK:
        return "🟢"
    if status in STATUS_PROTOCOLO_PROBLEMA:
        return "🔴"
    if status in STATUS_PROTOCOLO_EM_ANDAMENTO:
        return "🟡"
    return "⚪"


def _badge_empresa_count(empresa_id: int) -> str:
    """Retorna '(N protocolos · último: 🟢 Aprovada)' para o seletor."""
    protocolos = listar_protocolos_empresa(empresa_id)
    if not protocolos:
        return "(sem protocolos)"
    ultimo = protocolos[0]
    b = _bolinha_status_protocolo(ultimo["status"])
    return f"({len(protocolos)} protocolos · último: {b} {ultimo['status']})"


def pagina_empresas_redesim():
    st.header("🏢 Empresas + Timeline REDESIM")
    st.caption(
        "**Consulta e manutenção** dos protocolos REDESIM por empresa. "
        "Para **criar protocolo novo**, use a página **➕ Novo Processo** — "
        "esta aqui serve para acompanhar timeline, atualizar status e "
        "cadastrar empresa avulsa."
    )

    # Cross-link do dashboard: pré-seleciona empresa via session_state
    focus_eid = st.session_state.pop("focus_empresa_id", None)

    empresas = _cache_empresas()

    tab_timeline, tab_painel, tab_nova = st.tabs([
        "📜 Timeline por empresa",
        "🔴 Painel REDESIM",
        "➕ Nova empresa (manual)",
    ])

    # ============================================================
    # ABA 1 — Timeline por empresa
    # ============================================================
    with tab_timeline:
        if not empresas:
            st.info(
                "Nenhuma empresa cadastrada ainda. Use a aba **➕ Nova empresa** "
                "ou suba um cartão CNPJ em **📄 Documentos → Upload Central**."
            )
        else:
            # Seletor de empresa — mostra razão + CNPJ + badge
            opcoes = {}
            for e in empresas:
                label = f"{e['razao_social']}"
                if e.get("cnpj"):
                    label += f" — {e['cnpj']}"
                label += f"  {_badge_empresa_count(e['id'])}"
                opcoes[label] = e

            # Se veio do Dashboard, força o seletor a vir nessa empresa
            if focus_eid is not None:
                emp_focada = next((e for e in empresas if e["id"] == focus_eid), None)
                if emp_focada:
                    st.success(
                        f"🔎 Você veio do Dashboard. Empresa em destaque: "
                        f"**{emp_focada['razao_social']}**"
                    )
                    label_focado = next(
                        (lbl for lbl, e in opcoes.items() if e["id"] == focus_eid),
                        None,
                    )
                    if label_focado:
                        st.session_state["sel_empresa_redesim"] = label_focado

            escolhida_label = st.selectbox(
                "Escolha a empresa",
                options=list(opcoes.keys()),
                key="sel_empresa_redesim",
            )
            empresa = opcoes[escolhida_label]
            empresa_id = empresa["id"]

            # --- Cartão da empresa ---
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 2])
                col1.markdown(f"**{empresa['razao_social']}**")
                col2.markdown(f"**CNPJ:** {empresa.get('cnpj') or '—'}")
                col3.markdown(
                    f"**Município/UF:** "
                    f"{empresa.get('municipio') or '—'}/{empresa.get('uf') or '—'}"
                )
                if empresa.get("endereco"):
                    st.caption(f"📍 {empresa['endereco']}")
                if empresa.get("responsavel"):
                    st.caption(f"👤 Responsável: {empresa['responsavel']}")

            st.markdown("---")

            # --- Timeline dos protocolos ---
            st.subheader("📜 Timeline REDESIM")
            st.caption(
                "🟢 Aprovada/Concluída · 🟡 Em análise/Pendente · "
                "🔴 Indeferida/Cancelada/Inativa"
            )
            protocolos = listar_protocolos_empresa(empresa_id)

            if not protocolos:
                st.info(
                    "Esta empresa ainda não tem nenhum protocolo REDESIM "
                    "registrado. Vá em **➕ Novo Processo** para cadastrar "
                    "o primeiro."
                )
            else:
                for proto in protocolos:
                    bolinha = _bolinha_status_protocolo(proto["status"])
                    sub_flag = " · 🔁 _substituído_" if proto.get("substituido_por_id") else ""
                    titulo = (
                        f"{bolinha} **{proto['tipo']}** · "
                        f"`{proto['numero_protocolo']}` · "
                        f"{proto.get('data_solicitacao') or '—'} · "
                        f"_{proto['status']}_{sub_flag}"
                    )
                    with st.expander(titulo, expanded=False):
                        if proto.get("substituido_por_id"):
                            st.info(
                                f"🔁 Este protocolo foi **substituído** pelo "
                                f"protocolo interno #{proto['substituido_por_id']}. "
                                "Permanece aqui como histórico."
                            )
                        cA, cB = st.columns(2)
                        cA.markdown(
                            f"**Tipo:** {proto['tipo']}\n\n"
                            f"**Número do protocolo:** `{proto['numero_protocolo']}`\n\n"
                            f"**Nº solicitação:** {proto.get('numero_solicitacao') or '—'}\n\n"
                            f"**Data solicitação:** {proto.get('data_solicitacao') or '—'}"
                        )
                        cB.markdown(
                            f"**Evento:** {proto.get('evento') or '—'}\n\n"
                            f"**Órgão registro:** {proto.get('orgao_registro') or '—'}\n\n"
                            f"**Status atual:** {bolinha} {proto['status']}\n\n"
                            f"**Criado em:** {proto.get('criado_em', '—')}"
                        )
                        if proto.get("observacoes"):
                            st.markdown(f"📝 **Observações:** {proto['observacoes']}")

                        st.markdown("---")
                        # Botões de ação
                        status_opcoes = (
                            STATUS_PROTOCOLO_VIABILIDADE
                            if proto["tipo"] == TIPO_PROTOCOLO_VIABILIDADE
                            else STATUS_PROTOCOLO_LICENCIAMENTO
                        )
                        st.caption(
                            "ℹ️ Ao marcar **Indeferida / Cancelada / Inativa**, "
                            "o campo abaixo fica obrigatório — anote o motivo e "
                            "como está resolvendo (erro no REDESIM → refazer; "
                            "ou vai direto no órgão)."
                        )
                        with st.form(f"form_upd_{proto['id']}"):
                            novo_status = st.selectbox(
                                "Atualizar status para",
                                options=status_opcoes,
                                index=status_opcoes.index(proto["status"])
                                if proto["status"] in status_opcoes else 0,
                                key=f"upd_status_{proto['id']}",
                            )
                            nova_obs = st.text_area(
                                "📝 Motivo / Observação",
                                value=proto.get("observacoes") or "",
                                height=90,
                                help="Obrigatório quando status = Indeferida / "
                                     "Cancelada / Inativa. Anote o que aconteceu "
                                     "e como está resolvendo.",
                                key=f"upd_obs_{proto['id']}",
                            )
                            c_ok, c_del = st.columns([1, 1])
                            salvar = c_ok.form_submit_button(
                                "💾 Salvar status", width="stretch"
                            )
                            excluir = c_del.form_submit_button(
                                "🗑️ Excluir este protocolo",
                                width="stretch",
                            )

                        if salvar:
                            obs_obrigatoria = (
                                novo_status in STATUS_PROTOCOLO_PROBLEMA
                            )
                            if (novo_status == proto["status"]
                                    and (nova_obs or "").strip()
                                    == (proto.get("observacoes") or "").strip()):
                                st.info("Nada mudou.")
                            elif obs_obrigatoria and not (nova_obs or "").strip():
                                st.error(
                                    f"⚠️ Como o status é **{novo_status}**, é "
                                    "obrigatório anotar o motivo e como está "
                                    "resolvendo. Ex: 'Erro no REDESIM, vou "
                                    "abrir novo' ou 'Vai direto no órgão'."
                                )
                            else:
                                atualizado, info_g = \
                                    atualizar_status_protocolo_com_gestta(
                                        proto["id"],
                                        novo_status,
                                        observacoes=(
                                            nova_obs.strip() or None
                                        ),
                                    )
                                if atualizado:
                                    st.success(
                                        f"✅ Status atualizado para "
                                        f"{_bolinha_status_protocolo(novo_status)} "
                                        f"**{novo_status}**."
                                        + (" Motivo registrado no histórico."
                                           if obs_obrigatoria else "")
                                    )
                                    _mostrar_feedback_gestta(
                                        info_g, novo_status,
                                    )
                                    # Pequeno delay pra usuario ler o feedback
                                    # do GESTTA antes do rerun (1.2s)
                                    import time as _time
                                    _time.sleep(1.2)
                                    st.rerun()
                                else:
                                    st.error("Falha ao atualizar protocolo.")

                        if excluir:
                            if excluir_protocolo_redesim(proto["id"]):
                                st.success("✅ Protocolo excluído.")
                                st.rerun()
                            else:
                                st.error("Falha ao excluir protocolo.")

            # --- Atalho para criar protocolo novo ---
            st.markdown("---")
            st.info(
                "💡 **Para adicionar um novo protocolo** (nova tentativa de "
                "viabilidade ou início do licenciamento), vá em "
                "**➕ Novo Processo** no menu lateral. Nessa página o sistema "
                "detecta automaticamente se a empresa já existe e oferece a "
                "opção de **substituir** os protocolos 🔴 anteriores pelo novo."
            )

    # ============================================================
    # ABA 2 — Painel REDESIM (todos os protocolos)
    # ============================================================
    with tab_painel:
        st.subheader("📜 Todos os protocolos REDESIM")
        protos_todos = listar_todos_protocolos()
        if not protos_todos:
            st.info("Nenhum protocolo REDESIM registrado ainda.")
        else:
            # Filtros
            cf1, cf2, cf3 = st.columns(3)
            filtro_tipo = cf1.selectbox(
                "Tipo",
                options=["(todos)"] + TIPOS_PROTOCOLO_REDESIM,
                key="filtro_tipo_painel",
            )
            status_unicos = sorted({p["status"] for p in protos_todos})
            filtro_status = cf2.multiselect(
                "Status",
                options=status_unicos,
                default=[],
                key="filtro_status_painel",
            )
            filtro_problema = cf3.checkbox(
                "Só problemáticos (🔴)",
                value=False,
                key="filtro_prob_painel",
            )

            filtrados = protos_todos
            if filtro_tipo != "(todos)":
                filtrados = [p for p in filtrados if p["tipo"] == filtro_tipo]
            if filtro_status:
                filtrados = [p for p in filtrados if p["status"] in filtro_status]
            if filtro_problema:
                filtrados = [
                    p for p in filtrados
                    if p["status"] in STATUS_PROTOCOLO_PROBLEMA
                ]

            st.caption(f"**{len(filtrados)}** protocolo(s) após filtros.")

            if filtrados:
                rows = []
                for p in filtrados:
                    rows.append({
                        "Situação": _bolinha_status_protocolo(p["status"]),
                        "Empresa": p.get("razao_social", "—"),
                        "CNPJ": p.get("cnpj") or "—",
                        "Tipo": p["tipo"],
                        "Protocolo": p["numero_protocolo"],
                        "Data": p.get("data_solicitacao") or "—",
                        "Evento": p.get("evento") or "—",
                        "Status": p["status"],
                    })
                df = pd.DataFrame(rows)

                def _est(row):
                    s = row["Status"]
                    if s in STATUS_PROTOCOLO_OK:
                        return ["background-color:#e8f5e9;color:#1b5e20;"] * len(row)
                    if s in STATUS_PROTOCOLO_PROBLEMA:
                        return ["background-color:#ffebee;color:#b71c1c;"] * len(row)
                    if s in STATUS_PROTOCOLO_EM_ANDAMENTO:
                        return ["background-color:#fff8e1;color:#8d6e00;"] * len(row)
                    return [""] * len(row)

                st.dataframe(
                    df.style.apply(_est, axis=1),
                    width="stretch",
                    hide_index=True,
                )

    # ============================================================
    # ABA 3 — Nova empresa (cadastro manual)
    # ============================================================
    with tab_nova:
        st.subheader("➕ Cadastrar nova empresa")
        st.caption(
            "Se a empresa ainda não está no sistema e você não tem o cartão CNPJ "
            "em PDF, cadastre manualmente aqui. Para cadastro automático, use "
            "a aba **🆔 Cartão CNPJ + Protocolo** acima."
        )
        with st.form("form_nova_empresa", clear_on_submit=True):
            razao = st.text_input("Razão social *", key="ne_razao")
            c1, c2 = st.columns(2)
            cnpj_in = c1.text_input(
                "CNPJ *",
                placeholder="99.999.999/0001-99",
                key="ne_cnpj",
            )
            resp = c2.text_input(
                "Responsável (opcional)",
                key="ne_resp",
            )
            end = st.text_input("Endereço (opcional)", key="ne_end")
            c3, c4 = st.columns([3, 1])
            mun = c3.text_input("Município (opcional)", key="ne_mun")
            uf = c4.text_input("UF", max_chars=2, key="ne_uf")

            criar = st.form_submit_button(
                "➕ Cadastrar empresa", width="stretch"
            )

        if criar:
            if not razao.strip() or not cnpj_in.strip():
                st.error("Razão social e CNPJ são obrigatórios.")
            else:
                # Verifica duplicidade
                ja_existe = buscar_empresa_por_cnpj(cnpj_in)
                if ja_existe:
                    st.warning(
                        f"⚠️ Já existe empresa com esse CNPJ: "
                        f"**{ja_existe['razao_social']}** (ID {ja_existe['id']}). "
                        f"Não cadastrarei duplicata. Use a aba Timeline para "
                        f"adicionar novos protocolos."
                    )
                else:
                    try:
                        novo_id = criar_empresa(
                            razao_social=razao.strip(),
                            cnpj=cnpj_in.strip(),
                            endereco=(end.strip() or None),
                            municipio=(mun.strip() or None),
                            uf=(uf.strip().upper() or None),
                            responsavel=(resp.strip() or None),
                        )
                        st.success(
                            f"✅ Empresa criada (ID {novo_id}). "
                            f"Agora vá na aba **Timeline** e adicione o primeiro "
                            f"protocolo REDESIM."
                        )
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Falha ao cadastrar empresa: {exc}")


# ---------------------------------------------------------
# PÁGINA: Tarefas GESTTA
# ---------------------------------------------------------
_RISCO_ICONE = {"ALTO": "🔴", "MÉDIO": "🟡", "BAIXO": "🟢"}

# Aliases esperados das colunas do XLSX do GESTTA → chaves internas
_MAPA_COLUNAS_GESTTA = {
    "tarefa_nome": ["Tarefa - Nome", "Tarefa", "Nome da tarefa"],
    "cliente_nome": ["Cliente - Nome", "Cliente", "Razão Social", "Empresa"],
    "responsavel": ["Tarefa - Responsável", "Responsável"],
    "atrasada": ["Tarefa - Atrasada?", "Atrasada?"],
    "status_gestta": ["Tarefa - Status", "Status"],
    "departamento": ["Empresa - Departamento", "Departamento"],
    "cnpj": ["Cliente - CNPJ", "CNPJ", "Empresa - CNPJ"],
}


def _normalizar_df_gestta(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia colunas do XLSX do GESTTA para as chaves internas."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    renomear = {}
    for chave, opcoes in _MAPA_COLUNAS_GESTTA.items():
        for opt in opcoes:
            if opt in df.columns:
                renomear[opt] = chave
                break
    df = df.rename(columns=renomear)
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def _renderizar_painel_destrava_tarefa(t: dict) -> None:
    """Painel inline pra cada tarefa GESTTA: histórico de anotações,
    sugestão de próximo passo, e o botão de salvar anotação.

    Decisão (Eduardo, 04/05/2026): só anotação. Conclusão/impedimento
    fica pra fazer manual no GESTTA — aqui é só pra deixar registro
    do andamento da licença.
    """
    gestta_id = t.get("gestta_id")
    tarefa_nome = t.get("tarefa_nome") or ""

    # ---- Histórico de anotações locais ----
    if gestta_id:
        anots = listar_anotacoes_locais_gestta(gestta_id)
    else:
        anots = []

    if anots:
        with st.container(border=True):
            st.markdown("**📜 Histórico de anotações**")
            for a in anots[:10]:
                tipo_icon = {
                    "NOTA": "💬", "STATUS_CHANGE": "🔄",
                    "CONCLUSAO": "✅", "IMPEDIMENTO": "🚫",
                }.get(a["tipo"], "💬")
                rep_badge = "🌐" if a.get("replicado") else "📍"
                st.markdown(
                    f"{tipo_icon} `{a['criado_em']}` {rep_badge} "
                    f"**{a.get('usuario') or 'você'}** — {a['texto']}"
                )
                if a.get("erro_replicar"):
                    st.caption(f"⚠ erro replicar: {a['erro_replicar'][:100]}")
            if len(anots) > 10:
                st.caption(f"… mais {len(anots) - 10} anotações antigas.")
            st.caption(
                "🌐 = replicado no GESTTA · 📍 = só local "
                "(GESTTA estava offline ou endpoint não mapeado)"
            )

    # ---- Sugestão de próximo passo ----
    pb = sugerir_proximo_passo(tarefa_nome)
    with st.container(border=True):
        st.markdown(
            f"**🤖 Próximo passo sugerido** "
            f"<span style='color:#6B7280; font-size:11px;'>"
            f"(playbook: {pb['chave']})</span>",
            unsafe_allow_html=True,
        )
        for i, (et, dt) in enumerate(pb["etapas"], 1):
            st.markdown(f"{i}. **{et}** — *{dt}*")
        st.info(f"💡 **Ação imediata:** {pb['primeira_acao']}")

    # ---- Caixa de anotação ----
    with st.container(border=True):
        st.markdown("**📝 Adicionar anotação na tarefa**")
        nota_key = f"gestta_nota_{t['id']}"
        nota = st.text_area(
            "Anote o pé atual da tarefa, próximas ações, contatos feitos…",
            key=nota_key,
            height=80,
            placeholder=(
                "Ex.: Liguei pro cliente, contrato chega na 6ª. "
                "Esperando assinatura do sócio."
            ),
        )

        externa = st.checkbox(
            "Visível ao cliente (deixe desmarcado pra anotação interna)",
            key=f"gestta_ext_{t['id']}",
            value=False,
        )

        if st.button(
            "💬 Salvar anotação no GESTTA",
            key=f"gestta_save_{t['id']}",
            width="stretch",
            type="primary",
            disabled=not gestta_id,
        ):
            if not (nota or "").strip():
                st.warning("Escreva alguma coisa antes.")
            else:
                _salvar_anotacao_e_replicar(
                    gestta_id, nota, tipo="NOTA", external=externa,
                )
                st.session_state[nota_key] = ""
                st.toast("Anotação salva no GESTTA ✅")
                st.rerun()

        st.caption(
            "💡 Concluir / marcar impedimento — faça direto no GESTTA. "
            "Aqui é só pra deixar registro do andamento."
        )

        if not gestta_id:
            st.caption(
                "⚠ Esta tarefa não tem `gestta_id` (provavelmente veio do "
                "import antigo via XLSX). Sem ele não dá pra replicar no "
                "GESTTA — só salva local."
            )


def _salvar_anotacao_e_replicar(
    gestta_id: str, texto: str,
    *, tipo: str = "NOTA", external: bool = False,
) -> None:
    """Salva anotação no banco local e replica no GESTTA via API.

    Endpoint validado: POST /core/customer/task/{id}/history/comment.
    Marca `replicado=0` + erro se falhar (mas mantém local).

    Args:
        external: True = visível ao cliente; False = só funcionários.
    """
    if not (texto or "").strip():
        texto = "(sem texto)"
    aid = adicionar_anotacao_local_gestta(gestta_id, texto, tipo=tipo)

    # JWT efetivo: prioriza o JWT pessoal do usuário logado, cai pro
    # global se ele ainda não cadastrou o próprio.
    from database import obter_jwt_gestta_efetivo
    from auth import usuario_atual as _u_at
    _u = _u_at() or {}
    _jwt_eff = obter_jwt_gestta_efetivo(_u.get("email"))

    if not _jwt_eff:
        marcar_anotacao_replicada(
            aid, sucesso=False,
            erro="Nenhum JWT GESTTA configurado (nem pessoal nem global).",
        )
        return

    try:
        from utils.gestta_api import GesttaClient
        cli = GesttaClient(_jwt_eff)
        cli.adicionar_comentario_tarefa(
            gestta_id, texto, external=external,
        )
        marcar_anotacao_replicada(aid, sucesso=True)
    except Exception as exc:  # noqa: BLE001
        marcar_anotacao_replicada(
            aid, sucesso=False, erro=str(exc)[:300],
        )


# =====================================================================
# Tarefas GESTTA — abas dedicadas (Regularização + Devolução)
# =====================================================================
def _renderizar_form_distrato(tarefa: dict):
    """Formulário inline para gerar termo de distrato.

    Coleta iniciativa, data de efeito e motivo, busca os dados da
    empresa vinculada (com fallback no cache de CNPJ), e gera Word + PDF
    em LICENÇAS/distratos/.
    """
    from utils.gerador_distrato import gerar_distrato
    from database import (
        buscar_empresa_por_cnpj as _bcnpj,
        cache_cnpj_get as _cache_get,
    )
    import os as _os

    tid = tarefa["id"]
    empresa_id = tarefa.get("empresa_id")
    nome_cliente = tarefa.get("cliente_nome") or "—"

    # ===== Levantamento dos dados da empresa =====
    dados_empresa = None
    if empresa_id:
        # Tenta achar dados ricos no cache de consulta CNPJ
        with st.spinner("Buscando dados da empresa..."):
            try:
                from db import get_connection as _gc
                with _gc() as conn:
                    r = conn.execute(
                        "SELECT * FROM empresas WHERE id = ?",
                        (empresa_id,),
                    ).fetchone()
                if r:
                    emp_row = dict(r)
                    cnpj = emp_row.get("cnpj") or ""
                    cached = _cache_get(cnpj) if cnpj else None
                    if cached:
                        dados_empresa = cached
                    else:
                        # Monta com o que tem no banco local
                        dados_empresa = {
                            "razao_social": emp_row.get("razao_social"),
                            "cnpj": cnpj,
                            "endereco": {
                                "logradouro": emp_row.get("endereco") or "",
                                "municipio": emp_row.get("municipio") or "",
                                "uf": emp_row.get("uf") or "",
                            },
                            "socios": [],
                        }
            except Exception as exc:
                st.warning(f"Não consegui ler dados da empresa: {exc}")

    if not dados_empresa:
        st.warning(
            "⚠️ Sem dados de empresa vinculada. Posso gerar o distrato "
            "com o NOME DO CLIENTE GESTTA, mas sem CNPJ/endereço. "
            "Pra ter os dados completos, vincule a tarefa a uma empresa "
            "no botão abaixo do card."
        )
        dados_empresa = {
            "razao_social": nome_cliente,
            "cnpj": "",
            "endereco": {},
            "socios": [],
        }

    # Mostra o que vai ser preenchido
    with st.expander("👀 Dados da empresa que serão usados", expanded=False):
        st.json({
            "razao_social": dados_empresa.get("razao_social"),
            "cnpj": dados_empresa.get("cnpj"),
            "endereco": dados_empresa.get("endereco"),
            "qtde_socios": len(dados_empresa.get("socios") or []),
        })

    # ===== Formulário =====
    fc1, fc2 = st.columns(2)
    with fc1:
        iniciativa = st.radio(
            "Iniciativa do distrato",
            options=[
                ("consensual", "🤝 Consensual (ambas concordam)"),
                ("cliente", "👤 Cliente pediu pra sair"),
                ("escritorio", "🏢 Escritório decidiu encerrar"),
            ],
            format_func=lambda x: x[1],
            key=f"distrato_inic_{tid}",
        )
    with fc2:
        from datetime import date as _date
        data_efeito = st.date_input(
            "Data de efeito",
            value=_date.today(),
            key=f"distrato_data_{tid}",
            format="DD/MM/YYYY",
        )

    motivo = st.text_area(
        "Motivo (opcional — vai entrar como observação na cláusula 2ª)",
        key=f"distrato_motivo_{tid}",
        placeholder=(
            "Ex.: Cliente migrou para o escritório XYZ por proximidade "
            "geográfica. Sem pendências de honorários."
        ),
        height=70,
    )

    bb1, bb2 = st.columns([1, 1])
    with bb1:
        if st.button(
            "🚀 Gerar Word + PDF agora",
            key=f"distrato_go_{tid}",
            type="primary",
            width="stretch",
        ):
            try:
                # Pasta de saída na workspace do usuário
                pasta = "/sessions/admiring-friendly-lovelace/mnt/LICENÇAS/distratos"
                _os.makedirs(pasta, exist_ok=True)

                with st.spinner("Gerando documento..."):
                    res = gerar_distrato(
                        dados_empresa=dados_empresa,
                        iniciativa=iniciativa[0],
                        data_efeito=str(data_efeito),
                        motivo=motivo.strip() or None,
                        pasta_destino=pasta,
                        gerar_pdf=True,
                    )

                st.success("✅ Distrato gerado!")
                # Links pros arquivos
                if res.get("pdf"):
                    st.markdown(
                        f"📄 [Abrir PDF](computer://{res['pdf']})"
                    )
                if res.get("docx"):
                    st.markdown(
                        f"📝 [Abrir Word]"
                        f"(computer://{res['docx']})"
                    )
                st.caption(
                    f"Arquivos salvos em `LICENÇAS/distratos/"
                    f"{res['filename_base']}.{{docx,pdf}}`"
                )
            except Exception as exc:
                st.error(f"Falha ao gerar: {exc}")
    with bb2:
        if st.button(
            "❌ Cancelar",
            key=f"distrato_cancel_{tid}",
            width="stretch",
        ):
            st.session_state.pop("_abrir_distrato_modal_tid", None)
            st.rerun()


def _sync_gestta_completo():
    """Sincroniza TODAS as tarefas do GESTTA do usuário logado.

    Usa o JWT pessoal (obter_jwt_gestta_efetivo). Busca tarefas em
    todos os tipos e todos os status (incluindo IMPEDIMENTO), filtrando
    pelo OWNER = nome do usuário se possível. Persiste tudo via
    upsert_tarefas_gestta_api e atualiza o `tipo` automaticamente.

    Retorna dict com {inseridas, atualizadas, total, owner_filter}.
    """
    from database import obter_jwt_gestta_efetivo, upsert_tarefas_gestta_api
    from auth import usuario_atual as _u_at
    from utils.gestta_api import GesttaClient

    _u = _u_at() or {}
    jwt = obter_jwt_gestta_efetivo(_u.get("email"))
    if not jwt:
        return {
            "erro": (
                "Sem JWT GESTTA configurado. Vá em ⚙️ Configurações "
                "→ Meu GESTTA pra cadastrar o seu token pessoal."
            )
        }

    cli = GesttaClient(jwt)
    info = cli.info_token()
    nome_usuario = (info or {}).get("user_name") or "—"

    # Busca TUDO (sem filtro de status — pega impedimento, em andamento,
    # concluída, atrasada, etc.)
    todas = []
    try:
        for t in cli.iter_tarefas(limit=100):
            todas.append(t)
    except Exception as exc:
        return {"erro": f"Falha ao buscar tarefas: {exc}"}

    # Filtra pelo owner == nome do usuário do JWT
    minhas = [
        t for t in todas
        if (((t.get("owner") or {}).get("name") or "").strip().upper()
            == nome_usuario.strip().upper())
    ]

    if not minhas:
        return {
            "total_geral": len(todas),
            "minhas": 0,
            "owner_filter": nome_usuario,
            "aviso": (
                f"Nenhuma tarefa encontrada com owner = '{nome_usuario}'. "
                f"Total geral retornado pela API: {len(todas)}. "
                f"Verifique se o nome bate exatamente com o cadastrado no "
                f"GESTTA — pode ser que apareça em formato diferente "
                f"(ex.: 'VINICIUS RAFAEL' vs 'Vinicius Rafael Queiroga')."
            ),
        }

    # Persiste no banco local
    resultado = upsert_tarefas_gestta_api(minhas)
    return {
        "total_geral": len(todas),
        "minhas": len(minhas),
        "owner_filter": nome_usuario,
        "inseridas": resultado.get("inseridas", 0),
        "atualizadas": resultado.get("atualizadas", 0),
        "matched_empresa": resultado.get("matched_empresa", 0),
    }


def _aba_regularizacao():
    """Visão focada em Licença de Funcionamento + Alvará Sanitário +
    Bombeiros. Mostra atrasadas no topo, agrupadas por tipo.
    """
    st.markdown(
        "**Tarefas de regularização** (Licença de Funcionamento, Alvará "
        "Sanitário, Bombeiros) — independente do responsável. "
        "Atrasadas aparecem primeiro pra você atacar."
    )

    # Botão de sincronização completa com GESTTA
    sb1, sb2 = st.columns([1, 3])
    with sb1:
        if st.button(
            "🔄 Sincronizar TUDO do GESTTA",
            key="btn_sync_gestta_full",
            type="primary",
            width="stretch",
            help=("Puxa via API GESTTA todas as suas tarefas "
                  "(abertas, em impedimento, atrasadas, em dia) e "
                  "atualiza o app. Usa o seu JWT pessoal."),
        ):
            with st.spinner("Sincronizando com o GESTTA…"):
                res = _sync_gestta_completo()
            if res.get("erro"):
                st.error(res["erro"])
            elif res.get("aviso"):
                st.warning(res["aviso"])
            else:
                st.success(
                    f"✅ Sincronizado! Owner filtrado: "
                    f"**{res['owner_filter']}**. "
                    f"{res['minhas']} tarefa(s) suas "
                    f"({res['inseridas']} novas, {res['atualizadas']} "
                    f"atualizadas, {res['matched_empresa']} já vinculadas "
                    f"a empresas). Total geral do escritório: "
                    f"{res['total_geral']}."
                )
                import time as _t
                _t.sleep(1.5)
                st.rerun()
    with sb2:
        st.caption(
            "💡 Clica em **Sincronizar** quando tiver criado/atualizado "
            "tarefas direto no GESTTA — assim o app puxa em tempo real. "
            "O filtro pega só as que estão com você como responsável "
            "(pelo nome do seu JWT pessoal)."
        )

    # Reclassifica tarefas antigas sem `tipo` (uma vez por carregamento)
    if not st.session_state.get("_tipos_reclassificados"):
        try:
            n = reclassificar_tipos_tarefas()
            st.session_state["_tipos_reclassificados"] = True
            if n:
                st.caption(
                    f"🔄 {n} tarefa(s) reclassificada(s) automaticamente "
                    f"pelo tipo."
                )
        except Exception:
            pass

    # Contadores por tipo
    try:
        contagem = contar_tarefas_por_tipo()
    except Exception as exc:
        st.error(f"Erro ao contar tarefas: {exc}")
        return

    TIPOS_FOCO = [
        TIPO_TAREFA_LICENCA_FUNC,
        TIPO_TAREFA_ALVARA_SANIT,
        TIPO_TAREFA_BOMBEIROS,
    ]

    # Cards-resumo
    cols = st.columns(3)
    for i, tipo_id in enumerate(TIPOS_FOCO):
        info = contagem.get(tipo_id, {"total": 0, "atrasadas": 0})
        label = TIPO_TAREFA_LABELS.get(tipo_id, tipo_id)
        cor_borda = (
            "#DC2626" if info["atrasadas"] > 0 else "#1F4FD3"
        )
        with cols[i]:
            st.markdown(
                f"<div style='background:#FFFFFF; border:1px solid #E5E9F2; "
                f"border-top:4px solid {cor_borda}; border-radius:8px; "
                f"padding:14px 16px; min-height:110px;'>"
                f"<div style='font-size:11px; font-weight:700; "
                f"text-transform:uppercase; letter-spacing:.5px; "
                f"color:#000000;'>{label}</div>"
                f"<div style='font-size:30px; font-weight:700; "
                f"color:#1A2A4A; margin:6px 0 4px;'>{info['total']}</div>"
                f"<div style='font-size:12px; color:#DC2626; "
                f"font-weight:600;'>"
                f"{'🔴 ' + str(info['atrasadas']) + ' atrasada(s)' if info['atrasadas'] else '🟢 nenhuma atrasada'}"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ===== Filtros =====
    fcol1, fcol2, fcol3 = st.columns([2, 2, 1])
    with fcol1:
        responsaveis_disponiveis = ["Todos"] + (
            listar_responsaveis_gestta() or []
        )
        resp_sel = st.selectbox(
            "Responsável",
            responsaveis_disponiveis,
            index=0,
            key="reg_resp_filter",
        )
    with fcol2:
        modo = st.radio(
            "Mostrar",
            ["Atrasadas primeiro (tudo)", "Só atrasadas",
             "Só no prazo"],
            horizontal=True,
            key="reg_modo_filter",
        )
    with fcol3:
        st.markdown("<div style='height:28px'></div>",
                    unsafe_allow_html=True)
        if st.button("🔄 Recarregar", key="btn_reload_reg",
                      width="stretch"):
            try:
                n = reclassificar_tipos_tarefas(forcar=True)
                st.success(f"Reclassificadas {n} tarefas.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    # ===== Lista filtrada =====
    apenas_atrasadas = (modo == "Só atrasadas")
    so_no_prazo = (modo == "Só no prazo")

    tarefas = listar_tarefas_gestta(
        apenas_pendentes=True,
        tipo=TIPOS_FOCO,
        responsavel=(resp_sel if resp_sel != "Todos" else None),
        apenas_atrasadas=apenas_atrasadas,
    )
    if so_no_prazo:
        tarefas = [
            t for t in tarefas
            if not (t.get("overdue") == 1 or
                    (t.get("atrasada") or "").upper()
                    in ("SIM", "YES", "TRUE", "1"))
        ]

    if not tarefas:
        st.info(
            "🎉 Nenhuma tarefa de regularização encontrada com esses "
            "filtros. Tudo limpo!"
        )
        return

    st.caption(f"**{len(tarefas)} tarefa(s)** com os filtros atuais.")

    # Agrupa por tipo pra ficar visualmente organizado
    por_tipo: dict[str, list] = {}
    for t in tarefas:
        por_tipo.setdefault(
            t.get("tipo") or "OUTROS", []
        ).append(t)

    for tipo_id in TIPOS_FOCO:
        lista_t = por_tipo.get(tipo_id, [])
        if not lista_t:
            continue
        n_atr = sum(
            1 for t in lista_t
            if t.get("overdue") == 1 or
            (t.get("atrasada") or "").upper() in ("SIM", "YES", "TRUE", "1")
        )
        label = TIPO_TAREFA_LABELS.get(tipo_id, tipo_id)
        st.markdown(
            f"### {label} · {len(lista_t)} tarefa(s)"
            + (f" · 🔴 {n_atr} atrasada(s)" if n_atr else "")
        )
        for t in lista_t:
            _render_card_tarefa_compacta(t)


def _aba_devolucoes():
    """Visão dedicada a devoluções/distratos — pra encerrar relação
    com clientes que estão saindo do escritório."""
    st.markdown(
        "**Tarefas de devolução / distrato** — clientes saindo do "
        "escritório. Use o botão **📝 Gerar contrato de distrato** "
        "em cada tarefa pra montar a documentação pronta."
    )

    try:
        contagem = contar_tarefas_por_tipo()
    except Exception as exc:
        st.error(f"Erro: {exc}")
        return

    info = contagem.get(TIPO_TAREFA_DEVOLUCAO, {"total": 0, "atrasadas": 0})
    cor = "#DC2626" if info["atrasadas"] > 0 else "#1F4FD3"

    st.markdown(
        f"<div style='background:#FFFFFF; border:1px solid #E5E9F2; "
        f"border-top:4px solid {cor}; border-radius:8px; "
        f"padding:14px 16px; max-width:300px;'>"
        f"<div style='font-size:11px; font-weight:700; "
        f"text-transform:uppercase; color:#000000;'>👋 Devoluções</div>"
        f"<div style='font-size:30px; font-weight:700; "
        f"color:#1A2A4A; margin:6px 0;'>{info['total']}</div>"
        f"<div style='font-size:12px; color:#DC2626; font-weight:600;'>"
        f"{'🔴 ' + str(info['atrasadas']) + ' atrasada(s)' if info['atrasadas'] else '🟢 nenhuma atrasada'}"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    fcol1, fcol2 = st.columns([2, 1])
    with fcol1:
        resp = ["Todos"] + (listar_responsaveis_gestta() or [])
        resp_sel = st.selectbox(
            "Responsável", resp, index=0, key="devol_resp_filter",
        )
    with fcol2:
        st.markdown("<div style='height:28px'></div>",
                    unsafe_allow_html=True)
        so_atr = st.checkbox(
            "Só atrasadas", key="devol_so_atr",
        )

    tarefas = listar_tarefas_gestta(
        apenas_pendentes=True,
        tipo=TIPO_TAREFA_DEVOLUCAO,
        responsavel=(resp_sel if resp_sel != "Todos" else None),
        apenas_atrasadas=so_atr,
    )

    if not tarefas:
        st.info(
            "Nenhuma tarefa de devolução pendente. Quando aparecer "
            "uma tarefa com termos como 'distrato', 'devolução', "
            "'encerramento', 'rescisão' no nome (no GESTTA), ela vem "
            "automaticamente pra esta aba."
        )
        return

    st.caption(f"**{len(tarefas)} tarefa(s) de devolução pendentes.**")
    for t in tarefas:
        _render_card_tarefa_compacta(t, mostrar_distrato=True)


def _render_card_tarefa_compacta(t: dict, mostrar_distrato: bool = False):
    """Card compacto pra listagem de tarefas por tipo. Mais enxuto
    que o expander gigante da aba de tarefas pendentes."""
    atrasada = (t.get("overdue") == 1 or
                (t.get("atrasada") or "").upper()
                in ("SIM", "YES", "TRUE", "1"))
    cor_borda = "#DC2626" if atrasada else "#E5E9F2"
    badge_atraso = "🔴 ATRASADA" if atrasada else "🟢 No prazo"
    cor_badge = "#DC2626" if atrasada else "#047857"
    due = t.get("due_date") or "—"
    if due and len(due) >= 10:
        due_fmt = f"{due[8:10]}/{due[5:7]}/{due[:4]}"
    else:
        due_fmt = "—"

    emp_label = (
        t.get("empresa_razao_social")
        if t.get("empresa_id") else "⚠️ sem empresa vinculada"
    )

    with st.container(border=False):
        st.markdown(
            f"<div style='background:#FFFFFF; border:1px solid #E5E9F2; "
            f"border-left:4px solid {cor_borda}; border-radius:6px; "
            f"padding:10px 14px; margin:8px 0;'>"
            f"<div style='display:flex; justify-content:space-between; "
            f"align-items:center;'>"
            f"<div style='font-weight:600; font-size:14px; "
            f"color:#1A2A4A;'>{t['tarefa_nome']}</div>"
            f"<div style='font-size:11px; color:{cor_badge}; "
            f"font-weight:700;'>{badge_atraso}</div>"
            f"</div>"
            f"<div style='font-size:13px; color:#000000; "
            f"margin-top:4px;'>"
            f"🏢 {t['cliente_nome']} · "
            f"👤 {t.get('responsavel') or '—'} · "
            f"📅 vence {due_fmt}"
            f"</div>"
            f"<div style='font-size:11px; color:#000000; "
            f"margin-top:2px;'>{emp_label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        acol1, acol2, acol3 = st.columns([1, 1, 1])
        with acol1:
            if st.button(
                "✅ Resolver",
                key=f"compact_resol_{t['id']}",
                width="stretch",
                help="Marca a tarefa como resolvida no app (não toca no GESTTA).",
            ):
                try:
                    marcar_tarefa_resolvida(t["id"])
                    st.toast("✅ Tarefa resolvida.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with acol2:
            if st.button(
                "👁️ Detalhes",
                key=f"compact_det_{t['id']}",
                width="stretch",
            ):
                st.session_state["focus_tarefa_id"] = t["id"]
                st.info(
                    "Use a aba **📋 Tarefas pendentes (todas)** acima "
                    "pra ver o painel completo desta tarefa."
                )
        with acol3:
            if mostrar_distrato:
                if st.button(
                    "📝 Gerar distrato",
                    key=f"compact_distr_{t['id']}",
                    width="stretch",
                    type="primary",
                    help="Gera Word + PDF do distrato pré-preenchido.",
                ):
                    st.session_state[
                        "_abrir_distrato_modal_tid"
                    ] = t["id"]

    # Se essa é a tarefa selecionada pra gerar distrato, mostra o modal
    if (mostrar_distrato and
            st.session_state.get("_abrir_distrato_modal_tid") == t["id"]):
        with st.container(border=True):
            st.markdown("#### 📝 Gerar Termo de Distrato")
            _renderizar_form_distrato(t)


def pagina_tarefas_gestta():
    st.header("📋 Tarefas GESTTA")
    st.caption(
        "Importa o relatório de tarefas do GESTTA (XLSX), classifica o risco "
        "(🔴 ALTO / 🟡 MÉDIO / 🟢 BAIXO), faz match com as empresas já "
        "cadastradas e permite vincular cada tarefa a um protocolo REDESIM."
    )

    focus_tid = st.session_state.pop("focus_tarefa_id", None)
    if focus_tid:
        t_focada = buscar_tarefa_gestta(focus_tid)
        if t_focada:
            st.success(
                f"🔎 Você veio do Dashboard. Tarefa em destaque: "
                f"**{t_focada['tarefa_nome']}** — {t_focada['cliente_nome']}. "
                f"Use a aba **📋 Tarefas pendentes** abaixo."
            )

    stats = estatisticas_tarefas_gestta()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📌 Pendentes", stats["total_pendentes"])
    c2.metric("🔴 ALTO",
              stats["por_risco"].get("ALTO", 0))
    c3.metric("🟡 MÉDIO", stats["por_risco"].get("MÉDIO", 0))
    c4.metric("🟢 BAIXO", stats["por_risco"].get("BAIXO", 0))
    c5.metric("✅ Resolvidas", stats["total_resolvidas"])

    if stats["sem_empresa"]:
        st.warning(
            f"⚠️ **{stats['sem_empresa']} tarefas sem empresa vinculada.** "
            "O GESTTA não exporta CNPJ — o match automático usa o nome do "
            "cliente normalizado. Cadastre a empresa em ➕ Novo Processo e "
            "use o botão **Re-tentar match** abaixo."
        )

    tab_regular, tab_devol, tab_upload, tab_lista, tab_stats = st.tabs([
        "🎯 Regularização (Licença + Alvará + Bombeiros)",
        "👋 Devoluções / Distratos",
        "📥 Importar XLSX",
        "📋 Tarefas pendentes (todas)",
        "📊 Estatísticas",
    ])

    # =====================================================
    # Aba: Regularização (foco em Licença + Alvará + Bombeiros)
    # =====================================================
    with tab_regular:
        _aba_regularizacao()

    # =====================================================
    # Aba: Devoluções
    # =====================================================
    with tab_devol:
        _aba_devolucoes()

    # -------- Aba: Importar ----------
    with tab_upload:
        st.subheader("📥 Importar relatório GESTTA")
        st.markdown(
            "No GESTTA, exporte o relatório de **tarefas atrasadas** em XLSX "
            "e suba abaixo. As colunas reconhecidas são: "
            "`Tarefa - Nome`, `Cliente - Nome`, `Tarefa - Responsável`, "
            "`Tarefa - Atrasada?`, `Tarefa - Status`, `Empresa - Departamento`."
        )
        st.info(
            "💡 **Dica:** se o GESTTA permitir acrescentar a coluna **CNPJ** "
            "no relatório, o matching empresa↔tarefa fica 100% confiável. "
            "Hoje o match é por nome normalizado (pode falhar em nomes "
            "parecidos)."
        )
        arq = st.file_uploader(
            "Arquivo XLSX do GESTTA",
            type=["xlsx", "xls"],
            key="gestta_upload",
        )
        if arq is not None:
            try:
                todas = pd.read_excel(arq, sheet_name=None)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Não consegui ler o XLSX: {exc}")
                return

            sheets = list(todas.keys())
            escolha = st.selectbox(
                "Planilha (sheet) a importar",
                sheets,
                index=0,
                key="gestta_sheet",
            )
            df_raw = todas[escolha]
            df = _normalizar_df_gestta(df_raw)

            colunas_ok = {"tarefa_nome", "cliente_nome"}
            if not colunas_ok.issubset(set(df.columns)):
                st.error(
                    "Não encontrei as colunas obrigatórias "
                    "`Tarefa - Nome` e `Cliente - Nome`. "
                    f"Colunas lidas: {list(df_raw.columns)}"
                )
                return

            # Pré-visualização com risco calculado
            preview = df.copy()
            preview[["risco", "motivo_risco"]] = preview["tarefa_nome"].apply(
                lambda t: pd.Series(classificar_risco_tarefa_gestta(t))
            )
            preview["empresa_no_banco"] = preview["cliente_nome"].apply(
                lambda n: "✅" if match_empresa_por_nome(n) else "❌"
            )

            st.caption(f"Prévia ({len(preview)} linhas):")
            st.dataframe(
                preview[[c for c in [
                    "risco", "empresa_no_banco", "tarefa_nome",
                    "cliente_nome", "responsavel", "atrasada",
                    "status_gestta", "departamento",
                ] if c in preview.columns]],
                width="stretch",
                hide_index=True,
            )

            n_auto = int((preview["empresa_no_banco"] == "✅").sum())
            st.caption(
                f"🔗 **{n_auto} / {len(preview)}** clientes já estão "
                "cadastrados no REDESIM Manager e serão vinculados "
                "automaticamente."
            )

            col_a, col_b = st.columns([1, 3])
            with col_a:
                substituir = st.checkbox(
                    "Atualizar tarefas existentes",
                    value=True,
                    help=(
                        "Se marcado, tarefas com mesmo "
                        "(tarefa, cliente, responsável) ainda não resolvidas "
                        "são atualizadas em vez de duplicadas."
                    ),
                )
            with col_b:
                if st.button(
                    f"📥 Importar {len(preview)} tarefas",
                    type="primary",
                    width="stretch",
                ):
                    registros = df.to_dict(orient="records")
                    res = importar_tarefas_gestta(
                        registros,
                        origem_arquivo=arq.name,
                        substituir_existentes=substituir,
                    )
                    st.success(
                        f"✅ Importado: {res['inseridos']} novas · "
                        f"{res['atualizados']} atualizadas · "
                        f"{res['matched']} com empresa já vinculada."
                    )
                    st.rerun()

    # -------- Aba: Lista ----------
    with tab_lista:
        st.subheader("📋 Tarefas pendentes")

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            risco_f = st.selectbox(
                "Risco", ["Todos"] + RISCOS_GESTTA, key="gestta_filt_risco",
            )
        with col_f2:
            resps = listar_responsaveis_gestta()
            resp_f = st.selectbox(
                "Responsável", ["Todos"] + resps, key="gestta_filt_resp",
            )
        with col_f3:
            sem_emp = st.checkbox("Só sem empresa", key="gestta_filt_semempresa")
        with col_f4:
            sem_prot = st.checkbox("Só sem protocolo", key="gestta_filt_semprot")

        col_aa, col_ab = st.columns([1, 3])
        with col_aa:
            if st.button(
                "🔄 Re-tentar match empresa",
                width="stretch",
                help="Tenta vincular as tarefas sem empresa a empresas "
                     "cadastradas no banco (por nome normalizado).",
            ):
                n = rematch_empresas_gestta()
                st.toast(f"✔ {n} tarefas vinculadas agora a empresas cadastradas.")
                st.rerun()

        tarefas = listar_tarefas_gestta(
            apenas_pendentes=True,
            risco=None if risco_f == "Todos" else risco_f,
            responsavel=None if resp_f == "Todos" else resp_f,
            somente_sem_empresa=sem_emp,
            somente_sem_protocolo=sem_prot,
        )

        if not tarefas:
            st.info("Nenhuma tarefa encontrada com esses filtros.")
            return

        st.caption(f"{len(tarefas)} tarefa(s).")

        empresas_cache = {e["id"]: e for e in _cache_empresas()}
        protocolos_cache = listar_todos_protocolos()

        for t in tarefas:
            risco_badge = _RISCO_ICONE.get(t["risco"], "⚪")
            emp_label = (
                f"🏢 {t['empresa_razao_social']}" if t["empresa_id"] else
                "⚠️ _sem empresa vinculada_"
            )
            prot_label = (
                f"📜 Protocolo {t['protocolo_numero']} ({t['protocolo_status']})"
                if t["protocolo_id"] else ""
            )
            titulo = (
                f"{risco_badge} **{t['tarefa_nome']}** — {t['cliente_nome']} "
                f"· resp. {t['responsavel'] or '—'}"
            )
            with st.expander(titulo):
                st.caption(t["motivo_risco"])
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Cliente GESTTA:** {t['cliente_nome']}")
                    st.markdown(f"**Vínculo:** {emp_label}")
                    if prot_label:
                        st.markdown(prot_label)
                with c2:
                    st.markdown(
                        f"**Atrasada:** {t['atrasada'] or '—'}  ·  "
                        f"**Status GESTTA:** {t['status_gestta'] or '—'}  ·  "
                        f"**Depto:** {t['departamento'] or '—'}"
                    )
                    st.caption(
                        f"Importada em {t['data_import']}"
                        + (f" — origem: {t['origem_arquivo']}"
                           if t["origem_arquivo"] else "")
                    )

                st.divider()

                # ============================================================
                # 🚀 PAINEL DESTRAVA TAREFA
                # ============================================================
                _renderizar_painel_destrava_tarefa(t)

                st.divider()

                # ---- Ações secundárias (vincular empresa/protocolo) ----
                acol1, acol2, acol3 = st.columns(3)

                # (1) Vincular empresa manualmente
                with acol1:
                    if not t["empresa_id"]:
                        opcoes_emp = [("— escolher —", None)] + [
                            (f"{e['razao_social']} ({e['cnpj'] or 's/CNPJ'})", e["id"])
                            for e in empresas_cache.values()
                        ]
                        sel = st.selectbox(
                            "Vincular à empresa cadastrada",
                            opcoes_emp,
                            format_func=lambda x: x[0],
                            key=f"gestta_vincemp_{t['id']}",
                        )
                        if st.button(
                            "🏢 Vincular empresa",
                            key=f"gestta_vincempbt_{t['id']}",
                            width="stretch",
                        ):
                            if sel[1]:
                                atualizar_tarefa_gestta(
                                    t["id"], empresa_id=sel[1]
                                )
                                st.toast("Empresa vinculada.")
                                st.rerun()
                            else:
                                st.warning("Escolha uma empresa primeiro.")
                    else:
                        if st.button(
                            "↪️ Ver timeline da empresa",
                            key=f"gestta_abretime_{t['id']}",
                            width="stretch",
                            help="Use o menu 🏢 Empresas / REDESIM para ver o "
                                 "histórico completo de protocolos.",
                        ):
                            st.info(
                                "Abra manualmente a página **🏢 Empresas / "
                                f"REDESIM** e busque por "
                                f"_{t['empresa_razao_social']}_."
                            )

                # (2) Vincular protocolo existente
                with acol2:
                    if t["empresa_id"]:
                        prots_da_emp = [
                            p for p in protocolos_cache
                            if p["empresa_id"] == t["empresa_id"]
                        ]
                        opcoes_prot = [("— escolher —", None)] + [
                            (f"{p['numero_protocolo']} "
                             f"({p['tipo']} / {p['status']})", p["id"])
                            for p in prots_da_emp
                        ]
                        sel_p = st.selectbox(
                            "Vincular a protocolo existente",
                            opcoes_prot,
                            format_func=lambda x: x[0],
                            key=f"gestta_vincprot_{t['id']}",
                        )
                        if st.button(
                            "📜 Vincular protocolo",
                            key=f"gestta_vincprotbt_{t['id']}",
                            width="stretch",
                            disabled=not prots_da_emp,
                        ):
                            if sel_p[1]:
                                atualizar_tarefa_gestta(
                                    t["id"], protocolo_id=sel_p[1]
                                )
                                st.toast("Protocolo vinculado.")
                                st.rerun()
                            else:
                                st.warning("Escolha um protocolo primeiro.")
                    else:
                        st.caption("Vincule uma empresa primeiro.")

                # (3) Resolver / excluir
                with acol3:
                    if st.button(
                        "✅ Marcar como resolvida",
                        key=f"gestta_resolv_{t['id']}",
                        width="stretch",
                        type="primary",
                    ):
                        marcar_tarefa_resolvida(t["id"], True)
                        st.toast("Tarefa resolvida.")
                        st.rerun()
                    if st.button(
                        "🗑 Excluir",
                        key=f"gestta_del_{t['id']}",
                        width="stretch",
                    ):
                        excluir_tarefa_gestta(t["id"])
                        st.toast("Tarefa excluída.")
                        st.rerun()

    # -------- Aba: Estatísticas ----------
    with tab_stats:
        st.subheader("📊 Estatísticas")
        stats2 = estatisticas_tarefas_gestta()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Por risco**")
            df_risco = pd.DataFrame(
                [{"Risco": r, "Qtd": stats2["por_risco"].get(r, 0)}
                 for r in RISCOS_GESTTA]
            )
            st.dataframe(df_risco, width="stretch", hide_index=True)
        with c2:
            st.markdown("**Por responsável**")
            df_resp = pd.DataFrame(
                [{"Responsável": k, "Qtd": v}
                 for k, v in sorted(
                     stats2["por_responsavel"].items(),
                     key=lambda x: -x[1])]
            )
            st.dataframe(df_resp, width="stretch", hide_index=True)

        st.markdown("**Cobertura**")
        cc1, cc2 = st.columns(2)
        cc1.metric(
            "Tarefas com empresa cadastrada",
            stats2["total_pendentes"] - stats2["sem_empresa"],
        )
        cc2.metric("Tarefas sem empresa", stats2["sem_empresa"])


# ---------------------------------------------------------
# PÁGINA: Pendências Gerais
# ---------------------------------------------------------
_PRIORIDADE_ICONE = {"Alta": "🔴", "Média": "🟡", "Baixa": "🟢"}
_TIPO_MOV_LABEL = {
    "nota": "📝 Nota", "status": "🔄 Status",
    "contato": "📞 Contato", "retorno": "↩️ Retorno",
}


def pagina_pendencias():
    st.header("📌 Pendências Gerais")
    st.caption(
        "Use esta aba para qualquer assunto que precise de acompanhamento "
        "fora do REDESIM: malha fina, retorno de cliente, processos "
        "administrativos, follow-ups. O sistema alerta as pendências "
        "que estão paradas há muito tempo ou cujo prazo venceu."
    )

    # Cross-link do dashboard: se chegou com focus_pendencia_id, mostra
    # destaque informativo no topo (e o expander dela abre automaticamente).
    focus_pid = st.session_state.pop("focus_pendencia_id", None)
    if focus_pid:
        p_focada = buscar_pendencia(focus_pid)
        if p_focada:
            st.success(
                f"🔎 Você veio do Dashboard. Pendência em destaque: "
                f"**{p_focada['assunto']}** — {p_focada['razao_social']}. "
                f"O item está expandido na aba **📋 Abertas** abaixo."
            )
            st.session_state["_pend_focado"] = focus_pid

    stats = estatisticas_pendencias()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📌 Abertas", stats["abertas"])
    c2.metric("🔴 Alta", stats["por_prioridade"].get("Alta", 0))
    c3.metric("🟡 Média", stats["por_prioridade"].get("Média", 0))
    c4.metric("✅ Resolvidas", stats["resolvidas"])

    tab_lista, tab_nova, tab_resolv = st.tabs([
        "📋 Abertas", "➕ Nova pendência", "✅ Resolvidas",
    ])

    # ===================== Aba: Lista =====================
    with tab_lista:
        empresas_cache = _cache_empresas()
        opc_emp = [(0, "— todas —")] + [(e["id"], e["razao_social"])
                                         for e in empresas_cache]

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            prio_f = st.selectbox(
                "Prioridade",
                ["Todas"] + PRIORIDADES_PENDENCIA,
                key="pend_prio_f",
            )
        with col_f2:
            status_abertos = [s for s in STATUS_PENDENCIA
                              if s not in {"Resolvida", "Cancelada"}]
            stat_f = st.selectbox(
                "Status",
                ["Todos"] + status_abertos,
                key="pend_stat_f",
            )
        with col_f3:
            emp_f = st.selectbox(
                "Empresa",
                opc_emp,
                format_func=lambda x: x[1],
                key="pend_emp_f",
            )
        with col_f4:
            so_alerta = st.checkbox("Só em alerta (🟡/🔴)", key="pend_so_alerta")

        pendencias = listar_pendencias(
            apenas_abertas=True,
            prioridade=None if prio_f == "Todas" else prio_f,
            status=None if stat_f == "Todos" else stat_f,
            empresa_id=None if emp_f[0] == 0 else emp_f[0],
            somente_atrasadas=so_alerta,
        )

        if not pendencias:
            st.info("Nenhuma pendência aberta com esses filtros.")
        else:
            st.caption(f"{len(pendencias)} pendência(s).")
            _pend_focado = st.session_state.get("_pend_focado")
            for p in pendencias:
                titulo = (
                    f"{p['alerta']} **{p['assunto']}** — "
                    f"{p['razao_social']} · {_PRIORIDADE_ICONE.get(p['prioridade'], '')}"
                    f" {p['prioridade']}"
                )
                _expandir = (_pend_focado is not None and p["id"] == _pend_focado)
                with st.expander(titulo, expanded=_expandir):
                    cm1, cm2, cm3, cm4 = st.columns(4)
                    cm1.metric("Parada", f"{p['dias_parado']}d")
                    if p["data_limite"]:
                        d = p["dias_para_prazo"]
                        cm2.metric(
                            "Prazo",
                            ("vencido " + str(abs(d)) + "d") if d is not None and d < 0
                            else (str(d) + "d") if d is not None else "—"
                        )
                    else:
                        cm2.metric("Prazo", "sem prazo")
                    cm3.metric("Status", p["status"])
                    cm4.metric("Aberta em", p["data_inicio"])

                    if p.get("descricao"):
                        st.markdown(f"**Descrição:** {p['descricao']}")
                    st.caption(
                        f"Empresa: {p['razao_social']}"
                        + (f" · CNPJ: {p['cnpj']}" if p.get("cnpj") else "")
                    )

                    # Timeline de movimentos
                    movs = listar_movimentos_pendencia(p["id"])
                    if movs:
                        with st.container(border=True):
                            st.caption("**Histórico:**")
                            for m in movs:
                                st.markdown(
                                    f"{_TIPO_MOV_LABEL.get(m['tipo'], m['tipo'])} "
                                    f"`{m['criado_em']}` — {m['texto']}"
                                )

                    st.divider()
                    # Form: nova nota
                    with st.form(f"pend_nota_form_{p['id']}", border=False):
                        cn1, cn2 = st.columns([3, 1])
                        with cn1:
                            nova_nota = st.text_input(
                                "Adicionar nota / contato",
                                key=f"pend_nota_{p['id']}",
                                placeholder="ex.: Liguei na Receita, retornar segunda",
                            )
                        with cn2:
                            tipo_nota = st.selectbox(
                                "Tipo",
                                ["nota", "contato", "retorno"],
                                key=f"pend_tipo_{p['id']}",
                            )
                        if st.form_submit_button(
                            "💬 Registrar",
                            width="stretch",
                        ):
                            if nova_nota.strip():
                                adicionar_movimento_pendencia(
                                    p["id"], nova_nota, tipo=tipo_nota,
                                )
                                st.toast("Nota registrada.")
                                st.rerun()
                            else:
                                st.warning("Escreva alguma coisa antes.")

                    # Ações principais
                    a1, a2, a3, a4 = st.columns(4)
                    with a1:
                        novo_stat = st.selectbox(
                            "Mudar status",
                            STATUS_PENDENCIA,
                            index=STATUS_PENDENCIA.index(p["status"]),
                            key=f"pend_st_{p['id']}",
                        )
                        if st.button("Aplicar status",
                                     key=f"pend_st_bt_{p['id']}",
                                     width="stretch"):
                            atualizar_status_pendencia(p["id"], novo_stat)
                            st.toast(f"Status: {novo_stat}.")
                            st.rerun()
                    with a2:
                        nova_prio = st.selectbox(
                            "Prioridade",
                            PRIORIDADES_PENDENCIA,
                            index=PRIORIDADES_PENDENCIA.index(p["prioridade"]),
                            key=f"pend_pr_{p['id']}",
                        )
                        if st.button("Aplicar prioridade",
                                     key=f"pend_pr_bt_{p['id']}",
                                     width="stretch"):
                            atualizar_pendencia(p["id"], prioridade=nova_prio)
                            st.toast(f"Prioridade: {nova_prio}.")
                            st.rerun()
                    with a3:
                        if st.button(
                            "✅ Resolver",
                            key=f"pend_res_{p['id']}",
                            width="stretch",
                            type="primary",
                        ):
                            resolver_pendencia(p["id"])
                            st.toast("Pendência resolvida.")
                            st.rerun()
                    with a4:
                        if st.button(
                            "🗑 Excluir",
                            key=f"pend_del_{p['id']}",
                            width="stretch",
                        ):
                            excluir_pendencia(p["id"])
                            st.toast("Pendência excluída.")
                            st.rerun()

    # ===================== Aba: Nova pendência =====================
    with tab_nova:
        st.subheader("➕ Nova pendência")
        st.caption(
            "Escolha como identificar o cliente — pode ser uma empresa "
            "cadastrada, criar uma nova, ou um serviço avulso (PF / sem CNPJ)."
        )

        modo = st.radio(
            "Tipo de cadastro",
            [
                "📄 Subir Cartão CNPJ (PDF)",
                "🏢 Empresa já cadastrada",
                "✏️ Cadastrar empresa nova (CNPJ + Razão Social)",
                "🆓 Serviço avulso / Pessoa Física (sem CNPJ)",
            ],
            key="pend_modo",
            horizontal=False,
        )

        # estado a alimentar pelos diferentes modos
        emp_id_escolhida: int | None = None
        cnpj_extraido: str | None = None
        razao_extraida: str | None = None
        cnpj_manual: str | None = None
        razao_manual: str | None = None
        cliente_avulso: str | None = None

        # ---------- Modo 1: Cartão CNPJ ----------
        if modo.startswith("📄"):
            with st.container(border=True):
                arq_pdf = st.file_uploader(
                    "Cartão CNPJ em PDF",
                    type=["pdf"],
                    key="pend_cnpj_pdf",
                )
                if arq_pdf is not None:
                    try:
                        dados = extrair_dados_cartao_cnpj(arq_pdf.read())
                        cnpj_extraido = dados.get("cnpj")
                        razao_extraida = dados.get("razao_social")
                        if cnpj_extraido:
                            st.success(
                                f"📄 PDF lido: **{razao_extraida}** "
                                f"· {cnpj_extraido}"
                            )
                            achada = buscar_empresa_por_cnpj(cnpj_extraido)
                            if achada:
                                emp_id_escolhida = achada["id"]
                                st.info(
                                    f"✅ Empresa já cadastrada (id {achada['id']})"
                                )
                            else:
                                st.warning(
                                    "Empresa nova — será criada ao salvar."
                                )
                        else:
                            st.error(
                                "Não consegui extrair o CNPJ. Tente outro modo."
                            )
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Erro ao processar PDF: {exc}")

        # ---------- Modo 2: Empresa cadastrada ----------
        elif modo.startswith("🏢"):
            with st.container(border=True):
                empresas = _cache_empresas()
                if not empresas:
                    st.warning(
                        "Nenhuma empresa cadastrada ainda. Use outro modo "
                        "para começar."
                    )
                else:
                    opc = [(0, "— escolher —")] + [
                        (e["id"], f"{e['razao_social']} ({e['cnpj'] or 's/CNPJ'})")
                        for e in empresas
                    ]
                    sel = st.selectbox(
                        "Empresa",
                        opc,
                        format_func=lambda x: x[1],
                        key="pend_emp_sel",
                    )
                    if sel[0]:
                        emp_id_escolhida = sel[0]

        # ---------- Modo 3: Cadastrar empresa nova ----------
        elif modo.startswith("✏️"):
            with st.container(border=True):
                cnpj_manual = st.text_input(
                    "CNPJ *",
                    placeholder="00.000.000/0000-00",
                    key="pend_cnpj_manual",
                )
                razao_manual = st.text_input(
                    "Razão Social *",
                    placeholder="ACME Comércio LTDA",
                    key="pend_razao_manual",
                )
                if cnpj_manual:
                    achada = buscar_empresa_por_cnpj(cnpj_manual)
                    if achada:
                        emp_id_escolhida = achada["id"]
                        st.info(
                            f"⚠️ CNPJ já cadastrado como "
                            f"**{achada['razao_social']}** (id {achada['id']}). "
                            "Vou vincular a pendência a essa empresa."
                        )

        # ---------- Modo 4: Serviço avulso / PF ----------
        else:  # 🆓
            with st.container(border=True):
                cliente_avulso = st.text_input(
                    "Nome do cliente *",
                    placeholder="ex.: João da Silva (PF) ou MEI Costa Norte",
                    key="pend_cliente_avulso",
                )
                st.caption(
                    "Para serviços avulsos sem CNPJ — pessoas físicas, MEIs "
                    "que não estão na sua base, ou serviços pontuais. Não "
                    "cria empresa no sistema."
                )

        st.divider()

        # ---------- Form de detalhes (comum a todos os modos) ----------
        with st.form("pend_nova_form"):
            st.markdown("**Detalhes da pendência**")
            assunto = st.text_input(
                "Assunto *",
                placeholder="ex.: Malha fina IRPF 2024",
                key="pend_form_assunto",
            )
            descricao = st.text_area(
                "Descrição (opcional)",
                placeholder="Detalhes do caso, documentos esperados, etc.",
                height=80,
                key="pend_form_descricao",
            )
            colp1, colp2, colp3 = st.columns(3)
            with colp1:
                prioridade = st.selectbox(
                    "Prioridade", PRIORIDADES_PENDENCIA,
                    index=1,
                    key="pend_form_prio",
                )
            with colp2:
                tem_prazo = st.checkbox("Tem prazo final?", value=False,
                                        key="pend_form_temprazo")
                data_limite = None
                if tem_prazo:
                    data_limite = st.date_input(
                        "Data limite",
                        value=date.today(),
                        key="pend_form_prazo",
                    ).strftime("%Y-%m-%d")
            with colp3:
                dias_alerta = st.number_input(
                    "Alerta após N dias parado",
                    min_value=1, max_value=90, value=7, step=1,
                    key="pend_form_alerta",
                    help="A pendência entra em 🟡 se ficar este nº de dias "
                         "sem nova movimentação.",
                )

            ok = st.form_submit_button(
                "📌 Criar pendência",
                type="primary",
                width="stretch",
            )
            if ok:
                if not assunto.strip():
                    st.error("Informe o assunto.")
                    st.stop()

                # Validações por modo
                if modo.startswith("📄"):
                    if not (cnpj_extraido and razao_extraida) and not emp_id_escolhida:
                        st.error("Suba o Cartão CNPJ válido antes de criar.")
                        st.stop()
                elif modo.startswith("🏢"):
                    if not emp_id_escolhida:
                        st.error("Escolha uma empresa cadastrada.")
                        st.stop()
                elif modo.startswith("✏️"):
                    if not (cnpj_manual or "").strip() or not (razao_manual or "").strip():
                        st.error("Preencha CNPJ e Razão Social.")
                        st.stop()
                else:  # 🆓
                    if not (cliente_avulso or "").strip():
                        st.error("Informe o nome do cliente avulso.")
                        st.stop()

                # Cria empresa se necessário
                if modo.startswith("📄") and not emp_id_escolhida and cnpj_extraido:
                    emp_id_escolhida = criar_empresa(
                        razao_extraida or "(sem nome)",
                        cnpj=cnpj_extraido,
                    )
                elif modo.startswith("✏️") and not emp_id_escolhida:
                    emp_id_escolhida = criar_empresa(
                        razao_manual.strip(), cnpj=cnpj_manual.strip(),
                    )

                pid = criar_pendencia(
                    empresa_id=emp_id_escolhida,
                    cliente_avulso=cliente_avulso,
                    assunto=assunto,
                    descricao=descricao or None,
                    prioridade=prioridade,
                    data_limite=data_limite,
                    dias_alerta=int(dias_alerta),
                )
                st.success(f"✅ Pendência #{pid} criada.")
                st.rerun()

    # ===================== Aba: Resolvidas =====================
    with tab_resolv:
        st.subheader("✅ Pendências resolvidas / canceladas")
        resolvidas = listar_pendencias(apenas_abertas=False)
        resolvidas = [p for p in resolvidas if p["resolvida"]]
        if not resolvidas:
            st.info("Nenhuma pendência fechada ainda.")
        else:
            df = pd.DataFrame([{
                "ID": p["id"],
                "Empresa": p["razao_social"],
                "Assunto": p["assunto"],
                "Prioridade": p["prioridade"],
                "Status": p["status"],
                "Aberta em": p["data_inicio"],
                "Atualizada em": p["atualizado_em"],
            } for p in resolvidas])
            st.dataframe(df, width="stretch", hide_index=True)


# ---------------------------------------------------------
# PÁGINA: 🔬 Consultor de CNAE (rica + verificação Cowork)
# ---------------------------------------------------------
def _badge_resposta(label: str, valor: str, cor: str) -> str:
    return f"""
      <span style="
        display:inline-block; padding:4px 10px; border-radius:8px;
        background:{cor}22; color:{cor}; font-weight:700; font-size:13px;
        border: 1px solid {cor}55;
      ">{label}: {valor}</span>
    """


def _card_area(icone: str, titulo: str, cor: str,
               status_label: str, conteudo_html: str,
               fonte: str | None = None) -> str:
    fonte_html = (
        f'<div class="card-area-fonte">⚖️ <i>{fonte}</i></div>'
    ) if fonte else ""
    return f"""
      <div class="card-area">
        <div class="card-area-head">
          <div class="card-area-titulo">{icone} {titulo}</div>
          <span class="card-area-badge" style="background:{cor};">{status_label}</span>
        </div>
        <div class="card-area-body">{conteudo_html}</div>
        {fonte_html}
      </div>
    """


# =====================================================================
# WIZARD: Empresa existente / Empresa nova
# =====================================================================
def _wizard_empresa_existente():
    """Recebe CNPJ → consulta BrasilAPI → cruza com base local."""
    st.markdown(
        "**Tem CNPJ?** Cole abaixo. Eu busco na Receita, leio o CNAE "
        "principal e secundários, e gero um **checklist completo** do "
        "que essa empresa precisa estar cadastrada (com link oficial "
        "pra cada órgão)."
    )
    c1, c2 = st.columns([3, 1])
    with c1:
        cnpj_in = st.text_input(
            "CNPJ",
            placeholder="00.000.000/0000-00",
            key="wiz_cnpj_input",
        ).strip()
    with c2:
        st.markdown("<div style='height:28px'></div>",
                    unsafe_allow_html=True)
        bt_analisar = st.button(
            "🔍 Analisar",
            type="primary", width="stretch",
            key="btn_wiz_analisar_cnpj",
        )

    if not cnpj_in:
        st.info("Cole o CNPJ pra começar.")
        return

    if not bt_analisar and st.session_state.get(
            "_wiz_last_cnpj") != cnpj_in:
        return

    st.session_state["_wiz_last_cnpj"] = cnpj_in

    from utils.cnpj_api import (
        consultar_cnpj, CNPJNaoEncontrado, CNPJApiError,
        cnpj_valido, formatar_cnpj,
    )
    from database import (
        analisar_empresa_completa, cache_cnpj_get,
    )

    if not cnpj_valido(cnpj_in):
        st.error(
            "CNPJ inválido (dígitos verificadores não batem). "
            "Confira o número."
        )
        return

    # Mostra se vai usar cache
    cache_hit = cache_cnpj_get(cnpj_in)
    if cache_hit:
        st.caption(
            f"⚡ Usando cache local de "
            f"`{cache_hit.get('consultado_em', '—')[:10]}` "
            f"(fonte: {cache_hit.get('fonte', '—')}). "
            f"Use o botão 'Recarregar do zero' pra forçar nova consulta."
        )
        recarregar = st.button(
            "🔄 Recarregar do zero (ignora cache)",
            key="btn_wiz_recarregar_cnpj",
        )
        if recarregar:
            try:
                dados = consultar_cnpj(cnpj_in)
                from database import cache_cnpj_set
                cache_cnpj_set(cnpj_in, dados)
                st.rerun()
            except Exception as exc:
                st.error(f"Falha ao recarregar: {exc}")

    with st.spinner("Consultando Receita e analisando CNAEs..."):
        try:
            rel = analisar_empresa_completa(cnpj_in)
        except CNPJNaoEncontrado:
            st.error(
                f"❌ CNPJ {formatar_cnpj(cnpj_in)} não encontrado "
                "na base da Receita."
            )
            return
        except CNPJApiError as exc:
            st.error(f"Falha ao consultar: {exc}")
            return
        except Exception as exc:
            st.error(f"Erro inesperado: {exc}")
            return

    _render_relatorio_empresa(rel)


def _wizard_empresa_nova():
    """Recebe lista de CNAEs pretendidos e mostra checklist pré-abertura."""
    st.markdown(
        "**Empresa ainda não existe** — você quer abrir e está pensando "
        "em quais CNAEs colocar. Liste abaixo (um por linha) e eu mostro "
        "tudo que precisa preparar **antes** de protocolar a abertura."
    )
    cnaes_in = st.text_area(
        "CNAEs pretendidos (um por linha — principal primeiro)",
        placeholder=(
            "ex.:\n4711-3/02\n4729-6/99\n9602-5/01"
        ),
        height=120,
        key="wiz_cnaes_novos_input",
    ).strip()

    uf_in = st.selectbox(
        "UF onde a empresa vai abrir",
        ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "PE", "CE",
         "GO", "DF", "ES", "MS", "MT", "PA", "MA", "RN", "AL",
         "SE", "PI", "PB", "AM", "RO", "AC", "RR", "AP", "TO"],
        index=0,
        key="wiz_nova_uf",
    )
    bt_nova = st.button(
        "📋 Gerar checklist de pré-abertura",
        type="primary", width="stretch",
        key="btn_wiz_nova",
    )

    if not bt_nova:
        return

    lista = [
        ln.strip() for ln in cnaes_in.split("\n") if ln.strip()
    ]
    if not lista:
        st.warning("Liste pelo menos 1 CNAE.")
        return

    from database import analisar_cnaes_pretendidos
    with st.spinner("Analisando CNAEs e montando checklist..."):
        try:
            rel = analisar_cnaes_pretendidos(lista, uf=uf_in)
        except Exception as exc:
            st.error(f"Erro: {exc}")
            return

    _render_relatorio_empresa(rel)


def _render_relatorio_empresa(rel: dict):
    """Renderiza o relatório completo de uma empresa (nova ou existente)."""
    emp = rel.get("empresa") or {}
    is_nova = rel.get("is_nova", False)

    # ===== HEADER DA EMPRESA =====
    if is_nova:
        st.markdown(
            "<div class='cnae-header'>"
            "<div class='cnae-label'>EMPRESA NOVA — Pré-abertura</div>"
            "<div class='cnae-codigo'>(ainda sem CNPJ)</div>"
            f"<div class='cnae-desc'>UF pretendida: "
            f"<b>{(emp.get('endereco') or {}).get('uf', '?')}</b> · "
            f"{rel.get('total_cnaes', 0)} CNAEs analisados</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        from utils.cnpj_api import formatar_cnpj
        situacao = emp.get("situacao", "?")
        cor_situacao = {
            "ATIVA": "#047857",
            "BAIXADA": "#DC2626",
            "INAPTA": "#DC2626",
            "SUSPENSA": "#D97706",
            "NULA": "#DC2626",
        }.get(situacao, "#000000")
        end = emp.get("endereco") or {}
        endereco_txt = (
            f"{end.get('logradouro', '')}, {end.get('numero', '')} · "
            f"{end.get('bairro', '')} · {end.get('municipio', '')}/"
            f"{end.get('uf', '')} · CEP {end.get('cep', '')}"
        )
        st.markdown(
            f"<div class='cnae-header'>"
            f"<div class='cnae-label'>CNPJ {formatar_cnpj(emp.get('cnpj', ''))}"
            f" · {emp.get('porte', '')}"
            f" · {emp.get('regime_tributario') or 'regime n/d'}</div>"
            f"<div class='cnae-codigo'>{emp.get('razao_social', '—')}</div>"
            f"<div class='cnae-desc'>"
            f"{('<b>' + emp.get('nome_fantasia', '') + '</b> · ') if emp.get('nome_fantasia') else ''}"
            f"<span style='color:{cor_situacao}; font-weight:600;'>"
            f"{situacao}</span> · "
            f"abertura: {emp.get('data_abertura', '—')} · "
            f"{emp.get('natureza_juridica', '—')}<br>"
            f"<small>{endereco_txt}</small>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ===== ALERTAS GLOBAIS =====
    for a in rel.get("alertas_globais", []):
        st.warning(a)

    # ===== RISCO CONSOLIDADO =====
    risco = rel.get("risco_consolidado", "INDEFINIDO")
    cor_risco = {
        "BAIXO": "#047857",
        "MÉDIO": "#D97706",
        "ALTO": "#DC2626",
    }.get(risco, "#1A2A4A")
    st.markdown(
        f"#### 🎯 Risco consolidado: "
        f"<span style='color:{cor_risco}; font-weight:700;'>{risco}</span>",
        unsafe_allow_html=True,
    )

    # ===== CNAES =====
    if rel.get("cnae_principal_analise"):
        a = rel["cnae_principal_analise"]
        st.markdown(
            f"**🥇 CNAE principal:** `{a.get('codigo', '—')}` — "
            f"{a.get('descricao', '—')}  · risco "
            f"**{a.get('risco_consolidado', '—')}**"
        )
    secs = rel.get("cnaes_secundarios_analise") or []
    if secs:
        with st.expander(
            f"🥈 {len(secs)} CNAE(s) secundário(s)",
            expanded=False,
        ):
            for a in secs:
                st.markdown(
                    f"- `{a.get('codigo', '—')}` — "
                    f"{a.get('descricao', '—')} "
                    f"(risco **{a.get('risco_consolidado', '—')}**)"
                )

    # ===== CHECKLIST POR ÓRGÃO =====
    st.markdown("### 📋 Checklist de cadastros / licenças")
    cl = rel.get("checklist", [])
    if not cl:
        st.info("Nenhum órgão regulador identificado pelos CNAEs.")
        return

    # Cabeçalho com legenda
    st.caption(
        "🔴 **Obrigatório** · 🟡 **Verificar** · "
        "✅ **Verificado** · ⛔ **Não se aplica** · 🚨 **Problema**. "
        "Use os botões em cada item pra registrar o que você confirmou "
        "no portal oficial — fica salvo pra próxima consulta."
    )

    # CNPJ usado pra salvar/carregar verificações (vazio se empresa nova)
    cnpj_atual = (emp.get("cnpj") or "").strip()

    # Pega o usuário logado pra registrar "verificado por X"
    from auth import usuario_atual as _u_atual
    _u = _u_atual() or {}
    quem = _u.get("nome") or _u.get("email") or "—"

    from database import (
        registrar_verificacao_orgao as _reg_verif,
        remover_verificacao_orgao as _rm_verif,
        STATUS_VERIFICACAO_OK, STATUS_VERIFICACAO_NA,
        STATUS_VERIFICACAO_PROBLEMA,
    )

    for item in cl:
        verif = item.get("verificacao") or None
        status = (verif or {}).get("status")
        # Determina marcador visual e cor do container
        if status == "verificado":
            marcador = "✅"
            cor_borda = "#047857"
        elif status == "nao_se_aplica":
            marcador = "⛔"
            cor_borda = "#6B7280"
        elif status == "problema":
            marcador = "🚨"
            cor_borda = "#DC2626"
        else:
            marcador = "🔴" if item["obrigatorio"] else "🟡"
            cor_borda = "#E5E9F2"

        esfera_emoji = {
            "federal": "🇧🇷",
            "estadual": "🏛️",
            "municipal": "🏙️",
        }.get(item.get("esfera"), "")

        with st.container(border=True):
            st.markdown(
                f"**{marcador} {item['sigla']}** {esfera_emoji} — "
                f"{item['nome']}"
            )

            # 🎯 REGRA OFICIAL determinística (se cadastrada)
            regras_of = item.get("regras_oficiais") or []
            if regras_of:
                for r in regras_of:
                    _badge_cor = {
                        "sim": "#DC2626",
                        "nao": "#047857",
                        "condicional": "#D97706",
                    }.get(r.get("obrigatoriedade"), "#1A2A4A")
                    _badge_txt = {
                        "sim": "🔴 OBRIGATÓRIO",
                        "nao": "🟢 DISPENSADO",
                        "condicional": "🟡 CONDICIONAL",
                    }.get(r.get("obrigatoriedade"), "❓ INDEFINIDO")

                    st.markdown(
                        f"<div style='background:#FFFFFF; "
                        f"border:1px solid {_badge_cor}; "
                        f"border-left:4px solid {_badge_cor}; "
                        f"border-radius:6px; padding:10px 12px; "
                        f"margin:8px 0;'>"
                        f"<div style='color:{_badge_cor}; "
                        f"font-weight:700; font-size:13px;'>"
                        f"{_badge_txt} · CNAE {r['cnae']}</div>",
                        unsafe_allow_html=True,
                    )
                    if r.get("obrigatoriedade") == "condicional":
                        if r.get("condicoes_obrigatorio"):
                            st.markdown(
                                f"**Obrigatório quando:** "
                                f"{r['condicoes_obrigatorio']}"
                            )
                        if r.get("condicoes_dispensa"):
                            st.markdown(
                                f"**Dispensado quando:** "
                                f"{r['condicoes_dispensa']}"
                            )
                    elif r.get("obrigatoriedade") == "sim":
                        if r.get("condicoes_obrigatorio"):
                            st.markdown(r["condicoes_obrigatorio"])
                    elif r.get("obrigatoriedade") == "nao":
                        if r.get("condicoes_dispensa"):
                            st.markdown(r["condicoes_dispensa"])
                    if r.get("observacoes"):
                        st.caption(f"💡 {r['observacoes']}")
                    if r.get("base_legal"):
                        link_html = ""
                        if r.get("link_lei"):
                            link_html = (
                                f" · <a href='{r['link_lei']}' "
                                f"target='_blank'>📚 ver lei</a>"
                            )
                        st.markdown(
                            f"<div style='font-size:11px; "
                            f"color:#000000; margin-top:6px;'>"
                            f"<b>Base legal:</b> {r['base_legal']}"
                            f"{link_html}</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                # Sem regra cadastrada — avisa
                st.markdown(
                    f"<div style='background:#FFFBEB; "
                    f"border:1px dashed #D97706; "
                    f"border-radius:6px; padding:8px 12px; "
                    f"margin:6px 0; font-size:12px; color:#1A2A4A;'>"
                    f"⚠️ <b>Sem regra cadastrada na base CSM</b> — "
                    f"verifique no portal oficial e, depois de "
                    f"confirmar, cadastre a regra em "
                    f"<b>📚 Base de Regras</b> pra não precisar "
                    f"pesquisar de novo."
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # Status atual em destaque (se houver)
            if verif:
                quando = (verif.get("verificado_em") or "—")[:10]
                quem_v = verif.get("verificado_por") or "—"
                texto_status = {
                    "verificado": (
                        f"✅ **Verificado em {quando}** por {quem_v}"
                    ),
                    "nao_se_aplica": (
                        f"⛔ **Marcado como não se aplica** "
                        f"em {quando} por {quem_v}"
                    ),
                    "problema": (
                        f"🚨 **Problema registrado** em {quando} "
                        f"por {quem_v}"
                    ),
                    "pendente": "🔵 Marcado como pendente novamente",
                }.get(status, "")
                if texto_status:
                    st.markdown(
                        f"<div style='background:#F6F8FC; padding:8px 12px; "
                        f"border-radius:6px; margin:6px 0;'>{texto_status}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                if verif.get("observacao"):
                    st.caption(f"📝 {verif['observacao']}")

            if item.get("descricao"):
                st.caption(item["descricao"])
            st.markdown("**Por que aparece aqui:**")
            for m in item.get("motivos", []):
                st.markdown(f"- {m}")

            # Linha 1: links oficiais
            cc1, cc2 = st.columns(2)
            with cc1:
                if item.get("link_consulta"):
                    st.link_button(
                        "🔍 Consultar situação",
                        item["link_consulta"],
                        width="stretch",
                    )
                else:
                    st.caption("(sem link de consulta cadastrado)")
            with cc2:
                if item.get("link_cadastro"):
                    st.link_button(
                        "📝 Cadastrar / fazer registro",
                        item["link_cadastro"],
                        width="stretch",
                    )
                else:
                    st.caption("(sem link de cadastro cadastrado)")

            # Linha 2: botões de verificação (só pra empresa existente)
            if cnpj_atual:
                key_pref = f"verif_{cnpj_atual}_{item['sigla']}"
                obs_key = f"{key_pref}_obs"

                st.markdown(
                    "<div style='margin-top:8px;'></div>",
                    unsafe_allow_html=True,
                )
                # Campo de observação opcional
                with st.expander("📝 Adicionar observação (opcional)",
                                  expanded=False):
                    st.text_area(
                        "Observação que será salva junto:",
                        key=obs_key,
                        placeholder=(
                            "Ex.: AVCB nº 12345 vence em 30/04/2027 · "
                            "RT é Dr. João CRM 12345 · etc."
                        ),
                        height=70,
                        label_visibility="collapsed",
                    )

                bcol1, bcol2, bcol3, bcol4 = st.columns(4)
                _obs = st.session_state.get(obs_key, "") or ""
                with bcol1:
                    if st.button(
                        "✅ Verificado",
                        key=f"{key_pref}_ok",
                        width="stretch",
                        disabled=(status == "verificado"),
                    ):
                        try:
                            _reg_verif(
                                cnpj_atual, item["sigla"],
                                STATUS_VERIFICACAO_OK,
                                verificado_por=quem,
                                observacao=(_obs or None),
                            )
                            st.success("Salvo!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro: {exc}")
                with bcol2:
                    if st.button(
                        "⛔ N/A",
                        key=f"{key_pref}_na",
                        width="stretch",
                        disabled=(status == "nao_se_aplica"),
                        help="Confirmei que não se aplica a esta empresa.",
                    ):
                        try:
                            _reg_verif(
                                cnpj_atual, item["sigla"],
                                STATUS_VERIFICACAO_NA,
                                verificado_por=quem,
                                observacao=(_obs or None),
                            )
                            st.success("Salvo!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro: {exc}")
                with bcol3:
                    if st.button(
                        "🚨 Problema",
                        key=f"{key_pref}_pb",
                        width="stretch",
                        disabled=(status == "problema"),
                        help="Encontrei pendência/irregularidade.",
                    ):
                        try:
                            _reg_verif(
                                cnpj_atual, item["sigla"],
                                STATUS_VERIFICACAO_PROBLEMA,
                                verificado_por=quem,
                                observacao=(_obs or None),
                            )
                            st.warning("Marcado como problema.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro: {exc}")
                with bcol4:
                    if st.button(
                        "🔄 Resetar",
                        key=f"{key_pref}_rst",
                        width="stretch",
                        disabled=(verif is None),
                        help="Apaga a verificação e volta a aparecer "
                             "como pendente.",
                    ):
                        try:
                            _rm_verif(cnpj_atual, item["sigla"])
                            st.info("Resetado.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro: {exc}")

    st.divider()

    # Resumo do progresso
    if cnpj_atual:
        _ok = sum(1 for x in cl
                  if (x.get("verificacao") or {}).get("status")
                  == "verificado")
        _na = sum(1 for x in cl
                  if (x.get("verificacao") or {}).get("status")
                  == "nao_se_aplica")
        _pb = sum(1 for x in cl
                  if (x.get("verificacao") or {}).get("status")
                  == "problema")
        _pd = len(cl) - _ok - _na - _pb
        st.markdown(
            f"**Progresso:** ✅ {_ok} verificados · "
            f"⛔ {_na} N/A · 🚨 {_pb} problemas · "
            f"🔴/🟡 {_pd} pendentes de **{len(cl)} órgãos**"
        )

    st.caption(
        f"Análise gerada em {rel.get('data_analise', '—')} · "
        f"{rel.get('total_cnaes', 0)} CNAEs cruzados · "
        f"{len(cl)} órgãos identificados."
    )


@st.cache_data(ttl=3600, show_spinner=False)
def _cnae_subclasses_cache():
    """Todas as subclasses CNAE (codigo + denominacao) para busca por texto. Cacheado."""
    from database import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT codigo, denominacao FROM cnae_concla WHERE nivel = 'subclasse'"
        ).fetchall()
    return [dict(r) for r in rows]


def _buscar_cnae_por_texto(texto, limite=40):
    """Busca subclasses CNAE cuja denominacao oficial contem os termos.
    Sem acento/maiuscula, ranqueado por nº de termos batidos. Sem IA."""
    from unidecode import unidecode
    termos = [unidecode(t).lower() for t in str(texto).split() if len(t) >= 3]
    if not termos:
        return []
    out = []
    for r in _cnae_subclasses_cache():
        deno = unidecode(str(r.get("denominacao", ""))).lower()
        hits = sum(1 for t in termos if t in deno)
        if hits:
            out.append((hits, r))
    out.sort(key=lambda x: (-x[0], x[1].get("codigo", "")))
    return [r for _, r in out[:limite]]


def pagina_consulta_cnae():
    st.header("🔬 Consultor de CNAE")
    st.caption(
        "Análise consolidada de exigências por CNAE — cruza CONCLA + NR-04 + "
        "Vigilância CVS-SP + Bombeiros IT-01 + ANVISA + Conselhos profissionais "
        "+ Licenciamento Ambiental + CGSIM. **Sempre confira nas fontes oficiais "
        "(links abaixo da consulta) antes de orientar o cliente.**"
    )

    # =====================================================
    # Wizard: CNAE individual primeiro (consulta rápida do dia-a-dia)
    # =====================================================
    with st.expander("🔎 Não sei o CNAE? Descreva a atividade da empresa"):
        _termo_busca = st.text_input(
            "Descreva o que a empresa vai fazer",
            placeholder="ex.: lanchonete, venda de sucos e salgados",
            key="busca_cnae_atividade",
        )
        if _termo_busca and len(_termo_busca.strip()) >= 3:
            _achados = _buscar_cnae_por_texto(_termo_busca)
            if not _achados:
                st.info("Nenhum CNAE encontrado com esses termos. Tente outras palavras.")
            else:
                import pandas as _pd
                st.caption(
                    f"{len(_achados)} CNAE(s) encontrados — confira a denominação "
                    "oficial e use o código na aba 'CNAE individual'."
                )
                st.dataframe(
                    _pd.DataFrame([
                        {"CNAE": a.get("codigo"), "Denominação oficial": a.get("denominacao")}
                        for a in _achados
                    ]),
                    hide_index=True, width="stretch",
                )

    tab_cnae, tab_cnpj, tab_nova = st.tabs([
        "🔬 CNAE individual",
        "🔎 Empresa existente (CNPJ)",
        "🆕 Empresa nova (vai abrir)",
    ])

    # -------- Aba 1: CNAE individual (consulta rápida) --------
    with tab_cnae:
        _consulta_cnae_individual()

    # -------- Aba 2: empresa existente --------
    with tab_cnpj:
        _wizard_empresa_existente()

    # -------- Aba 3: empresa nova --------
    with tab_nova:
        _wizard_empresa_nova()


def _consulta_cnae_individual():
    """Fluxo clássico: digita 1 CNAE e ve análise completa."""
    col_in, col_btn = st.columns([3, 1])
    with col_in:
        cnae_input = st.text_input(
            "CNAE",
            placeholder="ex.: 4711-3/02 ou 47113/02 ou 4711302",
            key="consulta_cnae_input",
        ).strip()
    with col_btn:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        consultar = st.button("🔍 Consultar", type="primary",
                              width="stretch",
                              key="btn_consultar_cnae_individual")

    if not cnae_input or not (consultar or
                               st.session_state.get("_cnae_last_input") == cnae_input):
        st.info(
            "Digite um CNAE no formato `0000-0/00` (a máscara é flexível — aceita "
            "também `47113/02` ou `4711302`)."
        )
        return

    st.session_state["_cnae_last_input"] = cnae_input
    analise = analisar_cnae(cnae_input)
    # registra consulta pra alimentar o schedule semanal
    try:
        registrar_consulta_cnae(analise["codigo"], "pagina_consulta_cnae")
    except Exception:
        pass

    cnae_norm = analise["codigo"]
    desc = analise.get("descricao") or "*Descrição não encontrada na base CONCLA*"

    # ============ STATUS DE COBERTURA DA BASE ============
    # Em vez do banner genérico "confirme nas fontes oficiais", mostra
    # o quão completa está a base pra ESTE CNAE — quantas fontes têm
    # dados específicos vs. inferidos.
    cobertura: list[tuple[str, str, bool]] = []
    # (fonte, descricao_curta, tem_dados_especificos)

    nr04_loc = analise.get("nr04") or {}
    cobertura.append((
        "NR-04 (MTE)",
        f"Grau {nr04_loc.get('grau_risco') or '—'}",
        bool(nr04_loc) and not nr04_loc.get("_inferido_por_divisao")
        and not nr04_loc.get("_grau_inferido_texto"),
    ))
    vig_loc = analise.get("vigilancia") or {}
    cobertura.append((
        "Vigilância Sanitária (CVS-SP)",
        ("EXIGE" if vig_loc.get("exige_licenca") else
         ("CONDICIONAL" if vig_loc.get("_aviso_invasivo_aplicado") else "OK")),
        not vig_loc.get("_inferido"),
    ))
    bomb_loc = analise.get("bombeiros") or {}
    cobertura.append((
        "Bombeiros (IT-01 CBPMESP)",
        "EXIGE" if bomb_loc.get("exige_avcb") else "OK",
        not bomb_loc.get("_inferido"),
    ))
    amb_loc = analise.get("ambiental") or {}
    cobertura.append((
        "Ambiental (CETESB/IBAMA)",
        "EXIGE" if amb_loc.get("exige_licenca") else "OK",
        not amb_loc.get("_inferido"),
    ))
    anv_loc = analise.get("anvisa") or {}
    cobertura.append((
        "ANVISA",
        "EXIGE" if anv_loc.get("exige_anvisa") else "OK",
        not anv_loc.get("_inferido"),
    ))
    cobertura.append((
        "Conselhos profissionais",
        f"{len(analise.get('conselhos') or [])} conselhos",
        True,  # essa base é uma whitelist — vazio = não exige mesmo
    ))

    cobertos = sum(1 for _, _, ok in cobertura if ok)
    total = len(cobertura)
    pct = round(cobertos * 100 / total)

    if cobertos == total:
        st.success(
            f"✅ **Cobertura completa: {cobertos}/{total} fontes oficiais "
            f"com dado específico para este CNAE.** Pode orientar o cliente "
            f"com base nas informações abaixo — todas vêm das normas oficiais "
            f"listadas em \"⚖️ Fontes locais consultadas\"."
        )
    elif pct >= 67:
        faltam = [n for n, _, ok in cobertura if not ok]
        st.warning(
            f"🟡 **Cobertura parcial: {cobertos}/{total} fontes oficiais "
            f"({pct}%).** Algumas usam inferência: **{', '.join(faltam)}**. "
            "Os campos marcados como **\"ESTIMADO\"** abaixo precisam de "
            "confirmação na fonte oficial — use os botões no final da página."
        )
    else:
        faltam = [n for n, _, ok in cobertura if not ok]
        st.error(
            f"🔴 **Cobertura baixa: {cobertos}/{total} fontes oficiais "
            f"({pct}%).** A base local não tem dados específicos para: "
            f"**{', '.join(faltam)}**. Os valores são estimativas — "
            "**confirme nas fontes oficiais** antes de orientar o cliente."
        )

    # ============ Cabeçalho com risco consolidado ============
    cor_risco = {
        "ALTO": "#DC2626", "MÉDIO": "#D97706",
        "BAIXO": "#059669", "INDEFINIDO": "#6B7280",
    }[analise["risco_consolidado"]]

    st.markdown(f"""
      <div class="cnae-header" style="
        border-left: 6px solid {cor_risco};
        border: 1px solid #E5E7EB;
        border-left: 6px solid {cor_risco};
        box-shadow: 0 1px 3px rgba(0,0,0,.08);
      ">
        <div class="cnae-label">📋 CNAE consultado</div>
        <div class="cnae-codigo">{cnae_norm}</div>
        <div class="cnae-desc">{desc}</div>
        <div class="cnae-badge" style="background:{cor_risco};">
          🎯 RISCO CONSOLIDADO: {analise['risco_consolidado']}
        </div>
      </div>
    """, unsafe_allow_html=True)

    # ============ REGRAS OFICIAIS (resposta determinística) ============
    # Quando há regra cadastrada na Base de Regras, mostramos AQUI no
    # topo com a resposta definitiva e a base legal. Isso é a CERTEZA
    # do sistema — sem isso, tudo embaixo é "provavelmente / verifique".
    regras_top = analise.get("regras_oficiais") or []
    if regras_top:
        st.markdown(
            "### ✅ Respostas oficiais (base curada CSM)"
        )
        st.caption(
            "Estas respostas vêm da base de regras com base legal "
            "verificável. **Use estas no atendimento ao cliente.**"
        )
        for r in regras_top:
            _badge_cor = {
                "sim": "#DC2626",
                "nao": "#047857",
                "condicional": "#D97706",
            }.get(r.get("obrigatoriedade"), "#1A2A4A")
            _badge_txt = {
                "sim": "🔴 OBRIGATÓRIO",
                "nao": "🟢 DISPENSADO",
                "condicional": "🟡 CONDICIONAL",
            }.get(r.get("obrigatoriedade"), "❓ INDEFINIDO")

            with st.container(border=True):
                uf_s = (f" / {r['orgao_uf']}"
                        if r.get("orgao_uf") else "")
                st.markdown(
                    f"<div style='display:flex; "
                    f"justify-content:space-between; "
                    f"align-items:center; margin-bottom:6px;'>"
                    f"<div style='font-size:18px; font-weight:700; "
                    f"color:#1A2A4A;'>"
                    f"📌 {r['orgao_sigla']}{uf_s}</div>"
                    f"<div style='background:{_badge_cor}; "
                    f"color:#FFFFFF; padding:4px 12px; "
                    f"border-radius:6px; font-size:12px; "
                    f"font-weight:700;'>{_badge_txt}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                if r.get("obrigatoriedade") == "condicional":
                    if r.get("condicoes_obrigatorio"):
                        st.markdown(
                            f"**🔴 Obrigatório quando:** "
                            f"{r['condicoes_obrigatorio']}"
                        )
                    if r.get("condicoes_dispensa"):
                        st.markdown(
                            f"**🟢 Dispensado quando:** "
                            f"{r['condicoes_dispensa']}"
                        )
                elif r.get("obrigatoriedade") == "sim":
                    if r.get("condicoes_obrigatorio"):
                        st.markdown(r["condicoes_obrigatorio"])
                elif r.get("obrigatoriedade") == "nao":
                    if r.get("condicoes_dispensa"):
                        st.markdown(r["condicoes_dispensa"])

                if r.get("observacoes"):
                    st.info(f"💡 **Na prática:** {r['observacoes']}")

                if r.get("base_legal"):
                    link_btn = ""
                    if r.get("link_lei"):
                        link_btn = (
                            f" · [📚 abrir lei oficial]"
                            f"({r['link_lei']})"
                        )
                    st.markdown(
                        f"📖 **Base legal:** {r['base_legal']}{link_btn}"
                    )
                st.caption(
                    f"Cadastrado por {r.get('autor', '—')} · "
                    f"última revisão: "
                    f"{(r.get('data_revisao') or r.get('data_cadastro') or '—')[:10]}"
                )
        st.divider()
    else:
        # Sem regra na base — avisa explicitamente
        st.warning(
            "⚠️ **Sem regra oficial cadastrada na base CSM pra este "
            "CNAE.** As informações abaixo são da base local "
            "auxiliar — confirme nas fontes oficiais antes de orientar "
            "o cliente e, depois, cadastre a regra em "
            "**📚 Base de Regras** pra não precisar pesquisar de novo."
        )

    # ============ Alertas ============
    for alerta in analise.get("alertas") or []:
        st.warning(f"⚠️ {alerta}")

    # ============ Alerta destacado: habilitação profissional condicional ====
    habs_top = analise.get("habilitacoes_profissionais") or []
    if habs_top:
        atividades_alto = [h for h in habs_top
                           if h.get("nivel_risco") == "ALTO"]
        if atividades_alto:
            nomes = ", ".join(h["atividade_gatilho"][:80]
                              for h in atividades_alto[:3])
            mais = (f" *(e mais {len(atividades_alto) - 3})*"
                    if len(atividades_alto) > 3 else "")
            st.error(
                "🚨 **ATENÇÃO — Habilitação profissional condicional.** "
                "Este CNAE pode parecer livre de exigência de conselho na PJ, "
                "mas as seguintes atividades — **se executadas** — "
                f"obrigam profissional habilitado: {nomes}{mais}. "
                "**Confirme com o cliente quais procedimentos serão realizados** "
                "antes de orientar — veja o card detalhado abaixo."
            )

    # ============ Cards por área (3 colunas, 2 linhas) ============
    cards_html: list[str] = []

    # 🏥 Vigilância
    vig = analise.get("vigilancia") or {}
    if vig.get("exige_licenca"):
        nivel = vig.get("nivel") or "—"
        risco_san = vig.get("risco_sanitario") or "—"
        cards_html.append(_card_area(
            "🏥", "Vigilância Sanitária", "#DC2626", "EXIGE",
            f"Nível: <b>{nivel}</b><br>"
            f"Risco sanitário: <b>{risco_san}</b><br>"
            + (f"<i>{vig.get('descricao')}</i>" if vig.get('descricao') else ""),
            fonte=vig.get("fonte"),
        ))
    elif vig.get("_aviso_invasivo_aplicado"):
        # CNAE de saúde — isenção CONDICIONAL: depende dos procedimentos
        cards_html.append(_card_area(
            "🏥", "Vigilância Sanitária", "#D97706", "CONDICIONAL",
            "<b>Isenção depende da atividade real.</b><br>"
            "Sem procedimentos invasivos: dispensado pela Portaria CVS "
            "13/2025.<br>"
            "<b style='color:#DC2626'>COM procedimentos invasivos "
            "(botox, harmonização, preenchimento, peelings profundos, "
            "microagulhamento profundo, laser ablativo, etc.): EXIGE "
            "licença sanitária.</b>",
            fonte=vig.get("fonte") or "Portaria CVS 13/2025",
        ))
    else:
        nota = "Confirme com a Vigilância municipal" if vig.get("_inferido") else "Não exige."
        cards_html.append(_card_area(
            "🏥", "Vigilância Sanitária", "#10B981", "OK",
            nota, fonte=vig.get("fonte"),
        ))

    # 🚒 Bombeiros
    bom = analise.get("bombeiros") or {}
    if bom.get("exige_avcb"):
        ocup = bom.get("ocupacao_it01") or "—"
        area = bom.get("area_limite_m2") or "—"
        grau = bom.get("grau_risco") or "—"
        cards_html.append(_card_area(
            "🚒", "Bombeiros (AVCB/CLCB)", "#DC2626", "EXIGE",
            f"Ocupação IT-01: <b>{ocup}</b><br>"
            f"Grau de risco: <b>{grau}</b><br>"
            f"Área limite: <b>{area} m²</b>",
            fonte=bom.get("fonte"),
        ))
    else:
        nota = ("Confirme com o Corpo de Bombeiros local"
                if bom.get("_inferido") else "Dispensa AVCB.")
        cards_html.append(_card_area(
            "🚒", "Bombeiros", "#10B981", "OK",
            nota, fonte=bom.get("fonte"),
        ))

    # 🌱 Ambiental
    amb = analise.get("ambiental") or {}
    if amb.get("exige_licenca"):
        orgao = amb.get("orgao") or "Órgão ambiental"
        tipo = amb.get("tipo_licenca") or "LP/LI/LO"
        porte = amb.get("porte_padrao") or "—"
        cards_html.append(_card_area(
            "🌱", "Licenciamento Ambiental", "#DC2626", "EXIGE",
            f"Órgão: <b>{orgao}</b><br>"
            f"Tipo: <b>{tipo}</b><br>"
            f"Porte padrão: <b>{porte}</b>",
            fonte=amb.get("fonte"),
        ))
    else:
        nota = ("Não classificado na base local. Verifique CETESB se atividade poluente."
                if amb.get("_inferido") else "Dispensa licença ambiental.")
        cards_html.append(_card_area(
            "🌱", "Ambiental", "#10B981", "OK",
            nota, fonte=amb.get("fonte"),
        ))

    # 💊 ANVISA
    anv = analise.get("anvisa") or {}
    if anv.get("exige_anvisa"):
        cat = anv.get("categoria") or "—"
        cards_html.append(_card_area(
            "💊", "ANVISA", "#DC2626", "EXIGE",
            f"Categoria: <b>{cat}</b><br>"
            f"<i>Notificação/registro federal obrigatório.</i>",
            fonte=anv.get("fonte"),
        ))
    else:
        nota = ("Não classificado. Verifique se manipula produtos sob vigilância federal."
                if anv.get("_inferido") else "Dispensa ANVISA.")
        cards_html.append(_card_area(
            "💊", "ANVISA", "#10B981", "OK",
            nota, fonte=anv.get("fonte"),
        ))

    # 🏛️ Conselhos profissionais
    cons = analise.get("conselhos") or []
    _LBL_TIPO_REGISTRO = {
        "INSCRICAO_PJ": "📋 Inscrição da PJ",
        "RT_OBRIGATORIO": "👷 Apenas RT habilitado",
        "AMBOS": "📋 PJ + 👷 RT",
    }
    if cons:
        siglas = ", ".join(c["conselho_sigla"] for c in cons)
        partes = []
        is_inferido_setorial = any(
            c.get("_inferido_setorial") for c in cons
        )
        for c in cons:
            tipo = _LBL_TIPO_REGISTRO.get(c.get("tipo_registro"))
            tipo_html = f" <span style='font-size:11px; color:#6B7280;'>({tipo})</span>" if tipo else ""
            nome_html = f" <i>({c.get('conselho_nome')})</i>" if c.get('conselho_nome') else ""
            partes.append(
                f"• <b>{c['conselho_sigla']}</b>{nome_html}{tipo_html}"
                + (f" — {c.get('obrigatoriedade')}" if c.get('obrigatoriedade') else "")
            )
        descs = "<br>".join(partes)
        if is_inferido_setorial:
            descs = (
                "<b style='color:#DC2626'>🚨 CONSELHOS APLICÁVEIS "
                "(verifique formação do RT):</b><br>"
                + descs
                + "<br><br><i style='font-size:11px;'>O conselho efetivo "
                "depende da formação do profissional/RT da clínica. PJ "
                "deve ter inscrição no conselho do RT.</i>"
            )
            badge_cor = "#DC2626"
            badge_label = f"VERIFICAR · {siglas}"
        else:
            badge_cor = "#D97706"
            badge_label = siglas
        cards_html.append(_card_area(
            "🏛️", "Conselhos Profissionais", badge_cor, badge_label,
            descs, fonte=cons[0].get("fonte"),
        ))
    else:
        cards_html.append(_card_area(
            "🏛️", "Conselhos Profissionais", "#10B981", "OK",
            "Nenhum conselho profissional exigido para este CNAE.",
        ))

    # 📜 Outros registros federais (CTF/IBAMA, MAPA, INMETRO etc.)
    outros = analise.get("outros_registros") or []
    if outros:
        siglas_o = ", ".join(o["orgao"].replace("_", " ") for o in outros)
        partes = []
        for o in outros:
            nome = o.get("orgao_nome") or o["orgao"]
            cat = f" · {o.get('categoria')}" if o.get('categoria') else ""
            obs_html = (
                f"<br><span style='font-size:11px; color:#6B7280;'>{o['observacao']}</span>"
                if o.get("observacao") else ""
            )
            partes.append(
                f"• <b>{nome}</b>{cat} — {o.get('obrigatoriedade', 'OBRIGATORIO')}{obs_html}"
            )
        cards_html.append(_card_area(
            "📜", "Outros registros federais", "#D97706", siglas_o,
            "<br>".join(partes), fonte=outros[0].get("fonte"),
        ))
    else:
        cards_html.append(_card_area(
            "📜", "Outros registros federais", "#10B981", "OK",
            "CTF/IBAMA, MAPA e INMETRO: não exigidos para este CNAE.",
        ))

    # 📊 NR-04 (risco trabalhista)
    nr = analise.get("nr04") or {}
    if nr:
        grau = nr.get("grau_risco") or "—"
        risco_lab = nr.get("risco") or "—"
        inferido = (nr.get("_inferido_por_divisao") or
                    nr.get("_grau_inferido_texto"))
        cor_nr = "#DC2626" if (nr.get("grau_risco") or 0) >= 3 else (
            "#D97706" if (nr.get("grau_risco") or 0) == 2 else "#10B981")
        if inferido:
            cor_nr = "#6B7280"  # cinza quando estimado
            badge = f"GRAU {grau} · ESTIMADO"
            extra_aviso = (
                "<br><span style='font-size:11px; color:#B45309; "
                "font-weight:600;'>⚠️ Estimativa por divisão CNAE — "
                "confirme no Quadro I oficial da NR-04 antes de usar "
                "para SESMT/dimensionamento.</span>"
            )
        else:
            badge = f"GRAU {grau}"
            extra_aviso = ""
        cards_html.append(_card_area(
            "📊", "Risco Trabalhista (NR-04)", cor_nr, badge,
            f"Classificação: <b>{risco_lab}</b><br>"
            f"<i>Define obrigatoriedade de SESMT, EPI, PPRA, etc.</i>"
            f"{extra_aviso}",
            fonte=nr.get("fonte"),
        ))
    else:
        # Não deveria acontecer porque buscar_risco_cnae sempre retorna
        # algo (via fallback), mas pra segurança:
        cards_html.append(_card_area(
            "📊", "NR-04", "#6B7280", "—",
            "Grau de risco não disponível para este CNAE — confirme "
            "no Quadro I da NR-04.",
        ))

    # ⚠️ Habilitação profissional CONDICIONAL — atividades dentro do CNAE
    # que exigem profissional habilitado, mesmo que o CNAE em si não
    # obrigue inscrição PJ em conselho.
    habs = analise.get("habilitacoes_profissionais") or []
    if habs:
        # Cor do badge varia pelo maior nível de risco
        niveis = {h.get("nivel_risco") for h in habs}
        if "ALTO" in niveis:
            cor_hab, lab_hab = "#DC2626", "ATENÇÃO"
        elif "MEDIO" in niveis:
            cor_hab, lab_hab = "#D97706", "CONFIRMAR"
        else:
            cor_hab, lab_hab = "#6B7280", "VER"

        linhas = []
        for h in habs:
            sigla = h.get("conselho_sigla") or "—"
            sigla_html = (
                f"<span style='background:#FEE2E2; color:#991B1B; "
                f"padding:2px 6px; border-radius:4px; font-weight:600; "
                f"font-size:11px;'>{sigla}</span>"
                if sigla != "—" else
                "<span style='color:#6B7280; font-size:11px;'>"
                "(sem conselho específico)</span>"
            )
            linhas.append(
                f"<div style='margin-bottom:10px;'>"
                f"🔸 <b>{h['atividade_gatilho']}</b> {sigla_html}<br>"
                f"<span style='font-size:12px;'>👨‍⚕️ {h['quem_executa']}</span>"
                + (f"<br><span style='font-size:11px; color:#6B7280; "
                   f"font-style:italic;'>{h.get('observacao')}</span>"
                   if h.get('observacao') else "")
                + "</div>"
            )
        body_hab = (
            "<b style='color:#991B1B;'>Atividades CONDICIONAIS — confirme "
            "com o cliente o que ele faz de fato:</b><br><br>"
            + "".join(linhas)
        )
        cards_html.append(_card_area(
            "⚠️", "Habilitação profissional CONDICIONAL",
            cor_hab, lab_hab,
            body_hab,
            fonte=habs[0].get("fonte"),
        ))

    # Renderiza em grid 3x2
    cols = st.columns(3)
    for i, html in enumerate(cards_html):
        with cols[i % 3]:
            st.markdown(html, unsafe_allow_html=True)
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ============ Fontes locais consultadas (referência interna) ============
    if analise.get("fontes"):
        with st.expander("⚖️ Fontes locais consultadas (fundamentação legal)",
                          expanded=False):
            st.caption(
                "Normas/portarias usadas pela análise acima a partir da base "
                "local. Para verificação em tempo real, use os links abaixo."
            )
            for f in analise["fontes"]:
                st.markdown(f"- {f}")

    # ============ 🔗 Confirmar nas fontes oficiais (SEMPRE) ============
    st.divider()
    st.markdown("### 🔗 Confirmar nas fontes oficiais")
    st.caption(
        "**Toda consulta deve ser confirmada nas fontes oficiais antes "
        "de orientar o cliente.** Os botões abaixo abrem os sites dos "
        "órgãos competentes em nova aba."
    )

    cnae_q = analise["codigo"].replace("-", "").replace("/", "")

    # Fontes sempre relevantes
    fontes_sempre: list[tuple[str, str, str]] = [
        ("🏛️ CONCLA / IBGE — busca oficial do CNAE",
         f"https://concla.ibge.gov.br/busca-online-cnae.html?view=subclasse&tipo=cnae&versao=10&subclasse={cnae_q}",
         "Descrição oficial, notas explicativas e atividades "
         "compreendidas / não compreendidas."),
        ("🌐 REDESIM — Portal Nacional",
         "https://www.gov.br/empresas-e-negocios/pt-br/redesim",
         "Roteiro oficial de licenciamento integrado (federal, "
         "estadual, municipal)."),
        ("⚖️ CGSIM — Resoluções de classificação de risco",
         "https://www.gov.br/empresas-e-negocios/pt-br/redesim/legislacao",
         "Resolução CGSIM 51/2019 e atualizações — classifica "
         "atividades em baixo / médio / alto risco."),
    ]

    # Fontes condicionais — sempre listadas porque o usuário precisa
    # confirmar mesmo quando a base local diz "não exige"
    fontes_cond: list[tuple[str, str, str]] = [
        ("🏥 CVS-SP — Centro de Vigilância Sanitária (SES-SP)",
         "https://cvs.saude.sp.gov.br/",
         "Portaria CVS 13/2025 (lista de baixo risco isenta), normas "
         "técnicas, consultas. Para outras UFs, use a Vigilância "
         "Sanitária estadual correspondente."),
        ("🏥 ANVISA — Setor Regulado",
         "https://www.gov.br/anvisa/pt-br/setorregulado",
         "Regulamentos federais — alimentos, medicamentos, saneantes, "
         "cosméticos, produtos para saúde."),
        ("🚒 CBPMESP — Bombeiros SP (IT-01 e normas)",
         "https://www.bombeiros.sp.gov.br/dsci/itcb_normas",
         "IT-01 (procedimentos administrativos), tabela de ocupações "
         "e exigência de AVCB/CLCB."),
        ("🚒 Via Fácil Bombeiros (SP)",
         "https://www.viafacilbombeiros.sp.gov.br/",
         "Portal de regularização e protocolos AVCB/CLCB no estado de "
         "São Paulo."),
        ("🌱 CETESB — Licenciamento Ambiental SP",
         "https://cetesb.sp.gov.br/licenciamentoambiental/",
         "Tabela de atividades sujeitas a licenciamento, CNAEs de "
         "impacto, Decreto 8.468 / Lei 997."),
        ("🌱 IBAMA — CTF/APP",
         "https://servicos.ibama.gov.br/ctf/",
         "Cadastro Técnico Federal — atividades potencialmente "
         "poluidoras / utilizadoras de recursos."),
        ("🌾 MAPA — Ministério da Agricultura",
         "https://www.gov.br/agricultura/pt-br",
         "Registro de estabelecimentos (laticínios, abatedouros, "
         "fertilizantes, sementes, etc.)."),
        ("📐 INMETRO",
         "https://www.gov.br/inmetro/pt-br",
         "Metrologia legal — balanças, taxímetros, equipamentos "
         "que exigem certificação."),
        ("👷 MTE — NR-04 (grau de risco / SESMT)",
         "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/"
         "inspecao-do-trabalho/seguranca-e-saude-no-trabalho/"
         "normas-regulamentadoras",
         "Quadro I da NR-04 — grau de risco por CNAE (1 a 4) e "
         "dimensionamento do SESMT."),
        ("📋 Facilita SP — Viabilidade integrada",
         "https://www.facilita.sp.gov.br/",
         "Consulta prévia de viabilidade integrada com municípios "
         "paulistas."),
    ]

    # Conselhos — só os que aparecem no resultado
    conselhos_links = {
        "CRC":     ("Conselho Federal de Contabilidade", "https://cfc.org.br/"),
        "CRM":     ("Conselho Federal de Medicina", "https://portal.cfm.org.br/"),
        "CREA":    ("Confea / Crea — Engenharia", "https://www.confea.org.br/"),
        "CAU":     ("CAU/BR — Arquitetura", "https://www.caubr.gov.br/"),
        "OAB":     ("Conselho Federal da OAB", "https://www.oab.org.br/"),
        "CFA":     ("Conselho Federal de Administração", "https://cfa.org.br/"),
        "CRO":     ("Conselho Federal de Odontologia", "https://website.cfo.org.br/"),
        "CRP":     ("Conselho Federal de Psicologia", "https://site.cfp.org.br/"),
        "CRN":     ("Conselho Federal de Nutricionistas", "https://www.cfn.org.br/"),
        "COREN":   ("Cofen — Enfermagem", "http://www.cofen.gov.br/"),
        "CRF":     ("Conselho Federal de Farmácia", "https://www.cff.org.br/"),
        "CRMV":    ("Conselho Federal de Medicina Veterinária", "https://www.cfmv.gov.br/"),
        "CONFEF":  ("Conselho Federal de Educação Física", "https://www.confef.org.br/"),
        "CREF":    ("CONFEF/CREF — Educação Física", "https://www.confef.org.br/"),
        "CRECI":   ("Cofeci/Creci — Corretores", "https://www.cofeci.gov.br/"),
        "CRBio":   ("CFBio — Biólogos", "https://www.cfbio.gov.br/"),
        "CRBM":    ("CFBM — Biomedicina", "https://cfbm.gov.br/"),
        "CREFITO": ("Coffito — Fisioterapia e Terapia Ocupacional", "https://www.coffito.gov.br/"),
        "CRQ":     ("CFQ — Químicos", "https://www.cfq.org.br/"),
        "CFFa":    ("CFFa — Fonoaudiologia", "https://www.fonoaudiologia.org.br/cffa/"),
    }
    fontes_conselhos: list[tuple[str, str, str]] = []
    siglas_ja_adicionadas: set[str] = set()
    # Conselhos da PJ (obrigatórios)
    for c in (analise.get("conselhos") or []):
        sig = (c.get("conselho_sigla") or "").upper()
        if sig in conselhos_links and sig not in siglas_ja_adicionadas:
            nome, url = conselhos_links[sig]
            fontes_conselhos.append((
                f"👨‍⚕️ {sig} — {nome}", url,
                f"Confirme exigência de registro profissional ou da PJ "
                f"para este CNAE no site oficial do {sig}.",
            ))
            siglas_ja_adicionadas.add(sig)
    # Conselhos das habilitações CONDICIONAIS (profissional habilitado
    # mesmo sem PJ obrigada) — só os que ainda não foram listados acima
    for h in (analise.get("habilitacoes_profissionais") or []):
        sig = (h.get("conselho_sigla") or "").upper()
        if sig in conselhos_links and sig not in siglas_ja_adicionadas:
            nome, url = conselhos_links[sig]
            fontes_conselhos.append((
                f"👨‍⚕️ {sig} — {nome} *(habilitação condicional)*",
                url,
                f"Para atividades específicas dentro deste CNAE "
                f"({h.get('atividade_gatilho', '')[:60]}…), o profissional "
                f"precisa ter habilitação do {sig}. Confirme no site oficial.",
            ))
            siglas_ja_adicionadas.add(sig)

    todas_fontes = fontes_sempre + fontes_cond + fontes_conselhos
    cols = st.columns(2)
    for i, (titulo, url, desc) in enumerate(todas_fontes):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"**{titulo}**")
                st.caption(desc)
                st.link_button(
                    "🔗 Abrir fonte oficial", url,
                    width="stretch",
                )
            st.markdown("<div style='height:6px'></div>",
                        unsafe_allow_html=True)

    st.caption(
        "💡 **Boa prática:** ao concluir a consulta, abra no mínimo "
        "**CONCLA + REDESIM + a Vigilância Sanitária estadual** "
        "(e os órgãos específicos da atividade) antes de orientar o "
        "cliente. Comparando lado a lado com a análise local você "
        "garante que está usando informação oficial e atualizada."
    )


# ---------------------------------------------------------
# PÁGINA — ⚙️ Configurações (JWT GESTTA + status do banco)
# ---------------------------------------------------------
def pagina_configuracoes():
    st.header("⚙️ Configurações")
    st.caption(
        "Status do sistema, segredos e configurações que precisam ser "
        "atualizados com frequência (ex.: token GESTTA a cada 24h)."
    )

    # ---- Solicitações de cadastro pendentes ----
    try:
        from database import (
            listar_solicitacoes_cadastro,
            atualizar_solicitacao_cadastro,
            contar_solicitacoes_pendentes,
        )
        pendentes = contar_solicitacoes_pendentes()
    except Exception:
        pendentes = 0

    with st.container(border=True):
        st.markdown(
            f"### 📨 Solicitações de cadastro pendentes "
            f"({pendentes})"
        )
        if pendentes == 0:
            st.caption(
                "Nenhuma solicitação pendente. Quando alguém clica em "
                "'Criar conta' na tela de login, aparece aqui pra você "
                "aprovar."
            )
        else:
            st.caption(
                "Pessoas pedindo acesso ao sistema. Aprovar cria o "
                "usuário no Supabase Auth (você precisa fazer o passo "
                "manual no painel — eu mostro o atalho)."
            )
            from auth import usuario_atual
            admin = usuario_atual() or {}
            admin_email = admin.get("email", "admin")

            try:
                lista = listar_solicitacoes_cadastro(status="pendente")
            except Exception as exc:
                st.error(f"Erro ao listar: {exc}")
                lista = []

            for s in lista:
                with st.expander(
                    f"👤 {s['nome']} · {s['email']} · "
                    f"_{s.get('funcao') or 'sem cargo'}_",
                ):
                    st.markdown(
                        f"**Nome:** {s['nome']}  \n"
                        f"**Email:** `{s['email']}`  \n"
                        f"**Função:** {s.get('funcao') or '—'}  \n"
                        f"**Justificativa:** "
                        f"{s.get('justificativa') or '—'}  \n"
                        f"**Solicitado em:** {s['criado_em']}"
                    )
                    obs = st.text_area(
                        "Observação (opcional, salva no histórico)",
                        key=f"obs_{s['id']}", height=60,
                    )
                    c1, c2, c3 = st.columns([2, 1, 1])
                    sup_url = os.getenv("SUPABASE_URL", "")
                    if sup_url:
                        ref = (sup_url.replace("https://", "")
                               .split(".")[0])
                        cria_user_url = (
                            f"https://supabase.com/dashboard/project/"
                            f"{ref}/auth/users"
                        )
                    else:
                        cria_user_url = "https://supabase.com/dashboard"

                    with c1:
                        st.link_button(
                            "🌐 Abrir Supabase pra criar o usuário",
                            cria_user_url,
                            width="stretch",
                        )
                    with c2:
                        if st.button("✅ Aprovar",
                                      key=f"apr_{s['id']}",
                                      width="stretch",
                                      type="primary"):
                            try:
                                atualizar_solicitacao_cadastro(
                                    s["id"], "aprovada",
                                    revisado_por=admin_email,
                                    observacao=obs or None,
                                )
                                st.success(
                                    "Aprovada! Agora abra o Supabase no "
                                    "botão acima e crie o usuário com este "
                                    f"email: `{s['email']}`. Marque "
                                    "**'Auto Confirm User'** ✓."
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Erro: {exc}")
                    with c3:
                        if st.button("❌ Rejeitar",
                                      key=f"rej_{s['id']}",
                                      width="stretch"):
                            try:
                                atualizar_solicitacao_cadastro(
                                    s["id"], "rejeitada",
                                    revisado_por=admin_email,
                                    observacao=obs or None,
                                )
                                st.warning("Solicitação rejeitada.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Erro: {exc}")

    # ---- Status do backend de banco ----
    from db import info_backend
    info = info_backend()
    with st.container(border=True):
        st.markdown("### 💾 Banco de dados")
        if info["backend"] == "postgres":
            st.success(f"{info['label']}")
            st.caption(
                "Os dados estão persistindo no Postgres do Supabase. "
                "Múltiplos usuários da equipe podem acessar simultaneamente."
            )
        else:
            st.warning(f"{info['label']}")
            st.caption(
                "⚠ Você está em **modo desenvolvimento local** — o banco "
                "é um arquivo SQLite no seu PC. Para multi-usuário, "
                "configure a variável `DATABASE_URL` com o Postgres do "
                "Supabase."
            )

    # ---- Meu Telegram (alertas chegam pro seu Telegram pessoal) ----
    with st.container(border=True):
        st.markdown("### 📲 Meu Telegram (alertas pessoais)")
        st.caption(
            "Cadastre o **seu** chat_id pra que os lembretes diários "
            "(10h e 15h) cheguem no SEU Telegram, não no do admin. "
            "Cada usuário que se cadastra aqui recebe a própria cópia "
            "dos alertas."
        )
        from auth import usuario_atual as _u_atual
        _u = _u_atual() or {}
        _meu_email = _u.get("email") or ""

        if not _meu_email or _u.get("_dev"):
            st.info(
                "Faça login com sua conta real (em produção) pra "
                "configurar o Telegram pessoal."
            )
        else:
            try:
                from database import (
                    buscar_telegram_usuario as _btu,
                    definir_telegram_usuario as _dtu,
                    desativar_telegram_usuario as _desat,
                )
                _atual = _btu(_meu_email)
            except Exception as exc:
                st.error(f"Erro ao ler config: {exc}")
                _atual = None

            if _atual and _atual.get("ativo") and _atual.get("chat_id"):
                st.success(
                    f"✅ Você está recebendo alertas no chat_id "
                    f"**{_atual['chat_id']}**"
                )
            elif _atual and not _atual.get("ativo"):
                st.warning(
                    "⏸️ Alertas pausados. Reative abaixo se quiser "
                    "voltar a receber."
                )
            else:
                st.info(
                    "ℹ️ Você ainda não cadastrou um chat_id. "
                    "Sem isso, os alertas do bot continuam indo só "
                    "pro admin."
                )

            with st.expander(
                "🧭 Como descobrir meu chat_id (passo a passo)",
                expanded=not _atual,
            ):
                st.markdown(
                    "1. Abra o Telegram e procure o bot "
                    "`@redesim_csm_bot` (ou o bot da CSM que o admin "
                    "configurou).  \n"
                    "2. Clique **Iniciar** / mande qualquer mensagem "
                    "(ex.: `oi`).  \n"
                    "3. Abra esta URL no navegador "
                    "(substitua `<SEU_TOKEN>` pelo do bot — peça ao "
                    "admin):  \n"
                    "    `https://api.telegram.org/bot<SEU_TOKEN>/"
                    "getUpdates`  \n"
                    "4. Procure o número em `\"chat\":{\"id\": ...}` — "
                    "esse é o seu **chat_id** (geralmente 9-10 dígitos). "
                    "Cole abaixo."
                )

            _novo_chat = st.text_input(
                "Meu chat_id",
                value=(_atual or {}).get("chat_id", "") or "",
                placeholder="Ex.: 1009247169",
                help=(
                    "Número do seu chat privado com o bot. "
                    "Não compartilhe com ninguém."
                ),
                key="meu_telegram_chat_id",
            )
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                if st.button(
                    "💾 Salvar e testar",
                    type="primary",
                    width="stretch",
                    key="btn_salvar_telegram_pessoal",
                ):
                    if not _novo_chat.strip():
                        st.warning("Cole o seu chat_id antes de salvar.")
                    else:
                        try:
                            _dtu(
                                _meu_email,
                                _novo_chat.strip(),
                                nome=_u.get("nome"),
                                ativo=True,
                            )
                            # Manda mensagem de teste
                            from utils.notifier import enviar_telegram
                            _ok, _err = enviar_telegram(
                                f"✅ Olá {_u.get('nome') or _u.get('email')}!"
                                f"\n\nSeu Telegram foi configurado com "
                                f"sucesso no REDESIM Manager. "
                                f"A partir de agora você recebe os "
                                f"lembretes diários (10h e 15h) "
                                f"diretamente aqui.",
                                chat_id=_novo_chat.strip(),
                            )
                            if _ok:
                                st.success(
                                    "✅ Salvo e mensagem de teste "
                                    "enviada! Confira seu Telegram."
                                )
                            else:
                                st.warning(
                                    f"Chat_id salvo mas o envio de "
                                    f"teste falhou: {_err}. Verifique "
                                    f"se o número está correto e se "
                                    f"você iniciou conversa com o bot."
                                )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro ao salvar: {exc}")
            with c2:
                if _atual and _atual.get("ativo"):
                    if st.button(
                        "⏸️ Pausar",
                        width="stretch",
                        key="btn_pausar_telegram_pessoal",
                    ):
                        try:
                            _desat(_meu_email)
                            st.info("Alertas pessoais pausados.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro: {exc}")
            with c3:
                # Lista de quem está recebendo (visível pra todos
                # pra dar transparência sobre quem está no broadcast)
                try:
                    from database import listar_telegrams_ativos as _lta
                    _ativos = _lta()
                    if _ativos:
                        with st.popover(
                            f"👥 {len(_ativos)} ativo(s)",
                            width="stretch",
                        ):
                            for d in _ativos:
                                marca = "👤"
                                if d["email"] == _meu_email:
                                    marca = "🫵"
                                st.write(
                                    f"{marca} {d.get('nome') or d['email']} "
                                    f"`(chat {d['chat_id']})`"
                                )
                except Exception:
                    pass

    # ---- Meu GESTTA (JWT pessoal — cada usuário vincula o seu) ----
    with st.container(border=True):
        st.markdown("### 🔑 Meu GESTTA (JWT pessoal)")
        st.caption(
            "Cole AQUI o JWT do **seu** usuário GESTTA. Assim quando "
            "você navega no app, as buscas e os comentários no GESTTA "
            "vão pela sua conta — respeitando suas permissões e "
            "aparecendo com seu nome no histórico das tarefas. Se você "
            "não cadastrar, o app cai no JWT global (do admin)."
        )
        from auth import usuario_atual as _u_at
        from utils.gestta_api import jwt_info as _jinfo
        from database import (
            definir_gestta_jwt_usuario as _set_jwt,
            buscar_gestta_jwt_usuario as _get_jwt,
            desativar_gestta_jwt_usuario as _desat_jwt,
            listar_jwts_gestta_ativos as _lst_jwts,
        )
        _u = _u_at() or {}
        _meu_email = _u.get("email") or ""

        if not _meu_email or _u.get("_dev"):
            st.info(
                "Faça login com sua conta real (em produção) pra "
                "configurar o GESTTA pessoal."
            )
        else:
            try:
                _rec = _get_jwt(_meu_email)
            except Exception as exc:
                st.error(f"Erro ao ler config: {exc}")
                _rec = None

            if _rec and _rec.get("ativo") and _rec.get("jwt"):
                _info_atual = _jinfo(_rec["jwt"])
                _cor = "🟢"
                if _info_atual.get("expirado"):
                    _cor = "🔴"
                elif (_info_atual.get("horas_restantes") or 0) < 6:
                    _cor = "🟡"
                _status_txt = (
                    "expirado" if _info_atual.get("expirado") else "ativo"
                )
                st.markdown(
                    f"**Status:** {_cor} {_status_txt} · "
                    f"expira em "
                    f"**{_info_atual.get('horas_restantes', '—')}h**"
                )
                st.caption(
                    f"GESTTA: `{_rec.get('gestta_user') or '—'}` · "
                    f"Empresa: `{_rec.get('gestta_company') or '—'}` · "
                    f"Atualizado: `{_rec.get('atualizado_em') or '—'}`"
                )
            elif _rec and not _rec.get("ativo"):
                st.warning(
                    "⏸️ Seu JWT pessoal está pausado — o app está "
                    "usando o JWT global (do admin). Reative abaixo se "
                    "quiser voltar a usar o seu."
                )
            else:
                st.info(
                    "ℹ️ Você ainda não cadastrou um JWT pessoal. "
                    "O app está usando o JWT global (do admin) — "
                    "que pode estar mostrando tarefas que não são suas."
                )

            with st.expander(
                "🧭 Como pegar meu JWT GESTTA (passo a passo)",
                expanded=not _rec,
            ):
                st.markdown(
                    "1. Abra `https://app.gestta.com.br` e faça login "
                    "com **sua** conta GESTTA.  \n"
                    "2. Aperte **F12** pra abrir o DevTools.  \n"
                    "3. Aba **Application** → **Local Storage** → "
                    "`https://app.gestta.com.br`.  \n"
                    "4. Procure a chave **`ngStorage-jwt`** e clique "
                    "duas vezes pra ver o valor.  \n"
                    "5. Copie o conteúdo SEM as aspas externas (começa "
                    "com `JWT eyJ...`).  \n"
                    "6. Cole aqui em baixo e clique **Salvar e testar**."
                )

            _novo_jwt_pess = st.text_area(
                "Meu JWT GESTTA",
                value="",
                placeholder="JWT eyJhbGciOi...",
                height=100,
                help=(
                    "Cole o JWT do SEU usuário GESTTA. Vale ~24h — "
                    "renove quando o app der erro 401."
                ),
                key="meu_gestta_jwt_input",
            )
            cc1, cc2, cc3 = st.columns([2, 1, 1])
            with cc1:
                if st.button(
                    "💾 Salvar e testar",
                    type="primary",
                    width="stretch",
                    key="btn_salvar_gestta_pessoal",
                ):
                    _jwt_strip = (_novo_jwt_pess or "").strip()
                    if not _jwt_strip:
                        st.warning("Cole o JWT antes de salvar.")
                    else:
                        # Valida formato + extrai dados
                        try:
                            _info_novo = _jinfo(_jwt_strip)
                        except Exception as exc:
                            st.error(
                                f"JWT inválido (não consegui decodificar): "
                                f"{exc}"
                            )
                            _info_novo = None

                        if _info_novo and _info_novo.get("valido"):
                            if _info_novo.get("expirado"):
                                st.warning(
                                    "⚠️ Esse JWT já está expirado. "
                                    "Gere um novo no GESTTA."
                                )
                            try:
                                _set_jwt(
                                    _meu_email,
                                    _jwt_strip,
                                    nome=_u.get("nome"),
                                    gestta_user=_info_novo.get("user_name"),
                                    gestta_company=_info_novo.get("company"),
                                    ativo=True,
                                )
                                st.success(
                                    f"✅ Salvo! GESTTA `"
                                    f"{_info_novo.get('user_name') or '—'}` "
                                    f"· expira em "
                                    f"{_info_novo.get('horas_restantes', '—')}h."
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Erro ao salvar: {exc}")
                        elif _info_novo is not None:
                            st.error(
                                "JWT mal formado — esperado um token "
                                "começando com `JWT eyJ...`."
                            )
            with cc2:
                if _rec and _rec.get("ativo"):
                    if st.button(
                        "⏸️ Pausar",
                        width="stretch",
                        key="btn_pausar_gestta_pessoal",
                    ):
                        try:
                            _desat_jwt(_meu_email)
                            st.info(
                                "JWT pessoal pausado. O app voltou pro "
                                "JWT global (admin)."
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Erro: {exc}")
            with cc3:
                try:
                    _ativos_g = _lst_jwts()
                    if _ativos_g:
                        with st.popover(
                            f"👥 {len(_ativos_g)} pessoa(s)",
                            width="stretch",
                        ):
                            for d in _ativos_g:
                                marca = "👤"
                                if d["email"] == _meu_email:
                                    marca = "🫵"
                                st.write(
                                    f"{marca} {d.get('nome') or d['email']} "
                                    f"→ GESTTA: "
                                    f"`{d.get('gestta_user') or '—'}`"
                                )
                except Exception:
                    pass

    # ---- JWT GLOBAL do GESTTA (fallback / admin) ----
    with st.container(border=True):
        st.markdown("### 🔑 Token GESTTA global (fallback)")
        st.caption(
            "Token de fallback usado quando nenhum usuário tem JWT "
            "pessoal configurado — e pelo cron diário do GitHub Actions "
            "(que não tem usuário logado). Mantenha um JWT válido aqui "
            "como segurança. Vence em ~24h."
        )
        try:
            from utils.gestta_api import jwt_info
            from config import GESTTA_JWT
            atual = jwt_info(GESTTA_JWT) if GESTTA_JWT else {"valido": False}
        except Exception:
            atual = {"valido": False, "erro": "não configurado"}

        if atual.get("valido"):
            cor = "🟢"
            if atual.get("expirado"):
                cor = "🔴"
            elif (atual.get("horas_restantes") or 0) < 6:
                cor = "🟡"
            st.markdown(
                f"**Status:** {cor} "
                f"{('expirado' if atual.get('expirado') else 'ativo')}"
                + f" · expira em **{atual.get('horas_restantes', '—')}h**"
            )
            st.caption(
                f"Usuário: `{atual.get('user_name') or '—'}` · "
                f"Empresa: `{atual.get('company') or '—'}`"
            )
        else:
            st.error("Token não configurado ou inválido.")

        with st.form("form_jwt"):
            novo_jwt = st.text_area(
                "Colar o novo JWT (começando com `JWT eyJ...`)",
                height=100,
                placeholder="JWT eyJhbGciOi...",
                help=(
                    "Como pegar: abra app.gestta.com.br logado, F12 → "
                    "Application → Local Storage → ngStorage-jwt — copie "
                    "o valor SEM as aspas."
                ),
            )
            salvar = st.form_submit_button(
                "💾 Salvar token", type="primary",
                width="stretch",
            )
        if salvar:
            if not novo_jwt.strip():
                st.warning("Cole o token antes de salvar.")
            else:
                # Em produção (Streamlit Cloud) precisaria de uma forma de
                # persistir entre redeploys. Por enquanto, salva em
                # st.session_state pra durar a sessão, e mostra instrução.
                st.session_state["GESTTA_JWT_OVERRIDE"] = novo_jwt.strip()
                os.environ["GESTTA_JWT"] = novo_jwt.strip()
                st.success(
                    "✅ Token aplicado nesta sessão. "
                    "Em produção, peça pro admin atualizar o segredo "
                    "GESTTA_JWT no Streamlit Cloud para que persista entre "
                    "reinícios."
                )

    # ---- Usuário logado ----
    with st.container(border=True):
        st.markdown("### 👤 Sessão atual")
        from auth import usuario_atual
        u = usuario_atual() or {}
        st.markdown(
            f"- **Nome:** {u.get('nome', '—')}\n"
            f"- **Email:** {u.get('email', '—')}\n"
            f"- **ID:** `{u.get('id', '—')}`"
        )
        if u.get("_dev"):
            st.info(
                "🧪 Você está em **modo dev** (sem autenticação). "
                "Em produção, este painel mostrará o usuário real do "
                "Supabase Auth."
            )

    # ---- Versões / Saúde ----
    with st.container(border=True):
        st.markdown("### 📦 Versões instaladas")
        try:
            import importlib.metadata as md
            versoes = {p: md.version(p) for p in [
                "streamlit", "pandas", "psycopg2-binary",
                "supabase", "openpyxl",
            ] if _pkg_existe(p)}
            cols_v = st.columns(min(len(versoes) or 1, 5))
            for i, (pkg, v) in enumerate(versoes.items()):
                with cols_v[i % len(cols_v)]:
                    st.metric(pkg, v)
        except Exception as exc:
            st.caption(f"(não foi possível listar versões: {exc})")


def _pkg_existe(nome: str) -> bool:
    try:
        import importlib.metadata as md
        md.version(nome)
        return True
    except Exception:
        return False


# ---------------------------------------------------------
# PÁGINA — 📋 Fila de Renovação (Licenças + VISA)
# ---------------------------------------------------------
def pagina_fila_renovacao():
    st.header("📋 Fila de Renovação — Licenças & VISA")
    st.caption(
        "Suas tarefas GESTTA de **Licença de Funcionamento** e "
        "**Vigilância Sanitária** que ainda não tem protocolo "
        "REDESIM iniciado. Ordenadas pelas mais ANTIGAS primeiro — "
        "ataque por aí."
    )

    # Reclassifica tarefas antigas sem `tipo` setado (só uma vez)
    if not st.session_state.get("_tipos_fila_reclass"):
        try:
            reclassificar_tipos_tarefas(forcar=True)
            st.session_state["_tipos_fila_reclass"] = True
        except Exception:
            pass

    # Botão de sincronização com GESTTA
    sb1, sb2 = st.columns([1, 3])
    with sb1:
        if st.button("🔄 Sincronizar GESTTA",
                     type="primary",
                     width="stretch",
                     key="btn_fila_sync"):
            with st.spinner("Sincronizando..."):
                res = _sync_gestta_completo()
            if res.get("erro"):
                st.error(res["erro"])
            elif res.get("aviso"):
                st.warning(res["aviso"])
            else:
                st.success(
                    f"✅ {res.get('minhas', 0)} tarefas suas "
                    f"sincronizadas ({res.get('inseridas', 0)} novas, "
                    f"{res.get('atualizadas', 0)} atualizadas)."
                )
            import time as _t
            _t.sleep(1.0)
            st.rerun()
    with sb2:
        st.caption(
            "💡 Clica em **Sincronizar GESTTA** se você criou tarefa "
            "nova lá agora. As classificações são atualizadas "
            "automaticamente."
        )

    # ===== Filtros =====
    fcol1, fcol2, fcol3 = st.columns([2, 2, 1])
    with fcol1:
        tipo_filtro = st.radio(
            "Tipo",
            options=["Todos", "Licença de Funcionamento",
                     "Alvará Sanitário"],
            horizontal=True,
            key="fila_tipo_filtro",
        )
    with fcol2:
        mostrar_pulados = st.checkbox(
            "Mostrar pulados",
            key="fila_mostrar_pulados",
        )
    with fcol3:
        st.markdown("<div style='height:28px'></div>",
                    unsafe_allow_html=True)
        st.caption("")

    # ===== Carrega a fila =====
    try:
        fila_completa = fila_renovacao_licencas(
            incluir_pulados=mostrar_pulados,
            incluir_protocolados=False,
        )
    except Exception as exc:
        st.error(f"Erro: {exc}")
        return

    # Aplica filtro de tipo
    if tipo_filtro == "Licença de Funcionamento":
        fila = [t for t in fila_completa
                if t.get("tipo") == "LICENCA_FUNCIONAMENTO"]
    elif tipo_filtro == "Alvará Sanitário":
        fila = [t for t in fila_completa
                if t.get("tipo") == "ALVARA_SANITARIO"]
    else:
        fila = fila_completa

    # ===== Cards-resumo no topo =====
    lic = [t for t in fila if t.get("tipo") == "LICENCA_FUNCIONAMENTO"]
    visa = [t for t in fila if t.get("tipo") == "ALVARA_SANITARIO"]
    atrasadas = sum(1 for t in fila if (
        t.get("overdue") == 1 or
        (t.get("atrasada") or "").upper() in ("SIM","YES","TRUE","1")
    ))

    cs = st.columns(4)
    with cs[0]:
        st.metric("📋 Total na fila", len(fila))
    with cs[1]:
        st.metric("🏢 Licença Funcionamento", len(lic))
    with cs[2]:
        st.metric("🏥 Vigilância Sanitária", len(visa))
    with cs[3]:
        st.metric("🔴 Atrasadas", atrasadas,
                  delta=f"{int(100*atrasadas/max(1,len(fila)))}%"
                        if fila else None,
                  delta_color="inverse")

    st.markdown("---")

    if not fila:
        st.success(
            "🎉 Nenhuma renovação pendente na fila! Tudo protocolado "
            "ou pulado."
        )
        return

    # ===== Lista de cards =====
    for idx, t in enumerate(fila, start=1):
        _render_card_fila(idx, t)


def _render_card_fila(idx: int, t: dict):
    """Card individual de uma tarefa na fila de renovação."""
    from datetime import datetime as _dt

    atrasada = (t.get("overdue") == 1 or
                (t.get("atrasada") or "").upper()
                in ("SIM", "YES", "TRUE", "1"))
    cor_borda = "#DC2626" if atrasada else "#1F4FD3"

    # Calcula dias de atraso
    due_str = t.get("due_date") or ""
    dias_atraso = None
    if due_str and len(due_str) >= 10:
        try:
            dt = _dt.strptime(due_str[:10], "%Y-%m-%d")
            dias_atraso = (_dt.now() - dt).days
        except Exception:
            pass

    tipo_label = {
        "LICENCA_FUNCIONAMENTO": "🏢 Licença de Funcionamento",
        "ALVARA_SANITARIO": "🏥 Vigilância Sanitária (VISA)",
    }.get(t.get("tipo"), t.get("tipo", "?"))

    municipio = t.get("empresa_municipio") or "—"
    uf = t.get("empresa_uf") or ""
    empresa_label = (
        t.get("empresa_razao_social") or
        f"⚠️ {t.get('cliente_nome', '—')} (sem empresa cadastrada)"
    )
    cnpj = t.get("empresa_cnpj") or "sem CNPJ"

    # Header do card
    pulado = bool(t.get("pulado"))
    if pulado:
        cor_borda = "#999999"
        cor_bg = "#F5F5F5"
    else:
        cor_bg = "#FFFFFF"

    with st.container(border=True):
        # Linha 1: número + tipo + status atraso
        hc1, hc2 = st.columns([3, 1])
        with hc1:
            st.markdown(
                f"### {idx}. {empresa_label}"
            )
            sub = []
            sub.append(f"**{tipo_label}**")
            sub.append(f"📅 Vencimento: **{due_str[:10] or '—'}**")
            if dias_atraso is not None and dias_atraso > 0:
                sub.append(f"🔴 **{dias_atraso} dias** de atraso")
            sub.append(f"🏙️ {municipio}/{uf}")
            sub.append(f"📌 CNPJ: `{cnpj}`")
            if t.get("status") == "IMPEDIMENT":
                sub.append("⏸️ **Em IMPEDIMENTO no GESTTA**")
            st.markdown(" · ".join(sub))

            if pulado:
                st.caption(
                    f"⏭️ **PULADO** em "
                    f"{(t.get('pulado_em') or '')[:10]} — "
                    f"motivo: {t.get('motivo_pulado') or '—'}"
                )

            st.caption(
                f"📋 Tarefa GESTTA: _{t.get('tarefa_nome', '—')}_"
            )

        with hc2:
            if not pulado:
                # Botão "Iniciar protocolo"
                if st.button(
                    "🚀 Iniciar protocolo",
                    key=f"fila_iniciar_{t['id']}",
                    type="primary",
                    width="stretch",
                    help="Abre o Facilita-SP em nova aba e mostra "
                         "form pra colar o número quando você "
                         "protocolar lá.",
                ):
                    st.session_state[
                        "_fila_iniciar_id"
                    ] = t["id"]
                if st.button(
                    "⏭️ Pular",
                    key=f"fila_pular_{t['id']}",
                    width="stretch",
                    help="Tira da fila (não vou trabalhar agora).",
                ):
                    st.session_state[
                        "_fila_pular_id"
                    ] = t["id"]
            else:
                if st.button(
                    "↩️ Despular",
                    key=f"fila_despular_{t['id']}",
                    width="stretch",
                ):
                    try:
                        despular_tarefa_gestta(t["id"])
                        st.toast("Tarefa voltou pra fila.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

        # Modal de iniciar protocolo (se selecionado)
        if st.session_state.get("_fila_iniciar_id") == t["id"]:
            _render_modal_iniciar_protocolo(t)
        # Modal de pular (com motivo)
        if st.session_state.get("_fila_pular_id") == t["id"]:
            _render_modal_pular(t)


def _render_modal_iniciar_protocolo(t: dict):
    """Form inline pra iniciar o protocolo: abre Facilita-SP +
    espera você colar o número."""
    st.markdown("---")
    st.markdown("#### 🚀 Iniciar protocolo no Facilita-SP")

    empresa_label = (
        t.get("empresa_razao_social") or
        t.get("cliente_nome", "—")
    )
    cnpj = t.get("empresa_cnpj") or ""

    cb1, cb2 = st.columns([2, 1])
    with cb1:
        st.markdown(
            f"**Cliente:** {empresa_label}  \n"
            f"**CNPJ:** `{cnpj}`  \n"
            f"**Próximos passos:**"
        )
        st.markdown("""
1. Abra o **Facilita-SP** (botão ao lado)
2. Use o **certificado A1 do cliente** pra autenticar
3. Solicite a **Viabilidade** (preenche CNAE, atividade, endereço)
4. Quando o Facilita gerar o **número de protocolo**, copie e cole abaixo
5. Clique em **"Cadastrar protocolo"** — o tracking começa
        """)
    with cb2:
        st.link_button(
            "🌐 Abrir Facilita-SP",
            "https://www.facilitasp.sp.gov.br/",
            width="stretch",
        )
        st.link_button(
            "📋 REDESIM Nacional",
            "https://www.gov.br/empresas-e-negocios/pt-br/redesim",
            width="stretch",
        )

    st.markdown("---")
    st.markdown("**Cole aqui o número de protocolo gerado:**")
    fcol1, fcol2 = st.columns([2, 1])
    with fcol1:
        numero = st.text_input(
            "Número do protocolo *",
            key=f"fila_numero_{t['id']}",
            placeholder="Ex.: VIA.2026.1234567 ou 0123456789",
        )
        obs = st.text_area(
            "Observações iniciais (opcional)",
            key=f"fila_obs_{t['id']}",
            height=60,
            placeholder=(
                "Ex.: Aguardando análise da CETESB · CNAE 5611-2/01"
            ),
        )
    with fcol2:
        tipo_protocolo = st.radio(
            "Tipo",
            options=["Viabilidade", "Licenciamento"],
            key=f"fila_tipo_prot_{t['id']}",
            help="Comece pela Viabilidade (geralmente). "
                 "Quando o Facilita reaproveitar o protocolo no "
                 "Licenciamento, você muda aqui também.",
        )
        from datetime import date as _date
        data_sol = st.date_input(
            "Data de solicitação",
            value=_date.today(),
            key=f"fila_data_{t['id']}",
            format="DD/MM/YYYY",
        )

    bg1, bg2 = st.columns(2)
    with bg1:
        if st.button(
            "💾 Cadastrar protocolo",
            type="primary",
            width="stretch",
            key=f"fila_save_{t['id']}",
        ):
            if not numero.strip():
                st.error("Cole o número do protocolo primeiro.")
            elif not t.get("empresa_id"):
                st.error(
                    "Esta tarefa não está vinculada a uma empresa "
                    "cadastrada no app. Vá em **📋 Tarefas GESTTA → "
                    "Tarefas pendentes** e vincule à empresa primeiro."
                )
            else:
                try:
                    pid = iniciar_protocolo_da_tarefa(
                        tarefa_id=t["id"],
                        numero_protocolo=numero.strip(),
                        tipo_protocolo=tipo_protocolo,
                        data_solicitacao=str(data_sol),
                        observacoes=obs.strip() or None,
                    )
                    st.success(
                        f"✅ Protocolo #{pid} cadastrado! "
                        f"Tarefa GESTTA vinculada — daqui pra frente, "
                        f"toda mudança de status vai pro GESTTA "
                        f"automaticamente."
                    )
                    # Anota no GESTTA que o protocolo foi criado (post-back)
                    try:
                        _r_post = _replicar_status_no_gestta(
                            {"id": pid, "numero_protocolo": numero.strip(),
                             "tipo": tipo_protocolo},
                            "Em análise",
                            observacoes="Protocolo criado/registrado via REDESIM Manager.",
                        )
                        if _r_post.get("ok"):
                            st.info("📝 Anotação de criação enviada ao GESTTA.")
                        else:
                            st.caption(f"GESTTA: {_r_post.get('mensagem')}")
                    except Exception as _e_post:
                        st.caption(f"GESTTA: não anotou ({_e_post}).")
                    st.session_state.pop("_fila_iniciar_id", None)
                    import time as _t
                    _t.sleep(1.5)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro: {exc}")
    with bg2:
        if st.button(
            "❌ Cancelar",
            width="stretch",
            key=f"fila_cancel_{t['id']}",
        ):
            st.session_state.pop("_fila_iniciar_id", None)
            st.rerun()


def _render_modal_pular(t: dict):
    """Form inline pra pular tarefa (com motivo)."""
    st.markdown("---")
    st.markdown("#### ⏭️ Pular esta tarefa")
    st.caption(
        "Tira da fila. Você pode despular depois marcando "
        "'Mostrar pulados' no filtro acima."
    )

    motivo = st.text_input(
        "Motivo (opcional)",
        key=f"fila_motivo_pul_{t['id']}",
        placeholder=(
            "Ex.: cliente vai sair, duplicado, errado, "
            "aguardando documento..."
        ),
    )
    pc1, pc2 = st.columns(2)
    with pc1:
        if st.button(
            "⏭️ Confirmar pular",
            type="primary",
            width="stretch",
            key=f"fila_pular_ok_{t['id']}",
        ):
            try:
                pular_tarefa_gestta(t["id"], motivo=motivo or None)
                st.toast("⏭️ Tarefa pulada — saiu da fila.")
                st.session_state.pop("_fila_pular_id", None)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with pc2:
        if st.button(
            "❌ Cancelar",
            width="stretch",
            key=f"fila_pular_cancel_{t['id']}",
        ):
            st.session_state.pop("_fila_pular_id", None)
            st.rerun()


# ---------------------------------------------------------
# PÁGINA — 💰 Cobranças DOMÍNIO (Thomson Reuters)
# ---------------------------------------------------------
def pagina_cobrancas_dominio():
    st.header("💰 Cobranças DOMÍNIO — Renovações concluídas")
    st.caption(
        "Toda renovação de licença concluída no app gera "
        "AUTOMATICAMENTE uma cobrança pendente aqui. Quando você "
        "lançar no DOMÍNIO (Thomson Reuters), marque como 'Lançada' "
        "pra sair desta lista."
    )

    from database import (
        garantir_valores_cobranca_padrao,
        listar_cobrancas_pendentes,
        listar_valores_cobranca,
        atualizar_valor_cobranca,
        marcar_cobranca_lancada,
        cancelar_cobranca,
        criar_cobranca_pendente,
        contar_cobrancas_pendentes,
        total_pendente_cobranca,
        listar_cobrancas_por_mes,
        atualizar_comissao,
        TIPO_COB_LICENCA_REDESIM, TIPO_COB_VISA,
        TIPO_COB_AVCB, TIPO_COB_OUTRO,
        VALORES_COBRANCA_PADRAO,
    )
    from auth import usuario_atual as _u_at

    garantir_valores_cobranca_padrao()
    _u = _u_at() or {}
    quem = _u.get("nome") or _u.get("email") or "—"

    # === Cards-resumo ===
    qtd = contar_cobrancas_pendentes()
    total = total_pendente_cobranca()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("📌 Pendentes", qtd)
    with c2:
        st.metric("💵 Total a lançar", f"R$ {total:,.2f}".replace(",","X").replace(".",",").replace("X","."))
    with c3:
        st.metric("👤 Responsável", quem.split()[0] if quem else "—")

    if qtd == 0:
        st.success(
            "🎉 Nenhuma cobrança pendente. Tudo lançado no DOMÍNIO!"
        )
    else:
        st.markdown("---")

    tab_pend, tab_lanc, tab_mes, tab_val, tab_manual = st.tabs([
        f"📌 Pendentes ({qtd})",
        "✅ Lançadas",
        "📊 Por Mês",
        "⚙️ Valores sugeridos",
        "➕ Criar manual",
    ])

    # ============== TAB 1: Pendentes ==============
    with tab_pend:
        if qtd == 0:
            st.info("Nada pra lançar agora.")
        else:
            pends = listar_cobrancas_pendentes(status="pendente")
            for cb in pends:
                tipo_label = {
                    "LICENCA_REDESIM": "📋 Licença REDESIM",
                    "VISA": "🏥 Vigilância Sanitária",
                    "AVCB": "🚒 AVCB Bombeiros",
                    "OUTRO": "📌 Outro",
                }.get(cb.get("tipo_servico"), cb.get("tipo_servico", "?"))
                valor_str = f"R$ {(cb.get('valor_sugerido') or 0):.2f}".replace(".",",")

                with st.container(border=True):
                    cc1, cc2 = st.columns([3, 1])
                    with cc1:
                        st.markdown(
                            f"### {cb.get('cliente_nome', '—')}"
                        )
                        info = []
                        info.append(f"**Tipo:** {tipo_label}")
                        info.append(f"**Valor:** {valor_str}")
                        if cb.get("cliente_cnpj"):
                            info.append(f"**CNPJ:** {cb['cliente_cnpj']}")
                        if cb.get("descricao"):
                            info.append(f"**Origem:** {cb['descricao']}")
                        st.markdown(" · ".join(info))
                        st.caption(
                            f"Criada em {(cb.get('criado_em') or '')[:16]} "
                            f"· responsável: {cb.get('responsavel') or '—'}"
                        )
                    with cc2:
                        valor_real = st.number_input(
                            "Valor real lançado",
                            min_value=0.0,
                            value=float(cb.get("valor_sugerido") or 0),
                            step=10.0, format="%.2f",
                            key=f"cob_val_{cb['id']}",
                        )
                        comissao_val = st.number_input(
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
                        )
                        bcol1, bcol2 = st.columns(2)
                        with bcol1:
                            if st.button(
                                "✅ Lancei",
                                key=f"cob_lanc_{cb['id']}",
                                type="primary",
                                width="stretch",
                            ):
                                marcar_cobranca_lancada(
                                    cb["id"],
                                    valor_lancado=valor_real,
                                    lancado_por=quem,
                                    observacao=obs_lanc or None,
                                    comissao=comissao_val if comissao_val > 0 else None,
                                )
                                st.toast("✅ Cobrança baixada!")
                                st.rerun()
                        with bcol2:
                            if st.button(
                                "❌ Cancelar",
                                key=f"cob_canc_{cb['id']}",
                                width="stretch",
                                help="Marca como cancelada (não vai cobrar).",
                            ):
                                cancelar_cobranca(
                                    cb["id"],
                                    motivo=obs_lanc or "cancelada pelo usuário",
                                )
                                st.toast("Cobrança cancelada.")
                                st.rerun()

    # ============== TAB 2: Lançadas ==============
    with tab_lanc:
        lancadas = listar_cobrancas_pendentes(status="lancada")
        if not lancadas:
            st.info("Nenhuma cobrança lançada ainda.")
        else:
            import pandas as _pd
            df = _pd.DataFrame([{
                "Cliente": l.get("cliente_nome"),
                "Tipo": l.get("tipo_servico"),
                "Valor lançado": f"R$ {(l.get('valor_lancado') or 0):.2f}",
                "Comissão": f"R$ {(l.get('comissao') or 0):.2f}",
                "Lançada em": (l.get("lancado_em") or "")[:16],
                "Por": l.get("lancado_por"),
                "Obs": l.get("observacao") or "",
            } for l in lancadas])
            st.dataframe(df, width="stretch", hide_index=True)
            total_lanc = sum(float(l.get("valor_lancado") or 0) for l in lancadas)
            total_com  = sum(float(l.get("comissao") or 0) for l in lancadas)
            def _brl(v): return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
            col_tl, col_tc = st.columns(2)
            col_tl.success(f"💵 **Total lançado:** {_brl(total_lanc)} em {len(lancadas)} cobrança(s)")
            col_tc.info(f"💰 **Minha comissão total:** {_brl(total_com)}")
            st.divider()
            with st.expander("✏️ Editar comissão de uma cobrança"):
                _opcoes = {
                    f"{l.get('cliente_nome')} — {l.get('tipo_servico')} "
                    f"(R$ {(l.get('comissao') or 0):.2f}) [id {l['id']}]": l
                    for l in lancadas
                }
                _sel = st.selectbox(
                    "Cobrança lançada",
                    list(_opcoes.keys()),
                    key="edit_com_sel",
                )
                if _sel:
                    _cb = _opcoes[_sel]
                    _novo = st.number_input(
                        "Nova comissão (R$)",
                        min_value=0.0,
                        value=float(_cb.get("comissao") or 0),
                        step=10.0,
                        format="%.2f",
                        key="edit_com_val",
                    )
                    if st.button("💾 Salvar comissão", key="edit_com_save"):
                        atualizar_comissao(
                            _cb["id"], _novo if _novo > 0 else None
                        )
                        st.toast("✅ Comissão atualizada!")
                        st.rerun()

    # ============== TAB 3: Por Mês ==============
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
            st.dataframe(df_mes, width="stretch", hide_index=True)
            grand_total  = sum(m["total_lancado"] for m in meses)
            grand_comiss = sum(m["total_comissao"] for m in meses)
            def _brl2(v): return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
            col_gt, col_gc = st.columns(2)
            col_gt.success(f"💵 **Total geral:** {_brl2(grand_total)}")
            col_gc.info(f"💰 **Comissão acumulada:** {_brl2(grand_comiss)}")

    # ============== TAB 4: Valores sugeridos ==============
    with tab_val:
        st.markdown(
            "Configure os valores padrão usados quando o sistema cria "
            "uma cobrança automaticamente. Você ainda pode ajustar o "
            "valor de cada cobrança individualmente na hora de lançar."
        )
        valores = listar_valores_cobranca()
        for v in valores:
            with st.container(border=True):
                vcol1, vcol2, vcol3 = st.columns([2, 2, 1])
                with vcol1:
                    st.markdown(f"**{v.get('descricao')}**")
                    st.caption(f"código: `{v['tipo_servico']}`")
                with vcol2:
                    novo_val = st.number_input(
                        "Valor sugerido (R$)",
                        min_value=0.0,
                        value=float(v["valor_sugerido"]),
                        step=10.0, format="%.2f",
                        key=f"vsug_{v['tipo_servico']}",
                    )
                with vcol3:
                    st.markdown("<div style='height:28px'></div>",
                                unsafe_allow_html=True)
                    if st.button(
                        "💾 Atualizar",
                        key=f"vsav_{v['tipo_servico']}",
                        width="stretch",
                    ):
                        atualizar_valor_cobranca(
                            v["tipo_servico"], novo_val,
                            atualizado_por=quem,
                        )
                        st.toast("Valor atualizado.")
                        st.rerun()

    # ============== TAB 4: Criar manual ==============
    with tab_manual:
        st.markdown(
            "Use quando você fez uma renovação manualmente (sem usar "
            "o sistema) e quer registrar a cobrança aqui pra não "
            "esquecer de lançar no DOMÍNIO."
        )
        mcol1, mcol2 = st.columns(2)
        with mcol1:
            mc_cli = st.text_input(
                "Cliente (razão social)",
                key="cobm_cli",
            )
            mc_cnpj = st.text_input(
                "CNPJ (opcional)",
                key="cobm_cnpj",
                placeholder="00.000.000/0000-00",
            )
        with mcol2:
            mc_tipo = st.selectbox(
                "Tipo de serviço",
                options=[
                    TIPO_COB_LICENCA_REDESIM,
                    TIPO_COB_VISA,
                    TIPO_COB_AVCB,
                    TIPO_COB_OUTRO,
                ],
                format_func=lambda x: {
                    "LICENCA_REDESIM": "📋 Licença REDESIM (R$ 250)",
                    "VISA": "🏥 Vigilância Sanitária (R$ 600)",
                    "AVCB": "🚒 AVCB Bombeiros (R$ 500)",
                    "OUTRO": "📌 Outro (R$ 300)",
                }.get(x, x),
                key="cobm_tipo",
            )
            mc_desc = st.text_input(
                "Descrição (opcional)",
                key="cobm_desc",
                placeholder="Ex.: Renovação licença Cotia",
            )
        if st.button(
            "➕ Criar cobrança pendente",
            type="primary",
            width="stretch",
            key="btn_cobm_criar",
        ):
            if not mc_cli.strip():
                st.error("Preencha o cliente.")
            else:
                cob_id = criar_cobranca_pendente(
                    cliente_nome=mc_cli.strip(),
                    cliente_cnpj=mc_cnpj.strip() or None,
                    tipo_servico=mc_tipo,
                    descricao=mc_desc.strip() or None,
                    responsavel=quem,
                )
                st.success(f"✅ Cobrança #{cob_id} criada.")
                st.rerun()


# ---------------------------------------------------------
# PÁGINA — 📚 Base de Regras Oficiais por CNAE × Órgão
# ---------------------------------------------------------
def pagina_base_regras():
    st.header("📚 Base de Regras Oficiais")
    st.caption(
        "Cada regra cadastrada aqui dá CERTEZA ao Consultor de CNAE — "
        "em vez de 'provavelmente precisa de CRECI', o sistema responde "
        "🔴 OBRIGATÓRIO / 🟢 DISPENSADO / 🟡 CONDICIONAL com base legal "
        "citada e link pra lei. Não cadastre regra sem fonte oficial."
    )

    from database import (
        upsert_regra_oficial, buscar_regras_cnae,
        buscar_regra_especifica, remover_regra_oficial,
        extrair_cnaes_da_carteira,
        OBRIGATORIEDADE_SIM, OBRIGATORIEDADE_NAO,
        OBRIGATORIEDADE_CONDICIONAL,
    )
    from auth import usuario_atual as _u_at

    _u = _u_at() or {}
    autor = _u.get("nome") or _u.get("email") or "—"

    tab_cadastrar, tab_pendentes, tab_buscar = st.tabs([
        "✍️ Cadastrar regra",
        "📋 CNAEs da carteira sem regra",
        "🔎 Buscar regras existentes",
    ])

    # ============ Tab 1: Cadastrar regra ============
    with tab_cadastrar:
        st.markdown(
            "Preencha os campos abaixo **com base em lei/resolução "
            "oficial**. Se você não consegue citar a base legal, "
            "não cadastre — pesquise mais antes."
        )

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            cnae_in = st.text_input(
                "CNAE *",
                placeholder="6822-6/00",
                key="reg_cnae",
            ).strip()
        with c2:
            orgao_in = st.text_input(
                "Sigla do órgão * (ex.: CRECI, CRC, ANVISA)",
                key="reg_orgao",
            ).strip().upper()
        with c3:
            uf_in = st.text_input(
                "UF (se estadual)",
                key="reg_uf", max_chars=2,
                help="Deixe vazio se for regra federal.",
            ).strip().upper()

        st.markdown("### Resposta")
        obg = st.radio(
            "Esse CNAE exige cadastro/licença nesse órgão?",
            options=[
                ("sim", "🔴 SIM — sempre obrigatório"),
                ("nao", "🟢 NÃO — dispensa cadastro"),
                ("condicional",
                 "🟡 CONDICIONAL — depende do que a empresa faz"),
            ],
            format_func=lambda x: x[1],
            key="reg_obg",
            horizontal=False,
        )
        obg_val = obg[0] if obg else "condicional"

        cond_obg = ""
        cond_disp = ""
        if obg_val == OBRIGATORIEDADE_SIM:
            cond_obg = st.text_area(
                "Por que é sempre obrigatório? (explicação curta) *",
                placeholder=(
                    "Ex.: 'Corretagem é ato privativo do Corretor "
                    "de Imóveis. PJ que exerce a atividade precisa de "
                    "RT registrado no CRECI + registro PJ.'"
                ),
                key="reg_cond_obg",
                height=80,
            ).strip()
        elif obg_val == OBRIGATORIEDADE_NAO:
            cond_disp = st.text_area(
                "Por que dispensa o cadastro? *",
                placeholder=(
                    "Ex.: 'Aluguel de imóvel próprio não configura "
                    "intermediação — dispensa CRECI (Res. COFECI "
                    "327/92 art. 3º).'"
                ),
                key="reg_cond_disp",
                height=80,
            ).strip()
        else:
            st.caption(
                "Pra regra **condicional**, preencha PELO MENOS uma "
                "das condições abaixo (idealmente as duas)."
            )
            cond_obg = st.text_area(
                "Obrigatório QUANDO...",
                placeholder=(
                    "Ex.: 'A empresa INTERMEDIA negócios imobiliários "
                    "(busca compradores/inquilinos, agencia venda).'"
                ),
                key="reg_cond_obg2",
                height=80,
            ).strip()
            cond_disp = st.text_area(
                "Dispensado QUANDO...",
                placeholder=(
                    "Ex.: 'A empresa apenas ADMINISTRA imóveis (cobra "
                    "aluguel, paga IPTU, manutenção) sem intermediar "
                    "novos contratos.'"
                ),
                key="reg_cond_disp2",
                height=80,
            ).strip()

        observ = st.text_area(
            "Observações práticas (dica/exemplo — opcional)",
            placeholder=(
                "Ex.: 'Na prática: se a empresa SÓ recebe procuração "
                "pra administrar → dispensa. Se busca novos inquilinos "
                "→ exige.'"
            ),
            key="reg_obs",
            height=60,
        ).strip()

        cb1, cb2 = st.columns(2)
        with cb1:
            base_legal = st.text_input(
                "Base legal * (lei + resolução)",
                placeholder=(
                    "Lei 6.530/78 art. 3º + Res. COFECI 327/92 art. 3º"
                ),
                key="reg_base_legal",
            ).strip()
        with cb2:
            link_lei = st.text_input(
                "Link pro PDF/texto da lei *",
                placeholder=(
                    "https://www.planalto.gov.br/ccivil_03/leis/l6530.htm"
                ),
                key="reg_link_lei",
            ).strip()

        if st.button(
            "💾 Salvar regra",
            type="primary",
            width="stretch",
            key="btn_salvar_regra",
        ):
            # Validações
            erros = []
            if not cnae_in:
                erros.append("CNAE obrigatório.")
            if not orgao_in:
                erros.append("Sigla do órgão obrigatória.")
            if not base_legal:
                erros.append(
                    "Base legal obrigatória — cite lei/resolução com "
                    "número e artigo."
                )
            if not link_lei or not link_lei.startswith("http"):
                erros.append(
                    "Link pra lei obrigatório (URL começando com "
                    "http/https)."
                )
            if obg_val == OBRIGATORIEDADE_SIM and not cond_obg:
                erros.append("Explique por que é obrigatório.")
            if obg_val == OBRIGATORIEDADE_NAO and not cond_disp:
                erros.append("Explique por que dispensa.")
            if obg_val == OBRIGATORIEDADE_CONDICIONAL and \
                    not (cond_obg or cond_disp):
                erros.append(
                    "Regra condicional precisa de pelo menos uma "
                    "das condições."
                )

            if erros:
                for e in erros:
                    st.error(e)
            else:
                try:
                    upsert_regra_oficial(
                        cnae_in, orgao_in, obg_val,
                        orgao_uf=(uf_in or None),
                        condicoes_obrigatorio=(cond_obg or None),
                        condicoes_dispensa=(cond_disp or None),
                        observacoes=(observ or None),
                        base_legal=base_legal,
                        link_lei=link_lei,
                        autor=autor,
                    )
                    st.success(
                        f"✅ Regra salva: CNAE {cnae_in} × "
                        f"{orgao_in}{'/' + uf_in if uf_in else ''} "
                        f"= {obg_val.upper()}"
                    )
                except Exception as exc:
                    st.error(f"Erro: {exc}")

    # ============ Tab 2: CNAEs sem regra ============
    with tab_pendentes:
        st.markdown(
            "CNAEs que aparecem na **sua carteira** mas ainda não "
            "têm regra cadastrada — ordenados por frequência. "
            "Priorize os de cima."
        )
        try:
            cnaes_carteira = extrair_cnaes_da_carteira()
        except Exception as exc:
            st.error(f"Erro ao escanear carteira: {exc}")
            cnaes_carteira = []

        if not cnaes_carteira:
            st.info(
                "Nenhum CNAE da carteira detectado ainda. Use o "
                "Consultor de CNAE pra cadastrar empresas e os "
                "CNAEs vão aparecer aqui."
            )
        else:
            import pandas as pd
            # Pra cada CNAE da carteira, conta quantas regras tem
            linhas = []
            for c in cnaes_carteira:
                cn = c["cnae"]
                regras = buscar_regras_cnae(cn)
                linhas.append({
                    "CNAE": cn,
                    "Ocorrências na carteira": c["ocorrencias"],
                    "Regras cadastradas": len(regras),
                    "Órgãos cobertos": ", ".join(
                        sorted({r["orgao_sigla"] for r in regras})
                    ) or "—",
                    "Status": (
                        "✅ ok" if regras else "⚠️ FALTA cadastrar"
                    ),
                })
            df = pd.DataFrame(linhas)
            st.dataframe(df, width="stretch", hide_index=True)

    # ============ Tab 3: Buscar regras ============
    with tab_buscar:
        cnae_busca = st.text_input(
            "Digite o CNAE pra ver as regras já cadastradas",
            placeholder="6822-6/00",
            key="reg_busca_cnae",
        ).strip()

        if cnae_busca:
            try:
                regras = buscar_regras_cnae(cnae_busca)
            except Exception as exc:
                st.error(f"Erro: {exc}")
                regras = []

            if not regras:
                st.warning(
                    f"Nenhuma regra cadastrada pro CNAE {cnae_busca}. "
                    f"Vá pra aba **✍️ Cadastrar regra** pra criar."
                )
            else:
                for r in regras:
                    cor = {
                        "sim": "#DC2626",
                        "nao": "#047857",
                        "condicional": "#D97706",
                    }.get(r["obrigatoriedade"], "#000000")
                    label = {
                        "sim": "🔴 OBRIGATÓRIO",
                        "nao": "🟢 DISPENSADO",
                        "condicional": "🟡 CONDICIONAL",
                    }.get(r["obrigatoriedade"], "?")
                    uf_s = f" / {r['orgao_uf']}" if r.get("orgao_uf") else ""

                    with st.container(border=True):
                        st.markdown(
                            f"### {r['orgao_sigla']}{uf_s} "
                            f"<span style='color:{cor};'>{label}</span>",
                            unsafe_allow_html=True,
                        )
                        if r.get("condicoes_obrigatorio"):
                            st.markdown(
                                f"**Obrigatório quando:** "
                                f"{r['condicoes_obrigatorio']}"
                            )
                        if r.get("condicoes_dispensa"):
                            st.markdown(
                                f"**Dispensado quando:** "
                                f"{r['condicoes_dispensa']}"
                            )
                        if r.get("observacoes"):
                            st.caption(f"💡 {r['observacoes']}")
                        if r.get("base_legal"):
                            link_html = ""
                            if r.get("link_lei"):
                                link_html = (
                                    f" · <a href='{r['link_lei']}' "
                                    f"target='_blank'>📚 ver lei</a>"
                                )
                            st.markdown(
                                f"**Base legal:** {r['base_legal']}"
                                f"{link_html}",
                                unsafe_allow_html=True,
                            )
                        st.caption(
                            f"Cadastrado por {r.get('autor', '—')} · "
                            f"última revisão: "
                            f"{(r.get('data_revisao') or r.get('data_cadastro') or '—')[:16]}"
                        )
                        if st.button(
                            "🗑️ Remover esta regra",
                            key=f"rm_regra_{r['id']}",
                        ):
                            try:
                                remover_regra_oficial(
                                    r["cnae"], r["orgao_sigla"],
                                    orgao_uf=r.get("orgao_uf"),
                                )
                                st.success("Removida.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Erro: {exc}")


# ---------------------------------------------------------
# ROTEAMENTO
# ---------------------------------------------------------
def pagina_fila_do_dia():
    st.header("📋 Fila do dia")
    st.caption(
        "O que precisa de ação — mais parado/urgente no topo. "
        "Esta tela só lê; resolva nas páginas de origem."
    )
    import pandas as _pd
    from database import (
        processos_atrasados, documentos_proximos_vencimento,
        alvaras_vencendo, listar_pendencias,
        contar_cobrancas_pendentes, total_pendente_cobranca,
    )

    def _secao(titulo, dados, ajuda=""):
        st.subheader(titulo)
        if ajuda:
            st.caption(ajuda)
        if dados:
            st.dataframe(_pd.DataFrame(dados), hide_index=True, width="stretch")
        else:
            st.caption("Nada por aqui. 👍")

    try:
        _secao(
            "🚦 Processos em aberto (mais parados no topo)",
            processos_atrasados(0),
            "Quanto mais dias parado, mais urgente.",
        )
    except Exception as _e:
        st.warning(f"Não consegui carregar processos: {_e}")

    _c1, _c2 = st.columns(2)
    with _c1:
        try:
            _secao("📄 Documentos/licenças vencendo", documentos_proximos_vencimento())
        except Exception as _e:
            st.warning(f"Documentos: {_e}")
    with _c2:
        try:
            _secao("🚒 Alvarás de bombeiros vencendo", alvaras_vencendo())
        except Exception as _e:
            st.warning(f"Alvarás: {_e}")

    try:
        _secao("📌 Pendências abertas", listar_pendencias())
    except Exception as _e:
        st.warning(f"Pendências: {_e}")

    try:
        _qtd = contar_cobrancas_pendentes()
        _tot = total_pendente_cobranca()
        if _qtd:
            st.info(f"💰 {_qtd} cobrança(s) DOMÍNIO pendente(s) — R$ {_tot:.2f} a lançar.")
    except Exception:
        pass


def pagina_renovacoes_licencas():
    st.header("📋 Licenças / Renovações")
    st.caption(
        "Tarefas do GESTTA com 'licença' no nome — vencidas e a vencer, por cliente. "
        "Só leitura: trabalhe a tarefa e atualize no GESTTA."
    )
    from database import listar_tarefas_gestta
    from unidecode import unidecode
    import pandas as _pd

    try:
        _tarefas = listar_tarefas_gestta(apenas_pendentes=True)
    except Exception as _e:
        st.warning(f"Não consegui carregar tarefas do GESTTA: {_e}")
        return

    _lic = [
        t for t in _tarefas
        if "licenc" in unidecode(str(t.get("tarefa_nome", ""))).lower()
    ]
    if not _lic:
        st.info("Nenhuma tarefa de licença pendente. (Sincronize o GESTTA se faltar algo.)")
        return

    def _venc(t):
        return (
            str(t.get("overdue")) in ("1", "True")
            or str(t.get("atrasada", "")).strip().lower() in ("sim", "1", "true")
        )

    def _row(t):
        return {
            "Cliente": t.get("cliente_nome"),
            "Tarefa": t.get("tarefa_nome"),
            "Vencimento": (str(t.get("due_date") or ""))[:10],
            "Responsável": t.get("responsavel"),
            "Status": t.get("status_gestta"),
            "Progresso": f"{t.get('done_step') or 0}/{t.get('total_step') or 0}",
        }

    _vencidas = sorted([t for t in _lic if _venc(t)], key=lambda t: (str(t.get("due_date") or "")))
    _avencer = sorted([t for t in _lic if not _venc(t)], key=lambda t: (str(t.get("due_date") or "")))

    st.subheader(f"🔴 Vencidas / atrasadas ({len(_vencidas)})")
    if _vencidas:
        st.dataframe(_pd.DataFrame([_row(t) for t in _vencidas]), hide_index=True, width="stretch")
    else:
        st.caption("Nenhuma vencida. 👍")

    st.subheader(f"🟠 A vencer / em aberto ({len(_avencer)})")
    if _avencer:
        st.dataframe(_pd.DataFrame([_row(t) for t in _avencer]), hide_index=True, width="stretch")
    else:
        st.caption("Nada em aberto.")


PAGINAS = {
    "📊 Dashboard/Kanban": pagina_dashboard,
    "📋 Fila do dia": pagina_fila_do_dia,
    "➕ Novo Processo": pagina_novo_processo,
    "📄 Documentos": pagina_documentos_vencimento,
    "🏢 Empresas / REDESIM": pagina_empresas_redesim,
    "📋 Tarefas GESTTA": pagina_tarefas_gestta,
    "📋 Licenças / Renovações": pagina_renovacoes_licencas,
    "📌 Pendências Gerais": pagina_pendencias,
    "🔬 Consultor de CNAE": pagina_consulta_cnae,
    "📋 Fila de Renovação": pagina_fila_renovacao,
    "💰 Cobranças DOMÍNIO": pagina_cobrancas_dominio,
    "📚 Base de Regras": pagina_base_regras,
    "🏷️ Classificador CNAE": pagina_classificador,
    "📋 Matriz de Risco CNAE": pagina_matriz_risco,
    "🏥 Portaria CVS-SP (Vigilância)": pagina_vigilancia,
    "🚒 Matriz IT-01 Bombeiros": pagina_bombeiros,
    "📥 Atualizar Normas": pagina_atualizar_normas,
    "📲 Configurar Telegram": pagina_telegram,
    "⏰ Lembretes / Testes": pagina_lembretes,
    "⚙️ Configurações": pagina_configuracoes,
}

# Widget do usuário logado na sidebar
renderizar_widget_sidebar()

PAGINAS[pagina]()
