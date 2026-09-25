"""
Dashboard de Pontuacao — pagina dedicada.

Recebe os DataFrames ja carregados, com RLS e filtros granulares de
UI aplicados pelo ``app.py``. Calcula KPIs em pontos, renderiza os
cards (principais, contexto, MIX) e a secao de prioridades.

Aceleradores aparecem na secao de prioridades por escolha de design
(continuam visiveis para nao perder contexto operacional), mas nao
entram no calculo de pontos.

Permissoes: respeita ``pode_ver('cards_gerenciais', role)``, igual
ao dashboard de vendas.

Alem da pagina, o modulo hospeda ``render_diagnostico_pontuacao`` — o
expander admin-only que audita o mapeamento categoria -> PTS. Nao e uma
pagina (renderiza inline, sem substituir o dashboard), mas mora aqui por
tema: e sobre a mesma pontuacao. Se outros diagnosticos surgirem, vale
promover a um modulo proprio.
"""

from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from src.dashboard.kpis.pontuacao import (
    calcular_medias_pontos_por_nivel,
    calcular_mix_pontos,
    calcular_pontos_cancelados,
    calcular_pontos_em_analise,
    calcular_prioridades_pontuacao,
    calcular_resumo_lojas_pontuacao,
    calcular_resumo_lojas_pontuacao_por_regiao,
    ROTULO_TOTAL_RESUMO_LOJAS,
)
from src.dashboard.components.tables import botao_exportar_csv, exibir_tabela
from src.dashboard.permissions import pode_ver
from src.dashboard.ui.kpi_cards_pontuacao import render_kpis_pontuacao
from src.dashboard.ui.prioridades_pontuacao import render_prioridades_pontuacao


def render_dashboard_pontuacao(
    *,
    kpis: Dict,
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    df_sup: pd.DataFrame,
    mapa_pontos: Dict[str, float],
    du_decorridos: int,
    perfil: Optional[str],
    peso_headcount: Optional[float] = None,
    df_metas_loja: Optional[pd.DataFrame] = None,
    consultor_selecionado: bool = False,
    mes: Optional[int] = None,
    ano: Optional[int] = None,
) -> None:
    """Renderiza a pagina de Pontuacao.

    Args:
        kpis: dict de ``calcular_kpis_gerais`` ja calculado em ``main()``
            (contem ``total_pontos``, ``meta_prata``, ``meta_ouro``,
            ``projecao_pontos``, ``perc_proj``, etc).
        df: contratos pagos pos-RLS e pos-filtros.
        df_analise: contratos em analise pos-RLS e pos-filtros.
        df_cancelados: contratos cancelados pos-RLS e pos-filtros.
        df_metas_produto: metas por produto pos-RLS.
        df_sup: supervisores pos-RLS (usado em medias e aceleradores).
        mapa_pontos: categoria_codigo -> PTS (vem de
            ``carregar_pontuacao_efetiva``).
        du_decorridos: dias uteis decorridos no periodo.
        perfil: role efetivo (apos Visualizar Como).
        df_metas_loja: metas de pontos de escopo LOJA pos-RLS/filtros
            (``df_metas_f``), usadas no resumo por loja. Nunca o frame
            de escopo CONSULTOR que alimenta ``kpis``.
        consultor_selecionado: filtro de consultor ativo — oculta o
            resumo por loja.
        mes, ano: competencia, so para o nome do arquivo exportado.
    """
    # Consultor nao ve cards gerenciais — segue a mesma matriz do
    # dashboard de vendas.
    if not pode_ver("cards_gerenciais", perfil):
        st.info(
            "Seu perfil não tem acesso aos KPIs gerenciais da página "
            "de Pontuação."
        )
        return

    meta_prata = float(kpis.get("meta_prata", 0) or 0)
    meta_ouro = float(kpis.get("meta_ouro", 0) or 0)
    du_total = int(kpis.get("du_total", 0) or 0)

    kpis_analise_pts = calcular_pontos_em_analise(
        df_analise, mapa_pontos, du_decorridos
    )
    kpis_cancel_pts = calcular_pontos_cancelados(
        df_cancelados, df, df_analise, mapa_pontos
    )
    medias_pts = calcular_medias_pontos_por_nivel(
        df, du_decorridos, df_sup, peso_headcount=peso_headcount
    )
    mix_pontos = calcular_mix_pontos(df, meta_prata, du_total)

    render_kpis_pontuacao(
        kpis=kpis,
        kpis_analise_pts=kpis_analise_pts,
        kpis_cancel_pts=kpis_cancel_pts,
        medias_pts=medias_pts,
        mix_pontos=mix_pontos,
    )

    prioridades = calcular_prioridades_pontuacao(
        df=df,
        df_analise=df_analise,
        mapa_pontos=mapa_pontos,
        meta_prata=meta_prata,
        meta_ouro=meta_ouro,
    )
    render_prioridades_pontuacao(
        prioridades=prioridades,
        df=df,
        df_metas_produto=df_metas_produto,
        df_sup=df_sup,
        perfil=perfil or "",
        meta_prata=meta_prata,
        meta_ouro=meta_ouro,
    )

    if pode_ver("resumo_lojas_pontuacao", perfil):
        _render_resumo_lojas(
            df=df,
            df_metas_loja=df_metas_loja,
            kpis=kpis,
            consultor_selecionado=consultor_selecionado,
            perfil=perfil,
            mes=mes,
            ano=ano,
        )


