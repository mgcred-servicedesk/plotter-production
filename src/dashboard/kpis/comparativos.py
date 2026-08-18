"""
Comparação de período por entidade (loja/consultor).

Generaliza o diff de dois períodos que hoje só existe por região
(``kpis/regioes.py::calcular_evolucao_media_du``) para qualquer
entidade — usado pelo chat de IA para responder perguntas como "quais
lojas cresceram"/"quais consultores caíram".
"""
from typing import Optional, Set

import pandas as pd

from src.dashboard.kpis.gerais import (
    excluir_lojas_backoffice,
    excluir_supervisores,
)

_ENTIDADES_VALIDAS = {"LOJA", "CONSULTOR"}


def calcular_evolucao_por_entidade(
    df_atual: pd.DataFrame,
    du_dec_atual: int,
    df_ant: Optional[pd.DataFrame],
    du_dec_ant: int,
    entidade: str = "LOJA",
    df_supervisores: Optional[pd.DataFrame] = None,
    entidades_excluir: Optional[Set[str]] = None,
    df_supervisores_ant: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compara VALOR/DU por entidade (loja ou consultor) entre dois períodos.

    Diferente de ``calcular_evolucao_media_du`` (kpis/regioes.py), que só
    agrega por REGIAO e itera as entidades do período atual: aqui a
    entidade é parametrizável e o resultado usa a UNIÃO das entidades dos
    dois períodos — necessário para que uma entidade que caiu a zero no
    período atual continue aparecendo ("quais lojas caíram" precisa dela).

    No nível CONSULTOR exclui supervisores e lojas de backoffice (Vai e
    Vem) dos dois períodos, mesma regra de
    ``kpis/rankings.py::_preparar``. Cada período usa a lista de
    supervisores VIGENTE nele: ``df_supervisores`` recorta o atual e
    ``df_supervisores_ant`` o de comparação. Omitir o segundo faz o
    primeiro valer para os dois — comportamento anterior, correto só
    enquanto ninguém muda de papel entre os períodos comparados; quem
    foi promovido no intervalo sumiria do período em que ainda era
    consultor. Os frames vêm de ``carregar_supervisores(mes, ano)``,
    que já resolve o papel por competência. No nível
    LOJA não há exclusão extra: a exclusão de Vai e Vem é do eixo
    consultor — "a loja em si segue no ranking/zerados de lojas"
    (business-rules.md), paridade com ``calcular_ranking_lojas``. Não
    confundir com a "média por loja" de ``calcular_kpis_medias``, que é
    média ENTRE lojas (aí o Vai e Vem distorceria a base e é excluído);
    aqui cada loja é uma linha própria. Chamador que não queira a linha
    do Vai e Vem passa ``entidades_excluir={"VAI E VEM"}``.

    Retorna DataFrame com colunas [<Loja|Consultor>, Mês Anterior, Mês
    Atual, Variação Abs., % Evolução, Status] — sem linha TOTAL e sem
    completar universo de entidades zeradas nos dois períodos (ruído
    para uma resposta de chat).

    ``Status`` é ``"nova"`` (sem produção no período de comparação),
    ``"descontinuada"`` (sem produção no período atual) ou ``"normal"``.
    Para "nova"/"descontinuada" ``% Evolução`` fica ``None`` — nunca
    ``0``, que pareceria "sem variação" quando na verdade não há base de
    comparação.

    Raises:
        ValueError: se ``entidade`` não for "LOJA" nem "CONSULTOR".
    """
    entidade_norm = str(entidade).strip().upper()
    if entidade_norm not in _ENTIDADES_VALIDAS:
        raise ValueError(
            f"entidade deve ser 'LOJA' ou 'CONSULTOR', recebido {entidade!r}"
        )
    entidade = entidade_norm

    label = "Loja" if entidade == "LOJA" else "Consultor"

    # Fallback explicito: sem a lista do periodo de comparacao, a atual
    # vale para os dois (comportamento anterior a 2026-08-18).
    df_sup_ant = (
        df_supervisores_ant
        if df_supervisores_ant is not None
        else df_supervisores
    )

    def _serie(
        df: Optional[pd.DataFrame],
        du_dec: int,
        df_sup: Optional[pd.DataFrame],
    ) -> pd.Series:
        if (
            df is None
            or df.empty
            or entidade not in df.columns
            or "VALOR" not in df.columns
        ):
            return pd.Series(dtype=float)
        df_v = df[df["VALOR"] > 0]
        if entidade == "CONSULTOR":
            df_v = excluir_lojas_backoffice(
                excluir_supervisores(df_v, df_sup)
            )
        if df_v.empty:
            return pd.Series(dtype=float)
        # Mesmo max(du, 1) de calcular_evolucao_media_du /
        # calcular_ranking_media_du: evita divisão por zero. Com du=0 a
        # série vira o total bruto do período — sem exceção, mas se só
        # um dos lados tiver du=0 a comparação fica distorcida (cabe ao
        # chamador não passar du=0 para um período com produção).
        du_safe = max(du_dec, 1)
        return df_v.groupby(entidade)["VALOR"].sum() / du_safe

    serie_atual = _serie(df_atual, du_dec_atual, df_supervisores)
    serie_ant = _serie(df_ant, du_dec_ant, df_sup_ant)

    todas_entidades = sorted(set(serie_atual.index) | set(serie_ant.index))
    if entidades_excluir:
        # Mesma normalização de excluir_lojas_backoffice (strip+upper):
        # a base não é uniformemente maiúscula nem sem espaços.
        excluir_norm = {str(e).strip().upper() for e in entidades_excluir}
        todas_entidades = [
            e
            for e in todas_entidades
            if str(e).strip().upper() not in excluir_norm
        ]

    if not todas_entidades:
        return pd.DataFrame()

    linhas = []
    for nome in todas_entidades:
        tinha_atual = nome in serie_atual.index
        tinha_ant = nome in serie_ant.index
        valor_atual = float(serie_atual.get(nome, 0.0))
        valor_ant = float(serie_ant.get(nome, 0.0))

        if tinha_atual and not tinha_ant:
            status, pct = "nova", None
        elif tinha_ant and not tinha_atual:
            status, pct = "descontinuada", None
        else:
            status = "normal"
            # valor_ant > 0 por construção (a série soma só VALOR > 0);
            # a guarda protege caso esse filtro mude no futuro.
            pct = (
                (valor_atual - valor_ant) / valor_ant * 100
                if valor_ant > 0
                else None
            )

        linhas.append(
            {
                label: nome,
                "Mês Anterior": valor_ant,
                "Mês Atual": valor_atual,
                "Variação Abs.": valor_atual - valor_ant,
                "% Evolução": pct,
                "Status": status,
            }
        )

    return pd.DataFrame(linhas)
