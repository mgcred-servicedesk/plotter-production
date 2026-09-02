"""
Aba Gestao: apuracao por produto MIX com filtro multi-criterio.

Tres eixos montam a leitura — nivel (consultor/loja/supervisor/regiao),
metrica (valor, quantidade, ticket medio, share do mix) e os criterios
por produto, que podem ser absolutos (R$) ou relativos (% da media, da
meta, ou percentil). A combinacao aceita E, OU e "pelo menos N".
O recorte inteiro pode ser salvo como preset (tabela ``gestao_presets``,
migracao 064).

Visivel apenas para admin/gestor/gerente_comercial (gating em
permissions.py). O ``df`` recebido ja passou por RLS em ``app.py``,
entao o gerente_comercial ve somente as suas regioes — o mesmo vale
para ``df_universo``, que traz os consultores ATIVOS do RH para que quem
nao vendeu nada no periodo tambem apareca na lista.
"""
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.config.settings import MESES_PT
from src.dashboard.auth import usuario_logado
from src.dashboard.components.tables import exibir_tabela
from src.dashboard.formatters import (
    formatar_decimal,
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)
from src.dashboard.kpis.gestao import (
    ACEL_SUPER_CONTA,
    BASE_ABSOLUTA,
    BASE_MEDIA_GRUPO,
    BASE_MEDIA_REGIAO,
    BASE_META,
    BASE_PERCENTIL,
    COL_DIAS,
    COL_TOTAL,
    COLUNAS_ID,
    COMB_E,
    COMB_MINIMO,
    COMB_OU,
    METRICA_PROD_DIA,
    METRICA_QTD,
    METRICA_SHARE,
    METRICA_TICKET,
    METRICA_VALOR,
    MODO_ACIMA,
    MODO_ATE,
    MODO_ENTRE,
    MODO_POSITIVO,
    MODO_ZERO,
    NIVEL_CONSULTOR,
    NIVEL_LOJA,
    NIVEL_REGIAO,
    NIVEL_SUPERVISOR,
    PRODUTOS_GESTAO,
    ROTULOS_ACELERADORES,
    calcular_lacuna,
    construir_tabela,
    diagnosticar_criterios,
    filtrar_por_criterios,
    matriz_metas,
)
# Aliases `_PROD`: `kpis.gestao` e `kpis.produtividade` tem colunas de
# mesmo nome (COL_DIAS, COL_LOJA) com papeis diferentes — uma e coluna
# da matriz de produtos, a outra da tabela nominal de performance.
from src.dashboard.kpis.produtividade import (
    COL_COMPETENCIA,
    COL_CONSULTOR as COL_CONSULTOR_PROD,
    COL_DIAS as COL_DIAS_PROD,
    COL_IDX_LOJA as COL_IDX_LOJA_PROD,
    COL_IDX_REGIAO as COL_IDX_REGIAO_PROD,
    COL_LOJA as COL_LOJA_PROD,
    COL_PROD_DIA as COL_PROD_DIA_PROD,
    COL_PRODUCAO as COL_PRODUCAO_PROD,
    benchmark_por,
    linhas_sem_vinculo,
    produtividade_carteira,
    produtividade_por_consultor,
    serie_por_consultor,
    variacao_ultima_competencia,
)
from src.dashboard.loaders import (
    CAMPO_CADASTRO,
    CAMPO_PAGAMENTO,
    MAX_MESES_INTERVALO,
    carregar_presets_gestao,
    excluir_preset_gestao,
    meses_do_intervalo,
    salvar_preset_gestao,
)
from src.dashboard.ui.charts import criar_grafico_produtividade
from src.dashboard.ui.header import chart_card_close, chart_card_open

_PRODUTO_LABELS = list(PRODUTOS_GESTAO)
# "Total" e criterio de primeira classe: a pergunta mais comum da
# gestao ("quem produziu menos de X no periodo") nao exigia nenhuma
# logica nova — a coluna ja existia na tabela.
#
# Aceleradores entram na mesma lista, no fim: sao criterio como
# qualquer produto ("quem fez CLT baixo E menos de 2 BMG Med"), mas
# medidos SEMPRE em quantidade de contratos.
_COLUNAS_CRITERIO = [*_PRODUTO_LABELS, COL_TOTAL, *ROTULOS_ACELERADORES]
_PRODUTOS_DEFAULT = ["CLT", "CNC", "Consignado"]

_COL_LACUNA = "Falta p/ limiar"
_COL_LACUNA_ACEL = "Falta acelerador (qtd)"


def _eh_acelerador(rotulo: str) -> bool:
    return rotulo in ROTULOS_ACELERADORES

_NIVEIS = {
    "Consultor": NIVEL_CONSULTOR,
    "Loja": NIVEL_LOJA,
    "Supervisor": NIVEL_SUPERVISOR,
    "Regiao": NIVEL_REGIAO,
}

_METRICAS = {
    "Valor pago (R$)": METRICA_VALOR,
    "Contratos (qtd)": METRICA_QTD,
    "Ticket medio (R$)": METRICA_TICKET,
    "Share no mix (%)": METRICA_SHARE,
    "Produtividade (R$/dia elegivel)": METRICA_PROD_DIA,
}

_MODOS = {
    "Ate (≤)": MODO_ATE,
    "Entre": MODO_ENTRE,
    "A partir de (≥)": MODO_ACIMA,
    "Sem venda (= 0)": MODO_ZERO,
    "Com venda (> 0)": MODO_POSITIVO,
}

_BASES = {
    "Valor absoluto": BASE_ABSOLUTA,
    "% da media do grupo": BASE_MEDIA_GRUPO,
    "% da media da regiao": BASE_MEDIA_REGIAO,
    "Percentil do grupo": BASE_PERCENTIL,
    "% da meta": BASE_META,
}

_COMBINACOES = {
    "E — todos os criterios": COMB_E,
    "OU — qualquer criterio": COMB_OU,
    "Pelo menos N criterios": COMB_MINIMO,
}

# Modos que dispensam limiar: nao ha numero nem base a escolher.
_MODOS_SEM_LIMIAR = {MODO_ZERO, MODO_POSITIVO}

_CAMPOS_DATA = {
    "Data do pagamento": CAMPO_PAGAMENTO,
    "Data de cadastro": CAMPO_CADASTRO,
}

# Atalhos de faixa. Existem por dois motivos: substituem em pt-BR o
# "Choose a date range / None" do calendario (que e inglês-only, vem
# cravado no bundle do Streamlit) e cobrem as faixas que a gestao
# realmente pede, poupando o calendario na maioria dos acessos.
# "Ano ate agora" foi retirado de proposito: em dezembro varreria 12
# meses de contratos numa tacada, que e exatamente a consulta que o
# compute Nano nao aguenta. Faixas longas continuam possiveis pelo
# calendario, mas deixam de ser um clique acidental.
_ATALHOS_PERIODO = (
    "Mes atual",
    "Mes anterior",
    "Ultimos 30 dias",
    "Ultimos 3 meses",
)


def _primeiro_dia(ano: int, mes: int) -> date:
    """Primeiro dia de um mes, normalizando mes fora de 1..12."""
    while mes < 1:
        mes += 12
        ano -= 1
    while mes > 12:
        mes -= 12
        ano += 1
    return date(ano, mes, 1)


