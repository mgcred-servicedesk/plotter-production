"""
Dashboard interativo de vendas — MGCred.

Entrypoint principal para deploy no Streamlit Cloud.
Consome dados diretamente do banco Supabase (PostgreSQL),
via views v_* e RPCs (ex.: obter_pontuacao_periodo).
Autocontido: nao depende dos modulos de KPI antigos
(kpi_dashboard.py, kpi_analiticos.py) nem dos loaders
de planilha (column_mapper.py, pontuacao_loader.py).

Frontend: streamlit-antd-components para navegacao,
tabelas via st.dataframe, CSS design system customizado.
"""

import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

sys.path.insert(0, str(Path(__file__).parent))

from src.dashboard.auth import (
    tela_login,
    usuario_logado,
)
from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.gerais import (
    calcular_kpis_gerais,
    calcular_kpis_analise,
    calcular_kpis_cancelados,
    calcular_kpis_qtd_produtos,
    calcular_medias_du_por_nivel,
    calcular_medias_organizacao,
    calcular_metas_produto_diarias,
)
from src.dashboard.pages.config import render_pagina_config
from src.dashboard.pages.dashboard_pontuacao import (
    render_dashboard_pontuacao,
)
from src.dashboard.pages.detalhes_cards import (
    render_detalhe_cancelados,
    render_detalhe_em_analise,
    render_detalhe_media_consultor,
    render_detalhe_media_loja,
)
from src.dashboard.loaders import (
    aplicar_nomes_display_produto,
    carregar_consultores_ativos,
    carregar_contratos_pagos_intervalo,
    carregar_digitacao_diaria_detalhe,
    carregar_universo_lojas,
    carregar_metas_produto_consultor,
    carregar_pagamentos_online,
    carregar_periodo_dashboard,
    carregar_pontuacao_efetiva,
    carregar_reconquista,
    carregar_ultimo_periodo,
    consolidar_dados,
)
from src.dashboard.permissions import pode_ver
from src.dashboard.rls import (
    aplicar_rls,
    aplicar_rls_metas,
)
from src.dashboard.tabs.analiticos import render_tab_analiticos
from src.dashboard.tabs.detalhes import render_tab_detalhes
from src.dashboard.tabs.em_analise import render_tab_em_analise
from src.dashboard.tabs.evolucao import render_tab_evolucao
from src.dashboard.tabs.gestao_consultores import render_tab_gestao
from src.dashboard.tabs.pagamentos_online import render_tab_pagamentos_online
from src.dashboard.tabs.produtos import render_tab_produtos
from src.dashboard.tabs.rankings import render_tab_rankings
from src.dashboard.tabs.regioes import render_tab_regioes
from src.dashboard.ui.header import (
    render_header,
    render_status_bar,
)
from src.dashboard.ui.kpi_cards import (  # noqa: F401  (re-exports: criar_cards_metas_produto, criar_cards_qtd_produto)
    criar_cards_indicadores_principais,
    criar_cards_metas_produto,
    criar_cards_qtd_produto,
)
from src.dashboard.ui.kpi_cards_reforma import render_kpis_reforma
from src.dashboard.ui.prioridades_acao import render_prioridades_acao
from src.dashboard.ui.resumo_executivo import render_resumo_executivo
from src.dashboard.ui.sidebar import (
    aplicar_filtros_ui,
    filtrar_metas_ui,
    render_sidebar_filtros_perfil,
    render_sidebar_usuario,
    render_sidebar_visualizar_como,
    render_theme_toggle,
)
from src.dashboard.ui.skeleton import render_skeleton
from src.dashboard.ui.theme import (
    aplicar_tema,
    carregar_estilos_customizados,
    get_theme,
    ocultar_widgets_nativos,
    render_overlay_fresh_login,
)
from src.dashboard.ui.theme_claro_avancado import aplicar_tema_claro_avancado
from src.shared.dias_uteis import calcular_dias_uteis

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Dashboard de Vendas - MGCred",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════
# Helpers de main() — blocos coesos extraidos
# ══════════════════════════════════════════════════════


def _render_aviso_pontuacao_fallback(df_pontos: pd.DataFrame) -> None:
    """Expander avisando quando ha categorias com pontuacao de fallback."""
    if df_pontos.empty:
        return
    fallbacks = df_pontos[df_pontos["is_fallback"] == True]  # noqa
    if fallbacks.empty:
        return
    with st.expander(
        "Info: Pontuacao usando dados de periodo anterior (fallback)",
        expanded=False,
    ):
        st.info(
            "Algumas categorias estao usando pontuacao de um "
            "periodo anterior pois o periodo atual nao tem dados."
        )
        exibir_tabela(
            fallbacks[
                ["categoria_codigo", "pontos", "periodo_origem"]
            ].rename(
                columns={
                    "categoria_codigo": "Categoria",
                    "pontos": "Pontos",
                    "periodo_origem": "Origem",
                }
            )
        )


