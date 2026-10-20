# Sprint 1 — fundação do TaskFlow

## Escopo

Preparar o ambiente de desenvolvimento, banco de dados, modelos de usuários e
organizações, autenticação JWT, testes e verificações de qualidade. A API de
organizações não faz parte desta implementação da fundação.

## Auditoria em 20/10/2026

| Item do planejamento | Evidência | Situação |
| --- | --- | --- |
| Python, Git, Docker, VS Code e Windows | Python 3.12.10; Git 2.52.0.windows.1; Docker 29.4.3; Compose 5.1.3; VS Code 1.142.0; Windows 11 | Verificado |
| Repositório GitHub e diretórios | `origin` aponta para `danielbramos4/taskflow-backend`; `apps/`, `config/`, `tests/` | Implementado |
| Ambiente virtual e projeto Django | `.venv`; Django 5.2.18; `manage.py` | Implementado |
| PostgreSQL e Docker Compose | PostgreSQL 17; porta local 5434; volume persistente; conexão Django validada | Implementado |
| Usuários e organizações | `User`, `Organization`, `Membership`; vínculo único por usuário/organização e papéis owner/member | Implementado |
| JWT e permissões | Login, refresh e `/me/`; autenticação obrigatória nos endpoints protegidos | Implementado para os endpoints existentes |
| Pytest | 6 testes de autenticação e 5 testes de modelos de organizações | 11 testes aprovados |
| Ruff e GitHub Actions | `pyproject.toml`, dependências versionadas e `.github/workflows/ci.yml` | Configurado localmente; execução remota pendente |
| Critérios de aceitação | Checklist abaixo | Validação local concluída; CI remota pendente |

## Critérios de aceitação da fundação

Estes critérios registram a base verificável a partir do planejamento informado.
Requisitos adicionais de produto devem ser acrescentados antes de ampliar o escopo.

- [x] Ferramentas de desenvolvimento disponíveis no Windows.
- [x] Repositório Git local inicializado e remoto GitHub definido.
- [x] Ambiente virtual e projeto Django funcionais.
- [x] Dependências de execução e desenvolvimento declaradas com versões fixadas.
- [x] `.env` fora do versionamento e `.env.example` disponível como referência.
- [x] Precedência ambiente do processo > `.env` explícita e documentada.
- [x] PostgreSQL acessível pelo Django e com armazenamento persistente.
- [x] Migrações existentes aplicadas e modelos sem migrações pendentes.
- [x] Usuários podem pertencer a várias organizações; organizações podem ter vários membros.
- [x] O banco rejeita vínculos duplicados entre o mesmo usuário e organização.
- [x] Login válido emite access/refresh e senha incorreta recebe 401.
- [x] Refresh válido emite um novo access token.
- [x] `/me/` retorna o próprio usuário e rejeita ausência de token ou token inválido.
- [x] `pip check`, Ruff, Django e os 11 testes passam localmente.
- [x] Workflow preparado com banco isolado e sem segredos locais.
- [ ] Publicar as alterações e confirmar uma execução bem-sucedida no GitHub Actions.

Os papéis owner/member estão modelados; regras de autorização para futuras
operações sobre organizações ainda precisam ser definidas e testadas junto com
esses endpoints. A configuração atual garante autenticação nos endpoints existentes.

## Comandos de aceitação

Na raiz do repositório, com o PostgreSQL disponível:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py showmigrations --plan
.\.venv\Scripts\python.exe -m pytest --reuse-db -v --tb=short
```

`--reuse-db` mantém o banco separado de testes. As verificações locais não alteram
a senha do PostgreSQL, não removem volumes e não implementam funcionalidades de
uma sprint futura. O comando de migração do CI atua apenas no banco temporário
criado pelo próprio workflow.

## Pendência de entrega

A presença do workflow local não comprova uma execução no GitHub. A validação
remota deve ser registrada somente depois de uma execução verde na aba Actions.
As alterações de credenciais e os testes de autenticação que já estavam no diretório
de trabalho devem ser incluídos na revisão da entrega, preservando o `.env` local.
