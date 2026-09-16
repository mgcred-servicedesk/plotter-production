"""Secao Campanhas — terceira visao do dashboard.

Irmã de Vendas e Pontuacao no ``sac.segmented`` do ``app.py``, mas com
uma diferenca estrutural: **nao usa o periodo da sidebar**. Campanha tem
janela propria (a Semestral 2026-H2 vai de 01/07 a 31/12/2026), entao a
secao carrega o que precisa e o seletor de mes nao a governa.

Por isso o despacho no ``app.py`` acontece **antes** de
``carregar_periodo_dashboard``: abrir Campanhas nao paga a carga de
Vendas (contratos do mes, metas, supervisores, analise, cancelados,
reconquista, KPIs). Pontuacao nao pode fazer isso porque depende de
``kpis``; Campanhas pode, e no compute Nano isso importa.

RLS: a secao carrega dados proprios, logo aplica ``aplicar_rls`` ela
mesma, antes de qualquer agregacao ou render.

## Assets

Arte por campanha em ``assets/campanhas/<slug>/``, descoberta por
prefixo — **sem codigo**: soltar o arquivo na pasta basta.

| Prefixo do arquivo | Onde aparece |
|---|---|
| ``hero*.*``     | faixa do cabecalho, abrindo a pagina |
| ``rodape*.*``   | faixa no fim da pagina |
| ``lateral*.*``  | coluna estreita a direita dos rankings |

Varios arquivos do mesmo prefixo convivem (``hero-1.png``,
``hero-2.png``, ...) e entram **em colunas de largura igual**, na ordem
alfabetica do nome. Formato: png, jpg, jpeg, webp, gif ou svg. Nada
configurado = nada renderizado, sem erro.

**As pecas precisam compartilhar a proporcao** para sairem do mesmo
tamanho na mesma faixa: ``width="stretch"`` iguala a largura, nao a
altura. As da Semestral 2026-H2 estao normalizadas em disco numa
moldura transparente de 1078x422 (a da arte do premio), com o conteudo
centralizado.
"""

from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd
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
    CAMPANHAS,
    Campanha,
    apurar,
    contemplacao,
    marcar_contemplados,
    apurar_por_familia,
    campanha_padrao,
    preparar,
    ranking,
    ritmo,
    rotulo_desempate,
)
from src.dashboard.kpis.gerais import excluir_supervisores
from src.dashboard.loaders import carregar_consolidado_intervalo
from src.dashboard.rls import aplicar_rls
from src.dashboard.ui.theme import CHART_COLORS

_RAIZ_ASSETS = Path("assets/campanhas")
_EXTENSOES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")

# Chave do container dos cards — vira a classe `st-key-<chave>` no DOM e
# e o que limita o CSS abaixo a esta pagina.
_CHAVE_CARDS = "campanha_cards"

# Cards da mesma linha com a mesma altura.
#
# `st.metric` cresce quando recebe `delta`: na linha de topo, Atingimento
# e Projecao (com delta) ficavam ~25px mais altos que Realizado e Falta,
# e a moldura da CSS do projeto tornava o degrau visivel.
#
# A coluna (`stColumn`) JA estica sozinha — `stHorizontalBlock` e flex
# com `align-items: stretch`. O que falta e repassar essa altura pelos
# dois wrappers ate o card. Por isso a regra NAO toca no `stColumn`:
# por-lhe `height: 100%` faz a altura percentual referenciar um pai de
# altura automatica (referencia circular), o valor resolve como `auto` e
# a coluna PARA de esticar — foi o que derrubou a primeira tentativa.
#
# Medido com Playwright numa reproducao isolada: 93/118/93/118 antes,
# 118/118/118/118 depois.
_CSS_CARDS = f"""
<style>
.st-key-{_CHAVE_CARDS} [data-testid="stColumn"] [data-testid="stVerticalBlock"],
.st-key-{_CHAVE_CARDS} [data-testid="stElementContainer"],
.st-key-{_CHAVE_CARDS} [data-testid="stMetric"] {{
    height: 100%;
}}
</style>
"""


# ══════════════════════════════════════════════════════
# Assets
# ══════════════════════════════════════════════════════