def _ritmo_organizacao(
    role: str | None,
    df_f: pd.DataFrame,
    df_full: pd.DataFrame,
    df_sup_full: pd.DataFrame,
) -> tuple[pd.DataFrame | None, int]:
    """Base e normalizador do ritmo da organizacao (media DU de referencia).

    Para supervisor/consultor, restringe df_full as regioes presentes em
    df_f e normaliza por nº de lojas (supervisor) ou consultores
    não-supervisor (consultor). Outros perfis: (None, 1).
    """
    if role not in ("supervisor", "consultor") or df_f.empty:
        return None, 1
    if "REGIAO" not in df_f.columns:
        return None, 1
    regioes = df_f["REGIAO"].dropna().unique()
    df_reg = df_full[df_full["REGIAO"].isin(regioes)]
    if df_reg.empty:
        return None, 1
    if role == "supervisor" and "LOJA" in df_reg.columns:
        return df_reg, max(int(df_reg["LOJA"].nunique()), 1)
    if role == "consultor" and "CONSULTOR" in df_reg.columns:
        sups = set(
            df_sup_full["SUPERVISOR"].dropna()
            if "SUPERVISOR" in df_sup_full.columns
            else []
        )
        n_cons = int(
            df_reg[~df_reg["CONSULTOR"].isin(sups)]["CONSULTOR"].nunique()
        )
        return df_reg, max(n_cons, 1)
    return df_reg, 1


def _serie_diaria_pago(df_f: pd.DataFrame) -> list | None:
    """Serie diaria de VALOR pago (>= 2 pontos) p/ sparkline; senao None."""
    if "DATA" not in df_f.columns or df_f.empty:
        return None
    df_com_data = df_f.dropna(subset=["DATA"])
    if df_com_data.empty:
        return None
    serie = (
        df_com_data.groupby(df_com_data["DATA"].dt.date)["VALOR"]
        .sum()
        .sort_index()
    )
    return serie.tolist() if len(serie) >= 2 else None


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════


