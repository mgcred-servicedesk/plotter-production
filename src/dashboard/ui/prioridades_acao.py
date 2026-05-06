"""
Prioridades de Ação — Prioridade 3 da Reforma UX/UI.

Identifica automaticamente onde a equipe deve focar:
- Produtos com maior gap
- Regiões com pior desempenho
- Lojas com pior desempenho
- Consultores abaixo do esperado
"""

from typing import Dict, List

import pandas as pd
import streamlit as st

from src.dashboard.formatters import formatar_moeda, formatar_percentual
from src.dashboard.ui.colors import (
    get_status_color,
    get_status_bg_color,
    get_status_label,
)


# Colunas de meta em `df_metas_produto` que NÃO estão em R$
# (são quantidades de produtos contados por unidade). Devem ficar
# fora do somatório quando a meta a calcular é em valor.
# Fonte: src/dashboard/kpis/gerais.py::_PRODUTOS_QTD
_META_PRODUTO_QTD_COLS = {
    "EMISSAO",
    "SUPER_CONTA",
    "BMG_MED",
    "VIDA_FAMILIAR",
}

# Aceleradores: produto, nome de exibição, coluna booleana no df,
# coluna de meta em df_metas_produto, ícone.
_ACELERADORES = [
    {
        "produto": "EMISSAO",
        "nome": "Emissão",
        "col_bool": "is_emissao_cartao",
        "col_meta": "EMISSAO",
        "icon": "🎯",
    },
    {
        "produto": "SUPER_CONTA",
        "nome": "Super Conta",
        "col_bool": "is_super_conta",
        "col_meta": "SUPER_CONTA",
        "icon": "💳",
    },
    {
        "produto": "BMG_MED",
        "nome": "BMG Med",
        "col_bool": "is_bmg_med",
        "col_meta": "BMG_MED",
        "icon": "🏥",
    },
    {
        "produto": "VIDA_FAMILIAR",
        "nome": "Vida Familiar",
        "col_bool": "is_seguro_vida",
        "col_meta": "VIDA_FAMILIAR",
        "icon": "🛡️",
    },
]


def calcular_prioridades_produto(
    metas_produto: List[Dict],
    top_n: int = 3,
) -> List[Dict]:
    """
    Identifica os produtos com maior prioridade de ação.

    Critérios:
    1. Menor % de atingimento
    2. Maior gap financeiro absoluto

    Returns:
        Lista de dicts com: produto, perc_ating, gap_valor, prioridade
    """
    prioridades = []

    for prod in metas_produto:
        if prod.get("is_mix", False):
            continue

        perc = float(prod.get("perc_atingido", 0) or 0)
        valor_atual = float(prod.get("valor_atual", 0) or 0)
        meta_total = float(prod.get("meta_total", 0) or 0)
        gap_valor = max(0.0, meta_total - valor_atual)

        # Score de prioridade: quanto menor o %, maior a prioridade
        # Peso: 70% % atingimento, 30% gap financeiro (em milhões)
        score = (100 - perc) * 0.7 + (gap_valor / 1_000_000) * 0.3

        # Só inclui produtos com meta cadastrada e abaixo dela
        if meta_total > 0 and perc < 100:
            prioridades.append(
                {
                    "produto": prod.get("produto", ""),
                    "perc_ating": perc,
                    "gap_valor": gap_valor,
                    "score": score,
                }
            )

    # Ordenar por prioridade (maior score primeiro)
    prioridades.sort(key=lambda x: x["score"], reverse=True)
    return prioridades[:top_n]


