"""
Catraca estrutural: todo wrapper ``@st.cache_data`` de
``src/dashboard/loaders.py`` que DELEGA por uma linha
(``return _fetch_algo(...)`` / ``return _executar_algo(...)``) precisa
aceitar ``_cache_version``.

## Por que isso existe

Incidente de 09/2026: o ranking de consultores por atingimento veio
0,0% para TODOS, e o Dashboard de Pontuação da consultora PAULA
VIRGINIA GUIMARAES GONCALVES mostrou "% META PRATA 0.0%" com o aviso
"Loja HELP PENHA sem meta individual (escopo CONSULTOR)" — mesmo a
loja tendo meta individual de R$ 360.000 cadastrada (chamar o código
puro fora do Streamlit dava o número certo: 205.761 / 360.000 = 57,2%).

Causa raiz: ``_metas_produto_consultor_atual``/``_historico`` eram
wrappers de UMA linha decorados com ``@st.cache_data`` que só delegam
para ``_fetch_metas_produto_consultor``. ``st.cache_data`` versiona a
função DECORADA (assinatura + código-fonte dela), não as funções que
ela chama por dentro. Quando ``_fetch_metas_produto_consultor`` ganhou
colunas novas (``META_PRATA``, ``META_OURO``, aceleradores), a chave de
cache do wrapper não mudou — sessões já abertas continuaram servindo o
DataFrame do formato ANTIGO (7 colunas, sem ``META_PRATA``) por até 6h
(24h no histórico). Todo consumidor lia "sem meta" e caía no caminho de
meta 0. A suíte de testes (que chama o código puro, sem
``st.cache_data`` no meio) nunca teria pego isso — daí o teste-catraca
aqui: ele audita a ASSINATURA dos wrappers, não o resultado.

A correção pontual (`_metas_produto_consultor_atual`/`_historico` com
`_cache_version: int = 1`) já foi aplicada em ``src/`` fora desta
tarefa — mesmo padrão que ``_consolidar_atual``/``_historico`` já
usavam (``_cache_version=4``).

## O tamanho real do problema — e por que a maioria fica de fora

Auditoria via AST (2026-09-11): dos wrappers cacheados que delegam por
uma linha, **25** ainda NÃO têm ``_cache_version`` — a mesma bomba-relógio
esperando o próximo `_fetch_*` mudar de formato. Corrigi-los AGORA
invalidaria o cache de produção para todo mundo de uma vez (o mesmo
efeito colateral, só que espalhado por 25 fontes de dado ao mesmo
tempo) — fora do escopo desta tarefa, que é fechar a lacuna de
cobertura, não pagar a dívida. Por isso ``ALLOWLIST_DIVIDA_CONHECIDA``
existe: um wrapper nela é dívida DOCUMENTADA e aceita; um wrapper NOVO
fora dela quebra o teste. A lista só pode ENCOLHER — quando alguém
adiciona ``_cache_version`` de verdade a um desses (pagando a dívida),
``test_allowlist_fica_honesta_quando_a_divida_e_paga`` força a remoção
do nome da lista, para ela nunca virar papel.
"""
import ast
import inspect
import pathlib

import pytest

from src.dashboard import loaders

# Divida PRE-EXISTENTE (auditoria de 2026-09-11, ver docstring do
# módulo): wrappers @st.cache_data de uma linha que delegam para um
# `_fetch_*`/executor sem `_cache_version`. NAO adicionar nomes aqui
# para "abafar" um wrapper novo que devia ter sido versionado desde o
# início — isso é o próprio bug do incidente se repetindo. Só encolhe.
ALLOWLIST_DIVIDA_CONHECIDA = frozenset({
    "_contratos_pagos_atual", "_contratos_pagos_historico",
    "_contratos_em_analise_atual", "_contratos_em_analise_historico",
    "_digitacao_diaria_atual", "_digitacao_diaria_historico",
    "_digitacao_detalhe_atual", "_digitacao_detalhe_historico",
    "_contratos_cancelados_atual", "_contratos_cancelados_historico",
    "_pontuacao_atual", "_pontuacao_historico",
    "_metas_atual", "_metas_historico",
    "_metas_produto_atual", "_metas_produto_historico",
    "_metas_consultor_atual", "_metas_consultor_historico",
    "_vinculos_consultores_atual", "_vinculos_consultores_historico",
    "_pagamentos_online_cache",
    "_cobranca_consignavel_atual", "_cobranca_consignavel_historico",
    "_faixa_acelerador_atual", "_faixa_acelerador_historico",
})


def _e_decorator_cache_data(deco: ast.expr) -> bool:
    alvo = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(alvo, ast.Attribute):
        return alvo.attr == "cache_data"
    if isinstance(alvo, ast.Name):
        return alvo.id == "cache_data"
    return False


def _e_delegacao_de_uma_linha(corpo: list[ast.stmt]) -> bool:
    """``corpo`` (já sem docstring) é exatamente ``return outra_fn(...)``.

    Só essa forma tem o problema: qualquer lógica própria no wrapper
    (filtro, merge, cast) já faria o código-fonte da própria função
    mudar quando o formato mudasse — o que ``st.cache_data`` PEGA.
    """
    return (
        len(corpo) == 1
        and isinstance(corpo[0], ast.Return)
        and isinstance(corpo[0].value, ast.Call)
        and isinstance(corpo[0].value.func, ast.Name)
    )


