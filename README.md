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

## Exemplo de uso

```python
from auth_3cplus import ThreeCAuthClient

client = ThreeCAuthClient()
client.login()
dados = client.verificar_sessao()
print(dados.get("name"))
client.logout()
```

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
