# Cliente de Autenticação 3C Plus

Este repositório contém um cliente simples em Python para autenticação na
API **3C Plus**. O módulo `auth_3cplus.py` pode ser reutilizado em outros
projetos para obter e gerenciar o token de acesso.

## Instalação

```bash
pip install -r requirements.txt
```

## Variáveis de ambiente

| Variável                | Descrição                                  |
|------------------------|----------------------------------------------|
| `THREEC_USER`          | E-mail do usuário                            |
| `THREEC_PASSWORD`      | Senha                                       |
| `THREEC_COMPANY_ID`    | ID da empresa                                |
| `THREEC_COMPANY_DOMAIN`| Domínio da empresa                           |
| `THREEC_BASE_URL`      | (opcional) URL base da API                   |

As variáveis podem ser definidas em um arquivo `.env` na raiz do projeto e
serão carregadas automaticamente pelo cliente.

## Exemplo de uso

```python
from dotenv import load_dotenv
from auth_3cplus import ThreeCAuthClient

load_dotenv()
client = ThreeCAuthClient()
client.login()
dados = client.verificar_sessao()
print(dados.get("name"))
client.logout()
```

## Mailing e campanhas de discagem

O módulo `mailing_3cplus.py` permite criar containers de mailing, enviar
contatos e ajustar o peso de campanhas.

```python
from auth_3cplus import ThreeCAuthClient
from mailing_3cplus import ThreeCMailingClient, Contact

auth = ThreeCAuthClient()
auth.login()

mailing = ThreeCMailingClient(auth)
campanhas = mailing.listar_campanhas()
container = mailing.criar_mailing_container("Meu mailing", campanhas[0]["id"])

contatos = [
    Contact(name="João", phones=["5511999999999"], external_id="1").to_dict(),
]
mailing.enviar_mailing_json(container["mailing_id"], contatos)
mailing.ajustar_peso_mailing(container["mailing_id"], 100)
```

Os endpoints utilizados podem variar entre ambientes. Utilize o parâmetro
`endpoints` do cliente para sobrescrever ou acrescentar caminhos.

## Tabela de erros

| Exceção              | Cenário                                                         |
|----------------------|-----------------------------------------------------------------|
| `InvalidCredentials` | Usuário ou senha incorretos                                     |
| `TokenExpired`       | Token expirado ao chamar `verificar_sessao` ou `logout`         |
| `Unauthorized`       | Métodos chamados sem autenticação                               |
| `RateLimitExceeded`  | Limite de requisições atingido                                  |
| `ApiUnavailable`     | Erros 5xx ou timeouts                                           |

## Observações de segurança

- O token de acesso é mantido apenas em memória e **não é persistido em disco**.
- Senhas e tokens **não** são registrados nos logs.
