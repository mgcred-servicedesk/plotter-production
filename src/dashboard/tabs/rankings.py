"""
Aba Rankings: lojas, consultores, regioes e por produto.

Dados org-wide (pre-RLS) para comparativo justo entre todos.
Visibilidade por perfil:
  admin / gestor          → Lojas | Consultores | Regioes | Por Produto
  gerente_comercial /
  supervisor              → Lojas | Consultores | Regioes | Por Produto
  consultor               → Consultores | Por Produto (visao consultor)

Highlight visual:
  gerente_comercial → destaca lojas da sua regiao em todos os rankings
  supervisor        → destaca a propria loja em todos os rankings

Flag "Somente dados da regiao": restringe todas as sub-abas ao recorte
regional. Admin/gestor escolhem a regiao num seletor; demais perfis usam
a(s) regiao(oes) do proprio escopo RLS (fail-closed: escopo sem REGIAO
nao exibe nada).
"""

import re
import unicodedata
from typing import Callable, Optional

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import botao_exportar_csv, exibir_tabela
from src.dashboard.kpis.produtos import (
    COL_PRODUTO_DETALHADO,
    adicionar_produto_detalhado,
)
from src.dashboard.kpis.rankings import (
    calcular_ranking_consultores,
    calcular_ranking_lojas,
    calcular_ranking_pontos,
    calcular_ranking_por_acelerador,
    calcular_ranking_por_produto,
    listar_sem_producao,
)

# Perfis com visao de controle: enxergam lojas/consultores ativos
# SEM producao no periodo (universo completo nos rankings).
_PERFIS_CONTROLE = ("admin", "gestor", "gerente_comercial")

_HighlightFn = Callable[[pd.DataFrame], pd.Series]

# top_n "infinito": obtem o ranking completo para que a fixacao do
# escopo do usuario abaixo do Top N (ver _exibir_ranking_pinned)
# possa preservar a posicao real das linhas cortadas.
_SEM_LIMITE = 10**9

# Icones da sub-navegacao. Material Symbols (`:material/<nome>:`), nao
# Bootstrap: o st.pills renderiza markdown no rotulo. Nomes validos em
# `streamlit.material_icon_names.ALL_MATERIAL_ICONS`. `map` em Regioes
# acompanha a aba principal homonima; `rocket_launch` em Por
# Aceleradores acompanha a sub-aba Aceleradores de Analiticos.
_ICONES_RANKINGS = {
    "Lojas": "storefront",
    "Consultores": "people",
    "Regioes": "map",
    "Por Produto": "inventory_2",
    "Por Aceleradores": "rocket_launch",
}


def _divider(label: str, icon: str, color: str) -> None:
    sac.divider(label=label, icon=icon, align="left", color=color)


def _slug(txt: str) -> str:
    """Normaliza texto para uso em keys e nomes de arquivo."""
    s = unicodedata.normalize("NFKD", str(txt))
    s = s.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _make_highlight_fn(
    df_scope: pd.DataFrame,
    perfil: Optional[str],
) -> Optional[_HighlightFn]:
    """Cria função de highlight baseada no perfil e escopo RLS.

    Gerente comercial: destaca todas as lojas da sua região.
    Supervisor:        destaca apenas a sua loja.
    Consultor:         destaca o próprio nome na coluna "Consultor".
    Outros perfis:     sem highlight (retorna None).

    A função retornada recebe um df de ranking e devolve uma
    pd.Series bool com o mesmo índice.
    """
    if perfil == "consultor":
        if "CONSULTOR" not in df_scope.columns or df_scope.empty:
            return None
        nomes: frozenset = frozenset(df_scope["CONSULTOR"].dropna().unique())
        if not nomes:
            return None

        def _fn_consultor(rk: pd.DataFrame) -> pd.Series:
            if "Consultor" in rk.columns:
                return rk["Consultor"].isin(nomes)
            return pd.Series(False, index=rk.index)

        return _fn_consultor

    if perfil not in ("gerente_comercial", "supervisor"):
        return None
    if "LOJA" not in df_scope.columns or df_scope.empty:
        return None

    lojas: frozenset = frozenset(df_scope["LOJA"].dropna().unique())
    if not lojas:
        return None

    def _fn(rk: pd.DataFrame) -> pd.Series:
        if "Loja" in rk.columns:
            return rk["Loja"].isin(lojas)
        return pd.Series(False, index=rk.index)

    return _fn