def calcular_prioridades_loja(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    top_n: int = 4,
) -> List[Dict]:
    """
    Identifica as lojas com maior prioridade de ação.

    Mesmo raciocínio de calcular_prioridades_regiao, mas agregado
    ao nível de loja individual.

    Returns:
        Lista de dicts com: loja, regiao, perc_ating, valor, meta, score
    """
    if df.empty or "LOJA" not in df.columns:
        return []

    # Meta por loja em valor: usa apenas a coluna MIX (meta em R$).
    meta_por_loja: Dict[str, float] = {}
    if not df_metas_produto.empty and "LOJA" in df_metas_produto.columns:
        if "MIX" in df_metas_produto.columns:
            meta_por_loja = dict(
                zip(
                    df_metas_produto["LOJA"],
                    pd.to_numeric(df_metas_produto["MIX"], errors="coerce")
                    .fillna(0)
                    .astype(float),
                )
            )

    # Mapeamento LOJA → REGIAO para exibição
    loja_regiao = {}
    if "REGIAO" in df.columns:
        loja_regiao = (
            df[["LOJA", "REGIAO"]]
            .drop_duplicates()
            .set_index("LOJA")["REGIAO"]
            .to_dict()
        )

    prioridades = []
    for loja in df["LOJA"].dropna().unique():
        df_loja = df[df["LOJA"] == loja]
        valor_realizado = (
            float(df_loja["VALOR"].sum()) if "VALOR" in df_loja.columns else 0.0
        )

        meta_loja = float(meta_por_loja.get(loja, 0.0))
        perc = (valor_realizado / meta_loja * 100) if meta_loja > 0 else 0

        if meta_loja > 0 and perc < 100:
            prioridades.append(
                {
                    "loja": loja,
                    "regiao": loja_regiao.get(loja, ""),
                    "perc_ating": perc,
                    "valor": valor_realizado,
                    "meta": meta_loja,
                    "score": 100 - perc,
                }
            )

    prioridades.sort(key=lambda x: x["score"], reverse=True)
    return prioridades[:top_n]


