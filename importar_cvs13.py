"""
importar_cvs13.py
-----------------
Importa a lista de CNAEs ISENTOS de licenciamento sanitário da
Portaria CVS-SP nº 13, de 07/11/2025.

Ações:
  - Lê redesim_manager/data/cvs13_cnaes.json (1.202 CNAEs)
  - UPSERT em `vigilancia_sanitaria` com:
        exige_licenca = 0
        nivel = 'ISENTO'
        risco_sanitario = 'BAIXO_ISENTO'
        fonte = 'Portaria CVS 13/2025'
        descricao = (do PDF)
  - Marca em `normas_atualizacao` como nova versão da base CVS-SP

Uso:
    python redesim_manager\\importar_cvs13.py
    python redesim_manager\\importar_cvs13.py --dry-run    # só conta, não grava
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from database import (
    init_db, get_conn, upsert_vigilancia,
    registrar_atualizacao_norma,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(HERE / "data" / "cvs13_cnaes.json"),
                    help="Caminho do JSON exportado pelo parser do PDF.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Só mostra o que seria importado, não grava no banco.")
    args = ap.parse_args()

    p = Path(args.json)
    if not p.exists():
        print(f"❌ JSON não encontrado: {p}")
        sys.exit(1)

    print(f"📂 Lendo {p} ({p.stat().st_size / 1024:.0f} KB)…")
    with p.open(encoding="utf-8") as f:
        cnaes = json.load(f)
    print(f"✅ {len(cnaes)} CNAEs no JSON.\n")

    # Análise prévia: quantos já estão na base com exige_licenca=1
    init_db()
    with get_conn() as conn:
        rows = {
            r["cnae"]: dict(r) for r in conn.execute(
                "SELECT cnae, exige_licenca, fonte FROM vigilancia_sanitaria"
            ).fetchall()
        }
    print(f"📊 Base atual de Vigilância: {len(rows)} CNAEs cadastrados.")

    novos = sum(1 for c in cnaes if c["cnae"] not in rows)
    sobrescreve_obrigatorio = sum(
        1 for c in cnaes
        if c["cnae"] in rows and rows[c["cnae"]].get("exige_licenca")
    )
    sobrescreve_isento = sum(
        1 for c in cnaes
        if c["cnae"] in rows and not rows[c["cnae"]].get("exige_licenca")
    )

    print(f"  ➕ Novos:                     {novos}")
    print(f"  ⚠️  Sobrescreve OBRIGATÓRIO:   {sobrescreve_obrigatorio}")
    print(f"     (era exigir licença, vira ISENTO)")
    print(f"  🔄 Atualiza outros isentos:   {sobrescreve_isento}")

    com_cond = sum(1 for c in cnaes if "Desde que" in (c.get("condicionante") or ""))
    print(f"\n  📌 Com condicionante específica ('Desde que…'): {com_cond}")
    print(f"     → mantém isenção MAS depende de cumprir a condição.")

    if args.dry_run:
        print("\n🟡 dry-run: nada gravado no banco.")
        return

    print("\n💾 Importando…")
    inseridos = atualizados = 0
    cond_count = isento_count = 0
    for c in cnaes:
        cnae = c["cnae"]
        descricao = (c.get("descricao") or "").strip()
        cond = (c.get("condicionante") or "").strip()
        # 🔑 Distingue isenção TOTAL de CONDICIONAL:
        #    - "Não compete à vigilância sanitária" → ISENTO total
        #    - "Desde que ..." → ISENCAO_CONDICIONAL (depende de regras)
        is_condicional = bool(cond) and (
            "desde que" in cond.lower()
            or "exclusivamente" in cond.lower()
            or "apenas" in cond.lower()
        )
        if is_condicional:
            nivel = "ISENCAO_CONDICIONAL"
            descricao = f"{descricao} | ⚠️ ISENÇÃO CONDICIONAL: {cond}"
            cond_count += 1
        else:
            nivel = "ISENTO"
            isento_count += 1
        try:
            upsert_vigilancia(
                cnae=cnae,
                descricao=descricao or "(sem descrição extraída)",
                exige_licenca=False,  # ambos casos: não exige licença POR PADRÃO
                nivel=nivel,
                fonte="Portaria CVS 13/2025",
            )
            if cnae in rows:
                atualizados += 1
            else:
                inseridos += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠ erro em {cnae}: {exc}")
    print(f"\n  ✅ Isentos totais (sem condição): {isento_count}")
    print(f"  ⚠️  Isentos CONDICIONAIS:          {cond_count}")
    print(f"     (precisa cumprir condição pra ficar isento)")

    print(f"\n✅ Inseridos:     {inseridos}")
    print(f"🔄 Atualizados:   {atualizados}")

    # Registra na norma
    registrar_atualizacao_norma(
        base="CVS-SP",
        orgao="Centro de Vigilância Sanitária — SES-SP",
        versao="Portaria CVS 13/2025",
        observacoes=(
            f"Importação da Portaria CVS nº 13, de 07/11/2025 — "
            f"atividades de Risco I (Baixo) ISENTAS de licenciamento. "
            f"Total: {len(cnaes)} CNAEs. {com_cond} com condicionante 'Desde que'."
        ),
    )
    print("\n📚 Registrada em `normas_atualizacao`.")
    print("\n🎯 Concluído. Para conferir no app:")
    print("   streamlit run redesim_manager\\app.py")
    print("   → 🔬 Consultor de CNAE → digita um CNAE da lista")


if __name__ == "__main__":
    main()
