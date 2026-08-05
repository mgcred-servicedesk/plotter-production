# Validar refactor de UI com `AppTest` diffado contra o commit anterior

> **Resumo em uma linha.** Extração/movimentação de componente Streamlit
> se valida rodando o app headless em `streamlit.testing.v1.AppTest`
> nas duas versões e diffando o inventário de widgets — não no olho.

## Contexto

Refactor mecânico de UI (mover funções de `app.py` para um módulo,
renomear, reordenar imports) não é coberto pela suíte: `tests/` cobre
KPIs e loaders, não render. `ruff` pega import órfão, não regressão
visual. E "abri no navegador e parecia igual" não distingue *igual* de
*parecido*, nem cobre os perfis que o validador não consegue logar.

Sinais de que o padrão se aplica:

- a mudança move/renomeia código de render sem intenção de alterar
  comportamento;
- o componente é condicional por perfil (RLS, `visualizar_como`) e
  validar à mão exigiria uma credencial por perfil;
- o componente escreve em `st.session_state` e outra parte do app lê.

## Decisão

Rodar o **mesmo** script de inventário contra as duas versões do app e
diffar a saída. Diff vazio é a evidência.

**Fazer:**

- Criar a versão anterior com `git worktree add <tmp> HEAD --detach`.
  O `app.py` faz `sys.path.insert(0, Path(__file__).parent)`, então
  apontar o `AppTest` para o `app.py` da worktree resolve `src.*` de
  lá — mas **um processo por versão**, senão `sys.modules` mistura as
  duas árvores.
- Injetar o login direto em `at.session_state["usuario_logado"]`
  (`usuario_logado()` só lê essa chave) e o perfil simulado em
  `visualizar_como`. Não é preciso senha nem usuário de teste no banco.
- Cobrir **um cenário por branch de perfil** do componente. Para a
  sidebar: `admin` (Visualizar Como), `gerente_comercial`
  (multiselect de Loja), `supervisor` (selectbox de Consultor).
- Emitir inventário **determinístico**: chave, label, nº de opções e
  valor dos widgets; `sha1` + tamanho do markdown (o HTML é longo e o
  hash já detecta qualquer alteração); e as chaves de `session_state`
  que o componente escreve.
- Emitir **dois** hashes por markdown: o cru e um normalizado
  (`re.sub(r"\s+", " ", txt)`). Mover um bloco de CSS/HTML muda o nível
  de aninhamento e, portanto, a indentação do literal — o hash cru
  acusa, o normalizado prova que o payload é o mesmo. Ver "Armadilha"
  abaixo. Normalizar também o `mtime` que
  `carregar_estilos_customizados()` embute (`/* CSS v<mtime> */`): a
  worktree do baseline tem `mtime` próprio e geraria ruído garantido.
- Imprimir `at.exception` — vazio é parte do critério de aceite.
- Exportar `PYTHONHASHSEED=0` nos dois lados. Um `st.json`/`st.code` de
  dict montado a partir de `set` sai com o mesmo `len` e hash diferente
  **a cada processo** — a randomização de hash de `str` muda a ordem de
  iteração. Sem o seed fixo isso vira falso positivo garantido.
- Para elemento sem `.value` (`UnknownElement` — `plotly_chart` é o
  caso), hashear `str(node.proto)`. Acessar `.value` levanta `KeyError`
  (ele procura o id do elemento no `session_state`), então envolver em
  `try` e cair para o `proto`. E **normalizar o campo `id`**:
  `id: "$$ID-<hash>-None"` deriva do `active_script_hash`, que depende
  do **caminho** do `app.py` — a worktree do baseline e a raiz divergem
  sempre, com `proto_len` idêntico.
  `re.sub(r'id: "\$\$ID-[^"]*"', 'id: "$$ID"', raw)` resolve.
- Ler `at.session_state` com `chave in at.session_state` + indexação.
  O `SafeSessionState` do `AppTest` **não** expõe `.get()`: a chamada cai
  no `__getattr__`, vira lookup da chave `"get"` e levanta
  `AttributeError` no fim do script — depois do inventário já impresso,
  o que faz o run parecer bem-sucedido no arquivo e falhar no exit code.
- Sujar o `session_state` de propósito quando houver branch de limpeza
  (ex.: `_vc_sel_ant` diferente da seleção força `_limpar_filtros_ui`),
  e assertar que as chaves sumiram.
