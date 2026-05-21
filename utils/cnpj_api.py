"""
cnpj_api.py
-----------
Consulta de CNPJ via APIs públicas (sem cadastro, sem custo).

Ordem de tentativa:
  1. BrasilAPI  (https://brasilapi.com.br) — espelho oficial Receita,
     muito estável, sem rate limit prático.
  2. ReceitaWS  (https://receitaws.com.br) — fallback. Limite de 3
     requisições por minuto na versão gratuita.

Resultado normalizado:
  {
    "cnpj":             "12345678000190",
    "razao_social":     "EXEMPLO LTDA",
    "nome_fantasia":    "Exemplo",
    "situacao":         "ATIVA" | "BAIXADA" | "INAPTA" | "SUSPENSA",
    "situacao_motivo":  "",
    "data_abertura":    "2010-05-20",
    "natureza_juridica":"Sociedade Empresária Limitada",
    "porte":            "ME" | "EPP" | "DEMAIS",
    "regime_tributario":"SIMPLES"|"LUCRO_PRESUMIDO"|"LUCRO_REAL"|None,
    "capital_social":   100000.00,
    "tipo":             "MATRIZ" | "FILIAL",
    "cnae_principal": {
        "codigo": "6920-6/01", "descricao": "..."
    },
    "cnaes_secundarios": [
        {"codigo": "...", "descricao": "..."}, ...
    ],
    "endereco": {
        "logradouro": "...", "numero": "...", "complemento": "...",
        "bairro": "...", "cep": "...", "municipio": "...",
        "uf": "...", "pais": "BRASIL",
    },
    "telefone":  "...",
    "email":     "...",
    "socios":    [{"nome":"...", "qualificacao":"..."}, ...],
    "fonte":     "brasilapi" | "receitaws",
    "consultado_em": "2026-05-21T14:30:00",
  }

Levanta `CNPJNaoEncontrado` se a Receita não conhece o CNPJ.
Levanta `CNPJApiError` se TODAS as fontes falharem.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import requests

log = logging.getLogger(__name__)

# Timeout curto pra não travar a UI do Streamlit
TIMEOUT_SEG = 12

# User-Agent identificável (algumas APIs bloqueiam UA padrão de requests)
_UA = (
    "REDESIM-Manager/1.0 (+CSM Contabilidade; "
    "contabil@csm.com.br) python-requests"
)


class CNPJApiError(Exception):
    """Falha ao consultar todas as fontes disponíveis."""


class CNPJNaoEncontrado(Exception):
    """CNPJ não existe na base da Receita."""


# ============================================================
# Validação / formatação
# ============================================================
def limpar_cnpj(cnpj: str) -> str:
    """Tira pontos/traços/barras. Retorna só os 14 dígitos."""
    return re.sub(r"\D", "", cnpj or "")


def cnpj_valido(cnpj: str) -> bool:
    """Valida CNPJ pelos dígitos verificadores (não consulta Receita)."""
    cnpj = limpar_cnpj(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def _dv(digs: str, pesos: list[int]) -> int:
        s = sum(int(d) * p for d, p in zip(digs, pesos))
        r = s % 11
        return 0 if r < 2 else 11 - r

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    dv1 = _dv(cnpj[:12], p1)
    dv2 = _dv(cnpj[:13], p2)
    return dv1 == int(cnpj[12]) and dv2 == int(cnpj[13])


def formatar_cnpj(cnpj: str) -> str:
    """Formata 14 dígitos como 00.000.000/0000-00."""
    c = limpar_cnpj(cnpj)
    if len(c) != 14:
        return cnpj
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


# ============================================================
# Fontes
# ============================================================
def _via_brasilapi(cnpj: str) -> dict[str, Any]:
    """Consulta BrasilAPI v1. Endpoint: /api/cnpj/v1/{cnpj}"""
    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=TIMEOUT_SEG)
    if resp.status_code == 404:
        raise CNPJNaoEncontrado(cnpj)
    if resp.status_code != 200:
        raise CNPJApiError(f"BrasilAPI HTTP {resp.status_code}")
    d = resp.json() or {}

    cnae_pr = (d.get("cnae_fiscal") or "")
    cnae_pr_d = (d.get("cnae_fiscal_descricao") or "")
    cnaes_sec = [
        {"codigo": _fmt_cnae(c.get("codigo")),
         "descricao": c.get("descricao") or ""}
        for c in (d.get("cnaes_secundarios") or [])
    ]

    return {
        "cnpj": cnpj,
        "razao_social": (d.get("razao_social") or "").strip(),
        "nome_fantasia": (d.get("nome_fantasia") or "").strip(),
        "situacao": (d.get("descricao_situacao_cadastral") or "").upper(),
        "situacao_motivo": (
            d.get("descricao_motivo_situacao_cadastral") or "").strip(),
        "data_abertura": d.get("data_inicio_atividade") or "",
        "natureza_juridica": (
            d.get("natureza_juridica") or "").strip(),
        "porte": _porte_brasilapi(d.get("porte")),
        "regime_tributario": _regime_brasilapi(d),
        "capital_social": float(d.get("capital_social") or 0),
        "tipo": (d.get("descricao_identificador_matriz_filial")
                 or "").upper(),
        "cnae_principal": {
            "codigo": _fmt_cnae(cnae_pr),
            "descricao": cnae_pr_d,
        },
        "cnaes_secundarios": cnaes_sec,
        "endereco": {
            "logradouro": (d.get("logradouro") or "").strip(),
            "numero": (d.get("numero") or "").strip(),
            "complemento": (d.get("complemento") or "").strip(),
            "bairro": (d.get("bairro") or "").strip(),
            "cep": _fmt_cep(d.get("cep")),
            "municipio": (d.get("municipio") or "").strip(),
            "uf": (d.get("uf") or "").strip(),
            "pais": "BRASIL",
        },
        "telefone": _fmt_tel(d.get("ddd_telefone_1")),
        "email": (d.get("email") or "").strip(),
        "socios": [
            {"nome": (s.get("nome_socio") or "").strip(),
             "qualificacao": (s.get("qualificacao_socio") or "").strip()}
            for s in (d.get("qsa") or [])
        ],
        "fonte": "brasilapi",
        "consultado_em": datetime.now().isoformat(timespec="seconds"),
    }


def _via_receitaws(cnpj: str) -> dict[str, Any]:
    """Fallback: ReceitaWS. 3 req/min na versão gratuita."""
    url = f"https://receitaws.com.br/v1/cnpj/{cnpj}"
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=TIMEOUT_SEG)
    if resp.status_code == 429:
        raise CNPJApiError("ReceitaWS rate limit (3/min)")
    if resp.status_code != 200:
        raise CNPJApiError(f"ReceitaWS HTTP {resp.status_code}")
    d = resp.json() or {}
    if d.get("status") == "ERROR":
        msg = (d.get("message") or "").lower()
        if "número de cnpj inválido" in msg or "não existe" in msg:
            raise CNPJNaoEncontrado(cnpj)
        raise CNPJApiError(f"ReceitaWS: {d.get('message')}")

    atividade_principal = (d.get("atividade_principal") or [{}])[0]
    return {
        "cnpj": cnpj,
        "razao_social": (d.get("nome") or "").strip(),
        "nome_fantasia": (d.get("fantasia") or "").strip(),
        "situacao": (d.get("situacao") or "").upper(),
        "situacao_motivo": (d.get("motivo_situacao") or "").strip(),
        "data_abertura": _fmt_data(d.get("abertura")),
        "natureza_juridica": (
            d.get("natureza_juridica") or "").strip(),
        "porte": (d.get("porte") or "").upper(),
        "regime_tributario": (
            "SIMPLES" if d.get("simples", {}).get("optante") else None
        ),
        "capital_social": _parse_money(d.get("capital_social")),
        "tipo": (d.get("tipo") or "").upper(),
        "cnae_principal": {
            "codigo": atividade_principal.get("code", ""),
            "descricao": atividade_principal.get("text", ""),
        },
        "cnaes_secundarios": [
            {"codigo": a.get("code", ""),
             "descricao": a.get("text", "")}
            for a in (d.get("atividades_secundarias") or [])
        ],
        "endereco": {
            "logradouro": (d.get("logradouro") or "").strip(),
            "numero": (d.get("numero") or "").strip(),
            "complemento": (d.get("complemento") or "").strip(),
            "bairro": (d.get("bairro") or "").strip(),
            "cep": _fmt_cep(d.get("cep")),
            "municipio": (d.get("municipio") or "").strip(),
            "uf": (d.get("uf") or "").strip(),
            "pais": "BRASIL",
        },
        "telefone": (d.get("telefone") or "").strip(),
        "email": (d.get("email") or "").strip(),
        "socios": [
            {"nome": (s.get("nome") or "").strip(),
             "qualificacao": (s.get("qual") or "").strip()}
            for s in (d.get("qsa") or [])
        ],
        "fonte": "receitaws",
        "consultado_em": datetime.now().isoformat(timespec="seconds"),
    }


# ============================================================
# Função pública
# ============================================================
def consultar_cnpj(cnpj: str) -> dict[str, Any]:
    """
    Consulta o CNPJ pela melhor fonte disponível.

    Tenta BrasilAPI primeiro. Se falhar com erro de rede / 5xx, tenta
    ReceitaWS. Se a Receita devolve "não encontrado", levanta
    CNPJNaoEncontrado sem tentar outras (poupa tempo).
    """
    cnpj = limpar_cnpj(cnpj)
    if len(cnpj) != 14:
        raise CNPJApiError("CNPJ deve ter 14 dígitos.")
    if not cnpj_valido(cnpj):
        raise CNPJApiError("CNPJ inválido (dígitos verificadores).")

    erros = []
    for nome, fn in [("brasilapi", _via_brasilapi),
                     ("receitaws", _via_receitaws)]:
        try:
            return fn(cnpj)
        except CNPJNaoEncontrado:
            # Receita disse "não existe" — não vale a pena tentar outra fonte
            raise
        except (CNPJApiError, requests.RequestException) as exc:
            log.warning("[%s] %s", nome, exc)
            erros.append(f"{nome}: {exc}")
            continue

    raise CNPJApiError(
        "Todas as fontes falharam → " + " | ".join(erros)
    )


# ============================================================
# Helpers internos
# ============================================================
def _fmt_cnae(codigo) -> str:
    """Recebe '6920601' ou 6920601 → '6920-6/01'."""
    if codigo is None:
        return ""
    s = re.sub(r"\D", "", str(codigo))
    if len(s) == 7:
        return f"{s[:4]}-{s[4]}/{s[5:]}"
    return str(codigo)


def _fmt_cep(cep) -> str:
    if not cep:
        return ""
    s = re.sub(r"\D", "", str(cep))
    if len(s) == 8:
        return f"{s[:5]}-{s[5:]}"
    return str(cep)


def _fmt_tel(tel) -> str:
    if not tel:
        return ""
    s = re.sub(r"\D", "", str(tel))
    if len(s) == 11:
        return f"({s[:2]}) {s[2:7]}-{s[7:]}"
    if len(s) == 10:
        return f"({s[:2]}) {s[2:6]}-{s[6:]}"
    return str(tel)


def _fmt_data(s: str | None) -> str:
    """'20/05/2010' → '2010-05-20'."""
    if not s:
        return ""
    try:
        d, m, y = s.split("/")
        return f"{y}-{m}-{d}"
    except Exception:
        return s or ""


def _parse_money(s) -> float:
    if s is None:
        return 0.0
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except Exception:
        return 0.0


def _porte_brasilapi(codigo) -> str:
    mapa = {
        "00": "NAO_INFORMADO",
        "01": "ME",       # micro
        "03": "EPP",      # equiparado
        "05": "DEMAIS",   # médio + grande
    }
    return mapa.get(str(codigo or "").zfill(2), "DESCONHECIDO")


def _regime_brasilapi(d: dict) -> str | None:
    if d.get("opcao_pelo_simples"):
        return "SIMPLES"
    if d.get("opcao_pelo_mei"):
        return "MEI"
    # BrasilAPI não traz lucro presumido/real explicitamente
    return None
