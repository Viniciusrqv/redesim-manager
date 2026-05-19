"""
diagnostico_alertas.py
----------------------
Diagnostica por que alertas podem não estar chegando.
Rode no PowerShell (com a venv ativa):

    python redesim_manager/diagnostico_alertas.py

NÃO modifica nada no banco. Só lê e imprime.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# garante que dá pra rodar a partir da raiz ou da própria pasta
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from config import (
    DIAS_AMARELO, DIAS_VERMELHO, HORARIO_LEMBRETE,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    telegram_configurado, twilio_configurado,
    DATABASE_PATH,
)
from database import (
    get_conn, init_db, processos_atrasados,
    documentos_proximos_vencimento, alvaras_vencendo,
    listar_todos_protocolos, STATUS_PROTOCOLO_OK, STATUS_PROTOCOLO_PROBLEMA,
)
from utils.notifier import enviar_telegram


def linha(c="="):
    print(c * 70)


def main():
    init_db()
    print()
    linha()
    print(f"  DIAGNÓSTICO DE ALERTAS  —  {datetime.now():%d/%m/%Y %H:%M}")
    linha()

    # 1. Configuração geral
    print(f"\n[1/6] Configuração")
    print(f"  • Banco: {DATABASE_PATH}")
    print(f"  • DIAS_AMARELO  = {DIAS_AMARELO}")
    print(f"  • DIAS_VERMELHO = {DIAS_VERMELHO}")
    print(f"  • HORARIO_LEMBRETE = {HORARIO_LEMBRETE}")
    print(f"  • Telegram configurado? {'✅ sim' if telegram_configurado() else '❌ não'}")
    if telegram_configurado():
        print(f"      Token: {TELEGRAM_BOT_TOKEN[:10]}…  Chat: {TELEGRAM_CHAT_ID}")
    print(f"  • Twilio  configurado? {'✅ sim' if twilio_configurado() else '— não'}")

    # 2. Processos atrasados (tabela 'processos')
    print(f"\n[2/6] Processos atrasados (tabela 'processos')")
    procs = processos_atrasados(DIAS_AMARELO)
    if not procs:
        print("  ✅ Nenhum processo com mais de 3 dias parado.")
    else:
        print(f"  ⚠ {len(procs)} processo(s) parados há ≥{DIAS_AMARELO}d:")
        for p in procs:
            cor = "🔴" if p["dias_parado"] >= DIAS_VERMELHO else "🟡"
            print(f"    {cor} ID {p['id']:<4} {p['razao_social'][:40]:<40} "
                  f"status={p['status']:<25} {p['dias_parado']}d")

    # 3. Protocolos REDESIM em andamento (tabela 'protocolos_redesim')
    print(f"\n[3/6] Protocolos REDESIM em andamento (tabela 'protocolos_redesim')")
    todos = listar_todos_protocolos()
    em_andamento = [
        p for p in todos
        if p["status"] not in (STATUS_PROTOCOLO_OK | STATUS_PROTOCOLO_PROBLEMA)
        and not p.get("substituido_por_id")
    ]
    print(f"  Total em andamento: {len(em_andamento)}")
    if em_andamento:
        with get_conn() as conn:
            for p in em_andamento:
                # calcula dias parado a partir de data_solicitacao
                ds = p.get("data_solicitacao")
                dias = "—"
                if ds:
                    try:
                        d0 = datetime.strptime(ds, "%Y-%m-%d")
                        dias = (datetime.now() - d0).days
                    except Exception:
                        pass
                emp = conn.execute(
                    "SELECT razao_social FROM empresas WHERE id = ?",
                    (p["empresa_id"],),
                ).fetchone()
                rs = emp["razao_social"] if emp else "?"
                cor = "🟢"
                if isinstance(dias, int):
                    if dias >= DIAS_VERMELHO:
                        cor = "🔴"
                    elif dias >= DIAS_AMARELO:
                        cor = "🟡"
                print(f"    {cor} {p['numero_protocolo']:<18} {p['tipo']:<14} "
                      f"{rs[:38]:<38} {p['status']:<22} {dias}d")
        print(
            "\n  ⚠ ATENÇÃO: o scheduler atual SÓ monitora a tabela 'processos',"
            "\n    NÃO esta tabela. Se você espera alerta nesses protocolos,"
            "\n    o scheduler precisa ser estendido (já em curso)."
        )

    # 4. Documentos a vencer
    print(f"\n[4/6] Documentos a vencer")
    docs = documentos_proximos_vencimento()
    print(f"  {len(docs)} documento(s) na janela de alerta")

    # 5. Alvarás Bombeiros
    print(f"\n[5/6] Alvarás AVCB/CLCB vencendo em até 60d")
    avcbs = alvaras_vencendo(dias=60)
    print(f"  {len(avcbs)} alvará(s) na janela")

    # 6. Últimas notificações enviadas
    print(f"\n[6/6] Últimas 10 notificações registradas")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT criado_em, canal, sucesso, erro, substr(mensagem, 1, 70) AS m
               FROM notificacoes ORDER BY id DESC LIMIT 10"""
        ).fetchall()
    if not rows:
        print("  ❌ Nenhuma notificação registrada — provável que o scheduler.py "
              "NUNCA tenha rodado neste banco.")
    else:
        for r in rows:
            ok = "✅" if r["sucesso"] else "❌"
            print(f"  {ok} {r['criado_em']}  [{r['canal']}]  {r['m']}…")
            if not r["sucesso"] and r["erro"]:
                print(f"      erro: {r['erro'][:100]}")

    # 7. Teste vivo do Telegram
    print(f"\n[+] Teste de envio do Telegram")
    if not telegram_configurado():
        print("  ⏭ pulando (token/chat_id não configurado)")
    else:
        msg = (f"🔧 <b>Teste do diagnóstico</b>\n"
               f"Hora: {datetime.now():%d/%m/%Y %H:%M:%S}\n"
               f"Se você recebeu, o canal Telegram está OK.")
        ok, err = enviar_telegram(msg)
        if ok:
            print("  ✅ Mensagem de teste enviada — confira o Telegram agora.")
        else:
            print(f"  ❌ Falhou: {err}")

    linha()
    print("Fim do diagnóstico.")
    linha()


if __name__ == "__main__":
    main()