def _render_resumo_lojas(
    *,
    df: pd.DataFrame,
    df_metas_loja: Optional[pd.DataFrame],
    kpis: Dict,
    consultor_selecionado: bool,
    perfil: Optional[str] = None,
    mes: Optional[int] = None,
    ano: Optional[int] = None,
) -> None:
    """Tabela-resumo por loja no fim da pagina (admin/gestor/gerente).

    Oculta com um consultor selecionado: a meta aqui e a de escopo LOJA,
    e comparar os pontos de uma pessoa contra ela subestima o
    atingimento — a distorcao que os cards ja corrigem trocando para a
    meta individual.
    """
    st.markdown("---")
    st.markdown("### 🏪 Resumo por Loja")

    if consultor_selecionado:
        st.caption(
            "Resumo por loja indisponível com um consultor selecionado — "
            "a meta da loja não se compara com a produção de uma pessoa."
        )
        return

    args_resumo = dict(
        df=df,
        df_metas=(
            df_metas_loja if df_metas_loja is not None else pd.DataFrame()
        ),
        du_total=int(kpis.get("du_total", 0) or 0),
        du_decorridos=int(kpis.get("du_decorridos", 0) or 0),
        du_restantes=int(kpis.get("du_restantes", 0) or 0),
    )
    resumo = calcular_resumo_lojas_pontuacao(**args_resumo)
    if resumo.empty:
        st.info("Nenhuma loja com pontos ou meta no período.")
        return

    # Flag so para quem enxerga mais de uma regiao (admin/gestor); o
    # gerente comercial ja esta recortado na propria regiao.
    por_regiao = pode_ver("resumo_lojas_por_regiao", perfil) and st.toggle(
        "Separar por região",
        key="resumo_lojas_por_regiao",
        help=(
            "Uma tabela por região (a região do período, mesmo eixo das "
            "metas), cada uma com o próprio total, e o total geral no fim."
        ),
    )

    st.caption(
        "Pontos efetivos (pagos) e projeção no ritmo atual. Meta diária = "
        "pontos que faltam para a meta ÷ dias úteis restantes (0 quando "
        "a meta já foi batida)."
    )

    du_restantes = args_resumo["du_restantes"]
    if por_regiao:
        separado = calcular_resumo_lojas_pontuacao_por_regiao(**args_resumo)
        for regiao, resumo_regiao in separado["regioes"]:
            st.markdown(f"#### {regiao}")
            _exibir_resumo(resumo_regiao)
        st.markdown("#### Total geral")
        _exibir_resumo(separado["total"])
        exportacao = montar_exportacao_resumo_lojas(
            separado["regioes"], du_restantes, total_geral=separado["total"]
        )
    else:
        _exibir_resumo(resumo)
        exportacao = montar_exportacao_resumo_lojas(
            [(None, resumo)], du_restantes
        )

    if du_restantes <= 0:
        st.caption(
            "Período encerrado — meta diária em branco para lojas que "
            "não bateram a meta."
        )

    # Frames ja pos-RLS/filtros (contrato de `botao_exportar_csv`).
    competencia = f"_{ano}_{mes:02d}" if mes and ano else ""
    sufixo = "_por_regiao" if por_regiao else ""
    botao_exportar_csv(
        exportacao,
        nome=f"resumo_lojas_pontuacao{competencia}{sufixo}",
        key="exp_resumo_lojas_pontuacao",
    )