def faixa_do_atalho(nome: str, hoje: date) -> Optional[Tuple[date, date]]:
    """Converte um atalho na faixa (inicio, fim), ambos inclusivos.

    "Ultimos 30 dias" conta HOJE como um dos 30 (29 dias para tras) —
    e a leitura de quem pede "os ultimos 30 dias" olhando o dia de
    hoje. "Ultimos 3 meses" abre no primeiro dia de dois meses atras,
    somando o mes corrente: tres meses corridos, nao 90 dias.
    """
    if nome == "Mes atual":
        return hoje.replace(day=1), hoje
    if nome == "Mes anterior":
        fim = hoje.replace(day=1) - timedelta(days=1)
        return fim.replace(day=1), fim
    if nome == "Ultimos 30 dias":
        return hoje - timedelta(days=29), hoje
    if nome == "Ultimos 3 meses":
        return _primeiro_dia(hoje.year, hoje.month - 2), hoje
    return None


def _data_por_extenso(dia: date) -> str:
    """'1º de junho de 2026' — o calendario e inglês, isto nao e."""
    numero = "1º" if dia.day == 1 else str(dia.day)
    return f"{numero} de {MESES_PT[dia.month]} de {dia.year}"

_Criterios = Dict[str, Dict[str, float | str]]


def _rotulo_de(mapa: dict, valor: str, padrao: str) -> str:
    """Chave de exibicao a partir do valor interno (leitura de preset)."""
    for rotulo, interno in mapa.items():
        if interno == valor:
            return rotulo
    return padrao


def _aviso_base_elegivel() -> None:
    """Aviso PERMANENTE sobre o que o denominador e — e o que nao e.

    Nao e caption discreto de proposito: a leitura errada desse numero
    ("fulano trabalha pouco") e exatamente o risco que a base de
    vinculo carrega, e ela nao tem como se defender sozinha na tela.
    """
    st.warning(
        "**Base: dias de VINCULO, nao de presenca.** Ferias, faltas e "
        "afastamentos **nao** sao descontados — o dia conta enquanto a "
        "pessoa estiver vinculada a loja. Quem tirou ferias aparece com "
        "produtividade baixa sem ter produzido menos por dia "
        "trabalhado. Use para conversar com o time e priorizar "
        "acompanhamento; **nao** e insumo de decisao de RH.",
        icon=":material/info:",
    )


def _formatar_valor(valor: float, metrica: str) -> str:
    """Formata um numero na unidade da metrica ativa."""
    if metrica == METRICA_QTD:
        return formatar_numero(valor)
    if metrica == METRICA_SHARE:
        return formatar_percentual(valor)
    if metrica == METRICA_PROD_DIA:
        return f"{formatar_moeda(valor)}/dia"
    return formatar_moeda(valor)


# ── Presets ──────────────────────────────────────────


def _config_atual(
    nivel: str,
    metrica: str,
    combinacao: str,
    minimo: int,
    incluir_zerados: bool,
    produtos: List[str],
    criterios: _Criterios,
    periodo: Optional[dict] = None,
) -> dict:
    """Serializa o recorte inteiro para gravar em ``gestao_presets``.

    ``periodo`` guarda o intervalo personalizado com datas ABSOLUTAS
    (ISO). Um preset de periodo envelhece — reaplicado em outro mes,
    volta com as mesmas datas, nao "o mesmo intervalo relativo a hoje".
    E o comportamento previsivel; faixa movel fica como evolucao.
    """
    return {
        "nivel": nivel,
        "metrica": metrica,
        "combinacao": combinacao,
        "minimo": int(minimo),
        "incluir_zerados": bool(incluir_zerados),
        "produtos": list(produtos),
        "criterios": criterios,
        "periodo": periodo or {"ativo": False},
    }


def _periodo_config(
    ativo: bool,
    data_ini: Optional[date],
    data_fim: Optional[date],
    campo: str,
) -> dict:
    """Bloco de periodo do preset, com datas em ISO (serializavel)."""
    if not ativo or data_ini is None or data_fim is None:
        return {"ativo": False}
    return {
        "ativo": True,
        "data_ini": data_ini.isoformat(),
        "data_fim": data_fim.isoformat(),
        "campo": campo,
    }


def _datas_do_preset(periodo: dict) -> Optional[Tuple[date, date]]:
    """Le ``data_ini``/``data_fim`` do preset; ``None`` se ilegiveis.

    Preset gravado por outra versao (ou editado a mao no banco) nao
    pode derrubar a aba — data invalida vira "sem intervalo salvo" e a
    UI cai no padrao.
    """
    try:
        ini = date.fromisoformat(periodo["data_ini"])
        fim = date.fromisoformat(periodo["data_fim"])
    except (KeyError, TypeError, ValueError):
        return None
    return (ini, fim) if fim >= ini else None


_PRESET_PENDENTE = "_gestao_preset_pendente"


def _aplicar_preset_pendente() -> None:
    """Aplica o preset escolhido no run ANTERIOR, antes dos widgets.

    Streamlit proibe escrever em ``session_state[k]`` depois que o
    widget de chave ``k`` foi instanciado — e o botao "Aplicar" so e
    clicado depois que toda a aba ja renderizou. Por isso o clique
    apenas guarda a config e pede rerun; quem escreve de fato e esta
    funcao, chamada no topo do render.
    """
    config = st.session_state.pop(_PRESET_PENDENTE, None)
    if config:
        _aplicar_preset(config)


def _aplicar_preset(config: dict) -> None:
    """Escreve a config do preset nas chaves dos widgets.

    Preset antigo com chave faltando cai no default do widget — a
    tabela ``gestao_presets`` guarda jsonb justamente para que os eixos
    possam crescer sem invalidar o que ja foi salvo.
    """
    st.session_state["gestao_nivel"] = _rotulo_de(
        _NIVEIS, config.get("nivel"), "Consultor"
    )
    st.session_state["gestao_metrica"] = _rotulo_de(
        _METRICAS, config.get("metrica"), "Valor pago (R$)"
    )
    st.session_state["gestao_combinacao"] = _rotulo_de(
        _COMBINACOES, config.get("combinacao"), "E — todos os criterios"
    )
    st.session_state["gestao_minimo"] = int(config.get("minimo", 1) or 1)
    st.session_state["gestao_incluir_zerados"] = bool(
        config.get("incluir_zerados", True)
    )
    produtos = [
        p for p in config.get("produtos", []) if p in _COLUNAS_CRITERIO
    ]
    st.session_state["gestao_produtos"] = produtos

    periodo = config.get("periodo") or {}
    st.session_state["gestao_periodo_ativo"] = bool(periodo.get("ativo"))
    if periodo.get("ativo"):
        st.session_state["gestao_periodo_campo"] = _rotulo_de(
            _CAMPOS_DATA, periodo.get("campo"), "Data do pagamento"
        )
        datas = _datas_do_preset(periodo)
        if datas:
            st.session_state["gestao_periodo_datas"] = datas

    for rotulo, crit in (config.get("criterios") or {}).items():
        if rotulo not in _COLUNAS_CRITERIO:
            continue
        st.session_state[f"gestao_modo_{rotulo}"] = _rotulo_de(
            _MODOS, crit.get("modo"), "Ate (≤)"
        )
        st.session_state[f"gestao_base_{rotulo}"] = _rotulo_de(
            _BASES, crit.get("base"), "Valor absoluto"
        )
        for chave, sufixo in (("min", "min"), ("max", "max")):
            if crit.get(chave) is not None:
                st.session_state[f"gestao_{sufixo}_{rotulo}"] = float(
                    crit[chave]
                )


