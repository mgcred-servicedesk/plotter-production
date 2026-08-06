# 2026-08-06 — Popover do filtro de Consultor corta a última opção (bug upstream, não corrigido em CSS)

**Agente:** Claude Code
**Tipo:** research / bugfix (parcial — mitigação de UX, sem fix de causa raiz)
**Arquivos tocados:** `src/dashboard/ui/sidebar.py`
**Commit(s):** ver branch `fix/sidebar-filtro-consultor-universo`

## Objetivo

Usuário reportou que o dropdown do filtro "Consultor" (sidebar, perfis
supervisor/gerente) não mostra a última opção da lista — a barra de
rolagem não desce até o fim. Pediu correção.

## O que foi feito

- Diagnosticado (sem browser tooling — via prints de DevTools que o
  usuário coletou a pedido) que a causa **não é falta de `max-height`/
  `overflow` em CSS**. É um bug de posicionamento no próprio
  Streamlit 1.60 (frontend usa `react-aria-components` para
  `st.selectbox`, não mais BaseWeb).
- Evidência: o elemento que posiciona o popover tem, no `style`
  inline (calculado via JS a cada abertura):
  `position: fixed; bottom: 135px; left: 20px; max-height: 798px;
  transform: translate(20px, 853px);`. `max-height` é generoso — não
  é o gargalo. O `translateY(853px)` empurra o popover para muito
  abaixo do viewport a partir de uma âncora já perto do fim da tela.
- Duas tentativas de fix via CSS (`assets/dashboard_style.css`,
  mirando `[data-baseweb=...]`) foram aplicadas e **revertidas** —
  não tinham efeito real (o app não usa mais BaseWeb; os seletores
  não casavam com o elemento certo) e arriscavam interferir em outros
  dropdowns do app.
- Mitigação aplicada: `help="Digite parte do nome para filtrar."` no
  `st.selectbox` de `_render_consultor_subselect` (mesmo texto que já
  existia no seletor de "Visualizar Como" para admin/gestor) — reduz
  a necessidade de rolar a lista até o fim, já que o combobox suporta
  busca por texto nativamente.

## Decisões não óbvias

- **Por que não uma correção de CSS?** O offset errado
  (`translate(20px, 853px)`) é calculado em JavaScript pelo próprio
  Streamlit a cada abertura do dropdown, com base em quão fundo o
  campo está dentro do scroll da sidebar. CSS `!important` não
  recalcula esse número — só sobrescreve propriedades estáticas.
  Forçar uma posição fixa via CSS quebraria outros dropdowns do app
  que hoje funcionam bem (ex.: campos mais no topo da sidebar).
- **Por que não patchear via JS injetado?** `st.markdown(...,
  unsafe_allow_html=True)` sanitiza `<script>` tags (Streamlit não
  executa). Rodar JS arbitrário exigiria `st.components.v1.html`
  (iframe, sandboxing complica manipular o DOM pai) — desproporcional
  para esse bug e fora do escopo sem aprovação explícita.
- **Caso relacionado já corrigido pelo Streamlit:**
  [issue #9387](https://github.com/streamlit/streamlit/issues/9387) /
  [PR #16087](https://github.com/streamlit/streamlit/pull/16087)
  descreve e corrige exatamente essa classe de bug — mas para
  `st.popover`, não para o `ComboBox` usado por `st.selectbox`
  (componentes diferentes no frontend do Streamlit). A correção não
  se aplica ao nosso caso.

## Pendências / follow-ups

- [ ] Abrir issue no `streamlit/streamlit` com a reprodução (prints de
      DevTools já coletados nesta investigação) — ainda não feito,
      aguardando decisão do usuário.
- [ ] Considerar compactar a sidebar acima do filtro de Consultor
      (ex.: colapsar "Visualizar Como"/Período) para reduzir a
      profundidade do campo na tela — reduz a chance do bug aparecer,
      não é garantia. Não implementado (mudança estrutural maior,
      discutir separado).
- [ ] Se o Streamlit corrigir isso upstream numa versão futura,
      revisitar — o `help=` adicionado pode ficar ou sair conforme UX.

## Referências

- [github.com/streamlit/streamlit#9387](https://github.com/streamlit/streamlit/issues/9387)
- [github.com/streamlit/streamlit#10204](https://github.com/streamlit/streamlit/issues/10204) (visual, scrollbar)
- [github.com/streamlit/streamlit#10239](https://github.com/streamlit/streamlit/issues/10239) (altura dinâmica de popover, em aberto)
- [PR #16087](https://github.com/streamlit/streamlit/pull/16087) (fix aplicado só a `st.popover`)
