"""
Chaves de comparacao de texto — duas, porque sao duas responsabilidades.

Ate 09/2026 existia so uma implementacao (`strip + upper`), copiada em
cinco lugares do dashboard. Como ela servia aos dois usos ao mesmo
tempo, a diferenca entre eles nunca precisou ser nomeada — e a falta do
nome escondeu um bug: o merge de producao por nome nao casava
``JOÃO DA SILVA`` com ``JOAO DA SILVA``, e a pessoa aparecia com
producao zerada no acelerador.

A correcao obvia (dobrar acento na implementacao unica) quebraria a aba
de Produtos, e e por isso que sao duas funcoes:

``normalizar_nome`` — compara PESSOAS
    Dobra acento. Os dois lados da comparacao sao dados vindos do
    banco, digitados por gente diferente em cadastros diferentes: o
    mesmo consultor aparece com e sem acento conforme a origem. Aqui,
    acento e ruido.

``normalizar_rotulo`` — compara ROTULO DE DADO contra constante
    **Nao** dobra acento. De um lado vem o dado, do outro uma constante
    escrita no codigo (``"CARTÃO BENEFICIO"``, ``"Venda Pré-Adesão"``,
    ``"SEGURO PRESTAMISTA"``). Dobrar acento so em um dos lados faz a
    comparacao falhar em silencio — some da contagem, nao levanta erro.
    Se um dia os dois lados passarem por aqui, dobrar vira seguro; ate
    la, nao.

Mora em ``shared/`` porque ``kpis/`` (dados) e ``tabs/`` (UI) precisam
das duas, e ``shared`` e a unica camada que ambas podem importar sem
inverter a dependencia — era essa a objecao registrada no antigo
``_norm_texto``, que preferia replicar o ``_norm`` de ``tabs/`` a
importar da camada de UI.
"""

import pandas as pd


def normalizar_rotulo(serie: pd.Series) -> pd.Series:
    """Chave de comparacao de rotulo: ``str + strip + upper``.

    Para casar valor do banco com constante escrita no codigo. **Nao**
    dobra acento de proposito — ver o topo do modulo.
    """
    return serie.astype(str).str.strip().str.upper()


def normalizar_nome(serie: pd.Series) -> pd.Series:
    """Chave de comparacao de nome de pessoa: rotulo + acento dobrado.

    ``JOÃO DA SILVA``, ``joao da silva`` e ``  João Da Silva  `` viram
    a mesma chave. Usada em todo merge/`isin` que cruza nome de
    consultor ou supervisor entre fontes diferentes (cadastro,
    reconquista, cobranca consignavel, supervisor_vigencia).

    Implementacao: a decomposicao NFKD separa a letra do diacritico
    (``Ç`` -> ``C`` + cedilha), e o ``replace`` apaga o bloco Unicode
    dos diacriticos combinantes. Nao se usa o ida-e-volta por ASCII
    (``encode``/``decode``) porque ele quebra em serie sem nenhuma
    string — uma coluna toda nula chega como ``float`` e o acessor
    ``.str`` levanta ``AttributeError``. Com ``replace``, o dtype
    continua string do inicio ao fim.

    Nulo permanece nulo — nao vira string vazia nem o literal "NONE",
    para que nome ausente nunca case com nome ausente do outro lado.
    """
    return (
        normalizar_rotulo(serie)
        .str.normalize("NFKD")
        # String NAO-crua de proposito: o Python resolve os escapes e o
        # regex chega ao motor com os caracteres combinantes literais.
        # Cru ("[\\u0300-\\u036f]") estoura com "invalid escape
        # sequence" — as colunas de texto sao Arrow-backed e vao para o
        # RE2 do pyarrow, que nao entende \\u.
        .str.replace("[\u0300-\u036f]", "", regex=True)
    )