def _exibir_ranking(
    rk: pd.DataFrame,
    highlight_fn: Optional[_HighlightFn],
    nome: Optional[str] = None,
    key: Optional[str] = None,
) -> None:
    """Exibe um ranking, aplicando o highlight do perfil se houver.

    nome/key: se fornecidos, exibe botao de exportar CSV abaixo da
    tabela. O export espelha EXATAMENTE o ranking renderizado — os
    rankings sao org-wide por design (comparativo justo), portanto o
    CSV contem o mesmo recorte ja visivel na tela.
    """
    mask = highlight_fn(rk) if highlight_fn else None
    exibir_tabela(rk, highlight_mask=mask)
    if nome and key:
        botao_exportar_csv(rk, nome, key)


def _exibir_ranking_pinned(
    rk_full: pd.DataFrame,
    top_n: int,
    highlight_fn: Optional[_HighlightFn],
    nome: Optional[str] = None,
    key: Optional[str] = None,
) -> None:
    """Exibe o Top N e fixa abaixo as linhas do escopo do usuario.

    Usado nas visoes sem fallback por regiao (Por Produto / Por
    Aceleradores). `rk_full` deve ser o ranking COMPLETO (sem corte),
    para que as linhas do escopo cortadas mantenham a posicao real.
    """
    top = rk_full.head(top_n)
    if highlight_fn is not None:
        fora = rk_full.iloc[top_n:]
        if not fora.empty:
            pinned = fora[highlight_fn(fora)]
            if not pinned.empty:
                top = pd.concat([top, pinned])
    _exibir_ranking(top, highlight_fn, nome=nome, key=key)


def _render_par(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    df_sup,
    tipo: str,
    top_n: int,
    suffix: str = "",
    top_label: bool = True,
    highlight_fn: Optional[_HighlightFn] = None,
    export_prefix: str = "",
    df_universo: Optional[pd.DataFrame] = None,
) -> None:
    """Renderiza par de colunas: Atingimento | Pontos para loja ou consultor.

    top_label=False omite o prefixo "Top N" (visoes de regiao sem limite).
    highlight_fn: se fornecida, gera máscara de destaque para o ranking.
    export_prefix: identifica nome/key dos botoes de exportar CSV
    (vazio = sem botao).
    df_universo: universo de lojas/consultores ativos — entidades sem
    producao entram zeradas no fim (usar so em visoes de lista completa,
    senao o corte do Top N as esconde).
    """
    label = "Loja" if tipo == "loja" else "Consultor"
    prefix = f"Top {top_n} " if top_label else ""

    def _export_args(sufixo: str) -> dict:
        if not export_prefix:
            return {}
        return {
            "nome": f"ranking_{export_prefix}_{sufixo}",
            "key": f"exp_rk_{export_prefix}_{sufixo}",
        }

    col1, col2 = st.columns(2)
    with col1:
        _divider(f"{prefix}{label}s por Atingimento{suffix}", "graph-up-arrow", "green")
        if tipo == "loja":
            rk = calcular_ranking_lojas(
                df, df_metas, top_n=top_n, df_universo=df_universo,
            )
        else:
            rk = calcular_ranking_consultores(
                df, df_metas, top_n=top_n, df_supervisores=df_sup,
                df_universo=df_universo,
            )
        if not rk.empty:
            _exibir_ranking(rk, highlight_fn, **_export_args("atingimento"))
        else:
            st.info("Sem dados")

    with col2:
        _divider(f"{prefix}{label}s por Pontos{suffix}", "star-fill", "blue")
        rk = calcular_ranking_pontos(
            df, tipo=tipo, top_n=top_n,
            df_supervisores=(df_sup if tipo == "consultor" else None),
            df_universo=df_universo,
        )
        if not rk.empty:
            _exibir_ranking(rk, highlight_fn, **_export_args("pontos"))
        else:
            st.info("Sem dados")


def _filtrar_universo_regiao(
    df_universo: Optional[pd.DataFrame],
    regioes,
) -> Optional[pd.DataFrame]:
    """Recorta o universo pela(s) regiao(oes) exibida(s)."""
    if df_universo is None or "REGIAO" not in df_universo.columns:
        return None
    regioes = {regioes} if isinstance(regioes, str) else set(regioes)
    return df_universo[df_universo["REGIAO"].isin(regioes)]


