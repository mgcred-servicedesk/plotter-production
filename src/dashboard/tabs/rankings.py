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
"""

from typing import Callable, Optional

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.rankings import (
    calcular_ranking_consultores,
    calcular_ranking_lojas,
    calcular_ranking_pontos,
    calcular_ranking_por_acelerador,
    calcular_ranking_por_produto,
)

_HighlightFn = Callable[[pd.DataFrame], pd.Series]

# top_n "infinito": obtem o ranking completo para que a fixacao do
# escopo do usuario abaixo do Top N (ver _exibir_ranking_pinned)
# possa preservar a posicao real das linhas cortadas.
_SEM_LIMITE = 10**9


def _divider(label: str, icon: str, color: str) -> None:
    sac.divider(label=label, icon=icon, align="left", color=color)


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
) -> None:
    """Exibe um ranking, aplicando o highlight do perfil se houver."""
    mask = highlight_fn(rk) if highlight_fn else None
    exibir_tabela(rk, highlight_mask=mask)


def _exibir_ranking_pinned(
    rk_full: pd.DataFrame,
    top_n: int,
    highlight_fn: Optional[_HighlightFn],
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
    _exibir_ranking(top, highlight_fn)


def _render_par(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    df_sup,
    tipo: str,
    top_n: int,
    suffix: str = "",
    top_label: bool = True,
    highlight_fn: Optional[_HighlightFn] = None,
) -> None:
    """Renderiza par de colunas: Atingimento | Pontos para loja ou consultor.

    top_label=False omite o prefixo "Top N" (visoes de regiao sem limite).
    highlight_fn: se fornecida, gera máscara de destaque para o ranking.
    """
    label = "Loja" if tipo == "loja" else "Consultor"
    prefix = f"Top {top_n} " if top_label else ""

    col1, col2 = st.columns(2)
    with col1:
        _divider(f"{prefix}{label}s por Atingimento{suffix}", "graph-up-arrow", "green")
        if tipo == "loja":
            rk = calcular_ranking_lojas(df, df_metas, top_n=top_n)
        else:
            rk = calcular_ranking_consultores(
                df, df_metas, top_n=top_n, df_supervisores=df_sup,
            )
        if not rk.empty:
            _exibir_ranking(rk, highlight_fn)
        else:
            st.info("Sem dados")

    with col2:
        _divider(f"{prefix}{label}s por Pontos{suffix}", "star-fill", "blue")
        rk = calcular_ranking_pontos(
            df, tipo=tipo, top_n=top_n,
            df_supervisores=(df_sup if tipo == "consultor" else None),
        )
        if not rk.empty:
            _exibir_ranking(rk, highlight_fn)
        else:
            st.info("Sem dados")


def _render_secao_regiao(
    df_scope: pd.DataFrame,
    df_full: pd.DataFrame,
    df_metas: pd.DataFrame,
    df_sup,
    tipo: str,
    key_prefix: str,
    highlight_fn: Optional[_HighlightFn] = None,
) -> None:
    """Seção 'por região' abaixo dos rankings globais.

    df_scope → determina a(s) região(ões) do usuário (respeita RLS).
    df_full  → fonte dos dados de ranking (todas as lojas/consultores
               da região, independente do escopo RLS do usuário).

    Supervisor vê apenas sua região no seletor, mas o ranking exibe
    TODAS as lojas daquela região para que saiba sua posição relativa.
    """
    if "REGIAO" not in df_scope.columns or df_scope.empty:
        return

    regioes = sorted(df_scope["REGIAO"].dropna().unique().tolist())
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
    df_reg = df_full[df_full["REGIAO"] == regiao]
    _render_par(
        df_reg, df_metas, df_sup, tipo=tipo,
        top_n=max(len(df_reg), 1),
        suffix=f" — {regiao}",
        top_label=False,
        highlight_fn=highlight_fn,
    )


def _render_lojas(
    df, df_metas, df_scope, df_sup, top_n: int,
    highlight_fn: Optional[_HighlightFn] = None,
) -> None:
    _render_par(df, df_metas, df_sup, tipo="loja", top_n=top_n, highlight_fn=highlight_fn)
    _render_secao_regiao(
        df_scope, df, df_metas, df_sup,
        tipo="loja", key_prefix="lojas", highlight_fn=highlight_fn,
    )


def _render_consultores(
    df, df_metas, df_scope, df_sup, top_n: int,
    highlight_fn: Optional[_HighlightFn] = None,
) -> None:
    _render_par(df, df_metas, df_sup, tipo="consultor", top_n=top_n, highlight_fn=highlight_fn)
    _render_secao_regiao(
        df_scope, df, df_metas, df_sup,
        tipo="consultor", key_prefix="cons", highlight_fn=highlight_fn,
    )


def _render_regioes(
    df, df_metas, df_sup, top_n: int,
    highlight_fn: Optional[_HighlightFn] = None,
) -> None:
    """Rankings intra-regiao com expander por regiao."""
    if "REGIAO" not in df.columns:
        st.warning("Dados de regiao nao disponiveis")
        return

    regioes = sorted(df["REGIAO"].dropna().unique().tolist())
    if not regioes:
        st.warning("Nenhuma regiao encontrada")
        return

    for regiao in regioes:
        df_reg = df[df["REGIAO"] == regiao]
        with st.expander(str(regiao), expanded=False):
            n_reg = max(len(df_reg), 1)
            _render_par(
                df_reg, df_metas, df_sup,
                tipo="loja", top_n=n_reg, suffix=f" — {regiao}",
                top_label=False, highlight_fn=highlight_fn,
            )
            _render_par(
                df_reg, df_metas, df_sup,
                tipo="consultor", top_n=n_reg, suffix=f" — {regiao}",
                top_label=False, highlight_fn=highlight_fn,
            )


def render_tab_rankings(
    df,
    df_metas,
    df_sup,
    df_scope: Optional[pd.DataFrame] = None,
    perfil: Optional[str] = None,
) -> None:
    """Renderiza aba de Rankings.

    Args:
        df: dados org-wide (pre-RLS) para rankings globais.
        df_scope: dados filtrados por RLS (escopo do usuario) para
            rankings por regiao e highlight. Se None, usa df.
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

    highlight_fn = _make_highlight_fn(_df_scope, perfil)

    top_n = st.number_input(
        "Exibir top",
        min_value=1,
        max_value=500,
        value=10,
        step=5,
        key="rankings_top_n",
    )

    tab_items = []
    if not _is_consultor:
        tab_items.append(sac.TabsItem(label="Lojas", icon="shop"))
    tab_items.append(sac.TabsItem(label="Consultores", icon="people"))
    if _ver_regioes:
        tab_items.append(sac.TabsItem(label="Regioes", icon="geo-alt"))
    tab_items.append(sac.TabsItem(label="Por Produto", icon="box-seam"))
    tab_items.append(sac.TabsItem(label="Por Aceleradores", icon="lightning-charge"))

    menu = sac.tabs(
        items=tab_items,
        align="start",
        variant="outline",
    )

    if menu == "Lojas":
        _render_lojas(df, df_metas, _df_scope, df_sup, top_n=top_n, highlight_fn=highlight_fn)

    elif menu == "Consultores":
        _render_consultores(df, df_metas, _df_scope, df_sup, top_n=top_n, highlight_fn=highlight_fn)

    elif menu == "Regioes":
        _render_regioes(df, df_metas, df_sup, top_n=top_n, highlight_fn=highlight_fn)

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
            for prod, rk in rankings.items():
                if not rk.empty:
                    with st.expander(prod, expanded=False):
                        _exibir_ranking_pinned(rk, top_n, highlight_fn)
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
                        _exibir_ranking_pinned(rk, top_n, highlight_fn)
        else:
            st.warning("Dados nao disponiveis")
