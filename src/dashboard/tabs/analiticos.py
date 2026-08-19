"""
Aba Analiticos: detalhamento de contratos (pagos/em analise/
cancelados), consultores por produto, producao por regiao e
distribuicao de produtos.
"""

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.config.settings import PRODUTOS_EMISSAO
from src.dashboard.components.tables import (
    botao_exportar_csv,
    exibir_tabela,
)
from src.dashboard.formatters import (
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)
from src.dashboard.kpis.gerais import (
    calcular_assertividade_consultores,
    calcular_oportunidades_perdidas,
    separar_cancelados_liquidos,
)
from src.dashboard.kpis.produtos import (
    COL_PRODUTO_DETALHADO,
    adicionar_produto_detalhado,
    calcular_distribuicao_produtos,
    calcular_distribuicao_produtos_por_loja,
)
from src.dashboard.loaders import VIGENCIA_VIGENTE


# Compat: alias local mantido — implementação canônica em
# components/tables.py (CSV sob demanda via callable).
_exportar_csv = botao_exportar_csv


# Colunas de produto exibidas nas tabelas de detalhamento, na ordem
# da hierarquia do banco: grupo (PRODUTO_DETALHADO — grupo_dashboard com
# o PACK desmembrado em FGTS / ANT. DE BENEF. / CNC 13º) →
# TIPO_PRODUTO (produtos.tipo) → SUBTIPO (produtos.subtipo).
_COLS_PRODUTO = [COL_PRODUTO_DETALHADO, "TIPO_PRODUTO", "SUBTIPO"]


# Icones das sub-navegacoes. Sao Material Symbols (`:material/<nome>:`),
# nao Bootstrap: o st.pills renderiza markdown no rotulo. Nomes validos
# em `streamlit.material_icon_names.ALL_MATERIAL_ICONS`.
# `rocket_launch` em Aceleradores (e nao `bolt`, a traducao literal do
# antigo `lightning-charge`) porque `bolt` ja e o icone da aba principal
# Pagamentos Online.
_ICONES_ANALITICOS = {
    "Propostas Pagas": "check_circle",
    "Em Analise": "schedule",
    "Cancelados": "cancel",
    "Aceleradores": "rocket_launch",
    "Reconquista": "autorenew",
    "Cobranca Consignavel": "payments",
    "Distribuicao de Produtos": "pie_chart",
}

_ICONES_RECONQUISTA = {
    "Por Loja": "storefront",
    "Detalhamento": "table_chart",
}


def _opcoes_coluna(df: pd.DataFrame, coluna: str) -> list:
    """Valores distintos de `coluna` para selectbox (sem nulo/vazio).

    Em analise/cancelados chegam com "" onde o join de produto nao
    resolveu; pagos chegam com NaN. Ambos ficam fora das opcoes.
    """
    if coluna not in df.columns:
        return []
    return sorted(
        {
            str(x).strip()
            for x in df[coluna].unique()
            if pd.notna(x) and str(x).strip()
        }
    )


