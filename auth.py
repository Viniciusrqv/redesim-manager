"""
auth.py
-------
Autenticação via Supabase Auth + tela de login no Streamlit.

Em DEV (sem SUPABASE_URL configurada) bypassa o login automaticamente
pra rodar local sem fricção.

Em PROD:
  - Mostra tela com 3 abas: Entrar / Criar conta / Esqueci a senha
  - Login: chama Supabase Auth
  - Criar conta: salva solicitação na tabela `solicitacoes_cadastro`
    (Eduardo aprova depois pelo painel ⚙️ Configurações)
  - Recuperação: envia link via Supabase

"Mantenha me conectado":
  - Salva o `refresh_token` do Supabase num cookie (30 dias)
  - No carregamento do app, tenta restaurar a sessão usando o refresh_token
  - Se válido, loga automaticamente — F5 não derruba mais o usuário
"""
from __future__ import annotations

import os
from typing import Optional

import streamlit as st

# Importa segredos da camada db (que já lê de st.secrets ou .env)
try:
    from db import is_postgres  # noqa: F401  (dispara load do env)
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()

# Nome do cookie que guarda o refresh_token do Supabase.
# Duração: 30 dias (Supabase regenera o refresh_token a cada uso).
_COOKIE_REFRESH = "redesim_refresh_token"
_COOKIE_MAX_AGE_DIAS = 30


def _supabase_disponivel() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def _get_client():
    """Cria e cacheia o client Supabase."""
    if "_supabase_client" not in st.session_state:
        try:
            from supabase import create_client
            st.session_state["_supabase_client"] = create_client(
                SUPABASE_URL, SUPABASE_ANON_KEY,
            )
        except Exception as exc:
            st.error(f"Erro ao conectar com Supabase: {exc}")
            st.stop()
    return st.session_state["_supabase_client"]


# ====================================================================
# Cookie controller (silencioso se a lib não estiver instalada)
# ====================================================================
def _get_cookies():
    """Retorna o controller de cookies ou None se a lib não existir."""
    if "_cookies_ctrl" in st.session_state:
        return st.session_state["_cookies_ctrl"]
    try:
        from streamlit_cookies_controller import CookieController
        ctrl = CookieController(key="redesim_cookies")
        st.session_state["_cookies_ctrl"] = ctrl
        return ctrl
    except Exception:
        # Lib não instalada → desativa o "mantenha me conectado"
        # graciosamente; login simplesmente exige email/senha a cada F5.
        return None


def _salvar_refresh_token(token: str) -> None:
    """Persiste o refresh_token no cookie (válido 30d)."""
    ctrl = _get_cookies()
    if ctrl is None or not token:
        return
    try:
        from datetime import datetime, timedelta
        ctrl.set(
            _COOKIE_REFRESH, token,
            expires=datetime.utcnow() + timedelta(days=_COOKIE_MAX_AGE_DIAS),
            secure=True,
            same_site="lax",
        )
    except Exception:
        # Não bloqueia o login se o cookie falhar
        pass


def _ler_refresh_token() -> Optional[str]:
    ctrl = _get_cookies()
    if ctrl is None:
        return None
    try:
        return ctrl.get(_COOKIE_REFRESH)
    except Exception:
        return None


def _limpar_refresh_token() -> None:
    ctrl = _get_cookies()
    if ctrl is None:
        return
    try:
        ctrl.remove(_COOKIE_REFRESH)
    except Exception:
        pass