def _render_presets(config_atual_fn) -> None:
    """Barra de presets: aplicar, salvar e excluir o recorte atual."""
    usuario = usuario_logado() or {}
    usuario_id = usuario.get("id", "")
    if not usuario_id:
        return

    try:
        presets = carregar_presets_gestao(usuario_id)
    except Exception:
        st.caption("⚠ Presets indisponiveis (verifique a migracao 064).")
        return

    with st.expander("Recortes salvos", expanded=False):
        if presets:
            rotulos = {
                (
                    p["nome"]
                    if p["proprio"]
                    else f"{p['nome']} (compartilhado)"
                ): p
                for p in presets
            }
            col_sel, col_aplicar, col_excluir = st.columns([3, 1, 1])
            with col_sel:
                escolhido = st.selectbox(
                    "Preset",
                    list(rotulos),
                    key="gestao_preset_sel",
                    label_visibility="collapsed",
                )
            preset = rotulos[escolhido]
            with col_aplicar:
                if st.button("Aplicar", key="gestao_preset_aplicar"):
                    # So guarda: escrever agora bateria na proibicao do
                    # Streamlit (widgets desta aba ja instanciados).
                    st.session_state[_PRESET_PENDENTE] = (
                        preset.get("config") or {}
                    )
                    st.rerun()
            with col_excluir:
                # Preset compartilhado por outra pessoa e somente
                # leitura: quem nao e dono nao apaga.
                if st.button(
                    "Excluir",
                    key="gestao_preset_excluir",
                    disabled=not preset["proprio"],
                ):
                    ok, msg = excluir_preset_gestao(usuario_id, preset["id"])
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
        else:
            st.caption("Nenhum recorte salvo ainda.")

        col_nome, col_share, col_salvar = st.columns([3, 1, 1])
        with col_nome:
            nome = st.text_input(
                "Nome do recorte",
                key="gestao_preset_nome",
                placeholder="Ex.: CLT abaixo da media",
                label_visibility="collapsed",
            )
        with col_share:
            compartilhar = st.toggle(
                "Compartilhar",
                key="gestao_preset_share",
                help="Deixa o recorte visivel (somente leitura) para os "
                     "demais usuarios.",
            )
        with col_salvar:
            if st.button("Salvar", key="gestao_preset_salvar"):
                nomes_proprios = {
                    p["nome"] for p in presets if p["proprio"]
                }
                if nome.strip() in nomes_proprios:
                    st.warning(
                        f"Ja existe um recorte seu chamado '{nome.strip()}'. "
                        "Salvar de novo substitui o anterior."
                    )
                ok, msg = salvar_preset_gestao(
                    usuario_id, nome, config_atual_fn(), compartilhar
                )
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()


# ── Criterios ────────────────────────────────────────


def _coletar_criterios(produtos: List[str], metrica: str) -> _Criterios:
    """Renderiza os controles por produto e devolve os criterios ativos."""
    criterios: _Criterios = {}
    unidade = {
        METRICA_QTD: "contratos",
        METRICA_SHARE: "%",
        METRICA_TICKET: "R$",
        METRICA_PROD_DIA: "R$/dia",
    }.get(metrica, "R$")

    for rotulo in produtos:
        acelerador = _eh_acelerador(rotulo)
        st.markdown(
            f"**{rotulo}**" + (" · contratos" if acelerador else "")
        )
        if rotulo == ACEL_SUPER_CONTA:
            # Unico acelerador que tambem e produto: sem esta linha,
            # da para achar que filtrar por ela tira o valor do CNC.
            st.caption(
                "O valor destas propostas continua somado em **CNC** "
                "(e no Total, se CNC estiver selecionado). Aqui o "
                "criterio e sobre a QUANTIDADE de Super Conta."
            )
        col_modo, col_base, col_a, col_b = st.columns([1.2, 1.2, 1, 1])
        with col_modo:
            modo = _MODOS[
                st.selectbox(
                    "Modo", list(_MODOS), key=f"gestao_modo_{rotulo}"
                )
            ]

        if modo in _MODOS_SEM_LIMIAR:
            criterios[rotulo] = {"modo": modo}
            continue

        # Acelerador nao tem meta individual: oferecer a base seria
        # oferecer um caminho que o filtro depois ignora.
        bases = (
            {k: v for k, v in _BASES.items() if v != BASE_META}
            if acelerador
            else _BASES
        )
        with col_base:
            base = bases[
                st.selectbox(
                    "Comparar com",
                    list(bases),
                    key=f"gestao_base_{rotulo}",
                    help="Bases relativas usam PERCENTUAL: 50% da media "
                         "do grupo, 80% da meta, percentil 20.",
                )
            ]

        relativo = base != BASE_ABSOLUTA
        # Acelerador conta contratos: passo 1 e teto na casa das
        # unidades. Um step de 1.000 aqui seria inutilizavel.
        if acelerador and not relativo:
            sufixo, passo, padrao_teto = "contratos", 1.0, 2.0
        elif metrica == METRICA_PROD_DIA and not relativo:
            # Valor por DIA vive na casa das centenas: um step de
            # 1.000 pularia a faixa inteira de uma vez.
            sufixo, passo, padrao_teto = unidade, 100.0, 700.0
        else:
            sufixo = "%" if relativo else unidade
            passo = 5.0 if relativo else 1000.0
            padrao_teto = 100.0 if relativo else 15000.0

        crit: Dict[str, float | str] = {"modo": modo, "base": base}
        if modo in (MODO_ENTRE, MODO_ACIMA):
            with col_a:
                crit["min"] = st.number_input(
                    f"Minimo ({sufixo})",
                    min_value=0.0,
                    value=0.0 if modo == MODO_ENTRE else padrao_teto,
                    step=passo,
                    key=f"gestao_min_{rotulo}",
                )
        if modo in (MODO_ENTRE, MODO_ATE):
            with col_b if modo == MODO_ENTRE else col_a:
                crit["max"] = st.number_input(
                    f"Maximo ({sufixo})",
                    min_value=0.0,
                    value=padrao_teto,
                    step=passo,
                    key=f"gestao_max_{rotulo}",
                )
        criterios[rotulo] = crit
    return criterios


