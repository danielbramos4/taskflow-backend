# Sprint 4 — tarefas por projeto

## Objetivo e formato

Permitir organizar tarefas dentro dos projetos da Sprint 3, mantendo o isolamento
por organização e os papéis owner/member existentes. Prioridade confirmada pelo
usuário em 27/10/2026: tarefas por projeto. Execução por entregas, sem prazo fixo.
As Sprints 1 a 3 estão integradas à main, com 351 testes aprovados na base.

## Modelo e regras

Novo app `apps.tasks`, com o modelo Task:

| Campo | Regra |
| --- | --- |
| `id` | Identificador inteiro gerado pelo servidor. |
| `project` | Projeto indicado no caminho, dentro da organização autorizada; não pode ser trocado pela API. |
| `title` | Obrigatório, até 150 caracteres; espaços nas extremidades removidos; não aceita vazio. |
| `description` | Opcional, padrão vazio, até 5.000 caracteres; não aceita null. |
| `status` | Padrão `todo`; valores do domínio: `todo`, `in_progress`, `done`. Alteração pela API somente na Entrega 3. |
| `created_by` | Usuário do JWT na criação; pode ficar nulo após exclusão administrativa da conta. |
| `created_at`, `updated_at` | Datas controladas pelo servidor. |

Títulos repetidos são permitidos; a identidade usa o ID. A organização da tarefa
é a do projeto; não há um segundo vínculo que possa divergir. Excluir um projeto
com tarefas pelo ORM é protegido (`PROTECT`). Excluir administrativamente uma
conta preserva suas tarefas e torna a autoria nula (`SET_NULL`). Nenhuma dessas
exclusões é oferecida pela API desta sprint.

Todos os participantes da organização consultam suas tarefas. Somente owners
criam e alteram. Autoria, superusuário e participação em outra organização não
concedem privilégios. Perda de papel/vínculo vale na próxima requisição com o
mesmo JWT. Escritas bloqueiam a organização e consultam novamente a autorização
depois da espera, compatíveis com as escritas de projetos e membros existentes.

Projetos arquivados mantêm suas tarefas consultáveis e administráveis segundo
os mesmos papéis: o arquivamento continua sendo uma marca de organização do
trabalho, sem acrescentar um bloqueio de acesso ou de edição.

## Contrato da API

Prefixo: `/api/v1/organizations/{organization_id}/projects/{project_id}/tasks/`.

| Entrega | Operação | Resultado |
| --- | --- | --- |
| 1 | GET da coleção | 200; tarefas do projeto autorizado, com paginação de 20 registros. |
| 1 | POST da coleção | 201; owner informa `title` e `description` opcional; servidor define projeto, autor e status todo. |
| 2 | GET de `{task_id}/` | 200; consulta individual limitada a organização e projeto. |
| 2 | PATCH de `{task_id}/` | 200; owner altera título e/ou descrição. |
| 3 | Mesmo PATCH com `status` | Planejado: owner alterna entre os três estados, sem excluir a tarefa. |

Resposta: `id`, `project_id`, `title`, `description`, `status`, `created_by_id`,
`created_at`, `updated_at`. Não inclui dados privados da conta. Coleção com
`count`, `next`, `previous`, `results`, ordenada por `created_at, id` (mais antigas
primeiro). Parâmetros de projeto, organização ou usuário não ampliam o acesso.
Filtros de status e pesquisa não fazem parte desta sprint.

POST aceita somente título e descrição. Enviar identidade, projeto, organização,
status (inclusive todo), autor, datas ou campos desconhecidos recebe 400.
Valores inválidos e corpos que não são objetos JSON recebem 400. Sem JWT válido:
401. Member em escrita: 403. Organização sem vínculo, projeto inexistente ou
projeto de outra organização no caminho: 404. Métodos não oferecidos: 405.
Falhas de integridade inesperadas recebem 500 com mensagem genérica e rollback,
inclusive quando a falha ocorre ao concluir a transação. Não há DELETE ou PUT.
PATCH individual aceita somente título e descrição; protege os mesmos campos
de identidade, vínculos, autoria, status e datas que o POST. Campos omitidos
permanecem intactos; PATCH vazio preserva também updated_at. A busca confere
organização, projeto e tarefa, sem ampliar acesso por parâmetros de consulta.

