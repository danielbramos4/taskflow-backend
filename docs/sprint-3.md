# Sprint 3 — projetos por organização

## Objetivo e formato

Permitir que equipes organizem seu trabalho em projetos vinculados a uma
organização, preservando o isolamento e os papéis entregues na Sprint 2.
Prioridade escolhida pelo usuário: projetos por organização. Execução por
entregas, sem prazo fixo. A Entrega 1 está implementada e validada localmente,
para revisão no PR. As Entregas 2 a 4 continuam planejadas: consulta/edição,
arquivamento e aceite completo.

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

POST aceita somente `name` e `description`. PATCH da Entrega 2 aceita somente
esses campos; a Entrega 3 acrescenta `is_archived` ao PATCH. Campos de identidade,
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

- [ ] Implementar GET e PATCH de detalhes com busca limitada à organização.
- [ ] Preservar campos omitidos no PATCH e validar limites/valores.
- [ ] Proibir alteração de organização, autor, datas, ID e arquivamento nesta entrega.
- [ ] Testar tentativa de acessar projeto de B pelo caminho de A e IDs inexistentes.
- [ ] Testar papéis distintos da mesma pessoa em organizações diferentes.
- [ ] Testar autoria sem vínculo e alteração/revogação de papel com o mesmo JWT.
- [ ] Documentar requests, respostas e erros e conferir o CI do PR.

**Aceite:** membro consulta com 200 e edita com 403; externo recebe 404;
campos inválidos ou tentativa de transferir o projeto não modificam dados.

## Entrega 3 — arquivar e restaurar sem apagar

**Resultado:** proprietários sinalizam projetos arquivados e podem restaurá-los.

- [ ] Acrescentar `is_archived` booleano ao PATCH, mantendo POST ativo por padrão.
- [ ] Garantir que arquivados continuam consultáveis e editáveis com as mesmas permissões.
- [ ] Rejeitar valores de arquivamento inválidos e campos não permitidos.
- [ ] Testar arquivar/restaurar, membro sem escrita e isolamento entre organizações.
- [ ] Garantir que nenhum arquivamento exclui projeto, organização, conta ou vínculo.
- [ ] Documentar o comportamento e conferir o CI do PR.

**Aceite:** proprietário alterna o sinalizador com 200, sem perder dados nem
alterar vínculos. Membro recebe 403; externo recebe 404; DELETE continua 405.

## Entrega 4 — validar o fluxo e encerrar a sprint

- [ ] Documentar um fluxo completo com organização, projeto, membro e arquivamento.
- [ ] Validar login/refresh, gestão de organizações/membros e os 195 testes da base.
- [ ] Validar papéis, isolamento, revogação e persistência de projetos.
- [ ] Conferir que não há alteração de modelo sem migração nem migração destrutiva.
- [ ] Aprovar Ruff, formatação, dependências, Django, Pytest e GitHub Actions.
- [ ] Integrar cada entrega somente após seus checks e registrar as evidências finais.
- [ ] Revisar e fechar os critérios abaixo, sem ampliar para tarefas.

## Critérios de aceitação da sprint

- [ ] Proprietário cria projeto somente na organização em que possui esse papel.
- [ ] Nome, descrição, organização, autor e datas seguem o contrato.
- [ ] Participantes consultam apenas os projetos da organização autorizada.
- [ ] Projeto de outra organização não é acessível pela troca de IDs no caminho.
- [ ] Membro não cria, edita, arquiva ou restaura projetos.
- [ ] Autoria não substitui participação nem papel para conceder acesso.
- [ ] Revogação de vínculo/papel vale com o mesmo JWT e após espera nas escritas.
- [ ] Arquivamento/restauração preservam os dados e respeitam os papéis.
- [ ] Paginação e erros seguem o contrato documentado.
- [ ] Sprints anteriores e testes novos passam no PostgreSQL e no CI.
- [ ] Migrações são aditivas; configurações, segredos e volumes existentes preservados.
- [ ] Documentação e PRs refletem o que foi efetivamente entregue.

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

Foram aprovados **246 testes em 25,08 s** no PostgreSQL separado de testes:
195 anteriores e 51 novos. A cobertura nova inclui modelo e preservação de dados,
limites dos campos, identidade, autoria, papéis por organização, paginação,
erros, remoção de vínculo e dois testes de revogação concorrente de acesso.
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
ficam registrados no PR desta entrega. Próximo trabalho: Entrega 2, após
revisão e integração da criação/listagem de projetos.
