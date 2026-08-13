"""
Tools que o assistente de IA (Claude) pode chamar.

O modelo NUNCA calcula KPI sozinho: cada tool aqui so reusa/reshapeia
funcoes ja existentes em kpis/*.py, sempre sobre dados pos-RLS.
``ChatContext`` nunca carrega frames pre-RLS (df_full/df_sup_full) —
ver docs/agents/rls.md — entao nenhuma tool tem como alcancar dado
fora do escopo do usuario logado.
"""
import logging
from typing import Callable, NamedTuple, Optional

import pandas as pd

from src.dashboard.kpis.comparativos import calcular_evolucao_por_entidade
from src.dashboard.kpis.rankings import (
    calcular_ranking_consultores,
    calcular_ranking_lojas,
    calcular_ranking_media_du,
    calcular_ranking_pontos,
    calcular_ranking_ticket_medio,
    listar_sem_producao,
)
from src.dashboard.loaders import (
    carregar_consultores_ativos,
    carregar_universo_lojas,
    consolidar_dados,
)
from src.dashboard.rls import aplicar_rls, aplicar_rls_supervisores
from src.dashboard.ui.sidebar import aplicar_filtros_ui
from src.shared.dias_uteis import calcular_dias_uteis

logger = logging.getLogger(__name__)

_LIMITE_MAXIMO = 25
_LIMITE_PADRAO = 10


class ChatContext(NamedTuple):
    """Dados ja carregados/pos-RLS do periodo selecionado no dashboard.

    Nunca inclua aqui frames pre-RLS (df_full/df_sup_full) — as tools
    fecham sobre este contexto e herdam qualquer escopo que ele carregue.
    """

    df: pd.DataFrame
    df_metas: pd.DataFrame
    df_sup: pd.DataFrame
    df_analise: pd.DataFrame
    df_cancelados: pd.DataFrame
    kpis: dict
    kpis_qtd: dict
    kpis_analise: dict
    kpis_cancel: dict
    medias: dict
    mes: int
    ano: int
    dia_atual: int
    du_decorridos: int
    role: Optional[str]


def _mes_ano_anterior(mes: int, ano: int) -> tuple[int, int]:
    return (mes - 1, ano) if mes > 1 else (12, ano - 1)


