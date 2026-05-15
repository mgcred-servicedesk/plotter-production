"""
Graficos Plotly do dashboard.

Usa ``chart_theme``/``CHART_COLORS`` de ``ui.theme`` para
manter coerencia visual entre tema claro e escuro.
``_template``/``_aplicar`` sao helpers internos usados pelas
funcoes publicas ``criar_grafico_*``/``criar_heatmap_*``.
"""

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.dashboard.formatters import formatar_moeda, formatar_numero
from src.dashboard.ui.theme import CHART_COLORS, chart_theme


def _template():
    """Configuracao base para graficos Plotly."""
    ct = chart_theme()
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": dict(
            family=(
                "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            ),
            size=12,
            color=ct["text"],
        ),
        "title_font": dict(size=16, weight=700),
        "legend": dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color=ct["text"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        "margin": dict(l=60, r=30, t=60, b=50),
        "hoverlabel": dict(
            bgcolor=ct["tooltip_bg"],
            font_color=ct["tooltip_text"],
            font_size=12,
            bordercolor=ct["border"],
        ),
    }


def _aplicar(fig, t):
    """Aplica template a um grafico."""
    ct = chart_theme()
    text_color = ct["text"]
    fig.update_layout(
        paper_bgcolor=t["paper_bgcolor"],
        plot_bgcolor=t["plot_bgcolor"],
        font=t["font"],
        legend=t["legend"],
        hoverlabel=t["hoverlabel"],
    )
    # subplot_titles criam annotations — forcar cor do texto
    for ann in fig.layout.annotations:
        ann.font.color = text_color
    fig.update_xaxes(
        gridcolor=ct["grid"],
        zerolinecolor=ct["grid_zero"],
        tickfont_color=text_color,
        title_font_color=text_color,
    )
    fig.update_yaxes(
        gridcolor=ct["grid"],
        zerolinecolor=ct["grid_zero"],
        tickfont_color=text_color,
        title_font_color=text_color,
    )
    return fig


def _proximo_du(d: date, feriados: frozenset) -> date:
    """Avança d para o próximo dia útil (seg-sex, não feriado)."""
    while d.weekday() >= 5 or d in feriados:
        d += timedelta(days=1)
    return d


def _serie_acumulado_por_du(
    df: pd.DataFrame,
    feriados: Optional[set] = None,
) -> tuple[list[int], list[float]]:
    """Agrega VALOR por dia útil e retorna (lista_du, lista_acumulado).

    Datas em fins de semana ou feriados são atribuídas ao próximo DU,
    preservando o volume total e garantindo que o eixo X tenha exatamente
    os DU reais do mês (ex.: 19 em abril com 3 feriados).
    """
    if df is None or df.empty or "DATA" not in df.columns or "VALOR" not in df.columns:
        return [], []
    _fer = frozenset(feriados) if feriados else frozenset()
    datas = pd.to_datetime(df["DATA"], errors="coerce").dt.date
    datas_ajustadas = datas.apply(lambda d: _proximo_du(d, _fer) if pd.notna(d) else None)
    diario = (
        df.assign(DATA=datas_ajustadas)[df["VALOR"] > 0]
        .dropna(subset=["DATA"])
        .groupby("DATA")["VALOR"]
        .sum()
        .sort_index()
        .cumsum()
    )
    dus = list(range(1, len(diario) + 1))
    return dus, diario.tolist()