def _restaurar_sessao_via_cookie() -> Optional[dict]:
    """Tenta logar usando o refresh_token persistido. Retorna o user ou None."""
    if not _supabase_disponivel():
        return None
    if "auth_user" in st.session_state:
        # Já logado — nada a fazer
        return st.session_state["auth_user"]

    refresh = _ler_refresh_token()
    if not refresh:
        return None

    try:
        cli = _get_client()
        # set_session aceita um refresh_token e devolve um access novo
        resp = cli.auth.refresh_session(refresh)
        user = resp.user
        sess = resp.session
        if not user:
            return None
        st.session_state["auth_user"] = {
            "id": user.id,
            "email": user.email,
            "nome": (user.user_metadata or {}).get(
                "full_name", user.email),
        }
        # Atualiza o cookie com o NOVO refresh_token (rotação)
        if sess and getattr(sess, "refresh_token", None):
            _salvar_refresh_token(sess.refresh_token)
        return st.session_state["auth_user"]
    except Exception:
        # Token inválido/expirado → limpa o cookie e força login manual
        _limpar_refresh_token()
        return None


# ====================================================================
# API pública
# ====================================================================
def usuario_atual() -> Optional[dict]:
    """Retorna o usuário logado ou None."""
    return st.session_state.get("auth_user")


def exigir_login() -> dict:
    """Bloqueia o app ate o usuario logar.
    Em DEV (sem Supabase configurado) retorna um usuario fake.
    """
    if not _supabase_disponivel():
        return {
            "id": "dev-user",
            "email": "dev@local",
            "nome": "Admin (DEV local)",
            "_dev": True,
        }

    # Criar CookieController SEMPRE no inicio para renderizar junto com a pagina.
    # Sem isso, o componente nao esta pronto quando precisamos ler/salvar cookies.
    _get_cookies()

    user = st.session_state.get("auth_user")
    if user:
        return user

    # Dar um rerun na primeira vez para o CookieController inicializar
    if "cookie_ctrl_init" not in st.session_state:
        st.session_state["cookie_ctrl_init"] = True
        st.rerun()

    # Tentar autologin via cookie (F5 nao deve deslogar)
    restaurado = _restaurar_sessao_via_cookie()
    if restaurado:
        return restaurado

    _renderizar_tela_login()
    st.stop()


def logout():
    """Faz logout do Supabase, limpa o cookie e a sessão."""
    if _supabase_disponivel():
        try:
            _get_client().auth.sign_out()
        except Exception:
            pass
    _limpar_refresh_token()
    for k in ("auth_user", "_supabase_client"):
        st.session_state.pop(k, None)
    st.rerun()


# ====================================================================
# AÇÕES (chamadas pelos botões)
# ====================================================================
def _acao_login():
    """Executa login. Lê estado de st.session_state e atualiza."""
    email = (st.session_state.get("login_email") or "").strip()
    senha = st.session_state.get("login_senha") or ""
    manter = st.session_state.get("login_manter_conectado", True)
    if not email or not senha:
        st.session_state["_login_msg"] = ("error", "Preencha email e senha.")
        return
    try:
        cli = _get_client()
        resp = cli.auth.sign_in_with_password({
            "email": email, "password": senha,
        })
        user = resp.user
        sess = resp.session
        if user:
            st.session_state["auth_user"] = {
                "id": user.id,
                "email": user.email,
                "nome": (user.user_metadata or {}).get(
                    "full_name", user.email),
            }
            # Se o checkbox "mantenha me conectado" está marcado,
            # salva o refresh_token no cookie (vale 30 dias).
            if manter and sess and getattr(sess, "refresh_token", None):
                _salvar_refresh_token(sess.refresh_token)
            # Limpa campos
            st.session_state.pop("login_email", None)
            st.session_state.pop("login_senha", None)
            st.session_state["_login_msg"] = ("success", "Entrando…")
        else:
            st.session_state["_login_msg"] = (
                "error", "Email ou senha incorretos.")
    except Exception as exc:
        msg = str(exc)
        if "Invalid login credentials" in msg:
            st.session_state["_login_msg"] = (
                "error", "❌ Email ou senha incorretos.")
        elif "Email not confirmed" in msg:
            st.session_state["_login_msg"] = (
                "error",
                "📧 Sua conta ainda não foi confirmada. Peça ao admin.")
        else:
            st.session_state["_login_msg"] = ("error", f"Erro: {msg[:150]}")


