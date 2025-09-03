"""Testes para o cliente de autenticação 3C Plus.

Os testes não dependem de bibliotecas externas como ``requests``.
Um módulo ``requests`` mínimo é injetado em ``sys.modules`` para que o
cliente funcione em ambientes sem dependências instaladas.
"""

from __future__ import annotations

# mypy: ignore-errors

import sys
import types
from typing import Any, Dict, List, Optional

import pytest


# ---------------------------------------------------------------------------
# Módulo fake ``requests``
# ---------------------------------------------------------------------------


class RequestException(Exception):
    """Exceção base das requisições."""


class Timeout(RequestException):
    """Exceção para simular timeout."""


class Response:
    def __init__(self, status_code: int = 200, json_data: Optional[Dict[str, Any]] = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> Dict[str, Any]:
        return self._json


class Session:
    def __init__(self) -> None:
        self.headers: Dict[str, str] = {}
        self._post_queue: List[Any] = []
        self._get_queue: List[Any] = []

    # Métodos utilitários para os testes adicionarem respostas
    def queue_post(self, resp: Any) -> None:  # resp pode ser Response ou Exception
        self._post_queue.append(resp)

    def queue_get(self, resp: Any) -> None:
        self._get_queue.append(resp)

    # Métodos que simulam as requisições
    def post(self, url: str, json: Optional[Dict[str, Any]] = None, timeout: float | None = None) -> Response:
        resp = self._post_queue.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    def get(self, url: str, timeout: float | None = None) -> Response:
        resp = self._get_queue.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


fake_requests = types.ModuleType("requests")
fake_requests.Session = Session
fake_requests.Response = Response
fake_requests.exceptions = types.SimpleNamespace(
    RequestException=RequestException, Timeout=Timeout
)
sys.modules["requests"] = fake_requests
sys.modules["requests.exceptions"] = fake_requests.exceptions

from requests.exceptions import Timeout as ReqTimeout  # noqa: E402

Timeout = ReqTimeout

import os  # noqa: E402

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# Agora podemos importar o cliente que depende de ``requests``
from auth_3cplus import (  # noqa: E402  - import após injeção de módulo
    InvalidCredentials,
    ThreeCAuthClient,
    TokenExpired,
    Unauthorized,
)


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


def test_login_success_variations():
    for data in (
        {"token": "abc"},
        {"api_token": "abc"},
        {"data": {"api_token": "abc"}},
    ):
        session = Session()
        session.queue_post(Response(200, data))
        client = ThreeCAuthClient(base_url="http://test/api/v1", session=session)
        token = client.login("u", "p", 1, "d")
        assert token == "abc"
        assert client.is_autenticado


def test_login_invalid_credentials():
    session = Session()
    session.queue_post(Response(401, {}))
    client = ThreeCAuthClient(base_url="http://test/api/v1", session=session)
    with pytest.raises(InvalidCredentials):
        client.login("u", "p", 1, "d")


def test_verificar_sessao_token_expirado():
    session = Session()
    session.queue_post(Response(200, {"token": "abc"}))
    session.queue_get(Response(401, {}))
    client = ThreeCAuthClient(base_url="http://test/api/v1", session=session)
    client.login("u", "p", 1, "d")
    with pytest.raises(TokenExpired):
        client.verificar_sessao()


def test_logout_limpa_token():
    session = Session()
    session.queue_post(Response(200, {"token": "abc"}))
    session.queue_get(Response(200, {}))
    client = ThreeCAuthClient(base_url="http://test/api/v1", session=session)
    client.login("u", "p", 1, "d")
    client.logout()
    assert not client.is_autenticado
    with pytest.raises(Unauthorized):
        client.auth_headers()


@pytest.mark.xfail()
def test_retry_login():
    session = Session()
    session.queue_post(RequestException())
    session.queue_post(Response(502, {}))
    session.queue_post(Response(200, {"token": "abc"}))
    client = ThreeCAuthClient(base_url="http://test/api/v1", timeout=0.1, session=session)
    token = client.login("u", "p", 1, "d")
    assert token == "abc"


def test_auth_headers_sem_login():
    client = ThreeCAuthClient(base_url="http://test/api/v1", session=Session())
    with pytest.raises(Unauthorized):
        client.auth_headers()