def _carregar_periodo_comparacao(
    contexto: ChatContext, periodo_comparacao: str
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Carrega e recorta (RLS + filtros de UI) o periodo de comparacao.

    Reaplica exatamente o mesmo escopo (perfil + filtros granulares) do
    periodo atual — nunca le o Supabase em escopo total. Mes de
    comparacao ja fechado: usa du_total como "dias decorridos" (mesmo
    idioma de tabs/produtos.py para o mes anterior).
    """
    if periodo_comparacao == "mesmo_mes_ano_anterior":
        mes_cmp, ano_cmp = contexto.mes, contexto.ano - 1
    else:
        mes_cmp, ano_cmp = _mes_ano_anterior(contexto.mes, contexto.ano)

    df_cmp, _df_metas_cmp, df_sup_cmp = consolidar_dados(mes_cmp, ano_cmp)
    df_cmp = aplicar_filtros_ui(aplicar_rls(df_cmp))
    df_sup_cmp = aplicar_rls_supervisores(df_sup_cmp, df_cmp)
    du_total_cmp, _, _ = calcular_dias_uteis(ano_cmp, mes_cmp, 1)
    return df_cmp, df_sup_cmp, du_total_cmp


def tool_comparar_entidades(contexto: ChatContext, entrada: dict) -> dict:
    """Quais lojas/consultores cresceram ou caíram vs. um período anterior."""
    entidade = str(entrada.get("entidade", "loja")).strip().lower()
    if entidade not in ("loja", "consultor"):
        return {"erro": f"entidade invalida: {entidade!r} (use 'loja' ou 'consultor')"}

    periodo_comparacao = entrada.get("periodo_comparacao", "mes_anterior")
    if periodo_comparacao not in ("mes_anterior", "mesmo_mes_ano_anterior"):
        periodo_comparacao = "mes_anterior"

    direcao = entrada.get("direcao", "todas")
    try:
        limite = min(int(entrada.get("limite") or _LIMITE_PADRAO), _LIMITE_MAXIMO)
    except (TypeError, ValueError):
        limite = _LIMITE_PADRAO

    try:
        # df_sup_cmp (cadastro de supervisores do periodo de comparacao)
        # nao e usado: calcular_evolucao_por_entidade aceita um unico
        # df_supervisores aplicado aos dois periodos — usamos o cadastro
        # ATUAL (contexto.df_sup) para os dois, deliberadamente ("quem e
        # supervisor hoje"). Rastrear quem era supervisor no periodo
        # anterior exigiria um segundo parametro na funcao de comparacao;
        # fora de escopo do MVP (impacto baixo: só afeta consultor que
        # deixou de ser supervisor entre os dois períodos).
        df_cmp, _df_sup_cmp, du_total_cmp = _carregar_periodo_comparacao(
            contexto, periodo_comparacao
        )
    except Exception:
        logger.exception("Chat IA: falha ao carregar periodo de comparacao")
        return {"erro": "Não consegui carregar o período de comparação."}

    coluna_entidade = "LOJA" if entidade == "loja" else "CONSULTOR"
    resultado = calcular_evolucao_por_entidade(
        df_atual=contexto.df,
        du_dec_atual=contexto.du_decorridos,
        df_ant=df_cmp,
        du_dec_ant=du_total_cmp,
        entidade=coluna_entidade,
        df_supervisores=contexto.df_sup,
    )
    if resultado.empty:
        return {
            "entidade": entidade,
            "periodo_comparacao": periodo_comparacao,
            "total_comparadas": 0,
            "resultados": [],
        }

    if direcao == "crescimento":
        # Inclui "nova" (sem produção no período anterior): do ponto de
        # vista do usuário, uma loja/consultor que saiu de zero também
        # "cresceu" — só não tem % calculável. Simétrico ao "queda"
        # abaixo, que inclui "descontinuada".
        mascara_crescimento = (resultado["Status"] == "nova") | (
            resultado["% Evolução"].notna() & (resultado["% Evolução"] > 0)
        )
        resultado = resultado[mascara_crescimento].sort_values(
            "% Evolução", ascending=False, na_position="last"
        )
    elif direcao == "queda":
        mascara_queda = resultado["Status"] == "descontinuada"
        if "% Evolução" in resultado.columns:
            mascara_queda = mascara_queda | (
                resultado["% Evolução"].notna() & (resultado["% Evolução"] < 0)
            )
        resultado = resultado[mascara_queda].sort_values(
            "% Evolução", ascending=True, na_position="first"
        )
    else:
        resultado = resultado.reindex(
            resultado["Variação Abs."].abs().sort_values(ascending=False).index
        )

    total = len(resultado)
    resultado = resultado.head(limite)

    label = "Loja" if entidade == "loja" else "Consultor"
    linhas = []
    for _, row in resultado.iterrows():
        variacao_pct = row.get("% Evolução")
        linhas.append(
            {
                "nome": row.get(label),
                "valor_anterior": round(float(row.get("Mês Anterior", 0.0)), 2),
                "valor_atual": round(float(row.get("Mês Atual", 0.0)), 2),
                "variacao_pct": (
                    round(float(variacao_pct), 1) if pd.notna(variacao_pct) else None
                ),
                "variacao_abs": round(float(row.get("Variação Abs.", 0.0)), 2),
                "status": row.get("Status"),
            }
        )

    return {
        "entidade": entidade,
        "periodo_comparacao": periodo_comparacao,
        "total_comparadas": total,
        "resultados": linhas,
    }


def tool_ranking_periodo(contexto: ChatContext, entrada: dict) -> dict:
    """Top N lojas/consultores no período atual, por critério."""
    entidade = str(entrada.get("entidade", "loja")).strip().lower()
    if entidade not in ("loja", "consultor"):
        return {"erro": f"entidade invalida: {entidade!r} (use 'loja' ou 'consultor')"}

    criterio = entrada.get("criterio", "atingimento")
    try:
        limite = min(int(entrada.get("limite") or _LIMITE_PADRAO), _LIMITE_MAXIMO)
    except (TypeError, ValueError):
        limite = _LIMITE_PADRAO

    try:
        if criterio == "atingimento":
            if entidade == "loja":
                ranking = calcular_ranking_lojas(
                    contexto.df, contexto.df_metas, top_n=limite
                )
            else:
                ranking = calcular_ranking_consultores(
                    contexto.df,
                    contexto.df_metas,
                    top_n=limite,
                    df_supervisores=contexto.df_sup,
                )
        elif criterio == "pontos":
            ranking = calcular_ranking_pontos(
                contexto.df,
                tipo=entidade,
                top_n=limite,
                df_supervisores=contexto.df_sup,
            )
        elif criterio == "ticket_medio":
            ranking = calcular_ranking_ticket_medio(
                contexto.df,
                tipo=entidade,
                top_n=limite,
                df_supervisores=contexto.df_sup,
            )
        elif criterio == "media_du":
            ranking = calcular_ranking_media_du(
                contexto.df,
                tipo=entidade,
                top_n=limite,
                du_decorridos=contexto.du_decorridos,
                df_supervisores=contexto.df_sup,
            )
        else:
            return {"erro": f"critério inválido: {criterio!r}"}
    except Exception:
        logger.exception("Chat IA: falha ao calcular ranking")
        return {"erro": "Não consegui calcular o ranking pedido."}

    if ranking.empty:
        return {"entidade": entidade, "criterio": criterio, "resultados": []}

    label = "Loja" if entidade == "loja" else "Consultor"
    linhas = []
    for _, row in ranking.iterrows():
        linha: dict = {
            "posicao": int(row.get("Posição", 0)),
            "nome": row.get(label),
        }
        if "Valor" in ranking.columns:
            linha["valor"] = round(float(row.get("Valor", 0.0)), 2)
        if "Pontos" in ranking.columns:
            linha["pontos"] = round(float(row.get("Pontos", 0.0)), 2)
        if "Atingimento %" in ranking.columns:
            linha["atingimento_pct"] = round(float(row.get("Atingimento %", 0.0)), 1)
        if "Ticket Médio" in ranking.columns:
            linha["ticket_medio"] = round(float(row.get("Ticket Médio", 0.0)), 2)
        if "Média DU" in ranking.columns:
            linha["media_du"] = round(float(row.get("Média DU", 0.0)), 2)
        linhas.append(linha)

    return {"entidade": entidade, "criterio": criterio, "resultados": linhas}


def tool_listar_sem_producao(contexto: ChatContext, entrada: dict) -> dict:
    """Lojas/consultores ativos sem nenhuma venda no período atual."""
    entidade = str(entrada.get("entidade", "loja")).strip().lower()
    if entidade not in ("loja", "consultor"):
        return {"erro": f"entidade invalida: {entidade!r} (use 'loja' ou 'consultor')"}

    try:
        if entidade == "loja":
            universo = aplicar_filtros_ui(
                aplicar_rls(carregar_universo_lojas(contexto.mes, contexto.ano))
            )
        else:
            universo = aplicar_filtros_ui(
                aplicar_rls(carregar_consultores_ativos())
            )
    except Exception:
        logger.exception("Chat IA: falha ao carregar universo de referência")
        return {"erro": "Não consegui carregar a lista de referência."}

    zerados = listar_sem_producao(
        contexto.df, universo, tipo=entidade, df_supervisores=contexto.df_sup
    )
    if zerados.empty:
        return {"entidade": entidade, "total": 0, "nomes": []}

    label = "Loja" if entidade == "loja" else "Consultor"
    nomes = zerados[label].tolist()
    return {
        "entidade": entidade,
        "total": len(nomes),
        "nomes": nomes[:_LIMITE_MAXIMO],
    }


def tool_resumo_kpis_periodo(contexto: ChatContext, _entrada: dict) -> dict:
    """Resumo dos KPIs gerais do período atual selecionado no dashboard."""
    k = contexto.kpis
    return {
        "mes": contexto.mes,
        "ano": contexto.ano,
        "total_vendas": round(float(k.get("total_vendas", 0)), 2),
        "total_pontos": round(float(k.get("total_pontos", 0)), 2),
        "meta_prata": round(float(k.get("meta_prata", 0)), 2),
        "perc_atingimento_prata": round(float(k.get("perc_ating_prata", 0)), 1),
        "perc_atingimento_ouro": round(float(k.get("perc_ating_ouro", 0)), 1),
        "projecao_fechamento": round(float(k.get("projecao", 0)), 2),
        "perc_projecao": round(float(k.get("perc_proj", 0)), 1),
        "ticket_medio": round(float(k.get("ticket_medio", 0)), 2),
        "num_lojas": int(k.get("num_lojas", 0)),
        "num_consultores": int(k.get("num_consultores", 0)),
        "du_total": int(k.get("du_total", 0)),
        "du_decorridos": int(k.get("du_decorridos", 0)),
        "valor_em_analise": round(
            float(contexto.kpis_analise.get("valor_analise", 0)), 2
        ),
        "qtd_em_analise": int(contexto.kpis_analise.get("qtd_analise", 0)),
        "valor_cancelado": round(
            float(contexto.kpis_cancel.get("valor_cancelados", 0)), 2
        ),
        "qtd_cancelada": int(contexto.kpis_cancel.get("qtd_cancelados", 0)),
        "indice_perda_pct": round(
            float(contexto.kpis_cancel.get("indice_perda", 0)), 1
        ),
    }


TOOLS_SCHEMA: list[dict] = [
    {
        "name": "comparar_entidades",
        "description": (
            "Compara o valor vendido por lojas ou consultores entre o "
            "período atual e um período anterior, indicando quem cresceu, "
            "caiu, é novo (sem histórico anterior) ou ficou descontinuado "
            "(sem produção no período atual). Use para perguntas como "
            "'quais lojas tiveram crescimento em vendas' ou 'quais "
            "consultores tiveram redução de produção'. Só suporta "
            "comparação com o mês anterior ou com o mesmo mês do ano "
            "anterior — para qualquer outro período, diga que não é "
            "suportado em vez de chamar esta tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entidade": {
                    "type": "string",
                    "enum": ["loja", "consultor"],
                    "description": "Nível de agregação da comparação.",
                },
                "periodo_comparacao": {
                    "type": "string",
                    "enum": ["mes_anterior", "mesmo_mes_ano_anterior"],
                    "description": (
                        "Período usado como base (padrão: mês anterior)."
                    ),
                },
                "direcao": {
                    "type": "string",
                    "enum": ["crescimento", "queda", "todas"],
                    "description": "Filtra o resultado por direção da variação.",
                },
                "limite": {
                    "type": "integer",
                    "description": (
                        f"Quantidade máxima de resultados (máx. {_LIMITE_MAXIMO})."
                    ),
                },
            },
            "required": ["entidade"],
        },
    },
    {
        "name": "ranking_periodo",
        "description": (
            "Retorna o ranking (top N) de lojas ou consultores no período "
            "atual, por atingimento de meta, pontos, ticket médio ou média "
            "diária de dias úteis. Use para perguntas como 'quais as "
            "melhores lojas' ou 'top consultores por pontos'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entidade": {"type": "string", "enum": ["loja", "consultor"]},
                "criterio": {
                    "type": "string",
                    "enum": ["atingimento", "pontos", "ticket_medio", "media_du"],
                    "description": (
                        "Critério de ordenação (padrão: atingimento de meta)."
                    ),
                },
                "limite": {
                    "type": "integer",
                    "description": (
                        f"Quantidade máxima de resultados (máx. {_LIMITE_MAXIMO})."
                    ),
                },
            },
            "required": ["entidade"],
        },
    },
    {
        "name": "listar_sem_producao",
        "description": (
            "Lista lojas ou consultores ativos que não tiveram nenhuma "
            "venda no período atual. Use para perguntas como 'quem não "
            "produziu nada esse mês' ou 'quais lojas estão zeradas'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entidade": {"type": "string", "enum": ["loja", "consultor"]},
            },
            "required": ["entidade"],
        },
    },
    {
        "name": "resumo_kpis_periodo",
        "description": (
            "Retorna um resumo dos KPIs gerais do período atualmente "
            "selecionado no dashboard: total vendido, % de atingimento de "
            "meta, projeção de fechamento, valores em análise/cancelados. "
            "Use para perguntas gerais como 'como estamos indo esse mês'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


def construir_dispatch(contexto: ChatContext) -> dict[str, Callable[[dict], dict]]:
    """Fecha cada tool sobre ``contexto``.

    Nenhuma tool recebe dado fora do escopo RLS do usuário logado,
    porque ``contexto`` nunca carrega frames pré-RLS.
    """
    return {
        "comparar_entidades": lambda entrada: tool_comparar_entidades(
            contexto, entrada
        ),
        "ranking_periodo": lambda entrada: tool_ranking_periodo(contexto, entrada),
        "listar_sem_producao": lambda entrada: tool_listar_sem_producao(
            contexto, entrada
        ),
        "resumo_kpis_periodo": lambda entrada: tool_resumo_kpis_periodo(
            contexto, entrada
        ),
    }
