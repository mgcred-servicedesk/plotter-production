# 2026-07-31 — Upgrade Streamlit 1.58.0 → 1.60.0 (fase 1)

**Agente:** Claude Code
**Tipo:** manutenção / dependências
**Arquivos tocados:** `requirements.txt`, `ruff.toml` (novo),
`.streamlit/config.toml`, `docs/agents/conventions.md`
**Commit(s):** (não commitado)

## Objetivo

Subir o Streamlit da 1.58.0 para a 1.60.0 (última, lançada 21/07/2026),
pulando a 1.59.0 (06/07/2026). Fase 1 de um plano de 3: só o Streamlit,
sem mexer em mais nenhuma dependência, para isolar a causa de qualquer
regressão.

## O que foi feito

- `requirements.txt`: `streamlit==1.58.0` → `streamlit==1.60.0`.
- `.venv` atualizado. **Nenhuma outra dependência mudou** — confirmado
  antes por `pip install --dry-run` (o relatório listou um único
  pacote a instalar) e depois por `pip check` (sem conflitos).

## Decisões não óbvias

- **Nada a migrar nas remoções da 1.59.** Saíram `st.bokeh_chart` e
  `SnowparkConnection`; nenhum dos dois aparece no código.
- **`pyarrow` e `websockets` ficam onde estão.** A 1.60 pina
  `pyarrow<25` e `websockets<17`, e traz um fix explícito de
  "PyArrow 25 threading crashes". As versões novas desses dois
  (25.0.0 e 17.0.1) estão **bloqueadas pelo Streamlit**, não por nós —
  não tratar como dívida.
- **`client.disableDataExport` (1.60) NÃO afeta as exportações do
  projeto.** Ele desliga só o botão CSV nativo da toolbar do
  `st.dataframe`/`st.data_editor` e o copiar-para-clipboard. As
  exportações reais são `st.download_button` (`botao_exportar_csv` em
  `components/tables.py` + o export de `gestao_consultores.py`) e
  seguem intactas. O botão da toolbar **não fura RLS** — baixa o
  DataFrame já filtrado antes do render. Ligar o config é decisão de
  governança (padronizar no nosso CSV pt-BR com BOM), não de segurança,
  e ficou para a fase 3.
- **Os três acoplamentos com DOM interno foram verificados no bundle
  da 1.60, não presumidos:**
  - `stBaseButton-pills` / `-pillsActive` continuam existindo — são
    montados em runtime como `` `stBaseButton-${kind}` ``, por isso não
    aparecem em busca literal no bundle. Verificar o prefixo, não a
    string completa.
  - O sandbox dos iframes de componente ainda inclui
    `allow-same-origin` **e** `allow-scripts` — é disso que dependem os
    três `st.iframe` que fazem `window.parent.document` (`theme.py`,
    `kpi_cards_reforma.py`, `kpi_cards_pontuacao.py`).
  - A breaking change "reject spoofed host messages from child frames
    and scripts" mira o protocolo `postMessage` host↔app (CWE-346), que
    é canal diferente do acesso direto ao DOM same-origin que usamos.

## Fase 2 — demais dependências (executada em seguida)

Feita em dois passos, para poder atribuir regressão:

- **Passo A:** pandas `3.0.2 → 3.0.5`, plotly `6.7.0 → 6.9.0`,
  pytest `9.0.3 → 9.1.1`, ruff `0.15.7 → 0.16.1`.
- **Passo B (isolado):** numpy `2.4.6 → 2.5.1` — separado por ser o
  único capaz de mexer em resultado numérico.

Ambos: 372 passed, `pip check` limpo, boot HTTP 200. A suíte foi
rodada também com `-W error::DeprecationWarning` (deprecation vira
falha) e passou igual — nenhum caminho nosso encosta em API depreciada
do pandas 3.0.5 / numpy 2.5.1.

`requirements.txt` atualizado. Validação manual do usuário: os botões
‹ › dos carrosséis MIX seguem funcionando na 1.60 — confirma que o
acesso `window.parent.document` a partir do `st.iframe` sobreviveu.

### Decisão: `ruff.toml` fixando o `select`

O ruff `0.16` **ampliou o conjunto default de regras**. Sem nenhuma
alteração de código, `ruff check src/ app.py` — o gate documentado no
`CLAUDE.md` — saiu de "All checks passed" para **635 erros**. O projeto
não tinha config de ruff, então herdava o default da ferramenta.

Diagnóstico (não presumido): rodando o próprio 0.16.1 restrito ao
escopo antigo, `ruff check --select E4,E7,E9,F src/ app.py` volta a
"All checks passed" — ou seja, **zero problema real**. Distribuição dos
635: UP006 266, UP045 204 (juntas 74%, só modernização de anotação de
tipo), C408 43, UP035 39, I001 16, BLE001 11, DTZ005 9, resto ~47.

Criado `ruff.toml` com `[lint] select = ["E4","E7","E9","F"]`.
Justificativa: **desacopla o gate de lint da versão da ferramenta**.
Sem `select` explícito, subir o ruff é mudança de escopo disfarçada —
o comando passa a significar outra coisa. Todo o resto (line-length,
target-version, excludes) ficou no default de propósito: o objetivo é
congelar o comportamento que o projeto já tinha, não introduzir
convenção nova.

Efeito colateral bom: com `select` explícito, o piso
`ruff>=0.15.0` do `requirements-dev.txt` deixa de ser um problema para
quem monta o ambiente do zero — não foi preciso pinar a versão.