## Entrega 1 — criar e listar tarefas

- [x] Criar modelo e migração inicial aditiva, sem alterar modelos anteriores.
- [x] Registrar app e coleção aninhada no projeto e na organização.
- [x] Definir projeto, autor e status inicial no servidor; validar entrada.
- [x] Reutilizar autorização da organização e reconsultá-la após o bloqueio.
- [x] Paginar e ordenar sem misturar projetos ou equipes.
- [x] Testar JWT, papéis, campos, projetos arquivados e preservação de dados.
- [x] Testar revogação concorrente e falha real de integridade no PostgreSQL.
- [x] Validar migração, base anterior e verificações de qualidade.
- [x] Integrar a entrega após CI aprovado e revisão do PR.

**Aceite:** owner cria com 201; member lê com 200 e cria com 403; externo recebe
404; projeto de outra organização não pode ser usado no caminho. Criação
inválida ou não autorizada não deixa tarefa persistida.

## Entrega 2 — consultar e editar tarefas

- [x] Implementar GET/PATCH individual com busca limitada aos dois pais.
- [x] Permitir somente título e descrição no PATCH, preservando campos omitidos.
- [x] Rejeitar transferência de projeto, alteração de autor, status e datas.
- [x] Testar papéis, IDs cruzados, autoria e revogação com o mesmo JWT.
- [x] Testar espera pelo bloqueio e rollback; documentar e validar CI.

**Aceite:** participante consulta com 200; owner edita com 200; member recebe
403 ao editar e externo recebe 404. Campos proibidos, dados inválidos e IDs
cruzados não alteram registros. Status permanece protegido até a Entrega 3.

## Entrega 3 — alterar estado de execução

- [ ] Acrescentar status ao PATCH, aceitando somente todo, in_progress e done.
- [ ] Permitir transições entre quaisquer desses estados, inclusive reabrir.
- [ ] Preservar conteúdo, autoria, projeto e vínculos em cada transição.
- [ ] Validar atomicidade com campos combinados, papéis e revogação concorrente.
- [ ] Documentar exemplos e erros; conferir testes e CI.

## Entrega 4 — fluxo completo e encerramento

- [ ] Validar fluxo de organização, projeto, tarefa, membro e estados com JWT real.
- [ ] Validar promoção, rebaixamento, remoção do criador e refresh sem devolver acesso.
- [ ] Aprovar a suíte anterior e nova no PostgreSQL local e no CI.
- [ ] Conferir migrações, configurações, segredos, arquivos preexistentes e volumes.
- [ ] Integrar as entregas após checks, registrar evidências e fechar o aceite.

## Critérios de aceitação da sprint

- [ ] Tarefas pertencem a um único projeto e à organização desse projeto.
- [ ] Participantes leem somente projetos de organizações autorizadas.
- [ ] Owners criam e alteram; members não escrevem; autoria não concede acesso.
- [ ] Título, descrição, status e campos controlados seguem o contrato.
- [ ] GET/PATCH individual não aceita IDs de tarefa de outro projeto.
- [ ] Mudanças de estado preservam registros, conteúdo e relacionamentos.
- [ ] Revogação vale com o mesmo JWT e após espera por bloqueio.
- [ ] Paginação, erros e rollback funcionam no PostgreSQL.
- [ ] Sprints anteriores e fluxo novo passam localmente e no CI.
- [ ] Migrações aditivas; credenciais, dados e volumes existentes preservados.
- [ ] Documentação e PRs correspondem ao comportamento integrado.

## Limites

Sem responsáveis por tarefa, prazos, prioridade, etiquetas, comentários, anexos,
frontend, notificações, novos papéis ou exclusões pela API. Nenhuma troca de
senha, remoção de volume ou migração destrutiva. Arquivos não versionados de
outros trabalhos são preservados e permanecem fora da entrega.

## Progresso da Entrega 1 — 27/10/2026

Modelo e coleção GET/POST implementados, com projeto/autoria definidos no
servidor, validação estrita dos campos de entrada e paginação estável. A criação
reutiliza a transação e o bloqueio da organização, revalidando o papel após a
espera. O status inicial é todo e permanece protegido no POST.

