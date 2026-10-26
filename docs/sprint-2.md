# Sprint 2 — organizações e permissões

## Objetivo e formato

Permitir que um usuário autenticado crie e gerencie organizações, consulte apenas
as organizações das quais participa e administre seus membros conforme o papel
que possui em cada organização.

Escopo escolhido: organizações e permissões. Execução por entregas, sem prazo
fixo. Sprint concluída em 26/10/2026, com as quatro entregas e todos os critérios
de aceite validados. As Entregas 1, 2 e 3 foram integradas à `main` pelos
[PR #2](https://github.com/danielbramos4/taskflow-backend/pull/2),
[PR #3](https://github.com/danielbramos4/taskflow-backend/pull/3) e
[PR #4](https://github.com/danielbramos4/taskflow-backend/pull/4).
A Entrega 4 encerra a documentação, o teste integrado e a revisão dos critérios.

## Ponto de partida da sprint

- Sprint 1 integrada à `main`, com CI aprovado e 11 testes existentes.
- Django, PostgreSQL, JWT e `/api/v1/auth/me/` funcionais.
- Modelos `Organization` e `Membership` disponíveis.
- Papéis existentes: `owner` e `member`.
- Restrição de unicidade do vínculo usuário/organização já aplicada no banco.
- APIs de organizações e regras de autorização dessas operações ainda ausentes.

## Regras de acesso entregues

O papel vale dentro de cada organização: ser proprietário de A não concede
permissões sobre B. A identidade sempre vem do JWT validado pelo servidor.

| Operação | Proprietário da organização | Membro da organização | Usuário sem vínculo |
| --- | --- | --- | --- |
| Criar uma organização | Permitido, como qualquer usuário autenticado | Permitido | Permitido |
| Listar organizações | Apenas as próprias | Apenas as próprias | Lista vazia se não tiver vínculos |
| Consultar detalhes | Permitido | Permitido | 404 |
| Editar nome e slug | Permitido | 403 | 404 |
| Listar membros e papéis | Permitido | Permitido | 404 |
| Adicionar membro existente | Permitido | 403 | 404 |
| Alterar papel de um membro | Permitido, preservando um proprietário ativo | 403 | 404 |
| Remover um vínculo | Permitido, preservando um proprietário ativo | 403 | 404 |

Requisições sem autenticação válida recebem 401. Para quem não participa da
organização, recursos existentes e inexistentes têm a mesma resposta 404.
Não há exceção automática para `is_staff` ou `is_superuser` nessa API.

## Contrato da API

Os caminhos usam IDs inteiros dos modelos existentes. O vínculo de membro é
sempre consultado dentro da organização indicada no caminho.

| Método | Caminho | Entrada e resultado esperado |
| --- | --- | --- |
| GET | `/api/v1/organizations/` | Lista paginada das próprias organizações. |
| POST | `/api/v1/organizations/` | Recebe `name` e `slug`; cria organização e vínculo `owner` para o solicitante; retorna 201. |
| GET | `/api/v1/organizations/{organization_id}/` | Retorna os dados da organização e o papel do solicitante. |
| PATCH | `/api/v1/organizations/{organization_id}/` | Proprietário altera `name` e/ou `slug`; retorna 200. |
| GET | `/api/v1/organizations/{organization_id}/memberships/` | Lista paginada de vínculos da organização. |
| POST | `/api/v1/organizations/{organization_id}/memberships/` | Proprietário informa `user_id` de usuário ativo existente e `role`, com padrão `member`; retorna 201. |
| PATCH | `/api/v1/organizations/{organization_id}/memberships/{membership_id}/` | Proprietário altera somente `role`; retorna 200. |
| DELETE | `/api/v1/organizations/{organization_id}/memberships/{membership_id}/` | Proprietário remove somente o vínculo; retorna 204. |

Resposta de organização: `id`, `name`, `slug`, `my_role`, `created_at`, `updated_at`.
Resposta de vínculo: `id`, `user_id`, `username`, `role`, `created_at`.
As respostas não incluem senhas, tokens ou e-mails de outros usuários.

Paginação: 20 registros por página, com `count`, `next`, `previous` e
`results`. Ordenação estável por `name, id` nas organizações e `created_at, id`
nos vínculos. Não adicionar filtros que ampliem o conjunto acessível ao usuário.

Validações: nome obrigatório e não vazio, slug válido e único, limites atuais dos
modelos, papel limitado a `owner`/`member`, usuário ativo existente e vínculo único.
Campos inesperados ou tentativas de modificar campos controlados pelo servidor
recebem 400. No PATCH de vínculo, `user_id` e a organização não são modificáveis.
Erros de validação e a tentativa de remover/rebaixar o último proprietário ativo
recebem 400; métodos não oferecidos recebem 405. Erros internos não expõem SQL
nem detalhes de configuração.

## Entrega 1 — criar e listar as próprias organizações

**Resultado:** o usuário consegue iniciar sua organização e vê somente suas
participações na listagem.

- [x] Implementar serialização e rotas de coleção de organizações.
- [x] Exigir JWT e filtrar a listagem pelos vínculos do solicitante.
- [x] Criar organização e vínculo `owner` na mesma transação.
- [x] Definir o criador pelo JWT; impedir que o cliente escolha outro proprietário.
- [x] Validar nome, slug, campos permitidos e paginação.
- [x] Testar sucesso, falha de validação, ausência de autenticação e isolamento.
- [x] Testar que falha na criação do vínculo não deixa organização órfã.

**Aceite:** criar retorna 201 e exatamente um vínculo de proprietário para o
solicitante. O usuário A não vê a organização exclusiva de B na listagem. Um
usuário sem vínculos recebe uma lista vazia com 200.

## Entrega 2 — consultar e editar com autorização por organização

**Resultado:** participantes consultam detalhes e apenas proprietários editam.

- [x] Implementar GET e PATCH de detalhes.
- [x] Centralizar a verificação de participação e de papel por organização.
- [x] Aplicar o mesmo isolamento na busca por ID usado nos detalhes.
- [x] Testar proprietário, membro, usuário externo e usuário sem token.
- [x] Testar um usuário proprietário de A e membro de B: pode editar A, não B.
- [x] Testar IDs de organizações inexistentes e tentativas de trocar identidade.

**Aceite:** membro consulta com 200, mas recebe 403 ao editar; usuário externo
recebe 404. Nome/slug inválidos não alteram a organização. Campos como `my_role`
não podem ser usados para obter privilégios.

## Entrega 3 — administrar membros sem perder o proprietário

**Resultado:** proprietários controlam a equipe, com isolamento e preservação de
pelo menos um proprietário ativo nas operações da API.

- [x] Implementar listagem, inclusão, alteração de papel e remoção de vínculos.
- [x] Usar os IDs de usuários ativos já existentes; não criar contas nessa operação.
- [x] Rejeitar vínculo duplicado sem converter inclusão em atualização implícita.
- [x] Impedir acesso a um vínculo de B usando o caminho da organização A.
- [x] Impedir que membros comuns adicionem pessoas, se promovam ou removam vínculos.
- [x] Permitir promoção a proprietário antes de rebaixar/remover o proprietário anterior.
- [x] Impedir remoção/rebaixamento do último proprietário ativo, inclusive em concorrência.
- [x] Garantir que a remoção de vínculo preserve o usuário e a organização.
- [x] Testar todos os cenários e manter os testes da Sprint 1 aprovados.

**Aceite:** alterar/remover vínculo afeta somente a organização autorizada. A
remoção de acesso passa a valer na requisição seguinte, mesmo com JWT ainda
válido. Duas alterações concorrentes não deixam a organização sem proprietário
ativo. Uma pessoa pode sair do papel de proprietário se outro proprietário ativo
permanecer; membros não possuem uma operação separada de saída nesta sprint.

## Entrega 4 — validar e documentar o fluxo completo

**Resultado:** API documentada, testes de isolamento aprovados e entrega revisável.

- [x] Documentar requests, respostas, paginação e erros no README.
- [x] Registrar exemplo completo: criar organização, adicionar membro e testar permissões.
- [x] Garantir compatibilidade dos endpoints de autenticação já existentes.
- [x] Executar Pytest com PostgreSQL e manter os 11 testes anteriores aprovados.
- [x] Aprovar Ruff, formatação, `pip check` e verificações Django.
- [x] Confirmar que não há mudanças de modelo sem migração.
- [x] Publicar cada entrega em PR e conferir CI verde antes da integração.
- [x] Revisar os critérios abaixo e registrar as execuções de validação.

## Critérios de aceitação da sprint

- [x] Um usuário cria uma organização e se torna proprietário automaticamente.
- [x] Listagens e detalhes respeitam os vínculos do usuário em todas as organizações.
- [x] Autenticação não permite acesso a recursos de uma organização externa.
- [x] Membro lê dados permitidos, mas não administra a organização ou seus membros.
- [x] Proprietário administra somente organizações em que possui esse papel.
- [x] Vínculo e papel não são forjáveis por campos enviados pelo cliente.
- [x] A API não deixa organizações órfãs ao criar ou alterar vínculos.
- [x] Exclusão de vínculo não exclui conta, organização ou dados de outra equipe.
- [x] Remover um vínculo revoga o acesso sem exigir expiração do JWT.
- [x] Respostas de erro e regras de paginação seguem o contrato documentado.
- [x] Testes antigos e novos passam no PostgreSQL e no GitHub Actions.
- [x] Documentação, critérios e PRs refletem o comportamento entregue.

## Cuidados de implementação

Filtrar o conjunto consultado e verificar as operações de escrita são medidas
complementares: permissões de objeto não filtram automaticamente listagens nem
garantem a autorização de criação. A checagem de vínculo deve acontecer a cada
requisição; o papel não será embutido no JWT como fonte de autorização.

Na gestão de vínculos, serializar as alterações de uma mesma organização em uma
transação, bloqueando a linha da organização antes de verificar proprietários.
Todos os caminhos de alteração de vínculos devem seguir a mesma regra para que
duas operações concorrentes não removam o último proprietário.

Antes de implementar as regras, conferir por leitura se há organizações antigas
sem proprietário ativo. Se houver, definir a regularização com o usuário; não
atribuir acesso, alterar papéis ou apagar registros automaticamente.

O plano reutiliza os modelos atuais e não prevê migrações de esquema. Qualquer
necessidade de mudança será justificada durante a implementação. As credenciais,
o `.env` e os volumes existentes permanecem preservados.

## Limites desta sprint

Não inclui projetos/tarefas, frontend, cadastro público de usuários, convites por
e-mail, novos papéis, exclusão de organizações, autenticação nova ou alterações
de infraestrutura. A administração usa contas existentes. Alterações de estado
de usuários fora desta API, como desativação administrativa de um proprietário,
exigem uma regra futura própria para preservar a propriedade ativa.

## Sequência de execução

Concluir cada entrega com seus testes e critérios antes de iniciar a seguinte:
1 → 2 → 3 → 4. Uma entrega pode ser dividida em PRs menores conforme a revisão;
não há datas, estimativas em dias ou quantidade de testes tratadas como compromisso.

As quatro entregas foram implementadas e validadas. Não há funcionalidades
pendentes no escopo acordado da Sprint 2. O planejamento da próxima sprint
será uma decisão separada.

## Progresso da Entrega 1 — 23/10/2026

O [PR #2](https://github.com/danielbramos4/taskflow-backend/pull/2) contém a criação
e listagem de organizações. A [execução CI #9](https://github.com/danielbramos4/taskflow-backend/actions/runs/40002910065),
para o commit `369bb76`, aprovou 50 testes (11 anteriores e 39 novos), Ruff,
formatação, dependências, verificações Django e migrações no PostgreSQL 17.

Em 26/10/2026, WSL e Docker voltaram a responder e o PostgreSQL existente foi
validado localmente. Os 50 testes passaram também no banco separado de testes
(`--reuse-db`, 6,16 s), com Django sem problemas e nenhuma migração pendente.
A auditoria somente leitura encontrou zero organizações existentes e zero sem
proprietário ativo; não há registros antigos para regularizar. Credenciais,
modelos e Compose foram preservados byte a byte; nenhum volume foi removido.

Modelos, credenciais e volumes existentes foram preservados. A criação da
organização e do proprietário é atômica; a listagem é filtrada pelo vínculo do
solicitante e informa seu papel em cada organização. O estado da revisão e da
integração deve ser consultado no próprio PR.

## Progresso da Entrega 2 — 26/10/2026

Consulta e edição de organizações implementadas. Listagem e detalhes compartilham
um conjunto filtrado pelos vínculos do solicitante; a permissão de escrita exige
papel `owner` na organização consultada. Não há exceção para superusuários.

A suíte local aprovou 97 testes em 8,30 s no PostgreSQL separado de testes,
incluindo os 50 anteriores e 47 cenários novos. Foram verificados: leitura por
participantes, edição pelo proprietário, rejeição de membros e usuários externos,
IDs inexistentes, troca de identidade, mudanças de papel e remoção de vínculo
com o mesmo JWT. Também há cobertura de PATCH parcial, campos inválidos,
slug duplicado inclusive após a validação, falha de integridade e métodos
não oferecidos. Ruff, formatação, `pip check`, verificações Django e ausência de
migrações de modelo passaram.

README atualizado com caminhos, exemplos e respostas. A validação remota e o
estado da revisão ficam registrados no PR da Entrega 2. Credenciais, Compose,
modelos e migrações existentes foram preservados; nenhum volume foi removido.

## Progresso da Entrega 3 — 26/10/2026

Administração de membros implementada: listagem paginada para participantes;
inclusão de contas ativas existentes, alteração de papel e remoção de vínculo
reservadas a proprietários da organização correspondente. Respostas omitem dados
privados da conta e não há criação de usuários nem alteração de identidade ou
de organização de um vínculo. Duplicidades recebem 400 sem modificar o papel.

Cada escrita bloqueia a linha da organização dentro de uma transação e consulta
novamente vínculo e papel após obter o bloqueio. O membro alvo é buscado somente
dentro dessa organização. Remoção ou rebaixamento exige outro proprietário ativo;
a API mantém essa regra em alterações simultâneas. Mudanças de contas fora desta
API continuam sujeitas ao limite já descrito no planejamento.

A suíte completa aprovou 194 testes em 19,78 s no PostgreSQL separado de testes:
97 anteriores e 97 novos, incluindo dez testes com transações e conexões reais
concorrentes. Esses testes comprovam a espera pelo bloqueio compartilhado da
organização, a preservação de um proprietário em rebaixamentos/remoções
simultâneos, a rejeição de inclusão duplicada concorrente e a nova autorização
após revogação de acesso durante a espera. Os testes de autenticação anteriores
permanecem aprovados. Ruff, formatação, dependências, Django e a verificação de
migrações passaram; nenhuma mudança de modelo foi necessária.

A auditoria somente leitura do banco de desenvolvimento encontrou zero
organizações e zero sem proprietário ativo. Segredos, configurações do banco,
modelos e migrações existentes permanecem preservados. O
[CI #19](https://github.com/danielbramos4/taskflow-backend/actions/runs/40377163078)
aprovou os 194 testes no PostgreSQL 17; a Entrega 3 foi integrada pelo PR #4.

## Encerramento da Entrega 4 — 26/10/2026

O README contém o contrato disponível, exemplos de entrada, campos de resposta,
paginação, erros e um roteiro completo com três contas de desenvolvimento:
criação de organização, inclusão e leitura por membro, rejeição de escrita,
transferência de propriedade, proteção do último proprietário e revogação de
acesso. O roteiro também confere que a conta removida mantém login, perfil e
refresh JWT, sem recuperar o vínculo excluído.

O novo teste integrado `tests/organizations/test_sprint2_flow.py` percorre esse
ciclo usando os endpoints reais de login e refresh e preserva uma organização
externa. A suíte completa aprovou **195 testes em 21,88 s** no PostgreSQL separado
de testes: os 194 anteriores e esse aceite integrado. Inclui os 11 testes da
Sprint 1 e os dez cenários de concorrência real da Entrega 3, sem testes ignorados.
Ruff, formatação, `pip check`, Django e `makemigrations --check --dry-run`
passaram. A inspeção das migrações aplicadas encontrou zero pendências.

| Critério revisado | Evidência automatizada |
| --- | --- |
| Criação e proprietário atômicos | `test_api.py`: criação e rollback de falha do vínculo. |
| Isolamento nas listagens e detalhes | `test_api.py`, `test_detail_api.py` e `test_membership_api.py`: usuários externos, superusuários e IDs de outras organizações. |
| Leitura e escrita por papel da organização | `test_detail_api.py` e `test_membership_api.py`: membro recebe 403; proprietário de A não administra B como membro. |
| Identidade, vínculo e papel não forjáveis | Testes de campos controlados pelo servidor, troca de usuário/organização e consultas que tentam ampliar acesso. |
| Proprietário ativo preservado | `test_membership_api.py` e `test_membership_concurrency.py`: último proprietário, substituto inativo e saídas simultâneas. |
| Remoção preserva conta e dados externos | `test_membership_api.py` e `test_sprint2_flow.py`: remoção só do vínculo, perfil/refresh funcionais e outra equipe intacta. |
| Revogação sem renovar JWT | Testes de consulta/edição após mudança de papel ou remoção, incluindo revogação enquanto uma escrita espera pelo bloqueio. |
| Paginação e respostas de erro | Testes de ordenação estável, contagem por organização, páginas inválidas, dados inválidos e métodos não oferecidos. |
| Compatibilidade da fundação e fluxo completo | `tests/accounts/test_auth.py`, `test_models.py` e `test_sprint2_flow.py`, executados com toda a suíte. |

As três entregas funcionais foram integradas após seus CIs aprovados. O PR de
encerramento registra a execução remota do commit final e é integrado somente
com os checks aprovados; o CI da `main` confirma o resultado após a integração.
Não houve mudanças de código da aplicação, modelos, migrações, dependências ou
infraestrutura nesta entrega. Os arquivos existentes fora da documentação foram
comparados por hash e preservados, inclusive `.env` e configurações do banco.
A auditoria de desenvolvimento encontrou zero organizações e nenhuma sem
proprietário ativo. Nenhuma correção de dados ou remoção de volume foi necessária.

Todos os critérios do escopo da Sprint 2 estão atendidos. As limitações
administrativas fora desta API continuam documentadas em “Limites desta sprint”.

## Referências técnicas

- [Permissões no Django REST Framework](https://www.django-rest-framework.org/api-guide/permissions/).
- [Filtragem por usuário no Django REST Framework](https://www.django-rest-framework.org/api-guide/filtering/).
- [Transações no Django 5.2](https://docs.djangoproject.com/en/5.2/topics/db/transactions/).
- [Bloqueio de linhas com select_for_update no Django 5.2](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update).
