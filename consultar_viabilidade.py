"""
consultar_viabilidade.py
------------------------
**Fase 1 — POC** de automação da consulta de Viabilidade no Facilita-SP /
Via Rápida REDESIM, usando Playwright + Chrome com sessão persistente.

NÃO mexe no banco — só lista no terminal os protocolos retornados pelo
portal. Use isto para validar que a raspagem está correta antes de
seguir para a Fase 2 (sincronizar com `protocolos_redesim`).

----------------------------------------------------------------------
PRÉ-REQUISITOS (instalar UMA VEZ no PowerShell, com a venv ativa):

    pip install -r requirements.txt
    playwright install chromium

----------------------------------------------------------------------
COMO USAR:

    python redesim_manager\\consultar_viabilidade.py

Na primeira execução o navegador abre VISÍVEL em
`https://vreredesim.sp.gov.br/home`. Você:
  1. Clica em "LOGIN VIA gov.br"
  2. Escolhe o certificado A1 da empresa
  3. Quando chegar no painel REDESIM (logado), volta no terminal e
     aperta ENTER.
O script então navega sozinho para "Viabilidade → Consultar →
Visualizar todos os protocolos" e imprime a tabela.

A sessão fica salva em `redesim_manager/data/browser_profile/`.
Próximas execuções não pedirão login (até a sessão expirar — algumas
horas / dia, depende do gov.br).

----------------------------------------------------------------------
FLAGS opcionais:
    --headless     Roda sem janela visível (só funciona se já houver
                   sessão salva e válida).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# garante que dá pra rodar de qualquer cwd
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

PROFILE_DIR = HERE / "data" / "browser_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

URL_HOME = "https://vreredesim.sp.gov.br/home"
URL_VIABILIDADE_CONSULTAR = (
    "https://www.jucesp.sp.gov.br/IntegradorPaulista/"
    "Viabilidade/ConsultarViabilidade"
)


def _imprimir_tabela(linhas: list[dict]) -> None:
    if not linhas:
        print("⚠ Nenhum protocolo encontrado na tabela.")
        return

    cols = ["protocolo", "data_solicitacao", "nome_empresarial",
            "evento", "status"]
    larguras = {c: max(len(c), max(len(str(l.get(c, ""))) for l in linhas))
                for c in cols}

    sep = " | "
    cab = sep.join(c.upper().ljust(larguras[c]) for c in cols)
    print(cab)
    print("-" * len(cab))
    for l in linhas:
        print(sep.join(str(l.get(c, "")).ljust(larguras[c]) for c in cols))


def consultar(headless: bool = False) -> list[dict]:
    """Abre o portal, navega até 'Visualizar todos os protocolos' e
    devolve a lista de dicionários extraída da tabela.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise SystemExit(
            "❌ Playwright não está instalado. Rode no PowerShell:\n"
            "   pip install playwright\n"
            "   playwright install chromium"
        )

    print(f"📂 Perfil persistente: {PROFILE_DIR}")
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = ctx.new_page()

        # Tenta direto a URL de consulta — se a sessão ainda for válida,
        # o portal abre normalmente; se não, redireciona para login.
        print("🌐 Abrindo portal Facilita-SP...")
        page.goto(URL_VIABILIDADE_CONSULTAR, wait_until="domcontentloaded")
        time.sleep(2)

        url_atual = page.url.lower()
        precisa_logar = (
            "consultarviabilidade" not in url_atual
            or "login" in url_atual
            or "sso" in url_atual
        )

        if precisa_logar:
            print()
            print("🔐 Sessão expirada ou primeira execução.")
            print(f"   Abrindo {URL_HOME} para você logar manualmente.")
            page.goto(URL_HOME, wait_until="domcontentloaded")
            print()
            print("=" * 60)
            print("👉 Faça login na janela que abriu:")
            print("   1. Clique em 'LOGIN VIA gov.br'")
            print("   2. Selecione o certificado A1 da empresa")
            print("   3. Aguarde chegar no painel REDESIM")
            print("=" * 60)
            input("Quando estiver logado, aperte ENTER aqui no terminal... ")

            print("🌐 Indo para a consulta de viabilidade...")
            page.goto(URL_VIABILIDADE_CONSULTAR, wait_until="domcontentloaded")
            time.sleep(2)

        # Clica em "Visualizar todos os protocolos"
        print("👆 Clicando em 'Visualizar todos os protocolos'...")
        try:
            page.get_by_role(
                "button", name="Visualizar todos os protocolos"
            ).click(timeout=8000)
        except PWTimeout:
            # fallback: tenta por texto
            try:
                page.click(
                    "text=Visualizar todos os protocolos", timeout=8000
                )
            except PWTimeout:
                print(
                    "❌ Não encontrei o botão 'Visualizar todos os "
                    "protocolos'. A página atual está em:"
                )
                print(f"   {page.url}")
                ctx.close()
                return []

        # Aguarda a tabela aparecer
        try:
            page.wait_for_selector("table tbody tr", timeout=15000)
        except PWTimeout:
            print(
                "⚠ Tabela não apareceu em 15s. Pode ser que você não "
                "tenha protocolos, ou a página tem outro layout."
            )
            ctx.close()
            return []

        # Extrai a tabela
        print("📋 Extraindo linhas da tabela...")
        linhas = page.evaluate(
            """
            () => {
              const rows = document.querySelectorAll('table tbody tr');
              return Array.from(rows).map(r => {
                const c = r.querySelectorAll('td');
                return {
                  protocolo: (c[0]?.innerText || '').trim(),
                  data_solicitacao: (c[1]?.innerText || '').trim(),
                  nome_empresarial: (c[2]?.innerText || '').trim(),
                  evento: (c[3]?.innerText || '').trim(),
                  status: (c[4]?.innerText || '').trim(),
                };
              }).filter(r => r.protocolo);
            }
            """
        )

        ctx.close()
        return linhas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--headless", action="store_true",
        help="Roda sem janela (só funciona se a sessão já estiver salva)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Saída em JSON (para uso em pipelines)",
    )
    args = parser.parse_args()

    linhas = consultar(headless=args.headless)

    print()
    if args.json:
        print(json.dumps(linhas, indent=2, ensure_ascii=False))
    else:
        print(f"✅ {len(linhas)} protocolo(s) encontrado(s):\n")
        _imprimir_tabela(linhas)


if __name__ == "__main__":
    main()
