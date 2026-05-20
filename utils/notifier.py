"""
notifier.py
-----------
Envia notificações por Telegram e/ou SMS (Twilio).
Use a função `enviar_alerta(mensagem, processo_id=None)` para
disparar pelos canais configurados.

Telegram personalizado por usuário:
  - Cada usuário registra o próprio chat_id pelo painel ⚙️ Configurações.
  - `enviar_alerta` agora faz BROADCAST: envia pra todos os usuários
    ativos com chat_id, e (se não houver nenhum cadastrado) cai pro
    TELEGRAM_CHAT_ID global do .env/secrets como fallback.
"""
import logging
import requests

from config import (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                    telegram_configurado, twilio_configurado,
                    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                    TWILIO_FROM_NUMBER, TWILIO_TO_NUMBER)
from database import registrar_notificacao

log = logging.getLogger(__name__)


# ============================================================
# TELEGRAM
# ============================================================
def enviar_telegram(mensagem: str, chat_id: str = None,
                    token: str = None) -> tuple[bool, str]:
    """
    Envia uma mensagem via Telegram Bot pra UM destino.
    Retorna (sucesso, erro).
    """
    token = token or TELEGRAM_BOT_TOKEN
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False, "Telegram não configurado (TOKEN/CHAT_ID ausente)."
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": mensagem,
            "parse_mode": "HTML",
        }, timeout=15)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def enviar_telegram_broadcast(mensagem: str) -> list[dict]:
    """
    Envia a mensagem pra TODOS os usuários ativos com chat_id.

    Retorna uma lista de dicts: [{"email":..., "ok":..., "erro":...}, ...]
    Se ninguém estiver cadastrado, cai pro CHAT_ID global (admin) como
    fallback pra não deixar nenhum alerta no escuro durante migração.
    """
    try:
        from database import listar_telegrams_ativos
        destinos = listar_telegrams_ativos()
    except Exception as exc:
        log.warning("Não foi possível ler lista de Telegrams: %s", exc)
        destinos = []

    if not destinos:
        # Fallback: chat_id global do .env/secrets (admin)
        if TELEGRAM_CHAT_ID:
            ok, err = enviar_telegram(mensagem, chat_id=TELEGRAM_CHAT_ID)
            return [{
                "email": "(global)",
                "chat_id": TELEGRAM_CHAT_ID,
                "ok": ok,
                "erro": err,
            }]
        return []

    resultados = []
    for d in destinos:
        ok, err = enviar_telegram(mensagem, chat_id=d["chat_id"])
        resultados.append({
            "email": d["email"],
            "chat_id": d["chat_id"],
            "ok": ok,
            "erro": err,
        })
    return resultados


# ============================================================
# TWILIO (SMS)
# ============================================================
def enviar_sms(mensagem: str) -> tuple[bool, str]:
    if not twilio_configurado():
        return False, "Twilio não configurado."
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=mensagem,
            from_=TWILIO_FROM_NUMBER,
            to=TWILIO_TO_NUMBER,
        )
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# ============================================================
# DISPATCHER
# ============================================================
def enviar_alerta(mensagem: str, processo_id: int | None = None) -> dict:
    """
    Envia alerta pelos canais configurados, registra log no banco
    e devolve um dicionário com o resultado de cada canal.

    Para Telegram, faz BROADCAST: todos os usuários ativos com chat_id
    recebem (cada um no Telegram dele). Se nenhum estiver cadastrado,
    cai pro chat_id global (admin) como fallback.
    """
    resultado: dict = {}
    if telegram_configurado():
        envios = enviar_telegram_broadcast(mensagem)
        resultado["telegram"] = {
            "destinos": envios,
            "ok": any(e["ok"] for e in envios),
            "total": len(envios),
        }
        # Loga UMA linha por destinatário, pra ficar fácil debug
        for e in envios:
            registrar_notificacao(
                processo_id, "telegram",
                f"[{e.get('email')}] {mensagem}",
                e["ok"], e.get("erro") or "",
            )
    if twilio_configurado():
        ok, err = enviar_sms(mensagem)
        resultado["sms"] = {"ok": ok, "erro": err}
        registrar_notificacao(processo_id, "sms", mensagem, ok, err)
    if not resultado:
        log.warning("Nenhum canal de notificação está configurado.")
    return resultado