def _render_sem_producao(
    df: pd.DataFrame,
    df_universo: Optional[pd.DataFrame],
    tipo: str,
    df_sup=None,
    key_suffix: str = "",
) -> None:
    """Bloco de controle: entidades ativas SEM producao no periodo.

    Renderizado apenas para _PERFIS_CONTROLE (o gate e feito no
    render_tab_rankings, que zera os universos p/ demais perfis).
    `df` deve ser o MESMO df dos rankings exibidos (org-wide ou ja
    recortado pelo flag de regiao) — a lista espelha o que esta na tela.
    """
    if df_universo is None or df_universo.empty:
        return
    zerados = listar_sem_producao(
        df, df_universo, tipo=tipo, df_supervisores=df_sup,
    )
    plural = "lojas" if tipo == "loja" else "consultores"
    if zerados.empty:
        st.caption(
            "Sem produção no período: nenhuma loja ativa zerada."
            if tipo == "loja"
            else "Sem produção no período: nenhum consultor ativo zerado."
        )
        return
    with st.expander(
        f"⚠ Sem produção no período ({len(zerados)} {plural})",
        expanded=False,
    ):
        exibir_tabela(zerados)
        botao_exportar_csv(
            zerados,
            f"sem_producao_{plural}{key_suffix}",
            f"exp_sem_prod_{plural}{key_suffix}",
        )


def _render_sem_producao_produto(
    df: pd.DataFrame,
    produto: str,
    df_universo: Optional[pd.DataFrame],
    tipo: str,
    df_sup=None,
) -> None:
    """Zerados no produto, dentro do expander da sub-aba Por Produto.

    Sem expander aninhado (o Streamlit nao permite): caption + tabela
    + export direto. So renderiza para perfis de controle — os
    universos chegam None para os demais.

    Criterio por produto: nenhum contrato com VALOR > 0 daquele produto
    (``PRODUTO_DETALHADO`` — mesma dimensao do ranking exibido acima,
    com o PACK desmembrado).
    """
    if df_universo is None or df_universo.empty:
        return
    df_split = adicionar_produto_detalhado(df)
    if COL_PRODUTO_DETALHADO in df_split.columns:
        df_prod = df_split[df_split[COL_PRODUTO_DETALHADO] == produto]
    else:
        df_prod = df.iloc[0:0]
    zerados = listar_sem_producao(
        df_prod, df_universo, tipo=tipo, df_supervisores=df_sup,
    )
    if zerados.empty:
        return
    plural = "lojas" if tipo == "loja" else "consultores"
    st.caption(f"⚠ Sem produção em {produto}: {len(zerados)} {plural}")
    exibir_tabela(zerados)
    botao_exportar_csv(
        zerados,
        f"sem_producao_{_slug(produto)}_{tipo}",
        f"exp_sem_prod_prod_{tipo}_{_slug(produto)}",
    )


def _render_secao_regiao(
    df_scope: pd.DataFrame,
    df_full: pd.DataFrame,
    df_metas: pd.DataFrame,
    df_sup,
    tipo: str,
    key_prefix: str,
    highlight_fn: Optional[_HighlightFn] = None,
    df_universo: Optional[pd.DataFrame] = None,
) -> None:
    """Seção 'por região' abaixo dos rankings globais.

    df_scope → determina a(s) região(ões) do usuário (respeita RLS).
    df_full  → fonte dos dados de ranking (todas as lojas/consultores
               da região, independente do escopo RLS do usuário).
    df_universo → universo de ativos (já recortado pelo RLS do perfil);
               regiões só com zerados entram no seletor e as entidades
               sem produção aparecem zeradas no fim do ranking.

    Supervisor vê apenas sua região no seletor, mas o ranking exibe
    TODAS as lojas daquela região para que saiba sua posição relativa.
    """
    regioes_set: set = set()
    if "REGIAO" in df_scope.columns and not df_scope.empty:
        regioes_set |= set(df_scope["REGIAO"].dropna())
    if df_universo is not None and "REGIAO" in df_universo.columns:
        regioes_set |= set(df_universo["REGIAO"].dropna())
    regioes_set.discard("")

    regioes = sorted(regioes_set)
    if not regioes:
        return

    _divider("Rankings por Regiao", "geo-alt", "violet")

    if len(regioes) == 1:
        regiao = regioes[0]
        st.caption(f"Regiao: **{regiao}**")
    else:
        regiao = st.selectbox(
            "Selecionar Regiao",
            regioes,
            key=f"{key_prefix}_sel_regiao",
        )

    # Filtra df_full (org-wide) pela região → mostra todos da região
    if "REGIAO" in df_full.columns:
        df_reg = df_full[df_full["REGIAO"] == regiao]
    else:
        df_reg = df_full.iloc[0:0]
    base = "lojas" if tipo == "loja" else "consultores"
    _render_par(
        df_reg, df_metas, df_sup, tipo=tipo,
        top_n=_SEM_LIMITE,
        suffix=f" — {regiao}",
        top_label=False,
        highlight_fn=highlight_fn,
        export_prefix=f"{base}_{_slug(regiao)}",
        df_universo=_filtrar_universo_regiao(df_universo, regiao),
    )


