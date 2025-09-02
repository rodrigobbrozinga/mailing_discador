"""Exemplo básico de uso do cliente de autenticação 3C Plus."""

from auth_3cplus import ThreeCAuthClient


def main() -> None:
    client = ThreeCAuthClient()
    client.login()
    dados = client.verificar_sessao()
    print(f"Logado como: {dados.get('name')} ({dados.get('email')})")
    client.logout()


if __name__ == "__main__":
    main()
