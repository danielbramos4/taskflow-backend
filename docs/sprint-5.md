# Sprint 5 — responsáveis e prazos das tarefas

## Objetivo e formato

Organizar o trabalho existente com responsáveis e prazos opcionais, preservando
os projetos, estados e permissões das sprints anteriores. Prioridade escolhida
pelo usuário: responsáveis e prazos nas tarefas. Planejamento registrado em
28/10/2026; execução por entregas, sem prazo fixo. A Sprint 4 está integrada à
main pelo PR #13, com 525 testes aprovados.

## Regras de responsabilidade

Uma tarefa pode ficar sem responsável ou ter um único vínculo de participante
da sua organização como responsável. Owners e members são elegíveis, desde que
a conta esteja ativa no momento da atribuição. Ser responsável não concede
permissões adicionais: owners continuam administrando e members consultando.
Autoria e responsabilidade são independentes.

O modelo Task recebe `assignee`, uma chave estrangeira opcional para Membership,
com SET_NULL. Usar o vínculo garante que remover a participação limpa a
responsabilidade sem excluir tarefa ou conta. Reingresso cria outro vínculo e
não restaura atribuições antigas. Exclusão administrativa da conta também limpa
a responsabilidade pela remoção de seus vínculos. Alterar owner/member sem
remover o vínculo mantém a atribuição e aplica as permissões do novo papel.

O PATCH altera updated_at quando modifica a tarefa. A limpeza automática pela
exclusão do vínculo usa SET_NULL e preserva as demais colunas, inclusive datas.
Projetos arquivados mantêm as mesmas regras de acesso e administração.

## Contrato da Entrega 1

Os endpoints de tarefas existentes permanecem nos mesmos caminhos:
`/api/v1/organizations/{organization_id}/projects/{project_id}/tasks/`
e seu detalhe `{task_id}/`.

| Campo | Regra |
| --- | --- |
| `assignee_membership_id` | Opcional no POST/PATCH; ID de Membership da organização do projeto, com conta ativa. null deixa sem responsável. |
| `assignee_user_id` | Somente leitura; ID da conta correspondente ao vínculo; null quando não há responsável. |

Os dois campos são acrescentados às respostas da coleção, criação, consulta e
edição. Não contêm e-mail, senha ou tokens. Para escolher o vínculo, consulte a
coleção de membros da organização e use seu campo `id`, não `user_id`. O ID de
vínculo de outra organização é rejeitado mesmo quando a mesma pessoa participa
das duas equipes ou o solicitante é owner de ambas.

POST aceita título, descrição opcional e assignee_membership_id opcional;
continua criando com status todo e rejeitando status enviado pelo cliente.
PATCH aceita título, descrição, status e assignee_membership_id. O responsável
omitido é preservado; enviar null remove apenas a atribuição. Não há novo método
nem autorização por responsável. Campos de identidade, vínculos de projeto,
autoria, datas, assignee_user_id e nomes alternativos como assignee_id recebem
400. Qualquer campo inválido impede toda a escrita.

Vínculo inexistente, removido, de outra organização ou associado a conta inativa
recebe 400 no campo assignee_membership_id, sem expor dados da conta. JWT inválido
ou ausente recebe 401; member tentando escrever recebe 403; organização sem
participação ou IDs de tarefa/projeto inconsistentes recebem 404.

Atribuição participa da mesma transação e bloqueio da organização usados pelas
outras alterações. Papel do solicitante e existência/elegibilidade do vínculo
destinatário são consultados após a espera. Remoção de membros pela API usa esse
mesmo bloqueio. Falhas de integridade, inclusive ao commit, recebem erro genérico
e rollback. A coleção carrega os vínculos junto das tarefas, sem uma consulta
adicional por responsável a cada linha.

## Entrega 1 — responsáveis

- [x] Acrescentar vínculo opcional com migração aditiva e tarefas existentes sem responsável.
- [x] Permitir atribuir, trocar, omitir ou limpar responsável no POST/PATCH de owner.
- [x] Limitar a participantes da organização com conta ativa; manter permissões atuais.
- [x] Expor IDs de vínculo e conta nas respostas sem dados privados.
- [x] Preservar tarefas/contas ao remover vínculo e não restaurar atribuição no reingresso.
- [x] Testar papéis, isolamento, campos inválidos, projetos arquivados e consultas da coleção.
- [x] Testar solicitante/vínculo alterado durante espera e rollback real no PostgreSQL.
- [x] Validar migração, base anterior, qualidade e documentar a validação no PowerShell.
- [ ] Integrar após revisão e CI aprovado.

