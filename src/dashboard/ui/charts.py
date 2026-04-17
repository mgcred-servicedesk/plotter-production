"""
Graficos Plotly do dashboard.

Usa ``chart_theme``/``CHART_COLORS`` de ``ui.theme`` para
manter coerencia visual entre tema claro e escuro.
``_template``/``_aplicar`` sao helpers internos usados pelas
funcoes publicas ``criar_grafico_*``/``criar_heatmap_*``.
"""

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
        title_font_color=text_color,
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


def criar_grafico_produtos(df_produtos):
    """Grafico completo de produtos."""
    t = _template()

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Realizado vs Meta",
            "% Atingimento por Produto",
            "Projecao vs Meta",
            "Ticket Medio por Produto",
        ),
        specs=[
            [{"type": "bar"}, {"type": "bar"}],
            [{"type": "scatter"}, {"type": "bar"}],
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

    cores = df_produtos["% Atingimento"].apply(
        lambda x: CHART_COLORS["success"] if x >= 100 else CHART_COLORS["danger"]
    )
    fig.add_trace(
        go.Bar(
            name="% Atingimento",
            x=df_produtos["Produto"],
            y=df_produtos["% Atingimento"],
            marker_color=cores,
            marker_line=dict(width=0),
            text=df_produtos["% Atingimento"].apply(lambda x: f"{x:.1f}%"),
            textposition="outside",
            textfont=dict(size=10),
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    fig.add_hline(
        y=100,
        line_dash="dash",
        line_color=CHART_COLORS["neutral"],
        line_width=1,
        opacity=0.5,
        row=1,
        col=2,
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

    fig.add_trace(
        go.Bar(
            name="Ticket Medio",
            x=df_produtos["Produto"],
            y=df_produtos["Ticket Médio"],
            marker_color=CHART_COLORS["secondary"],
            marker_line=dict(width=0),
            text=df_produtos["Ticket Médio"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
            showlegend=False,
        ),
        row=2,
        col=2,
    )

    fig.update_layout(
        height=640,
        showlegend=True,
        title_text="Analise Completa de Produtos",
        bargap=0.2,
        autosize=True,
    )
    return _aplicar(fig, t)


def criar_grafico_evolucao(df_evolucao, kpis):
    """Grafico de evolucao diaria."""
    t = _template()
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
        ),
        row=2,
        col=1,
    )

    fig.add_hline(
        y=kpis["meta_prata"],
        line_dash="dash",
        line_color=CHART_COLORS["success"],
        line_width=2,
        annotation_text="Meta Prata",
        annotation_font=dict(size=11, color=CHART_COLORS["success"]),
        row=2,
        col=1,
    )
    fig.add_hline(
        y=kpis["projecao"],
        line_dash="dot",
        line_color=CHART_COLORS["warning"],
        line_width=2,
        annotation_text="Projecao",
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
    y_labels = [
        f"★ {r}" if r in destaque else r
        for r in regioes
    ]

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

    # Texto exibido nas celulas: posicao + % atingimento
    text = []
    for i in range(len(regioes)):
        row = []
        for j in range(len(produtos)):
            pos = int(z[i][j])
            ating = df_ating.iloc[i, j]
            row.append(f"{pos}º<br>{ating:.1f}%")
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
            textfont=dict(size=13, color=ct["text"]),
            hovertext=hover,
            hoverinfo="text",
            colorscale=colorscale,
            zmin=1,
            zmax=n_regioes,
            showscale=True,
            colorbar=dict(
                title="Posicao",
                titlefont=dict(color=ct["text"]),
                tickfont=dict(color=ct["text"]),
                tickvals=list(range(1, n_regioes + 1)),
                ticktext=[
                    f"{i}º" for i in range(1, n_regioes + 1)
                ],
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
        xaxis_title="Produto",
        yaxis_title="Regiao",
        height=max(380, 80 * n_regioes),
        autosize=True,
        yaxis=dict(autorange="reversed"),
    )

    return _aplicar(fig, t)
