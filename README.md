# Dashboard de Performance Comercial — MGCred

Dashboard interativo de vendas em Streamlit, alimentado **diretamente pelo
Supabase** (PostgreSQL). Consolida pontuação, metas, análises por
região/loja/consultor e KPIs de performance, com autenticação e
Row-Level Security por perfil.

> **Entrypoint único:** [`app.py`](app.py) na raiz. Toda a lógica vive em
> [`src/`](src/). O projeto não gera mais relatórios Excel/PDF — esse
> pipeline foi descontinuado; os dados são lidos do Supabase em tempo real.

## 📋 Funcionalidades

- **Dashboard interativo** com Streamlit + streamlit-antd-components
- **Sistema de pontuação** por produto (`pontos = VALOR × PTS`) e metas
- **Análises comparativas** entre regiões, lojas e consultores
- **KPIs de performance**, projeção de fechamento e prioridades de ação
- **Autenticação e Row-Level Security (RLS)** por perfil

## 📚 Documentação

O conhecimento de projeto (arquitetura, regras de negócio, convenções) é
mantido em **[`docs/agents/`](docs/agents/README.md)** — fonte única de
verdade. Comece por:

- [`AGENTS.md`](AGENTS.md) — princípios inegociáveis e ponto de entrada
- [`docs/agents/architecture.md`](docs/agents/architecture.md) — entrypoint, árvore, banco
- [`docs/agents/business-rules.md`](docs/agents/business-rules.md) — regras de pontuação, cartão, seguros, metas
- [`docs/agents/rls.md`](docs/agents/rls.md) — ordem de RLS e hierarquia de perfis

## 🚀 Instalação

Pré-requisitos: Python 3.11+.

```bash
# 1. Ambiente virtual
python -m venv .venv
source .venv/bin/activate          # Linux/Mac

# 2. Dependências
pip install -r requirements.txt    # requirements-dev.txt para dev (ruff, pytest)

# 3. Variáveis de ambiente
cp .env.example .env
# Edite .env e defina ao menos SUPABASE_URL e SUPABASE_KEY
```

## 📊 Como Usar

```bash
streamlit run app.py
```

O dashboard fica disponível em `http://localhost:8501`.

## 🗂️ Estrutura (resumo)

```
app.py                  ← entrypoint único (orquestrador)
src/
  config/               ← supabase_client, settings (constantes de negócio)
  shared/               ← dias_uteis
  dashboard/
    auth, rls, permissions, loaders, user_mgmt, feriados_mgmt
    kpis/  tabs/  ui/  pages/  components/
configuracao/           ← planilhas auxiliares (HC, lojas, supervisores)
database/migrations/    ← migrations SQL numeradas
assets/                 ← logotipo, design system (CSS)
tests/                  ← suíte pytest
```

Árvore completa e fluxo de carregamento em
[`docs/agents/architecture.md`](docs/agents/architecture.md).

## 🔐 Autenticação e Controle de Acesso

- Login obrigatório; usuários ficam na tabela `usuarios` do **Supabase**
  (senhas com hash bcrypt). Gerenciamento via página de admin
  ([`user_mgmt.py`](src/dashboard/user_mgmt.py)).
- Acesso filtrado por **Row-Level Security** conforme o perfil
  (`admin`, `gerente_comercial`, `supervisor`, `consultor`). `admin` pode
  simular outros perfis via "Visualizar Como".
- Detalhes e ordem obrigatória de aplicação em
  [`docs/agents/rls.md`](docs/agents/rls.md).

Seed inicial de admin: [`scripts/seed_admin.py`](scripts/seed_admin.py).

## 🛠️ Tecnologias

- **Python 3.11+**
- **Streamlit 1.35+** + **streamlit-antd-components** — frontend
- **Supabase (PostgreSQL)** — fonte de dados (views `v_*` e RPCs)
- **Pandas 2.2+** / **NumPy 1.26+** — manipulação de dados
- **Plotly 5.20+** — gráficos interativos
- **openpyxl** — leitura das planilhas auxiliares de `configuracao/`
- **bcrypt** — hash de senhas
- **ruff** / **pytest** — lint e testes

## 🧪 Testes e Lint

```bash
pytest tests/
ruff check src/ app.py
```

## 👥 Contribuindo

1. Leia [`AGENTS.md`](AGENTS.md) e o doc de [`docs/agents/`](docs/agents/README.md) da área que vai tocar.
2. Siga PEP 8; docstrings em português.
3. Adicione testes para novas funcionalidades e rode `ruff check` antes de abrir PR.

## 📄 Licença

Uso interno da empresa.
