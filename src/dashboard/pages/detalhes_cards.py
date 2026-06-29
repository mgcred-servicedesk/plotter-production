"""Paginas de detalhe (drill-down) dos cards de contexto.

Cada ``render_*`` corresponde a um dos quatro cards de contexto do
dashboard de vendas (Em Analise, Cancelados, Media por Consultor,
Media por Loja). Recebe os DataFrames ja carregados, com RLS e filtros
de UI aplicados pelo ``app.py``, calcula os detalhamentos via funcoes
puras de ``src.dashboard.kpis.detalhes_cards`` e renderiza com
``exibir_tabela`` (nunca ``st.dataframe`` direto).

Convencao de dividers: titulo da pagina em ``color="blue"``; quadros
internos em ``color="gray"``. Icones Bootstrap coerentes com o tema do
card.

Permissoes: o roteamento que aciona estas paginas so promove a
``card_page`` quando ``pode_ver('cards_drilldown', role)`` (admin,
gestor e gerente_comercial; supervisor/consultor sao fail-closed), com
leitura fail-closed do query param. Estas funcoes nao reavaliam permissao.
"""

from typing import Optional

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.formatters import (
    formatar_moeda,
    formatar_moeda_compacta,
    formatar_numero,
)
from src.dashboard.kpis.detalhes_cards import (
    COL_PRODUTO_DETALHADO,
    adicionar_produto_detalhado,
    detalhe_analise_pivot,
    detalhe_analise_por_regiao,
    detalhe_cancelados_pivot,
    detalhe_cancelados_por_regiao,
    detalhe_digitacao_diaria,
    detalhe_medias_por_produto,
    detalhe_medias_por_regiao,
    detalhe_reaproveitamento,
    filtrar_ultimo_dia,
    ocultar_colunas_zeradas,
)
from src.dashboard.ui.kpi_cards_reforma import _calcular_indicador_media


# ── Helpers ───────────────────────────────────────────────────────


def _dimensao_por_perfil(perfil: Optional[str]) -> str:
    """Retorna a dimensao de agrupamento dos detalhes por perfil.

    Admin e gestor veem o consolidado por REGIAO. Gerente comercial,
    cujo escopo e por regioes mas cujo foco operacional sao as lojas,
    ve por LOJA. Outros perfis (que nao deveriam acessar esta tela)
    defaultam para REGIAO.
    """
    if perfil == "gerente_comercial":
        return "LOJA"
    return "REGIAO"


# ── Colunas por tipo de formatacao (passadas a exibir_tabela) ──────

# Digitacao diaria: valor_digitado NAO casa o auto-detect de moeda.
_MOEDA_DIGITACAO = ["valor_digitado"]
_PERC_DIGITACAO = ["Var. %"]

# Medias por produto/regiao.
_MOEDA_MEDIAS = ["Valor", "Média", "Média DU", "Projeção"]
_NUMERO_MEDIAS = ["Qtd Base"]

# Reaproveitamento (sem projecao).
_MOEDA_REAP = ["Valor"]
_NUMERO_REAP = ["Quantidade"]


def _divider_quadro(label: str, icon: str) -> None:
    """Divider cinza padrao para um quadro interno de detalhe."""
    sac.divider(label=label, icon=icon, align="left", color="gray")


def _divider_titulo(label: str, icon: str) -> None:
    """Divider azul padrao para o titulo da pagina de detalhe."""
    sac.divider(label=label, icon=icon, align="left", color="blue")


# ──────────────────────────────────────────────────────────────────
# Em Analise
# ──────────────────────────────────────────────────────────────────


def _farol_html(
    valor: float,
    media_ref: float,
    maior_e_melhor: bool,
) -> str:
    """Span do farol comparando ``valor`` com a media entre regioes.

    Reusa ``_calcular_indicador_media`` (banda de ±10%). Quando
    ``maior_e_melhor`` for ``False`` (ex.: cancelados, onde ficar ACIMA
    da media e ruim), inverte apenas a cor/emoji do verde↔vermelho — a
    descricao "Acima/Abaixo da média" permanece factual.
    """
    emoji, cor, label_ind, descricao = _calcular_indicador_media(
        valor, media_ref
    )
    if not maior_e_melhor:
        inversao = {
            "🟢": ("🔴", "#EF4444"),
            "🔴": ("🟢", "#10A37F"),
        }
        if emoji in inversao:
            emoji, cor = inversao[emoji]
    return (
        f'<span style="color:{cor};">{emoji} {descricao} '
        f'({label_ind})</span>'
    )


