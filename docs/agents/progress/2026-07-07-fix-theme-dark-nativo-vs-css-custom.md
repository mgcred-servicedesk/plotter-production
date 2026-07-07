# 2026-07-07 — Fix: [theme.dark] nativo conflitava com o dark mode do CSS custom

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `.streamlit/config.toml`

## Objetivo

Com o tema do SO/navegador em dark, botões e componentes nativos do
Streamlit escureciam sozinhos enquanto o restante do dashboard
(controlado pelo CSS customizado `--mg-*`) permanecia no light —
visual quebrado (botões pretos sobre fundo claro, pill de navegação
preta, ícones da sidebar pretos).

## O que foi feito

- Removida a seção `[theme.dark]` de `.streamlit/config.toml`
  (adicionada no bloco 1 de `2026-07-07-ui-ux-streamlit-158-bloco1-2.md`
  sob a premissa de que ficaria "registrada para futura migração").
- Comentário do config atualizado com aviso explícito: **não** definir
  `[theme.dark]` enquanto o dark mode for controlado pelo CSS custom.
- Paleta light da marca em `[theme]` (bloco 1) foi **mantida** — o
  problema era exclusivamente a variante dark.

## Decisões não óbvias

- **`[theme.dark]` não é inerte no Streamlit ≥1.46** — a premissa do
  bloco 1 estava errada. Verificado no bundle do frontend
  (`static/js/index.*.js`): quando existe variante dark configurada, o
  tema ativo default é resolvido por `window.matchMedia('(prefers-color-scheme: dark)')`
  e há listener de `change` — ou seja, a mera presença da seção ativa
  o tema dual nativo seguindo o SO. Widgets nativos (emotion/CSS-in-JS
  com cores concretas) e componentes custom (que recebem o tema via
  protocolo de components) escurecem sem que o CSS `--mg-*` acompanhe,
  pois este resolve o tema por `st.session_state` (default light).
- **Remover a seção em vez de sincronizar os dois sistemas** — a
  sincronização (tema nativo dual + CSS custom seguindo o mesmo
  estado) é a "migração futura" já prevista; fora de escopo para um
  bugfix. A paleta dark nativa continua preservada em
  `src/dashboard/ui/theme.py` (`_NATIVE_THEME["dark"]`).
- **`_NATIVE_THEME` em `theme.py` está sem uso** (nenhuma referência
  fora da definição). Mantido como registro da paleta para a migração
  futura; remoção exigiria decisão explícita do usuário.

## Pendências / follow-ups

- [ ] Validar visualmente com SO em dark: widgets nativos devem
      permanecer light até o usuário trocar o toggle custom.
- [ ] Migração ao tema nativo dual — requisito central: **colapsar as
      3 fontes de estado de tema em 1** (hoje: tema nativo do config,
      `st.session_state["theme"]`/`--mg-*`, e
      `localStorage.mgcred_theme` + JS de detecção). Desenho validado
      contra a 1.58:
      1. Tema nativo (`[theme]`/`[theme.dark]` + menu nativo
         reexibido) vira a única fonte de verdade;
      2. `--mg-*` e `chart_theme()` passam a derivar de
         `st.context.theme.type` (existe na 1.58); remover o toggle
         custom, o `localStorage.mgcred_theme` e a detecção
         JS/query-param `_theme` — mantê-los em paralelo recria a
         dessincronizacao;
      3. Tratar a janela de lag do `st.context.theme` (issue
         streamlit#11920: valor pode vir errado no 1o load e logo
         apos troca no menu, sem rerun automatico) — aceitar flash de
         1 render ou shim JS que força rerun quando DOM ≠ injetado.
      Obs: o frontend 1.58 **não** expõe o tema ativo no DOM (sem
      `--st-*` nem `data-theme` nativo) — sync CSS-only não é
      possível sem ponte via Python/JS. Reaproveitar a paleta de
      `_NATIVE_THEME` e remover o aviso do config ao concluir.

## Patterns criados ou atualizados

- (nenhum)

## Referências

- Entrada relacionada:
  [2026-07-07-ui-ux-streamlit-158-bloco1-2.md](2026-07-07-ui-ux-streamlit-158-bloco1-2.md)
  (bloco 1 introduziu a seção removida aqui)
- Verificação: `streamlit==1.58.0`,
  `.venv/.../streamlit/static/static/js/index.dkY5s53S.js`
  (lógica `prefers-color-scheme`)
