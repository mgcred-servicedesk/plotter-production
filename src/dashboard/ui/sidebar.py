"""
Componentes da sidebar do dashboard.

Reune tudo que e renderizado dentro de ``st.sidebar`` (toggle de
tema, card do usuario, expander de Periodo, "Visualizar Como",
filtros granulares Loja -> Consultor) e o par de funcoes que **le**
o estado escrito por esses filtros (``aplicar_filtros_ui``,
``filtrar_metas_ui``), aplicado sobre DataFrames ja recortados pelo
RLS de perfil.

Contrato de estado (``st.session_state``):

- ``ui_filtro_lojas``     -> list[str], lojas selecionadas
- ``ui_filtro_consultor`` -> str, consultor selecionado ("" = todos)
- ``_ui_lojas_ant``       -> list[str], selecao anterior de lojas
  (detecta troca de loja para resetar o consultor)
- ``visualizar_como``     -> dict de perfil simulado (admin/gestor)
- ``ano_padrao`` / ``mes_padrao`` -> int, periodo inicial resolvido
  a partir do ultimo mes com dado no banco
- ``periodo_padrao_carregado``   -> bool, trava que resolve esse
  padrao uma unica vez por sessao

Quem escreve essas chaves e a sidebar; quem le sao
``aplicar_filtros_ui`` / ``filtrar_metas_ui`` e o ``app.py``
(invalidacao de cache por chave de filtro).

O modulo **nao** conhece chave de cache de outros modulos: o botao
"Atualizar Dados" so dispara o callback ``on_refresh`` recebido de
``app.py`` (ver ``render_periodo``).
"""

import html
from datetime import datetime
from typing import Callable, Optional

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.config.settings import MESES_PT_TITULO
from src.dashboard.auth import (
    fazer_logout,
    usuario_logado,
)
from src.dashboard.loaders import (
    carregar_consultores_ativos,
    carregar_lojas_ativas,
    carregar_ultimo_periodo,
)
from src.dashboard.rls import aplicar_rls
from src.dashboard.ui.theme import (
    get_theme_mode,
    set_theme_mode,
)


