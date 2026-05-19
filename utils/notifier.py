"""
notifier.py
-----------
Envia notificações por Telegram e/ou SMS (Twilio).
Use a função `enviar_alerta(mensagem, processo_id=None)` para
disparar pelos canais configurados.
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
    Envia uma mensagem via Telegram Bot.
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
    """
    resultado = {}
    if telegram_configurado():
        ok, err = enviar_telegram(mensagem)
        resultado["telegram"] = {"ok": ok, "erro": err}
        registrar_notificacao(processo_id, "telegram", mensagem, ok, err)
    if twilio_configurado():
        ok, err = enviar_sms(mensagem)
        resultado["sms"] = {"ok": ok, "erro": err}
        registrar_notificacao(processo_id, "sms", mensagem, ok, err)
    if not resultado:
        log.warning("Nenhum canal de notificação está configurado.")
    return resultado