# Colunas do resumo por tipo, para arredondar a exportacao igual a tela
# (pontos com 2 casas, percentual com 1).
_COLS_PONTOS_RESUMO = [
    "Pontos",
    "Projeção",
    "Meta Prata",
    "Meta Ouro",
    "Meta Diária Prata",
    "Meta Diária Ouro",
]
_COLS_PERC_RESUMO = ["Ating. Prata %", "Ating. Ouro %"]


def _observacao_linha(linha: pd.Series, du_restantes: int) -> str:
    """Texto que na tela vive nos captions e no CSV precisa da linha."""
    notas = []
    for nivel in ("Prata", "Ouro"):
        meta = linha[f"Meta {nivel}"]
        if meta <= 0:
            notas.append(f"Sem meta {nivel} cadastrada")
        elif du_restantes <= 0 and pd.isna(linha[f"Meta Diária {nivel}"]):
            notas.append(f"Período encerrado — {nivel} não atingida")
    return "; ".join(notas)


def montar_exportacao_resumo_lojas(
    blocos: List[Tuple[Optional[str], pd.DataFrame]],
    du_restantes: int,
    total_geral: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Frame do CSV do resumo por loja — o que esta na tela, legivel no Excel.

    - Numeros continuam NUMEROS (sem separador de milhar nem "%"): com
      ``sep=";"``/``decimal=","`` do ``botao_exportar_csv`` o Excel pt-BR
      soma e ordena direto. Arredondados como na tela: pontos 2 casas,
      percentual 1.
    - "Nao se aplica" fica em branco, e a coluna ``Observação`` diz o
      porque — na tela isso esta nos captions, que nao vao para o arquivo.
    - Separado por regiao (``blocos`` com nome): coluna ``Região``
      primeiro, ``TOTAL`` de cada bloco vira ``TOTAL <regiao>`` e
      ``total_geral`` entra por ultimo como ``TOTAL GERAL``. Sem regiao
      (um bloco com nome ``None``) a coluna nao existe.
    """
    por_regiao = any(nome is not None for nome, _ in blocos)
    partes = []
    for nome, resumo in blocos:
        parte = resumo.copy()
        if por_regiao:
            eh_total = parte["Loja"] == ROTULO_TOTAL_RESUMO_LOJAS
            parte.loc[eh_total, "Loja"] = f"{ROTULO_TOTAL_RESUMO_LOJAS} {nome}"
            parte.insert(0, "Região", nome)
        partes.append(parte)

    if por_regiao and total_geral is not None and not total_geral.empty:
        geral = total_geral.copy()
        geral["Loja"] = f"{ROTULO_TOTAL_RESUMO_LOJAS} GERAL"
        geral.insert(0, "Região", "")
        partes.append(geral)

    if not partes:
        return pd.DataFrame()
    saida = pd.concat(partes, ignore_index=True)

    saida["Observação"] = saida.apply(
        _observacao_linha, axis=1, du_restantes=du_restantes
    )
    saida[_COLS_PONTOS_RESUMO] = saida[_COLS_PONTOS_RESUMO].round(2)
    saida[_COLS_PERC_RESUMO] = saida[_COLS_PERC_RESUMO].round(1)
    return saida


def _exibir_resumo(resumo: pd.DataFrame) -> None:
    """Uma tabela do resumo (geral, regiao ou total) + aviso de sem meta."""
    exibir_tabela(
        resumo,
        colunas_pontos=[
            "Pontos",
            "Projeção",
            "Meta Prata",
            "Meta Ouro",
            "Meta Diária Prata",
            "Meta Diária Ouro",
        ],
        colunas_percentual=["Ating. Prata %", "Ating. Ouro %"],
        highlight_mask=resumo["Loja"] == ROTULO_TOTAL_RESUMO_LOJAS,
    )

    # Vazio na tabela = nao se aplica. Nomear as lojas afetadas, como a
    # aba Rankings faz, para ninguem ler a celula vazia como 0%.
    lojas = resumo[resumo["Loja"] != ROTULO_TOTAL_RESUMO_LOJAS]
    sem_meta = lojas.loc[lojas["Meta Prata"] <= 0, "Loja"].tolist()
    if sem_meta:
        st.caption(
            "⚠ Sem Meta Prata cadastrada (atingimento e meta diária em "
            "branco): " + ", ".join(sem_meta)
        )


def render_diagnostico_pontuacao(diag: Dict) -> None:
    """Renderiza o expander de diagnostico do mapeamento de pontuacao.

    Audita quantos contratos receberam pontos, quais categorias
    aparecem nos contratos vs. na RPC de pontuacao, o mapa
    categoria -> PTS, os TIPO_PRODUTO que ficaram sem categoria e as
    categorias sem match. E ferramenta de suporte, nao KPI.

    Quem decide *quando* exibir (diagnostico presente e perfil admin)
    e o chamador (``app.py``); a funcao apenas renderiza.

    Args:
        diag: dict gravado em ``st.session_state['_diag_pontuacao']``
            por ``consolidar_dados``. Chaves consumidas aqui:
            ``total_contratos``, ``sem_categoria``,
            ``com_pontos_mapeados``, ``categorias_no_contrato``,
            ``categorias_na_pontuacao``, ``mapa_pontos`` e
            ``tipos_sem_categoria`` (opcional).
    """
    with st.expander(
        f"Diagnostico de pontuacao — "
        f"{diag['com_pontos_mapeados']}/{diag['total_contratos']} "
        f"contratos com pontos",
        expanded=False,
    ):
        c1, c2, c3 = st.columns(3)
        c1.metric("Total contratos", diag["total_contratos"])
        c2.metric("Sem categoria", diag["sem_categoria"])
        c3.metric("Com pontos", diag["com_pontos_mapeados"])

        st.markdown("**Categorias nos contratos:**")
        st.code(
            ", ".join(c for c in diag["categorias_no_contrato"] if c)
            or "(vazio)",
        )

        st.markdown("**Categorias na pontuacao (RPC):**")
        st.code(
            ", ".join(diag["categorias_na_pontuacao"]) or "(vazio)",
        )

        st.markdown("**Mapa de pontos:**")
        st.json(diag["mapa_pontos"])

        # Tipos sem categoria (não mapeados pelo fallback)
        tipos_sem_cat = diag.get("tipos_sem_categoria", [])
        if tipos_sem_cat:
            st.warning(
                f"**{diag['sem_categoria']} contratos sem categoria** "
                f"— TIPO_PRODUTO nao mapeado:"
            )
            st.dataframe(
                pd.DataFrame(tipos_sem_cat),
                width="stretch",
                hide_index=True,
            )

        # Categorias sem match
        cats_contrato = {c for c in diag["categorias_no_contrato"] if c}
        cats_pontuacao = set(diag["categorias_na_pontuacao"])
        sem_match = sorted(cats_contrato - cats_pontuacao)
        if sem_match:
            st.warning(
                f"**{len(sem_match)} categorias sem pontuacao:** "
                + ", ".join(sem_match)
            )

        # Saque no cartao Gov — taxa propria (CARTAO_GOV) em vez do
        # alias CARTAO. O aviso e o unico sinal de que a planilha do
        # mes veio sem a linha: nesse caso a taxa antiga permanece, e
        # os pontos desses contratos estao desatualizados.
        reclass = diag.get("saque_gov_reclassificado", 0)
        sem_taxa = diag.get("saque_gov_sem_pontuacao", 0)
        if sem_taxa:
            st.warning(
                f"**{sem_taxa} saques no cartao Gov sem taxa propria** "
                f"— CARTAO_GOV ausente da pontuacao do periodo; esses "
                f"contratos seguem com a taxa do cartao comum. "
                f"Importar a linha 'CARTAO GOV' da planilha do mes."
            )
        elif reclass:
            st.caption(
                f"{reclass} saque(s) no cartao Gov pontuando por "
                f"CARTAO_GOV."
            )