def calcular_prioridades_consultor(
    df: pd.DataFrame,
    df_sup: pd.DataFrame,
    du_decorridos: int,
    top_n: int = 4,
) -> List[Dict]:
    """
    Identifica consultores abaixo da média da própria loja.

    Exclui supervisores e consultores com poucos dias de atividade
    (considerados novos no período — menos de metade dos DU decorridos,
    mínimo 3 dias).

    Returns:
        Lista de dicts: consultor, loja, regiao, valor, perc_media, score
    """
    if df.empty or "CONSULTOR" not in df.columns or "VALOR" not in df.columns:
        return []

    # Nomes de supervisores para exclusão
    supervisores: set = set()
    if not df_sup.empty and "SUPERVISOR" in df_sup.columns:
        supervisores = set(df_sup["SUPERVISOR"].dropna().str.strip())

    # Consultor é "novo" se tiver menos de metade dos DU decorridos
    # em dias únicos de venda (mínimo 3 dias como piso).
    min_dias_ativos = max(3, du_decorridos // 2) if du_decorridos > 0 else 3

    dias_por_consultor: Dict[str, int] = {}
    if "DATA" in df.columns:
        dias_por_consultor = (
            df.groupby("CONSULTOR")["DATA"]
            .apply(lambda s: s.dt.date.nunique())
            .to_dict()
        )

    # Agregar valor e loja por consultor
    cols_agg: Dict[str, str] = {"VALOR": "sum", "LOJA": "first"}
    if "REGIAO" in df.columns:
        cols_agg["REGIAO"] = "first"

    grp = df.groupby("CONSULTOR").agg(cols_agg).reset_index()
    grp = grp.rename(columns={"VALOR": "valor_total", "LOJA": "loja"})
    if "REGIAO" in grp.columns:
        grp = grp.rename(columns={"REGIAO": "regiao"})
    else:
        grp["regiao"] = ""

    # Excluir supervisores
    grp = grp[~grp["CONSULTOR"].isin(supervisores)].copy()

    # Excluir consultores novos
    grp["dias_ativos"] = (
        grp["CONSULTOR"].map(dias_por_consultor).fillna(0).astype(int)
    )
    grp = grp[grp["dias_ativos"] >= min_dias_ativos].copy()

    if grp.empty:
        return []

    # Valor diário por consultor
    grp["valor_du"] = grp["valor_total"] / max(du_decorridos, 1)

    # Média diária da loja (entre consultores não-novos, não-supervisores)
    media_loja = grp.groupby("loja")["valor_du"].mean().to_dict()
    grp["media_loja_du"] = grp["loja"].map(media_loja).fillna(0)

    grp["perc_media"] = grp.apply(
        lambda r: (r["valor_du"] / r["media_loja_du"] * 100)
        if r["media_loja_du"] > 0
        else 0,
        axis=1,
    )

    # Apenas consultores abaixo de 80 % da média da loja
    abaixo = grp[grp["perc_media"] < 80].sort_values("perc_media")

    result = []
    for _, row in abaixo.head(top_n).iterrows():
        result.append(
            {
                "consultor": row["CONSULTOR"],
                "loja": row["loja"],
                "regiao": row.get("regiao", ""),
                "valor": float(row["valor_total"]),
                "valor_du": float(row["valor_du"]),
                "media_loja_du": float(row["media_loja_du"]),
                "perc_media": float(row["perc_media"]),
                "score": 100 - float(row["perc_media"]),
            }
        )

    return result


def calcular_prioridades_regiao(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    top_n: int = 3,
) -> List[Dict]:
    """
    Identifica as regiões com maior prioridade de ação.

    Meta regional em VALOR (R$) = soma da coluna MIX do df_metas_produto
    (coluna MIX = meta em valor de todos os produtos da loja), agregada por
    região via mapping LOJA → REGIAO presente em ``df``.

    Returns:
        Lista de dicts com: regiao, perc_ating, valor, meta, score
    """
    if df.empty or "REGIAO" not in df.columns or "LOJA" not in df.columns:
        return []

    # Meta por loja em valor: usa apenas a coluna MIX (meta em R$).
    # A coluna MIX representa o mix total de produtos em valor monetário.
    # Não somar outras colunas (CNC, FGTS, etc) pois já estão no MIX.
    meta_por_loja: Dict[str, float] = {}
    if not df_metas_produto.empty and "LOJA" in df_metas_produto.columns:
        if "MIX" in df_metas_produto.columns:
            meta_por_loja = dict(
                zip(
                    df_metas_produto["LOJA"],
                    pd.to_numeric(df_metas_produto["MIX"], errors="coerce")
                    .fillna(0)
                    .astype(float),
                )
            )

    # Mapping LOJA → REGIAO (a partir de df, fonte canônica)
    loja_regiao = df[["LOJA", "REGIAO"]].drop_duplicates().set_index("LOJA")["REGIAO"]

    prioridades = []
    for regiao in df["REGIAO"].dropna().unique():
        df_reg = df[df["REGIAO"] == regiao]
        valor_realizado = (
            float(df_reg["VALOR"].sum()) if "VALOR" in df_reg.columns else 0.0
        )

        lojas_regiao = [loja for loja, reg in loja_regiao.items() if reg == regiao]
        meta_regiao = float(sum(meta_por_loja.get(loja, 0.0) for loja in lojas_regiao))

        perc = (valor_realizado / meta_regiao * 100) if meta_regiao > 0 else 0

        if meta_regiao > 0 and perc < 100:
            prioridades.append(
                {
                    "regiao": regiao,
                    "perc_ating": perc,
                    "valor": valor_realizado,
                    "meta": meta_regiao,
                    "score": 100 - perc,
                }
            )

    prioridades.sort(key=lambda x: x["score"], reverse=True)
    return prioridades[:top_n]


def calcular_aceleradores_loja(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    top_n: int = 4,
) -> List[Dict]:
    """
    Para cada acelerador, retorna lojas zeradas (prioridade) ou as de
    pior desempenho ordenadas do pior para o melhor.

    Só inclui lojas com meta configurada. Se não houver meta para
    nenhuma loja num acelerador, a entrada é omitida.
    """
    if df.empty or "LOJA" not in df.columns:
        return []

    loja_regiao: Dict[str, str] = {}
    if "REGIAO" in df.columns:
        loja_regiao = (
            df[["LOJA", "REGIAO"]]
            .drop_duplicates()
            .set_index("LOJA")["REGIAO"]
            .to_dict()
        )

    resultado = []
    for acel in _ACELERADORES:
        col_bool = acel["col_bool"]
        col_meta = acel["col_meta"]

        if col_bool not in df.columns:
            continue

        # Contagem por loja
        qtd_por_loja = df.groupby("LOJA")[col_bool].sum().astype(int)

        # Meta por loja (apenas lojas com meta > 0)
        meta_por_loja: Dict[str, float] = {}
        if (
            not df_metas_produto.empty
            and col_meta in df_metas_produto.columns
            and "LOJA" in df_metas_produto.columns
        ):
            meta_por_loja = {
                loja: float(v)
                for loja, v in zip(
                    df_metas_produto["LOJA"],
                    pd.to_numeric(df_metas_produto[col_meta], errors="coerce").fillna(0),
                )
                if float(v) > 0
            }

        if not meta_por_loja:
            continue

        lojas_data = []
        for loja, qtd in qtd_por_loja.items():
            meta = meta_por_loja.get(loja)
            if meta is None:
                continue
            perc = (int(qtd) / meta * 100) if meta > 0 else 0.0
            lojas_data.append(
                {
                    "loja": loja,
                    "regiao": loja_regiao.get(loja, ""),
                    "qtd": int(qtd),
                    "meta": int(meta),
                    "perc": perc,
                }
            )

        zeros = [item for item in lojas_data if item["qtd"] == 0]
        nao_zeros = sorted(
            [item for item in lojas_data if item["qtd"] > 0],
            key=lambda x: x["perc"],
        )

        tem_zeros = bool(zeros)
        exibir = (zeros + nao_zeros)[:top_n] if tem_zeros else nao_zeros[:top_n]

        if not exibir:
            continue

        resultado.append(
            {
                "produto": acel["produto"],
                "nome": acel["nome"],
                "icon": acel["icon"],
                "lojas": exibir,
                "todos_zeros": zeros,  # lista completa, sem cap
                "tem_zeros": tem_zeros,
            }
        )

    return resultado


def calcular_aceleradores_consultor(
    df: pd.DataFrame,
    df_sup: pd.DataFrame,
    top_n: int = 4,
) -> List[Dict]:
    """
    Para cada acelerador, retorna consultores zerados (prioridade) ou os
    de pior desempenho (menor contagem em relação à média da organização).

    Exclui supervisores. Consultores sem nenhuma venda no mês (sem linha
    no df) não aparecem — só os que têm pelo menos uma linha.
    """
    if df.empty or "CONSULTOR" not in df.columns:
        return []

    supervisores: set = set()
    if df_sup is not None and not df_sup.empty and "SUPERVISOR" in df_sup.columns:
        supervisores = set(df_sup["SUPERVISOR"].dropna().str.strip())

    df_cons = df[~df["CONSULTOR"].isin(supervisores)].copy()
    if df_cons.empty:
        return []

    loja_por_cons: Dict[str, str] = {}
    if "LOJA" in df_cons.columns:
        loja_por_cons = df_cons.groupby("CONSULTOR")["LOJA"].first().to_dict()

    resultado = []
    for acel in _ACELERADORES:
        col_bool = acel["col_bool"]

        if col_bool not in df_cons.columns:
            continue

        qtd_por_cons = df_cons.groupby("CONSULTOR")[col_bool].sum().astype(int)

        total = int(qtd_por_cons.sum())
        num_cons = len(qtd_por_cons)
        media = total / num_cons if num_cons > 0 else 0.0

        cons_data = []
        for cons, qtd in qtd_por_cons.items():
            perc_media = (int(qtd) / media * 100) if media > 0 else 0.0
            cons_data.append(
                {
                    "consultor": cons,
                    "loja": loja_por_cons.get(cons, ""),
                    "qtd": int(qtd),
                    "media_org": round(media, 1),
                    "perc_media": perc_media,
                }
            )

        zeros = [c for c in cons_data if c["qtd"] == 0]
        nao_zeros = sorted(
            [c for c in cons_data if c["qtd"] > 0],
            key=lambda x: x["qtd"],
        )

        tem_zeros = bool(zeros)
        exibir = (zeros + nao_zeros)[:top_n] if tem_zeros else nao_zeros[:top_n]

        if not exibir:
            continue

        resultado.append(
            {
                "produto": acel["produto"],
                "nome": acel["nome"],
                "icon": acel["icon"],
                "consultores": exibir,
                "todos_zeros": zeros,  # lista completa, sem cap
                "tem_zeros": tem_zeros,
            }
        )

    return resultado


def _render_item_acelerador(nome: str, qtd: int, detalhe: str, is_zero: bool) -> str:
    """Retorna HTML de um item compacto de acelerador."""
    cor = "#EF4444" if is_zero else "#F59E0B"
    bg = "#FEF2F2" if is_zero else "#FFFBEB"
    return (
        f'<div class="mg-prioridade-card" style="'
        f'border-left-color:{cor}; padding:7px 10px; margin-bottom:5px;">'
        f'<div style="font-size:12px; font-weight:600; color:var(--mg-text);">'
        f"{nome}"
        f'<span class="mg-prioridade-badge" style="background:{bg}; color:{cor}; '
        f'font-size:11px; margin-left:6px;">{qtd}</span>'
        f"</div>"
        f'<div style="font-size:11px; color:var(--mg-text-muted); margin-top:2px;">'
        f"{detalhe}</div>"
        f"</div>"
    )


def _render_expander_zeros_loja(restantes: List[Dict], total: int) -> None:
    """Expander com as lojas zeradas ainda não exibidas.

    O label mostra o total de zerados; o conteúdo exibe apenas os itens
    além do top_n já visível, criando efeito de accordion.
    """
    with st.expander(f"Ver todas as {total} lojas zeradas"):
        itens_html = []
        for item in restantes:
            regiao = f" ({item['regiao']})" if item.get("regiao") else ""
            meta_txt = f"Meta: {item['meta']}" if item["meta"] > 0 else "s/ meta"
            itens_html.append(
                _render_item_acelerador(
                    f"{item['loja']}{regiao}",
                    item["qtd"],
                    meta_txt,
                    is_zero=True,
                )
            )
        st.markdown("".join(itens_html), unsafe_allow_html=True)


def _render_expander_zeros_consultor(restantes: List[Dict], total: int) -> None:
    """Expander com os consultores zerados ainda não exibidos.

    O label mostra o total de zerados; o conteúdo exibe apenas os itens
    além do top_n já visível, criando efeito de accordion.
    """
    with st.expander(f"Ver todos os {total} zerados"):
        itens_html = []
        for item in restantes:
            loja_txt = item["loja"] if item.get("loja") else ""
            itens_html.append(
                _render_item_acelerador(
                    item["consultor"],
                    item["qtd"],
                    loja_txt,
                    is_zero=True,
                )
            )
        st.markdown("".join(itens_html), unsafe_allow_html=True)


def render_prioridades_aceleradores(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    df_sup: pd.DataFrame,
    perfil: str = "",
) -> None:
    """
    Seção dedicada aos aceleradores dentro de Onde Agir Agora.

    Mostra, para cada acelerador, as lojas e/ou consultores zerados ou
    de pior desempenho — ajustado conforme o escopo do perfil (df já
    filtrado por RLS antes de chegar aqui).

    Para admin e gerente_comercial, quando há zeros além do top_n
    exibido, um expander permite ver a lista completa de zerados.
    """
    if df.empty:
        return

    mostrar_lojas = (
        "LOJA" in df.columns
        and df["LOJA"].nunique() > 1
        and perfil not in ("consultor",)
    )
    mostrar_consultores = (
        "CONSULTOR" in df.columns
        and df["CONSULTOR"].nunique() > 1
        and perfil not in ("consultor",)
    )

    if not mostrar_lojas and not mostrar_consultores:
        return

    acel_lojas = calcular_aceleradores_loja(df, df_metas_produto) if mostrar_lojas else []
    acel_cons = calcular_aceleradores_consultor(df, df_sup) if mostrar_consultores else []

    if not acel_lojas and not acel_cons:
        return

    pode_expandir = perfil in ("admin", "gestor", "gerente_comercial")

    st.markdown("---")
    st.markdown("### 🚀 Aceleradores — Onde Agir")

    lojas_map = {a["produto"]: a for a in acel_lojas}
    cons_map = {a["produto"]: a for a in acel_cons}

    cols = st.columns(4)
    for col, acel in zip(cols, _ACELERADORES):
        prod = acel["produto"]
        dados_loja = lojas_map.get(prod)
        dados_cons = cons_map.get(prod)

        tem_algo = (mostrar_lojas and dados_loja) or (mostrar_consultores and dados_cons)
        if not tem_algo:
            continue

        with col:
            st.markdown(
                f'<div style="font-size:15px; font-weight:700; '
                f'margin-bottom:8px; color:var(--mg-text);">'
                f'{acel["icon"]} {acel["nome"]}</div>',
                unsafe_allow_html=True,
            )

            if mostrar_lojas and dados_loja:
                tem_z = dados_loja["tem_zeros"]
                label = "🔴 Lojas Zeradas" if tem_z else "📉 Piores Lojas"
                st.caption(label)
                itens_html = []
                for item in dados_loja["lojas"]:
                    regiao = f" ({item['regiao']})" if item.get("regiao") else ""
                    meta_txt = (
                        f"Meta: {item['meta']} · {item['perc']:.0f}%"
                        if item["meta"] > 0
                        else "s/ meta"
                    )
                    itens_html.append(
                        _render_item_acelerador(
                            f"{item['loja']}{regiao}",
                            item["qtd"],
                            meta_txt,
                            item["qtd"] == 0,
                        )
                    )
                st.markdown("".join(itens_html), unsafe_allow_html=True)

                # Expander com os zerados além do top_n já visível
                todos_z = dados_loja.get("todos_zeros", [])
                exibidos_zeros = [i for i in dados_loja["lojas"] if i["qtd"] == 0]
                restantes_loja = todos_z[len(exibidos_zeros):]
                if pode_expandir and restantes_loja:
                    _render_expander_zeros_loja(restantes_loja, total=len(todos_z))

            if mostrar_consultores and dados_cons:
                tem_z = dados_cons["tem_zeros"]
                label = "🔴 Consultores Zerados" if tem_z else "📉 Consultores Abaixo"
                st.caption(label)
                itens_html = []
                for item in dados_cons["consultores"]:
                    loja_txt = item["loja"] if item.get("loja") else ""
                    detalhe = (
                        f"{loja_txt} · Média org: {item['media_org']:.1f}"
                        if item["media_org"] > 0
                        else loja_txt
                    )
                    itens_html.append(
                        _render_item_acelerador(
                            item["consultor"],
                            item["qtd"],
                            detalhe,
                            item["qtd"] == 0,
                        )
                    )
                st.markdown("".join(itens_html), unsafe_allow_html=True)

                # Expander com os zerados além do top_n já visível
                todos_z = dados_cons.get("todos_zeros", [])
                exibidos_zeros = [i for i in dados_cons["consultores"] if i["qtd"] == 0]
                restantes_cons = todos_z[len(exibidos_zeros):]
                if pode_expandir and restantes_cons:
                    _render_expander_zeros_consultor(restantes_cons, total=len(todos_z))


def _html_card_produto(i: int, prio: Dict) -> str:
    perc = prio["perc_ating"]
    cor = get_status_color(perc)
    bg_cor = get_status_bg_color(perc)
    label = get_status_label(perc)
    return (
        f'<div class="mg-prioridade-card" style="border-left-color: {cor};">'
        f'<div style="display: flex; align-items: center;">'
        f'<span class="mg-prioridade-numero" style="background: {cor};">{i}</span>'
        f'<span class="mg-prioridade-titulo">{prio["produto"]}'
        f'<span class="mg-prioridade-badge" style="background: {bg_cor}; color: {cor};">'
        f"{formatar_percentual(perc)} · {label}</span></span></div>"
        f'<div class="mg-prioridade-detalhe">Falta: {formatar_moeda(prio["gap_valor"])}</div>'
        f"</div>"
    )


def _html_card_loja(i: int, prio: Dict) -> str:
    perc = prio["perc_ating"]
    cor = get_status_color(perc)
    bg_cor = get_status_bg_color(perc)
    label = get_status_label(perc)
    regiao_label = f" ({prio['regiao']})" if prio.get("regiao") else ""
    return (
        f'<div class="mg-prioridade-card" style="border-left-color: {cor};">'
        f'<div style="display: flex; align-items: center;">'
        f'<span class="mg-prioridade-numero" style="background: {cor};">{i}</span>'
        f'<span class="mg-prioridade-titulo">{prio["loja"]}{regiao_label}'
        f'<span class="mg-prioridade-badge" style="background: {bg_cor}; color: {cor};">'
        f"{formatar_percentual(perc)} · {label}</span></span></div>"
        f'<div class="mg-prioridade-detalhe">'
        f"Realizado: {formatar_moeda(prio['valor'])} / Meta: {formatar_moeda(prio['meta'])}"
        f"</div></div>"
    )


def _html_card_regiao(i: int, prio: Dict) -> str:
    perc = prio["perc_ating"]
    cor = get_status_color(perc)
    bg_cor = get_status_bg_color(perc)
    label = get_status_label(perc)
    return (
        f'<div class="mg-prioridade-card" style="border-left-color: {cor};">'
        f'<div style="display: flex; align-items: center;">'
        f'<span class="mg-prioridade-numero" style="background: {cor};">{i}</span>'
        f'<span class="mg-prioridade-titulo">{prio["regiao"]}'
        f'<span class="mg-prioridade-badge" style="background: {bg_cor}; color: {cor};">'
        f"{formatar_percentual(perc)} · {label}</span></span></div>"
        f'<div class="mg-prioridade-detalhe">'
        f"Realizado: {formatar_moeda(prio['valor'])} / Meta: {formatar_moeda(prio['meta'])}"
        f"</div></div>"
    )


def _html_card_consultor(i: int, prio: Dict) -> str:
    perc = prio["perc_media"]
    cor = get_status_color(perc)
    bg_cor = get_status_bg_color(perc)
    loja_label = f" · {prio['loja']}" if prio.get("loja") else ""
    return (
        f'<div class="mg-prioridade-card" style="border-left-color: {cor};">'
        f'<div style="display: flex; align-items: center;">'
        f'<span class="mg-prioridade-numero" style="background: {cor};">{i}</span>'
        f'<span class="mg-prioridade-titulo">{prio["consultor"]}'
        f'<span class="mg-prioridade-badge" style="background: {bg_cor}; color: {cor};">'
        f"{formatar_percentual(perc)} da média</span></span></div>"
        f'<div class="mg-prioridade-detalhe">'
        f"{loja_label} · Média/DU: {formatar_moeda(prio['valor_du'])}"
        f" vs média loja: {formatar_moeda(prio['media_loja_du'])}"
        f"</div></div>"
    )


def _render_lista_com_expander(
    lista: List[Dict],
    top_n: int,
    fn_html,
    label_expander: str,
    msg_vazia: str,
) -> None:
    """Renderiza top_n itens e, se houver mais, um expander com o restante."""
    if not lista:
        st.info(msg_vazia)
        return
    exibir = lista[:top_n]
    restantes = lista[top_n:]
    st.markdown(
        "".join(fn_html(i, p) for i, p in enumerate(exibir, 1)),
        unsafe_allow_html=True,
    )
    if restantes:
        with st.expander(f"Ver mais {len(restantes)} {label_expander}"):
            st.markdown(
                "".join(fn_html(i, p) for i, p in enumerate(restantes, top_n + 1)),
                unsafe_allow_html=True,
            )


def render_prioridades_acao(
    metas_produto: List[Dict],
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    kpis: Dict,
    perfil: str = "",
    df_sup: pd.DataFrame = None,
    du_decorridos: int = 0,
) -> None:
    """
    Renderiza o bloco de Prioridades de Ação.

    Layout padrão (3 colunas):
      col1: Produtos que Precisam de Atenção
      col2: Regiões que Precisam de Atenção
      col3: Lojas que Precisam de Atenção

    Layout Gerente Comercial:
      col1: Produtos que Precisam de Atenção
      col2: Lojas que Precisam de Atenção
      col3: Consultores que Precisam de Atenção

    Todos os painéis exibem top_n automaticamente; os itens além do
    limite ficam num expander com numeração contínua.
    """
    if df_sup is None:
        df_sup = pd.DataFrame()

    st.markdown("---")
    st.markdown("### 🎯 Onde Agir Agora (Prioridades)")

    # Busca todos os elegíveis (sem cap) — fatiamento acontece no render
    prioridades_prod = calcular_prioridades_produto(metas_produto, top_n=50)
    prioridades_reg = calcular_prioridades_regiao(df, df_metas_produto, top_n=50)
    prioridades_loja = calcular_prioridades_loja(df, df_metas_produto, top_n=50)

    _eh_gerente = perfil == "gerente_comercial"

    if _eh_gerente:
        prioridades_consultor = calcular_prioridades_consultor(
            df, df_sup, du_decorridos, top_n=50
        )
    else:
        prioridades_consultor = []

    # Container principal
    css_prioridades = """
    <style>
    .mg-prioridade-card {
        background: var(--mg-surface);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 12px;
        border-left: 4px solid var(--mg-primary);
        transition: all 0.2s ease;
    }
    .mg-prioridade-card:hover {
        transform: translateX(4px);
        box-shadow: var(--mg-shadow-sm);
    }
    .mg-prioridade-numero {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        background: var(--mg-primary);
        color: white;
        font-size: 14px;
        font-weight: 700;
        border-radius: 50%;
        margin-right: 12px;
    }
    .mg-prioridade-titulo {
        font-size: 16px;
        font-weight: 600;
        color: var(--mg-text);
    }
    .mg-prioridade-detalhe {
        font-size: 14px;
        color: var(--mg-text-muted);
        margin-left: 40px;
        margin-top: 4px;
    }
    .mg-prioridade-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 13px;
        font-weight: 600;
        margin-left: 8px;
    }
    </style>
    """
    st.markdown(css_prioridades, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**🔥 Produtos que Precisam de Atenção**")
        _render_lista_com_expander(
            prioridades_prod, 3, _html_card_produto,
            "produtos", "Todos os produtos atingiram a meta! 🎉",
        )

    with col2:
        if _eh_gerente:
            st.markdown("**🏪 Lojas que Precisam de Atenção**")
            _render_lista_com_expander(
                prioridades_loja, 4, _html_card_loja,
                "lojas", "Todas as lojas estão acima da meta! 🎉",
            )
        else:
            st.markdown("**📍 Regiões que Precisam de Atenção**")
            _render_lista_com_expander(
                prioridades_reg, 2, _html_card_regiao,
                "regiões", "Todas as regiões estão acima da meta! 🎉",
            )

    with col3:
        if _eh_gerente:
            st.markdown("**👤 Consultores que Precisam de Atenção**")
            _render_lista_com_expander(
                prioridades_consultor, 4, _html_card_consultor,
                "consultores", "Todos os consultores estão acima de 80% da média da loja! 🎉",
            )
        else:
            st.markdown("**🏪 Lojas que Precisam de Atenção**")
            _render_lista_com_expander(
                prioridades_loja, 4, _html_card_loja,
                "lojas", "Todas as lojas estão acima da meta! 🎉",
            )

    # Seção dedicada dos Aceleradores
    render_prioridades_aceleradores(df, df_metas_produto, df_sup, perfil)

    # Resumo de ação
    st.markdown("---")

    # Gerar mensagem de ação sugerida
    acoes = []
    if prioridades_prod:
        top_prod = prioridades_prod[0]
        acoes.append(
            f"Focar em **{top_prod['produto']}** (falta de {formatar_moeda(top_prod['gap_valor'])})"
        )
    if _eh_gerente:
        if prioridades_loja:
            top_loja = prioridades_loja[0]
            acoes.append(
                f"Atuar na loja **{top_loja['loja']}** ({formatar_percentual(top_loja['perc_ating'])} da meta)"
            )
        if prioridades_consultor:
            top_cons = prioridades_consultor[0]
            acoes.append(
                f"Apoiar **{top_cons['consultor']}** ({formatar_percentual(top_cons['perc_media'])} da média da loja)"
            )
    else:
        if prioridades_reg:
            top_reg = prioridades_reg[0]
            acoes.append(
                f"Apoiar região **{top_reg['regiao']}** ({formatar_percentual(top_reg['perc_ating'])} da meta)"
            )
        if prioridades_loja:
            top_loja = prioridades_loja[0]
            acoes.append(
                f"Atuar na loja **{top_loja['loja']}** ({formatar_percentual(top_loja['perc_ating'])} da meta)"
            )

    if acoes:
        itens = "".join(f'<li style="margin-bottom: 4px;">{a}</li>' for a in acoes)
        st.markdown(
            f"""
            <div style="background: var(--mg-primary-soft);
                        border: 1px solid var(--mg-primary-ring);
                        padding: 16px 20px; border-radius: 12px;
                        margin-top: 16px;">
                <div style="font-size: 14px; font-weight: 600;
                            color: var(--mg-primary);
                            margin-bottom: 8px;">
                    💡 Ações Recomendadas para Hoje:
                </div>
                <ul style="margin: 0; padding-left: 20px;
                           color: var(--mg-primary);">
                    {itens}
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
