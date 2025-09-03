# -*- coding: utf-8 -*-
"""Cliente para operações de mailing na API 3C Plus.

O módulo implementa a classe :class:`ThreeCMailingClient` responsável por
criar containers de mailing, enviar contatos e ajustar peso do mailing.
Ele reutiliza o cliente de autenticação :class:`auth_3cplus.ThreeCAuthClient`
para manter o token válido e realizar as requisições autenticadas.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests  # type: ignore[import-untyped]
from requests import Response, Session  # type: ignore[import-untyped]
from requests.exceptions import RequestException, Timeout  # type: ignore[import-untyped]

from auth_3cplus import (
    ApiUnavailable,
    InputInvalid,
    RateLimitExceeded,
    ThreeCAuthClient,
    Unauthorized,
)


# ---------------------------------------------------------------------------
# Exceções específicas
# ---------------------------------------------------------------------------


class ThreeCMailingError(Exception):
    """Erro base para operações de mailing."""


class CampaignNotFound(ThreeCMailingError):
    """Campanha não encontrada."""


class CreateMailingFailed(ThreeCMailingError):
    """Falha ao criar container de mailing."""


class UploadFailed(ThreeCMailingError):
    """Falha ao enviar contatos."""


class WeightUpdateFailed(ThreeCMailingError):
    """Falha ao atualizar peso do mailing."""


# ---------------------------------------------------------------------------
# Estruturas de dados
# ---------------------------------------------------------------------------


@dataclass
class Contact:
    """Representa um contato a ser enviado para a API."""

    name: Optional[str] = None
    document: Optional[str] = None
    phones: List[str] = field(default_factory=list)
    email: Optional[str] = None
    external_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:  # validações simples
        if len(self.phones) > 20:
            raise ValueError("Cada contato pode conter no máximo 20 telefones")
        self.phones = [str(p) for p in self.phones]

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "document": self.document,
            "phones": self.phones,
            "email": self.email,
            "external_id": self.external_id,
        }
        data.update(self.extra)
        # Remove chaves com valor None
        return {k: v for k, v in data.items() if v is not None}


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------


class ThreeCMailingClient:
    """Cliente desacoplado para operações de mailing na 3C Plus."""

    DEFAULT_ENDPOINTS: Dict[str, List[str]] = {
        "listar_campanhas": ["campaign lists", "campaign/lists"],
        "criar_container": ["create malling list", "create mailing list"],
        "enviar_json": ["create mailing json"],
        "enviar_array": ["create mailing by array"],
        "enviar_csv": ["malling list csv", "mailing/list/csv"],
        "ajustar_peso": ["Update weight"],
    }

    def __init__(
        self,
        auth_client: ThreeCAuthClient,
        *,
        base_url: str | None = None,
        timeout: float = 20.0,
        max_retries: int = 3,
        endpoints: Optional[Dict[str, Iterable[str]]] = None,
        session: Optional[Session] = None,
        persist_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.auth_client = auth_client
        self.base_url = (base_url or auth_client.base_url).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or auth_client.session or requests.Session()
        self.logger = logging.getLogger(self.__class__.__name__)
        # merge endpoints
        self.endpoints: Dict[str, List[str]] = {
            k: list(v) for k, v in self.DEFAULT_ENDPOINTS.items()
        }
        if endpoints:
            for k, v in endpoints.items():
                self.endpoints[k] = list(v)
        self.persist_callback = persist_callback
        self.mailing_ids: List[int] = []
        self.campaign_ids: List[int] = []

    # ------------------------------------------------------------------
    # Resolução de endpoints
    # ------------------------------------------------------------------
    def _resolve_endpoint(self, key: str) -> List[str]:
        paths = self.endpoints.get(key)
        if not paths:
            raise ThreeCMailingError(f"Endpoint não configurado para: {key}")
        clean = [p.lstrip("/") for p in paths]
        return clean

    # ------------------------------------------------------------------
    # Requisições HTTP com retry e variações de endpoints
    # ------------------------------------------------------------------
    def _request_json(
        self,
        method: str,
        endpoint_key: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        data_fields: Optional[Dict[str, Any]] = None,
        files: Any | None = None,
        idempotent: bool = False,
    ) -> Response:
        paths = self._resolve_endpoint(endpoint_key)
        last_exc: Exception | None = None
        for path in paths:
            url = f"{self.base_url}/{path}".replace(" ", "/")
            headers: Dict[str, str] = {}
            if idempotent:
                headers["Idempotency-Key"] = str(uuid.uuid4())
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = self.session.request(
                        method,
                        url,
                        json=json_data,
                        params=params,
                        data=data_fields,
                        files=files,
                        headers=headers or None,
                        timeout=self.timeout,
                    )
                except Timeout as exc:
                    last_exc = exc
                except RequestException as exc:
                    last_exc = exc
                else:
                    if response.status_code == 404:
                        # tenta próxima variação
                        break
                    if response.status_code >= 500:
                        last_exc = ApiUnavailable(
                            f"Erro {response.status_code} na API"
                        )
                    else:
                        return response
                if attempt < self.max_retries:
                    sleep = (2 ** (attempt - 1)) + 0.1
                    time.sleep(sleep)
            if last_exc and isinstance(last_exc, ApiUnavailable):
                continue
        # se chegou aqui, algo deu errado
        if isinstance(last_exc, Timeout):
            raise ApiUnavailable("Tempo de requisição excedido") from last_exc
        if isinstance(last_exc, RequestException):
            raise ApiUnavailable("Erro de rede") from last_exc
        # pode ter retornado 404 em todos os caminhos
        raise CampaignNotFound(f"Endpoint {endpoint_key} não encontrado")

    def _get_json(self, endpoint_key: str, *, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        resp = self._request_json("GET", endpoint_key, params=params)
        return self._handle_response(resp, endpoint_key)

    def _post_json(
        self,
        endpoint_key: str,
        json_data: Dict[str, Any] | None = None,
        data_fields: Dict[str, Any] | None = None,
        files: Any | None = None,
    ) -> Dict[str, Any]:
        resp = self._request_json(
            "POST",
            endpoint_key,
            json_data=json_data,
            data_fields=data_fields,
            files=files,
            idempotent=True,
        )
        return self._handle_response(resp, endpoint_key)

    def _put_json(self, endpoint_key: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._request_json(
            "PUT", endpoint_key, json_data=json_data, idempotent=True
        )
        return self._handle_response(resp, endpoint_key)

    def _handle_response(self, response: Response, endpoint_key: str) -> Dict[str, Any]:
        if response.status_code in {200, 201}:
            try:
                return response.json()
            except ValueError as exc:  # pragma: no cover - resposta inválida
                raise ThreeCMailingError("Resposta inválida da API") from exc
        if response.status_code in {400, 422}:
            raise InputInvalid("Payload inválido")
        if response.status_code in {401, 403}:
            raise Unauthorized("Não autorizado")
        if response.status_code == 404:
            raise CampaignNotFound(f"Endpoint {endpoint_key} não encontrado")
        if response.status_code == 409:
            raise UploadFailed("Dados duplicados")
        if response.status_code == 429:
            raise RateLimitExceeded("Muitas requisições")
        if response.status_code >= 500:
            raise ApiUnavailable("Serviço indisponível")
        raise ThreeCMailingError(
            f"Erro inesperado ({response.status_code}) ao acessar {endpoint_key}"
        )

    # ------------------------------------------------------------------
    # Operações públicas
    # ------------------------------------------------------------------
    def listar_campanhas(
        self, filtro: str | None = None, somente_ativas: bool = True
    ) -> List[Dict[str, Any]]:
        data = self._get_json("listar_campanhas")
        campanhas = data.get("data") or data.get("campaigns") or []
        result: List[Dict[str, Any]] = []
        for camp in campanhas:
            if filtro and filtro.lower() not in str(camp.get("name", "")).lower():
                continue
            if somente_ativas and not camp.get("active", True):
                continue
            cid = camp.get("id")
            if isinstance(cid, int):
                self.campaign_ids.append(cid)
            result.append(camp)
        return result

    def criar_mailing_container(
        self, nome: str, campanha_id: int, meta: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": nome,
            "campaign_id": campanha_id,
        }
        if meta:
            payload["meta"] = meta
        try:
            data = self._post_json("criar_container", payload)
        except UploadFailed as exc:
            raise CreateMailingFailed("Conflito ao criar mailing") from exc
        mailing_id = self._extract_id(data, [
            "data.mailing_id",
            "data.id",
            "mailing_id",
            "id",
        ])
        result = {
            "mailing_id": mailing_id,
            "campaign_id": campanha_id,
        }
        self.mailing_ids.append(mailing_id)
        if self.persist_callback:
            try:
                self.persist_callback(result)
            except Exception:  # pragma: no cover - callback externo
                self.logger.exception("Falha no callback de persistência")
        return result

    def enviar_mailing_json(
        self, mailing_id: int, contatos: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        contatos_validados = [Contact(**c).to_dict() for c in contatos]
        payload = {"mailing_id": mailing_id, "data": contatos_validados}
        if len(contatos_validados) > 20:
            self.logger.info("Enviando %s contatos", len(contatos_validados))
        data = self._post_json("enviar_json", payload)
        return data

    def enviar_mailing_array(
        self,
        mailing_id: int,
        contatos: List[Dict[str, Any]] | List[List[str | int]],
    ) -> Dict[str, Any]:
        payload = {"mailing_id": mailing_id, "data": contatos}
        data = self._post_json("enviar_array", payload)
        return data

    def enviar_mailing_csv(
        self,
        mailing_id: int,
        caminho_csv: str,
        *,
        colmap: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        if not os.path.exists(caminho_csv):
            raise UploadFailed("Arquivo CSV não encontrado")
        with open(caminho_csv, "rb") as f:
            files = {"file": (os.path.basename(caminho_csv), f, "text/csv")}
            data_form = {"mailing_id": str(mailing_id)}
            if colmap:
                data_form.update(colmap)
            resp = self._request_json(
                "POST",
                "enviar_csv",
                data_fields=data_form,
                files=files,
                idempotent=True,
            )
            return self._handle_response(resp, "enviar_csv")

    def ajustar_peso_mailing(self, mailing_id: int, peso: int) -> None:
        payload = {"mailing_id": mailing_id, "weight": peso}
        data = self._put_json("ajustar_peso", payload)
        if not data.get("success", True):  # API pode retornar status
            raise WeightUpdateFailed("Falha ao atualizar peso")

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _extract_id(self, data: Dict[str, Any], keys: List[str]) -> int:
        for key in keys:
            target = data
            parts = key.split(".")
            try:
                for part in parts:
                    target = target[part]
            except (KeyError, TypeError):
                continue
            if isinstance(target, int):
                return target
            if isinstance(target, str) and target.isdigit():
                return int(target)
        raise CreateMailingFailed("ID do mailing não encontrado na resposta")
