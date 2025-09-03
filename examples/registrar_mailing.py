"""Exemplo de registro de mailing na 3C Plus."""

from __future__ import annotations

from dotenv import load_dotenv
from auth_3cplus import ThreeCAuthClient
from mailing_3cplus import Contact, ThreeCMailingClient


def main() -> None:
    load_dotenv()
    auth = ThreeCAuthClient()
    auth.login()

    mailing = ThreeCMailingClient(auth)

    campanhas = mailing.listar_campanhas()
    if not campanhas:
        print("Nenhuma campanha encontrada")
        return

    campanha = campanhas[0]
    print("Usando campanha:", campanha.get("name"))

    container = mailing.criar_mailing_container("Meu Mailing", campanha["id"])
    mailing_id = container["mailing_id"]

    contatos = [
        Contact(name="João", phones=["5511999999999"], external_id="1").to_dict(),
        Contact(name="Maria", phones=["5511888888888"], external_id="2").to_dict(),
    ]
    mailing.enviar_mailing_json(mailing_id, contatos)

    mailing.ajustar_peso_mailing(mailing_id, 100)

    print("Mailing criado:", container)


if __name__ == "__main__":  # pragma: no cover - exemplo manual
    main()
