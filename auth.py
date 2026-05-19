"""
auth.py
-------
Autenticação via Supabase Auth + tela de login no Streamlit.

Em DEV (sem SUPABASE_URL configurada) bypassa o login automaticamente
pra Eduardo continuar mexendo localmente sem fricção.

Em PROD:
  - Mostra tela de login (email + senha)
  - Cria sessão em st.session_state["user"]
  - Bloqueia o app inteiro até logar
"""
from __future__ import annotations

import os
from typing import Optional

import streamlit as st

# Importa segredos da camada db (que já lê de st.secrets ou .env)
try:
    from db import is_postgres  # noqa: F401  (importação que dispara load do env)
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()


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
# API pública
# ====================================================================
def usuario_atual() -> Optional[dict]:
    """Retorna o usuário logado ou None."""
    return st.session_state.get("auth_user")


def exigir_login() -> dict:
    """Bloqueia o app até o usuário logar.
    Em DEV (sem Supabase configurado) retorna um usuário fake.
    """
    if not _supabase_disponivel():
        # Modo dev — bypassa
        return {
            "id": "dev-user",
            "email": "dev@local",
            "nome": "Admin (DEV local)",
            "_dev": True,
        }

    user = st.session_state.get("auth_user")
    if user:
        return user

    # Não logado — mostra tela de login
    _renderizar_tela_login()
    st.stop()  # não permite o resto do app rodar


def logout():
    """Faz logout do Supabase e limpa a sessão."""
    if _supabase_disponivel():
        try:
            _get_client().auth.sign_out()
        except Exception:
            pass
    for k in ("auth_user", "_supabase_client"):
        st.session_state.pop(k, None)
    st.rerun()


# ====================================================================
# UI
# ====================================================================
def _renderizar_tela_login():
    """Tela de login centralizada. Bonita o suficiente."""
    # CSS pra centralizar
    st.markdown("""
      <style>
        .block-container { padding-top: 4rem; max-width: 480px; }
        .login-card {
          background: #1F2937; border: 1px solid #374151;
          border-radius: 14px; padding: 32px 28px;
          box-shadow: 0 8px 20px rgba(0,0,0,.3);
        }
        .login-title {
          font-size: 24px; font-weight: 800; text-align: center;
          margin-bottom: 4px; color: #F9FAFB;
        }
        .login-sub {
          text-align: center; color: #9CA3AF;
          font-size: 13px; margin-bottom: 24px;
        }
      </style>
    """, unsafe_allow_html=True)

    st.markdown(
        "<div class='login-title'>📝 REDESIM Manager</div>"
        "<div class='login-sub'>CSM Contabilidade — entre com sua conta</div>",
        unsafe_allow_html=True,
    )

    tab_login, tab_reset = st.tabs(["🔐 Entrar", "🔑 Esqueci a senha"])

    with tab_login:
        with st.form("form_login", clear_on_submit=False):
            email = st.text_input(
                "Email", placeholder="seu.email@csm.com.br",
                key="login_email",
            )
            senha = st.text_input(
                "Senha", type="password", key="login_senha",
            )
            submitted = st.form_submit_button(
                "🔓 Entrar", type="primary", use_container_width=True,
            )

        if submitted:
            if not email or not senha:
                st.error("Preencha email e senha.")
                return
            try:
                cli = _get_client()
                resp = cli.auth.sign_in_with_password({
                    "email": email.strip(),
                    "password": senha,
                })
                user = resp.user
                if user:
                    st.session_state["auth_user"] = {
                        "id": user.id,
                        "email": user.email,
                        "nome": (user.user_metadata or {}).get(
                            "full_name", user.email),
                    }
                    st.success("Login OK — entrando…")
                    st.rerun()
                else:
                    st.error("Email ou senha incorretos.")
            except Exception as exc:
                msg = str(exc)
                if "Invalid login credentials" in msg:
                    st.error("❌ Email ou senha incorretos.")
                elif "Email not confirmed" in msg:
                    st.error(
                        "📧 Confirme seu email — verifique a caixa de "
                        "entrada do Supabase.")
                else:
                    st.error(f"Erro: {msg[:150]}")

    with tab_reset:
        st.caption(
            "Digite seu email e enviaremos um link de recuperação. "
            "(Verifique também a caixa de spam.)"
        )
        with st.form("form_reset"):
            email_r = st.text_input(
                "Email", key="reset_email",
                placeholder="seu.email@csm.com.br",
            )
            sub = st.form_submit_button(
                "📧 Enviar link", use_container_width=True,
            )
        if sub:
            if not email_r:
                st.warning("Digite o email.")
            else:
                try:
                    cli = _get_client()
                    cli.auth.reset_password_email(email_r.strip())
                    st.success(
                        "Link enviado! Cheque seu email "
                        "(pode demorar até 1 min)."
                    )
                except Exception as exc:
                    st.error(f"Erro: {str(exc)[:150]}")

    st.divider()
    st.caption(
        "👤 Para criar uma conta nova, peça ao admin "
        "(Vinicius Rafael) — não há cadastro público por questões de "
        "segurança."
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
    if not is_dev:
        if st.sidebar.button("Sair", key="btn_logout",
                              use_container_width=True):
            logout()
