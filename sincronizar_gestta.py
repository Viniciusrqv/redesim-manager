"""
sincronizar_gestta.py
---------------------
Lê GESTTA_JWT do .env, baixa as tarefas do GESTTA via API e grava na
tabela `tarefas_gestta` do banco local.

Uso:
    python redesim_manager\\sincronizar_gestta.py
    python redesim_manager\\sincronizar_gestta.py --apenas-info
    python redesim_manager\\sincronizar_gestta.py --status TODOS
    python redesim_manager\\sincronizar_gestta.py --inicio 2026-01-01 --fim 2026-12-31

Por padrão sincroniza tarefas com status OPEN do mês atual (date_type=DUE_DATE).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from config import GESTTA_JWT, gestta_configurado
from database import init_db, upsert_tarefas_gestta_api
from utils.gestta_api import (
    GesttaClient, GesttaAuthError, GesttaAPIError,
    TIPOS_TAREFA_GESTTA, STATUS_TAREFA_GESTTA_ABERTAS, jwt_info,
)


def linha(c="="):
    print(c * 70)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apenas-info", action="store_true",
                    help="Mostra info do JWT (usuário, empresa, expiração) e sai.")
    ap.add_argument("--status", default="ABERTAS",
                    choices=["ABERTAS", "TODOS"],
                    help="Quais status sincronizar (ABERTAS = OPEN+IMPEDIMENT)")
    ap.add_argument("--inicio", default=None,
                    help="Data inicial YYYY-MM-DD (default: primeiro dia do mês atual)")
    ap.add_argument("--fim", default=None,
                    help="Data final YYYY-MM-DD (default: 30 dias após hoje)")
    ap.add_argument("--limit-paginacao", type=int, default=50,
                    help="Itens por página (padrão 50)")
    args = ap.parse_args()

    print()
    linha()
    print("  SINCRONIZAÇÃO GESTTA (via API REST)")
    linha()

    if not gestta_configurado():
        print("\n❌ GESTTA_JWT vazio no .env.")
        print("\nComo configurar:")
        print("  1. Abra https://app.gestta.com.br logado")
        print("  2. F12 → Application → Local Storage → app.gestta.com.br")
        print("  3. Clique em ngStorage-jwt e copie o valor (começa com `\"JWT eyJ...\"`)")
        print("  4. Cole em redesim_manager/.env na linha GESTTA_JWT=")
        print("     (sem as aspas externas, mantenha o \"JWT \" no início)")
        sys.exit(1)

    info = jwt_info(GESTTA_JWT)
    print(f"\n👤 Usuário: {info.get('user_name')} ({info.get('user_email')})")
    print(f"🏢 Empresa: {info.get('company')}")
    print(f"🔐 Role:    {info.get('role')}")
    if info.get("expirado"):
        print(f"\n❌ JWT EXPIRADO em {info.get('expira_em')}.")
        print("   Renove o token (passos acima) e rode de novo.")
        sys.exit(2)
    horas = info.get("horas_restantes", 0)
    if horas < 2:
        print(f"⚠ JWT expira em {horas}h — considere renovar.")
    else:
        print(f"⏰ JWT válido por mais {horas}h.")

    if args.apenas_info:
        print()
        linha()
        sys.exit(0)

    init_db()

    inicio = args.inicio or date.today().replace(day=1).isoformat()
    fim = args.fim or (date.today() + timedelta(days=30)).isoformat()
    status = STATUS_TAREFA_GESTTA_ABERTAS if args.status == "ABERTAS" else None

    print(f"\n📅 Período: {inicio} até {fim}")
    print(f"📊 Status:  {args.status} ({status if status else 'todos'})")

    cli = GesttaClient(GESTTA_JWT)

    try:
        # Conta primeiro
        total = cli.contar_tarefas(
            tipos=TIPOS_TAREFA_GESTTA, status=status,
            start_date=inicio, end_date=fim,
        )
        print(f"\n🧮 Total no GESTTA: {total} tarefas no filtro.")

        if total == 0:
            print("\n✅ Nada a sincronizar.")
            return

        print(f"📥 Baixando (paginação de {args.limit_paginacao}/página)...")
        baixadas = []
        for i, t in enumerate(cli.iter_tarefas(
            tipos=TIPOS_TAREFA_GESTTA, status=status,
            start_date=inicio, end_date=fim, limit=args.limit_paginacao,
        )):
            baixadas.append(t)
            if (i + 1) % 50 == 0:
                print(f"   ... {i+1} / {total}")
        print(f"✅ {len(baixadas)} tarefas baixadas.")

    except GesttaAuthError as e:
        print(f"\n❌ Falha de autenticação: {e}")
        sys.exit(2)
    except GesttaAPIError as e:
        print(f"\n❌ Erro da API: {e}")
        sys.exit(3)

    print("\n💾 Gravando no banco local...")
    res = upsert_tarefas_gestta_api(baixadas)
    print(f"✅ Inseridas:    {res['inseridas']}")
    print(f"🔄 Atualizadas:  {res['atualizadas']}")
    print(f"🔗 Empresa vinc.: {res['matched_empresa']} (de {len(baixadas)})")

    # Distribuição rápida
    from collections import Counter
    por_resp = Counter((t.get("owner") or {}).get("name") or "—" for t in baixadas)
    por_status = Counter(t.get("status") or "—" for t in baixadas)
    por_tipo = Counter(t.get("type") or "—" for t in baixadas)
    print("\n📊 Por responsável (top 5):")
    for n, q in por_resp.most_common(5):
        print(f"   {q:>4}  {n}")
    print(f"\n📊 Por status: {dict(por_status)}")
    print(f"📊 Por tipo:   {dict(por_tipo)}")

    linha()
    print("Concluído. Abra o app em **📋 Tarefas GESTTA** ou no Dashboard.")
    linha()


if __name__ == "__main__":
    main()
