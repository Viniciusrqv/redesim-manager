"""
fechar_protocolos_orfaos.py
---------------------------
Limpeza única: fecha protocolos REDESIM que ficaram "em andamento"
mas cuja empresa já tem processo antigo finalizado
(Deferido/Indeferido/Arquivado).

Causa: o sistema antigo (processos) e o novo (protocolos_redesim)
nasceram separados. Antes do fix no atualizar_status, fechar o
processo no Dashboard não fechava o protocolo REDESIM correspondente
— e o Telegram continuava mandando ATRASO CRÍTICO desses órfãos.

Rode 1x (antes/depois do deploy do fix):
    python redesim_manager/fechar_protocolos_orfaos.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from database import init_db, get_conn  # noqa: E402


MAPA_STATUS = {
    "Deferido": ("Concluída", "Aprovada"),   # licenciamento, viabilidade
    "Indeferido": ("Indeferida", "Indeferida"),
    "Arquivado": ("Cancelada", "Cancelada"),
}


def main():
    init_db()
    print("=" * 70)
    print(" LIMPEZA — fechando protocolos REDESIM órfãos")
    print("=" * 70)

    with get_conn() as conn:
        # Acha empresas com processo finalizado
        proc_finalizados = conn.execute(
            """SELECT id AS processo_id, empresa_id, status,
                      ultima_movimentacao
               FROM processos
               WHERE status IN ('Deferido','Indeferido','Arquivado')"""
        ).fetchall()
        emp_status = {}
        for row in proc_finalizados:
            d = dict(row)
            # Pega o status mais recente por empresa
            atual = emp_status.get(d["empresa_id"])
            if atual is None or d["ultima_movimentacao"] > atual["data"]:
                emp_status[d["empresa_id"]] = {
                    "status": d["status"],
                    "data": d["ultima_movimentacao"],
                }

        print(f"Empresas com processo finalizado: {len(emp_status)}")

        # Acha protocolos REDESIM ainda abertos dessas empresas
        if not emp_status:
            print("Nada a fazer.")
            return

        emp_ids = list(emp_status.keys())
        placeholders = ",".join("?" * len(emp_ids))
        protocolos_orfaos = conn.execute(
            f"""SELECT id, empresa_id, tipo, numero_protocolo, status
                FROM protocolos_redesim
                WHERE empresa_id IN ({placeholders})
                  AND status NOT IN
                    ('Aprovada','Concluída','Indeferida',
                     'Cancelada','Inativa')
                  AND substituido_por_id IS NULL""",
            tuple(emp_ids),
        ).fetchall()

        print(f"Protocolos órfãos encontrados: {len(protocolos_orfaos)}")
        if not protocolos_orfaos:
            print("Nada a fechar. ✅")
            return

        # Fecha cada um conforme o status do processo da empresa
        n = 0
        for r in protocolos_orfaos:
            p = dict(r)
            status_proc = emp_status[p["empresa_id"]]["status"]
            status_lic, status_via = MAPA_STATUS[status_proc]
            novo_status = (
                status_via if p["tipo"] == "Viabilidade"
                else status_lic
            )
            conn.execute(
                """UPDATE protocolos_redesim
                   SET status = ?,
                       atualizado_em = datetime('now','localtime')
                   WHERE id = ?""",
                (novo_status, p["id"]),
            )
            print(
                f"  ✓ #{p['id']:5d} {p['numero_protocolo'] or '?':>12s} "
                f"({p['tipo']:14s}) {p['status']:30s} → {novo_status}"
            )
            n += 1

        print("=" * 70)
        print(f"Total fechado: {n} protocolo(s).")
        print(
            "✅ A próxima rodada do GitHub Actions (10h ou 15h) NÃO vai "
            "mais mandar alerta destes."
        )


if __name__ == "__main__":
    main()
