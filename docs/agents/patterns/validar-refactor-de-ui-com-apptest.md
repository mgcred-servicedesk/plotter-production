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
- Ler `at.session_state` com `chave in at.session_state` + indexação.
  O `SafeSessionState` do `AppTest` **não** expõe `.get()`: a chamada cai
  no `__getattr__`, vira lookup da chave `"get"` e levanta
  `AttributeError` no fim do script — depois do inventário já impresso,
  o que faz o run parecer bem-sucedido no arquivo e falhar no exit code.
- Sujar o `session_state` de propósito quando houver branch de limpeza
  (ex.: `_vc_sel_ant` diferente da seleção força `_limpar_filtros_ui`),
  e assertar que as chaves sumiram.
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
- Doc complementar: [docs/agents/ui-components.md](../ui-components.md),
  [docs/agents/rls.md](../rls.md)

---

**Autor (agente):** Claude Code (`ui-dash`, via `task-orchestrator`)
**Criado em:** 2026-08-04
**Última revisão:** 2026-08-04 por Claude Code (ST-06 — `at.session_state`
sem `.get()`)
