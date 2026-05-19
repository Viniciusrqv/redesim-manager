"""
importar_gestta_json.py
-----------------------
Lê o JSON exportado pela API do GESTTA e SUBSTITUI o conteúdo da tabela
`tarefas_gestta` (apenas registros com origem_arquivo='API GESTTA').

Preserva os vínculos manuais (empresa_id, protocolo_id, resolvida) que
você já tinha marcado para tarefas que continuam na nova lista (matching
por gestta_id).

Uso:
    python redesim_manager\\importar_gestta_json.py [caminho_do_json]

Default: redesim_manager/data/tarefas_gestta_sync.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from database import init_db, upsert_tarefas_gestta_api, get_conn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path", nargs="?",
                    default=str(HERE / "data" / "tarefas_gestta_sync.json"))
    ap.add_argument("--keep-old", action="store_true",
                    help="NÃO limpa as antigas — apenas faz upsert (modo aditivo).")
    ap.add_argument("--full-reset", action="store_true", default=True,
                    help="Apaga TODAS as tarefas_gestta (independente de origem) "
                         "antes de inserir as novas. Default: ligado.")
    args = ap.parse_args()

    p = Path(args.json_path)
    if not p.exists():
        print(f"❌ Arquivo não encontrado: {p}")
        sys.exit(1)

    print(f"📂 Lendo {p} ({p.stat().st_size / 1024:.0f} KB)...")
    with p.open(encoding="utf-8") as f:
        tarefas = json.load(f)
    print(f"✅ {len(tarefas)} tarefas no JSON.")

    init_db()

    if not args.keep_old:
        # 1) backup dos vínculos manuais de TODAS as tarefas_gestta
        #    (não só da origem API — Eduardo pode querer reset completo)
        with get_conn() as conn:
            backup = {
                r["gestta_id"]: dict(r) for r in conn.execute(
                    """SELECT gestta_id, empresa_id, protocolo_id, resolvida
                         FROM tarefas_gestta
                        WHERE gestta_id IS NOT NULL"""
                ).fetchall()
            }
            n_back = len(backup)
            # 2) limpa TUDO (full reset — também remove imports antigos de XLSX)
            cur = conn.execute("DELETE FROM tarefas_gestta")
            n_del = cur.rowcount
            conn.commit()
        print(f"🗑  Removidas {n_del} tarefas antigas (full reset).")
        print(f"💾 Backup de {n_back} vínculos manuais antes da limpeza.")

    print("\n💾 Inserindo tarefas novas no banco local...")
    res = upsert_tarefas_gestta_api(tarefas)
    print(f"✅ Inseridas:    {res['inseridas']}")
    print(f"🔄 Atualizadas:  {res['atualizadas']}")
    print(f"🔗 Empresa vinc. (auto): {res['matched_empresa']}")

    if not args.keep_old:
        # 3) restaura vínculos manuais por gestta_id
        restored = 0
        with get_conn() as conn:
            for gid, info in backup.items():
                params = []
                sets = []
                if info.get("empresa_id") is not None:
                    sets.append("empresa_id = COALESCE(empresa_id, ?)")
                    params.append(info["empresa_id"])
                if info.get("protocolo_id") is not None:
                    sets.append("protocolo_id = COALESCE(protocolo_id, ?)")
                    params.append(info["protocolo_id"])
                if info.get("resolvida"):
                    sets.append("resolvida = ?")
                    params.append(1)
                if not sets:
                    continue
                params.append(gid)
                cur = conn.execute(
                    f"UPDATE tarefas_gestta SET {', '.join(sets)} "
                    f"WHERE gestta_id = ?",
                    params,
                )
                restored += cur.rowcount
            conn.commit()
        if restored:
            print(f"♻️  Vínculos manuais restaurados: {restored}")

    # Distribuições
    por_resp = Counter((t.get("owner") or {}).get("name") or "—" for t in tarefas)
    por_status = Counter(t.get("status") or "—" for t in tarefas)
    por_tipo = Counter(t.get("type") or "—" for t in tarefas)
    print("\n📊 Por responsável (top 10):")
    for n, q in por_resp.most_common(10):
        print(f"   {q:>4}  {n}")
    print(f"\n📊 Por status:  {dict(por_status)}")
    print(f"📊 Por tipo:    {dict(por_tipo)}")
    print(f"\n💡 Abra o app: streamlit run redesim_manager\\app.py")
    print("   → Dashboard ou 📋 Tarefas GESTTA")


if __name__ == "__main__":
    main()
