"""
gestta_api.py
-------------
Cliente HTTP da API privada do GESTTA (https://api.gestta.com.br).

A API não é pública mas o front do GESTTA usa REST com JWT armazenado em
`localStorage["ngStorage-jwt"]`. O Eduardo cola o JWT no .env e este módulo
chama os endpoints diretamente.

⚠️  O JWT expira em ~24h. Quando expirar, o sistema avisa e o Eduardo
copia um novo do navegador (DevTools → Application → Local Storage).

Como pegar o JWT:
  1. Abrir https://app.gestta.com.br logado
  2. F12 → Application → Local Storage → app.gestta.com.br
  3. Copiar o valor da chave `ngStorage-jwt`
     (vem como `"JWT eyJ..."` — copie o conteúdo INCLUINDO o `JWT ` no
     início, mas SEM as aspas externas)
  4. Colar em `redesim_manager/.env` na variável GESTTA_JWT
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Iterable

import requests

log = logging.getLogger(__name__)

API_BASE = "https://api.gestta.com.br"

# Tipos suportados pelo endpoint /core/customer/task/search
TIPOS_TAREFA_GESTTA = ["SERVICE_ORDER", "RECURRENT", "ACCOUNTING"]

# Status conhecidos das tarefas
STATUS_TAREFA_GESTTA_ABERTAS = ["OPEN", "IMPEDIMENT"]


class GesttaAuthError(RuntimeError):
    """Token JWT ausente, inválido ou expirado."""


class GesttaAPIError(RuntimeError):
    """Erro genérico de chamada à API."""


def _jwt_payload(jwt: str) -> dict:
    """Decodifica o payload (segunda parte) do JWT sem validar assinatura."""
    if not jwt:
        return {}
    raw = jwt.replace("JWT ", "", 1).strip()
    parts = raw.split(".")
    if len(parts) != 3:
        return {}
    body = parts[1]
    # base64 url decode (adiciona padding se faltar)
    body += "=" * (-len(body) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(body))
    except Exception:  # noqa: BLE001
        return {}


def jwt_info(jwt: str) -> dict:
    """Retorna info legível do JWT: usuário, empresa, expiração, dias restantes."""
    p = _jwt_payload(jwt)
    if not p:
        return {"valido": False, "erro": "Não foi possível decodificar o JWT."}
    exp = p.get("exp")
    iat = p.get("iat")
    info: dict = {
        "valido": True,
        "user_id": p.get("_id"),
        "user_name": p.get("name"),
        "user_email": p.get("email"),
        "company": p.get("company", {}).get("name"),
        "company_id": p.get("company", {}).get("_id"),
        "role": p.get("role"),
    }
    if exp:
        d_exp = datetime.fromtimestamp(exp, tz=timezone.utc)
        agora = datetime.now(timezone.utc)
        info["expira_em"] = d_exp.isoformat()
        delta = d_exp - agora
        info["expirado"] = delta.total_seconds() < 0
        info["horas_restantes"] = round(delta.total_seconds() / 3600, 1)
    if iat:
        info["emitido_em"] = datetime.fromtimestamp(iat, tz=timezone.utc).isoformat()
    return info


class GesttaClient:
    """Cliente da API do GESTTA. Use:

        cli = GesttaClient(jwt)
        for tarefa in cli.iter_tarefas(start='2026-04-01', end='2026-05-01'):
            ...
    """

    def __init__(self, jwt: str, *, timeout: int = 20):
        if not jwt:
            raise GesttaAuthError("JWT vazio. Configure GESTTA_JWT no .env.")
        # GESTTA aceita o header literal `Authorization: JWT eyJ...`
        if not jwt.startswith("JWT "):
            jwt = "JWT " + jwt
        self.jwt = jwt
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": jwt,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "REDESIM-Manager/1.0 (CSM Contabilidade)",
        })

    # ------------------------------------------------------------ utilitários
    def _check(self, resp: requests.Response, ctx: str) -> dict:
        if resp.status_code == 401:
            raise GesttaAuthError(
                f"JWT inválido ou expirado (HTTP 401 em {ctx}). "
                f"Cole um novo token no .env."
            )
        if resp.status_code >= 400:
            raise GesttaAPIError(
                f"{ctx} retornou HTTP {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise GesttaAPIError(
                f"{ctx} não retornou JSON válido: {exc}"
            ) from exc

    def info_token(self) -> dict:
        return jwt_info(self.jwt)

    # ------------------------------------------------------------ /core/customer/task/search
    def listar_tarefas(
        self,
        *,
        tipos: Iterable[str] = TIPOS_TAREFA_GESTTA,
        status: Iterable[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        date_type: str = "DUE_DATE",
        page: int = 1,
        limit: int = 50,
        no_owner: bool = True,
        os_workflow: bool = True,
    ) -> dict:
        """Chama POST /core/customer/task/search e retorna o objeto bruto:
        { docs, limit, page, pages, total }.

        Datas em ISO (`YYYY-MM-DDTHH:MM:SS.sssZ`) ou `YYYY-MM-DD`.
        """
        body = {
            "type": list(tipos),
            "date_type": date_type,
            "page": page,
            "limit": limit,
            "no_owner": no_owner,
            "os_workflow": os_workflow,
        }
        if status is not None:
            body["status"] = list(status)
        if start_date:
            body["start_date"] = (
                start_date if "T" in start_date
                else f"{start_date}T03:00:00.000Z"
            )
        if end_date:
            body["end_date"] = (
                end_date if "T" in end_date
                else f"{end_date}T02:59:59.999Z"
            )
        resp = self._session.post(
            f"{API_BASE}/core/customer/task/search",
            json=body, timeout=self.timeout,
        )
        return self._check(resp, "listar_tarefas")

    def iter_tarefas(self, **kwargs) -> Iterable[dict]:
        """Gerador que pagina automaticamente sobre `listar_tarefas`."""
        page = 1
        kwargs.setdefault("limit", 50)
        while True:
            kwargs["page"] = page
            resp = self.listar_tarefas(**kwargs)
            docs = resp.get("docs") or []
            for d in docs:
                yield d
            if page >= (resp.get("pages") or 1) or not docs:
                break
            page += 1

    def contar_tarefas(self, **kwargs) -> int:
        """Atalho: total reportado pela primeira página."""
        kwargs["limit"] = 1
        kwargs["page"] = 1
        resp = self.listar_tarefas(**kwargs)
        return int(resp.get("total") or 0)

    # ------------------------------------------------------------ /core/customer
    def listar_clientes(self, *, page: int = 1, limit: int = 200) -> dict:
        resp = self._session.get(
            f"{API_BASE}/core/customer",
            params={"page": page, "limit": limit},
            timeout=self.timeout,
        )
        return self._check(resp, "listar_clientes")

    # ------------------------------------------------------------ /core/company/user
    def listar_usuarios_empresa(self) -> dict:
        resp = self._session.get(
            f"{API_BASE}/core/company/user", timeout=self.timeout,
        )
        return self._check(resp, "listar_usuarios_empresa")

    # ------------------------------------------------------------ /core/company/department
    def listar_departamentos(self) -> dict:
        resp = self._session.get(
            f"{API_BASE}/core/company/department", timeout=self.timeout,
        )
        return self._check(resp, "listar_departamentos")

    # ============================================================
    # ESCRITA — endpoints validados via Claude in Chrome (04/05/2026)
    # ============================================================

    def adicionar_comentario_tarefa(
        self, gestta_id: str, texto: str,
        *, mentions: list | None = None, cc_mentions: list | None = None,
        files: list | None = None, external: bool = False,
    ) -> dict:
        """POST de comentário/anotação numa tarefa.

        Endpoint REAL (capturado em 04/05/2026 via interceptor XHR):
            POST /core/customer/task/{gestta_id}/history/comment

        Body esperado pelo GESTTA:
            {
              "files": [],
              "external": false,
              "message": "<p>texto em HTML</p>",
              "mentions": [],
              "cc_mentions": []
            }

        Response 201 com `_id` do history criado, e o objeto inteiro
        do company / task / history.

        Args:
            gestta_id: _id da tarefa (24 hex chars)
            texto: texto puro ou HTML; se for puro, envolve em <p>
            mentions: lista de user IDs mencionados (@nome)
            cc_mentions: lista de user IDs em cópia
            files: anexos (cada item dict do upload prévio)
            external: se True, anotação é visível ao cliente
                (aba "Usuários de cliente"); se False, fica só
                interno (aba "Funcionários" — uso comum nosso).
        """
        msg = texto if texto.lstrip().startswith("<") else f"<p>{texto}</p>"
        body = {
            "files": files or [],
            "external": bool(external),
            "message": msg,
            "mentions": mentions or [],
            "cc_mentions": cc_mentions or [],
        }
        path = f"/core/customer/task/{gestta_id}/history/comment"
        resp = self._session.post(
            f"{API_BASE}{path}", json=body, timeout=self.timeout,
        )
        if resp.status_code in (200, 201):
            data = None
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                pass
            return {
                "endpoint_usado": path,
                "status": resp.status_code,
                "history_id": (data or {}).get("_id"),
                "data": data,
            }
        raise GesttaAPIError(
            f"POST {path} retornou HTTP {resp.status_code}: "
            f"{resp.text[:200]}"
        )

    # NOTA: alterar_status_tarefa() foi removido em 04/05/2026.
    # Decisão do Eduardo: a conclusão / impedimento da tarefa fica
    # pra fazer manualmente no GESTTA. Aqui só replicamos anotações,
    # que é o que importa pra deixar o histórico atualizado.
