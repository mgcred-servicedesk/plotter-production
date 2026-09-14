"""
Row-Level Security (RLS) para o dashboard.

Filtra DataFrames de acordo com o perfil e escopo do
usuário logado, garantindo que cada papel veja apenas
os dados autorizados.

Perfis:
    admin             → sem filtro (todos os dados)
    gestor            → sem filtro (visao global)
    gerente_comercial → filtra por REGIAO (escopo = regiões)
    supervisor        → filtra por LOJA (escopo = lojas)
    consultor         → filtra por CONSULTOR (escopo = nomes)
"""

from typing import Callable, Mapping, NamedTuple, Optional

import pandas as pd
import streamlit as st


class DecisaoRls(NamedTuple):
    """Decisao de autorizacao, SEM o DataFrame na jogada.

    Tres estados possiveis, e so tres:

    - ``global_=True`` — admin/gestor, sem recorte;
    - ``coluna`` preenchida — recortar por ``coluna in escopo``;
    - ambos vazios — **negar**: perfil ausente, escopo vazio ou role
      desconhecido.

    Existe porque a decisao de QUEM ve o que estava escrita duas vezes,
    e as duas divergiram: ``aplicar_rls`` negava acesso sem escopo,
    enquanto o recorte de Reconquista (``loaders._filtro_rls_reconquista``)
    devolvia a base inteira no mesmo caso. Com a decisao em um lugar so,
    cada adaptador de dataset fica responsavel apenas pela parte que e
    dele: se a coluna de escopo nao existe NAQUELE frame, ele nega.
    """

    global_: bool
    coluna: Optional[str]
    escopo: tuple


def decidir_rls(colunas_por_perfil: Mapping[str, str]) -> DecisaoRls:
    """Resolve o recorte do perfil efetivo, dado o mapa role -> coluna.

    ``colunas_por_perfil`` e do CHAMADOR porque o nome da coluna muda
    com o dataset (``REGIAO``/``LOJA``/``CONSULTOR`` nos frames do
    dashboard; ``regiao``/``loja``/``consultor`` minusculos na view de
    Reconquista). A regra de autorizacao, essa, e a mesma para todos.

    Fail-closed em toda ausencia de informacao — ver ``DecisaoRls``.
    """
    perfil = _obter_perfil_efetivo()
    if not perfil:
        return DecisaoRls(False, None, ())

    role = perfil.get("perfil")
    if role in ("admin", "gestor"):
        return DecisaoRls(True, None, ())

    escopo = perfil.get("escopo") or []
    coluna = colunas_por_perfil.get(role)
    if not escopo or coluna is None:
        return DecisaoRls(False, None, ())

    return DecisaoRls(False, coluna, tuple(escopo))


def _obter_perfil_efetivo() -> Optional[dict]:
    """
    Retorna o perfil efetivo (considera 'visualizar como'
    para admin e gestor).
    """
    usuario = st.session_state.get("usuario_logado")
    if not usuario:
        return None

    visualizar_como = st.session_state.get("visualizar_como")
    if visualizar_como and usuario.get("perfil") in ("admin", "gestor"):
        return visualizar_como

    return usuario


def aplicar_rls(
    df: pd.DataFrame,
    coluna_regiao: str = "REGIAO",
    coluna_loja: str = "LOJA",
    coluna_consultor: str = "CONSULTOR",
    coluna_regiao_atual: str = "REGIAO_ATUAL",
) -> pd.DataFrame:
    """
    Aplica filtro de segurança por linha no DataFrame.

    Args:
        df: DataFrame a ser filtrado.
        coluna_regiao: Nome da coluna de região.
        coluna_loja: Nome da coluna de loja.
        coluna_consultor: Nome da coluna de consultor.

    Returns:
        DataFrame filtrado conforme o perfil do usuário.
    """
    # Demais perfis SEMPRE exigem escopo. Fail-closed: sem escopo,
    # coluna de escopo ausente ou perfil desconhecido => nao expoe
    # nada (DataFrame vazio), nunca a base inteira. A obrigatoriedade
    # de escopo desses perfis e garantida no cadastro
    # (auth.criar_usuario / editar_usuario); aqui e defesa em
    # profundidade contra escopo vazio vindo de outras origens.
    # Gerente comercial: recorte pela regiao ATUAL da loja (organograma
    # vigente), nao pela regiao point-in-time. Assim enxerga o historico
    # completo das lojas que sao dele HOJE. Fallback para coluna_regiao
    # quando a df ainda nao carrega REGIAO_ATUAL (equivale ao estado
    # pre-remanejamento, em que regiao == regiao atual).
    col_gerente = (
        coluna_regiao_atual
        if coluna_regiao_atual in df.columns
        else coluna_regiao
    )
    decisao = decidir_rls({
        "gerente_comercial": col_gerente,
        "supervisor": coluna_loja,
        "consultor": coluna_consultor,
    })

    # Admin e gestao: visao global (sem filtro).
    if decisao.global_:
        return df

    if decisao.coluna is None or decisao.coluna not in df.columns:
        return df.iloc[0:0].copy()

    return df[df[decisao.coluna].isin(decisao.escopo)].copy()