def assets_da_campanha(slug: str, prefixo: str) -> List[Path]:
    """Arquivos de arte cujo nome comeca por ``prefixo``, ordenados.

    Tolerante de proposito: pasta inexistente, permissao negada ou
    campanha sem arte devolvem lista vazia. Arte e ilustracao — a
    ausencia dela nunca pode derrubar a apuracao.
    """
    pasta = _RAIZ_ASSETS / slug
    try:
        if not pasta.is_dir():
            return []
        return sorted(
            item
            for item in pasta.iterdir()
            if item.is_file()
            and item.suffix.lower() in _EXTENSOES
            and item.stem.lower().startswith(prefixo)
        )
    except OSError:
        return []


def _render_faixa(figuras: List[Path]) -> None:
    """Renderiza as figuras lado a lado, em colunas de largura igual.

    Colunas iguais + molduras de mesma proporcao = figuras do mesmo
    tamanho na tela. As pecas sao normalizadas em disco para uma
    moldura transparente comum (a da arte do premio, 1078x422), com o
    conteudo centralizado: sem isso, duas artes de proporcoes
    diferentes na mesma linha renderiam com alturas diferentes, porque
    ``width="stretch"`` iguala a largura, nao a altura.
    """
    for col, fig in zip(st.columns(len(figuras)), figuras):
        with col:
            st.image(str(fig), width="stretch")


def _render_hero(camp: Campanha) -> None:
    """Cabecalho: todas as artes ``hero*`` numa faixa so.

    Varias convivem (``hero-1``, ``hero-2``, ...) e entram em ordem
    alfabetica — hoje o titulo da campanha e a arte do premio.

    Renderiza a ~70% da largura (as colunas 1/5/1) porque a arte e
    2,55:1: ocupando a pagina inteira, duas pecas lado a lado passavam
    de 290px de altura e empurravam o termometro — o numero da campanha
    — para fora da primeira tela. Proporcao, nao pixel fixo, para o
    corte acompanhar a largura da janela.
    """
    figuras = assets_da_campanha(camp.slug, "hero")
    if not figuras:
        return
    _, centro, _ = st.columns([1, 5, 1])
    with centro:
        _render_faixa(figuras)


def _render_rodape(camp: Campanha) -> None:
    figuras = assets_da_campanha(camp.slug, "rodape")
    if not figuras:
        return
    st.divider()
    _render_faixa(figuras)


# ══════════════════════════════════════════════════════
# Termometro
# ══════════════════════════════════════════════════════