- **Para provar *eviction* de cache, envenene o VALOR e preserve a
  CHAVE.** Assertar "a chave sumiu" depois de um clique que dispara
  `st.rerun()` não funciona: o rerun recalcula e a chave volta. Rode uma
  vez, troque o valor memoizado por uma sentinela mantendo a chave de
  invalidação real (`_kpis_cache` com `total_vendas = -424242`,
  `_df_ant_cache` virando `DataFrame({"SENTINELA": [1]})`), clique e
  rode de novo. Se a limpeza não acontecer, a chave bate e a **sentinela
  sobrevive**; se acontecer, volta o valor real. Um cenário cobre todos
  os pares `<prefixo>_cache`/`<prefixo>_chave` de uma vez.
- **Quando a chave é escrita *durante* o run, injetá-la antes do
  `at.run()` não adianta** — o valor real sobrescreve. É o caso de
  `_diag_pontuacao`, side-effect de `consolidar_dados`. Patchar a função
  no módulo (`src.dashboard.loaders.consolidar_dados = wrapper`) antes do
  run: o call site é lookup de global no mesmo módulo, então o wrapper
  pega. Para importar `src.*` da árvore certa, dar
  `sys.path.insert(0, dirname(app.py alvo))` **antes** do primeiro
  `import src.…` do script.
- Vários cenários podem dividir **um** processo (um `AppTest` novo por
  cenário, `session_state` isolado) desde que seja a mesma versão do
  app — e o `cache_data` fica quente do 2º em diante, o que corta a
  maior parte do custo de I/O.
- Preferir **travessia recursiva de `at.main.children`** aos acessores
  tipados (`at.dataframe`, `at.markdown`, …): pega elemento dentro de
  bloco aninhado (`st.columns`, `st.expander`, `st.status`), preserva a
  ordem de render e emite o caminho do bloco junto. E, ao contrário do
  que diz o item acima sobre `sac.*`, o componente **aparece** nessa
  travessia como `component_instance` — dá para contar os `sac.divider`
  de cada página. O que continua invisível é o *conteúdo* do iframe.
- Quando o componente é um **dispatch** (`if/elif` por chave), incluir
  um cenário com **chave inexistente**. Ele prova o ramo "nenhum caso
  casou" — que é justamente o que uma extração desatenta quebra (um
  `else` inventado, um `elif` virado `if`).
  Forjar a chave da navegação principal (`nav_principal`) tem um detalhe
  próprio: o `st.pills` **descarta** valor de `session_state` fora de
  `options` e cai no `default` — tanto para rótulo inexistente quanto
  para aba que a matriz esconde do perfil. Ou seja, o `tab` só assume
  rótulo visível, e o cenário serve para provar que as duas versões
  coincidem nessa coerção, não para alcançar o ramo default do despacho.
- Rodar a partir da raiz do projeto com as credenciais exportadas
  (`set -a; . .env; set +a`): o `load_dotenv()` da worktree procura a
  partir do arquivo dela e **não** acha o `.env` da raiz.

**Não fazer:**

- Não diffar o HTML renderizado inteiro — muda por ruído de ordem de
  atributo e vira falso positivo.
- Não rodar num loop / matriz grande: cada processo é cache frio e
  carrega o dashboard inteiro do Supabase (instância Nano). Três a seis
  runs cobrem os perfis; mais que isso é custo de I/O sem informação
  nova.
- Não confiar em `sac.*` no inventário: `streamlit-antd-components` roda
  em iframe e **não** aparece como elemento nativo. Prove que o branch
  executou pelo widget nativo que vem depois do `sac.divider`.

## Exemplo

```python
# scratchpad/validate_sidebar.py  — um processo por (versao, cenario)
from streamlit.testing.v1 import AppTest

at = AppTest.from_file(sys.argv[1], default_timeout=300)   # app.py alvo
at.session_state["usuario_logado"] = {
    "nome": "Teste Gerente",
    "perfil": "gerente_comercial",
    "escopo": [regiao_real],          # escopo vazio => RLS fail-closed
}
at.run()

print(f"EXCEPTIONS: {[e.value for e in at.exception]}")
for m in at.sidebar.multiselect:
    print(f"multiselect key={m.key!r} n_options={len(m.options)} value={m.value!r}")
for md in at.sidebar.markdown:
    print(f"markdown sha1={hashlib.sha1(md.value.encode()).hexdigest()[:10]}")
```