def _render_resumo(
    resultado: pd.DataFrame,
    tabela: pd.DataFrame,
    lacuna_total: float,
    metrica: str,
    nivel: str,
    lacuna_acel: float = 0.0,
    lacuna_periodo: Optional[float] = None,
) -> None:
    """Cabecalho de leitura: quantos, que fatia do universo, quanto falta."""
    total = len(resultado)
    universo = len(tabela)
    pct = (total / universo * 100) if universo else 0.0

    col_a, col_b, col_c = st.columns(3)
    col_a.metric(
        f"{nivel}(es) no criterio",
        f"{total:,}".replace(",", "."),
        delta=f"{pct:.0f}% de {universo}",
        delta_color="off",
    )
    # Somar lacunas POR DIA de pessoas diferentes nao da dinheiro
    # nenhum. Na produtividade o card mostra a lacuna ja multiplicada
    # pelos dias de cada um: o que faltou no periodo, em R$.
    if metrica == METRICA_PROD_DIA and lacuna_periodo is not None:
        col_b.metric(
            "Falta p/ limiar (no periodo)", formatar_moeda(lacuna_periodo)
        )
    else:
        col_b.metric(
            "Falta p/ limiar (total)", _formatar_valor(lacuna_total, metrica)
        )
    # Em ticket e share, somar a coluna Total das linhas nao significa
    # nada (media de medias), entao o card exibe a media do grupo. Na
    # produtividade tambem nao: o card exibe a RAZAO DAS SOMAS do grupo
    # (producao total / dias totais), que e o mesmo criterio dos
    # benchmarks — media de medias daria o mesmo peso a quem teve 2
    # dias e a quem teve 23.
    if COL_TOTAL in resultado.columns and not resultado.empty:
        if metrica == METRICA_PROD_DIA:
            rotulo_c, valor_c = "Produtividade do grupo", (
                _produtividade_do_grupo(resultado)
            )
        elif metrica in (METRICA_TICKET, METRICA_SHARE):
            rotulo_c, valor_c = "Media do grupo", float(
                resultado[COL_TOTAL].mean()
            )
        else:
            rotulo_c, valor_c = "Producao do grupo", float(
                resultado[COL_TOTAL].sum()
            )
    else:
        rotulo_c, valor_c = "Producao do grupo", 0.0
    col_c.metric(rotulo_c, _formatar_valor(valor_c, metrica))

    if lacuna_acel > 0:
        st.caption(
            f"Aceleradores: faltam **{formatar_numero(lacuna_acel)} "
            "contratos** no total para o grupo sair dos criterios de "
            "acelerador."
        )

    if not resultado.empty and "Regiao" in resultado.columns:
        por_regiao = (
            resultado["Regiao"]
            .replace("", "(sem regiao)")
            .value_counts()
            .sort_index()
        )
        st.caption(
            "Por regiao: "
            + " · ".join(f"{r} {q}" for r, q in por_regiao.items())
        )


def _produtividade_do_grupo(resultado: pd.DataFrame) -> float:
    """Razao das somas do grupo exibido: producao total / dias totais.

    ``Total`` ja e producao/dia, entao ``Total * dias`` devolve a
    producao de cada linha. Linhas sem dia elegivel saem dos DOIS lados
    (o produto vira NaN e o ``sum`` as ignora) — nao ha producao sem
    denominador inflando o numero.
    """
    if resultado.empty or COL_DIAS not in resultado.columns:
        return 0.0
    dias = pd.to_numeric(resultado[COL_DIAS], errors="coerce")
    prod = pd.to_numeric(resultado[COL_TOTAL], errors="coerce") * dias
    dias_validos = dias.where(prod.notna()).sum()
    if not dias_validos:
        return 0.0
    return float(prod.sum() / dias_validos)


def _motivo_meta_indisponivel(
    periodo_ativo: bool,
    nivel: str,
    ignorados: Optional[List[str]] = None,
    metrica: str = METRICA_VALOR,
) -> str:
    """Explica por que a base '% da meta' caiu, na ordem que ela cai.

    Sem isso o aviso dava sempre a mesma razao (pack/nivel) mesmo
    quando o motivo real era outro — mandar o gestor investigar a
    coisa errada e pior do que nao avisar.
    """
    if ignorados and all(_eh_acelerador(r) for r in ignorados):
        return (
            "Acelerador nao tem meta individual: a base '% da meta' "
            "nao se aplica a ele. Use valor absoluto, media do grupo "
            "ou percentil."
        )
    if metrica == METRICA_PROD_DIA:
        return (
            "A meta e MENSAL em R$ e a metrica aqui e por DIA: comparar "
            "as duas daria um limiar dezenas de vezes maior que a "
            "realidade. Use valor absoluto, media do grupo/regiao ou "
            "percentil."
        )
    if periodo_ativo:
        return (
            "A meta e MENSAL e nao descreve um intervalo livre de datas: "
            "com periodo personalizado ativo, a base '% da meta' fica "
            "indisponivel."
        )
    if nivel != NIVEL_CONSULTOR:
        return (
            "A base '% da meta' e o alvo individual do consultor "
            f"(gravado por loja) — nao existe no nivel {nivel}."
        )
    return (
        "A base '% da meta' cobre apenas produtos com alvo individual: "
        "o pack (FGTS / ANT. DE BENEF. / CNC 13º) tem meta conjunta, "
        "sem alvo por categoria."
    )


def _render_periodo() -> Tuple[bool, Optional[date], Optional[date], str]:
    """Intervalo livre de datas, opcional, sobrepondo o mes da sidebar.

    Desligado (padrao), a aba usa o mes selecionado no dashboard —
    nenhuma mudanca para quem so quer o mes corrente. Ligado, a
    apuracao passa a ser da faixa escolhida, que pode cruzar meses
    anteriores.
    """
    ativo = st.toggle(
        "Periodo personalizado (ignora o mes da sidebar)",
        value=False,
        key="gestao_periodo_ativo",
        help=(
            "Apura uma faixa livre de datas, inclusive cobrindo meses "
            f"anteriores ao selecionado. Maximo de {MAX_MESES_INTERVALO} "
            "meses por consulta."
        ),
    )
    if not ativo:
        return False, None, None, CAMPO_PAGAMENTO

    hoje = date.today()

    # Os atalhos escrevem em session_state ANTES do date_input ser
    # instanciado (mais abaixo, nesta mesma funcao) — e por isso que
    # podem gravar direto na chave do widget sem o rodeio do rerun.
    colunas_atalho = st.columns(len(_ATALHOS_PERIODO))
    for coluna, nome in zip(colunas_atalho, _ATALHOS_PERIODO):
        with coluna:
            if st.button(
                nome,
                key=f"gestao_atalho_{nome}",
                use_container_width=True,
            ):
                faixa = faixa_do_atalho(nome, hoje)
                if faixa:
                    st.session_state["gestao_periodo_datas"] = faixa

    col_datas, col_campo = st.columns([2, 1])
    with col_datas:
        intervalo = st.date_input(
            "De / ate",
            value=(hoje.replace(day=1), hoje),
            format="DD/MM/YYYY",
            key="gestao_periodo_datas",
        )
    with col_campo:
        campo = _CAMPOS_DATA[
            st.selectbox(
                "Delimitar por",
                list(_CAMPOS_DATA),
                key="gestao_periodo_campo",
                help=(
                    "Pagamento: quanto ENTROU na faixa. Cadastro: o que "
                    "foi DIGITADO na faixa e ja pagou — contrato "
                    "cadastrado na faixa e ainda nao pago nao aparece, "
                    "porque a aba so le contratos pagos."
                ),
            )
        ]

    # date_input com range devolve tupla de 1 elemento enquanto o
    # usuario ainda nao escolheu a segunda data.
    if not isinstance(intervalo, (tuple, list)) or len(intervalo) < 2:
        st.info("Escolha a data final do intervalo.")
        return True, None, None, campo
    return True, intervalo[0], intervalo[1], campo


