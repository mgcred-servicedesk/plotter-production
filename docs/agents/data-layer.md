# Camada de Dados — Supabase

## Cliente

```python
from src.config.supabase_client import get_supabase_client

def _sb():
    return get_supabase_client()
```

## Views e RPCs (preferir sobre joins na aplicação)

| Objeto | Tipo | Uso |
|---|---|---|
| `v_contratos_dashboard` | view | contratos pagos com joins + flags já resolvidos + `created_at` (rótulo "Atualizado em" no status bar) |
| `v_contratos_cancelados` | view | contratos cancelados agregados |
| `obter_cancelados_classificados(p_mes, p_ano)` | RPC | cancelados (30 dias) + coluna `classificacao` (redigitada/recuperada/liquido); matching por nome+categoria no banco (ver [business-rules.md](business-rules.md)) |
| `obter_pontuacao_periodo(p_mes, p_ano)` | RPC | pontuação final por consultor/loja/região |

> **Depreciado:** `obter_contratos_cancelados(p_mes, p_ano)` (migration 003)
> foi substituída por `obter_cancelados_classificados`. Mantida no banco por
> ora; **remover em migration futura** (`DROP FUNCTION`) quando confirmado que
> nada mais a consome.

Migrações em `database/migrations/` (numeradas sequencialmente a partir de 001). Nunca consultar
`contratos` diretamente quando uma view cobre o caso — a view já
encapsula joins, filtros de status e resolução de `grupo_dashboard`/`grupo_meta`.

## Loaders (`src/dashboard/loaders.py`)

Todas as funções `carregar_*` consumidas pelo `app.py` vivem em um
único módulo `src/dashboard/loaders.py`. Cada uma segue o padrão
descrito abaixo (`_fetch_*` + `_*_atual` + `_*_historico` + wrapper
público). Principais:

| Função | Retorno | Cache `_atual` / `_historico` |
|---|---|---|
| `consolidar_dados(mes, ano)` | `(df, df_metas, df_sup)` pagos | 30 min / 24 h |
| `carregar_contratos_em_analise(mes, ano)` | DataFrame pipeline | 30 min / 24 h |
| `carregar_contratos_cancelados(mes, ano)` | DataFrame cancelados | 30 min / 24 h |
| `carregar_metas_produto(mes, ano)` | DataFrame metas por produto | 6 h / 24 h |
| `carregar_metas_consultor(mes, ano, loja)` | dict `{meta_prata, meta_ouro}` | 6 h / 24 h |
| `carregar_pontuacao_efetiva(mes, ano)` | DataFrame via RPC | 6 h / 24 h |
| `carregar_categorias()` | DataFrame estático | 24 h |
| `carregar_lojas_regioes()` | `(lojas, regioes)` | 24 h |
| `carregar_consultores_cadastro()` | lista de nomes | 24 h |
| `carregar_ultimo_periodo()` | `{mes, ano}` mais recente | 24 h |

### Exemplo — view (paginada por keyset)

```python
all_data = _paginar_keyset(
    lambda: (
        _sb()
        .from_("v_contratos_dashboard")
        .select("*")
        .eq("periodo_id", periodo["id"])
        .order("id")
        .limit(_PAGE_SIZE)
    ),
    "id",
)
```

### Exemplo — RPC

```python
resp = (
    _sb()
    .rpc("obter_pontuacao_periodo", {"p_mes": mes, "p_ano": ano})
    .execute()
)
df = pd.DataFrame(resp.data or [])
```

RPC com resultset potencialmente **> 1000 linhas**: nunca paginar com
`.range()` — o PostgREST reexecuta a função inteira a cada página.
Padrão do projeto: variante `*_json` (migration 057) que agrega o
resultado da função original em JSON único (`json_agg` +
`COALESCE('[]')`) e é chamada **uma vez**, sem `.range()`/`.limit()`:

```python
resp = _sb().rpc("obter_cancelados_classificados_json", params).execute()
all_data = resp.data or []   # lista já parseada pelo postgrest-py
```

As funções originais (`RETURNS TABLE`) são mantidas para debug/uso
manual no SQL Editor.

## Paginação

Supabase limita respostas a 1000 linhas. O padrão canônico é **keyset
pagination** via helper `_paginar_keyset` (loaders.py) — cursor
`WHERE chave > último ORDER BY chave LIMIT N`:

```python
_PAGE_SIZE = 1000

all_data = _paginar_keyset(
    lambda: (
        _sb()
        .from_("v_reconquista")
        .select("*")
        .eq("ref_ano", ref_ano)
        .eq("ref_mes", ref_mes)
        .order("co_adesao")
        .limit(_PAGE_SIZE)
    ),
    "co_adesao",
)
```