def aplicar_rls_metas(
    df_metas: pd.DataFrame,
    df_dados: pd.DataFrame,
    coluna_loja: str = "LOJA",
    coluna_regiao: str = "REGIAO",
    coluna_regiao_atual: str = "REGIAO_ATUAL",
) -> pd.DataFrame:
    """
    Filtra metas conforme o perfil/escopo RLS do usuário.

    NÃO usa a presença de contratos como proxy de escopo: uma
    loja ativa dentro do escopo conta sua meta mesmo sem nenhum
    contrato no período (ex.: loja recém-aberta). Apenas o perfil
    ``consultor`` (cujo escopo é por nome) recai sobre as lojas
    onde o consultor tem contratos.
    """
    perfil = _obter_perfil_efetivo()
    if not perfil:
        return df_metas.iloc[0:0].copy()

    role = perfil.get("perfil")
    escopo = perfil.get("escopo", [])

    if role in ("admin", "gestor"):
        return df_metas

    if role == "gerente_comercial" and escopo:
        # Recorte pela regiao ATUAL (lojas do gerente hoje); fallback
        # para REGIAO quando a df ainda nao carrega REGIAO_ATUAL.
        col = (
            coluna_regiao_atual
            if coluna_regiao_atual in df_metas.columns
            else coluna_regiao
        )
        if col in df_metas.columns:
            return df_metas[df_metas[col].isin(escopo)].copy()
        return df_metas.iloc[0:0].copy()

    if role == "supervisor" and escopo:
        if coluna_loja in df_metas.columns:
            return df_metas[df_metas[coluna_loja].isin(escopo)].copy()
        return df_metas.iloc[0:0].copy()

    if role == "consultor" and escopo:
        # Escopo do consultor é por nome; aproxima o escopo de loja
        # pelas lojas onde ele tem contratos.
        tem_loja = (
            coluna_loja in df_metas.columns
            and coluna_loja in df_dados.columns
        )
        if tem_loja:
            lojas_permitidas = df_dados[coluna_loja].unique()
            return df_metas[
                df_metas[coluna_loja].isin(lojas_permitidas)
            ].copy()
        return df_metas.iloc[0:0].copy()

    # Fail-closed: perfil sem escopo (ou desconhecido) nao ve metas.
    return df_metas.iloc[0:0].copy()


def aplicar_rls_supervisores(
    df_supervisores: pd.DataFrame,
    df_dados: pd.DataFrame,
    coluna_regiao: str = "REGIAO",
    coluna_loja: str = "LOJA",
) -> pd.DataFrame:
    """
    Filtra supervisores conforme o escopo RLS.
    """
    perfil = _obter_perfil_efetivo()
    if not perfil:
        return df_supervisores.iloc[0:0].copy()

    role = perfil.get("perfil")
    escopo = perfil.get("escopo", [])

    if role in ("admin", "gestor"):
        return df_supervisores

    if role == "gerente_comercial" and escopo:
        if coluna_regiao in df_supervisores.columns:
            return df_supervisores[df_supervisores[coluna_regiao].isin(escopo)].copy()

    if role == "supervisor" and escopo:
        if (
            coluna_loja in df_supervisores.columns
            and coluna_loja in df_dados.columns
        ):
            lojas_permitidas = df_dados[coluna_loja].unique()
            return df_supervisores[
                df_supervisores[coluna_loja].isin(lojas_permitidas)
            ].copy()

    if role == "consultor" and escopo:
        # Consultor vê apenas supervisores da(s) loja(s)
        # onde ele tem contratos.
        if coluna_loja in df_supervisores.columns and (coluna_loja in df_dados.columns):
            lojas_permitidas = df_dados[coluna_loja].unique()
            return df_supervisores[
                df_supervisores[coluna_loja].isin(lojas_permitidas)
            ].copy()

    # Fail-closed: perfil sem escopo (ou desconhecido) nao ve supervisores.
    return df_supervisores.iloc[0:0].copy()


