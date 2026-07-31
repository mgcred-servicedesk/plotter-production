# Convenções

## Idioma

- **Código** (variáveis, funções, classes): inglês.
- **Docstrings, comentários, documentação**: português do Brasil.
- **Dados**: PT-BR. Atenção a: vírgula decimal (`1.234,56`), prefixo `R$`,
  acentos em colunas (`REGIÃO`, `LOJA`), datas `dd/mm/yyyy`.

## Estilo (PEP 8)

- `snake_case` para variáveis e funções.
- `CamelCase` para classes.
- `UPPER_CASE_WITH_UNDERSCORES` para constantes.
- 4 espaços; linha máx. 79 chars (72 para docstrings/comentários).
- Linhas em branco entre definições top-level.
- Type hints onde prático; docstrings em funções públicas.

### Lint — `ruff.toml` fixa o conjunto de regras

`ruff.toml` declara `[lint] select = ["E4", "E7", "E9", "F"]`. Isso
**não** é preferência estética: é o que desacopla o gate de lint da
versão da ferramenta. Sem `select` explícito, o `ruff` usa o default
dele — e quando o default mudou (0.15 → 0.16), o mesmo código passou a
acusar 635 violações sem que uma linha tivesse mudado.

Consequências práticas:

- `ruff check src/ app.py` significa a mesma coisa antes e depois de um
  upgrade do ruff. Subir a ferramenta deixa de ser mudança de escopo
  disfarçada.
- Adotar regra nova (`UP*`, `C408`, `BLE001`, `DTZ005`, `SIM*`, …) é
  tarefa deliberada: acrescente ao `select` **e** trate as violações no
  mesmo trabalho. Nunca alargue o `select` de passagem.
- Anotações de tipo antigas (`Dict`, `List`, `Optional[X]`) continuam
  aceitas — `UP006`/`UP045` estão fora do `select` por decisão, não por
  esquecimento. São ~470 ocorrências no código.

## Nomenclatura por sufixo

| Sufixo | Significado |
|---|---|
| `df_f` | DataFrame filtrado (após filtro de região) |
| `df_sup` / `df_sup_f` | DataFrame de supervisores |
| `df_metas_f` | DataFrame de metas filtrado |
| `df_metas_prod_f` | DataFrame de metas por produto filtrado |
| `_render_*` | função Streamlit de render (side effects) |
| `calcular_*` | função pura (retorna DataFrame ou dict) |
| `criar_grafico_*` | retorna `fig` Plotly |
| `carregar_*` | query Supabase (wrapper público com branch `_atual`/`_historico`) |
| `_fetch_*` | query raw (sem cache) |
| `_eh_mes_atual` | branch de estratégia de cache |

## Formatters PT-BR

```python
def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_numero(valor):
    return f"{valor:,.0f}".replace(",", ".")

def formatar_percentual(valor):
    return f"{valor:.1f}%"
```

## Width API

Streamlit ≥ 1.35 deprecia `use_container_width=True` em favor de
`width="stretch"`. Aplica a `st.plotly_chart`, `st.dataframe`, `st.button`,
`st.image`.

```python
st.plotly_chart(fig, width="stretch")
st.dataframe(df, width="stretch", hide_index=True)
st.button("Sair", width="stretch")
```

**Exceção**: componentes `sac.*` (streamlit-antd-components) ainda usam
`use_container_width=` — é biblioteca diferente.

## Chart template (Plotly)

Todo gráfico passa por `_template()` e `_aplicar()`:

```python
def _template():
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor":  "rgba(0,0,0,0)",
        "font": dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", size=12),
        "legend": dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                       font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
        "margin": dict(l=60, r=30, t=60, b=50),
        "hoverlabel": dict(bgcolor="rgba(30,30,46,0.9)", font_color="#fff", font_size=12,
                           bordercolor="rgba(255,255,255,0.1)"),
    }

def _aplicar(fig, t):
    fig.update_layout(paper_bgcolor=t["paper_bgcolor"], plot_bgcolor=t["plot_bgcolor"],
                      font=t["font"], legend=t["legend"], hoverlabel=t["hoverlabel"])
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.1)", zerolinecolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)", zerolinecolor="rgba(128,128,128,0.15)")
    return fig
```

Fundos transparentes são **obrigatórios** — o tema (`assets/dashboard_style.css`)
usa CSS custom properties + localStorage para claro/escuro; charts precisam
adaptar automaticamente.

## Paleta de cores

```python
CHART_COLORS = {
    "primary":      "#2563eb",
    "primary_dark": "#1e40af",
    "secondary":    "#0d9488",
    "success":      "#059669",  # >= 100% da meta
    "danger":       "#dc2626",  # < 100% da meta
    "warning":      "#d97706",
    "neutral":      "#64748b",
    "purple":       "#7c3aed",
    "rose":         "#e11d48",
    "seq": ["#2563eb","#0d9488","#7c3aed","#d97706","#059669","#e11d48","#64748b","#0284c7"],
}
```

### Regra de color-coding de performance

```python
cores = df["% Atingimento"].apply(
    lambda x: CHART_COLORS["success"] if x >= 100 else CHART_COLORS["danger"]
)
```

## Princípios de design de dashboard

- Máximo **5–10 KPIs por tela**. Se tudo é destaque, nada é.
- Todo KPI precisa de **contexto** (delta, meta, tooltip `help=`).
- Tipo de gráfico por objetivo: linha (tendência), barra (comparação),
  funil (conversão), pizza (≤5 categorias), scatter (correlação).
- Métricas **acionáveis** (conversão, CAC, ROI, % atingimento) — não vanity.
- `layout="wide"` obrigatório; filtros na sidebar.
- No máx. 3 tipos de gráfico por página.
- Sem 3D; sem paletas arcoíris; sem widgets decorativos.

### Estrutura narrativa (reforma)

A tela segue uma ordem de altitude decrescente — de resultado para ação:

1. **Onde estamos** — resumo executivo + 3 KPIs dominantes (realizado, % meta, gap).
2. **Para onde vamos** — ritmo atual vs. necessário e projeção de fechamento.
3. **Onde agir** — prioridades de ação (produtos/regiões/consultores críticos).
4. **Exploração** — tabs com tabelas e gráficos detalhados.

Cor comunica **status** (verde ≥ meta, amarelo atenção, vermelho crítico,
azul/cinza neutro), nunca decoração. Implementado em
[`ui/resumo_executivo.py`](../../src/dashboard/ui/resumo_executivo.py),
[`ui/prioridades_acao.py`](../../src/dashboard/ui/prioridades_acao.py) e
[`ui/kpi_cards_reforma.py`](../../src/dashboard/ui/kpi_cards_reforma.py).

## Pandas/NumPy

- Vetorizar > `apply()` > loops.
- Método chaining (`.query().assign().groupby().agg()`) para legibilidade.
- Divisão segura: `df["pct"] = df["part"] / df["total"].replace(0, np.nan) * 100`.
- Após slicing: `sub = df[mask].copy()` (evita `SettingWithCopyWarning`).
- Datas: `pd.to_datetime(..., errors="coerce")`.
