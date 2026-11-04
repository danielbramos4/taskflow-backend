# Interface web e publicação do TaskFlow

Com o PostgreSQL local disponível e o servidor Django iniciado, abra
`http://127.0.0.1:8000/`. Entre com uma conta existente do TaskFlow. O painel
lista organizações e projetos disponíveis para essa conta. Proprietários podem
criar organizações e projetos, adicionar membros por ID, criar e editar tarefas
com responsável e prazo, alterar o estado, arquivar e restaurar projetos.
Membros consultam as tarefas e podem filtrar por responsável e prazo.

O ID da conta aparece no topo após entrar. Contas normais são cadastradas pelo
administrador em `/admin/`; o painel de trabalho fica na raiz `/`.
A API JWT continua disponível no mesmo endereço em `/api/v1/`.

## Publicar uma demonstração online no Render

1. Faça login no [Render](https://dashboard.render.com/) e abra **New → Blueprint**.
2. Conecte `danielbramos4/taskflow-backend`, selecione `main` e confira os serviços
   descritos em `render.yaml`: um serviço web Docker e um PostgreSQL separado.
3. Defina `TASKFLOW_ADMIN_PASSWORD` no próprio Render com uma senha nova e forte,
   de pelo menos 12 caracteres. O usuário inicial é `taskflow_admin`. A chave Django
   e a conexão com o banco são fornecidas pelo Render. Não use o `.env` local.
4. Aplique o Blueprint e aguarde o serviço ficar saudável. Abra o endereço
   `https://…onrender.com` mostrado pelo Render e entre com o administrador inicial.
5. Após confirmar o primeiro login, remova `TASKFLOW_ADMIN_PASSWORD` das variáveis
   do serviço. A conta já criada permanece e o startup não redefine sua senha.
   Em `/admin/`, você pode criar contas normais para a equipe.

O banco hospedado começa vazio. O Docker aplica as migrações e coleta CSS e JS
na inicialização. `/health/` indica a disponibilidade do banco; as rotas de
trabalho exigem autenticação. A configuração do Render usa HTTPS e cookies
seguros. As credenciais e registros do banco local não são enviados.

O Blueprint usa a modalidade gratuita para demonstração. Nela o serviço pode
adormecer e o [PostgreSQL gratuito expira após 30 dias](https://render.com/docs/free).
Para manter dados por mais tempo, escolha um plano durável e configure backups.
Veja também o [guia oficial do Render para Django](https://render.com/docs/deploy-django).
