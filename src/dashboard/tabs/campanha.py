"""Aba Campanha: acompanhamento da Campanha Semestral 2026-H2.

A aba carrega a **propria janela** (01/07 a 31/12/2026), nao o periodo
selecionado na sidebar: a campanha e semestral acumulada e o seletor de
mes nao a governa. A carga compoe os meses ja cacheados pelo dashboard
de vendas (ver ``loaders.carregar_consolidado_intervalo``), entao abrir
esta aba nao acrescenta consulta ao Supabase para mes que ja foi aberto.

RLS: a aba carrega dados proprios, logo aplica ``aplicar_rls`` ela
mesma, antes de qualquer agregacao ou render — os frames pos-RLS de
``main()`` sao de outro recorte de datas e nao servem aqui.
"""

from datetime import date

import plotly.graph_objects as go
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import (
    botao_exportar_csv,
    exibir_tabela,
)
from src.dashboard.formatters import (
    formatar_moeda,
    formatar_moeda_compacta,
    formatar_numero,
)
from src.dashboard.kpis.campanha import (
    CAMPANHA_FIM,
    CAMPANHA_INICIO,
    CAMPANHA_ROTULO,
    CATEGORIAS_EXCLUIDAS_NOTAVEIS,
    META_VALOR,
    apurar,
    apurar_por_familia,
    preparar,
    ranking,
    ritmo,
)
from src.dashboard.kpis.gerais import excluir_supervisores
from src.dashboard.loaders import carregar_consolidado_intervalo
from src.dashboard.rls import aplicar_rls
from src.dashboard.ui.theme import CHART_COLORS


def _cor_do_ritmo(atingimento: float, pct_tempo: float) -> str:
    """Verde quando a producao acompanha o tempo decorrido.

    Comparar atingimento com % de tempo (e nao com 100%) e o que
    responde "estamos no ritmo?" no meio da campanha — contra 100% tudo
    pareceria vermelho ate dezembro.
    """
    return (
        CHART_COLORS["success"]
        if atingimento >= pct_tempo
        else CHART_COLORS["danger"]
    )


def _termometro(apuracao: dict, pace: dict) -> go.Figure:
    """Barra horizontal: realizado x meta, com marcador de ritmo."""
    valor = apuracao["valor"]
    meta = apuracao["meta"]
    cor = _cor_do_ritmo(apuracao["atingimento"], pace["pct_tempo"])

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=[meta],
            y=[""],
            orientation="h",
            marker_color="rgba(128,128,128,0.15)",
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Bar(
            x=[valor],
            y=[""],
            orientation="h",
            marker_color=cor,
            text=[f"{formatar_moeda_compacta(valor)}"],
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(size=16, color="#fff"),
            hovertemplate=(
                f"Realizado: {formatar_moeda(valor)}<extra></extra>"
            ),
            showlegend=False,
        )
    )

    # Marcador do ritmo esperado: onde a campanha estaria se a producao
    # fosse linear no tempo. E a referencia que da sentido a cor.
    esperado = meta * pace["pct_tempo"]
    fig.add_vline(
        x=esperado,
        line=dict(color=CHART_COLORS["neutral"], width=2, dash="dash"),
        annotation_text=f"ritmo ({pace['pct_tempo'] * 100:.0f}% do tempo)",
        annotation_position="top",
        annotation_font_size=11,
    )

    fig.update_layout(
        barmode="overlay",
        height=130,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            range=[0, max(meta, valor) * 1.02],
            tickformat=",.0f",
            gridcolor="rgba(128,128,128,0.1)",
        ),
        yaxis=dict(showticklabels=False),
        hoverlabel=dict(
            bgcolor="rgba(30,30,46,0.9)",
            font_color="#fff",
            font_size=12,
            bordercolor="rgba(255,255,255,0.1)",
        ),
    )
    return fig


