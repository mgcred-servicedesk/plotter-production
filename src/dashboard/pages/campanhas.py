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

RLS: **so no analitico de propostas.** Apuracao, condicoes, familias
e rankings sao da REDE e todo perfil os ve inteiros (decisao do
usuario, 09/2026): posicao num ranking so faz sentido contra todos os
concorrentes, e meta/contemplacao sao globais — recortadas, um
supervisor veria a propria loja contra os R$ 75 mi. O analitico e o
unico bloco com linha crua (ADE, banco, valor), e esse passa por
``aplicar_rls`` dentro de ``tabela_analitico``.

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
    COLUNA_LOJA_CONSULTOR,
    COLUNA_MEDIA_DU,
    MARCA_MULTIPLAS_LOJAS,
    contemplacao,
    dias_uteis_campanha,
    excluir_desligados,
    marcar_contemplados,
    apurar_por_familia,
    campanha_padrao,
    preparar,
    ranking,
    ritmo,
    rotulo_desempate,
)
from src.dashboard.kpis.gerais import excluir_supervisores
from src.dashboard.loaders import (
    carregar_consolidado_intervalo,
    carregar_consultores_desligados,
)
from src.dashboard import rls as _rls
from src.dashboard.rls import aplicar_rls
from src.dashboard.tabs.rankings import _make_highlight_fn
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


def tabela_analitico(df: pd.DataFrame) -> pd.DataFrame:
    """Propostas da campanha, linha a linha, **recortadas pelo RLS**.

    Recebe o frame GLOBAL da campanha (o mesmo dos rankings) e aplica
    ``aplicar_rls`` aqui, no unico bloco da pagina que expoe linha crua:
    um gerente ve so as regioes dele e um supervisor so as lojas dele —
    que e o que torna o numero auditavel por quem responde por ele. O
    recorte mora DENTRO desta funcao, e nao no chamador, para que
    nenhum caminho monte o analitico sem ele. Fail-closed como
    ``aplicar_rls``: sem perfil, vazio.

    LOJA, REGIÃO e CONSULTOR entram mesmo sendo redundantes para quem
    tem escopo estreito: sem elas, quem audita nao confere de quem e
    cada proposta.
    """
    det = aplicar_rls(df)
    if det.empty:
        return pd.DataFrame()

    det = det.copy()
    # NUM_PROPOSTA preferido, CONTRATO_ID como fallback — mesmo criterio
    # da aba Analiticos (`_nr_ade`), para o mesmo ADE aparecer igual nas
    # duas telas.
    det["NR_ADE"] = (
        det.get("NUM_PROPOSTA", pd.Series("", index=det.index))
        .replace("", pd.NA)
        .fillna(det["CONTRATO_ID"].astype(str))
    )

    cols = [
        ("NR_ADE", "Nº ADE"),
        ("DATA_CADASTRO", "Data Digitação"),
        ("DATA", "Data Pagamento"),
        ("BANCO", "Banco"),
        ("VALOR", "Valor"),
        ("pontos", "Pontos"),
        ("TIPO_PRODUTO", "Produto"),
        ("CONSULTOR", "Consultor"),
        ("LOJA", "Loja"),
        ("REGIAO", "Região"),
    ]
    presentes = [(orig, novo) for orig, novo in cols if orig in det.columns]
    return (
        det[[o for o, _ in presentes]]
        .rename(columns=dict(presentes))
        .sort_values("Data Pagamento", ascending=False)
        .reset_index(drop=True)
    )