def _render_condicoes(camp: Campanha, premio: dict) -> None:
    """Os degraus de premiacao e onde a campanha esta neles.

    Mostra ``atingida`` e ``liberada`` separadas porque elas divergem, e
    a divergencia e a informacao mais acionavel da pagina: um degrau
    pode estar batido e nao valer, porque a cascata parou antes. Quem ve
    "CNC 100%" sem esse aviso conclui que ja ganhou.
    """
    sac.divider(label="Condições de premiação", align="left", color="gray")

    atual = premio["atual"]
    if atual is None:
        st.warning(
            f"**Nenhuma condição atingida.** Com o resultado de hoje, "
            f"ninguém é contemplado — a premiação começa na "
            f"{camp.condicoes[0].rotulo.lower()}."
        )
    else:
        st.success(
            f"**{atual.rotulo} atingida.** Com o resultado de hoje: "
            f"**{premio['consultores']} consultores** e "
            f"**{premio['lojas']} lojas** contemplados."
        )

    linhas = []
    for i, d in enumerate(premio["degraus"], start=1):
        cond = d["condicao"]
        if d["liberada"]:
            situacao = "Liberada"
        elif d["atingida"]:
            # Batida mas travada por um degrau anterior — o caso que a
            # rede mais confunde.
            situacao = "Atingida, mas travada"
        else:
            situacao = "Não atingida"
        linhas.append(
            {
                "#": i,
                "Condição": cond.rotulo,
                "Escopo": cond.familia or "Produção total",
                "Realizado": d["realizado"],
                "Meta": cond.meta,
                "% da Meta": d["atingimento"] * 100,
                "Falta": d["falta"],
                "Situação": situacao,
                "Consultores": cond.consultores,
                "Lojas": cond.lojas,
            }
        )

    exibir_tabela(
        pd.DataFrame(linhas),
        colunas_moeda=["Realizado", "Meta", "Falta"],
        colunas_percentual=["% da Meta"],
        colunas_numero=["#", "Consultores", "Lojas"],
    )
    st.caption(
        "Os degraus são cumulativos: cada um exige todos os anteriores. "
        "Bater o CLT sem bater o CNC não promove ninguém — por isso uma "
        "condição pode aparecer atingida e ainda assim travada. "
        "“Consultores” e “Lojas” são quantos passam a ser contemplados "
        "quando aquele degrau é liberado."
    )


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
            text=[formatar_moeda_compacta(valor)],
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
    fig.add_vline(
        x=meta * pace["pct_tempo"],
        line=dict(color=CHART_COLORS["neutral"], width=2, dash="dash"),
        annotation_text=f"ritmo ({pace['pct_tempo'] * 100:.0f}% do tempo)",
        annotation_position="top",
        annotation_font_size=11,
    )

    # Eixo em milhoes, PT-BR. O default do Plotly (",.0f") escreve
    # "10,000,000" — separador de milhar ingles, num dashboard pt-BR.
    # Cinco divisoes fazem a ultima marca cair exatamente na meta.
    passo = meta / 5
    tickvals = [passo * i for i in range(6)]
    ticktext = ["0"] + [
        f"{passo * i / 1_000_000:,.0f} mi".replace(",", ".")
        for i in range(1, 6)
    ]

    fig.update_layout(
        barmode="overlay",
        height=130,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            range=[0, max(meta, valor) * 1.02],
            tickvals=tickvals,
            ticktext=ticktext,
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


# ══════════════════════════════════════════════════════
# Pagina
# ══════════════════════════════════════════════════════


def _selecionar_campanha(hoje: date) -> Optional[Campanha]:
    """Seletor — so aparece quando ha mais de uma campanha cadastrada.

    Com uma campanha so, um seletor de um item unico e ruido visual.
    A segunda entrada em ``CAMPANHAS`` faz o seletor nascer sozinho.
    """
    if not CAMPANHAS:
        return None
    if len(CAMPANHAS) == 1:
        return CAMPANHAS[0]

    padrao = campanha_padrao(hoje)
    rotulos = [c.rotulo for c in CAMPANHAS]
    indice = (
        rotulos.index(padrao.rotulo)
        if padrao and padrao.rotulo in rotulos
        else 0
    )
    escolhido = st.selectbox(
        "Campanha",
        rotulos,
        index=indice,
        key="campanha_selecionada",
    )
    return next(c for c in CAMPANHAS if c.rotulo == escolhido)


def render_pagina_campanhas(hoje: Optional[date] = None) -> None:
    """Renderiza a secao Campanhas.

    Args:
        hoje: injetavel para teste; ``None`` usa a data corrente.
    """
    hoje = hoje or date.today()

    camp = _selecionar_campanha(hoje)
    if camp is None:
        st.info("Nenhuma campanha cadastrada.")
        return

    _render_hero(camp)
    _render_painel(camp, hoje)
    _render_rodape(camp)


def _render_painel(camp: Campanha, hoje: date) -> None:
    """Apuracao, familias e rankings de UMA campanha."""
    sac.divider(label=camp.rotulo, icon="trophy", align="left", color="orange")

    with st.spinner("Apurando a campanha..."):
        bruto, df_sup, aviso = carregar_consolidado_intervalo(
            camp.inicio, camp.fim
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

    df = preparar(bruto, camp)
    if df.empty:
        st.info("Nenhum contrato de produto elegível na janela.")
        return

    apuracao = apurar(df, camp)
    pace = ritmo(apuracao, camp, hoje)

    st.plotly_chart(
        _termometro(apuracao, pace),
        width="stretch",
        config={"displayModeBar": False},
    )

    st.markdown(_CSS_CARDS, unsafe_allow_html=True)
    with st.container(key=_CHAVE_CARDS):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Realizado", formatar_moeda(apuracao["valor"]))
        c2.metric(
            "Atingimento",
            f"{apuracao['atingimento'] * 100:.1f}%",
            delta=(
                f"{(apuracao['atingimento'] - pace['pct_tempo']) * 100:+.1f}"
                " p.p. vs ritmo"
            ),
        )
        c3.metric("Falta", formatar_moeda(apuracao["falta"]))
        c4.metric(
            "Projeção",
            formatar_moeda_compacta(pace["projecao"]),
            delta=f"{pace['projecao_vs_meta'] * 100:.0f}% da meta",
        )

        d1, d2, d3 = st.columns(3)
        d1.metric("Dias restantes", formatar_numero(pace["dias_restantes"]))
        d2.metric(
            "Necessário/dia",
            formatar_moeda_compacta(pace["necessario_dia"]),
        )
        d3.metric("Contratos", formatar_numero(apuracao["qtd"]))

    if camp.descricao:
        st.caption(camp.descricao)
    st.caption(
        f"Pagos de {camp.inicio.strftime('%d/%m/%Y')} a "
        f"{camp.fim.strftime('%d/%m/%Y')} · elegíveis: "
        f"{', '.join(camp.familias)} · fora: "
        f"{', '.join(camp.excluidas_notaveis)}. Projeção é extrapolação "
        "linear do ritmo até hoje — não considera sazonalidade."
    )

    # ── Condicoes de premiacao ─────────────────────
    premio = contemplacao(df, camp)
    if camp.condicoes:
        _render_condicoes(camp, premio)

    # ── Producao por familia ───────────────────────
    sac.divider(label="Produção por família", align="left", color="gray")
    exibir_tabela(
        apurar_por_familia(df, camp),
        colunas_moeda=["Valor"],
        colunas_numero=["Contratos"],
        colunas_percentual=["% do Total"],
        colunas_pontos=["Pontos"],
    )

    # ── Rankings ───────────────────────────────────
    sac.divider(
        label=(
            "Rankings (por pontos · desempate: produção "
            f"{camp.familia_desempate})"
        ),
        align="left",
        color="gray",
    )

    laterais = assets_da_campanha(camp.slug, "lateral")
    col_rank, col_arte = (
        st.columns([3, 1]) if laterais else (st.container(), None)
    )

    with col_rank:
        aba = st.radio(
            "Ranking",
            ["Consultores", "Lojas"],
            horizontal=True,
            key="campanha_ranking",
            label_visibility="collapsed",
        )

        if aba == "Consultores":
            # Supervisor nao concorre no ranking de CONSULTOR: como
            # supervisor ele concorre pela producao da loja que
            # supervisiona (decisao do usuario, 09/2026). A producao que
            # fez como consultor NAO se perde — segue somando para a
            # loja de origem, porque o ranking de LOJA usa o frame
            # completo e `contratos.loja_id` e por contrato.
            #
            # `df_sup` vem dos MESES DA CAMPANHA (uniao), nao do mes da
            # sidebar: quem foi promovido no meio da janela (migration
            # 110) precisa sair do ranking de consultor.
            rk = ranking(excluir_supervisores(df, df_sup), "CONSULTOR", camp)
            nome_csv = f"{camp.slug}_ranking_consultores"
            vagas = premio["consultores"]
        else:
            rk = ranking(df, "LOJA", camp)
            nome_csv = f"{camp.slug}_ranking_lojas"
            vagas = premio["lojas"]

        if camp.condicoes:
            rk = marcar_contemplados(rk, vagas)
            if vagas:
                st.caption(
                    f"**{vagas}** primeiros são contemplados pelo degrau "
                    f"vigente ({premio['atual'].rotulo})."
                )
            else:
                st.caption(
                    "Nenhuma condição atingida — o ranking mostra as "
                    "posições, mas ainda não há contemplados."
                )

        if rk.empty:
            st.info("Sem dados para este ranking.")
        else:
            # Paginado como as demais tabelas longas do projeto: o
            # ranking de consultores passa de 300 linhas no semestre e
            # empurrava o rodape para muito longe.
            exibir_tabela(
                rk,
                colunas_moeda=["Valor", rotulo_desempate(camp)],
                colunas_numero=["#", "Contratos"],
                colunas_pontos=["Pontos"],
                paginacao=100,
                key=f"tab_{nome_csv}",
            )
            botao_exportar_csv(rk, nome_csv, key=f"csv_{nome_csv}")

    if col_arte is not None:
        with col_arte:
            for fig in laterais:
                st.image(str(fig), width="stretch")