def criar_grafico_produtos(
    df_produtos,
    df_atual: Optional[pd.DataFrame] = None,
    df_ant: Optional[pd.DataFrame] = None,
    feriados_atual: Optional[set] = None,
    feriados_ant: Optional[set] = None,
):
    """Grafico completo de produtos."""
    t = _template()

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Realizado vs Meta",
            "Acumulado do Mes — Atual vs Anterior",
            "Projecao vs Meta",
            "",
        ),
        specs=[
            [{"type": "bar"}, {"type": "scatter", "rowspan": 2}],
            [{"type": "scatter"}, None],
        ],
        vertical_spacing=0.14,
        horizontal_spacing=0.10,
    )

    fig.add_trace(
        go.Bar(
            name="Realizado",
            x=df_produtos["Produto"],
            y=df_produtos["Valor"],
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
            text=df_produtos["Valor"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            name="Meta",
            x=df_produtos["Produto"],
            y=df_produtos["Meta"],
            marker_color=CHART_COLORS["primary_dark"],
            marker_line=dict(width=0),
            text=df_produtos["Meta"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            name="Projecao",
            x=df_produtos["Produto"],
            y=df_produtos["Projeção"],
            mode="lines+markers",
            marker=dict(
                size=10,
                color=CHART_COLORS["rose"],
                line=dict(width=2, color=chart_theme()["bg"]),
            ),
            line=dict(width=3, color=CHART_COLORS["rose"]),
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            name="Meta",
            x=df_produtos["Produto"],
            y=df_produtos["Meta"],
            mode="lines+markers",
            marker=dict(size=8, color=CHART_COLORS["primary_dark"]),
            line=dict(
                width=2,
                color=CHART_COLORS["primary_dark"],
                dash="dash",
            ),
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    # Acumulado mês atual
    dus_atual, acum_atual = _serie_acumulado_por_du(df_atual, feriados_atual)
    if dus_atual:
        fig.add_trace(
            go.Scatter(
                name="Mês Atual",
                x=dus_atual,
                y=acum_atual,
                mode="lines+markers",
                marker=dict(
                    size=5,
                    color=CHART_COLORS["primary"],
                    line=dict(width=1, color=chart_theme()["bg"]),
                ),
                line=dict(width=3, color=CHART_COLORS["primary"]),
                hovertemplate="DU %{x}<br>%{y:,.0f}<extra>Mês Atual</extra>",
            ),
            row=1,
            col=2,
        )

    # Acumulado mês anterior
    dus_ant, acum_ant = _serie_acumulado_por_du(df_ant, feriados_ant)
    if dus_ant:
        fig.add_trace(
            go.Scatter(
                name="Mês Anterior",
                x=dus_ant,
                y=acum_ant,
                mode="lines+markers",
                marker=dict(size=5, color=CHART_COLORS["neutral"]),
                line=dict(
                    width=2,
                    color=CHART_COLORS["neutral"],
                    dash="dash",
                ),
                hovertemplate="DU %{x}<br>%{y:,.0f}<extra>Mês Anterior</extra>",
            ),
            row=1,
            col=2,
        )

    fig.update_xaxes(
        title_text="Dia Útil",
        row=1,
        col=2,
        dtick=1,
    )
    fig.update_yaxes(
        title_text="Volume Acumulado (R$)",
        row=1,
        col=2,
        tickformat=",.0f",
    )

    fig.update_layout(
        height=640,
        showlegend=True,
        title_text="Analise Completa de Produtos",
        bargap=0.2,
        autosize=True,
    )
    return _aplicar(fig, t)


def criar_grafico_evolucao(df_evolucao, kpis, ano=None, mes=None):
    """Grafico de evolucao diaria."""
    import calendar
    from datetime import date as _date

    t = _template()
    meta_valor = float(kpis.get("meta_global_valor", 0) or 0)
    projecao_valor = float(kpis.get("projecao", 0) or 0)

    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=(
            "Evolucao Diaria de Vendas",
            "Evolucao Acumulada vs Meta",
        ),
        vertical_spacing=0.15,
    )

    fig.add_trace(
        go.Bar(
            name="Valor Diario",
            x=df_evolucao["DATA"],
            y=df_evolucao["VALOR"],
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
            hovertemplate="%{x|%d/%m}<br>%{y:,.0f}<extra>Valor Diário</extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            name="Valor Acumulado",
            x=df_evolucao["DATA"],
            y=df_evolucao["Valor Acumulado"],
            mode="lines+markers",
            marker=dict(
                size=5,
                color=CHART_COLORS["primary_dark"],
                line=dict(width=1, color=chart_theme()["bg"]),
            ),
            line=dict(width=3, color=CHART_COLORS["primary_dark"]),
            fill="tozeroy",
            fillcolor="rgba(37, 99, 235, 0.08)",
            hovertemplate="%{x|%d/%m}<br>Acumulado: %{y:,.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    # Trajetória de meta: linha diagonal do 1º ao último dia do mês,
    # mostrando o ritmo diário necessário para atingir a meta em R$.
    if meta_valor > 0 and ano and mes:
        last_day = calendar.monthrange(ano, mes)[1]
        traj_x = [
            pd.Timestamp(_date(ano, mes, 1)),
            pd.Timestamp(_date(ano, mes, last_day)),
        ]
        fig.add_trace(
            go.Scatter(
                name="Ritmo de Meta",
                x=traj_x,
                y=[0, meta_valor],
                mode="lines",
                line=dict(width=2, color=CHART_COLORS["success"], dash="dash"),
                hovertemplate="%{x|%d/%m}<br>Esperado: %{y:,.0f}<extra>Ritmo de Meta</extra>",
            ),
            row=2,
            col=1,
        )

    # Meta total (linha horizontal em R$)
    if meta_valor > 0:
        fig.add_hline(
            y=meta_valor,
            line_dash="dot",
            line_color=CHART_COLORS["success"],
            line_width=2,
            annotation_text=f"Meta ({formatar_moeda(meta_valor)})",
            annotation_font=dict(size=11, color=CHART_COLORS["success"]),
            row=2,
            col=1,
        )

    # Projeção (em R$) — exibe apenas quando difere da meta em mais de 2%
    if projecao_valor > 0 and (
        meta_valor == 0
        or abs(projecao_valor - meta_valor) > meta_valor * 0.02
    ):
        fig.add_hline(
            y=projecao_valor,
            line_dash="dot",
            line_color=CHART_COLORS["warning"],
            line_width=2,
            annotation_text=f"Projecao ({formatar_moeda(projecao_valor)})",
            annotation_font=dict(size=11, color=CHART_COLORS["warning"]),
            row=2,
            col=1,
        )

    fig.update_layout(
        height=640,
        showlegend=True,
        hovermode="x unified",
        autosize=True,
    )
    return _aplicar(fig, t)


def criar_grafico_regional(df_regioes):
    """Grafico de analise regional."""
    t = _template()
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "Valor por Regiao",
            "% Atingimento por Regiao",
        ),
        specs=[[{"type": "bar"}, {"type": "bar"}]],
    )

    df_s = df_regioes.sort_values("Valor", ascending=False)

    fig.add_trace(
        go.Bar(
            x=df_s["Região"],
            y=df_s["Valor"],
            name="Valor",
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
            text=df_s["Valor"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=1,
    )

    cores = df_s["% Atingimento"].apply(
        lambda x: CHART_COLORS["success"] if x >= 100 else CHART_COLORS["danger"]
    )
    fig.add_trace(
        go.Bar(
            x=df_s["Região"],
            y=df_s["% Atingimento"],
            name="% Atingimento",
            marker_color=cores,
            marker_line=dict(width=0),
            text=df_s["% Atingimento"].apply(lambda x: f"{x:.1f}%"),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        height=460,
        showlegend=False,
        title_text="Analise por Regiao",
        bargap=0.25,
        autosize=True,
    )
    return _aplicar(fig, t)


def criar_grafico_media_regiao(df_media):
    """Grafico de media de pontos por regiao."""
    t = _template()
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df_media["Região"],
            y=df_media["Pontos Médio"],
            name="Pontos Medio",
            marker_color=CHART_COLORS["secondary"],
            marker_line=dict(width=0),
            text=df_media["Pontos Médio"].apply(formatar_numero),
            textposition="outside",
            textfont=dict(size=11),
        )
    )

    fig.update_layout(
        title="Media de Pontos por Consultor por Regiao",
        xaxis_title="Regiao",
        yaxis_title="Pontos Medio",
        height=400,
        bargap=0.3,
        autosize=True,
    )
    return _aplicar(fig, t)


def criar_heatmap_regiao_produto(
    df_ranking,
    df_ating,
    regioes_destaque=None,
):
    """Mapa de calor: ranking de regioes por produto.

    Celulas mostram a posicao; hover exibe o % atingimento.
    Escala: 1o lugar (verde) → ultimo (vermelho).
    regioes_destaque: lista de regioes para destacar com
    marcador visual (ex: regiao do gerente comercial).
    """
    t = _template()
    ct = chart_theme()

    regioes = df_ranking.index.tolist()
    produtos = df_ranking.columns.tolist()

    z = df_ranking.values
    n_regioes = len(regioes)

    destaque = set(regioes_destaque or [])

    # Labels do eixo Y com marcador para regioes destacadas
    y_labels = [f"★ {r}" if r in destaque else r for r in regioes]

    # Texto de hover com % atingimento
    hover = []
    for i, reg in enumerate(regioes):
        row = []
        for j, prod in enumerate(produtos):
            ating = df_ating.iloc[i, j]
            pos = int(z[i][j])
            marca = " (sua regiao)" if reg in destaque else ""
            row.append(
                f"<b>{reg}{marca}</b><br>"
                f"Produto: {prod}<br>"
                f"Posicao: {pos}º<br>"
                f"Atingimento: {ating:.1f}%"
            )
        hover.append(row)

    # Texto exibido nas celulas: apenas posicao em negrito/branco
    text = []
    for i in range(len(regioes)):
        row = []
        for j in range(len(produtos)):
            pos = int(z[i][j])
            row.append(f"<b>{pos}º</b>")
        text.append(row)

    # Escala invertida: 1 (melhor) = verde, max = vermelho
    colorscale = [
        [0.0, "#059669"],
        [0.5, "#fbbf24"],
        [1.0, "#dc2626"],
    ]

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=produtos,
            y=y_labels,
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=13, color="#FFFFFF"),
            hovertext=hover,
            hoverinfo="text",
            colorscale=colorscale,
            zmin=1,
            zmax=n_regioes,
            showscale=True,
            colorbar=dict(
                title=dict(text="Posicao", font=dict(color=ct["text"])),
                tickfont=dict(color=ct["text"]),
                tickvals=list(range(1, n_regioes + 1)),
                ticktext=[f"{i}º" for i in range(1, n_regioes + 1)],
            ),
            xgap=3,
            ygap=3,
        )
    )

    # Bordas de destaque nas linhas do usuario
    if destaque:
        for i, reg in enumerate(regioes):
            if reg in destaque:
                fig.add_shape(
                    type="rect",
                    x0=-0.5,
                    x1=len(produtos) - 0.5,
                    y0=i - 0.5,
                    y1=i + 0.5,
                    line=dict(
                        color="#2563eb",
                        width=3,
                    ),
                    layer="above",
                )

    fig.update_layout(
        title="Mapa de Calor: Ranking por Produto x Regiao",
        xaxis=dict(side="top", title="Produto"),
        yaxis_title="Regiao",
        height=max(340, 75 * n_regioes),
        autosize=True,
        yaxis=dict(autorange="reversed"),
    )

    return _aplicar(fig, t)
