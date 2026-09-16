# Medir CSS do Streamlit num repro isolado, não no app logado

> **Resumo em uma linha.** Pergunta de *geometria* (altura, alinhamento,
> vão) se responde medindo o DOM com Playwright num app Streamlit mínimo
> que reproduz só o caso — não abrindo o dashboard e olhando.

## Contexto

Complementa
[validar-refactor-de-ui-com-apptest.md](validar-refactor-de-ui-com-apptest.md).
Os dois validam UI, mas respondem a perguntas diferentes, e usar o
errado custa tempo:

| Pergunta | Ferramenta |
|---|---|
| "os widgets/`session_state` continuam os mesmos?" | `AppTest` |
| "este card tem a mesma altura daquele?" | Playwright + repro |

`AppTest` roda headless **sem navegador**: não há layout calculado, logo
nenhuma altura, largura ou `getComputedStyle`. Para CSS ele é cego.

E abrir o app real esbarra em duas coisas: a senha de produção (que não
deve entrar em transcrição nem em script) e o ruído — tema, dados,
sidebar e as outras seções entram no meio da medição.

Sinais de que o padrão se aplica:

- a mudança é uma regra de CSS, não de conteúdo;
- o sintoma é geométrico ("desalinhado", "mais alto", "sobra espaço");
- a suíte passa e o `ruff` passa, e ainda assim está errado na tela.

## Decisão

Escrever um `repro.py` de ~20 linhas que carregue **a folha de estilo do
projeto** e **a constante de CSS real do módulo** (importada, não
copiada), renderize o caso lado a lado com e sem a regra, e medir o DOM.

**Fazer:**

- **Importar** o CSS do módulo de produção
  (`from src.dashboard.pages.campanhas import _CSS_CARDS`). Copiar e
  colar o CSS no repro valida uma cópia, não o que vai para o ar.
- Rodar numa **porta própria** (8502), com `PYTHONPATH=$PWD` — o
  `streamlit run` não herda o path do shell e `src` não resolve.
- Renderizar o caso **duas vezes**: fora e dentro do container que a
  regra escopa. O "fora" é a prova de que nada vazou para o resto do app.
- **Medir, não olhar:** `getBoundingClientRect().height` de cada
  elemento e comparar os números. "Parece igual" não distingue 93 de 96.
- Testar **variantes de seletor no mesmo run** quando a primeira não
  pegar — três candidatos numa página custam um screenshot.
- Terminar com um **teste que trave o escopo** do seletor na suíte, já
  que o repro é descartável e não roda no CI.

## Exemplo

```python
# repro.py — porta 8502, PYTHONPATH=$PWD
import streamlit as st
from src.dashboard.pages.campanhas import _CSS_CARDS, _CHAVE_CARDS

st.markdown("<style>" + open("assets/dashboard_style.css").read()
            + "</style>", unsafe_allow_html=True)

def linha():
    c1, c2 = st.columns(2)
    c1.metric("Sem delta", "R$ 1")
    c2.metric("Com delta", "R$ 2", delta="+1")

st.write("#### fora do container (não pode mudar)")
linha()
st.write("#### dentro")
st.markdown(_CSS_CARDS, unsafe_allow_html=True)
with st.container(key=_CHAVE_CARDS):
    linha()
```

```python
# mede as alturas em vez de olhar o screenshot
alturas = pg.eval_on_selector_all(
    '[data-testid="stMetric"]',
    "els => els.map(e => Math.round(e.getBoundingClientRect().height))")
# fora: [93, 118]  dentro: [118, 118]
```

**Armadilha que este padrão já pagou:** `height: 100%` num item de flex
cujo pai tem altura automática é referência circular — resolve como
`auto` e o item **para** de esticar. A primeira tentativa pôs a regra no
`stColumn`, que já esticava sozinho (`stHorizontalBlock` é flex com
`align-items: stretch`), e a regra escrita para consertar foi a que
quebrou. Sem medir, isso passaria por "a CSS não pegou".

## Quando NÃO usar

- Mudança de **conteúdo** (rótulo, coluna, valor): a suíte cobre, e
  `AppTest` cobre inventário de widget.
- Refactor mecânico de render: o padrão do `AppTest` é mais barato e
  cobre perfis sem navegador.
- Validar **dado**: RLS, KPI e agregação se testam em `tests/`, nunca
  por pixel.

## Referências

- [validar-refactor-de-ui-com-apptest.md](validar-refactor-de-ui-com-apptest.md)
  — o complemento; inclusive mostra como injetar login em
  `at.session_state["usuario_logado"]` sem senha.
- `TestCssDosCards` em `tests/test_kpis_campanha.py` — o teste que trava
  o escopo depois que o repro é descartado.
- [progress/2026-09-16b](../progress/2026-09-16b-campanhas-terceira-secao.md)

> **Dependência:** `playwright` está no `.venv` mas **não** em
> `requirements.txt`, e o binário do Chromium (~117 MB) é baixado à
> parte com `.venv/bin/python -m playwright install chromium`. Quem
> clonar do zero não tem nenhum dos dois. Decidir se entra nos
> requirements (como extra de desenvolvimento) é item em aberto.

---

**Autor (agente):** Claude Code
**Criado em:** 2026-09-16