Regras:

- A `coluna_chave` deve ser **única** (PK ou UNIQUE) — chave repetida
  faz linhas serem puladas entre páginas. Chaves em uso:
  `v_contratos_dashboard.id` (PK), `v_pagamentos_online_efetivo.proposta`
  (PK), `v_reconquista.co_adesao` (UNIQUE).
- A query base deve trazer `.order(coluna_chave)` e `.limit(_PAGE_SIZE)`.
- **OFFSET é proibido em novos loaders**: cada página com OFFSET
  reordena o resultset inteiro (sort que spilla para temp files —
  dreno do Disk IO Budget, ver migration 054 e progress doc
  2026-07-08). A exigência de ordenação estável do commit `705885b`
  continua valendo — agora garantida pela chave única.

## Estratégia de cache — `_atual` vs `_historico`

Mês corrente é volátil; meses passados são imutáveis. Todo loader de
dados quebra em **três funções**:

1. **Wrapper público** `carregar_*` — faz branch com `_eh_mes_atual()`.
2. **`_fetch_*`** — executa a query (sem cache).
3. **Dois wrappers cacheados** `_*_atual` (TTL curto) e `_*_historico` (TTL longo).

```python
def _eh_mes_atual(mes: int, ano: int) -> bool:
    hoje = datetime.now()
    return mes == hoje.month and ano == hoje.year


def carregar_contratos_pagos(mes: int, ano: int) -> pd.DataFrame:
    """TTL real: 30min para mes corrente, 24h para historico."""
    if _eh_mes_atual(mes, ano):
        return _contratos_pagos_atual(mes, ano)
    return _contratos_pagos_historico(mes, ano)


def _fetch_contratos_pagos(mes: int, ano: int) -> pd.DataFrame:
    """Executa a query sem cache."""
    ...


@st.cache_data(ttl=1800)   # 30 min
def _contratos_pagos_atual(mes: int, ano: int) -> pd.DataFrame:
    return _fetch_contratos_pagos(mes, ano)


@st.cache_data(ttl=86400)  # 24 h
def _contratos_pagos_historico(mes: int, ano: int) -> pd.DataFrame:
    return _fetch_contratos_pagos(mes, ano)
```

### Convenções de TTL

| Tipo de dado | `_atual` | `_historico` |
|---|---|---|
| Contratos (pagos, em análise, cancelados) | 1800s (30 min) | 86400s (24 h) |
| Pontuação (RPC) | 21600s (6 h) | 86400s (24 h) |
| Metas / Metas por produto | 21600s (6 h) | 86400s (24 h) |
| Categorias, Períodos, Feriados | 86400s (24 h) | — (imutável) |

Config estática sem `mes`/`ano` pode usar um único `@st.cache_data(ttl=86400)`.

## Colunas padronizadas após `_fetch_*`

| Coluna | Tipo | Notas |
|---|---|---|
| `LOJA` | str | uppercase |
| `REGIAO` | str | uppercase |
| `CONSULTOR` | str | uppercase |
| `TIPO_PRODUTO` | str | uppercase |
| `TIPO OPER.` | str | de `tipo_operacao` — identifica BMG MED, Seguro, etc. |
| `SUBTIPO` | str | uppercase; `SUPER CONTA` é subtipo de CNC |
| `VALOR` | float | sempre `float(c.get("valor", 0))` |
| `pontos` | float | lowercase — campo computado |
| `DATA` | datetime | `pd.to_datetime(..., errors="coerce")` |
| `CREATED_AT` | datetime (UTC) | `pd.to_datetime(..., utc=True)`; usado pelo status bar para "Atualizado em" (convertido para `America/Sao_Paulo` na exibição) |
| `grupo_dashboard` | str \| None | da view / `categorias_produto` |
| `grupo_meta` | str \| None | idem |
| `conta_valor` | bool | se False → `VALOR = 0` no agregado |
| `conta_pontuacao` | bool | se False → `pontos = 0` |

## Dias úteis e feriados

**Nunca** calcular dias úteis inline. Sempre:

```python
from src.shared.dias_uteis import calcular_dias_uteis

du_total, du_dec, du_rest = calcular_dias_uteis(ano, mes, dia_atual)
```

O módulo carrega feriados da tabela `feriados` (cache 24h) e exclui
sábados/domingos. CRUD de feriados vive em `src/dashboard/feriados_mgmt.py`
(página admin).
