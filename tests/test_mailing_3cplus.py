"""Testes para o cliente de mailing 3C Plus."""

from __future__ import annotations

# mypy: ignore-errors

import os
import sys
import pytest
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class Response:
    def __init__(self, status_code: int = 200, json_data: Optional[Dict[str, Any]] = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> Dict[str, Any]:
        return self._json


class Session:
    """Sessão fake com filas por método."""

    def __init__(self) -> None:
        self.headers: Dict[str, str] = {}
        self._queues: Dict[str, List[Any]] = {"GET": [], "POST": [], "PUT": []}

    def queue_get(self, resp: Any) -> None:
        self._queues["GET"].append(resp)

    def queue_post(self, resp: Any) -> None:
        self._queues["POST"].append(resp)

    def queue_put(self, resp: Any) -> None:
        self._queues["PUT"].append(resp)

    def get(self, url: str, timeout: float | None = None) -> Response:
        resp = self._queues["GET"].pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    def post(self, url: str, json: Any | None = None, timeout: float | None = None) -> Response:
        resp = self._queues["POST"].pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    def put(self, url: str, json: Any | None = None, timeout: float | None = None) -> Response:
        resp = self._queues["PUT"].pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    def request(
        self,
        method: str,
        url: str,
        json: Any | None = None,
        params: Any | None = None,
        data: Any | None = None,
        files: Any | None = None,
        headers: Any | None = None,
        timeout: float | None = None,
    ) -> Response:
        method = method.upper()
        if method == "GET":
            return self.get(url, timeout=timeout)
        if method == "POST":
            return self.post(url, json=json, timeout=timeout)
        if method == "PUT":
            return self.put(url, json=json, timeout=timeout)
        raise NotImplementedError


from auth_3cplus import ThreeCAuthClient  # noqa: E402
from mailing_3cplus import (  # noqa: E402
    CampaignNotFound,
    CreateMailingFailed,
    ThreeCMailingClient,
    Unauthorized,
    UploadFailed,
)


def build_client(session: Session) -> ThreeCMailingClient:
    auth = ThreeCAuthClient(base_url="http://test/api/v1", session=session)
    auth._token = "t"  # type: ignore[attr-defined]
    session.headers["Authorization"] = "Bearer t"
    return ThreeCMailingClient(auth, session=session)


def test_listar_campanhas_fallback_e_filtro():
    session = Session()
    session.queue_get(Response(404))
    session.queue_get(
        Response(200, {"data": [{"id": 1, "name": "Camp1", "active": True}, {"id": 2, "name": "Desativada", "active": False}]})
    )
    client = build_client(session)
    campanhas = client.listar_campanhas(filtro="Camp")
    assert len(campanhas) == 1
    assert campanhas[0]["id"] == 1


def test_listar_campanhas_unauthorized():
    session = Session()
    session.queue_get(Response(401))
    client = build_client(session)
    with pytest.raises(Unauthorized):
        client.listar_campanhas()


def test_criar_container_sucesso_variacoes_e_conflito():
    session = Session()
    session.queue_post(Response(201, {"data": {"id": 99}}))
    client = build_client(session)
    res = client.criar_mailing_container("teste", 1)
    assert res["mailing_id"] == 99
    assert 99 in client.mailing_ids

    session.queue_post(Response(409))
    with pytest.raises(CreateMailingFailed):
        client.criar_mailing_container("x", 1)

    session.queue_post(Response(201, {"mailing_id": 77}))
    res2 = client.criar_mailing_container("y", 1)
    assert res2["mailing_id"] == 77


def test_enviar_mailing_json_parcial():
    session = Session()
    session.queue_post(Response(200, {"success": [{"external_id": "1"}], "failed": [{"external_id": "2"}] }))
    client = build_client(session)
    contatos = [
        {"name": "A", "phones": ["1"], "external_id": "1"},
        {"name": "B", "phones": ["2"], "external_id": "2"},
    ]
    data = client.enviar_mailing_json(5, contatos)
    assert len(data.get("failed", [])) == 1


def test_ajustar_peso_sucesso_e_erro():
    session = Session()
    session.queue_put(Response(200, {"success": True}))
    client = build_client(session)
    client.ajustar_peso_mailing(1, 0)

    session.queue_put(Response(404))
    with pytest.raises(CampaignNotFound):
        client.ajustar_peso_mailing(1, 10)


def test_enviar_csv_arquivo_inexistente(tmp_path):
    session = Session()
    client = build_client(session)
    csv_path = tmp_path / "arquivo.csv"
    with pytest.raises(UploadFailed):
        client.enviar_mailing_csv(1, str(csv_path))
