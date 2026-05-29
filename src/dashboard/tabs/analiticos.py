"""
Aba Analiticos: detalhamento de contratos (pagos/em analise/
cancelados), consultores por produto, producao por regiao e
distribuicao de produtos.
"""

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.config.settings import PRODUTOS_EMISSAO
from src.dashboard.components.tables import exibir_tabela
from src.dashboard.formatters import formatar_moeda, formatar_numero
from src.dashboard.kpis.produtos import calcular_distribuicao_produtos


def _exportar_csv(df: pd.DataFrame, nome: str, key: str):
    """Botao de download CSV para uma tabela."""
    csv = df.to_csv(index=False, sep=";", decimal=",")
    st.download_button(
        label=f"Exportar {nome}",
        data=csv,
        file_name=f"{nome}.csv",
        mime="text/csv",
        key=key,
        icon=":material/download:",
    )


def _render_detalhamento_pagos(df, df_sup):
    """Sub-aba: detalhamento de contratos pagos."""
    if df.empty:
        st.warning("Nenhum contrato pago no periodo.")
        return

    st.markdown(f"**{len(df):,} contratos pagos**".replace(",", "."))

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key="det_pago_loja")
    with col2:
        consultores = ["Todos"] + sorted(
            df["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_pago_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df.columns:
            produtos += sorted(
                [
                    str(x) for x in df["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_pago_prod"
        )

    df_d = df.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

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
    cols += ["TIPO_PRODUTO", "TIPO OPER.", "VALOR", "BANCO"]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA": "Data Pagamento",
            "TIPO_PRODUTO": "Produto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(df_tabela, colunas_moeda=["Valor"])
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

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(
            df_analise["LOJA"].unique().tolist()
        )
        filt_loja = st.selectbox(
            "Loja", lojas, key="det_analise_loja"
        )
    with col2:
        consultores = ["Todos"] + sorted(
            df_analise["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_analise_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df_analise.columns:
            produtos += sorted(
                [
                    str(x)
                    for x in df_analise["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_analise_prod"
        )

    df_d = df_analise.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

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
    cols += [
        "TIPO_PRODUTO", "TIPO OPER.", "VALOR",
        "STATUS_BANCO", "BANCO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
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
    exibir_tabela(df_tabela, colunas_moeda=["Valor"])
    _exportar_csv(
        df_tabela, "contratos_em_analise", "exp_analise"
    )


def _render_detalhamento_cancelados(df_cancel):
    """Sub-aba: detalhamento de contratos cancelados."""
    if df_cancel.empty:
        st.warning("Nenhum contrato cancelado no periodo.")
        return

    st.markdown(
        f"**{len(df_cancel):,} contratos cancelados**"
        .replace(",", ".")
    )

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(
            df_cancel["LOJA"].unique().tolist()
        )
        filt_loja = st.selectbox(
            "Loja", lojas, key="det_cancel_loja"
        )
    with col2:
        consultores = ["Todos"] + sorted(
            df_cancel["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_cancel_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df_cancel.columns:
            produtos += sorted(
                [
                    str(x)
                    for x in df_cancel["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_cancel_prod"
        )

    df_d = df_cancel.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

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
    cols += [
        "TIPO_PRODUTO", "TIPO OPER.", "VALOR",
        "SUB_STATUS", "STATUS_PAG", "BANCO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA_CADASTRO": "Data Cadastro",
            "TIPO_PRODUTO": "Produto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "SUB_STATUS": "Sub-Status",
            "STATUS_PAG": "Status Pagamento",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(df_tabela, colunas_moeda=["Valor"])
    _exportar_csv(
        df_tabela, "contratos_cancelados", "exp_cancel"
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

    df_all = pd.concat(resultados, ignore_index=True)

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
    cols_base += ["TIPO_PRODUTO", "TIPO OPER.", "VALOR", "BANCO"]

    df_res = (
        encontrados[[c for c in cols_base if c in encontrados.columns]]
        .sort_values("_DATA", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "_DATA": "Data",
            "TIPO_PRODUTO": "Produto",
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
        "loja", "regiao", "total_clientes", "reconquistados",
        "taxa_pct", "gap_pp", "saldo_medio", "dias_atraso_medio",
    ]
    df_view = por_loja[[c for c in cols if c in por_loja.columns]].rename(
        columns={
            "loja": "Loja",
            "regiao": "Regiao",
            "total_clientes": "Base",
            "reconquistados": "Reconquistados",
            "taxa_pct": "Taxa %",
            "gap_pp": "Gap (pp)",
            "saldo_medio": "Saldo Medio",
            "dias_atraso_medio": "Dias Atraso Medio",
        }
    ).sort_values("Taxa %", ascending=False)
    exibir_tabela(
        df_view,
        colunas_moeda=["Saldo Medio"],
        colunas_numero=["Base", "Reconquistados", "Dias Atraso Medio"],
    )
    _exportar_csv(df_view, "reconquista_por_loja", "exp_rec_loja")


def _render_reconquista_detalhamento(clientes: pd.DataFrame) -> None:
    """Listagem analitica completa — 1 linha por cliente (cod_ade)."""
    if clientes.empty:
        st.warning("Sem clientes nesta maciça no escopo atual.")
        return

    # Filtros locais
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        status_opts = ["Todos"] + sorted(
            clientes["status"].dropna().unique().tolist()
        ) if "status" in clientes.columns else ["Todos"]
        filt_status = st.selectbox("Status", status_opts, key="rec_det_status")

    with c2:
        lojas_opts = (
            sorted(clientes["loja"].dropna().unique().tolist())
            if "loja" in clientes.columns else []
        )
        filt_lojas = st.multiselect(
            "Loja", lojas_opts, key="rec_det_lojas",
            placeholder="Todas",
        )

    with c3:
        cons_opts = ["Todos"] + sorted(
            clientes["consultor"].dropna().unique().tolist()
        ) if "consultor" in clientes.columns else ["Todos"]
        filt_cons = st.selectbox("Consultor", cons_opts, key="rec_det_cons")

    with c4:
        bloqueio_opts = ["Todos", "Com bloqueio", "Sem bloqueio"]
        filt_bloq = st.selectbox(
            "Bloqueio", bloqueio_opts, key="rec_det_bloqueio"
        )

    df_f = clientes.copy()
    if filt_status != "Todos" and "status" in df_f.columns:
        df_f = df_f[df_f["status"] == filt_status]
    if filt_lojas and "loja" in df_f.columns:
        df_f = df_f[df_f["loja"].isin(filt_lojas)]
    if filt_cons != "Todos" and "consultor" in df_f.columns:
        df_f = df_f[df_f["consultor"] == filt_cons]
    if "mot_ipd_operar" in df_f.columns:
        if filt_bloq == "Com bloqueio":
            df_f = df_f[df_f["mot_ipd_operar"].notna() & (df_f["mot_ipd_operar"] != "")]
        elif filt_bloq == "Sem bloqueio":
            df_f = df_f[df_f["mot_ipd_operar"].isna() | (df_f["mot_ipd_operar"] == "")]

    st.caption(
        f"{len(df_f):,} de {len(clientes):,} clientes "
        "(últimos estados após filtros)."
    )

    cols = [
        "cod_ade", "loja", "regiao", "consultor",
        "status", "tipo_conversao", "mot_ipd_operar",
        "subproduto", "saldo_contabil", "dias_atraso", "faixa_atraso",
        "banco_origem", "banco_destino",
        "aparicoes", "primeira_aparicao", "ultima_aparicao",
    ]
    df_view = df_f[[c for c in cols if c in df_f.columns]].rename(
        columns={
            "cod_ade": "Cod ADE",
            "loja": "Loja",
            "regiao": "Regiao",
            "consultor": "Consultor",
            "status": "Status",
            "tipo_conversao": "Tipo Conversao",
            "mot_ipd_operar": "Bloqueio",
            "subproduto": "Subproduto",
            "saldo_contabil": "Saldo",
            "dias_atraso": "Dias Atraso",
            "faixa_atraso": "Faixa Atraso",
            "banco_origem": "Banco Origem",
            "banco_destino": "Banco Destino",
            "aparicoes": "Aparicoes",
            "primeira_aparicao": "1a Aparicao",
            "ultima_aparicao": "Ultima Aparicao",
        }
    ).sort_values("Aparicoes", ascending=False)

    exibir_tabela(
        df_view,
        colunas_moeda=["Saldo"],
        colunas_numero=["Dias Atraso", "Aparicoes"],
    )
    _exportar_csv(df_view, "reconquista_clientes", "exp_rec_clientes")


def _render_reconquista_resistentes(resistentes: pd.DataFrame) -> None:
    st.caption(
        f"{len(resistentes):,} clientes com 3+ aparições nesta maciça "
        "sem conversão. **Bloqueio** preenchido indica impedimento "
        "operacional (não é resistência real)."
    )
    if resistentes.empty:
        st.warning("Nenhum cliente nessa condição.")
        return
    cols = [
        "cod_ade", "loja", "consultor", "mot_ipd_operar",
        "aparicoes", "saldo_medio", "dias_atraso_medio",
        "primeira_aparicao", "ultima_aparicao",
    ]
    df_view = resistentes[[c for c in cols if c in resistentes.columns]].rename(
        columns={
            "cod_ade": "Cod ADE",
            "loja": "Loja",
            "consultor": "Consultor",
            "mot_ipd_operar": "Bloqueio",
            "aparicoes": "Aparicoes",
            "saldo_medio": "Saldo Medio",
            "dias_atraso_medio": "Dias Atraso Medio",
            "primeira_aparicao": "1a Aparicao",
            "ultima_aparicao": "Ultima Aparicao",
        }
    ).sort_values("Aparicoes", ascending=False)
    exibir_tabela(
        df_view,
        colunas_moeda=["Saldo Medio"],
        colunas_numero=["Aparicoes", "Dias Atraso Medio"],
    )
    _exportar_csv(df_view, "reconquista_resistentes", "exp_rec_resist")


def _render_reconquista(reconquista: dict | None):
    """Sub-aba Reconquista: drill-down da maciça ativa.

    Foco em loja/regiao (o lead pertence a loja). Detalhamento
    expoe listagem por cliente; Resistentes destaca o subconjunto
    acionavel (3+ aparicoes sem conversao).
    """
    if not reconquista or reconquista.get("macica") is None:
        st.info("Nenhuma maciça de reconquista disponível para este período.")
        return

    macica = reconquista["macica"]
    por_loja = reconquista.get("por_loja", pd.DataFrame())
    clientes = reconquista.get("clientes", pd.DataFrame())
    resistentes = reconquista.get("resistentes", pd.DataFrame())

    st.caption(
        f"Maciça **{macica.get('descricao') or macica.get('codigo', '')}** · "
        f"Meta: **{float(macica.get('meta_retencao') or 0):.0f}%** · "
        f"Primeiro envio: {macica.get('dat_primeiro_envio', '—')} · "
        f"Último envio: {macica.get('dat_ultimo_envio') or '—'}"
    )

    menu = sac.tabs(
        items=[
            sac.TabsItem(label="Por Loja", icon="shop"),
            sac.TabsItem(label="Detalhamento", icon="table"),
            sac.TabsItem(label="Resistentes", icon="exclamation-diamond"),
        ],
        align="start",
        variant="outline",
        key="acel_reconquista_tabs",
    )

    if menu == "Por Loja":
        _render_reconquista_por_loja(por_loja)
    elif menu == "Detalhamento":
        _render_reconquista_detalhamento(clientes)
    elif menu == "Resistentes":
        _render_reconquista_resistentes(resistentes)


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

    tab_items = [
        sac.TabsItem(label="Propostas Pagas", icon="check-circle"),
        sac.TabsItem(label="Em Analise", icon="hourglass-split"),
        sac.TabsItem(label="Cancelados", icon="x-circle"),
        sac.TabsItem(label="Aceleradores", icon="lightning-charge"),
        sac.TabsItem(label="Reconquista", icon="arrow-clockwise"),
    ]
    if not _is_consultor:
        tab_items.append(
            sac.TabsItem(label="Distribuicao de Produtos", icon="pie-chart")
        )

    menu = sac.tabs(
        items=tab_items,
        align="start",
        variant="outline",
    )

    if menu == "Propostas Pagas":
        _render_detalhamento_pagos(df, df_sup)

    elif menu == "Em Analise":
        _render_detalhamento_em_analise(df_analise)

    elif menu == "Cancelados":
        _render_detalhamento_cancelados(df_cancelados)

    elif menu == "Aceleradores":
        _render_aceleradores(df, df_analise, df_cancelados)

    elif menu == "Reconquista":
        _render_reconquista(reconquista)

    elif menu == "Distribuicao de Produtos":
        df_dist, cols_moeda, cols_num = calcular_distribuicao_produtos(df, df_sup)
        if not df_dist.empty:
            st.info("Distribuicao de valor (R$) e aceleradores (Qtd) por consultor")
            top_n = st.slider(
                "Exibir top N consultores",
                min_value=5,
                max_value=50,
                value=20,
                step=5,
            )
            exibir_tabela(
                df_dist.head(top_n),
                colunas_moeda=cols_moeda,
                colunas_numero=cols_num,
            )
            _exportar_csv(
                df_dist, "distribuicao_produtos",
                "exp_dist_prod",
            )
        else:
            st.warning("Dados nao disponiveis")