def _filtrar_detalhamento(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    """Filtros de Loja, Consultor, Produto, Banco e Subproduto.

    Produto filtra por ``PRODUTO_DETALHADO`` — a taxonomia do dashboard
    com o PACK desmembrado, para que FGTS, ANT. DE BENEF. e CNC 13º
    sejam buscaveis separadamente. Banco filtra por ``BANCO`` (valores
    crus, sem normalizacao — mesma logica de ``_opcoes_coluna`` ja usada
    em Produto). Subproduto filtra por ``SUBTIPO`` (NOVO, REFIN, MARGEM
    COMPLEMENTAR, SUPER CONTA...) e e em cascata: suas opcoes saem do
    recorte ja filtrado (incluindo Banco), evitando combinacoes sem
    linhas.
    """
    df = adicionar_produto_detalhado(df)
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key=f"{key_prefix}_loja")
    with col2:
        consultores = ["Todos"] + sorted(
            df["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key=f"{key_prefix}_cons"
        )
    with col3:
        produtos = ["Todos"] + _opcoes_coluna(df, COL_PRODUTO_DETALHADO)
        filt_prod = st.selectbox(
            "Produto", produtos, key=f"{key_prefix}_prod"
        )
    with col4:
        bancos = ["Todos"] + _opcoes_coluna(df, "BANCO")
        filt_banco = st.selectbox(
            "Banco", bancos, key=f"{key_prefix}_banco"
        )

    df_d = df.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and COL_PRODUTO_DETALHADO in df_d.columns:
        df_d = df_d[df_d[COL_PRODUTO_DETALHADO] == filt_prod]
    if filt_banco != "Todos" and "BANCO" in df_d.columns:
        df_d = df_d[df_d["BANCO"].astype(str).str.strip() == filt_banco]

    subprodutos = ["Todos"] + _opcoes_coluna(df_d, "SUBTIPO")
    # Cascata: ao trocar Produto/Banco, o Subproduto selecionado pode nao
    # existir mais nas opcoes. Reseta antes de instanciar o widget
    # (depois disso o session_state e imutavel no mesmo rerun).
    key_sub = f"{key_prefix}_sub"
    if st.session_state.get(key_sub) not in subprodutos:
        st.session_state[key_sub] = "Todos"
    with col5:
        filt_sub = st.selectbox("Subproduto", subprodutos, key=key_sub)

    if filt_sub != "Todos" and "SUBTIPO" in df_d.columns:
        df_d = df_d[df_d["SUBTIPO"].astype(str).str.strip() == filt_sub]

    return df_d


def _render_detalhamento_pagos(df, df_sup):
    """Sub-aba: detalhamento de contratos pagos."""
    if df.empty:
        st.warning("Nenhum contrato pago no periodo.")
        return

    st.markdown(f"**{len(df):,} contratos pagos**".replace(",", "."))

    df_d = _filtrar_detalhamento(df, "det_pago")

    # KPIs
    total_valor = df_d["VALOR"].sum()
    total_trans = len(df_d[df_d["VALOR"] > 0])
    tk = total_valor / total_trans if total_trans > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Valor", formatar_moeda(total_valor))
    with col2:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col3:
        st.metric("Quantidade", formatar_numero(len(df_d)))

    # Tabela detalhada
    # NUM_PROPOSTA preferido; fallback para CONTRATO_ID em registros
    # importados antes da correção do campo Nº PROP/ADE.
    df_d = df_d.copy()
    df_d["NR_ADE"] = (
        df_d.get("NUM_PROPOSTA", pd.Series("", index=df_d.index))
        .replace("", pd.NA)
        .fillna(df_d["CONTRATO_ID"].astype(str))
    )

    cols = ["NR_ADE", "DATA", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += _COLS_PRODUTO + ["TIPO OPER.", "VALOR", "BANCO"]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA": "Data Pagamento",
            COL_PRODUTO_DETALHADO: "Grupo",
            "TIPO_PRODUTO": "Produto",
            "SUBTIPO": "Subproduto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(
        df_tabela,
        colunas_moeda=["Valor"],
        paginacao=100,
        key="tab_det_pagos",
    )
    _exportar_csv(df_tabela, "contratos_pagos", "exp_pagos")


def _render_detalhamento_em_analise(df_analise):
    """Sub-aba: detalhamento de contratos em analise."""
    if df_analise.empty:
        st.warning("Nenhum contrato em analise no periodo.")
        return

    st.markdown(
        f"**{len(df_analise):,} contratos em analise**"
        .replace(",", ".")
    )

    df_d = _filtrar_detalhamento(df_analise, "det_analise")

    # KPIs
    total_valor = df_d["VALOR"].sum()
    total_trans = len(df_d)
    tk = total_valor / total_trans if total_trans > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Valor Total", formatar_moeda(total_valor))
    with col2:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col3:
        st.metric("Quantidade", formatar_numero(total_trans))

    # Tabela detalhada
    df_d = df_d.copy()
    df_d["NR_ADE"] = (
        df_d.get("NUM_PROPOSTA", pd.Series("", index=df_d.index))
        .replace("", pd.NA)
        .fillna(df_d["CONTRATO_ID"].astype(str))
    )

    cols = ["NR_ADE", "DATA_CADASTRO", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += _COLS_PRODUTO + [
        "TIPO OPER.", "VALOR",
        "STATUS_BANCO", "BANCO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA_CADASTRO": "Data Cadastro",
            COL_PRODUTO_DETALHADO: "Grupo",
            "TIPO_PRODUTO": "Produto",
            "SUBTIPO": "Subproduto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "STATUS_BANCO": "Status Banco",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(
        df_tabela,
        colunas_moeda=["Valor"],
        paginacao=100,
        key="tab_det_analise",
    )
    _exportar_csv(
        df_tabela, "contratos_em_analise", "exp_analise"
    )


def _render_detalhamento_cancelados(df_cancel):
    """Sub-aba: detalhamento de contratos cancelados."""
    if df_cancel.empty:
        st.warning("Nenhum contrato cancelado no periodo.")
        return

    df_liq, n_redig, n_recup = separar_cancelados_liquidos(df_cancel)
    n_bruto = len(df_cancel)
    n_liq = len(df_liq)

    st.markdown(
        f"**{n_liq:,} cancelados liquidos** "
        f"(de {n_bruto:,} no bruto)".replace(",", ".")
    )
    if n_redig or n_recup:
        st.caption(
            f"Fora da conta: {n_redig} redigitada(s) "
            f"(superada por redigitacao em 7 dias) e "
            f"{n_recup} recuperada(s) (paga em 7 dias)."
        )

    df_d = _filtrar_detalhamento(df_cancel, "det_cancel")

    # KPIs — cancelados liquidos (exclui redigitadas e recuperadas),
    # no layout das sub-abas adjacentes (Valor Total / Ticket Medio /
    # Quantidade). O total geral (bruto) aparece como info secundaria.
    df_d_liq, _, _ = separar_cancelados_liquidos(df_d)
    n_liq_d = len(df_d_liq)
    n_bruto_d = len(df_d)
    valor_liq_d = df_d_liq["VALOR"].sum()
    tk = valor_liq_d / n_liq_d if n_liq_d > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Valor Total", formatar_moeda(valor_liq_d))
    with col2:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col3:
        st.metric("Quantidade", formatar_numero(n_liq_d))
    st.caption(
        f"Total geral: {formatar_numero(n_bruto_d)} no bruto"
    )

    # Tabela detalhada
    df_d = df_d.copy()
    df_d["NR_ADE"] = (
        df_d.get("NUM_PROPOSTA", pd.Series("", index=df_d.index))
        .replace("", pd.NA)
        .fillna(df_d["CONTRATO_ID"].astype(str))
    )

    cols = ["NR_ADE", "DATA_CADASTRO", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += _COLS_PRODUTO + [
        "TIPO OPER.", "VALOR",
        "SUB_STATUS", "STATUS_PAG", "BANCO", "CLASSIFICACAO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA_CADASTRO": "Data Cadastro",
            COL_PRODUTO_DETALHADO: "Grupo",
            "TIPO_PRODUTO": "Produto",
            "SUBTIPO": "Subproduto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "SUB_STATUS": "Sub-Status",
            "STATUS_PAG": "Status Pagamento",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
            "CLASSIFICACAO": "Classificacao",
        })
    )
    exibir_tabela(
        df_tabela,
        colunas_moeda=["Valor"],
        paginacao=100,
        key="tab_det_cancel",
    )
    _exportar_csv(
        df_tabela, "contratos_cancelados", "exp_cancel"
    )


# Por perfil: (coluna flag, rotulo "capturada por X", frase "fechou ... X")
_OPORTUNIDADE_POR_PERFIL = {
    "consultor": (
        "RECUPERADA_OUTRO", "outro consultor", "com outro consultor",
    ),
    "supervisor": (
        "RECUPERADA_OUTRA_LOJA", "outra loja", "em outra loja",
    ),
    "gerente_comercial": (
        "RECUPERADA_OUTRA_REGIAO", "outra regiao", "em outra regiao",
    ),
}


def _render_oportunidades_perdidas(df_cancelados, perfil):
    """Secao: vendas do cliente capturadas FORA do proprio nivel.

    Exibida para consultor (outro consultor), supervisor (outra loja)
    e gerente (outra regiao). Identidade de quem capturou nao e
    exibida (so qtd e valor perdido).
    """
    cfg = _OPORTUNIDADE_POR_PERFIL.get(perfil)
    if cfg is None:
        return
    coluna_flag, rotulo, frase = cfg

    res = calcular_oportunidades_perdidas(df_cancelados, coluna_flag)
    if res["qtd_perdidas"] == 0:
        return

    sac.divider(
        label="Oportunidades perdidas",
        icon="exclamation-triangle",
        align="left",
        color="gray",
    )
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            f"Vendas capturadas por {rotulo}",
            formatar_numero(res["qtd_perdidas"]),
        )
    with col2:
        st.metric(
            "Valor perdido",
            formatar_moeda(res["valor_perdido"]),
        )
    st.caption(
        f"Cancelados do seu escopo cujo cliente fechou o mesmo "
        f"produto {frase} em ate 7 dias. A identidade de quem "
        f"capturou a venda nao e exibida."
    )