def render_theme_toggle() -> None:
    """Segmented 3-state: light / system / dark.

    Renderiza tres botoes horizontais estilo macOS. O
    botao correspondente ao ``theme_mode`` atual recebe
    ``type='primary'``. Ao clicar, persiste via
    ``set_theme_mode`` e rerun.
    """
    current = get_theme_mode()
    opcoes = [
        ("light", ":material/light_mode:", "Claro"),
        ("system", ":material/computer:", "Sistema"),
        ("dark", ":material/dark_mode:", "Escuro"),
    ]
    st.markdown(
        '<div class="mg-theme-seg-wrapper"></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(3, gap="small")
    for col, (mode, icon, label) in zip(cols, opcoes):
        with col:
            if st.button(
                icon,
                key=f"theme_mode_{mode}",
                help=f"Tema {label}",
                width="stretch",
            ):
                if mode != current:
                    set_theme_mode(mode)
                    st.rerun()


def render_sidebar_usuario():
    """Informacoes do usuario e logout."""
    user = usuario_logado()
    if not user:
        return

    # Mapa de perfil -> classe CSS do badge
    _badge_map = {
        "admin": ("mg-badge-admin", "Admin"),
        "gestor": ("mg-badge-gestor", "Gestor"),
        "gerente_comercial": ("mg-badge-gerente", "Gerente"),
        "supervisor": ("mg-badge-supervisor", "Supervisor"),
    }
    badge_cls, badge_lbl = _badge_map.get(
        user["perfil"], ("mg-badge-admin", user["perfil"])
    )

    # Iniciais do usuario para avatar
    partes = user["nome"].split()
    iniciais = (
        (partes[0][0] + partes[-1][0]).upper()
        if len(partes) > 1
        else partes[0][:2].upper()
    )

    escopo_html = ""
    if user["perfil"] not in ("admin", "gestor") and user.get("escopo"):
        escopo_txt = ", ".join(user["escopo"])
        escopo_html = (
            f'<div class="mg-user-escopo">{html.escape(escopo_txt)}</div>'
        )

    st.markdown(
        f'<div class="mg-sidebar-user">'
        f'<div class="mg-avatar">{html.escape(iniciais)}</div>'
        f'<div class="mg-user-info">'
        f'<div class="mg-user-name">{html.escape(user["nome"])}</div>'
        f'<span class="mg-badge {badge_cls}">{html.escape(badge_lbl)}</span>'
        f"{escopo_html}"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="mg-sidebar-actions"></div>',
        unsafe_allow_html=True,
    )
    col_cfg, col_sair = st.columns(2)

    with col_cfg:
        icon = ":material/settings:"
        label = "Config"
        if user["perfil"] == "admin":
            icon = ":material/group:"
            label = "Usuários"
        if st.button(
            f"{icon} {label}",
            width="stretch",
        ):
            st.session_state["mostrar_config"] = not st.session_state.get(
                "mostrar_config", False
            )
            st.rerun()

    with col_sair:
        if st.button(
            ":material/logout: Sair",
            width="stretch",
        ):
            fazer_logout()
            st.rerun()


def render_periodo(*, on_refresh: Callable[[], None]) -> tuple[int, int]:
    """Expander "Período": seletores de Ano/Mes + botao "Atualizar Dados".

    Retorna ``(ano, mes)``. E a unica funcao de render deste modulo que
    devolve valor: o periodo escolhido governa o resto do dashboard
    (carga dos frames, titulo do header, chaves de cache), entao ele
    volta pelo ``return`` em vez de por ``session_state``.

    O padrao inicial vem do ultimo periodo COM DADO no banco
    (``carregar_ultimo_periodo``), resolvido uma unica vez por sessao e
    guardado em ``ano_padrao`` / ``mes_padrao``; sem resposta do banco,
    cai para o mes corrente. A flag ``periodo_padrao_carregado`` e o que
    impede que esse default sobrescreva a escolha do usuario a cada
    rerun.

    ``on_refresh`` e chamado no clique de "Atualizar Dados", antes do
    ``st.rerun()``. A sidebar so sabe que houve o PEDIDO de refresh;
    **quais** caches morrem e decisao de quem os possui — o chamador
    (``app.py``) compoe a limpeza a partir das funcoes expostas pelos
    modulos donos. Assim este modulo nao carrega o nome de nenhuma chave
    de cache de KPI ou de aba.
    """
    with st.expander(
        ":material/calendar_month: Período",
        expanded=True,
    ):
        _anos = [2024, 2025, 2026]
        if "periodo_padrao_carregado" not in st.session_state:
            _ultimo = carregar_ultimo_periodo()
            if _ultimo:
                st.session_state["ano_padrao"] = _ultimo["ano"]
                st.session_state["mes_padrao"] = _ultimo["mes"]
            else:
                _hoje = datetime.now()
                st.session_state["ano_padrao"] = _hoje.year
                st.session_state["mes_padrao"] = _hoje.month
            st.session_state["periodo_padrao_carregado"] = True

        _ano_padrao = st.session_state.get("ano_padrao", 2026)
        _mes_padrao = st.session_state.get("mes_padrao", 1)
        _idx_ano = (
            _anos.index(_ano_padrao) if _ano_padrao in _anos else len(_anos) - 1
        )

        c_ano, c_mes = st.columns(2)
        with c_ano:
            ano = st.selectbox("Ano", _anos, index=_idx_ano)
        with c_mes:
            mes = st.selectbox(
                "Mes",
                list(range(1, 13)),
                index=_mes_padrao - 1,
                format_func=lambda x: MESES_PT_TITULO[x],
            )

        # ── Botao para forcar atualizacao do cache ──
        if st.button(
            ":material/refresh: Atualizar Dados",
            help=(
                "Limpa o cache e recarrega todos os dados "
                "do banco. Use quando souber que os dados "
                "foram atualizados recentemente."
            ),
            key="btn_refresh_cache",
            width="stretch",
        ):
            on_refresh()
            st.rerun()

    return ano, mes


def _limpar_filtros_ui() -> None:
    """Apaga sub-filtros de UI (Loja, Consultor)."""
    st.session_state.pop("ui_filtro_lojas", None)
    st.session_state.pop("ui_filtro_consultor", None)
    st.session_state.pop("_ui_lojas_ant", None)


def aplicar_filtros_ui(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica filtros granulares de loja/consultor sobre df já com RLS."""
    lojas = st.session_state.get("ui_filtro_lojas") or []
    consultor = st.session_state.get("ui_filtro_consultor") or ""
    if lojas and "LOJA" in df.columns:
        df = df[df["LOJA"].isin(lojas)].copy()
    if consultor and "CONSULTOR" in df.columns:
        df = df[df["CONSULTOR"] == consultor].copy()
    return df


def filtrar_metas_ui(
    df_metas: pd.DataFrame, df_f: pd.DataFrame
) -> pd.DataFrame:
    """Restringe metas à seleção granular da sidebar (loja/consultor).

    Distinto do RLS de perfil (``aplicar_rls_metas``): aqui o filtro
    segue a seleção explícita do usuário. Quando ele seleciona lojas,
    restringe a essas lojas; quando seleciona apenas um consultor,
    usa as lojas presentes nos dados já filtrados (``df_f``).
    """
    if "LOJA" not in df_metas.columns:
        return df_metas
    lojas_ui = st.session_state.get("ui_filtro_lojas") or []
    if lojas_ui:
        return df_metas[df_metas["LOJA"].isin(lojas_ui)].copy()
    if "LOJA" in df_f.columns:
        lojas = df_f["LOJA"].unique()
        return df_metas[df_metas["LOJA"].isin(lojas)].copy()
    return df_metas


def _opcoes_consultor(
    df_source: pd.DataFrame,
    df_sup: pd.DataFrame,
    df_universo: Optional[pd.DataFrame] = None,
) -> list[str]:
    """Lista ordenada de consultores para o filtro, sem supervisores.

    União de quem tem produção no período (``df_source``) com o universo
    de consultores ativos (``df_universo``, já recortado por RLS/loja
    pelo chamador) — sem a união, um consultor ativo sem venda no
    período (comum em loja pequena ou no mês corrente) some do filtro
    mesmo existindo. Mesmo padrão já usado para o filtro de Loja
    (``carregar_lojas_ativas`` união com ``df``), só replicado aqui.
    """
    supervisores: set = set()
    if not df_sup.empty and "SUPERVISOR" in df_sup.columns:
        supervisores = set(df_sup["SUPERVISOR"].dropna())

    consultores_scope: set = set()
    if df_universo is not None and "CONSULTOR" in df_universo.columns:
        consultores_scope |= set(df_universo["CONSULTOR"].dropna())
    if "CONSULTOR" in df_source.columns:
        consultores_scope |= set(df_source["CONSULTOR"].dropna())

    return sorted(c for c in consultores_scope if c not in supervisores)


def _render_consultor_subselect(
    df_source: pd.DataFrame,
    df_sup: pd.DataFrame,
    key: str,
    df_universo: Optional[pd.DataFrame] = None,
) -> None:
    """Renderiza o selectbox de consultor e persiste em ui_filtro_consultor.

    Exclui supervisores da lista. Reseta automaticamente se o consultor
    anterior não está mais nas opções (loja mudou).

    ``help`` incentiva digitar em vez de rolar: o popover do BaseWeb/
    React Aria tem um bug de posicionamento upstream (reproduzido via
    DevTools em 2026-08) que corta a lista quando o campo está fundo
    na sidebar — CSS não resolve porque o offset errado é calculado em
    JS a cada abertura, não é uma propriedade estática. Ver
    docs/agents/progress/2026-08-06-popover-consultor-cortado-bug-upstream.md.
    """
    consultores = _opcoes_consultor(df_source, df_sup, df_universo)

    if not consultores:
        st.session_state["ui_filtro_consultor"] = ""
        return

    opcoes = [""] + consultores
    atual = st.session_state.get("ui_filtro_consultor", "")
    idx = opcoes.index(atual) if atual in opcoes else 0

    sel = st.selectbox(
        "Consultor",
        opcoes,
        index=idx,
        key=key,
        format_func=lambda x: "Todos" if x == "" else x,
        help="Digite parte do nome para filtrar.",
    )
    st.session_state["ui_filtro_consultor"] = sel


def render_sidebar_visualizar_como(df_full):
    """Seletor 'Visualizar como' para admin e gestor.

    Define apenas o perfil simulado e seu escopo de RLS
    (regiao/loja). A cadeia granular Loja → Consultor é
    renderizada por render_sidebar_filtros_perfil, que já
    considera o perfil efetivo (inclusive o simulado).
    """
    user = usuario_logado()
    if not user or user["perfil"] not in ("admin", "gestor"):
        return

    st.markdown(
        '<div class="mg-sim-card">'
        '<div class="mg-sim-header">'
        '<span class="mg-sim-icon">👁️</span>'
        '<span class="mg-sim-title">Visualizar Como</span>'
        "</div></div>",
        unsafe_allow_html=True,
    )

    opcoes = [
        "Admin (padrao)",
        "Gerente Comercial",
        "Supervisor",
        "Consultor",
    ]
    sel = st.selectbox(
        "Simular perfil",
        opcoes,
        key="sel_visualizar_perfil",
        label_visibility="collapsed",
    )

    # Limpa sub-filtros granulares ao trocar o perfil simulado
    if st.session_state.get("_vc_sel_ant") != sel:
        _limpar_filtros_ui()
        st.session_state["_vc_sel_ant"] = sel

    if sel == "Admin (padrao)":
        st.session_state.pop("visualizar_como", None)

    elif sel == "Gerente Comercial":
        # Regioes ATUAIS (organograma) a partir das lojas ativas —
        # inclui regioes sem producao no periodo. O escopo simulado e
        # casado contra REGIAO_ATUAL no aplicar_rls. Uniao com df_full
        # como fallback.
        _regs: set[str] = set()
        _df_ativas = carregar_lojas_ativas()
        if "REGIAO_ATUAL" in _df_ativas.columns:
            _regs |= set(_df_ativas["REGIAO_ATUAL"].dropna())
        _col_reg = (
            "REGIAO_ATUAL"
            if "REGIAO_ATUAL" in df_full.columns
            else "REGIAO"
        )
        if _col_reg in df_full.columns:
            _regs |= set(df_full[_col_reg].dropna())
        regioes = sorted(r for r in _regs if r)
        escopo = st.multiselect(
            "Regioes",
            regioes,
            key="sel_visualizar_regioes",
        )
        if escopo:
            st.session_state["visualizar_como"] = {
                "perfil": "gerente_comercial",
                "escopo": escopo,
            }
        else:
            st.session_state.pop("visualizar_como", None)

    elif sel == "Supervisor":
        # Lojas ATIVAS (todas) uniao com as que tem producao no periodo,
        # p/ simular supervisor mesmo de loja zerada.
        _lojas: set[str] = set()
        _df_ativas = carregar_lojas_ativas()
        if "LOJA" in _df_ativas.columns:
            _lojas |= set(_df_ativas["LOJA"].dropna())
        if "LOJA" in df_full.columns:
            _lojas |= set(df_full["LOJA"].dropna())
        lojas = sorted(lj for lj in _lojas if lj)
        escopo = st.multiselect(
            "Lojas",
            lojas,
            key="sel_visualizar_lojas",
        )
        if escopo:
            st.session_state["visualizar_como"] = {
                "perfil": "supervisor",
                "escopo": escopo,
            }
        else:
            st.session_state.pop("visualizar_como", None)

    elif sel == "Consultor":
        consultores = (
            sorted(df_full["CONSULTOR"].dropna().unique().tolist())
            if "CONSULTOR" in df_full.columns
            else []
        )
        sel_cons = st.selectbox(
            "Consultor",
            [""] + consultores,
            key="sel_visualizar_consultor",
            help="Digite parte do nome para filtrar.",
        )
        if sel_cons:
            st.session_state["visualizar_como"] = {
                "perfil": "consultor",
                "escopo": [sel_cons],
            }
        else:
            st.session_state.pop("visualizar_como", None)

    # st.rerun() nao e mais necessario aqui: a sidebar agora e
    # renderizada em main() ANTES de aplicar_rls(), entao o novo
    # valor de `visualizar_como` ja e respeitado no mesmo rerun
    # disparado automaticamente pelos widgets (selectbox/multiselect).


def render_sidebar_filtros_perfil(
    df: pd.DataFrame,
    df_sup: pd.DataFrame,
    role: str,
) -> None:
    """Filtros granulares Loja → Consultor para Gerente e Supervisor nativos.

    Renderiza dentro do sidebar. Escreve em ui_filtro_lojas e
    ui_filtro_consultor — os mesmos keys usados por aplicar_filtros_ui.
    Não exibe nada para admin/gestor (eles usam o Visualizar Como).
    """
    if role not in ("gerente_comercial", "supervisor"):
        return

    sac.divider(
        label="Filtrar Por",
        icon="funnel-fill",
        align="left",
        color="blue",
    )

    if role == "gerente_comercial":
        # Lojas ATIVAS da regiao do gerente (mesmo zeradas na producao):
        # tabela lojas -> RLS por REGIAO_ATUAL -> uniao com as que tem
        # producao no periodo. Assim o gerente enxerga/seleciona toda a
        # sua carteira, nao apenas quem vendeu.
        lojas_scope: set[str] = set()
        _df_ativas = aplicar_rls(carregar_lojas_ativas())
        if "LOJA" in _df_ativas.columns:
            lojas_scope |= set(_df_ativas["LOJA"].dropna())
        if "LOJA" in df.columns:
            lojas_scope |= set(df["LOJA"].dropna())
        lojas_disp = sorted(lj for lj in lojas_scope if lj)
        if not lojas_disp:
            return

        lojas_ant = st.session_state.get("_ui_lojas_ant") or []
        lojas_sel = st.multiselect(
            "Loja",
            lojas_disp,
            default=[lj for lj in lojas_ant if lj in lojas_disp],
            key="sel_filtro_lojas",
            placeholder="Todas as lojas",
        )
        if set(lojas_sel) != set(lojas_ant):
            st.session_state["ui_filtro_consultor"] = ""
            st.session_state["_ui_lojas_ant"] = lojas_sel
        st.session_state["ui_filtro_lojas"] = lojas_sel

        if lojas_sel:
            df_lojas = df[df["LOJA"].isin(lojas_sel)]
            _univ_cons_ger = aplicar_rls(carregar_consultores_ativos())
            if "LOJA" in _univ_cons_ger.columns:
                _univ_cons_ger = _univ_cons_ger[
                    _univ_cons_ger["LOJA"].isin(lojas_sel)
                ]
            _render_consultor_subselect(
                df_lojas, df_sup, key="sel_filtro_cons_ger",
                df_universo=_univ_cons_ger,
            )
        else:
            st.session_state["ui_filtro_consultor"] = ""

    elif role == "supervisor":
        _univ_cons_sup = aplicar_rls(carregar_consultores_ativos())
        _render_consultor_subselect(
            df, df_sup, key="sel_filtro_cons_sup", df_universo=_univ_cons_sup,
        )
        st.session_state["ui_filtro_lojas"] = []