def _render_lojas(
    df, df_metas, df_scope, df_sup, top_n: int,
    highlight_fn: Optional[_HighlightFn] = None,
    com_secao_regiao: bool = True,
    df_universo: Optional[pd.DataFrame] = None,
) -> None:
    _render_par(
        df, df_metas, df_sup, tipo="loja", top_n=top_n,
        highlight_fn=highlight_fn, export_prefix="lojas",
    )
    _render_sem_producao(df, df_universo, tipo="loja", key_suffix="_lojas")
    if com_secao_regiao:
        _render_secao_regiao(
            df_scope, df, df_metas, df_sup,
            tipo="loja", key_prefix="lojas", highlight_fn=highlight_fn,
            df_universo=df_universo,
        )


def _render_consultores(
    df, df_metas, df_scope, df_sup, top_n: int,
    highlight_fn: Optional[_HighlightFn] = None,
    com_secao_regiao: bool = True,
    df_universo: Optional[pd.DataFrame] = None,
) -> None:
    _render_par(
        df, df_metas, df_sup, tipo="consultor", top_n=top_n,
        highlight_fn=highlight_fn, export_prefix="consultores",
    )
    _render_sem_producao(
        df, df_universo, tipo="consultor", df_sup=df_sup, key_suffix="_cons",
    )
    if com_secao_regiao:
        _render_secao_regiao(
            df_scope, df, df_metas, df_sup,
            tipo="consultor", key_prefix="cons", highlight_fn=highlight_fn,
            df_universo=df_universo,
        )


def _render_regioes(
    df, df_metas, df_sup, top_n: int,
    highlight_fn: Optional[_HighlightFn] = None,
    df_lojas_univ: Optional[pd.DataFrame] = None,
    df_cons_univ: Optional[pd.DataFrame] = None,
) -> None:
    """Rankings intra-regiao com expander por regiao.

    Universos (visao de controle): regioes so com zerados ganham
    expander e as entidades sem producao entram zeradas no fim.
    """
    if "REGIAO" not in df.columns:
        st.warning("Dados de regiao nao disponiveis")
        return

    regioes_set = set(df["REGIAO"].dropna())
    for univ in (df_lojas_univ, df_cons_univ):
        if univ is not None and "REGIAO" in univ.columns:
            regioes_set |= set(univ["REGIAO"].dropna())
    regioes_set.discard("")

    regioes = sorted(regioes_set)
    if not regioes:
        st.warning("Nenhuma regiao encontrada")
        return

    for regiao in regioes:
        df_reg = df[df["REGIAO"] == regiao]
        with st.expander(str(regiao), expanded=False):
            _render_par(
                df_reg, df_metas, df_sup,
                tipo="loja", top_n=_SEM_LIMITE, suffix=f" — {regiao}",
                top_label=False, highlight_fn=highlight_fn,
                export_prefix=f"regiao_{_slug(regiao)}_lojas",
                df_universo=_filtrar_universo_regiao(df_lojas_univ, regiao),
            )
            _render_par(
                df_reg, df_metas, df_sup,
                tipo="consultor", top_n=_SEM_LIMITE, suffix=f" — {regiao}",
                top_label=False, highlight_fn=highlight_fn,
                export_prefix=f"regiao_{_slug(regiao)}_consultores",
                df_universo=_filtrar_universo_regiao(df_cons_univ, regiao),
            )


