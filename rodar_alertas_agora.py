"""
rodar_alertas_agora.py
----------------------
Dispara TODOS os checks do scheduler (atrasos, protocolos REDESIM,
documentos, AVCBs, pendências gerais) imediatamente, sem esperar 10h
nem 15h. Útil para teste manual e validação.

Uso:
    python redesim_manager\\rodar_alertas_agora.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from database import init_db
from scheduler import (
    checar_atrasos,
    checar_protocolos_redesim,
    checar_documentos_vencendo,
    checar_avcb_vencendo,
    checar_pendencias_gerais,
)


def main():
    init_db()
    print("=" * 60)
    print(f"  RODADA MANUAL DE ALERTAS — {datetime.now():%d/%m/%Y %H:%M:%S}")
    print("=" * 60)
    print()
    print("[1/5] Processos parados...")
    checar_atrasos()
    print("[2/5] Protocolos REDESIM em andamento...")
    checar_protocolos_redesim()
    print("[3/5] Documentos com vencimento...")
    checar_documentos_vencendo()
    print("[4/5] Alvarás AVCB/CLCB...")
    checar_avcb_vencendo()
    print("[5/5] Pendências gerais...")
    checar_pendencias_gerais()
    print()
    print("=" * 60)
    print("Confira o Telegram para ver os alertas que foram disparados.")
    print("=" * 60)


if __name__ == "__main__":
    main()