def _render_controles() -> Tuple[str, str, str, int, bool]:
    """Eixos da leitura: nivel, metrica, combinacao e universo."""
    col_nivel, col_metrica, col_comb = st.columns(3)
    with col_nivel:
        nivel = _NIVEIS[
            st.selectbox("Agrupar por", list(_NIVEIS), key="gestao_nivel")
        ]
    with col_metrica:
        metrica = _METRICAS[
            st.selectbox("Metrica", list(_METRICAS), key="gestao_metrica")
        ]
    with col_comb:
        combinacao = _COMBINACOES[
            st.selectbox(
                "Combinar criterios",
                list(_COMBINACOES),
                key="gestao_combinacao",
            )
        ]

    minimo = 1
    if combinacao == COMB_MINIMO:
        minimo = st.number_input(
            "Quantos criterios precisam ser atendidos",
            min_value=1,
            max_value=len(_COLUNAS_CRITERIO),
            value=1,
            step=1,
            key="gestao_minimo",
        )

    incluir_zerados = True
    if nivel == NIVEL_CONSULTOR:
        incluir_zerados = st.toggle(
            "Incluir consultores sem venda no periodo",
            value=True,
            key="gestao_incluir_zerados",
            help=(
                "Usa o cadastro de consultores ATIVOS do RH como universo. "
                "Desligado, a lista so contem quem teve algum pagamento — e "
                "um criterio como 'ate R$ 15.000' deixa de fora justamente "
                "quem nao vendeu nada."
            ),
        )
    return nivel, metrica, combinacao, int(minimo), incluir_zerados


def _render_criterios(
    df: pd.DataFrame,
    df_sup: Optional[pd.DataFrame] = None,
    df_universo: Optional[pd.DataFrame] = None,
    df_metas: Optional[pd.DataFrame] = None,
    carregar_intervalo: Optional[Callable] = None,
    df_vinculos: Optional[pd.DataFrame] = None,
) -> None:
    """Sub-visao de criterios: quem cabe no recorte de produto/limiar."""
    _aplicar_preset_pendente()

    st.markdown(
        "Monte o recorte: **agrupamento**, **metrica** e os **criterios** "
        "por produto. Limiares sao **inclusivos** e podem ser absolutos "
        "ou relativos (% da media, da meta, ou percentil)."
    )

    periodo_ativo, data_ini, data_fim, campo_data = (
        _render_periodo() if carregar_intervalo else
        (False, None, None, CAMPO_PAGAMENTO)
    )
    if periodo_ativo:
        if data_ini is None or data_fim is None:
            return
        df, aviso = carregar_intervalo(data_ini, data_fim, campo_data)
        if aviso:
            st.warning(aviso)
        if df.empty:
            if not aviso:
                st.warning(
                    "Nenhum contrato pago no intervalo selecionado."
                )
            return
        # O numero na tela deixou de ser o do mes da sidebar: diz isso
        # em voz alta, para ninguem ler a lista como se fosse do mes.
        rotulo_campo = _rotulo_de(
            _CAMPOS_DATA, campo_data, "Data do pagamento"
        )
        n_meses = len(meses_do_intervalo(data_ini, data_fim, campo_data))
        st.info(
            f"Apurando de **{_data_por_extenso(data_ini)}** a "
            f"**{_data_por_extenso(data_fim)}** "
            f"({data_ini:%d/%m/%Y} – {data_fim:%d/%m/%Y}) por "
            f"**{rotulo_campo.lower()}**, varrendo {n_meses} "
            f"{'mes' if n_meses == 1 else 'meses'}. "
            "O mes da sidebar esta ignorado nesta aba."
        )
        if campo_data == CAMPO_CADASTRO:
            st.caption(
                "⚠ Por data de cadastro, contrato digitado no intervalo "
                "e ainda NAO pago nao aparece — a aba le apenas "
                "contratos pagos."
            )
        # Meta e mensal: nao descreve uma faixa livre de datas. Zerar
        # df_metas faz a base '% da meta' cair no aviso de criterio
        # ignorado, em vez de comparar com um alvo que nao vale aqui.
        df_metas = None

    nivel, metrica, combinacao, minimo, incluir_zerados = _render_controles()

    produtos_sel = st.multiselect(
        "Produtos e aceleradores do criterio",
        _COLUNAS_CRITERIO,
        default=_PRODUTOS_DEFAULT,
        key="gestao_produtos",
        help=(
            "A coluna Total soma apenas os PRODUTOS escolhidos. "
            "Aceleradores (BMG Med, Vida Familiar, Emissao, Super "
            "Conta) contam contratos e ficam fora do Total — sao "
            "outra unidade. Super Conta e CNC em valor: o dinheiro "
            "dela ja esta somado em CNC, a coluna de acelerador so "
            "acrescenta a contagem."
        ),
    )

    # Total = soma dos produtos do criterio. "Total" e uma coluna
    # derivada, nao um produto: quando ele proprio e escolhido como
    # criterio, nao entra na propria soma. Aceleradores tambem ficam
    # de fora — contam contratos, nao a metrica dos produtos.
    produtos_total = [
        p for p in produtos_sel
        if p != COL_TOTAL and not _eh_acelerador(p)
    ]
    acels_sel = [p for p in produtos_sel if _eh_acelerador(p)]

    # A meta e MENSAL em R$: comparar um alvo do mes com um numero por
    # DIA daria um limiar 20x maior que a realidade. Zerar aqui faz a
    # base '% da meta' cair no aviso de criterio ignorado, o mesmo
    # caminho ja usado pelo periodo personalizado.
    if metrica == METRICA_PROD_DIA:
        df_metas = None

    tabela = construir_tabela(
        df,
        df_sup,
        df_universo if incluir_zerados else None,
        nivel=nivel,
        metrica=metrica,
        produtos_total=produtos_total or None,
        df_vinculos=df_vinculos,
    )
    if tabela.empty:
        st.warning("Nenhum dado no periodo para este agrupamento.")
        return

    if metrica == METRICA_PROD_DIA:
        _aviso_base_elegivel()
        sem_dias = int((tabela[COL_DIAS] <= 0).sum()) if (
            COL_DIAS in tabela.columns
        ) else 0
        if sem_dias:
            st.warning(
                f"**{sem_dias}** linha(s) sem dia elegivel no ledger de "
                "vinculos ficam com produtividade **em branco** — nao "
                "zero, e nao entram em nenhum criterio. Veja a "
                "sub-visao **Performance do time** para o diagnostico "
                "nominal."
            )

    if produtos_total:
        st.caption("Total = " + " + ".join(produtos_total))

    criterios = (
        _coletar_criterios(produtos_sel, metrica) if produtos_sel else {}
    )

    _render_presets(
        lambda: _config_atual(
            nivel,
            metrica,
            combinacao,
            minimo,
            incluir_zerados,
            produtos_sel,
            criterios,
            _periodo_config(
                periodo_ativo, data_ini, data_fim, campo_data
            ),
        )
    )

    # A base '% da meta' casa por Loja: so faz sentido no nivel
    # consultor, onde cada linha tem uma loja.
    metas = (
        matriz_metas(tabela, df_metas)
        if nivel == NIVEL_CONSULTOR
        else None
    )
    ignorados = diagnosticar_criterios(tabela, criterios, metas)
    if ignorados:
        st.warning(
            "Criterio ignorado em: "
            + ", ".join(ignorados)
            + ". "
            + _motivo_meta_indisponivel(
                periodo_ativo, nivel, ignorados, metrica
            )
        )

    resultado = filtrar_por_criterios(
        tabela, criterios, combinacao, minimo, metas
    )

    sac.divider(label=nivel, icon="people", align="left", color="gray")

    # Duas lacunas, uma por unidade: produto segue a metrica,
    # acelerador conta contratos. Somar as duas num numero so nao
    # significaria nada.
    rotulos_produto = [
        c for c in (*_PRODUTO_LABELS, COL_TOTAL) if c in criterios
    ]
    if criterios:
        metas_res = (
            matriz_metas(resultado, df_metas)
            if metas is not None
            else None
        )
        lacuna = calcular_lacuna(
            resultado, criterios, metas_res, apenas=rotulos_produto
        )
        lacuna_acel = calcular_lacuna(
            resultado, criterios, None, apenas=acels_sel
        )
        # Na produtividade, a lacuna por linha e R$/dia: multiplicada
        # pelos dias de cada um, vira o dinheiro que faltou no periodo.
        lacuna_periodo = None
        if metrica == METRICA_PROD_DIA and COL_DIAS in resultado.columns:
            dias_res = pd.to_numeric(
                resultado[COL_DIAS], errors="coerce"
            ).fillna(0.0)
            lacuna_periodo = float((lacuna * dias_res).sum())
        _render_resumo(
            resultado,
            tabela,
            float(lacuna.sum()),
            metrica,
            nivel,
            float(lacuna_acel.sum()),
            lacuna_periodo,
        )
    else:
        lacuna = pd.Series(0.0, index=resultado.index)
        lacuna_acel = pd.Series(0.0, index=resultado.index)
        st.info("Selecione ao menos um produto para filtrar.")

    # Foco por produto: exibe apenas as colunas dos produtos
    # selecionados (mais identificacao), ocultando os demais. O Total
    # fica sempre visivel — e a leitura de contexto que evita concluir
    # que alguem "nao produz" quando so nao produz naquele produto.
    if produtos_sel:
        cols_id = [
            c for c in COLUNAS_ID[nivel] if c in resultado.columns
        ]
        # Dias segue a identificacao: sem ele, "R$ 900/dia" nao diz se
        # sao 23 dias de casa ou 2.
        if COL_DIAS in resultado.columns:
            cols_id.append(COL_DIAS)
        cols_prod = [c for c in _COLUNAS_CRITERIO if c in produtos_sel]
        if COL_TOTAL not in cols_prod and COL_TOTAL in resultado.columns:
            cols_prod.append(COL_TOTAL)
        resultado = resultado[cols_id + cols_prod]

    if criterios and lacuna.gt(0).any():
        resultado = resultado.assign(**{_COL_LACUNA: lacuna})
    if criterios and lacuna_acel.gt(0).any():
        resultado = resultado.assign(**{_COL_LACUNA_ACEL: lacuna_acel})

    # Colunas de acelerador (e a lacuna delas) sao SEMPRE quantidade,
    # nao importa a metrica dos produtos — por isso a tabela recebe
    # duas listas de formatacao, nunca uma so.
    colunas_qtd = [
        c for c in (*ROTULOS_ACELERADORES, _COL_LACUNA_ACEL, COL_DIAS)
        if c in resultado.columns
    ]
    colunas_valor = [
        c for c in (*_PRODUTO_LABELS, COL_TOTAL, _COL_LACUNA)
        if c in resultado.columns
    ]
    if metrica == METRICA_QTD:
        exibir_tabela(
            resultado, colunas_numero=[*colunas_valor, *colunas_qtd]
        )
    elif metrica == METRICA_SHARE:
        exibir_tabela(
            resultado,
            colunas_percentual=colunas_valor,
            colunas_numero=colunas_qtd,
        )
    else:
        exibir_tabela(
            resultado,
            colunas_moeda=colunas_valor,
            colunas_numero=colunas_qtd,
        )

    if not resultado.empty:
        csv = resultado.to_csv(index=False, sep=";", decimal=",")
        st.download_button(
            label="Exportar CSV",
            data=csv,
            file_name="consultores_gestao.csv",
            mime="text/csv",
            key="gestao_export",
            icon=":material/download:",
        )