def _filtrar_somente_regiao(
    df: pd.DataFrame,
    df_scope: pd.DataFrame,
    perfil: Optional[str],
) -> tuple[pd.DataFrame, Optional[set]]:
    """Aplica o flag "Somente dados da regiao" sobre o df org-wide.

    Admin/gestor: escopo e global, entao a regiao vem de um seletor.
    Demais perfis: regiao(oes) derivadas do escopo RLS (df_scope),
    fail-closed — escopo vazio ou sem coluna REGIAO nao exibe nada.

    Retorna (df filtrado, regioes selecionadas) — as regioes permitem
    recortar tambem os universos de controle; None = nenhuma regiao.
    """
    if "REGIAO" not in df.columns:
        st.warning("Dados de regiao nao disponiveis")
        return df.iloc[0:0], None

    if perfil in ("admin", "gestor"):
        regioes = sorted(df["REGIAO"].dropna().unique().tolist())
        if not regioes:
            st.warning("Nenhuma regiao encontrada")
            return df.iloc[0:0], None
        regiao = st.selectbox(
            "Regiao",
            regioes,
            key="rankings_flag_sel_regiao",
        )
        return df[df["REGIAO"] == regiao], {regiao}

    if df_scope is None or "REGIAO" not in df_scope.columns:
        st.info("Sem regiao no escopo do perfil — nada a exibir.")
        return df.iloc[0:0], None

    regioes_scope = set(df_scope["REGIAO"].dropna().unique())
    if not regioes_scope:
        st.info("Sem regiao no escopo do perfil — nada a exibir.")
        return df.iloc[0:0], None

    st.caption("Regiao: **" + ", ".join(sorted(regioes_scope)) + "**")
    return df[df["REGIAO"].isin(regioes_scope)], regioes_scope


