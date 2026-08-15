# Dashboard de Performance Comercial — MGCred

Dashboard interno para acompanhamento da operação comercial da MGCred.
Consolida produção, pontuação, metas, pipeline e desempenho de múltiplas
equipes em uma interface Streamlit conectada ao Supabase.

O produto atende da visão executiva ao acompanhamento individual, com
recortes por região, loja, supervisor e consultor.

## Principais recursos

- KPIs de produção, pontuação, metas, ritmo por dia útil e projeção de
  fechamento.
- Análises por produto, região, loja e consultor, com comparativos mensais e
  anuais.
- Rankings, distribuição do mix, consultores sem produção e exportação CSV.
- Acompanhamento de contratos pagos, em análise e cancelados, com drill-downs.
- Gestão por critérios combinados, metas relativas, aceleradores, períodos
  personalizados e presets compartilháveis.
- Indicadores específicos de Reconquista, Cobrança Consignável, emissão e
  seguros.
- Monitoramento de Pagamentos Online.
- Assistente de IA baseado nos KPIs validados do dashboard, em rollout beta
  para administradores.

As regras detalhadas de pontuação e contabilização dos produtos estão em
[`docs/agents/business-rules.md`](docs/agents/business-rules.md).

## Arquitetura

[`app.py`](app.py) é o único entrypoint. Ele autentica o usuário, carrega o
período, aplica as restrições de acesso e despacha as páginas do dashboard.
A lógica fica organizada por responsabilidade:

```text
app.py                         # orquestrador Streamlit
src/dashboard/
  loaders.py                  # Supabase e cache atual/histórico
  kpis/                       # cálculos de negócio
  tabs/                       # páginas analíticas
  ui/                         # cards, gráficos, tema e sidebar
  pages/                      # páginas e drill-downs
  chat_ia/                    # tools e orquestração do assistente
database/migrations/          # evolução do schema Supabase
tests/                        # testes automatizados
```

Os dados são consultados diretamente no Supabase por views e RPCs. O mês
corrente usa cache de curta duração; períodos históricos usam cache mais
longo. O antigo pipeline de relatórios Excel/PDF foi removido.

Consulte a [arquitetura completa](docs/agents/architecture.md) e o
[padrão da camada de dados](docs/agents/data-layer.md).

## Acesso e segurança

O dashboard exige autenticação e aplica acesso fail-closed conforme cinco
perfis:

| Perfil | Escopo |
|---|---|
| `admin` | Visão global, configurações e simulação de outros perfis |
| `gestor` | Visão consolidada da operação |
| `gerente_comercial` | Regiões atribuídas |
| `supervisor` | Lojas atribuídas |
| `consultor` | Produção individual |

A ordem de aplicação das restrições é parte do contrato de segurança.
Veja [`docs/agents/rls.md`](docs/agents/rls.md).

## Executando localmente

Requisitos: Python 3.11+ e credenciais de acesso ao Supabase.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Preencha SUPABASE_URL e SUPABASE_KEY no .env

.venv/bin/streamlit run app.py
```

O dashboard fica disponível, por padrão, em `http://localhost:8501`.

## Stack

O baseline atual está definido em [`requirements.txt`](requirements.txt):

- Streamlit 1.61.1 e streamlit-antd-components ≥ 0.3.2
- Pandas 3.0.5 e NumPy 2.5.1
- Plotly 6.9.0
- Supabase Python 2.31.0
- Anthropic ≥ 0.70.0 e OpenAI ≥ 1.109.1 para o Assistente IA
- bcrypt ≥ 5.0.0 e python-dotenv 1.2.2

## Qualidade

Use sempre os binários da `.venv`:

```bash
.venv/bin/python -m pytest tests/
.venv/bin/ruff check src/ app.py
```

A suíte cobre KPIs, regras de produto, loaders, RLS, permissões, componentes
de UI, Gestão e ferramentas do Assistente IA.

## Documentação e agentes

Antes de contribuir, leia [`AGENTS.md`](AGENTS.md) e o índice em
[`docs/agents/README.md`](docs/agents/README.md). Essa pasta é a fonte
canônica de arquitetura, regras de negócio, convenções e progresso.

O desenvolvimento assistido opera com Claude como executor/orquestrador,
Devin como canal paralelo do dashboard quando disponível e Codex na revisão
de decisões. O contrato está em
[`docs/agents/collaboration.md`](docs/agents/collaboration.md).

## Licença

Uso interno da empresa.