def _render_assertividade_consultores(
    df, df_analise, df_cancelados, df_sup
):
    """Assertividade dos consultores no cenario de redigitacao."""
    res = calcular_assertividade_consultores(
        df_cancelados, df, df_analise, df_sup
    )
    por_consultor = res["por_consultor"]
    if por_consultor.empty:
        return

    sac.divider(
        label="Assertividade dos Consultores",
        icon="person-check",
        align="left",
        color="gray",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "Assertividade geral",
            formatar_percentual(res["assertividade_org"]),
        )
    with col2:
        st.metric(
            "Redigitacoes no periodo",
            formatar_numero(res["total_redigitadas"]),
        )

    st.caption(
        "Assertividade = 1 - redigitadas / (pagas + em analise + "
        "canceladas) por consultor. Quanto menor, mais retrabalho "
        "operacional (redigitacao de proposta)."
    )

    df_tab = por_consultor.rename(
        columns={
            "CONSULTOR": "Consultor",
            "total_propostas": "Propostas",
            "redigitadas": "Redigitadas",
            "assertividade": "Assertividade (%)",
        }
    )
    exibir_tabela(
        df_tab,
        colunas_numero=["Propostas", "Redigitadas"],
        colunas_percentual=["Assertividade (%)"],
    )


def _nr_ade(frame: pd.DataFrame) -> pd.Series:
    """Deriva coluna NR_ADE: NUM_PROPOSTA com fallback para CONTRATO_ID."""
    return (
        frame.get("NUM_PROPOSTA", pd.Series("", index=frame.index))
        .replace("", pd.NA)
        .fillna(frame["CONTRATO_ID"].astype(str))
    )