def render_tab_rankings(
    df,
    df_metas,
    df_sup,
    df_scope: Optional[pd.DataFrame] = None,
    perfil: Optional[str] = None,
    df_lojas_univ: Optional[pd.DataFrame] = None,
    df_cons_univ: Optional[pd.DataFrame] = None,
) -> None:
    """Renderiza aba de Rankings.

    Args:
        df: dados org-wide (pre-RLS) para rankings globais.
        df_scope: dados filtrados por RLS (escopo do usuario) para
            rankings por regiao e highlight. Se None, usa df.
        df_lojas_univ: universo de lojas ativas [LOJA, REGIAO] JA
            recortado pelo RLS do perfil (aplicar_rls no chamador).
            Habilita a visao de controle (sem producao) para
            _PERFIS_CONTROLE; ignorado para os demais perfis.
        df_cons_univ: idem para consultores [CONSULTOR, LOJA, REGIAO].
    """
    sac.divider(
        label="Rankings de Performance",
        icon="trophy-fill",
        align="left",
        color="blue",
    )

    _df_scope = df_scope if df_scope is not None else df
    _is_consultor = perfil == "consultor"
    _ver_regioes = perfil in ("admin", "gestor")

    # Visao de controle (sem producao) apenas p/ perfis de controle —
    # fail-closed: demais perfis nao recebem universo algum.
    if perfil not in _PERFIS_CONTROLE:
        df_lojas_univ = None
        df_cons_univ = None

    highlight_fn = _make_highlight_fn(_df_scope, perfil)

    top_n = st.number_input(
        "Exibir top",
        min_value=1,
        max_value=500,
        value=10,
        step=5,
        key="rankings_top_n",
    )

    somente_regiao = st.toggle(
        "Somente dados da regiao",
        key="rankings_somente_regiao",
        help=(
            "Restringe todos os rankings (todas as sub-abas) aos dados "
            "da regiao. Admin/gestor escolhem a regiao; demais perfis "
            "usam a regiao do proprio escopo."
        ),
    )
    if somente_regiao:
        df, _regioes_flag = _filtrar_somente_regiao(df, _df_scope, perfil)
        if _regioes_flag:
            df_lojas_univ = _filtrar_universo_regiao(
                df_lojas_univ, _regioes_flag,
            )
            df_cons_univ = _filtrar_universo_regiao(
                df_cons_univ, _regioes_flag,
            )
        else:
            df_lojas_univ = None
            df_cons_univ = None

    # st.pills (nao sac.tabs) pelo mesmo motivo da nav principal em
    # app.py: o sac roda em iframe e o CSS da lib tem
    # `.ant-tabs-nav-more{display:none}`, entao o que nao cabe na largura
    # fica INACESSIVEL. Sao ate 5 itens aqui — rotulos mais curtos que os
    # de Analiticos, logo quebra numa resolucao mais baixa, mas o mesmo
    # bug. O button group do st.pills quebra em linhas em vez de sumir.
    opcoes = []
    if not _is_consultor:
        opcoes.append("Lojas")
    opcoes.append("Consultores")
    if _ver_regioes:
        opcoes.append("Regioes")
    opcoes.append("Por Produto")
    opcoes.append("Por Aceleradores")

    menu = st.pills(
        "Sub-navegacao de Rankings",
        options=opcoes,
        default=opcoes[0],
        required=True,
        format_func=lambda r: f":material/{_ICONES_RANKINGS[r]}: {r}",
        label_visibility="collapsed",
        key="nav_rankings",
    )

    if menu == "Lojas":
        _render_lojas(
            df, df_metas, _df_scope, df_sup, top_n=top_n,
            highlight_fn=highlight_fn,
            com_secao_regiao=not somente_regiao,
            df_universo=df_lojas_univ,
        )

    elif menu == "Consultores":
        _render_consultores(
            df, df_metas, _df_scope, df_sup, top_n=top_n,
            highlight_fn=highlight_fn,
            com_secao_regiao=not somente_regiao,
            df_universo=df_cons_univ,
        )

    elif menu == "Regioes":
        _render_regioes(
            df, df_metas, df_sup, top_n=top_n, highlight_fn=highlight_fn,
            df_lojas_univ=df_lojas_univ, df_cons_univ=df_cons_univ,
        )

    elif menu == "Por Produto":
        if _is_consultor:
            tipo = "consultor"
        else:
            tipo_sel = sac.segmented(
                items=[
                    sac.SegmentedItem(label="Lojas", icon="shop"),
                    sac.SegmentedItem(label="Consultores", icon="people"),
                ],
                align="start",
                use_container_width=False,
            )
            tipo = "loja" if tipo_sel == "Lojas" else "consultor"

        rankings = calcular_ranking_por_produto(
            df,
            tipo=tipo,
            top_n=_SEM_LIMITE,
            df_supervisores=df_sup,
        )
        if rankings:
            _univ_prod = df_lojas_univ if tipo == "loja" else df_cons_univ
            for prod, rk in rankings.items():
                if not rk.empty:
                    with st.expander(prod, expanded=False):
                        _exibir_ranking_pinned(
                            rk, top_n, highlight_fn,
                            nome=f"ranking_produto_{tipo}_{_slug(prod)}",
                            key=f"exp_rk_prod_{tipo}_{_slug(prod)}",
                        )
                        _render_sem_producao_produto(
                            df, prod, _univ_prod, tipo, df_sup=df_sup,
                        )
        else:
            st.warning("Dados nao disponiveis")

    elif menu == "Por Aceleradores":
        if _is_consultor:
            tipo = "consultor"
        else:
            tipo_sel = sac.segmented(
                items=[
                    sac.SegmentedItem(label="Lojas", icon="shop"),
                    sac.SegmentedItem(label="Consultores", icon="people"),
                ],
                align="start",
                use_container_width=False,
            )
            tipo = "loja" if tipo_sel == "Lojas" else "consultor"

        rankings_acel = calcular_ranking_por_acelerador(
            df,
            tipo=tipo,
            top_n=_SEM_LIMITE,
            df_supervisores=df_sup,
        )
        if rankings_acel:
            for acel, rk in rankings_acel.items():
                if not rk.empty:
                    with st.expander(acel, expanded=False):
                        _exibir_ranking_pinned(
                            rk, top_n, highlight_fn,
                            nome=f"ranking_acelerador_{tipo}_{_slug(acel)}",
                            key=f"exp_rk_acel_{tipo}_{_slug(acel)}",
                        )
        else:
            st.warning("Dados nao disponiveis")