def main():
    """Funcao principal do dashboard."""
    carregar_estilos_customizados()
    aplicar_tema()

    # Camada complementar Aurora — só no modo claro,
    # SEMPRE depois de aplicar_tema() (sobrescreve tokens).
    if get_theme() == "light":
        aplicar_tema_claro_avancado()

    # ── Autenticacao ──────────────────────────────
    if not tela_login():
        return

    # Oculta widgets nativos do Streamlit (deploy, animação, menu ⋮)
    # apenas para não-admins. O motivo de esconder os widgets um a um,
    # e nao o header inteiro, esta no docstring de ocultar_widgets_nativos.
    _perfil_logado = (usuario_logado() or {}).get("perfil")
    if _perfil_logado != "admin":
        ocultar_widgets_nativos()

    # Overlay de transição para login recém-efetuado. A flag e consumida
    # aqui (pop): o overlay some sozinho por animação CSS, sem rerun.
    if st.session_state.pop("_fresh_login", False):
        _user = usuario_logado()
        _nome = (_user.get("nome", "").split()[0]) if _user else ""
        render_overlay_fresh_login(_nome)

    with st.sidebar:
        # ── Logo ocupa toda a largura ──
        logo = (
            "assets/logo-grayscale.png"
            if get_theme() == "dark"
            else "assets/logotipo-mg-cred.png"
        )
        st.image(logo, width="stretch")

        # ── Theme mode toggle 3-state (light/system/dark) ──
        render_theme_toggle()

        render_sidebar_usuario()

        # ── Periodo (colapsavel) ──────────────────────
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
                    from datetime import datetime as _dt

                    _hoje = _dt.now()
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
                    format_func=lambda x: {
                        1: "Janeiro",
                        2: "Fevereiro",
                        3: "Marco",
                        4: "Abril",
                        5: "Maio",
                        6: "Junho",
                        7: "Julho",
                        8: "Agosto",
                        9: "Setembro",
                        10: "Outubro",
                        11: "Novembro",
                        12: "Dezembro",
                    }[x],
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
                st.cache_data.clear()
                st.session_state.pop("_kpis_cache", None)
                st.session_state.pop("_kpis_chave", None)
                st.session_state.pop("_df_ant_cache", None)
                st.session_state.pop("_df_ant_chave", None)
                st.session_state.pop("_periodo_carregado", None)
                st.rerun()

    # ── Toggle Vendas ⇄ Pontuacao (state-driven) ──────
    # Decide a view ANTES do header para que o titulo acompanhe
    # a selecao do usuario.
    _view = st.session_state.get("dashboard_view", "vendas")
    if _view == "pontuacao":
        render_header(
            mes=mes,
            ano=ano,
            titulo="Dashboard de Pontuação",
            subtitulo="Apuração de pontuação e atingimento - MGCred",
        )
    else:
        render_header(mes=mes, ano=ano)

    # Segmented control logo abaixo do header — centralizado.
    _toggle_cols = st.columns([3, 4, 3])
    with _toggle_cols[1]:
        _sel = sac.segmented(
            items=[
                sac.SegmentedItem(
                    label="Dashboard de Vendas",
                    icon="bar-chart-fill",
                ),
                sac.SegmentedItem(
                    label="Dashboard de Pontuação",
                    icon="award-fill",
                ),
            ],
            index=1 if _view == "pontuacao" else 0,
            align="center",
            color="blue",
            key="sel_dashboard_view",
        )
    _nova_view = "pontuacao" if _sel == "Dashboard de Pontuação" else "vendas"
    if _nova_view != _view:
        st.session_state["dashboard_view"] = _nova_view
        st.rerun()

    # ── Config: renderiza sem carregar contratos ──────
    if st.session_state.get("mostrar_config"):
        render_pagina_config()
        return

    # ── Dashboard: carrega contratos apenas aqui ──────
    try:
        # Skeleton + status sao exibidos apenas na primeira carga
        # do periodo (cache miss). Em interacoes subsequentes (mudar
        # filtro, trocar de aba) os loaders cacheados respondem em
        # ms e o skeleton/status causariam apenas flicker visual.
        _chave_carga = (mes, ano)
        _eh_primeira = (
            st.session_state.get("_periodo_carregado") != _chave_carga
        )

        _is_admin = (usuario_logado() or {}).get("perfil") == "admin"

        if _eh_primeira:
            skeleton_ph = st.empty()
            with skeleton_ph:
                render_skeleton()
            _status_obj = st.status(
                ":shimmer[Carregando dados...]", expanded=False
            )
            _status_obj.__enter__()
        else:
            skeleton_ph = None
            _status_obj = None

        def _upd_status(label: str) -> None:
            if _status_obj is not None:
                _status_obj.update(label=f":shimmer[{label}]")

        # Carga do periodo: o loader reporta cada etapa via callback e
        # devolve os frames ja normalizados (regras do pipeline + nomes
        # de display). A UI de progresso (skeleton/status) fica aqui.
        (
            df,
            df_metas,
            df_sup,
            categorias,
            df_metas_produto,
            df_analise,
            df_cancelados,
        ) = carregar_periodo_dashboard(mes, ano, on_progress=_upd_status)

        if _status_obj is not None:
            _status_obj.update(label="Dados carregados", state="complete")
            _status_obj.__exit__(None, None, None)
            _status_obj.empty()
            skeleton_ph.empty()
            st.session_state["_periodo_carregado"] = _chave_carga

        _n_cancel_admin = len(df_cancelados) if _is_admin else 0

        # ── Diagnostico de pontuacao ─────────────
        diag = st.session_state.get("_diag_pontuacao")
        if diag and _is_admin:
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

        # Calcular dias uteis do periodo (para usar nos KPIs)
        hoje = datetime.now()
        dia_ref = hoje.day if (ano == hoje.year and mes == hoje.month) else 1
        _, du_decorridos, _ = calcular_dias_uteis(ano, mes, dia_ref)

        if df.empty and df_analise.empty and df_cancelados.empty:
            st.warning("Nenhum dado encontrado para o periodo selecionado.")
            return

        if df.empty:
            st.info(
                "Nenhum contrato pago no periodo. Exibindo apenas propostas em analise."
            )
            df_analise = aplicar_rls(df_analise)
            # Sem contratos pagos, mostrar apenas card de analise
            kpis_analise = calcular_kpis_analise(
                df_analise, pd.DataFrame(), du_decorridos
            )
            kpis_vazio = {
                "total_vendas": 0,
                "projecao": 0,
                "meta_diaria_pts": 0,
                "media_du": 0,
                "media_du_pontos": 1,
            }
            criar_cards_indicadores_principais(
                kpis_vazio,
                kpis_analise,
                {
                    "valor_cancelados": 0,
                    "qtd_cancelados": 0,
                    "indice_perda": 0,
                },
                {"media_du_loja": 0, "media_du_consultor": 0},
            )
            render_tab_em_analise(df_analise, df_sup)
            return

        # ── Snapshots pre-RLS para heatmap comparativo ──
        # Aliases simples: aplicar_rls retorna novos DataFrames
        # filtrados, entao os originais nao sao mutados pela
        # cadeia abaixo. Evita .copy() de DataFrames grandes
        # em todo rerun.
        df_full = df
        df_metas_full = df_metas
        df_metas_produto_full = df_metas_produto
        df_sup_full = df_sup

        # Médias da organização são calculadas após resolver o perfil
        # efetivo (ver bloco de KPIs abaixo), pois dependem do nível
        # do perfil para definir a granularidade do agrupamento.

        # ── Dados do mês anterior: lazy, só na aba Produtos ─
        # Carregamento adiado para dentro de `if tab == "Produtos":`.
        df_ant_full = pd.DataFrame()
        du_dec_ant = 0

        # ── Sidebar fase 1: Visualizar Como (admin/gestor) ──
        # Renderizado ANTES do aplicar_rls para que a mudanca de
        # perfil simulado entre em vigor no mesmo rerun (sem precisar
        # de st.rerun() explicito). Usa df_full (pre-RLS) para listar
        # todas as regioes/lojas/consultores disponiveis.
        with st.sidebar:
            render_sidebar_visualizar_como(df_full)

        # ── Perfil efetivo (resolvido APOS Visualizar Como) ──
        from src.dashboard.rls import _obter_perfil_efetivo

        perfil_efetivo = _obter_perfil_efetivo()
        role = perfil_efetivo["perfil"] if perfil_efetivo else None

        # ── Drill-down dos cards de contexto (fail-closed) ──
        # Le o query param `?card=<key>` UMA vez por navegacao e o
        # consome (clear). So promove a `card_page` se o perfil pode ver
        # o drill-down dos cards E a key e uma das quatro validas; param
        # forjado por perfil sem acesso (supervisor/consultor) e ignorado
        # (nao deixa estado pendurado). O roteamento em si ocorre adiante,
        # ja com os dados carregados.
        _CARDS_VALIDOS = {
            "em_analise",
            "cancelados",
            "media_consultor",
            "media_loja",
        }
        _card_param = st.query_params.get("card")
        if _card_param is not None:
            if pode_ver("cards_drilldown", role) and _card_param in _CARDS_VALIDOS:
                st.session_state["card_page"] = _card_param
            st.query_params.clear()

        # ── RLS: filtrar dados por perfil ─────────
        # df_sup NAO e recortado por escopo: a lista de supervisores so
        # serve para EXCLUSAO em metricas consultor-level (nunca e
        # exibida). Recorta-la deixava escapar supervisor cujo cadastro
        # em `supervisores` aponta outra loja/regiao (ex.: remanejamento
        # ainda nao refletido) — ele aparecia como consultor na regiao
        # visualizada. A exclusao deve usar sempre a lista global.
        df = aplicar_rls(df)
        df_metas = aplicar_rls_metas(df_metas, df)
        df_metas_produto = aplicar_rls_metas(df_metas_produto, df)
        if not df_analise.empty:
            df_analise = aplicar_rls(df_analise)
        if not df_cancelados.empty:
            df_cancelados = aplicar_rls(df_cancelados)

        # Calcular dias uteis (usar data atual se df vazio)
        if not df.empty:
            ultima_data = df["DATA"].max()
            dia_atual = ultima_data.day if hasattr(ultima_data, "day") else None
            ultima_atualizacao = (
                df["CREATED_AT"].max()
                if "CREATED_AT" in df.columns
                else None
            )
        else:
            ultima_data = None
            ultima_atualizacao = None
            dia_atual = datetime.now().day
        _, du_decorridos, _ = calcular_dias_uteis(ano, mes, dia_atual)

        # ── Dados filtrados (RLS ja aplicado) ─────────
        # Aliases: aplicar_filtros_ui (abaixo) ja retorna novos
        # DataFrames com .copy() interno, entao manter referencias
        # aqui e suficiente.
        df_f = df
        df_metas_f = df_metas
        df_metas_prod_f = df_metas_produto
        df_sup_f = df_sup
        df_analise_f = df_analise
        df_cancelados_f = df_cancelados

        # ── Sidebar fase 2: Filtros granulares (gerente/supervisor) ──
        # Renderizado APOS o RLS porque os filtros granulares de Loja
        # e Consultor devem listar apenas o escopo permitido.
        with st.sidebar:
            render_sidebar_filtros_perfil(df_f, df_sup_f, role or "")

        # ── Aplicar filtros granulares de UI (pos-RLS) ─
        _ui_lojas = st.session_state.get("ui_filtro_lojas") or []
        _ui_cons = st.session_state.get("ui_filtro_consultor") or ""
        if _ui_lojas or _ui_cons:
            df_f = aplicar_filtros_ui(df_f)
            df_analise_f = aplicar_filtros_ui(df_analise_f)
            df_cancelados_f = aplicar_filtros_ui(df_cancelados_f)
            df_metas_f = filtrar_metas_ui(df_metas_f, df_f)
            df_metas_prod_f = filtrar_metas_ui(df_metas_prod_f, df_f)

        render_status_bar(
            len(df_f),
            ultima_data,
            "Todas",
            num_em_analise=len(df_analise_f),
            num_cancelados=_n_cancel_admin,
            ultima_atualizacao=ultima_atualizacao,
        )

        # ── Aviso de pontuacao com fallback ───────
        df_pontos = carregar_pontuacao_efetiva(mes, ano)
        # Mapa categoria_codigo -> PTS, reusado pela pagina de Pontuacao
        # para calcular pontos em df_analise/df_cancelados.
        mapa_pontos: dict = (
            dict(
                zip(
                    df_pontos["categoria_codigo"],
                    df_pontos["pontos"].astype(float),
                )
            )
            if not df_pontos.empty
            else {}
        )
        _render_aviso_pontuacao_fallback(df_pontos)

        # ── Meta MIX por consultor: troca df_metas_prod_f ─
        # Ativa quando o perfil nativo é consultor OU quando outro perfil
        # filtrou até um consultor específico via filtro granular de UI.
        _consultor_selecionado = bool(st.session_state.get("ui_filtro_consultor"))
        if role == "consultor" or _consultor_selecionado:
            _mpc = carregar_metas_produto_consultor(mes, ano)
            _mpc = filtrar_metas_ui(_mpc, df_f)
            if not _mpc.empty:
                df_metas_prod_f = _mpc

        # ── Calculos de KPIs (memoizados em session_state) ──
        # Cache local por (mes, ano, regiao, role): troca de aba
        # nao recalcula. Invalidado pelo botao "Atualizar Dados".
        chave_kpis = (
            mes,
            ano,
            role,
            tuple(perfil_efetivo.get("escopo", []) if perfil_efetivo else []),
            tuple(sorted(st.session_state.get("ui_filtro_lojas") or [])),
            st.session_state.get("ui_filtro_consultor") or "",
        )
        if st.session_state.get("_kpis_chave") != chave_kpis:
            kpis = calcular_kpis_gerais(
                df_f,
                df_metas_f,
                df_metas_prod_f,
                ano,
                mes,
                dia_atual,
                df_sup_f,
            )

            kpis_analise = calcular_kpis_analise(
                df_analise_f,
                df_f,
                du_decorridos,
            )

            kpis_cancel = calcular_kpis_cancelados(
                df_cancelados_f,
                df_f,
                df_analise_f,
            )

            medias = calcular_medias_du_por_nivel(
                df_f,
                du_decorridos,
                df_sup_f,
            )

            metas_prod_diarias = calcular_metas_produto_diarias(
                df_f,
                df_metas_prod_f,
                kpis.get("du_total", 0),
                du_decorridos,
            )

            # Meta global em VALOR (R$) = meta_mix do calcular_kpis_gerais.
            # Diferente de `meta_prata`, que está em PONTOS.
            meta_global_valor = float(kpis.get("meta_mix", 0) or 0)
            total_vendas_valor = float(kpis.get("total_vendas", 0) or 0)
            kpis["meta_global_valor"] = meta_global_valor
            kpis["perc_ating_valor"] = (
                (total_vendas_valor / meta_global_valor * 100)
                if meta_global_valor > 0
                else 0
            )
            kpis["gap_valor"] = max(0, meta_global_valor - total_vendas_valor)

            # Média DU de referência: média da região por loja (supervisor)
            # ou por consultor (consultor). Para outros perfis, sem referência.
            _df_org_ritmo, _org_norm = _ritmo_organizacao(
                role, df_f, df_full, df_sup_full
            )
            kpis_qtd = calcular_kpis_qtd_produtos(
                df_f,
                df_analise_f,
                df_metas_prod_f,
                kpis.get("du_total", 0),
                du_decorridos,
                df_org=_df_org_ritmo,
                org_norm=_org_norm,
            )

            # ── Médias da organização (pre-RLS, granularidade por perfil) ──
            # Granularidade acompanha o filtro de UI: se o usuário afunilou
            # até consultor → granularidade consultor; até loja → supervisor;
            # sem filtro extra → granularidade nativa do perfil.
            if _consultor_selecionado:
                _perfil_media = "consultor"
            elif _ui_lojas and role == "gerente_comercial":
                _perfil_media = "supervisor"
            else:
                _perfil_media = role
            medias_organizacao = calcular_medias_organizacao(
                df_full,
                du_decorridos=du_decorridos,
                perfil=_perfil_media,
                df_sup=df_sup_full,
            )

            # Serie diaria de valor pago (para sparkline do card hero).
            daily_pago = _serie_diaria_pago(df_f)

            st.session_state["_kpis_cache"] = {
                "kpis": kpis,
                "kpis_analise": kpis_analise,
                "kpis_cancel": kpis_cancel,
                "medias": medias,
                "metas_prod_diarias": metas_prod_diarias,
                "medias_organizacao": medias_organizacao,
                "kpis_qtd": kpis_qtd,
                "daily_pago": daily_pago,
            }
            st.session_state["_kpis_chave"] = chave_kpis
        else:
            _cached = st.session_state["_kpis_cache"]
            kpis = _cached["kpis"]
            kpis_analise = _cached["kpis_analise"]
            kpis_cancel = _cached["kpis_cancel"]
            medias = _cached["medias"]
            metas_prod_diarias = _cached["metas_prod_diarias"]
            medias_organizacao = _cached["medias_organizacao"]
            kpis_qtd = _cached["kpis_qtd"]
            daily_pago = _cached["daily_pago"]

        # ── Dispatch: Dashboard de Pontuacao ──────────
        # Quando o toggle esta em 'pontuacao', renderizamos apenas a
        # pagina de pontuacao (cards + prioridades em pontos) e
        # encerramos. Nao mostramos os cards de vendas nem as tabs.
        if st.session_state.get("dashboard_view") == "pontuacao":
            render_dashboard_pontuacao(
                kpis=kpis,
                df=df_f,
                df_analise=df_analise_f,
                df_cancelados=df_cancelados_f,
                df_metas_produto=df_metas_prod_f,
                df_sup=df_sup_f,
                mapa_pontos=mapa_pontos,
                du_decorridos=du_decorridos,
                perfil=role,
            )
            return

        # Reconquista: apuração mensal por dt_fim_relacionamento
        # com defasagem de 1 mês (TTL 10min, RLS aplicada no
        # loader). Carregada uma vez e reusada tanto pelo bloco
        # resumido do header quanto pela sub-aba de Analiticos.
        try:
            dados_reconquista = carregar_reconquista(mes, ano)
        except Exception:
            logger.exception("Falha ao carregar Reconquista")
            dados_reconquista = None

        # Consultor nao ve cards gerenciais; sua aba
        # renderiza os cards pessoais
        if pode_ver("cards_gerenciais", role):
            # ── Drill-down: pagina de detalhe de um card ──────
            # Quando `card_page` esta setado (promovido pelo read
            # fail-closed acima), renderiza so o botao de voltar + a
            # pagina correspondente e encerra (pula cards e tabs),
            # espelhando o padrao do modo Config.
            _card_page = st.session_state.get("card_page")
            if _card_page:
                if st.button("← Voltar ao Dashboard"):
                    st.session_state["card_page"] = None
                    st.rerun()

                _du_total = kpis.get("du_total", 0)
                if _card_page == "em_analise":
                    # Aplica RLS server-side local no detalhe (o Supabase
                    # ja filtra, mas admin/gestor visualizando como gerente
                    # precisa restringir ao escopo simulado).
                    df_digitacao_detalhe = aplicar_rls(
                        carregar_digitacao_diaria_detalhe(mes, ano)
                    )
                    render_detalhe_em_analise(
                        df_analise=df_analise_f,
                        df_digitacao_detalhe=df_digitacao_detalhe,
                        du_decorridos=du_decorridos,
                        du_total=_du_total,
                        perfil=role,
                    )
                elif _card_page == "cancelados":
                    render_detalhe_cancelados(
                        df_cancelados=df_cancelados_f,
                        du_decorridos=du_decorridos,
                        du_total=_du_total,
                        perfil=role,
                    )
                elif _card_page == "media_consultor":
                    render_detalhe_media_consultor(
                        df=df_f,
                        du_decorridos=du_decorridos,
                        du_total=_du_total,
                        df_sup=df_sup_f,
                        perfil=role,
                    )
                elif _card_page == "media_loja":
                    render_detalhe_media_loja(
                        df=df_f,
                        du_decorridos=du_decorridos,
                        du_total=_du_total,
                        df_sup=df_sup_f,
                        perfil=role,
                    )
                return

            # KPIs Principais Reformulados
            # (3 principais + contexto + MIX + Aceleradores
            # + Reconquista + Média/Projeção)
            render_kpis_reforma(
                kpis=kpis,
                kpis_analise=kpis_analise,
                kpis_cancel=kpis_cancel,
                medias=medias,
                metas_produto=metas_prod_diarias,
                kpis_qtd=kpis_qtd,
                daily_pago=daily_pago,
                medias_organizacao=medias_organizacao,
                perfil=role,
                reconquista=dados_reconquista,
                mes=mes,
                ano=ano,
            )

            # Resumo Executivo comentado (após KPIs visuais)
            render_resumo_executivo(
                kpis=kpis,
                kpis_analise=kpis_analise,
                kpis_cancel=kpis_cancel,
                metas_produto=metas_prod_diarias,
            )

            # NOVA REFORMA UX/UI: Bloco 3 - Prioridades de Ação
            render_prioridades_acao(
                metas_produto=metas_prod_diarias,
                df=df_f,
                df_metas_produto=df_metas_prod_f,
                kpis=kpis,
                perfil=role,
                df_sup=df_sup_f,
                du_decorridos=du_decorridos,
                categorias=categorias,
                df_analise=df_analise_f,
            )

        # ── Navegacao principal ───────────────────

        # Monta abas conforme a matriz de permissoes.
        # Icones sao Material Symbols (:material/<nome>:), nao Bootstrap:
        # a navegacao usa st.pills, que renderiza markdown no rotulo.
        abas_disponiveis = [
            ("tab_produtos", "Produtos", "sell"),
            ("tab_regioes", "Regioes", "map"),
            ("tab_rankings_lojas", "Rankings", "emoji_events"),
            ("tab_analiticos", "Analiticos", "bar_chart"),
            ("tab_evolucao", "Evolucao", "trending_up"),
            ("tab_em_analise", "Em Analise", "schedule"),
            ("tab_detalhes", "Detalhes", "table_chart"),
            ("tab_pagamentos_online", "Pagamentos Online", "bolt"),
            ("tab_gestao", "Gestao", "filter_alt"),
        ]
        rotulos_visiveis = [
            rotulo
            for chave, rotulo, _icone in abas_disponiveis
            if pode_ver(chave, role)
        ]
        icones_aba = {rotulo: icone for _c, rotulo, icone in abas_disponiveis}

        if not rotulos_visiveis:
            st.warning("Nenhuma aba disponivel para seu perfil.")
            return

        # Navegacao em st.pills (nao sac.tabs): o button group nativo tem
        # flex-wrap, entao as abas quebram em varias linhas quando nao
        # cabem na largura, em vez de sumirem. O sac.tabs roda dentro de
        # um iframe e o CSS da propria lib esconde o botao de overflow
        # (.ant-tabs-nav-more{display:none}), tornando as abas que
        # transbordam inacessiveis em telas estreitas.
        # `required=True` impede desselecionar e cair sem nenhuma aba.
        tab = st.pills(
            "Navegacao principal",
            options=rotulos_visiveis,
            default=rotulos_visiveis[0],
            required=True,
            format_func=lambda r: f":material/{icones_aba[r]}: {r}",
            label_visibility="collapsed",
            key="nav_principal",
        )

        if tab == "Produtos":
            # Lazy load do mes anterior — so a aba Produtos consome.
            # Evita query Supabase + consolidacao quando usuario fica
            # em outras abas.
            mes_ant = mes - 1 if mes > 1 else 12
            ano_ant = ano if mes > 1 else ano - 1

            # Cache local do df_ant_full pos-RLS+filtros: evita repetir
            # aplicar_nomes_display_produto + aplicar_rls + aplicar_filtros_ui
            # a cada rerun da aba (ex: hover/clique em outros widgets).
            # Invalidado por mudanca de periodo, perfil ou filtros UI.
            chave_ant = (
                mes_ant,
                ano_ant,
                role,
                tuple(perfil_efetivo.get("escopo", []) if perfil_efetivo else []),
                tuple(sorted(st.session_state.get("ui_filtro_lojas") or [])),
                st.session_state.get("ui_filtro_consultor") or "",
            )
            if st.session_state.get("_df_ant_chave") != chave_ant:
                try:
                    _df_ant, _, _ = consolidar_dados(mes_ant, ano_ant)
                    _df_ant = aplicar_nomes_display_produto(_df_ant)
                    # Aplica o mesmo escopo de perfil e filtros de UI do mês
                    # atual, para que a curva do mês anterior no gráfico
                    # acumulado represente a mesma granularidade (região /
                    # loja / consultor) que está sendo visualizada.
                    _df_ant = aplicar_rls(_df_ant)
                    if (
                        st.session_state.get("ui_filtro_lojas")
                        or st.session_state.get("ui_filtro_consultor")
                    ):
                        _df_ant = aplicar_filtros_ui(_df_ant)
                except Exception as exc:
                    logger.exception(
                        "Falha ao carregar mês anterior (%s/%s)",
                        mes_ant, ano_ant,
                    )
                    st.warning(
                        f"Não foi possível carregar o mês anterior "
                        f"({mes_ant:02d}/{ano_ant}): {exc}"
                    )
                    _df_ant = pd.DataFrame()
                st.session_state["_df_ant_cache"] = _df_ant
                st.session_state["_df_ant_chave"] = chave_ant
            df_ant_full = st.session_state["_df_ant_cache"]
            du_dec_ant = calcular_dias_uteis(ano_ant, mes_ant, 1)[0]

            # Mesmo mês / ano anterior — lazy load com cache próprio.
            ano_yoy = ano - 1
            chave_yoy = (
                mes,
                ano_yoy,
                role,
                tuple(perfil_efetivo.get("escopo", []) if perfil_efetivo else []),
                tuple(sorted(st.session_state.get("ui_filtro_lojas") or [])),
                st.session_state.get("ui_filtro_consultor") or "",
            )
            if st.session_state.get("_df_ano_ant_chave") != chave_yoy:
                try:
                    _df_yoy, _, _ = consolidar_dados(mes, ano_yoy)
                    _df_yoy = aplicar_nomes_display_produto(_df_yoy)
                    _df_yoy = aplicar_rls(_df_yoy)
                    if (
                        st.session_state.get("ui_filtro_lojas")
                        or st.session_state.get("ui_filtro_consultor")
                    ):
                        _df_yoy = aplicar_filtros_ui(_df_yoy)
                except Exception as exc:
                    logger.exception(
                        "Falha ao carregar mesmo mês / ano anterior (%s/%s)",
                        mes, ano_yoy,
                    )
                    st.warning(
                        f"Não foi possível carregar o comparativo YoY "
                        f"({mes:02d}/{ano_yoy}): {exc}"
                    )
                    _df_yoy = pd.DataFrame()
                st.session_state["_df_ano_ant_cache"] = _df_yoy
                st.session_state["_df_ano_ant_chave"] = chave_yoy
            df_ano_ant_full = st.session_state["_df_ano_ant_cache"]

            render_tab_produtos(
                df_f,
                df_metas_prod_f,
                categorias,
                ano,
                mes,
                dia_atual,
                df_sup_f,
                df_analise=df_analise_f,
                du_total=kpis.get("du_total", 0),
                du_decorridos=du_decorridos,
                df_full=df_full,
                df_metas_produto_full=df_metas_produto_full,
                df_ant=df_ant_full,
                du_dec_ant=du_dec_ant,
                df_ano_ant=df_ano_ant_full,
            )
        elif tab == "Regioes":
            render_tab_regioes(
                df_f,
                df_metas_f,
                ano,
                mes,
                dia_atual,
                df_sup_f,
                df_metas_prod_f,
                categorias,
                df_full,
                df_metas_produto_full,
            )
        elif tab == "Rankings":
            # Universos de ativos p/ a visao de controle (sem producao).
            # Carregam global e passam pelo aplicar_rls (gerente enxerga
            # so a propria regiao via REGIAO_ATUAL; fail-closed). A aba
            # so os usa para admin/gestor/gerente_comercial.
            _univ_lojas = aplicar_rls(carregar_universo_lojas(mes, ano))
            _univ_cons = aplicar_rls(carregar_consultores_ativos())
            render_tab_rankings(
                df_full,
                df_metas_full,
                df_sup_full,
                df_scope=df_f,
                perfil=role,
                df_lojas_univ=_univ_lojas,
                df_cons_univ=_univ_cons,
            )
        elif tab == "Analiticos":
            render_tab_analiticos(
                df_f,
                df_sup_f,
                df_analise_f,
                df_cancelados_f,
                perfil=role,
                reconquista=dados_reconquista,
            )
        elif tab == "Evolucao":
            render_tab_evolucao(
                df_f,
                ano,
                mes,
                kpis,
            )
        elif tab == "Em Analise":
            render_tab_em_analise(df_analise_f, df_sup_f)
        elif tab == "Detalhes":
            render_tab_detalhes(df_f)
        elif tab == "Pagamentos Online":
            df_pag_online = carregar_pagamentos_online()
            render_tab_pagamentos_online(df_pag_online)
        elif tab == "Gestao":
            # Universo de consultores ATIVOS: sem ele a aba so enxerga
            # quem produziu, e um criterio "ate R$ X" perde quem vendeu
            # nada. Passa pelo mesmo recorte de df_f — aplicar_rls
            # (perfil) e os filtros granulares da sidebar — para que a
            # lista nao traga consultor de loja que o usuario filtrou.
            _univ_cons_gestao = aplicar_filtros_ui(
                aplicar_rls(carregar_consultores_ativos())
            )
            # Metas por produto de escopo CONSULTOR (alvo individual de
            # cada consultor da loja): sustentam a base "% da meta" nos
            # criterios. Ausentes, a base e ignorada com aviso na aba.
            _metas_gestao = filtrar_metas_ui(
                carregar_metas_produto_consultor(mes, ano), df_f
            )

            def _carregar_intervalo_gestao(ini, fim, campo):
                """Contratos pagos num intervalo livre, no escopo do usuario.

                A aba so escolhe as datas; o recorte de seguranca fica
                aqui, igual ao de df_f: aplicar_rls (perfil) primeiro,
                filtros granulares da sidebar depois. Um intervalo
                personalizado nao pode ser porta para ver o que o mes
                selecionado nao mostraria.
                """
                bruto, aviso = carregar_contratos_pagos_intervalo(
                    ini, fim, campo
                )
                if bruto.empty:
                    return bruto, aviso
                return aplicar_filtros_ui(aplicar_rls(bruto)), aviso

            render_tab_gestao(
                df_f,
                df_sup_f,
                _univ_cons_gestao,
                _metas_gestao,
                _carregar_intervalo_gestao,
            )

    except Exception:
        logger.exception("Erro inesperado no main()")
        st.error(
            "Erro inesperado. Tente recarregar a página ou contate o suporte."
        )


if __name__ == "__main__":
    main()