def _render_busca_ade(df, df_analise, df_cancelados):
    """Busca unificada por Nº ADE em todos os status."""
    fontes = [
        (df, "Pago", "DATA"),
        (df_analise, "Em Analise", "DATA_CADASTRO"),
        (df_cancelados, "Cancelado", "DATA_CADASTRO"),
    ]
    resultados = []
    for src, status, col_data in fontes:
        if src.empty:
            continue
        src2 = src.copy()
        src2["NR_ADE"] = _nr_ade(src2)
        src2["Status"] = status
        src2["_DATA"] = src2.get(col_data, pd.Series(dtype="object"))
        resultados.append(src2)

    if not resultados:
        return

    df_all = adicionar_produto_detalhado(
        pd.concat(resultados, ignore_index=True)
    )

    busca = st.text_input(
        "Buscar por Nº ADE",
        placeholder="Digite o número ADE e pressione Enter...",
        key="ade_search_input",
    )

    if not busca.strip():
        return

    mask = df_all["NR_ADE"].astype(str).str.contains(
        busca.strip(), case=False, na=False
    )
    encontrados = df_all[mask]

    if encontrados.empty:
        st.warning(f"Nenhum resultado para '{busca.strip()}'.")
        return

    st.success(f"{len(encontrados)} resultado(s) encontrado(s).")

    cols_base = ["NR_ADE", "Status", "_DATA", "LOJA", "CONSULTOR"]
    if "REGIAO" in encontrados.columns:
        cols_base.append("REGIAO")
    cols_base += _COLS_PRODUTO + ["TIPO OPER.", "VALOR", "BANCO"]

    df_res = (
        encontrados[[c for c in cols_base if c in encontrados.columns]]
        .sort_values("_DATA", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "_DATA": "Data",
            COL_PRODUTO_DETALHADO: "Grupo",
            "TIPO_PRODUTO": "Produto",
            "SUBTIPO": "Subproduto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(df_res, colunas_moeda=["Valor"])
    _exportar_csv(df_res, "busca_ade", "exp_busca_ade")


def _pool_seguros(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    tipo_oper: str,
) -> pd.DataFrame:
    """Une seguros (BMG MED ou Seguro) das 3 fontes e dedupe por CONTRATO_ID.

    Para BMG Med / Vida Familiar o "status" real do contrato vive em
    SUB_STATUS (Liquidada=paga, Cancelada=cancelada, demais=em analise);
    `status_banco` nao reflete o ciclo desses produtos.

    Em caso de duplicidade entre fontes (mesmo CONTRATO_ID), preserva a
    linha de pagos > analise > cancelados.
    """
    pieces = []
    for src, origem in (
        (df, "pago"),
        (df_analise, "analise"),
        (df_cancelados, "cancelado"),
    ):
        if src is None or src.empty or "TIPO OPER." not in src.columns:
            continue
        sub = src[src["TIPO OPER."] == tipo_oper].copy()
        if sub.empty:
            continue
        sub["_origem"] = origem
        pieces.append(sub)

    if not pieces:
        return pd.DataFrame()

    pool = pd.concat(pieces, ignore_index=True, sort=False)
    if "SUB_STATUS" not in pool.columns:
        pool["SUB_STATUS"] = ""
    pool["SUB_STATUS"] = pool["SUB_STATUS"].fillna("").astype(str)

    if "CONTRATO_ID" in pool.columns:
        prio = {"pago": 0, "analise": 1, "cancelado": 2}
        pool["_prio"] = pool["_origem"].map(prio).fillna(99)
        pool = (
            pool.sort_values("_prio")
            .drop_duplicates(subset=["CONTRATO_ID"], keep="first")
            .drop(columns=["_prio"])
        )

    return pool


def _classificar_status_seguro(sub_status: pd.Series) -> pd.Series:
    """Mapeia SUB_STATUS de seguros para Pagas / Em Analise / Cancelados."""
    s = sub_status.fillna("").astype(str).str.strip()
    return pd.Series(
        ["Pagas" if v == "Liquidada"
         else "Cancelados" if v == "Cancelada"
         else "Em Analise"
         for v in s],
        index=sub_status.index,
    )


def _filtrar_loja_consultor(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    """Filtros de Loja e Consultor compartilhados pelos expanders."""
    if df.empty:
        return df
    col1, col2 = st.columns(2)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].dropna().unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key=f"{key_prefix}_loja")
    with col2:
        cons = ["Todos"] + sorted(df["CONSULTOR"].dropna().unique().tolist())
        filt_cons = st.selectbox(
            "Consultor", cons, key=f"{key_prefix}_cons",
        )
    out = df.copy()
    if filt_loja != "Todas":
        out = out[out["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        out = out[out["CONSULTOR"] == filt_cons]
    return out


def _render_expander_seguro(
    nome: str,
    tipo_oper: str,
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    status_sel: str,
):
    """Renderiza expander para BMG Med ou Vida Familiar.

    Estes nao tem `status_banco` no fluxo normal; classificam por
    `SUB_STATUS` (Liquidada/Cancelada/demais).
    """
    pool = _pool_seguros(df, df_analise, df_cancelados, tipo_oper)
    if pool.empty:
        with st.expander(nome, expanded=False):
            st.warning(f"Nenhum contrato {nome} no periodo.")
        return

    pool["_STATUS"] = _classificar_status_seguro(pool["SUB_STATUS"])
    df_st = pool[pool["_STATUS"] == status_sel]
    qtd_total = len(df_st)

    titulo = f"{nome} — {qtd_total} contratos"
    with st.expander(titulo, expanded=False):
        if df_st.empty:
            st.info(f"Nenhum contrato {nome} em '{status_sel}'.")
            return

        df_f = _filtrar_loja_consultor(df_st, f"acel_{tipo_oper}")
        st.metric("Quantidade", formatar_numero(len(df_f)))

        df_f = df_f.copy()
        df_f["NR_ADE"] = _nr_ade(df_f)
        col_data = "DATA" if status_sel == "Pagas" else "DATA_CADASTRO"
        cols = ["NR_ADE", col_data, "LOJA", "CONSULTOR"]
        if "REGIAO" in df_f.columns:
            cols.append("REGIAO")
        cols += ["TIPO_PRODUTO", "SUB_STATUS", "BANCO"]
        cols_disp = [c for c in cols if c in df_f.columns]

        df_tab = (
            df_f[cols_disp]
            .sort_values(col_data, ascending=False)
            .rename(columns={
                "NR_ADE": "Nº ADE",
                "DATA": "Data Pagamento",
                "DATA_CADASTRO": "Data Cadastro",
                "TIPO_PRODUTO": "Produto",
                "SUB_STATUS": "Sub-Status",
                "BANCO": "Banco",
                "LOJA": "Loja",
                "CONSULTOR": "Consultor",
                "REGIAO": "Regiao",
            })
        )
        exibir_tabela(df_tab)
        _exportar_csv(
            df_tab, f"acel_{nome.lower().replace(' ', '_')}_{status_sel.lower().replace(' ', '_')}",
            f"exp_acel_{tipo_oper}_{status_sel}",
        )


def _render_expander_emissao(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    status_sel: str,
):
    """Emissao segue o ciclo normal (status_banco) — usa as 3 fontes
    nativas. Conta apenas como quantidade (VALOR zerado por design)."""
    fonte = {"Pagas": df, "Em Analise": df_analise, "Cancelados": df_cancelados}[status_sel]
    if fonte is None or fonte.empty or "TIPO_PRODUTO" not in fonte.columns:
        with st.expander("Emissao", expanded=False):
            st.warning("Nenhum contrato de emissao no periodo.")
        return

    mask = fonte["TIPO_PRODUTO"].astype(str).str.upper().isin(
        {p.upper() for p in PRODUTOS_EMISSAO}
    )
    df_e = fonte[mask]

    titulo = f"Emissao — {len(df_e)} contratos"
    with st.expander(titulo, expanded=False):
        if df_e.empty:
            st.info(f"Nenhuma emissao em '{status_sel}'.")
            return

        df_f = _filtrar_loja_consultor(df_e, "acel_emissao")
        st.metric("Quantidade", formatar_numero(len(df_f)))

        df_f = df_f.copy()
        df_f["NR_ADE"] = _nr_ade(df_f)
        col_data = "DATA" if status_sel == "Pagas" else "DATA_CADASTRO"
        cols = ["NR_ADE", col_data, "LOJA", "CONSULTOR"]
        if "REGIAO" in df_f.columns:
            cols.append("REGIAO")
        cols += ["TIPO_PRODUTO", "TIPO OPER.", "BANCO"]
        if status_sel != "Pagas" and "STATUS_BANCO" in df_f.columns:
            cols.append("STATUS_BANCO")
        cols_disp = [c for c in cols if c in df_f.columns]

        df_tab = (
            df_f[cols_disp]
            .sort_values(col_data, ascending=False)
            .rename(columns={
                "NR_ADE": "Nº ADE",
                "DATA": "Data Pagamento",
                "DATA_CADASTRO": "Data Cadastro",
                "TIPO_PRODUTO": "Produto",
                "TIPO OPER.": "Tipo Operacao",
                "STATUS_BANCO": "Status Banco",
                "BANCO": "Banco",
                "LOJA": "Loja",
                "CONSULTOR": "Consultor",
                "REGIAO": "Regiao",
            })
        )
        exibir_tabela(df_tab)
        _exportar_csv(
            df_tab, f"acel_emissao_{status_sel.lower().replace(' ', '_')}",
            f"exp_acel_emissao_{status_sel}",
        )


def _render_expander_super_conta(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    status_sel: str,
):
    """Super Conta segue o ciclo normal (status_banco). Conta valor e
    quantidade (e o mesmo valor ja esta computado em CNC por regra de
    negocio — exibido aqui apenas para auditoria)."""
    fonte = {"Pagas": df, "Em Analise": df_analise, "Cancelados": df_cancelados}[status_sel]
    if fonte is None or fonte.empty or "SUBTIPO" not in fonte.columns:
        with st.expander("Super Conta", expanded=False):
            st.warning("Nenhum contrato Super Conta no periodo.")
        return

    mask = fonte["SUBTIPO"].fillna("").astype(str).str.strip().str.upper() == "SUPER CONTA"
    df_s = fonte[mask]

    titulo = f"Super Conta — {len(df_s)} contratos"
    with st.expander(titulo, expanded=False):
        st.caption(
            "Valores tambem computados em CNC (regra de contagem dupla); "
            "isolados aqui para auditoria."
        )
        if df_s.empty:
            st.info(f"Nenhuma Super Conta em '{status_sel}'.")
            return

        df_f = _filtrar_loja_consultor(df_s, "acel_super_conta")
        total_valor = float(df_f["VALOR"].sum()) if "VALOR" in df_f.columns else 0.0
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Quantidade", formatar_numero(len(df_f)))
        with col2:
            st.metric("Valor Total", formatar_moeda(total_valor))

        df_f = df_f.copy()
        df_f["NR_ADE"] = _nr_ade(df_f)
        col_data = "DATA" if status_sel == "Pagas" else "DATA_CADASTRO"
        cols = ["NR_ADE", col_data, "LOJA", "CONSULTOR"]
        if "REGIAO" in df_f.columns:
            cols.append("REGIAO")
        cols += ["TIPO_PRODUTO", "TIPO OPER.", "VALOR", "BANCO"]
        if status_sel != "Pagas" and "STATUS_BANCO" in df_f.columns:
            cols.append("STATUS_BANCO")
        cols_disp = [c for c in cols if c in df_f.columns]

        df_tab = (
            df_f[cols_disp]
            .sort_values(col_data, ascending=False)
            .rename(columns={
                "NR_ADE": "Nº ADE",
                "DATA": "Data Pagamento",
                "DATA_CADASTRO": "Data Cadastro",
                "TIPO_PRODUTO": "Produto",
                "TIPO OPER.": "Tipo Operacao",
                "VALOR": "Valor",
                "STATUS_BANCO": "Status Banco",
                "BANCO": "Banco",
                "LOJA": "Loja",
                "CONSULTOR": "Consultor",
                "REGIAO": "Regiao",
            })
        )
        exibir_tabela(df_tab, colunas_moeda=["Valor"])
        _exportar_csv(
            df_tab, f"acel_super_conta_{status_sel.lower().replace(' ', '_')}",
            f"exp_acel_super_conta_{status_sel}",
        )


def _render_aceleradores(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
):
    """Sub-aba Aceleradores: BMG Med, Vida Familiar, Emissao, Super Conta."""
    status_sel = sac.segmented(
        items=[
            sac.SegmentedItem(label="Pagas", icon="check-circle"),
            sac.SegmentedItem(label="Em Analise", icon="hourglass-split"),
            sac.SegmentedItem(label="Cancelados", icon="x-circle"),
        ],
        align="start",
        use_container_width=False,
        key="acel_status",
    )

    _render_expander_seguro(
        "BMG Med", "BMG MED", df, df_analise, df_cancelados, status_sel,
    )
    _render_expander_seguro(
        "Vida Familiar", "Seguro", df, df_analise, df_cancelados, status_sel,
    )
    _render_expander_emissao(df, df_analise, df_cancelados, status_sel)
    _render_expander_super_conta(df, df_analise, df_cancelados, status_sel)


def _render_reconquista_por_loja(por_loja: pd.DataFrame) -> None:
    if por_loja.empty:
        st.warning("Sem dados por loja no escopo atual.")
        return
    cols = [
        "loja", "regiao", "total_clientes", "efetivadas", "promessas",
        "sem_reconquista", "conversao_pct", "faixa",
        "saldo_medio", "dias_atraso_medio",
    ]
    df_view = por_loja[[c for c in cols if c in por_loja.columns]].rename(
        columns={
            "loja": "Loja",
            "regiao": "Regiao",
            "total_clientes": "Elegíveis",
            "efetivadas": "Efetivadas",
            "promessas": "Promessas",
            "sem_reconquista": "Sem Reconquista",
            "conversao_pct": "Conversão %",
            "faixa": "Faixa Prêmio",
            "saldo_medio": "Saldo Medio",
            "dias_atraso_medio": "Dias Atraso Medio",
        }
    ).sort_values("Efetivadas", ascending=False)
    exibir_tabela(
        df_view,
        colunas_moeda=["Saldo Medio"],
        colunas_numero=[
            "Elegíveis", "Efetivadas", "Promessas",
            "Sem Reconquista", "Dias Atraso Medio",
        ],
    )
    _exportar_csv(df_view, "reconquista_por_loja", "exp_rec_loja")


def _render_reconquista_detalhamento(
    clientes: pd.DataFrame,
    apuracao_label: str,
    ref_label: str,
) -> None:
    """Listagem analitica — 1 linha por cliente (co_adesao) + link.

    Recebe TODAS as apuracoes ja marcadas pelo loader (`vigencia` e
    `apuracao_ref`, derivadas de ref_ano/ref_mes + a defasagem de 1
    mes) e abre no recorte vigente, como antes. Trocar de escopo e
    filtro em pandas sobre o frame que ja veio — nao ha fetch novo.

    As colunas de apuracao/vigencia aparecem nos DOIS escopos e vao no
    CSV: a referencia nunca sai da linha, entao lista completa e recorte
    do mes nunca se confundem.
    """
    if clientes is None or clientes.empty:
        st.warning("Sem clientes no escopo atual.")
        return

    # Cobertura da base (mais antiga → mais recente): o rotulo do
    # escopo precisa dizer o que "todas" significa nesta carga, ja que
    # a tabela e truncada e realimentada a cada import.
    rotulos_apuracao = (
        clientes[["apuracao_key", "apuracao_ref"]]
        .drop_duplicates()
        .sort_values("apuracao_key", ascending=False)["apuracao_ref"]
        .tolist()
    )
    cobertura = (
        f"{rotulos_apuracao[-1]} a {rotulos_apuracao[0]}"
        if len(rotulos_apuracao) > 1
        else (rotulos_apuracao[0] if rotulos_apuracao else "—")
    )

    # Escopo em st.pills: dois estados exclusivos que se alternam o
    # tempo todo. Chave FORA do padrao `nav_*` de proposito — isto e
    # filtro de tabela, nao sub-navegacao, e nao deve herdar o CSS de
    # sub-nav (assets/dashboard_style.css).
    escopo = st.pills(
        "Escopo do detalhamento",
        options=["Vigente", "Todas"],
        default="Vigente",
        required=True,
        format_func=lambda e: (
            f":material/event_available: Vigente · {apuracao_label}"
            if e == "Vigente"
            else f":material/history: Todas as apurações · {cobertura}"
        ),
        label_visibility="collapsed",
        key="rec_det_escopo",
    )

    todas = escopo == "Todas"
    base = (
        clientes if todas
        else clientes[clientes["vigencia"] == VIGENCIA_VIGENTE]
    )
    if base.empty:
        st.warning(
            f"Sem leads na apuração vigente ({apuracao_label} · fim de "
            f"relacionamento em {ref_label}). Troque o escopo para "
            f"consultar as demais apurações."
        )
        return

    # Filtros locais, sempre com as opcoes do escopo ativo — no escopo
    # vigente listar loja/consultor do historico inteiro ofereceria
    # combinacoes que filtram para nada.
    colunas = st.columns(5 if todas else 4)
    c1, c2, c3, c4 = colunas[:4]

    with c1:
        status_opts = ["Todos"] + (
            sorted(base["status"].dropna().unique().tolist())
            if "status" in base.columns else []
        )
        filt_status = st.selectbox("Status", status_opts, key="rec_det_status")

    with c2:
        lojas_opts = (
            sorted(base["loja"].dropna().unique().tolist())
            if "loja" in base.columns else []
        )
        filt_lojas = st.multiselect(
            "Loja", lojas_opts, key="rec_det_lojas",
            placeholder="Todas",
        )

    with c3:
        cons_opts = ["Todos"] + (
            sorted(base["consultor"].dropna().unique().tolist())
            if "consultor" in base.columns else []
        )
        filt_cons = st.selectbox("Consultor", cons_opts, key="rec_det_cons")

    with c4:
        eleg_opts = ["Todos"] + (
            sorted(base["flag_elegibilidade"].dropna().unique().tolist())
            if "flag_elegibilidade" in base.columns else []
        )
        filt_eleg = st.selectbox(
            "Elegibilidade", eleg_opts, key="rec_det_eleg"
        )

    # So no escopo completo: no vigente ha uma unica apuracao e o
    # filtro seria inerte.
    filt_apuracao = []
    if todas:
        with colunas[4]:
            filt_apuracao = st.multiselect(
                "Apuração", rotulos_apuracao, key="rec_det_apuracao",
                placeholder="Todas",
            )

    df_f = base.copy()
    if filt_status != "Todos" and "status" in df_f.columns:
        df_f = df_f[df_f["status"] == filt_status]
    if filt_lojas and "loja" in df_f.columns:
        df_f = df_f[df_f["loja"].isin(filt_lojas)]
    if filt_cons != "Todos" and "consultor" in df_f.columns:
        df_f = df_f[df_f["consultor"] == filt_cons]
    if filt_eleg != "Todos" and "flag_elegibilidade" in df_f.columns:
        df_f = df_f[df_f["flag_elegibilidade"] == filt_eleg]
    if filt_apuracao:
        df_f = df_f[df_f["apuracao_ref"].isin(filt_apuracao)]
    if todas:
        # Apuracao mais recente primeiro; dentro dela a ordem do fetch
        # (co_adesao), para a lista nao "dancar" entre reruns.
        df_f = df_f.sort_values(
            ["apuracao_key", "co_adesao"], ascending=[False, True]
        )

    st.caption(
        f"{formatar_numero(len(df_f))} de {formatar_numero(len(base))} "
        f"leads (após filtros) · **Vigente** = apuração "
        f"{apuracao_label}, fim de relacionamento em {ref_label}."
    )

    cols = [
        "co_adesao", "apuracao_ref", "vigencia", "status",
        "flag_elegibilidade", "loja", "regiao",
        "consultor", "subproduto",
        "dt_fim_relacionamento", "dt_macica", "dt_dna",
        "banco_origem", "banco_destino", "saldo_contabil", "dias_atraso",
        "faixa_atraso", "tipo_pagamento", "link_aceite",
    ]
    df_view = df_f[[c for c in cols if c in df_f.columns]].rename(
        columns={
            "co_adesao": "Cod ADE",
            "apuracao_ref": "Apuração",
            "vigencia": "Vigência",
            "status": "Status",
            "flag_elegibilidade": "Elegível",
            "loja": "Loja",
            "regiao": "Regiao",
            "consultor": "Consultor",
            "subproduto": "Subproduto",
            "dt_fim_relacionamento": "Fim Relac.",
            "dt_macica": "Dt Maciça",
            "dt_dna": "Dt DNA",
            "banco_origem": "Banco Origem",
            "banco_destino": "Banco Destino",
            "saldo_contabil": "Saldo",
            "dias_atraso": "Dias Atraso",
            "faixa_atraso": "Faixa Atraso",
            "tipo_pagamento": "Tipo Pgto",
            "link_aceite": "Link Aceite",
        }
    )

    exibir_tabela(
        df_view,
        colunas_moeda=["Saldo"],
        colunas_numero=["Dias Atraso"],
        # Destaque so faz sentido quando ha mistura de apuracoes: no
        # escopo vigente toda linha e vigente e o realce viraria ruido.
        highlight_mask=(
            (df_f["vigencia"] == VIGENCIA_VIGENTE) if todas else None
        ),
        paginacao=100,
        key="rec_det_tabela",
    )
    _exportar_csv(
        df_view,
        (
            "reconquista_clientes_todas_apuracoes" if todas
            else f"reconquista_clientes_{apuracao_label.replace('/', '-')}"
        ),
        "exp_rec_clientes",
    )


def _render_reconquista(reconquista: dict | None):
    """Sub-aba Reconquista (v2): apuração mensal por dt_fim_relacionamento.

    Defasagem de 1 mes ja resolvida no loader. O bloco de KPIs e o Por
    Loja seguem na apuracao VIGENTE (a apuracao da campanha e mensal);
    so o Detalhamento navega o historico inteiro, com a apuracao de
    cada lead marcada na linha.
    """
    if not reconquista:
        st.info("Sem dados de reconquista para este período.")
        return

    totais = reconquista.get("totais") or {}
    ref_mes = reconquista.get("ref_mes")
    ref_ano = reconquista.get("ref_ano")
    apur_mes = reconquista.get("apuracao_mes")
    apur_ano = reconquista.get("apuracao_ano")
    por_loja = reconquista.get("por_loja", pd.DataFrame())
    clientes = reconquista.get("clientes", pd.DataFrame())
    clientes_todos = reconquista.get("clientes_todos", pd.DataFrame())

    ref_label = f"{ref_mes:02d}/{ref_ano}" if ref_mes else "—"
    apur_label = f"{apur_mes:02d}/{apur_ano}" if apur_mes else "—"
    _faixa = (totais.get("faixa") or {}).get("rotulo", "—")
    _nao_eleg = int(totais.get("nao_elegivel", 0))
    _nao_eleg_txt = f" ({_nao_eleg} não elegíveis)" if _nao_eleg else ""
    st.caption(
        f"Apuração com defasagem de 1 mês · fim de relacionamento em "
        f"**{ref_label}** · {totais.get('total', 0)} elegíveis"
        f"{_nao_eleg_txt} · "
        f"Conversão: **{totais.get('conversao', 0.0):.1f}%** ({_faixa}) · "
        f"Efetivadas: {totais.get('efetivadas', 0)} · "
        f"Promessas: {totais.get('promessas', 0)} · "
        f"Sem reconquista: {totais.get('sem_reconquista', 0)}"
    )

    if clientes is None or clientes.empty:
        st.info(
            f"Sem contratos com fim de relacionamento em {ref_label}."
        )
        # Apuracao vigente vazia nao encerra a sub-aba: o historico
        # segue consultavel no Detalhamento (escopo "Todas"). So encerra
        # quando nao ha lead nenhum no escopo do perfil.
        if clientes_todos is None or clientes_todos.empty:
            return

    # st.pills pelo mesmo motivo do sub-nav de Analiticos (ver
    # render_tab_analiticos): sac.tabs esconde o que nao cabe. Aqui sao
    # so dois itens curtos — migrado por uniformidade, ja que este e o
    # terceiro nivel de navegacao e herda o mesmo estilo.
    menu = st.pills(
        "Sub-navegacao de Reconquista",
        options=list(_ICONES_RECONQUISTA),
        default="Por Loja",
        required=True,
        format_func=lambda r: f":material/{_ICONES_RECONQUISTA[r]}: {r}",
        label_visibility="collapsed",
        key="nav_reconquista",
    )

    if menu == "Por Loja":
        _render_reconquista_por_loja(por_loja)
    elif menu == "Detalhamento":
        _render_reconquista_detalhamento(
            clientes_todos, apur_label, ref_label
        )


def _render_cobranca_consignavel(reconquista: dict | None) -> None:
    """Sub-aba: propostas que compõem a Cobrança Consignável do mês.

    Lista os contratos RLS'd já calculados em `carregar_reconquista`
    (mesmo dado usado para a contagem do card do acelerador combinado —
    ver business-rules.md "Cobrança Consignável — critério"), sem novo
    fetch. Vazio tanto fora da vigência (< 08/2026) quanto quando não há
    propostas no período — mesmo tratamento das abas irmãs.
    """
    contratos = (reconquista or {}).get(
        "cobranca_consignavel_contratos", pd.DataFrame()
    )
    if contratos is None or contratos.empty:
        st.info("Nenhuma proposta de Cobrança Consignável no período.")
        return

    st.caption(
        "Contratos de Cobrança Consignável são considerados os valores cheios "
        "(Valor bruto), para os clientes o valor recebível é o Valor Base."
    )

    df_f = _filtrar_loja_consultor(contratos, "cobr_consig")

    total_valor = (
        float(df_f["VALOR"].sum()) if "VALOR" in df_f.columns else 0.0
    )
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Quantidade", formatar_numero(len(df_f)))
    with col2:
        st.metric("Valor Considerado", formatar_moeda(total_valor))

    df_f = df_f.copy()
    df_f["NR_ADE"] = _nr_ade(df_f)
    cols = ["NR_ADE", "DATA", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_f.columns:
        cols.append("REGIAO")
    # Base -> Bruto -> Considerado conta a historia da regra ("era X, a
    # venda cheia foi Y, entrou Y na producao") e deixa visivel o
    # GREATEST da migration 067 quando o bruto vem menor que a base
    # (Considerado = Base).
    cols += ["BANCO", "VALOR_BASE", "VALOR_BRUTO", "VALOR"]
    cols_disp = [c for c in cols if c in df_f.columns]

    df_tab = (
        df_f[cols_disp]
        .sort_values("DATA", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA": "Data Pagamento",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
            "BANCO": "Banco",
            "VALOR_BASE": "Valor Base",
            "VALOR_BRUTO": "Valor Bruto",
            "VALOR": "Valor Considerado",
        })
    )
    exibir_tabela(
        df_tab,
        colunas_moeda=["Valor Base", "Valor Bruto", "Valor Considerado"],
        paginacao=100,
        key="tab_cobr_consignavel",
    )
    _exportar_csv(
        df_tab, "cobranca_consignavel", "exp_cobr_consignavel"
    )


def _render_distribuicao_por_loja(df, somente_bmg_help: bool = False) -> None:
    """Distribuicao agregada por LOJA (inclui producao de supervisor)."""
    df_dist, cols_moeda, cols_num = calcular_distribuicao_produtos_por_loja(
        df, somente_bmg_help=somente_bmg_help,
    )
    if df_dist.empty:
        st.warning("Dados nao disponiveis")
        return

    st.info("Distribuicao de valor (R$) e aceleradores (Qtd) por loja")
    st.caption(
        "Inclui a producao do proprio supervisor no total da loja — "
        "a visao por consultor a exclui."
    )
    exibir_tabela(
        df_dist,
        colunas_moeda=cols_moeda,
        colunas_numero=cols_num,
        paginacao=100,
        key="tab_dist_prod_loja",
    )
    _exportar_csv(
        df_dist, "distribuicao_produtos_loja",
        "exp_dist_prod_loja",
    )


def _render_distribuicao_por_consultor(
    df, df_sup, key_tabela: str, com_busca: bool,
    somente_bmg_help: bool = False,
) -> None:
    """Distribuicao por CONSULTOR (supervisores excluidos).

    ``com_busca`` revela um selectbox de consultor **local** a esta
    sub-aba (key propria) — nao e o filtro global da sidebar, entao
    selecionar aqui nao afeta nenhuma outra aba. A busca so recorta o
    que aparece na tela: o CSV continua exportando o dataset completo.
    """
    df_dist, cols_moeda, cols_num = calcular_distribuicao_produtos(
        df, df_sup, somente_bmg_help=somente_bmg_help,
    )
    if df_dist.empty:
        st.warning("Dados nao disponiveis")
        return

    st.info("Distribuicao de valor (R$) e aceleradores (Qtd) por consultor")

    df_exib = df_dist
    if com_busca and "CONSULTOR" in df_dist.columns:
        consultores = ["Todos"] + sorted(
            df_dist["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="dist_prod_busca_cons",
        )
        if filt_cons != "Todos":
            df_exib = df_dist[df_dist["CONSULTOR"] == filt_cons]

    exibir_tabela(
        df_exib,
        colunas_moeda=cols_moeda,
        colunas_numero=cols_num,
        paginacao=100,
        key=key_tabela,
    )
    _exportar_csv(
        df_dist, "distribuicao_produtos",
        "exp_dist_prod",
    )


def _render_distribuicao_produtos(df, df_sup, perfil: str) -> None:
    """Sub-aba: distribuicao de produtos, com visao por perfil.

    Supervisor ve sempre a tabela por consultor — o escopo dele e uma
    loja so, entao a agregacao por loja renderia uma unica linha. Os
    demais perfis (admin/gestor/gerente_comercial) abrem na visao por
    loja e alternam para a de consultor pelo toggle.
    """
    somente_bmg_help = st.toggle(
        "Somente BMG/Help",
        key="dist_prod_bmg_help",
        help=(
            "Restringe toda a tabela — valor e quantidade — aos bancos "
            "BMG e Help."
        ),
    )

    if perfil == "supervisor":
        _render_distribuicao_por_consultor(
            df, df_sup, "tab_dist_prod_sup_cons", com_busca=False,
            somente_bmg_help=somente_bmg_help,
        )
        return

    ver_consultor = st.toggle(
        "Ver por Consultor",
        key="dist_prod_ver_consultor",
        help=(
            "Desligado: distribuicao agregada por loja. Ligado: detalhe "
            "por consultor, com busca."
        ),
    )
    if ver_consultor:
        _render_distribuicao_por_consultor(
            df, df_sup, "tab_dist_prod_cons", com_busca=True,
            somente_bmg_help=somente_bmg_help,
        )
    else:
        _render_distribuicao_por_loja(df, somente_bmg_help=somente_bmg_help)


def render_tab_analiticos(
    df, df_sup, df_analise, df_cancelados, perfil: str = "",
    reconquista: dict | None = None,
):
    """Renderiza aba de Analiticos."""
    sac.divider(
        label="Analiticos Detalhados",
        icon="bar-chart-fill",
        align="left",
        color="blue",
    )

    _render_busca_ade(df, df_analise, df_cancelados)

    _is_consultor = perfil == "consultor"

    # Sub-navegacao em st.pills (nao sac.tabs) pelo mesmo motivo da nav
    # principal em app.py: o sac roda em iframe e o CSS empacotado na lib
    # tem `.ant-tabs-nav-more{display:none}`, entao as abas que nao cabem
    # na largura ficam INACESSIVEIS, nao apenas cortadas — e CSS do
    # documento pai nao atravessa o iframe. Com 7 itens de rotulo longo
    # (a partir de "Cobranca Consignavel") isso passou a acontecer em
    # telas menores, escondendo "Distribuicao de Produtos", o ultimo da
    # lista. O button group do st.pills tem flex-wrap: quebra em linhas.
    # `required=True` impede desselecionar e cair sem nenhuma sub-aba.
    opcoes = [
        "Propostas Pagas",
        "Em Analise",
        "Cancelados",
        "Aceleradores",
        "Reconquista",
        "Cobranca Consignavel",
    ]
    if not _is_consultor:
        opcoes.append("Distribuicao de Produtos")

    menu = st.pills(
        "Sub-navegacao de Analiticos",
        options=opcoes,
        default=opcoes[0],
        required=True,
        format_func=lambda r: f":material/{_ICONES_ANALITICOS[r]}: {r}",
        label_visibility="collapsed",
        key="nav_analiticos",
    )

    if menu == "Propostas Pagas":
        _render_detalhamento_pagos(df, df_sup)

    elif menu == "Em Analise":
        _render_detalhamento_em_analise(df_analise)

    elif menu == "Cancelados":
        _render_detalhamento_cancelados(df_cancelados)
        _render_oportunidades_perdidas(df_cancelados, perfil)
        _render_assertividade_consultores(
            df, df_analise, df_cancelados, df_sup
        )

    elif menu == "Aceleradores":
        _render_aceleradores(df, df_analise, df_cancelados)

    elif menu == "Reconquista":
        _render_reconquista(reconquista)

    elif menu == "Cobranca Consignavel":
        _render_cobranca_consignavel(reconquista)

    elif menu == "Distribuicao de Produtos":
        _render_distribuicao_produtos(df, df_sup, perfil)