def mascara_destaque(
    rk: pd.DataFrame, df: pd.DataFrame
) -> Optional[pd.Series]:
    """Linhas do ranking que pertencem ao escopo de quem esta logado.

    Mesma regra dos rankings do dashboard de vendas — reusa
    ``_make_highlight_fn`` em vez de reescreve-la: gerente comercial
    destaca as lojas da regiao, supervisor a propria loja, consultor o
    proprio nome; admin/gestor sem destaque. O escopo sai de
    ``aplicar_rls(df)``, entao "visualizar como" e fail-closed valem
    igual. Destaque e so visual: o ranking continua o da rede.

    Adaptacao de colunas: o ranking da campanha usa ``LOJA`` e
    ``CONSULTOR`` (maiusculas) e, no de consultores, a coluna ``Loja``
    carrega ``MARCA_MULTIPLAS_LOJAS`` para quem mudou de loja. O
    consultor e do grupo da loja ATUAL dele — a mesma que a coluna
    mostra —, entao a marca e removida antes de comparar.
    """
    perfil = _rls._obter_perfil_efetivo()
    role = perfil.get("perfil") if perfil else None
    fn = _make_highlight_fn(aplicar_rls(df), role)
    if fn is None or rk.empty:
        return None

    vista = rk.rename(columns={"CONSULTOR": "Consultor"})
    if COLUNA_LOJA_CONSULTOR in vista.columns:
        vista[COLUNA_LOJA_CONSULTOR] = (
            vista[COLUNA_LOJA_CONSULTOR]
            .astype(str)
            .str.removesuffix(MARCA_MULTIPLAS_LOJAS)
        )
    elif "LOJA" in vista.columns:
        vista = vista.rename(columns={"LOJA": "Loja"})
    return fn(vista)


def legenda_multiplas_lojas(rk: pd.DataFrame) -> Optional[str]:
    """Explica o ``*`` da coluna Loja — so quando alguem o carrega.

    O ranking de consultores soma a producao pelo NOME, onde quer que
    ela tenha sido feita, mas a coluna mostra uma loja so: a atual. A
    marca avisa que houve outra; sem a legenda, ninguem sabe o que ela
    quer dizer.
    """
    if COLUNA_LOJA_CONSULTOR not in rk.columns:
        return None
    marcados = (
        rk[COLUNA_LOJA_CONSULTOR]
        .astype(str)
        .str.endswith(MARCA_MULTIPLAS_LOJAS)
    )
    if not marcados.any():
        return None
    return (
        f"`{MARCA_MULTIPLAS_LOJAS.strip()}` Produziu em mais de uma loja "
        "durante a campanha. A coluna mostra a loja atual (do pagamento "
        "mais recente); a produção feita em cada loja continua contando "
        "para aquela loja no ranking de lojas."
    )


