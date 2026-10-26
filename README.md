# TaskFlow Backend

Fundação do backend TaskFlow em Django, Django REST Framework e PostgreSQL.

Repositório: [danielbramos4/taskflow-backend](https://github.com/danielbramos4/taskflow-backend).
A fundação e os critérios concluídos estão em [Sprint 1](docs/sprint-1.md).
Organizações e permissões foram concluídas na [Sprint 2](docs/sprint-2.md),
com as quatro entregas e seus critérios de aceite validados.
O planejamento e o andamento de projetos por organização estão na
[Sprint 3](docs/sprint-3.md).

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
| GET | `/api/v1/organizations/{organization_id}/` | Consulta uma organização da qual o solicitante participa. |
| PATCH | `/api/v1/organizations/{organization_id}/` | Proprietário altera nome e/ou slug da organização. |
| GET | `/api/v1/organizations/{organization_id}/memberships/` | Participantes consultam membros e papéis, com paginação. |
| POST | `/api/v1/organizations/{organization_id}/memberships/` | Proprietário adiciona uma conta ativa existente. |
| PATCH | `/api/v1/organizations/{organization_id}/memberships/{membership_id}/` | Proprietário altera o papel de um membro. |
| DELETE | `/api/v1/organizations/{organization_id}/memberships/{membership_id}/` | Proprietário remove um vínculo, preservando a conta. |
| GET | `/api/v1/organizations/{organization_id}/projects/` | Participantes listam projetos da organização, com paginação. |
| POST | `/api/v1/organizations/{organization_id}/projects/` | Proprietário cria projeto, com organização e autoria definidas no servidor. |
| GET | `/api/v1/organizations/{organization_id}/projects/{project_id}/` | Participantes consultam um projeto dentro da organização autorizada. |
| PATCH | `/api/v1/organizations/{organization_id}/projects/{project_id}/` | Proprietário edita nome/descrição e arquiva ou restaura o projeto. |

As quatro entregas da Sprint 2 estão concluídas: organizações, administração
de membros, validação do fluxo completo e fechamento dos critérios de aceite.
As Entregas 1 a 3 da Sprint 3 oferecem criação, listagem, consulta, edição,
arquivamento e restauração de projetos. O aceite completo fica para a Entrega 4.

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

## Consulta e edição de organizações — Entrega 2

`GET /api/v1/organizations/{organization_id}/` exige JWT e participação na
organização. Proprietários e membros recebem 200 com os mesmos campos da
criação, incluindo seu próprio `my_role`.

Somente proprietários podem usar `PATCH` nesse caminho. Envie apenas os campos
que deseja alterar, por exemplo:

```json
{
  "name": "Novo nome da equipe"
}
```

A resposta 200 contém a organização atualizada; omitir `slug` preserva seu valor.
Um objeto vazio (`{}`) retorna 200 sem alterar os dados. Campos inesperados ou
controlados pelo servidor, nome/slug inválidos e slug duplicado recebem 400,
sem salvar alterações parciais. Falhas de integridade não previstas retornam
500 com mensagem genérica.

Membros recebem 403 ao editar. Usuários sem vínculo recebem 404 na consulta e
na edição, assim como para um ID inexistente, inclusive se forem superusuários.
Sem JWT válido, a resposta é 401. POST, PUT e DELETE nesse caminho recebem 405.
Ser proprietário de uma organização não dá permissão de edição em outra.

O vínculo e o papel são consultados a cada requisição: mudanças de papel e
remoção de vínculo passam a valer com o mesmo JWT na próxima requisição.
Parâmetros como `user_id`, `my_role` ou `organization_id` não trocam a identidade
nem o recurso indicado no caminho. A API desta entrega não altera vínculos.

## Administração de membros — Entrega 3

Todas as operações exigem JWT. Proprietários e membros podem consultar
`GET /api/v1/organizations/{organization_id}/memberships/`. A resposta é paginada
com `count`, `next`, `previous` e `results`, 20 vínculos por página e ordenação
por `created_at, id`. Cada vínculo contém somente `id`, `user_id`, `username`,
`role` e `created_at`; não inclui e-mail, senha ou tokens.

Somente proprietários administram os vínculos da organização correspondente.
Para adicionar uma conta ativa já existente, envie a
`POST /api/v1/organizations/{organization_id}/memberships/`:

```json
{
  "user_id": 42,
  "role": "member"
}
```

Substitua `42` pelo ID da conta escolhida. `role` aceita `member` e `owner`;
se omitido, o papel será `member`. A resposta 201 contém o vínculo criado.
Usuário inexistente/inativo ou vínculo já existente recebe 400. Incluir um
vínculo duplicado não altera seu papel e não cria outra conta.

Para promover um membro ou rebaixar um proprietário, envie somente o papel a
`PATCH /api/v1/organizations/{organization_id}/memberships/{membership_id}/`:

```json
{
  "role": "owner"
}
```

A resposta 200 contém o vínculo atualizado. Um objeto vazio mantém o papel.
`user_id`, `organization_id`, `id`, `username`, datas e campos inesperados não
podem ser alterados e recebem 400. O ID do vínculo deve pertencer à organização
do caminho; trocar apenas o ID da organização não concede acesso ao vínculo.

`DELETE` no mesmo caminho retorna 204 sem conteúdo e remove somente o vínculo.
A conta, a organização e os vínculos em outras equipes permanecem. A remoção
de acesso vale na próxima requisição, mesmo com o JWT anterior ainda válido.
Membros não têm uma operação separada para sair por conta própria nesta sprint.

Rebaixar ou remover o último proprietário ativo recebe 400. Primeiro promova
outro usuário ativo a `owner`; depois o proprietário anterior pode ser rebaixado
ou removido. Um proprietário inativo não conta como substituto. As operações de
escrita usam uma transação e o bloqueio da mesma organização no PostgreSQL,
com nova verificação de acesso após a espera. Alterações simultâneas pela API
preservam pelo menos um proprietário ativo. Mudanças administrativas nas contas
fora desta API, como desativar um proprietário, exigem uma regra própria futura.

Sem JWT válido: 401. Participante sem papel de proprietário ao escrever: 403.
Usuário sem vínculo, organização inexistente ou vínculo fora da organização: 404.
Campos inválidos, papel inválido, duplicidade e último proprietário ativo: 400.
Falhas de integridade inesperadas: 500 com mensagem genérica. Na coleção, PUT,
PATCH e DELETE recebem 405; no caminho individual, GET, POST e PUT recebem 405.
Não há exceção para superusuários sem vínculo nem ampliação de acesso por
parâmetros de consulta como `user_id` ou `organization_id`.

## Fluxo completo de aceite — Entrega 4

Para reproduzir manualmente, use três contas ativas de desenvolvimento já
existentes: A (criador), B (colega) e C (usuário externo). Obtenha access e refresh
de cada conta com `POST /api/v1/auth/token/`, usando suas credenciais localmente.
Use `Authorization: Bearer <access>` da conta indicada em cada passo; não
compartilhe os tokens. Consulte `GET /api/v1/auth/me/` de B para obter seu ID.

Escolha um slug ainda não utilizado. Os nomes entre chaves abaixo são os IDs
devolvidos pela API, não valores fixos a copiar.

| Passo | Conta e requisição | Resultado esperado |
| --- | --- | --- |
| 1 | A: `POST /api/v1/organizations/` com `{"name":"Equipe demo","slug":"equipe-demo"}` | 201; guardar `id` como `{org}`; `my_role` é `owner`. |
| 2 | A: `GET /api/v1/organizations/{org}/memberships/` | 200; guardar o `id` do vínculo de A como `{vinculo-a}`. |
| 3 | C: `GET /api/v1/organizations/{org}/` | 404; a organização não aparece na listagem de C. |
| 4 | A: `POST /api/v1/organizations/{org}/memberships/` com `{"user_id":<id-de-B>}` | 201; guardar `id` como `{vinculo-b}`; `role` é `member`. |
| 5 | B: `GET /api/v1/organizations/{org}/` e `GET /api/v1/organizations/{org}/memberships/` | 200; B é `member` e a equipe tem dois vínculos. |
| 6 | B: `PATCH /api/v1/organizations/{org}/` com `{"name":"Tentativa"}` | 403; o nome permanece igual. |
| 7 | A: `PATCH /api/v1/organizations/{org}/` com `{"name":"Equipe atualizada"}` | 200; B consulta o nome atualizado. |
| 8 | A: `PATCH /api/v1/organizations/{org}/memberships/{vinculo-b}/` com `{"role":"owner"}` | 200; com o mesmo JWT, B passa a consultar `my_role: owner` e pode editar a organização. |
| 9 | A: `PATCH /api/v1/organizations/{org}/memberships/{vinculo-a}/` com `{"role":"member"}` | 200; B é o proprietário ativo. A agora recebe 403 ao editar a organização. |
| 10 | B: `DELETE /api/v1/organizations/{org}/memberships/{vinculo-b}/` | 400; a tentativa de remover o último proprietário é rejeitada. |
| 11 | B: `DELETE /api/v1/organizations/{org}/memberships/{vinculo-a}/` | 204; apenas o vínculo de A é removido. |
| 12 | A: consultar novamente a organização e os membros com o mesmo JWT | 404; a listagem de organizações deixa de incluir a equipe. |
| 13 | A: `POST /api/v1/auth/token/refresh/` com `{"refresh":"<refresh-de-A>"}` e depois `GET /api/v1/auth/me/` com o novo access | 200 em ambos; a conta continua existente e não recupera acesso à organização removida. |

A listagem de membros usa `count`, `next`, `previous` e `results`. Os IDs dos
vínculos são diferentes dos IDs de usuários. As regras de paginação, demais
campos das respostas e erros 400/401/403/404/405 estão descritos nas seções acima.

O teste automatizado reproduz esse fluxo com login JWT real, dados fictícios e
o banco separado de testes; também verifica que dados de outra organização
permanecem intactos. Para executá-lo em um novo PowerShell na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/organizations/test_sprint2_flow.py --reuse-db -v --tb=short
```

## Projetos por organização — Sprint 3, Entrega 1

As operações exigem JWT e vínculo com a organização do caminho. Proprietários
podem criar; proprietários e membros podem consultar a coleção. A autoria é
um registro histórico e não substitui o vínculo ou o papel para conceder acesso.

Para criar, envie JSON a
`POST /api/v1/organizations/{organization_id}/projects/`:

```json
{
  "name": "Portal interno",
  "description": "Organizar a primeira versão do portal da equipe."
}
```

A resposta 201 contém `id`, `organization_id`, `name`, `description`,
`is_archived`, `created_by_id`, `created_at` e `updated_at`. Organização vem do
caminho, autor vem do JWT e `is_archived` começa como false. O cliente só pode
enviar `name` e `description`. Nome é obrigatório, tem até 150 caracteres e
não pode ficar vazio após retirar espaços nas extremidades. Descrição é
opcional, tem até 5.000 caracteres, padrão vazio e não aceita null. Nomes podem
se repetir; cada projeto possui seu próprio ID.

`GET` no mesmo caminho retorna `count`, `next`, `previous` e `results`, com
20 projetos por página e ordenação por `name, id`. Use `?page=2` para a próxima
página. Organização sem projetos retorna 200 com `results: []`. Parâmetros como
`organization_id`, `created_by_id` e `user_id` não alteram o escopo ou a identidade.

Erros: JWT ausente/inválido recebe 401; membro tentando criar recebe 403;
organização inexistente ou sem vínculo recebe 404, inclusive para superusuários.
Dados inválidos, limites excedidos, corpo que não é objeto JSON e campos
controlados pelo servidor recebem 400, sem criar projeto. PUT, PATCH e DELETE
na coleção recebem 405. Falhas de integridade inesperadas recebem 500 com
mensagem genérica, inclusive quando a validação do banco falha no encerramento
da transação. Escritas bloqueiam a organização e conferem novamente o
papel após a espera; revogações de acesso passam a valer com o mesmo JWT.

A migração `projects.0001_initial` cria somente a tabela nova e seus vínculos e
índices. Não altera as tabelas existentes. Para atualizar outra instalação em
um novo PowerShell na raiz do repositório, após revisar/aplicar o código:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate projects
.\.venv\Scripts\python.exe -m pytest tests/projects --reuse-db -v --tb=short
```

Projetos não podem ser transferidos ou excluídos pela API desta entrega.
O modelo protege a exclusão da organização com projetos e preserva o projeto
com autoria nula se a conta criadora for excluída administrativamente. A remoção
de um vínculo da equipe não remove seus projetos. O arquivamento da Entrega 3
preserva os registros e mantém os projetos visíveis aos participantes, sem expor
dados privados da conta.

## Consulta e edição de projetos — Sprint 3, Entrega 2

`GET /api/v1/organizations/{organization_id}/projects/{project_id}/` exige JWT
e participação na organização do caminho. Proprietários e membros recebem 200
com os mesmos oito campos da criação. Autoria nula e projetos já arquivados
também são consultáveis. O projeto deve pertencer à organização indicada;
ser proprietário de ambas as organizações não permite trocar apenas o pai na URL.

Somente proprietários podem enviar `PATCH` ao mesmo caminho. Exemplo:

```json
{
  "description": "Descrição revisada do projeto."
}
```

A resposta 200 contém o projeto atualizado. Campos omitidos mantêm seu valor;
descrição vazia (`""`) limpa o texto. Um objeto vazio (`{}`) retorna 200 sem
alterar os dados nem `updated_at`. Os limites de nome e descrição são os mesmos
da criação. Nome vazio, valores null, limites excedidos e corpo que não é objeto
JSON recebem 400 sem salvar alterações. Organização, autoria, ID, datas
e campos inesperados não são alteráveis e recebem 400. A Entrega 3 acrescenta
o sinalizador `is_archived` ao PATCH, conforme a seção seguinte.

Membros recebem 403 ao editar. Usuários sem vínculo recebem 404 tanto para
projetos existentes como inexistentes, inclusive superusuários. Quem possui
vínculo recebe 404 ao informar projeto inexistente ou de outra organização.
JWT ausente/inválido recebe 401. PUT, POST e DELETE no caminho individual recebem
405. Falhas de integridade, inclusive no commit, retornam 500 com mensagem genérica
e desfazem a edição.

Ser criador do projeto não dá acesso sem vínculo nem permissão sem papel de
proprietário. Mudanças de papel, promoção e remoção de vínculo passam a valer
com o mesmo JWT. A escrita bloqueia a organização e consulta novamente o papel
após a espera; a consulta do projeto fica limitada a essa organização. Parâmetros
como `project_id`, `organization_id` ou `user_id` não mudam o alvo nem a identidade.
Proprietários podem editar nome/descrição de projetos já arquivados sem alterar
o sinalizador. Arquivamento e restauração estão descritos na Entrega 3 abaixo.

Esta entrega não muda modelos ou migrações. Para validar em novo PowerShell
na raiz do repositório:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/projects --reuse-db -v --tb=short
```

## Arquivamento e restauração — Sprint 3, Entrega 3

Proprietários arquivam e restauram projetos no mesmo caminho de edição:
`PATCH /api/v1/organizations/{organization_id}/projects/{project_id}/`.

Para arquivar:

```json
{
  "is_archived": true
}
```

Para restaurar:

```json
{
  "is_archived": false
}
```

A resposta 200 contém o projeto com o sinalizador atualizado. São aceitos
somente os booleanos JSON `true` e `false`; strings como `"true"`, números como
`1`/`0`, null, listas e objetos recebem 400, sem salvar alterações. O sinalizador
é opcional no PATCH: se omitido, mantém seu valor. Repetir o mesmo valor retorna
200 sem duplicar nem remover registros. O POST continua aceitando somente nome
e descrição, criando projeto ativo; enviar `is_archived`, mesmo false, recebe 400.

Arquivar preserva nome, descrição, autoria, organização e vínculos da equipe.
Projetos arquivados continuam na listagem paginada e podem ser consultados por
participantes e editados por proprietários. O arquivamento organiza o trabalho
e pode ser revertido; ele não revoga acesso. DELETE continua recebendo 405.

É possível combinar nome, descrição e `is_archived` no mesmo PATCH. Todos os
campos são validados antes de salvar: um campo inválido ou proibido desfaz toda
a alteração. Atualizações usam a mesma transação e verificação de acesso da
edição, inclusive após a espera pelo bloqueio. Falhas de integridade também
desfazem a alteração e retornam mensagem genérica.

JWT inválido/ausente recebe 401; membro tentando arquivar/restaurar recebe 403;
usuário sem vínculo ou projeto fora da organização do caminho recebe 404.
Autoria e superusuário sem vínculo não concedem privilégios. Promoção,
rebaixamento e remoção de vínculo passam a valer com o mesmo JWT.

O sinalizador já existe no modelo; esta entrega não requer migração. Para
validar em um novo PowerShell na raiz do repositório:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/projects/test_archive_api.py tests/projects/test_concurrency.py --reuse-db -v --tb=short
```

## Validação local

Abra um novo terminal PowerShell na raiz do repositório, onde está `manage.py`.

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
