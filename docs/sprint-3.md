# Sprint 3 — projetos por organização

## Objetivo e formato

Permitir que equipes organizem seu trabalho em projetos vinculados a uma
organização, preservando o isolamento e os papéis entregues na Sprint 2.
Prioridade escolhida pelo usuário: projetos por organização. Execução por
entregas, sem prazo fixo. A Entrega 1 foi integrada à `main` pelo
[PR #6](https://github.com/danielbramos4/taskflow-backend/pull/6), com CI aprovado.
A Entrega 2 foi integrada à `main` pelo
[PR #7](https://github.com/danielbramos4/taskflow-backend/pull/7), com CI aprovado.
A Entrega 3 foi integrada à `main` pelo
[PR #8](https://github.com/danielbramos4/taskflow-backend/pull/8), com CI aprovado.
As quatro entregas e os critérios de aceite foram concluídos em 26/10/2026.
O encerramento acrescenta o teste do fluxo completo e a documentação de aceite.

## Base disponível

- Sprints 1 e 2 integradas à `main`, com 195 testes aprovados no PostgreSQL.
- JWT, perfil, organizações e gestão de membros disponíveis.
- Papéis `owner` e `member` consultados por organização a cada requisição.
- Alterações de membros serializadas pelo bloqueio da organização.
- Ruff, verificações Django, Pytest e GitHub Actions configurados.

## Modelo e regras de domínio

Novo modelo `Project`, no app `apps.projects`, com:

| Campo | Regra |
| --- | --- |
| `id` | Inteiro gerado pelo servidor; usado no caminho da API. |
| `organization` | Organização indicada no caminho; vínculo imutável pela API. |
| `name` | Obrigatório, até 150 caracteres, sem nome vazio após retirar espaços nas extremidades. |
| `description` | Texto opcional, até 5.000 caracteres; padrão vazio; não aceita null. |
| `is_archived` | Booleano com padrão false; controlado pelo servidor na criação. |
| `created_by` | Usuário do JWT na criação; autoria não concede permissão independente do vínculo. |
| `created_at`, `updated_at` | Datas controladas pelo servidor. |

Projetos diferentes podem ter o mesmo nome; a identificação usa o ID, não o nome.
Não haverá associação de membros por projeto: todos os participantes da
organização podem consultar seus projetos. A organização não pode ser trocada
por campos enviados pelo cliente. A remoção de vínculo não remove projetos.

A exclusão administrativa de uma organização com projetos é protegida pelo
modelo (`PROTECT`). A exclusão administrativa de uma conta preserva o projeto e
torna a autoria nula (`SET_NULL`). Esta sprint não oferece essas exclusões pela
API. O arquivamento preserva os registros e pode ser revertido por proprietário.

## Regras de acesso

| Operação | Proprietário da organização | Membro da organização | Usuário externo |
| --- | --- | --- | --- |
| Listar e consultar projetos | Permitido | Permitido | 404 |
| Criar projeto | Permitido | 403 | 404 |
| Editar nome/descrição | Permitido | 403 | 404 |
| Arquivar e restaurar | Permitido | 403 | 404 |

Sem JWT válido: 401. Não há exceção para superusuários sem vínculo. Proprietário
de A e membro de B só pode administrar projetos de A. Criador que perde vínculo
perde o acesso na próxima requisição, mesmo usando o mesmo JWT. Nas escritas,
bloquear a organização em transação antes de consultar novamente o vínculo e o
papel, compatível com a revogação concorrente da Sprint 2.

## Contrato da API

| Entrega | Método e caminho | Resultado |
| --- | --- | --- |
| 1 | `GET /api/v1/organizations/{organization_id}/projects/` | 200; coleção paginada da organização autorizada. |
| 1 | `POST /api/v1/organizations/{organization_id}/projects/` | 201; proprietário informa nome e descrição opcional. |
| 2 | `GET /api/v1/organizations/{organization_id}/projects/{project_id}/` | 200; projeto dentro da organização autorizada. |
| 2 | `PATCH /api/v1/organizations/{organization_id}/projects/{project_id}/` | 200; proprietário altera nome e/ou descrição. |
| 3 | Mesmo `PATCH`, com `is_archived` | 200; proprietário arquiva/restaura sem excluir. |

Resposta de projeto: `id`, `organization_id`, `name`, `description`,
`is_archived`, `created_by_id`, `created_at` e `updated_at`. A autoria pode ser
nula após exclusão administrativa da conta; respostas não expõem e-mail,
senha ou tokens de outros usuários.

Coleção com 20 registros por página, `count`, `next`, `previous` e `results`,
ordenada por `name, id`. Arquivados continuam visíveis aos participantes e podem
ser editados por proprietários; arquivamento é uma marca de organização, não
uma exclusão ou bloqueio de edição. Não há filtros ou parâmetros que ampliem
acesso a outras organizações.

POST aceita somente `name` e `description`. PATCH aceita esses campos e,
com a Entrega 3, `is_archived`, restrito aos booleanos JSON true/false; strings,
números e null são rejeitados. Campos de identidade,
organização, autoria, datas e campos inesperados recebem 400. Corpo que não é
objeto JSON, dados inválidos e limites excedidos recebem 400. Métodos não
oferecidos recebem 405; não há DELETE nem PUT. IDs inexistentes e recursos fora
da organização autorizada recebem 404. Falhas de integridade inesperadas recebem
500 com mensagem genérica, sem SQL ou configuração do banco.

## Entrega 1 — modelo, criação e listagem

**Resultado:** proprietário cria projetos e os participantes os encontram somente
na organização da qual participam.

- [x] Criar modelo Project e migração inicial aditiva, preservando modelos anteriores.
- [x] Registrar o app e a coleção aninhada na organização.
- [x] Reutilizar a verificação de participação/papel da organização.
- [x] Fixar organização e criador no servidor e impedir arquivamento no POST.
- [x] Validar campos, paginação e ordenação estável.
- [x] Testar proprietário, membro, usuário externo e JWT ausente/inválido.
- [x] Testar isolamento e revogação de autorização enquanto uma escrita aguarda bloqueio.
- [x] Validar a migração e a suíte anterior com PostgreSQL, Ruff e CI.

**Aceite:** POST de proprietário retorna 201 com autoria do JWT e projeto ativo;
membro lê a coleção mas recebe 403 ao criar; externo recebe 404. Criação inválida
ou não autorizada não deixa projeto persistido. A coleção não mistura equipes.

## Entrega 2 — consultar e editar projetos

**Resultado:** participantes consultam o projeto e apenas proprietários editam
nome e descrição, sem transferi-lo para outra organização ou autor.

- [x] Implementar GET e PATCH de detalhes com busca limitada à organização.
- [x] Preservar campos omitidos no PATCH e validar limites/valores.
- [x] Proibir alteração de organização, autor, datas, ID e arquivamento nesta entrega.
- [x] Testar tentativa de acessar projeto de B pelo caminho de A e IDs inexistentes.
- [x] Testar papéis distintos da mesma pessoa em organizações diferentes.
- [x] Testar autoria sem vínculo e alteração/revogação de papel com o mesmo JWT.
- [x] Documentar requests, respostas e erros e conferir o CI do PR.

**Aceite:** membro consulta com 200 e edita com 403; externo recebe 404;
campos inválidos ou tentativa de transferir o projeto não modificam dados.

## Entrega 3 — arquivar e restaurar sem apagar

**Resultado:** proprietários sinalizam projetos arquivados e podem restaurá-los.

- [x] Acrescentar `is_archived` booleano ao PATCH, mantendo POST ativo por padrão.
- [x] Garantir que arquivados continuam consultáveis e editáveis com as mesmas permissões.
- [x] Rejeitar valores de arquivamento inválidos e campos não permitidos.
- [x] Testar arquivar/restaurar, membro sem escrita e isolamento entre organizações.
- [x] Garantir que nenhum arquivamento exclui projeto, organização, conta ou vínculo.
- [x] Documentar o comportamento e conferir o CI do PR.

**Aceite:** proprietário alterna o sinalizador com 200, sem perder dados nem
alterar vínculos. Membro recebe 403; externo recebe 404; DELETE continua 405.

## Entrega 4 — validar o fluxo e encerrar a sprint

- [x] Documentar um fluxo completo com organização, projeto, membro e arquivamento.
- [x] Validar login/refresh, gestão de organizações/membros e os 195 testes da base.
- [x] Validar papéis, isolamento, revogação e persistência de projetos.
- [x] Conferir que não há alteração de modelo sem migração nem migração destrutiva.
- [x] Aprovar Ruff, formatação, dependências, Django, Pytest e GitHub Actions.
- [x] Integrar cada entrega somente após seus checks e registrar as evidências finais.
- [x] Revisar e fechar os critérios abaixo, sem ampliar para tarefas.

## Critérios de aceitação da sprint

- [x] Proprietário cria projeto somente na organização em que possui esse papel.
- [x] Nome, descrição, organização, autor e datas seguem o contrato.
- [x] Participantes consultam apenas os projetos da organização autorizada.
- [x] Projeto de outra organização não é acessível pela troca de IDs no caminho.
- [x] Membro não cria, edita, arquiva ou restaura projetos.
- [x] Autoria não substitui participação nem papel para conceder acesso.
- [x] Revogação de vínculo/papel vale com o mesmo JWT e após espera nas escritas.
- [x] Arquivamento/restauração preservam os dados e respeitam os papéis.
- [x] Paginação e erros seguem o contrato documentado.
- [x] Sprints anteriores e testes novos passam no PostgreSQL e no CI.
- [x] Migrações são aditivas; configurações, segredos e volumes existentes preservados.
- [x] Documentação e PRs refletem o que foi efetivamente entregue.

## Limites e sequência

Não inclui tarefas, responsáveis por tarefa, prazos, etiquetas, comentários,
anexos, frontend, notificações, novos papéis, cadastro de usuários, convites,
exclusão de projetos/organizações ou infraestrutura nova. Operações
administrativas fora desta API mantêm as limitações documentadas na Sprint 2.

Sequência: 1 → 2 → 3 → 4. Concluir cada entrega com testes e revisão antes de
iniciar a seguinte. Migrações existentes são preservadas; nenhuma senha será
alterada e nenhum volume será removido. Uma migração destrutiva ou correção
de dados existente exigirá explicação e confirmação explícita.

## Progresso da Entrega 1 — 26/10/2026

Modelo Project e coleção GET/POST implementados. O app reutiliza a verificação
central de acesso à organização, com consulta de vínculo/papel após o bloqueio
nas escritas. O criador é obtido do JWT e a organização é definida pelo caminho;
campos controlados pelo servidor são rejeitados na entrada.

Foram aprovados **247 testes em 31,15 s** no PostgreSQL separado de testes:
195 anteriores e 52 novos. A cobertura nova inclui modelo e preservação de dados,
limites dos campos, identidade, autoria, papéis por organização, paginação,
erros, remoção de vínculo, dois testes de revogação concorrente de acesso e
um teste de falha real de chave estrangeira adiada até o commit, com rollback
e mensagem genérica.
A execução conjunta dos módulos está organizada em pacote próprio para evitar
colisão entre nomes de arquivos de teste. Ruff, formatação, dependências,
verificações Django e correspondência entre modelos/migrações passaram.

A migração inicial contém somente CreateModel Project. Seu SQL foi revisado:
cria a tabela projects, seus índices e vínculos, sem alterar tabelas anteriores.
Foi validada no banco de testes e aplicada localmente com as contagens de
usuários, organizações e vínculos existentes preservadas. Há zero projetos de
desenvolvimento e nenhuma migração pendente; nenhum dado de exemplo foi criado
no banco local. Credenciais, Compose, modelos e migrações anteriores permanecem
intactos. A configuração Django apenas registra o novo app; sua leitura de
credenciais permanece igual.

README atualizado com a coleção disponível, validações e atualização segura
de outra instalação no PowerShell. A execução remota e o estado da revisão
ficam registrados no PR desta entrega. A criação/listagem foi integrada pelo PR #6.
Consulta e edição foram integradas pelo PR #7.

## Progresso da Entrega 2 — 26/10/2026

GET e PATCH individuais implementados com busca do projeto limitada à
organização autorizada. O mesmo filtro é compartilhado com a coleção; a
permissão é conferida sobre a organização antes de consultar o projeto.
Proprietários editam somente nome e descrição, preservando campos omitidos e
campos controlados pelo servidor. PATCH vazio mantém os dados e updated_at.

A edição bloqueia a organização e consulta novamente vínculo/papel após a
espera. Autoria não concede acesso independente: rebaixamento e remoção são
observados com o mesmo JWT, assim como a promoção de membro a proprietário.
O projeto pode ser consultado e editado se já estiver arquivado. A Entrega 2
mantinha is_archived protegido; a Entrega 3 acrescenta sua alteração ao PATCH.
IDs de projeto ou parâmetros
de consulta não transferem o alvo entre organizações.

A suíte local aprovou **304 testes em 29,92 s** no PostgreSQL separado de testes:
247 anteriores e 57 novos. Os testes novos verificam papéis, autoria, ausência de
JWT, superusuários, projetos de outra organização, campos proibidos, limites,
PATCH parcial, resposta sem dados privados, promoção/revogação com o mesmo JWT,
revogação concorrente durante a espera pelo bloqueio e falha real de chave
estrangeira adiada até o commit da edição, com rollback e mensagem genérica.
Ruff, formatação, dependências, Django e a verificação de migrações passaram.

Não houve mudança de modelos, configurações ou migrações. Os arquivos anteriores
fora do escopo desta entrega foram preservados por comparação de hashes,
incluindo credenciais, Compose, modelos e testes anteriores não afetados.
A auditoria somente leitura encontrou zero organizações e zero projetos no
banco de desenvolvimento e nenhuma migração pendente. Nenhum registro de exemplo
foi criado ou alterado nesse banco e nenhum volume foi removido.

README atualizado com caminhos, exemplos, campos, erros e validação em novo
PowerShell. A validação remota e o estado da revisão ficam registrados no PR
desta entrega. A consulta/edição foi integrada pelo PR #7; o arquivamento e o
encerramento foram realizados nas entregas seguintes.

## Progresso da Entrega 3 — 26/10/2026

Arquivamento/restauração implementados pelo PATCH individual, com booleanos
JSON true/false. A criação mantém is_archived protegido, inclusive quando o
cliente tenta informar false. Um serializer específico da edição acrescenta
somente esse campo aos campos já permitidos, reutilizando atualização parcial,
transação, bloqueio da organização e autorização existentes.

Projetos arquivados continuam consultáveis, aparecem na coleção paginada e
podem ser editados por proprietários. Arquivar/restaurar preserva a identidade,
organização, autoria, conteúdo e vínculos, sem criar ou excluir registros.
Valores inválidos e campos proibidos impedem toda a alteração; nome e descrição
podem ser enviados junto com o sinalizador em uma mesma operação válida.

A suíte local aprovou **350 testes em 29,12 s** no PostgreSQL separado de testes:
304 anteriores e 46 novos. A cobertura nova verifica arquivar/restaurar, repetição
da operação, preservação de registros e outra organização, consulta/edição de
arquivados, booleanos estritos, rejeição no POST, campos inválidos combinados,
papéis, autoria, JWT, superusuários e revogação com o mesmo token. Os testes de
concorrência foram estendidos para arquivamento e restauração enquanto a escrita
aguarda o bloqueio, com rebaixamento/remoção do solicitante; a falha de integridade
adiada até o commit também foi validada para arquivamento, com rollback.

Ruff, formatação, dependências, Django e verificações de migrações passaram.
Modelos, migrações, configurações e demais arquivos fora do escopo foram
preservados por comparação de hashes. A auditoria somente leitura encontrou
zero organizações e zero projetos no banco de desenvolvimento, sem migrações
pendentes. Nenhum registro de desenvolvimento ou volume foi alterado.

README atualizado com exemplos de arquivar e restaurar, valores aceitos, erros,
permissões e validação no PowerShell. A execução remota e o estado da revisão
ficam registrados no PR #8, integrado à main. O
[CI #33](https://github.com/danielbramos4/taskflow-backend/actions/runs/40407772795)
aprovou os 350 testes no PostgreSQL 17 para o commit `0aaabe6`.

## Encerramento — Entrega 4, 26/10/2026

O README documenta o fluxo completo de organizações, projetos, membros e
arquivamento. O teste `tests/projects/test_sprint3_flow.py` executa esse fluxo
pelas APIs, com login JWT real para três contas fictícias no banco de testes.
Ele valida criação/edição, arquivamento/restauração, isolamento de outra equipe,
promoção, rebaixamento e remoção do criador com os mesmos tokens. A renovação do
JWT preserva a conta e não devolve acesso à organização. Conteúdo, autoria,
organização, data de criação e projeto da outra equipe permanecem preservados.

A suíte local aprovou **351 testes em 36,83 s** no PostgreSQL separado de
testes: os 350 anteriores e um fluxo integrado novo, sem falhas ou testes
ignorados. Ruff, formatação (52 arquivos), dependências, Django e consistência
entre modelos e migrações passaram.

O encerramento altera somente README, este registro e o novo teste integrado.
Nenhum código de aplicação, modelo, migração, configuração ou teste anterior
foi alterado. A comparação de hashes preservou os 64 arquivos protegidos,
incluindo `.env`, Compose e configurações. O `.env` continua ignorado e fora do
Git. A auditoria somente leitura do banco local confirmou ausência de migrações
pendentes e de organizações sem proprietário ativo; nenhum dado de demonstração
foi inserido ou alterado. Senhas e volumes existentes foram preservados.

| Critério | Evidência automatizada |
| --- | --- |
| Criação, campos e identidade | `tests/projects/test_models.py` e `test_api.py` |
| Leitura, edição, papéis por organização e IDs isolados | `tests/projects/test_api.py` e `test_detail_api.py` |
| Arquivamento/restauração e preservação | `tests/projects/test_archive_api.py` |
| Revogação após bloqueio e rollback real no PostgreSQL | `tests/projects/test_concurrency.py` |
| Login, refresh e gestão de organizações/membros anteriores | `tests/accounts/` e `tests/organizations/` |
| Fluxo completo, autoria sem privilégio e tokens após revogação | `tests/projects/test_sprint3_flow.py` |

As entregas funcionais foram integradas pelos PRs #6, #7 e #8 somente após o
CI aprovado. O PR de encerramento registra o commit exato e a execução aprovada
dos checks antes da integração; a main também é conferida após o merge.
Sprint 3 encerrada no escopo de projetos por organização. Tarefas e demais
funcionalidades futuras permanecem fora desta entrega.