def _wrappers_cache_data_que_delegam() -> dict[str, bool]:
    """Nome -> True se a assinatura tem ``_cache_version``, para toda
    função de ``loaders.py`` decorada com ``@st.cache_data`` cujo corpo
    é uma delegação de uma linha (ver ``_e_delegacao_de_uma_linha``).

    AST sobre o ARQUIVO fonte, não ``inspect.signature`` sobre o
    objeto: o decorator do Streamlit não garante preservar a assinatura
    original via ``functools.wraps``, então o texto-fonte é a fonte
    estável de verdade — e é exatamente o que ``st.cache_data`` olha
    para montar a chave de cache.
    """
    caminho = inspect.getsourcefile(loaders)
    assert caminho is not None
    arvore = ast.parse(pathlib.Path(caminho).read_text(encoding="utf-8"))

    resultado: dict[str, bool] = {}
    for node in ast.iter_child_nodes(arvore):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any(_e_decorator_cache_data(d) for d in node.decorator_list):
            continue

        corpo = node.body
        if (
            corpo
            and isinstance(corpo[0], ast.Expr)
            and isinstance(corpo[0].value, ast.Constant)
        ):
            corpo = corpo[1:]  # pula a docstring

        if not _e_delegacao_de_uma_linha(corpo):
            continue

        nomes_arg = {a.arg for a in node.args.args} | {
            a.arg for a in node.args.kwonlyargs
        }
        resultado[node.name] = "_cache_version" in nomes_arg

    return resultado


@pytest.mark.unit
class TestCatracaCacheVersionEmWrappersQueDelegam:
    """Ver docstring do módulo para o incidente que motiva este teste."""

    def test_wrapper_fora_da_allowlist_precisa_de_cache_version(self):
        wrappers = _wrappers_cache_data_que_delegam()
        sem_versao = {nome for nome, tem in wrappers.items() if not tem}
        novos = sem_versao - ALLOWLIST_DIVIDA_CONHECIDA
        assert not novos, (
            f"Wrapper(s) {sorted(novos)} decorado(s) com @st.cache_data "
            "delegam por uma linha para um _fetch_*/executor SEM "
            "`_cache_version` — mesmo bug do incidente de 09/2026 (ranking "
            "de consultores 0% para todo mundo; HELP PENHA com meta "
            "individual real de 360.000 mas o app lendo formato antigo "
            "do cache por até 6h). Adicione `_cache_version: int = 1` à "
            "assinatura (ver `_metas_produto_consultor_atual` como "
            "referência) e passe-o explicitamente no dispatcher "
            "`carregar_*`. Se for dívida conhecida e deliberada (não "
            "corrigir agora, fora do escopo da tarefa atual), adicione o "
            "nome à ALLOWLIST_DIVIDA_CONHECIDA — mas isso NÃO resolve o "
            "risco de produção, só documenta."
        )

    def test_allowlist_fica_honesta_quando_a_divida_e_paga(self):
        """Nome na allowlist que já tem `_cache_version` (ou deixou de
        delegar por uma linha) precisa SAIR da lista — senão ela vira
        papel e ninguém percebe quando a dívida real encolheu."""
        wrappers = _wrappers_cache_data_que_delegam()
        sem_versao = {nome for nome, tem in wrappers.items() if not tem}
        resolvidos = ALLOWLIST_DIVIDA_CONHECIDA - sem_versao
        assert not resolvidos, (
            f"{sorted(resolvidos)} não está mais na situação de risco "
            "(já tem `_cache_version` ou não delega mais por uma linha) "
            "mas ainda consta em ALLOWLIST_DIVIDA_CONHECIDA — remova o(s) "
            "nome(s) da lista."
        )

    def test_wrappers_ja_protegidos_nao_regridem(self):
        """Os 4 wrappers corrigidos no incidente de 09/2026 continuam
        com `_cache_version` — trava contra alguém remover o parâmetro
        num refactor futuro sem perceber o motivo dele existir."""
        wrappers = _wrappers_cache_data_que_delegam()
        protegidos = {
            "_metas_produto_consultor_atual",
            "_metas_produto_consultor_historico",
            "_consolidar_atual",
            "_consolidar_historico",
        }
        for nome in protegidos:
            assert wrappers.get(nome) is True, (
                f"{nome} deveria ter `_cache_version` na assinatura"
            )

    def test_dispatcher_de_metas_consultor_passa_a_versao_explicitamente(self):
        """`_cache_version` só protege se o CHAMADOR passar o valor —
        um default sozinho na assinatura do wrapper não muda a chave do
        cache dele até alguém de fato invocar com outro valor. O
        dispatcher (`carregar_metas_produto_consultor`) precisa passar
        `_cache_version=` explicitamente nas duas chamadas."""
        caminho = inspect.getsourcefile(loaders)
        arvore = ast.parse(pathlib.Path(caminho).read_text(encoding="utf-8"))

        dispatcher = next(
            node
            for node in ast.walk(arvore)
            if isinstance(node, ast.FunctionDef)
            and node.name == "carregar_metas_produto_consultor"
        )
        chamadas_versionadas = [
            call
            for call in ast.walk(dispatcher)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in (
                "_metas_produto_consultor_atual",
                "_metas_produto_consultor_historico",
            )
            and any(kw.arg == "_cache_version" for kw in call.keywords)
        ]
        assert len(chamadas_versionadas) == 2
