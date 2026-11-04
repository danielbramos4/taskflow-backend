# TaskFlow: entrega do backend

O backend entrega autenticação JWT, organizações e membros, projetos e tarefas.
Proprietários criam e editam tarefas, atribuem responsáveis da organização,
definem prazos e mudam o estado. Participantes consultam somente os projetos a
que têm acesso. O [README](../README.md) lista todas as rotas e os contratos.

## Preparar e executar

Na raiz de um checkout limpo, com Python 3.12 e Docker Desktop em execução, siga
a [configuração do ambiente](../README.md#instalação-no-windows) para criar o ambiente
virtual, instalar as dependências e preencher seu `.env` local a partir do
`.env.example`. Em uma instalação existente, mantenha o `.env` e o volume de
dados. No PowerShell:

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

A API estará em `http://127.0.0.1:8000/api/v1/`. Para uma instalação vazia,
`manage.py createsuperuser` cria a primeira conta de desenvolvimento. Use essa
conta no `/admin/` para cadastrar outras contas que participarão da demonstração.

## Demonstrar a API

1. Obtenha um token com `POST /api/v1/auth/token/`, enviando `username` e
   `password`. Nas demais requisições, use `Authorization: Bearer <access>`.
2. Crie uma organização com `POST /api/v1/organizations/` e um projeto com
   `POST /api/v1/organizations/{org}/projects/`. Cada rota devolve seu `id`.
3. Adicione uma conta ativa com `POST /api/v1/organizations/{org}/memberships/`
   e o corpo `{"user_id": 42}`, substituindo `42` pelo ID da conta. Guarde o
   `id` do vínculo retornado para atribuir a tarefa.
4. Crie a tarefa em `POST /api/v1/organizations/{org}/projects/{projeto}/tasks/`:

   ```json
   {"title": "Revisar entrega", "assignee_membership_id": 7, "due_date": "2026-11-12"}
   ```

   Substitua `7` pelo ID real do vínculo. A tarefa começa em `todo`. Os estados
   aceitos na edição são `todo`, `in_progress` e `done`.
5. Liste as tarefas com `?assignee_membership_id=7&due_to=2026-11-12`. Os
   limites incluem a data indicada. Use `unassigned` no filtro para tarefas sem
   responsável. A resposta é paginada (`count`, `next`, `previous`, `results`).
6. Envie `PATCH` ao detalhe da tarefa (`.../tasks/{tarefa}/`) com
   `{"status":"done"}` para concluir. Para limpar o prazo, envie
   `{"due_date":null}`. Campos omitidos preservam seus valores.

Um membro comum pode consultar, mas recebe `403` ao editar. Quem não participa
da organização recebe `404` ao acessar seus recursos. Ao remover o vínculo do
responsável, a tarefa é preservada, com o prazo e o estado intactos; a atribuição
é limpa. Reingressar na equipe não restaura a atribuição automaticamente.

## Reproduzir a validação

Em um checkout limpo, com o PostgreSQL disponível:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pytest
```

O GitHub Actions executa as verificações, aplica todas as migrações em um
PostgreSQL 17 descartável e roda a suíte completa. O teste
`tests/tasks/test_deadline_filters.py` cobre o fluxo com login real, atribuição,
prazo, filtros, conclusão, remoção do vínculo e reingresso.

O escopo desta entrega é a API documentada e testada, executável localmente.