def _acao_solicitar_cadastro():
    """Salva uma solicitação de cadastro na tabela local."""
    nome = (st.session_state.get("cad_nome") or "").strip()
    email = (st.session_state.get("cad_email") or "").strip().lower()
    funcao = (st.session_state.get("cad_funcao") or "").strip() or None
    justificativa = (st.session_state.get("cad_just") or "").strip() or None

    if not nome:
        st.session_state["_cad_msg"] = ("error", "Digite seu nome completo.")
        return
    if not email or "@" not in email:
        st.session_state["_cad_msg"] = ("error", "Email inválido.")
        return

    try:
        from database import criar_solicitacao_cadastro
        criar_solicitacao_cadastro(
            nome=nome, email=email,
            funcao=funcao, justificativa=justificativa,
        )
        # Limpa campos
        for k in ("cad_nome", "cad_email", "cad_funcao", "cad_just"):
            st.session_state.pop(k, None)
        st.session_state["_cad_msg"] = (
            "success",
            f"✅ Solicitação enviada! O admin vai revisar e te avisar "
            f"por email ({email}) quando aprovar.",
        )
    except ValueError as exc:
        st.session_state["_cad_msg"] = ("warning", str(exc))
    except Exception as exc:
        st.session_state["_cad_msg"] = (
            "error", f"Erro ao salvar: {str(exc)[:150]}")


def _acao_reset_senha():
    email = (st.session_state.get("reset_email") or "").strip()
    if not email:
        st.session_state["_reset_msg"] = ("warning", "Digite o email.")
        return
    try:
        cli = _get_client()
        cli.auth.reset_password_email(email)
        st.session_state["_reset_msg"] = (
            "success",
            "Link enviado! Cheque seu email (pode demorar até 1 min).",
        )
    except Exception as exc:
        st.session_state["_reset_msg"] = (
            "error", f"Erro: {str(exc)[:150]}")


