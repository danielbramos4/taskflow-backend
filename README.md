# TaskFlow Backend

Fundação do backend TaskFlow em Django, Django REST Framework e PostgreSQL.

Repositório: [danielbramos4/taskflow-backend](https://github.com/danielbramos4/taskflow-backend).
A fundação e os critérios concluídos estão em [Sprint 1](docs/sprint-1.md).
O planejamento de organizações e permissões está em [Sprint 2](docs/sprint-2.md).

## Requisitos

- Windows com PowerShell e VS Code.
- Python 3.12 e Git.
- Docker Desktop em execução, com Docker Compose.
- Porta local `5434` disponível para o PostgreSQL.

## Instalação no Windows

No terminal, entre na raiz deste repositório, onde está `manage.py`.

Para uma instalação nova, crie o ambiente virtual apenas se ele não existir:

```powershell
if (-not (Test-Path .venv)) {
    python -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Os comandos usam diretamente o Python do ambiente virtual; não é preciso alterar
a política de execução do PowerShell nem ativar o ambiente.

Crie o `.env` somente se ele ainda não existir:

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
```

Edite o `.env` localmente antes de iniciar o projeto. Para um banco novo, defina
uma senha própria e uma chave Django própria. Para um banco existente, mantenha
a senha que já é aceita por ele. Os valores do `.env.example` são exemplos.
O `.env` é ignorado pelo Git; não compartilhe seu conteúdo.

As variáveis de ambiente do processo prevalecem sobre o `.env`, tanto no Django
quanto na interpolação do Compose. `$env:VAR` é uma configuração da sessão do
PowerShell; variáveis de Usuário/Sistema podem ser herdadas pelo VS Code.
O `.env` persiste em disco entre terminais.

Se uma variável temporária `POSTGRES_PASSWORD` estiver desatualizada, remova apenas
essa variável da sessão para voltar a usar o `.env`:

```powershell
Remove-Item Env:POSTGRES_PASSWORD -ErrorAction SilentlyContinue
```

Inicie o banco e aplique as migrações na instalação escolhida:

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

O Django executado no Windows usa `127.0.0.1:5434`; a porta do PostgreSQL dentro
do contêiner é `5432`. O volume `postgres_data` mantém os dados. Alterar
`POSTGRES_PASSWORD` no `.env` ou reiniciar o contêiner não altera a senha de um
banco já inicializado. Não remova volumes para resolver problemas de senha.

No VS Code, selecione `.venv/Scripts/python.exe` como interpretador Python.

## API disponível

| Método | Caminho | Comportamento |
| --- | --- | --- |
| POST | `/api/v1/auth/token/` | Recebe `username` e `password`; devolve access e refresh JWT. |
| POST | `/api/v1/auth/token/refresh/` | Recebe `refresh`; devolve um novo access JWT. |
| GET | `/api/v1/auth/me/` | Requer `Authorization: Bearer <access>` e devolve o próprio usuário. |
| GET | `/api/v1/organizations/` | Lista somente organizações do solicitante, com paginação. |
| POST | `/api/v1/organizations/` | Cria organização e vínculo de proprietário para o solicitante. |

A coleção de organizações está disponível na Entrega 1 da Sprint 2. Detalhes,
edição de organizações e administração de membros continuam nas próximas entregas.

## API de organizações — Entrega 1

As duas operações exigem `Authorization: Bearer <access>`. A identidade é obtida
do JWT; o cliente não escolhe outro usuário ou proprietário.

Para criar, envie JSON a `POST /api/v1/organizations/`:

```json
{
  "name": "Equipe Exemplo",
  "slug": "equipe-exemplo"
}
```

A resposta 201 contém `id`, `name`, `slug`, `my_role`, `created_at` e `updated_at`.
`my_role` será `owner`. A criação da organização e do vínculo é uma única
transação: uma falha no vínculo desfaz a organização.

`GET /api/v1/organizations/` retorna `count`, `next`, `previous` e `results`, com
20 organizações por página e ordenação por `name, id`. Use `?page=2` para a
próxima página. Um usuário pode aparecer como proprietário em uma organização e
como membro em outra; `my_role` é calculado para o usuário atual. Sem vínculos,
a resposta é 200 com `results: []`. Parâmetros como `user_id` não ampliam o acesso.

Erros previstos: 400 para campos inválidos, slug duplicado ou campos não aceitos;
401 para JWT ausente/inválido; 404 para página inexistente; 405 para métodos de
escrita não oferecidos na coleção. Somente `name` e `slug` são aceitos no POST;
campos como `id`, `owner`, `user_id` e `my_role` recebem 400. Falhas de integridade
não previstas na criação retornam 500 com mensagem genérica, sem detalhes do banco.

## Validação local

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pytest --reuse-db -v --tb=short
```

O Pytest usa o banco separado `test_<POSTGRES_DB>`. O usuário PostgreSQL precisa
poder criar bancos de teste. `--reuse-db` preserva esse banco ao final; os testes
não usam as tabelas do banco de desenvolvimento. Não configure o ambiente local
com um banco de produção.

Para conferir a conexão sem imprimir credenciais:

```powershell
.\.venv\Scripts\python.exe manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('PostgreSQL conectado com sucesso')"
```

## Qualidade e integração contínua

O Ruff verifica imports e erros comuns; o formatador padroniza o código. As
migrações históricas são verificadas pelo linter, mas preservadas pelo formatador.
Para aplicar correções locais de estilo:

```powershell
.\.venv\Scripts\python.exe -m ruff check --fix .
.\.venv\Scripts\python.exe -m ruff format .
```

O workflow `.github/workflows/ci.yml` executa Ruff, verificações Django, migrações
e Pytest em Python 3.12 e PostgreSQL 17. Ele usa um banco temporário e valores
fictícios próprios; não precisa de `.env` nem de segredos do desenvolvimento.
O workflow executa em pushes, pull requests e acionamento manual. A execução
remota da Sprint 1 foi aprovada; a evidência está registrada em
[Sprint 1](docs/sprint-1.md).

Referências: [configuração do Ruff](https://docs.astral.sh/ruff/configuration/) e
[PostgreSQL no GitHub Actions](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).