# ══════════════════════════════════════════════════════
# Sub-visao: Performance do time
# ══════════════════════════════════════════════════════

_JANELAS_TENDENCIA = {"3 meses": 3, "6 meses": 6, "12 meses": 12}

# Quantos consultores a serie mostra ao mesmo tempo. Acima disso o
# grafico vira um novelo e ninguem le nenhuma das linhas.
_MAX_LINHAS_SERIE = 5


def _competencias_fechadas(
    mes: int,
    ano: int,
    quantas: int,
    hoje: Optional[date] = None,
) -> List[Tuple[int, int]]:
    """Ate ``quantas`` competencias FECHADAS terminando em (mes, ano).

    O mes corrente nunca entra: ele ainda esta sendo produzido, e um
    mes pela metade ao lado de meses inteiros desenha uma queda que nao
    existe. Se o mes da sidebar for o corrente, a serie termina no
    anterior. Devolve em ordem crescente.
    """
    hoje = hoje or date.today()
    ref_mes, ref_ano = int(mes), int(ano)
    # Corrente ou futura: cai para o mes ANTERIOR AO DE HOJE, nao para
    # o anterior ao pedido — senao um mes futuro devolveria meses que
    # ainda nem comecaram.
    if (ref_ano, ref_mes) >= (hoje.year, hoje.month):
        ref_mes, ref_ano = (
            (12, hoje.year - 1) if hoje.month == 1
            else (hoje.month - 1, hoje.year)
        )

    saida: List[Tuple[int, int]] = []
    for _ in range(max(int(quantas), 0)):
        saida.append((ref_mes, ref_ano))
        ref_mes, ref_ano = (
            (12, ref_ano - 1) if ref_mes == 1 else (ref_mes - 1, ref_ano)
        )
    return list(reversed(saida))


def _du_coluna(df_vinculos: pd.DataFrame, coluna: str) -> Optional[int]:
    """Le uma coluna de DU do loader de vinculos.

    A coluna e constante em todas as linhas (``loaders.py``,
    ``_fetch_vinculos_consultores``); o ``max`` so escolhe um valor sem
    depender da ordem.
    """
    if coluna not in df_vinculos.columns:
        return None
    valores = pd.to_numeric(df_vinculos[coluna], errors="coerce").dropna()
    if valores.empty:
        return None
    du = int(valores.max())
    return du if du > 0 else None


def _du_apuracao(
    df_vinculos: Optional[pd.DataFrame],
) -> Tuple[Optional[int], Optional[int]]:
    """``(DU considerados, DU do mes)`` da apuracao em tela.

    Os dois so divergem no mes EM CURSO, onde o loader trunca os dias
    elegiveis na ultima data com dado: ai o teto do denominador e o DU
    DECORRIDO, nao o do mes, e o card precisa dizer isso — "20,4 de 21"
    e "2,0 de 2" contam historias diferentes sobre o mesmo escopo.
    ``None`` quando o escopo nao trouxe a coluna; sem referencia o card
    mostra so a media.
    """
    if df_vinculos is None or df_vinculos.empty:
        return None, None
    du_mes = _du_coluna(df_vinculos, "DU_COMPETENCIA")
    du_considerado = _du_coluna(df_vinculos, "DU_DECORRIDOS") or du_mes
    return du_considerado, du_mes