def _render_analitico(df: pd.DataFrame, camp: Campanha) -> None:
    """Renderiza ``tabela_analitico`` — o recorte de RLS acontece la."""
    sac.divider(
        label="Analítico de propostas", align="left", color="gray"
    )

    tabela = tabela_analitico(df)
    if tabela.empty:
        st.info("Sem propostas no seu escopo.")
        return

    st.caption(
        f"{formatar_numero(len(tabela))} propostas pagas entre "
        f"{camp.inicio.strftime('%d/%m/%Y')} e "
        f"{camp.fim.strftime('%d/%m/%Y')}, já filtradas pelo seu perfil "
        "(RLS). Só produtos elegíveis à campanha."
    )
    exibir_tabela(
        tabela,
        colunas_moeda=["Valor"],
        colunas_pontos=["Pontos"],
        paginacao=100,
        key="tab_campanha_analitico",
    )
    botao_exportar_csv(
        tabela,
        f"{camp.slug}_analitico_propostas",
        key="csv_campanha_analitico",
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

    # SEM RLS aqui, de proposito: apuracao, condicoes, familias e
    # rankings sao da rede inteira para todo perfil (ver docstring do
    # modulo). O recorte acontece so em `tabela_analitico`.
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

        # Media/DU no lugar da contagem de contratos: quantidade nao diz
        # nada numa campanha apurada em VALOR — um contrato de R$ 500 e
        # um de R$ 50 mil contavam igual. Producao por dia trabalhado e
        # a leitura que a rede usa (o dashboard de vendas ja fala em
        # "Media DU").
        du_total, du_dec = dias_uteis_campanha(camp, hoje)
        du_rest = max(du_total - du_dec, 0)
        media_du = apuracao["valor"] / du_dec if du_dec else 0.0
        # "Necessario" tambem por DU, e nao por dia corrido como no
        # `ritmo`: os dois cards ficam lado a lado e o leitor compara —
        # com denominadores diferentes (106 dias corridos x 72 DU) a
        # comparacao daria ~R$ 466K contra ~R$ 464K e sugeriria "quase
        # la", quando o necessario por DU e ~48% acima do ritmo atual.
        # Mesma unidade, comparacao honesta.
        necessario_du = apuracao["falta"] / du_rest if du_rest else 0.0

        d1, d2, d3 = st.columns(3)
        d1.metric(
            "Dias restantes",
            formatar_numero(pace["dias_restantes"]),
            delta=f"{du_rest} DU",
            delta_color="off",
        )
        d2.metric(
            "Média/DU",
            formatar_moeda_compacta(media_du),
            delta=f"{du_dec} de {du_total} DU",
            delta_color="off",
        )
        d3.metric(
            "Necessário/DU",
            formatar_moeda_compacta(necessario_du),
            delta=(
                f"{necessario_du / media_du - 1:+.0%} vs ritmo atual"
                if media_du
                else None
            ),
            delta_color="inverse",
        )

    if camp.descricao:
        st.caption(camp.descricao)
    st.caption(
        f"Pagos de {camp.inicio.strftime('%d/%m/%Y')} a "
        f"{camp.fim.strftime('%d/%m/%Y')} · elegíveis: "
        f"{', '.join(camp.familias)}."
    )

    # ── Condicoes de premiacao ─────────────────────
    premio = contemplacao(df, camp)
    if camp.condicoes:
        _render_condicoes(camp, premio)

    # ── Producao por familia ───────────────────────
    sac.divider(label="Produção por família", align="left", color="gray")
    exibir_tabela(
        apurar_por_familia(df, camp, du_dec),
        colunas_moeda=["Valor", COLUNA_MEDIA_DU],
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
            # Desligados saem ANTES do ranking: posicoes recalculadas, e
            # ninguem desligado ocupa vaga de premiacao. A producao deles
            # segue no ranking de lojas (frame completo). Afastado
            # (licenca) NAO e desligado e fica.
            base_cons, n_desligados = excluir_desligados(
                excluir_supervisores(df, df_sup),
                carregar_consultores_desligados(),
            )
            if n_desligados:
                st.caption(
                    f"{n_desligados} consultor(es) desligado(s) fora do "
                    "ranking — a produção deles continua no ranking de "
                    "lojas."
                )
            rk = ranking(
                base_cons,
                "CONSULTOR",
                camp,
                com_loja=True,
                du_decorridos=du_dec,
            )
            nome_csv = f"{camp.slug}_ranking_consultores"
            vagas = premio["consultores"]
        else:
            rk = ranking(df, "LOJA", camp, du_decorridos=du_dec)
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
            mascara = mascara_destaque(rk, df)
            if mascara is not None and mascara.any():
                st.caption(
                    "Linhas destacadas: o seu escopo (região, loja ou "
                    "você). As posições são da rede inteira."
                )
            exibir_tabela(
                rk,
                highlight_mask=mascara,
                colunas_moeda=["Valor", COLUNA_MEDIA_DU],
                # O desempate e em PONTOS — formatar como moeda diria
                # que o criterio e valor, que e exatamente a confusao
                # que a mudanca de criterio veio desfazer.
                colunas_pontos=["Pontos", rotulo_desempate(camp)],
                colunas_numero=["#"],
                paginacao=100,
                key=f"tab_{nome_csv}",
            )
            legenda = legenda_multiplas_lojas(rk)
            if legenda:
                st.caption(legenda)
            botao_exportar_csv(rk, nome_csv, key=f"csv_{nome_csv}")

    if col_arte is not None:
        with col_arte:
            for fig in laterais:
                st.image(str(fig), width="stretch")

    # ── Analitico de propostas ─────────────────────
    _render_analitico(df, camp)