# ══════════════════════════════════════════════════════
# Reconquista — adaptador do recorte por perfil
#
# Vive aqui, e nao em `loaders.py`, desde a Etapa 2 da revisao de
# 09/2026: recorte por perfil e autorizacao, nao carga. Foi a
# convivencia das duas implementacoes em arquivos diferentes que
# deixou a divergencia passar (a da Reconquista liberava a base
# inteira onde `aplicar_rls` negava — corrigido na Etapa 1). Agora as
# duas moram lado a lado e dividem `decidir_rls`.
#
# O vocabulario da view e minusculo (`regiao`/`loja`/`consultor`), ao
# contrario dos frames do dashboard — por isso o mapa de colunas e
# explicito aqui.
# ══════════════════════════════════════════════════════


def _filtro_rls_reconquista() -> Callable | None:
    """Funcao de recorte por perfil dos detalhes de Reconquista.

    A view expoe `regiao`, `loja` e `consultor` em texto (minusculos,
    ao contrario dos frames do dashboard) — por isso o mapa de colunas
    vai daqui para `decidir_rls`, que so decide QUEM ve o que.

    Devolve ``None`` apenas para admin/gestor, o unico caso em que nao
    ha recorte a aplicar. Todo o resto recebe uma funcao: ou o recorte
    por escopo, ou `_negar` (frame vazio, schema preservado).

    Fail-closed em tres pontos que antes devolviam a base inteira:
    perfil ausente, escopo vazio e role desconhecido caem em `_negar`;
    e coluna de escopo ausente NO FRAME tambem nega, em vez de entregar
    o frame como veio. Era a divergencia apontada na revisao — mesmo
    perfil, `aplicar_rls` negava e a Reconquista liberava.

    Extraida de `_filtrar_rls_reconquista` para que a lista completa
    (`clientes_todos`) passe pelo MESMO recorte dos cortes mensais:
    RLS antes de render, sem uma segunda implementacao para divergir.
    """
    decisao = decidir_rls({
        "gerente_comercial": "regiao",
        "supervisor": "loja",
        "consultor": "consultor",
    })
    if decisao.global_:
        return None

    def _negar(df):
        if df is None:
            return df
        return df.iloc[0:0].copy()

    if decisao.coluna is None:
        return _negar

    coluna, escopo = decisao.coluna, decisao.escopo

    def _filtra(df):
        if df is None or df.empty:
            return df
        if coluna not in df.columns:
            return _negar(df)
        return df[df[coluna].isin(escopo)].copy()

    return _filtra


def _filtrar_rls_reconquista(dados: dict) -> dict:
    """Aplica RLS sobre `clientes`/`clientes_ant`/`clientes_prox`."""
    _filtra = _filtro_rls_reconquista()
    if _filtra is None:
        return dados

    return {
        **dados,
        "clientes": _filtra(dados.get("clientes")),
        "clientes_ant": _filtra(dados.get("clientes_ant")),
        "clientes_prox": _filtra(dados.get("clientes_prox")),
    }


def obter_regioes_permitidas(
    regioes_disponiveis: list[str],
) -> list[str]:
    """
    Retorna as regiões que o usuário pode ver no filtro
    da sidebar.

    Admin e gerente_comercial veem as regiões do escopo.
    Supervisor não filtra por região (já filtrado por loja).
    """
    perfil = _obter_perfil_efetivo()
    if not perfil:
        # Fail-closed como as `aplicar_rls_*`: sem perfil nao se
        # monta o seletor. `[]` ja e o valor de "nao exibe filtro de
        # regiao" (mesmo retorno de supervisor/consultor); antes daqui
        # saia a lista completa de regioes da empresa.
        return []

    role = perfil.get("perfil")
    escopo = perfil.get("escopo", [])

    if role in ("admin", "gestor"):
        return regioes_disponiveis

    if role == "gerente_comercial" and escopo:
        filtradas = [r for r in regioes_disponiveis if r in escopo]
        if len(filtradas) > 1:
            return ["Todas"] + filtradas
        return filtradas

    # Supervisor e consultor: não exibem filtro de região
    return []
