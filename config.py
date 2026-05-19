"""
config.py
---------
Centraliza o carregamento das variáveis de ambiente (.env)
e fornece valores default seguros caso algo não esteja configurado.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis do .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ---- Telegram ----
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ---- Twilio (opcional) ----
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER", "").strip()

# ---- Configurações gerais ----
# Regra REDESIM: o CLI deve sair em até 4 dias úteis.
#   DIAS_AMARELO = ponto em que o processo entra em alerta preventivo
#   DIAS_VERMELHO = prazo máximo — passou disso, é atraso crítico
DIAS_AMARELO = int(os.getenv("DIAS_AMARELO", "3"))
DIAS_VERMELHO = int(os.getenv("DIAS_VERMELHO", "4"))
# DIAS_ALERTA fica como alias do DIAS_VERMELHO para compatibilidade com
# código antigo que ainda importa a constante.
DIAS_ALERTA = DIAS_VERMELHO
# HORARIO_LEMBRETE aceita um único horário ("09:00") ou uma lista
# separada por vírgula ("10:00,15:00"). Em ambos os casos, expomos
# também HORARIOS_LEMBRETE como lista para o scheduler.
HORARIO_LEMBRETE = os.getenv("HORARIO_LEMBRETE", "09:00")
HORARIOS_LEMBRETE = [h.strip() for h in HORARIO_LEMBRETE.split(",") if h.strip()]
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "data/redesim.db")
RESPONSAVEL_PADRAO = os.getenv("RESPONSAVEL_PADRAO", "").strip()

# Garantir que a pasta data exista
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


# ---- GESTTA (API privada) ----
# Token JWT copiado de localStorage["ngStorage-jwt"] do navegador logado
# em https://app.gestta.com.br . Expira em ~24h e precisa ser renovado.
GESTTA_JWT = os.getenv("GESTTA_JWT", "").strip()


def gestta_configurado() -> bool:
    return bool(GESTTA_JWT)


def telegram_configurado() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def twilio_configurado() -> bool:
    return all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                TWILIO_FROM_NUMBER, TWILIO_TO_NUMBER])