# ====================================================================
# UI
# ====================================================================
def _renderizar_tela_login():
    """Tela de login com 3 abas — sem st.form pra evitar o warning."""
    # CSS pra centralizar e estilizar
    st.markdown(
        '<link href="https://fonts.googleapis.com/css2?'
        'family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )
    st.markdown("""
      <style>
        html, body, [class*="css"], .stApp {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont,
                       'Segoe UI', Roboto, sans-serif !important;
          background: #F6F8FC;
        }
        .block-container { padding-top: 5rem; max-width: 460px; }
        .login-brand {
          display: inline-block;
          background: #1F4FD3;
          color: #FFFFFF !important;
          width: 56px; height: 56px;
          border-radius: 12px;
          font-size: 26px; font-weight: 600;
          line-height: 56px;
          text-align: center;
          margin: 0 auto 20px;
        }
        .login-wrap {
          background: #FFFFFF;
          border: 1px solid #E5E9F2;
          border-radius: 12px;
          padding: 32px 28px;
          box-shadow: 0 2px 8px rgba(15, 23, 42, .04);
        }
        .login-title {
          font-size: 22px; font-weight: 600;
          text-align: center;
          margin-bottom: 4px; color: #1A2A4A !important;
        }
        .login-sub {
          text-align: center; color: #6B7280;
          font-size: 13px; margin-bottom: 24px;
        }
        .stButton > button[kind="primary"] {
          background: #1F4FD3 !important;
          border-color: #1F4FD3 !important;
          font-weight: 500;
        }
        .stButton > button[kind="primary"]:hover {
          background: #1A41B3 !important;
          border-color: #1A41B3 !important;
        }
      </style>
    """, unsafe_allow_html=True)

    st.markdown(
        "<div style='text-align:center;'>"
        "<div class='login-brand'>R</div>"
        "</div>"
        "<div class='login-title'>REDESIM Manager</div>"
        "<div class='login-sub'>CSM Contabilidade · gestão de licenças "
        "e processos</div>",
        unsafe_allow_html=True,
    )

    tab_entrar, tab_cadastrar, tab_reset = st.tabs([
        "Entrar", "Criar conta", "Esqueci a senha",
    ])

    # -------- ENTRAR --------
    with tab_entrar:
        st.text_input(
            "Email", placeholder="seu.email@csm.com.br",
            key="login_email",
        )
        st.text_input(
            "Senha", type="password", key="login_senha",
        )
        st.checkbox(
            "🔒 Mantenha me conectado (não pede senha por 30 dias)",
            key="login_manter_conectado",
            value=True,
            help=(
                "Salva uma credencial segura no navegador (refresh "
                "token). Desmarque se estiver num computador público."
            ),
        )
        st.button(
            "Entrar", type="primary", use_container_width=True,
            on_click=_acao_login, key="btn_login",
        )
        msg = st.session_state.pop("_login_msg", None)
        if msg:
            tipo, txt = msg
            getattr(st, tipo)(txt)
            if tipo == "success":
                st.rerun()

    # -------- CRIAR CONTA --------
    with tab_cadastrar:
        st.caption(
            "Solicite acesso ao sistema. O admin (Vinicius Rafael) "
            "vai revisar e te avisar por email quando aprovar."
        )
        st.text_input(
            "Nome completo *", placeholder="Ex.: Maria Silva",
            key="cad_nome",
        )
        st.text_input(
            "Email *", placeholder="seu.email@csm.com.br",
            key="cad_email",
        )
        st.text_input(
            "Função / cargo", placeholder="Ex.: Auxiliar fiscal",
            key="cad_funcao",
        )
        st.text_area(
            "Justificativa (opcional)",
            placeholder="Por que você precisa de acesso?",
            key="cad_just",
            height=70,
        )
        st.button(
            "Solicitar acesso", type="primary",
            use_container_width=True,
            on_click=_acao_solicitar_cadastro, key="btn_cad",
        )
        msg = st.session_state.pop("_cad_msg", None)
        if msg:
            tipo, txt = msg
            getattr(st, tipo)(txt)

    # -------- ESQUECI A SENHA --------
    with tab_reset:
        st.caption(
            "Digite seu email e enviaremos um link de recuperação. "
            "Verifique também a caixa de spam."
        )
        st.text_input(
            "Email", key="reset_email",
            placeholder="seu.email@csm.com.br",
        )
        st.button(
            "Enviar link de recuperação", type="primary",
            use_container_width=True,
            on_click=_acao_reset_senha, key="btn_reset",
        )
        msg = st.session_state.pop("_reset_msg", None)
        if msg:
            tipo, txt = msg
            getattr(st, tipo)(txt)

    st.divider()
    st.caption(
        "🔒 Acesso controlado — somente usuários aprovados pelo "
        "admin (Vinicius Rafael) podem entrar."
    )


def renderizar_widget_sidebar():
    """Exibe info do usuário logado + botão de logout na sidebar."""
    user = usuario_atual()
    if not user:
        return
    st.sidebar.markdown("---")
    is_dev = user.get("_dev")
    icon = "🧪" if is_dev else "👤"
    st.sidebar.caption(
        f"{icon} **{user.get('nome') or user.get('email') or '—'}**"
        + ("  *(modo dev — sem auth)*" if is_dev else "")
    )

    # Mostra contador de solicitações pendentes pro admin
    if not is_dev:
        try:
            from database import contar_solicitacoes_pendentes
            pendentes = contar_solicitacoes_pendentes()
            if pendentes > 0:
                st.sidebar.warning(
                    f"📨 **{pendentes} solicitação(ões) de cadastro "
                    f"pendente(s).** Veja em ⚙️ Configurações."
                )
        except Exception:
            pass

        if st.sidebar.button("Sair", key="btn_logout",
                              use_container_width=True):
            logout()