def render_tab_campanha(df_sup=None, hoje: date | None = None) -> None:
    """Renderiza a aba da Campanha Semestral.

    Args:
        df_sup: supervisores do periodo selecionado, usado para tirar
            supervisor do ranking de CONSULTOR (ele conta para a loja).
        hoje: injetavel para teste; ``None`` usa a data corrente.
    """
    hoje = hoje or date.today()

    sac.divider(
        label=CAMPANHA_ROTULO,
        icon="trophy",
        align="left",
        color="orange",
    )

    with st.spinner("Apurando a campanha (01/07 a 31/12/2026)..."):
        bruto, aviso = carregar_consolidado_intervalo(
            CAMPANHA_INICIO, CAMPANHA_FIM
        )

    if aviso:
        st.warning(aviso)
        return
    if bruto.empty:
        st.info("Nenhum contrato pago na janela da campanha.")
        return

    # RLS antes de qualquer agregacao ou render.
    bruto = aplicar_rls(bruto)
    if bruto.empty:
        st.info("Sem dados da campanha no seu escopo.")
        return

    df = preparar(bruto, CAMPANHA_INICIO, CAMPANHA_FIM)
    if df.empty:
        st.info(
            "Nenhum contrato de produto elegivel na janela da campanha."
        )
        return

    apuracao = apurar(df, META_VALOR)
    pace = ritmo(apuracao, hoje, CAMPANHA_INICIO, CAMPANHA_FIM)

    # ── Termometro ─────────────────────────────────
    st.plotly_chart(
        _termometro(apuracao, pace),
        width="stretch",
        config={"displayModeBar": False},
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Realizado", formatar_moeda(apuracao["valor"]))
    c2.metric(
        "Atingimento",
        f"{apuracao['atingimento'] * 100:.1f}%",
        delta=f"{(apuracao['atingimento'] - pace['pct_tempo']) * 100:+.1f} p.p. vs ritmo",
    )
    c3.metric("Falta", formatar_moeda(apuracao["falta"]))
    c4.metric(
        "Projecao",
        formatar_moeda_compacta(pace["projecao"]),
        delta=f"{pace['projecao_vs_meta'] * 100:.0f}% da meta",
    )

    d1, d2, d3 = st.columns(3)
    d1.metric("Dias restantes", formatar_numero(pace["dias_restantes"]))
    d2.metric(
        "Necessario/dia",
        formatar_moeda_compacta(pace["necessario_dia"]),
    )
    d3.metric("Contratos", formatar_numero(apuracao["qtd"]))

    st.caption(
        f"Pagos de {CAMPANHA_INICIO.strftime('%d/%m/%Y')} a "
        f"{CAMPANHA_FIM.strftime('%d/%m/%Y')} · meta "
        f"{formatar_moeda(META_VALOR)} em valor · produtos elegiveis: "
        f"CNC (inclui Super Conta), CLT, Consignado (inclui "
        f"portabilidade), Ant. de Benef. e FGTS · fora: "
        f"{', '.join(CATEGORIAS_EXCLUIDAS_NOTAVEIS)}. Projecao e "
        f"extrapolacao linear do ritmo ate hoje — nao considera "
        f"sazonalidade."
    )

    # ── Producao por familia ───────────────────────
    sac.divider(label="Producao por familia", align="left", color="gray")
    familias = apurar_por_familia(df)
    exibir_tabela(
        familias,
        colunas_moeda=["Valor"],
        colunas_numero=["Contratos"],
        colunas_percentual=["% do Total"],
        colunas_pontos=["Pontos"],
    )

    # ── Rankings ───────────────────────────────────
    sac.divider(
        label="Rankings (por pontos · desempate: producao CNC)",
        align="left",
        color="gray",
    )

    aba = st.radio(
        "Ranking",
        ["Consultores", "Lojas"],
        horizontal=True,
        key="campanha_ranking",
        label_visibility="collapsed",
    )

    if aba == "Consultores":
        # Supervisor que vende conta para a loja, nunca no ranking de
        # consultor — mesma regra dos rankings de producao.
        rk = ranking(excluir_supervisores(df, df_sup), "CONSULTOR")
        nome_csv = "campanha_ranking_consultores"
    else:
        rk = ranking(df, "LOJA")
        nome_csv = "campanha_ranking_lojas"

    if rk.empty:
        st.info("Sem dados para este ranking.")
        return

    exibir_tabela(
        rk,
        colunas_moeda=["Valor", "CNC (desempate)"],
        colunas_numero=["#", "Contratos"],
        colunas_pontos=["Pontos"],
    )
    botao_exportar_csv(rk, nome_csv, key=f"csv_{nome_csv}")