def _card_dimensao(dimensao: str, valor_principal: str, sub_html: str) -> str:
    """Monta um card de dimensao (regiao/loja) no padrao ``mg-kpi-context``.

    ``flex: 1 1 220px`` deixa o card crescer para preencher a linha, mas
    o ``max-width`` impede que um card sozinho na ultima linha estique
    ate a largura toda (o "destaque" indevido). ``min-width:0`` permite
    encolher em telas estreitas.
    """
    return (
        f'<div class="mg-kpi-context" '
        f'style="flex:1 1 220px; max-width:300px; min-width:0;">'
        f'<div class="mg-kpi-ctx-label">📍 {dimensao}</div>'
        f'<div class="mg-kpi-ctx-valor">{valor_principal}</div>'
        f'<div class="mg-kpi-ctx-sub">{sub_html}</div>'
        f'</div>'
    )


def _fileira_cards(cards: list[str]) -> None:
    """Renderiza a fileira de cards centralizada, com respiro inferior.

    Flexbox com ``justify-content:center`` e quebra de linha: a fileira
    fica centralizada quando nao preenche a largura toda (poucos cards
    ou ultima linha apos quebra). O ``max-width`` por card (em
    ``_card_dimensao``) evita o card-destaque esticado. O ``margin-bottom``
    evita que os cards colem no quadro seguinte.
    """
    st.markdown(
        '<div style="display:flex; flex-wrap:wrap; '
        'justify-content:center; align-items:stretch; '
        'gap:clamp(10px,1.2vw,20px); '
        'margin-bottom:clamp(20px,2vw,32px);">'
        + "".join(cards)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_cards_dimensao(
    det: pd.DataFrame,
    du_decorridos: int,
    vazio_msg: str,
    maior_e_melhor: bool = True,
) -> None:
    """Cards por dimensao no topo da pagina (no lugar da tabela longa).

    ``det`` e um breakdown por REGIAO ou LOJA (saida de
    ``detalhe_analise_por_regiao`` / ``detalhe_cancelados_por_regiao``):
    colunas ``<dimensao>, Valor, Quantidade, Média DU, Projeção``.

    Cada card: titulo = dimensao; KPI principal = Valor; sub = Qtd,
    Média DU, Projeção (so com ``du_decorridos > 0``) e um farol que
    compara o Valor da dimensao com a MEDIA de Valor entre as dimensoes.
    ``maior_e_melhor=False`` inverte o farol (cancelados).
    """
    if det.empty:
        st.info(vazio_msg)
        return

    col_dim = det.columns[0]
    media_ref = float(det["Valor"].mean())
    tem_proj = du_decorridos > 0

    cards = []
    for _, row in det.iterrows():
        valor = float(row["Valor"])
        qtd = int(row["Quantidade"])
        media_du = float(row["Média DU"])
        projecao = float(row["Projeção"])
        linha_proj = (
            f"Projeção: <strong>{formatar_moeda_compacta(projecao)}</strong>"
            f"<br>"
            if tem_proj
            else ""
        )
        sub = (
            f'<span style="font-size:12px;">{formatar_moeda(valor)}</span><br>'
            f'{formatar_numero(qtd)} propostas<br>'
            f'Média DU: '
            f'<strong>{formatar_moeda_compacta(media_du)}</strong><br>'
            f'{linha_proj}'
            f'{_farol_html(valor, media_ref, maior_e_melhor)}'
        )
        cards.append(
            _card_dimensao(
                str(row[col_dim]), formatar_moeda_compacta(valor), sub
            )
        )

    _fileira_cards(cards)


def _render_cards_dimensao_medias(
    det: pd.DataFrame,
    base_plural: str,
    vazio_msg: str,
) -> None:
    """Cards por dimensao para as paginas de Média (Consultor / Loja).

    ``det`` e a saida de ``detalhe_medias_por_regiao``: colunas
    ``<dimensao>, Valor, Qtd Base, Média, Média DU, Projeção``. KPI
    principal = **Média** (por consultor/loja na dimensao); sub =
    quantidade da base, total, Média DU e Projeção fim do período. O
    farol compara a Média da dimensao com a media entre dimensoes (maior
    e melhor — produzir mais por consultor/loja e bom).
    """
    if det.empty:
        st.info(vazio_msg)
        return

    col_dim = det.columns[0]
    media_ref = float(det["Média"].mean())

    cards = []
    for _, row in det.iterrows():
        valor = float(row["Valor"])
        qtd_base = int(row["Qtd Base"])
        media = float(row["Média"])
        media_du = float(row["Média DU"])
        projecao = float(row["Projeção"])
        sub = (
            f'{formatar_numero(qtd_base)} {base_plural}<br>'
            f'Total: <strong>{formatar_moeda_compacta(valor)}</strong><br>'
            f'Média DU: '
            f'<strong>{formatar_moeda_compacta(media_du)}</strong><br>'
            f'Projeção: '
            f'<strong>{formatar_moeda_compacta(projecao)}</strong><br>'
            f'{_farol_html(media, media_ref, maior_e_melhor=True)}'
        )
        cards.append(
            _card_dimensao(
                str(row[col_dim]), formatar_moeda_compacta(media), sub
            )
        )

    _fileira_cards(cards)


def _exibir_pivot(pivot: pd.DataFrame, linha: str) -> None:
    """Exibe um pivot ja montado (colunas numericas em moeda).

    ``linha`` e a coluna-dimensao (ex.: ``REGIAO``); todas as demais sao
    valores monetarios. Colunas de valor inteiramente zeradas (ex.:
    ``OUTROS``) sao ocultadas. Pivot vazio → mensagem de "sem dados".
    """
    pivot = ocultar_colunas_zeradas(pivot, linha)
    if pivot.empty or pivot.shape[1] <= 1:
        st.info("Nenhum dado disponível para exibição.")
        return
    colunas_moeda = [c for c in pivot.columns if c != linha]
    exibir_tabela(pivot, colunas_moeda=colunas_moeda)


def _agregar_digitacao_diaria(
    df_digitacao_detalhe: pd.DataFrame,
) -> pd.DataFrame:
    """Reconstroi o agregado diario a partir do detalhe filtrado.

    O RPC ``obter_digitacao_diaria`` ja agrega por dia, mas sem colunas
    de dimensao (regiao/loja). Para garantir que a serie de "Ultimos 7
    Dias" use EXATAMENTE o mesmo escopo do pivot "Ultimo Dia Apurado",
    agregamos o detalhe ja filtrado por RLS.

    Entrada: colunas ``DATA_CADASTRO``, ``qtd_digitada``,
    ``valor_digitado``. Saida: colunas minusculas ``data_cadastro``,
    ``qtd_digitada``, ``valor_digitado`` (formato esperado por
    ``detalhe_digitacao_diaria``).
    """
    if df_digitacao_detalhe.empty:
        return pd.DataFrame(
            columns=["data_cadastro", "qtd_digitada", "valor_digitado"]
        )

    agregado = (
        df_digitacao_detalhe.groupby("DATA_CADASTRO", as_index=False)
        .agg({"qtd_digitada": "sum", "VALOR": "sum"})
        .rename(
            columns={
                "DATA_CADASTRO": "data_cadastro",
                "VALOR": "valor_digitado",
            }
        )
    )
    agregado["qtd_digitada"] = (
        pd.to_numeric(agregado["qtd_digitada"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
    agregado["valor_digitado"] = (
        pd.to_numeric(agregado["valor_digitado"], errors="coerce")
        .fillna(0.0)
    )
    return agregado


def render_detalhe_em_analise(
    *,
    df_analise: pd.DataFrame,
    df_digitacao_detalhe: pd.DataFrame,
    du_decorridos: int,
    du_total: int,
    perfil: Optional[str] = None,
) -> None:
    """Pagina de detalhe do card "Em Analise".

    Em vez de tabelas longas, surfa os KPIs como cards por dimensao no
    topo e resumos em pivots (formato da imagem-referencia):

    1. Cards por dimensao (Valor, Qtd, Média DU, Projeção, farol).
    2. Digitação do último dia — pivot dimensao × Produto da DIGITAÇÃO
       (todos os status), bate com o total digitado do dia.
    3. Ultimos 7 dias de digitacao — serie diaria (sem projecao).
    4. Analise por Produto — pivot dimensao × Produto (em análise).
    5. Analise por Banco — pivot dimensao × Banco (em análise).

    Os quadros 2 e 3 derivam do MESMO ``df_digitacao_detalhe`` (ja
    recortado por RLS client-side em ``app.py``): a série de 7 dias é
    reconstruída via ``_agregar_digitacao_diaria`` para usar exatamente o
    escopo do usuário — não o agregado global, que vazaria digitação de
    fora do escopo para perfis não-admin.

    Admin/gestor usam ``REGIAO``; gerente_comercial usa ``LOJA``.
    """
    dim = _dimensao_por_perfil(perfil)
    label_dim = "Loja" if dim == "LOJA" else "Região"

    _divider_titulo("Detalhe — Em Análise", "clock-history")

    # 1. Cards por dimensao
    _divider_quadro(f"Por {label_dim}", "map-fill")
    _render_cards_dimensao(
        detalhe_analise_por_regiao(
            df_analise, du_decorridos, du_total, dimensao=dim
        ),
        du_decorridos,
        "Sem contratos em análise para o período.",
    )

    # 2 + 3. Ultimo dia apurado (pivot) ao lado dos ultimos 7 dias
    col_dia, col_serie = st.columns([3, 2], gap="large")

    with col_dia:
        df_ultimo, rotulo = filtrar_ultimo_dia(df_digitacao_detalhe)
        _divider_quadro(
            f"Digitação do Último Dia{f' — {rotulo}' if rotulo else ''}",
            "calendar-check",
        )
        _exibir_pivot(
            detalhe_analise_pivot(
                adicionar_produto_detalhado(df_ultimo),
                dim,
                COL_PRODUTO_DETALHADO,
            ),
            dim,
        )

    with col_serie:
        _divider_quadro("Digitação — Últimos 7 Dias", "calendar-week")
        # Reconstrói o agregado diário a partir do detalhe JÁ recortado
        # por RLS — mesmo escopo do pivot "Último Dia" ao lado.
        df_dig = detalhe_digitacao_diaria(
            _agregar_digitacao_diaria(df_digitacao_detalhe),
            du_decorridos,
            du_total,
            ultimos_dias=7,
            incluir_projecao=False,
            base_variacao="valor",
        )
        if df_dig.empty:
            st.info(
                "Sem dados de digitação diária para o período. "
                "A série diária ainda não está disponível."
            )
        else:
            # Tabela objetiva: data, valor digitado e a variação % do
            # valor vs. o dia anterior (sem as colunas de quantidade).
            # Ordena do dia mais recente para o mais antigo (a Var. % ja
            # foi calculada vs. o dia anterior, entao a inversao e so de
            # exibicao).
            df_dig = df_dig[["data_cadastro", "valor_digitado", "Var. %"]]
            df_dig = df_dig.iloc[::-1].reset_index(drop=True)
            exibir_tabela(
                df_dig,
                colunas_moeda=_MOEDA_DIGITACAO,
                colunas_percentual=_PERC_DIGITACAO,
            )

    # 4. Analise por Produto (pivot dimensao × Produto, PACK desmembrado)
    _divider_quadro("Análise por Produto", "tags-fill")
    _exibir_pivot(
        detalhe_analise_pivot(
            adicionar_produto_detalhado(df_analise),
            dim,
            COL_PRODUTO_DETALHADO,
        ),
        dim,
    )

    # 5. Analise por Banco (pivot dimensao × Banco)
    _divider_quadro("Análise por Banco", "bank")
    _exibir_pivot(
        detalhe_analise_pivot(df_analise, dim, "BANCO"),
        dim,
    )


# ──────────────────────────────────────────────────────────────────
# Cancelados
# ──────────────────────────────────────────────────────────────────


def render_detalhe_cancelados(
    *,
    df_cancelados: pd.DataFrame,
    du_decorridos: int,
    du_total: int,
    perfil: Optional[str] = None,
) -> None:
    """Pagina de detalhe do card "Cancelados".

    Mesma logica do "Em Análise" (cards por dimensao + resumos em pivot),
    sobre os cancelados LIQUIDOS, mais o quadro de Reaproveitamento:

    1. Cards por dimensao (Valor, Qtd, Média DU, Projeção, farol). O farol
       e INVERTIDO — ficar acima da media de cancelamento e ruim.
    2. Cancelados por Produto — pivot dimensao × Produto (liquidos).
    3. Cancelados por Banco — pivot dimensao × Banco (liquidos).
    4. Reaproveitamento — composicao (redigitada/recuperada + oportunidade
       perdida por nivel); nao tem pivot/projecao.

    Admin/gestor usam ``REGIAO``; gerente_comercial usa ``LOJA``.
    """
    dim = _dimensao_por_perfil(perfil)
    label_dim = "Loja" if dim == "LOJA" else "Região"

    _divider_titulo("Detalhe — Cancelados", "exclamation-triangle-fill")

    # 1. Cards por dimensao (farol invertido: acima da media = ruim)
    _divider_quadro(f"Por {label_dim}", "map-fill")
    _render_cards_dimensao(
        detalhe_cancelados_por_regiao(
            df_cancelados, du_decorridos, du_total, dimensao=dim
        ),
        du_decorridos,
        "Sem cancelados líquidos para o período.",
        maior_e_melhor=False,
    )

    # 2. Cancelados por Produto (pivot dimensao × Produto, liquidos,
    #    PACK desmembrado)
    _divider_quadro("Cancelados por Produto", "tags-fill")
    _exibir_pivot(
        detalhe_cancelados_pivot(
            adicionar_produto_detalhado(df_cancelados),
            dim,
            COL_PRODUTO_DETALHADO,
        ),
        dim,
    )

    # 3. Cancelados por Banco (pivot dimensao × Banco, liquidos)
    _divider_quadro("Cancelados por Banco", "bank")
    _exibir_pivot(
        detalhe_cancelados_pivot(df_cancelados, dim, "BANCO"),
        dim,
    )

    # 4. Reaproveitamento (composicao, sem pivot/projecao)
    _divider_quadro("Reaproveitamento", "recycle")
    exibir_tabela(
        detalhe_reaproveitamento(df_cancelados),
        colunas_moeda=_MOEDA_REAP,
        colunas_numero=_NUMERO_REAP,
    )


# ──────────────────────────────────────────────────────────────────
# Medias por Consultor / Loja
# ──────────────────────────────────────────────────────────────────


def _render_detalhe_medias(
    *,
    titulo: str,
    icone: str,
    df: pd.DataFrame,
    base: str,
    du_decorridos: int,
    du_total: int,
    df_sup: Optional[pd.DataFrame],
    perfil: Optional[str] = None,
) -> None:
    """Renderiza as paginas de Media por Consultor / Loja (base unica).

    Mesma lógica das demais (cards por dimensao no topo), mas o KPI
    principal do card e a **Média** por consultor/loja. O resumo por
    produto fica como tabela (não há "pivot de valor" que represente
    média). Projeção linear = Média DU × du_total.

    Admin/gestor usam ``REGIAO``; gerente_comercial usa ``LOJA``.
    """
    dim = _dimensao_por_perfil(perfil)
    label_dim = "Loja" if dim == "LOJA" else "Região"

    _divider_titulo(titulo, icone)

    base_plural = "consultores" if base == "consultor" else "lojas"

    # 1. Cards por dimensao (KPI principal = Média por base)
    _divider_quadro(f"Por {label_dim}", "map-fill")
    _render_cards_dimensao_medias(
        detalhe_medias_por_regiao(
            df,
            base=base,
            du_decorridos=du_decorridos,
            du_totais=du_total,
            df_supervisores=df_sup,
            dimensao=dim,
        ),
        base_plural,
        f"Sem dados de média por {base} para o período.",
    )

    # 2. Por Produto (tabela-resumo de médias)
    _divider_quadro("Por Produto", "tags-fill")
    exibir_tabela(
        detalhe_medias_por_produto(
            df,
            base=base,
            du_decorridos=du_decorridos,
            du_totais=du_total,
            df_supervisores=df_sup,
        ),
        colunas_moeda=_MOEDA_MEDIAS,
        colunas_numero=_NUMERO_MEDIAS,
    )


def render_detalhe_media_consultor(
    *,
    df: pd.DataFrame,
    du_decorridos: int,
    du_total: int,
    df_sup: Optional[pd.DataFrame],
    perfil: Optional[str] = None,
) -> None:
    """Pagina de detalhe do card "Média por Consultor"."""
    _render_detalhe_medias(
        titulo="Detalhe — Média por Consultor",
        icone="person-fill",
        df=df,
        base="consultor",
        du_decorridos=du_decorridos,
        du_total=du_total,
        df_sup=df_sup,
        perfil=perfil,
    )


def render_detalhe_media_loja(
    *,
    df: pd.DataFrame,
    du_decorridos: int,
    du_total: int,
    df_sup: Optional[pd.DataFrame],
    perfil: Optional[str] = None,
) -> None:
    """Pagina de detalhe do card "Média por Loja"."""
    _render_detalhe_medias(
        titulo="Detalhe — Média por Loja",
        icone="shop",
        df=df,
        base="loja",
        du_decorridos=du_decorridos,
        du_total=du_total,
        df_sup=df_sup,
        perfil=perfil,
    )