## Entrega 2 — prazos opcionais

- [ ] Acrescentar due_date opcional em formato de data YYYY-MM-DD, sem horário.
- [ ] Permitir owner informar, alterar, omitir ou limpar o prazo com null.
- [ ] Aceitar datas passadas para registrar pendências, sem mudar status automaticamente.
- [ ] Preservar a independência entre prazo, responsabilidade e estado da tarefa.
- [ ] Validar datas, campos combinados, papéis, migração e concorrência; documentar e conferir CI.

## Entrega 3 — consultas por responsável e prazo

- [ ] Filtrar a coleção do projeto por vínculo responsável e tarefas sem responsável.
- [ ] Filtrar por intervalo de datas de prazo, com limites explícitos e datas válidas.
- [ ] Combinar filtros sem ampliar acesso a outros projetos ou organizações.
- [ ] Manter paginação e ordenação estáveis; testar erros, isolamento e conferir CI.

## Entrega 4 — fluxo completo e encerramento

- [ ] Validar atribuição, prazo, consulta, remoção de vínculo e reingresso com JWT real.
- [ ] Aprovar suíte anterior e nova no PostgreSQL e no CI.
- [ ] Conferir preservação de dados, credenciais, volumes e arquivos preexistentes.
- [ ] Integrar as entregas após checks e registrar o aceite completo.

## Critérios de aceitação

- [ ] Responsável é opcional e pertence à organização da tarefa no momento da atribuição.
- [ ] Responsabilidade não amplia acesso nem substitui autoria/papel.
- [ ] Remoção de vínculo limpa a atribuição e preserva a tarefa; reingresso não a restaura.
- [ ] Prazo opcional segue o contrato de data, sem alterar status automaticamente.
- [ ] Campos omitidos e erros de validação preservam valores e relacionamentos.
- [ ] Filtros respeitam organização/projeto, paginação e validação.
- [ ] Revogação durante espera e falhas de integridade não deixam escritas indevidas.
- [ ] Sprints anteriores e fluxo novo passam no PostgreSQL local e no CI.
- [ ] Migrações aditivas; segredos, dados, arquivos locais e volumes preservados.
- [ ] Documentação e PRs correspondem ao comportamento integrado.

## Limites

Sem interface web, cadastro de contas, notificações, convites, prioridade,
comentários, anexos, exclusões de tarefas pela API ou novos papéis. Nenhuma
alteração de senha ou remoção de volume. As operações administrativas fora da
API mantêm os limites já documentados nas sprints anteriores.

## Progresso da Entrega 1 — 28/10/2026

Responsáveis implementados no POST/PATCH e expostos na coleção/detalhe com IDs
explícitos de vínculo e conta. A validação é limitada à organização autorizada
e ocorre após o bloqueio; a remoção do vínculo limpa a atribuição via SET_NULL.
O carregamento conjunto do vínculo evita consultas por linha na paginação.

Foram aprovados **578 testes em 51,33 s** no PostgreSQL separado de testes:
525 anteriores e 53 novos (45 de API/modelo e oito de concorrência/rollback),
sem falhas ou testes ignorados. Quatro verificações de formato de resposta em
três arquivos anteriores foram atualizadas para incluir os dois campos novos.
Os demais contratos e casos anteriores foram preservados. A execução local
seleciona todos os diretórios versionados do TaskFlow e preserva arquivos não
versionados de outro trabalho; o CI executa o checkout completo do PR.

Ruff, formatação (66 arquivos), dependências, Django e consistência de migrações
aprovados. A migração tasks.0002_task_assignee contém somente AddField nullable
assignee com índice e chave estrangeira; o SQL foi revisado. Aplicada no banco
de testes e local com comparação do conteúdo anterior e posterior de usuários,
organizações, vínculos, projetos e campos anteriores das tarefas. Registros
preservados; tarefas existentes sem responsável; nenhuma migração pendente.

Os 86 arquivos protegidos, incluindo os sete arquivos locais não versionados,
foram preservados por hash. Credenciais, Compose, configurações, modelos de
organizações/projetos e migrações anteriores não foram alterados. Nenhuma senha
ou volume foi alterado e nenhum dado de demonstração foi criado no banco local.
README atualizado com os campos, regras e validação em novo PowerShell. O PR
registra o commit exato e o CI aprovado antes da integração; prazo e filtros
permanecem planejados para as entregas seguintes.