def _render_cards_carteira(
    resumo: Dict[str, float],
    du_considerado: Optional[int] = None,
    du_mes: Optional[int] = None,
) -> None:
    """Quatro numeros do escopo, na razao das somas.

    O card de dias mostra a MEDIA por colaborador, nao a soma do
    escopo: a soma e dias-colaborador (112 pessoas x ~21 dias uteis =
    2.352) e, sob o rotulo "dias" num mes de 21, nao se le como KPI
    nenhum. A media contra o DU da competencia responde a pergunta que
    esta sub-visao faz — quanto de mes cada pessoa teve —, e o total
    continua visivel no ``help`` como base do R$/dia ao lado.

    No mes em curso os dois cards de dias falam do PERIODO DECORRIDO —
    e o rotulo diz isso. Numerador e denominador param na mesma data
    (``data_ref_apuracao``, no ``app.py``); ler "de 2 DU decorridos"
    avisa que o R$/dia ao lado ainda e uma amostra de dois dias, nao o
    mes.
    """
    parcial = bool(
        du_considerado and du_mes and du_considerado < du_mes
    )
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Producao paga", formatar_moeda(resumo["producao"]))
    col_b.metric(
        "Dias por colaborador",
        formatar_decimal(resumo["dias_por_colaborador"]),
        delta=(
            f"de {du_considerado} DU decorridos"
            if parcial
            else (
                f"de {du_considerado} DU na competencia"
                if du_considerado
                else "media do escopo"
            )
        ),
        delta_color="off",
        help=(
            "Media de dias uteis de VINCULO por pessoa no escopo. "
            f"Base: {formatar_numero(resumo['dias'])} dias-colaborador "
            f"({formatar_numero(resumo['colaboradores'])} pessoas x os "
            "dias de vinculo de cada uma) — o mesmo denominador do "
            "R$ por dia elegivel ao lado. Abaixo do teto = gente que "
            "entrou, saiu ou foi transferida no meio do periodo."
            + (
                f" Mes EM CURSO: a apuracao para no ultimo dia com "
                f"dado ({du_considerado} de {du_mes} DU do mes)."
                if parcial
                else ""
            )
        ),
    )
    col_c.metric(
        "R$ por dia elegivel",
        formatar_moeda(resumo["produtividade"]),
        delta=(
            f"razao das somas · {du_considerado} DU decorridos"
            if parcial
            else "razao das somas"
        ),
        delta_color="off",
        help=(
            "Producao paga do escopo dividida pelos dias elegiveis do "
            "MESMO escopo — razao das somas, nunca a media das "
            "produtividades individuais."
            + (
                " Mes em curso: os dois lados param na ultima data com "
                "dado, entao o valor ja e comparavel com o de uma "
                "competencia fechada — mas apoiado em "
                f"{du_considerado} de {du_mes} dias uteis, e uma "
                "amostra curta oscila."
                if parcial
                else ""
            )
        ),
    )
    col_d.metric(
        "Colaboradores",
        formatar_numero(resumo["colaboradores"]),
        delta=f"{int(resumo['sem_producao'])} sem venda no periodo",
        delta_color="off",
    )


def _render_tendencia(
    prod_atual: pd.DataFrame,
    mes: int,
    ano: int,
    carregar_competencia: Callable,
) -> None:
    """Serie de produtividade nas ultimas competencias FECHADAS."""
    janela = _JANELAS_TENDENCIA[
        st.radio(
            "Janela da serie",
            list(_JANELAS_TENDENCIA),
            index=1,
            horizontal=True,
            key="perf_janela",
        )
    ]
    competencias = _competencias_fechadas(mes, ano, janela)
    if not competencias:
        st.info("Nenhuma competencia fechada anterior a esta.")
        return

    frames: Dict[Tuple[int, int], pd.DataFrame] = {}
    with st.spinner("Carregando competencias fechadas..."):
        for m, a in competencias:
            df_c, df_vin_c, df_sup_c = carregar_competencia(m, a)
            if df_c is None or df_c.empty:
                continue
            frames[(a, m)] = produtividade_por_consultor(
                df_c, df_vin_c, df_sup_c
            )

    serie = serie_por_consultor(frames)
    if serie.empty:
        st.info(
            "Sem dados nas competencias fechadas da janela escolhida."
        )
        return

    # Carteira pela razao das somas de cada competencia — nunca a media
    # das produtividades individuais.
    com_dias = serie[serie[COL_DIAS_PROD] > 0]
    somas = com_dias.groupby(COL_COMPETENCIA)[
        [COL_PRODUCAO_PROD, COL_DIAS_PROD]
    ].sum()
    carteira = pd.DataFrame(
        {
            COL_COMPETENCIA: somas.index,
            COL_PROD_DIA_PROD: (
                somas[COL_PRODUCAO_PROD] / somas[COL_DIAS_PROD]
            ).to_numpy(),
        }
    )

    nomes = sorted(prod_atual[COL_CONSULTOR_PROD].dropna().unique())
    escolhidos = st.multiselect(
        "Comparar colaboradores na serie",
        nomes,
        default=[],
        max_selections=_MAX_LINHAS_SERIE,
        key="perf_serie_consultores",
        help=(
            "Ate cinco linhas alem da carteira. Competencia sem dado "
            "fica como LACUNA no grafico — a linha corta, em vez de "
            "ligar os pontos por cima do buraco."
        ),
    )
    detalhe = (
        serie[serie[COL_CONSULTOR_PROD].isin(escolhidos)]
        if escolhidos
        else None
    )

    chart_card_open(
        "Evolucao da produtividade",
        icon="📈",
        subtitle=(
            f"{len(frames)} competencia(s) fechada(s) · base de dias "
            "de vinculo, sem desconto de afastamento"
        ),
    )
    st.plotly_chart(
        criar_grafico_produtividade(carteira, detalhe), width="stretch"
    )
    chart_card_close()

    variacao = variacao_ultima_competencia(serie)
    if variacao.empty:
        st.caption(
            "Variacao exige duas competencias fechadas consecutivas na "
            "janela."
        )
        return

    subiu = int((variacao["Variacao %"] > 0).sum())
    caiu = int((variacao["Variacao %"] < 0).sum())
    lacuna = int(variacao["Variacao %"].isna().sum())
    st.caption(
        f"Entre as duas ultimas competencias fechadas: **{subiu}** "
        f"subiram, **{caiu}** cairam, **{lacuna}** sem comparacao "
        "possivel (nao aparecem nas duas)."
    )