Foram aprovados **405 testes em 27,67 s** no PostgreSQL separado de testes:
os 351 anteriores e 54 novos, sem falhas ou skips. A cobertura inclui modelo,
campos, identidades, JWT, papéis por organização, isolamento dos dois pais,
paginação, projetos arquivados e autoria nula. Dois testes verificam bloqueio
real no PostgreSQL e rebaixamento/remoção durante a espera; outro valida falha
real de chave estrangeira adiada até o commit, com rollback e erro genérico.

Ruff, formatação (60 arquivos), dependências, Django e consistência de migrações
aprovados. Os testes locais selecionaram todos os diretórios versionados do
TaskFlow e os novos testes de tarefas, preservando arquivos não versionados de
outro trabalho fora dessa execução. O CI usa o checkout do PR e executa a suíte
completa versionada, com PostgreSQL 17. Seu resultado fica registrado no PR.

A migração tasks.0001_initial contém somente CreateModel Task. O SQL foi revisado:
cria tabela, índices e chaves estrangeiras, sem alterar tabelas anteriores. Foi
aplicada no banco de testes e no banco local. A comparação de conteúdo antes e
depois preservou todos os registros de usuários, organizações, vínculos e
projetos. Há zero tarefas de desenvolvimento e nenhuma migração pendente.

Os 71 arquivos protegidos, incluindo os sete arquivos não versionados
preexistentes, foram preservados por hash. Segredos, Compose, configurações de
credenciais e modelos/migrações anteriores permanecem intactos; settings apenas
registra o novo app. Nenhuma senha ou volume foi alterado e nenhum registro de
demonstração foi criado no banco local. README atualizado com a API, os limites
e a validação em novo PowerShell. A Entrega 1 foi integrada à main pelo
[PR #10](https://github.com/danielbramos4/taskflow-backend/pull/10), após CI
aprovado e conferência da implementação. O
[CI #39](https://github.com/danielbramos4/taskflow-backend/actions/runs/40601349609)
aprovou 405 testes no PostgreSQL 17 para o código da entrega; a atualização final
do registro também passou pelo CI antes da integração. A consulta/edição
individual é tratada na Entrega 2 abaixo.

## Progresso da Entrega 2 — 27/10/2026

Consulta e edição individual implementadas. Coleção e detalhe compartilham a
busca limitada ao projeto da organização autorizada. A autorização é conferida
sobre a organização; a tarefa só é buscada depois de validar os dois pais.
Owners alteram título e descrição; status, vínculos, autoria e datas continuam
protegidos. Atualização parcial salva somente campos fornecidos e updated_at;
PATCH vazio não altera nenhum dado. Tarefas de projetos arquivados mantêm as
mesmas regras de leitura e edição.

Foram aprovados **468 testes em 35,55 s** no PostgreSQL separado de testes:
os 405 anteriores e 63 novos, sem falhas ou testes ignorados. A validação local
seleciona os diretórios versionados do TaskFlow e preserva os arquivos de outro
trabalho fora da execução; o CI executa a suíte completa versionada.

Os testes novos verificam JWT, papéis, superusuários sem vínculo, autoria nula,
IDs cruzados de projeto e organização, consultas com IDs forjados, campos
protegidos, limites, corpos inválidos e atomicidade. Promoção, rebaixamento e
remoção são conferidos pelas APIs de membros com os mesmos JWTs. Um teste
preserva mudança concorrente em campo omitido; dois verificam revogação real
enquanto a edição aguarda o bloqueio da organização no PostgreSQL. Falha real de
chave estrangeira adiada ao commit desfaz a edição e retorna erro genérico.

Ruff, formatação, dependências, Django e consistência de migrações aprovados.
Não houve alteração de modelos, migrações ou configurações. Os 84 arquivos
protegidos, incluindo os sete arquivos não versionados preexistentes, foram
preservados por hash. A auditoria somente leitura encontrou zero organizações,
projetos e tarefas no banco local e nenhuma migração pendente. Senhas e volumes
permanecem preservados; nenhum dado de demonstração foi criado ou alterado.

README documenta caminhos, campos, exemplos, erros e validação em novo
PowerShell. A execução remota e o commit aprovado são registrados no PR desta
entrega. Integração à main aguarda o CI e a revisão; a Entrega 3 continua
planejada para a mudança de estado da tarefa.