```bash
git worktree add "$SP/baseline" HEAD --detach
set -a; . .env; set +a
for cen in admin gerente supervisor; do
  for ver in baseline atual; do ... ; done
  diff "$SP/baseline_$cen.txt" "$SP/atual_$cen.txt"   # vazio = OK
done
git worktree remove "$SP/baseline" --force
```

## Armadilha: nem todo diff é seu — rode o baseline duas vezes

Quando o diff acusa **um único elemento** e o `len` é idêntico ao do
baseline, suspeite do dado antes do código: rode o mesmo inventário
**duas vezes na mesma versão** e diffe baseline × baseline. Se a linha
diverge ali também, é ruído.

Caso real: o `st.json(diag['mapa_pontos'])` do diagnóstico de pontuação
alterna entre dois hashes com `len` fixo (208) porque a RPC devolve as
categorias sem `ORDER BY` — a ordem das chaves do dict muda de processo
para processo, e `PYTHONHASHSEED=0` não alcança isso (não é hash de
`str`, é ordem de linha do Postgres). Um script isolado que extrai só
aquele elemento nas duas versões fecha a prova em ~1 min de run.

## Armadilha: o banco muda debaixo do diff — congele os loaders

O passo acima (baseline duas vezes) responde *se* o ruído existe; quando
a resposta é "muito", ele não basta. Rodando a matriz perfil × aba no
**mês corrente** enquanto o ETL carrega, dois runs do **mesmo** baseline
separados por 4 minutos divergiram em **74 linhas estruturais**:
consultores novos entrando no `selectbox` de Detalhes, `FGTS` aparecendo
nas opções de Produto, uma tabela indo de 76 para 100 linhas e
**criando um bloco de paginação** que a versão anterior não tinha. Com
esse chão, "diff vazio" é inalcançável e "diff pequeno" não prova nada.

Antídoto: **congelar a fonte**. Um proxy sobre cada `carregar_*` de
`src/dashboard/loaders.py` (mais `shared/dias_uteis.carregar_feriados`)
grava o retorno em `pickle` na primeira chamada e o reproduz nas
seguintes — inclusive em **outro processo**, que é o ponto: baseline e
versão atual passam a renderizar a partir dos mesmos bytes.

```python
def _congelar(mod, nome):
    real = getattr(mod, nome)

    def proxy(*args, **kwargs):
        # callable (on_progress) muda de endereco a cada processo:
        # nunca entra na chave.
        bruto = "|".join([nome] + [_repr_arg(a) for a in args] + ...)
        alvo = f"{VCR_DIR}/{nome}_{sha1(bruto)[:16]}.pkl"
        if os.path.exists(alvo):
            return pickle.load(open(alvo, "rb"))
        MISSES.append(bruto)
        val = real(*args, **kwargs)
        pickle.dump(val, open(alvo, "wb"))
        return val

    setattr(mod, nome, proxy)

for n in dir(L):
    if n.startswith("carregar_") and callable(getattr(L, n)):
        _congelar(L, n)
```

- Patchar **antes** do primeiro `at.run()`: o `from ... import carregar_x`
  do `app.py` (e o das abas) só resolve quando o script roda, então pega
  o proxy. Mesmo mecanismo do patch de `consolidar_dados`.
- Ordem dos runs: **grave com o baseline**, depois rode as duas versões
  em modo replay puro e diffe **esses dois**. O run de gravação sai da
  comparação.
- **Contar os misses é meia validação de graça.** Miss no replay da
  versão nova = ela pediu dado que a antiga não pedia (loader a mais,
  argumento diferente, aba deixando de ser lazy). `0 misses` dos dois
  lados é parte do critério de aceite, junto do diff vazio.
- Bônus: replay não toca a rede. A matriz inteira (39 cenários) roda em
  ~1 min por versão, o que torna viável cobrir *todas* as combinações em
  vez de amostrar — e poupa a instância Nano.

## Armadilha: o dedent do `st.markdown` é condicional

Ao mover um `st.markdown` para menos níveis de indentação, o hash cru
muda **ou não** conforme a primeira linha do literal:

```python
"""<style>            # linha 1 sem indentação => prefixo comum = 0
    .x { ... }        # dedent é no-op, a indentação sobrevive no hash
</style>"""

f"""                  # literal começa com \n => todas as linhas têm
    <style>           # prefixo comum; o dedent remove tudo e o hash
    .x { ... }        # fica idêntico entre as duas versões
"""
```

Por isso o diff de uma extração pode acusar **um** bloco e não outro,
mesmo os dois tendo sido movidos juntos. Não é regressão: confirme com o
hash normalizado e, se quiser prova byte a byte, extraia o literal antigo
com `ast` de `git show HEAD:<arquivo>` e compare com o que a função nova
emite (monkeypatch de `st.markdown` para capturar o argumento):

```python
antigo.replace(" " * 12, " " * 8) == novo   # True => só indentação mudou
```

## Quando NÃO usar

- Mudança que **deve** alterar o render (novo card, nova aba): aí o diff
  é ruído por construção. Use o inventário só da versão nova, como
  smoke test de "renderiza sem exceção nos N perfis".
- Ajuste puro de CSS/`assets/dashboard_style.css`: o `AppTest` não
  aplica estilo, o inventário sai idêntico e a validação é vazia.
- Mudança trivial de texto num ponto só.

## Referências

- Aplicado em: [src/dashboard/ui/sidebar.py](../../../src/dashboard/ui/sidebar.py)
  (extração de 8 funções de sidebar de `app.py`)
- Commit relacionado: `c7230c9` — refactor(ui): extrai componentes de
  sidebar de app.py para ui/sidebar.py (ST-01)
- Reaplicado em: [src/dashboard/ui/theme.py](../../../src/dashboard/ui/theme.py)
  (ST-02 — extração dos dois blocos de CSS/HTML inline de `main()`;
  origem da seção "Armadilha" acima)
- Reaplicado em: [src/dashboard/pages/config.py](../../../src/dashboard/pages/config.py)
  (ST-06 — extração da página de Config de `main()`; diff vazio nos dois
  cenários de perfil)
- Reaplicado em: [src/dashboard/pages/dashboard_pontuacao.py](../../../src/dashboard/pages/dashboard_pontuacao.py)
  (ST-08 — extração do expander de diagnóstico de pontuação; origem do
  patch de `consolidar_dados` e dos 3 cenários num processo só)
- Reaplicado em: [src/dashboard/tabs/produtos.py](../../../src/dashboard/tabs/produtos.py)
  (ST-09 — lazy-load dos meses de comparação movido de `main()` para a
  aba; origem do `PYTHONHASHSEED=0`, do hash de `proto` para
  `plotly_chart` e da normalização do campo `id`. A aba alvo era a
  primeira de `rotulos_visiveis` para todos os perfis, então o `default`
  do `st.pills` já cai nela — não foi preciso forjar `nav_principal`.)
- Reaplicado em:
  [src/dashboard/pages/detalhes_cards.py](../../../src/dashboard/pages/detalhes_cards.py)
  (ST-10 — extração do dispatch do drill-down de cards; 8 cenários num
  processo por versão, diff vazio. Origem da travessia recursiva de
  `at.main.children` e do cenário de chave forjada.)
- Reaplicado em: [src/dashboard/ui/sidebar.py](../../../src/dashboard/ui/sidebar.py)
  (ST-11 — extração do bloco "Período"; 4 cenários por versão, diff
  restrito à mudança de rótulo intencional. Origem do envenenamento de
  cache com chave preservada e do baseline rodado duas vezes.)
- Reaplicado em: [app.py](../../../app.py) (Fase 2/OCP — registro único
  de abas substituindo o `if/elif` de 9 ramos; 39 cenários por versão
  (5 perfis × abas visíveis + 2 chaves forjadas) com diff **byte a
  byte** vazio. Origem do congelamento dos loaders em `pickle` e da
  contagem de misses como critério de aceite.)
- Doc complementar: [docs/agents/ui-components.md](../ui-components.md),
  [docs/agents/rls.md](../rls.md)

---

**Autor (agente):** Claude Code (`ui-dash`, via `task-orchestrator`)
**Criado em:** 2026-08-04
**Última revisão:** 2026-08-05 por Claude Code (Fase 2/OCP — congelar os
loaders com VCR de `pickle` quando o ETL escreve durante a validação)