def _render_performance(
    df: pd.DataFrame,
    df_sup: Optional[pd.DataFrame],
    df_vinculos: Optional[pd.DataFrame],
    mes: int,
    ano: int,
    carregar_competencia: Optional[Callable] = None,
) -> None:
    """Sub-visao nominal: como esta cada colaborador do escopo.

    Responde a pergunta que a sub-visao de criterios nao respondia:
    nao "quem cabe no recorte", e sim "qual o nivel de cada pessoa do
    time, corrigido pelo tempo que ela teve".
    """
    st.markdown(
        "Produtividade de cada colaborador da sua carteira: **producao "
        "paga dividida pelos dias uteis de vinculo** na competencia. "
        "Quem entrou no meio do mes deixa de ser lido como mau "
        "vendedor por ter tido menos dias."
    )
    _aviso_base_elegivel()

    if df_vinculos is None or df_vinculos.empty:
        st.warning(
            "Ledger de vinculos (`consultor_vigencia`) sem janelas nesta "
            "competencia para o seu escopo — sem ele nao ha denominador "
            "individual, e a produtividade nao pode ser calculada."
        )
        return

    prod = produtividade_por_consultor(df, df_vinculos, df_sup)
    if prod.empty:
        st.warning("Nenhum colaborador no escopo desta competencia.")
        return

    _du_considerado, _du_mes = _du_apuracao(df_vinculos)
    _render_cards_carteira(
        produtividade_carteira(prod), _du_considerado, _du_mes
    )

    sac.divider(
        label="Por colaborador", icon="person-badge", align="left",
        color="gray",
    )

    col_ordem, col_corte = st.columns([1.4, 1])
    with col_ordem:
        ordem = st.selectbox(
            "Ordenar por",
            [
                "Menor produtividade",
                "Maior produtividade",
                "Menor % da loja",
                "Maior producao",
            ],
            key="perf_ordem",
        )
    with col_corte:
        corte = st.slider(
            "Mostrar ate X% da media da loja",
            min_value=0,
            max_value=200,
            value=200,
            step=10,
            key="perf_corte",
            help=(
                "100% = exatamente a media da propria loja. Deixe em "
                "200% para ver o time inteiro. O corte e SEU: a aba "
                "nao classifica ninguem sozinha."
            ),
        )

    visao = prod[prod[COL_DIAS_PROD] > 0].copy()
    if corte < 200:
        visao = visao[visao[COL_IDX_LOJA_PROD] <= corte]

    ascendente = {
        "Menor produtividade": (COL_PROD_DIA_PROD, True),
        "Maior produtividade": (COL_PROD_DIA_PROD, False),
        "Menor % da loja": (COL_IDX_LOJA_PROD, True),
        "Maior producao": (COL_PRODUCAO_PROD, False),
    }[ordem]
    visao = visao.sort_values(
        ascendente[0], ascending=ascendente[1], na_position="last"
    ).reset_index(drop=True)

    if visao.empty:
        st.info("Nenhum colaborador dentro do corte escolhido.")
    else:
        st.caption(
            f"**{len(visao)}** de {int((prod[COL_DIAS_PROD] > 0).sum())} "
            "colaboradores com vinculo na competencia. "
            "**% da loja** e **% da regiao** comparam a pessoa com a "
            "razao das somas do proprio grupo (100% = na media)."
        )
        exibir_tabela(
            visao,
            colunas_moeda=[COL_PRODUCAO_PROD, COL_PROD_DIA_PROD],
            colunas_numero=[COL_DIAS_PROD],
            colunas_percentual=[COL_IDX_LOJA_PROD, COL_IDX_REGIAO_PROD],
        )
        st.download_button(
            label="Exportar CSV",
            data=visao.to_csv(index=False, sep=";", decimal=","),
            file_name=f"performance_consultores_{ano}_{mes:02d}.csv",
            mime="text/csv",
            key="perf_export",
            icon=":material/download:",
        )

    bench = benchmark_por(prod, COL_LOJA_PROD)
    if not bench.empty and len(bench) > 1:
        tabela_lojas = (
            pd.DataFrame(
                {
                    "Loja": bench.index,
                    COL_PROD_DIA_PROD: bench.to_numpy(),
                }
            )
            .sort_values(COL_PROD_DIA_PROD, ascending=False)
            .reset_index(drop=True)
        )
        with st.expander(
            f"Benchmark por loja ({len(tabela_lojas)} lojas no escopo)"
        ):
            exibir_tabela(
                tabela_lojas, colunas_moeda=[COL_PROD_DIA_PROD]
            )

    orfas = linhas_sem_vinculo(prod)
    if not orfas.empty:
        st.warning(
            f"**{len(orfas)}** pessoa(s) com producao paga e SEM janela "
            "de vinculo no ledger desta competencia. Ficam fora de "
            "todos os benchmarks e sem produtividade calculada — nao "
            "recebem denominador emprestado. Corrigir "
            "`consultor_vigencia` fecha o furo."
        )
        with st.expander("Producao sem vinculo no ledger"):
            exibir_tabela(
                orfas[
                    [COL_CONSULTOR_PROD, COL_LOJA_PROD, COL_PRODUCAO_PROD]
                ],
                colunas_moeda=[COL_PRODUCAO_PROD],
            )

    sac.divider(
        label="Tendencia", icon="graph-up", align="left", color="gray"
    )
    if carregar_competencia is None:
        st.info(
            "Serie historica indisponivel nesta sessao (loader de "
            "competencia nao injetado)."
        )
        return
    if not st.toggle(
        "Carregar serie das competencias fechadas",
        value=False,
        key="perf_tendencia",
        help=(
            "Carrega os meses anteriores sob demanda — cada competencia "
            "e uma leitura a mais no Supabase."
        ),
    ):
        st.caption(
            "Ligue para comparar a produtividade desta competencia com "
            "as anteriores."
        )
        return
    _render_tendencia(prod, mes, ano, carregar_competencia)


def render_tab_gestao(
    df: pd.DataFrame,
    df_sup: Optional[pd.DataFrame] = None,
    df_universo: Optional[pd.DataFrame] = None,
    df_metas: Optional[pd.DataFrame] = None,
    carregar_intervalo: Optional[Callable] = None,
    df_vinculos: Optional[pd.DataFrame] = None,
    mes: Optional[int] = None,
    ano: Optional[int] = None,
    carregar_competencia: Optional[Callable] = None,
) -> None:
    """Renderiza a aba de Gestao, com as duas sub-visoes.

    - **Criterios**: quem cabe num recorte de produto/limiar (a aba
      original, intacta).
    - **Performance do time**: como esta cada colaborador da carteira,
      medido por dia elegivel de vinculo.

    ``carregar_intervalo(ini, fim, campo) -> (df, aviso)`` e
    ``carregar_competencia(mes, ano) -> (df, df_vinculos, df_sup)`` sao
    injetados por ``app.py`` e ja devolvem os dados com RLS e filtros
    da sidebar aplicados. Sem eles, o periodo personalizado e a serie
    historica ficam indisponiveis e a aba segue no mes da sidebar.
    """
    sac.divider(
        label="Gestao de Consultores",
        icon="funnel-fill",
        align="left",
        color="blue",
    )

    # st.pills (nao sac.tabs) pelo mesmo motivo da nav principal em
    # app.py: o sac roda em iframe e o CSS da lib esconde o que nao
    # cabe na largura, deixando item INACESSIVEL.
    menu = st.pills(
        "Sub-navegacao de Gestao",
        options=["Criterios", "Performance do time"],
        default="Criterios",
        required=True,
        format_func=lambda r: (
            ":material/filter_alt: Criterios"
            if r == "Criterios"
            else ":material/speed: Performance do time"
        ),
        label_visibility="collapsed",
        key="nav_gestao",
    )

    if menu == "Criterios":
        _render_criterios(
            df, df_sup, df_universo, df_metas, carregar_intervalo,
            df_vinculos,
        )
    else:
        _render_performance(
            df,
            df_sup,
            df_vinculos,
            int(mes or date.today().month),
            int(ano or date.today().year),
            carregar_competencia,
        )