Alternativas descartadas: (a) voltar para o ruff 0.15.7 — só adia, e o
piso `>=0.15.0` continuaria entregando 0.16 em instalação nova, exigindo
pin; (b) adotar as 635 — os 470 de UP006/UP045 são auto-fixáveis, mas
BLE001 (`except Exception` genérico) e DTZ005 (`datetime.now()` sem tz,
potencialmente relevante num dashboard com corte por período) exigem
julgamento e mereceriam tarefa própria.

## Fase 3 — adoção das novidades

Levantamento item a item. **Só um item entrou**; os demais foram
adiados por motivo concreto, registrado abaixo.

### Adotado: `client.disableDataExport = true`

`.streamlit/config.toml`, seção `[client]`. Decisão do usuário.
Desliga o botão CSV nativo da toolbar de `st.dataframe`/`st.data_editor`
e o copiar-para-clipboard. **Não afeta** os exports do projeto, que são
`st.download_button`.

Racional: não é segurança — o botão da toolbar baixa o DataFrame já
filtrado pelo RLS antes do render, o mesmo dado da tela. É
padronização: toda tabela ganhava download implícito que ninguém
decidiu oferecer, no formato default do Streamlit (vírgula, sem BOM),
que corrompe acento no Excel pt-BR; os exports deliberados usam
`sep=";"`, `decimal=","` e UTF-8 com BOM. Custo aceito: o clipboard das
tabelas cai junto e a opção é app-wide.

### Adiado: `st.skeleton` (1.59) — colide com o tema

O `st.skeleton` renderiza com o **tema nativo**, que o `config.toml`
fixa em `base="light"` (com o aviso de não criar `[theme.dark]`, bug de
2026-07-07). O nosso `ui/skeleton.py` é construído sobre tokens
`--mg-*` e acompanha o dark customizado. Adotar o nativo colocaria um
elemento sempre claro na tela em modo dark — ou seja, é mexer em tema,
que o usuário separou para a conversa de refatoração.

Soma-se que o nosso skeleton é um **wireframe do layout** (status + 3
hero + 4 contexto + 5 produtos + chart + barra de tabs) e o
`st.skeleton` é um retângulo genérico (`height`/`width`): reproduzir o
wireframe exigiria ~13 chamadas dentro de colunas aninhadas — mais
código, menos fiel. Reavaliar junto com a migração de tema.

### Adiado: `persist_state` (1.59) — é refatoração, não parâmetro

`persist_state="session"` **exige `key`**, e nas abas só **7 de 38**
widgets têm `key`. Adotar significa nomear 31 widgets e fazer isso
conviver com o mecanismo de presets via `session_state` já existente em
`tabs/gestao_consultores.py`. Além do custo, muda comportamento para o
usuário final (hoje o filtro reseta ao trocar de aba) — decisão de UX.
Tarefa própria.

### Descartados por ganho nulo

- `st.tabs(height=…)` — o único `st.tabs` do projeto está na tela admin
  de usuários. Obs.: na 1.60 o `st.tabs` também ganhou `default`, `key`
  e `on_change`; vale reavaliar o custo de render dele algum dia.
- `st.columns(gap=<int px>)` — as 3 chamadas com `"small"`/`"large"`
  funcionam; pixel não resolve problema existente.
- `st.mermaid_chart`, `ButtonColumn`, `MarkdownColumn` — sem uso
  previsto hoje.
- `server.maxWidgetStateSize` (default 25 MB) e
  `server.xsrfCookieSameSite` (default `lax`) — confirmado que existem
  na 1.60; defaults sensatos. Mexer sem problema concreto seria config
  especulativa.

## Pendências / follow-ups

- [x] Botões ‹ › dos carrosséis MIX — validados pelo usuário na 1.60.
- [ ] **Validação manual pós-login ainda pendente:** CSS de tema
      injetado dentro dos iframes do `sac` (divisores e sub-abas de
      rankings/analíticos **no modo dark** — é onde a falha apareceria);
      pills da nav principal e cards recalibrados.
- [ ] Modernização de anotações de tipo (UP006/UP045, ~470
      ocorrências, auto-fixáveis) + BLE001/DTZ005 (exigem julgamento) —
      tarefa própria, se e quando for decidido alargar o `select`.
- [ ] `st.metric` com delta zero passou a renderizar cinza neutro em vez
      de colorido — mudança cosmética que atinge os ~20 `st.metric` de
      `analiticos.py` / `detalhes.py`. Confirmar se é aceitável.
- [ ] Fase 2 (não executada): pandas 3.0.5, plotly 6.9.0, ruff 0.16.1,
      pytest 9.1.1 e, separado, numpy 2.5.1.
- [ ] `streamlit-antd-components` continua em 0.3.2, última release em
      **janeiro/2024**. Não há versão nova — a saída real é migrar as
      sub-navegações para componentes nativos.
- [ ] Pacotes instalados e não importados por nenhum arquivo
      (`matplotlib`, `openpyxl`, `pyiceberg`, `strictyaml`, `flake8`,
      `autopep8`, `isort`) — resíduo do pipeline de relatórios removido.
      Nada foi desinstalado; aguarda autorização.

## Verificação

- `pip check` — sem conflitos; `streamlit.__version__ == "1.60.0"`.
- `.venv/bin/ruff check src/ app.py` — All checks passed.
- `.venv/bin/python -m pytest tests/` — 372 passed.
- Boot headless — `/` e `/_stcore/health` em HTTP 200, log sem exceção.
- API usada pelo projeto conferida por `inspect.signature`
  (`st.iframe`, `st.pills`, `st.tabs`, `st.columns`, …) e os 9 ícones
  Material da nav revalidados contra `ALL_MATERIAL_ICONS`.

## Referências

- Release notes 1.59.0 / 1.60.0:
  <https://docs.streamlit.io/develop/quick-reference/release-notes/2026>
- Anúncio 1.60: <https://discuss.streamlit.io/t/version-1-60/122051>
