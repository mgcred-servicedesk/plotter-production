# 2026-09-17 — Campanhas: destaque do escopo nos rankings

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/pages/campanhas.py`,
`src/dashboard/kpis/campanha.py`, `tests/test_kpis_campanha.py`

> Continua [2026-09-17](2026-09-17-campanhas-rls-so-no-analitico.md).

## Pedido

Destacar nos rankings da campanha (que são da rede) os consultores e
lojas do grupo de quem está logado, como já fazem os rankings do
dashboard de vendas.

## Decisões não óbvias

- **Reuso, não cópia.** `mascara_destaque` chama
  `tabs.rankings._make_highlight_fn` — mesma regra nas duas telas:
  gerente destaca as lojas da região, supervisor a própria loja,
  consultor o próprio nome, admin/gestor nada. Custo: importa um nome
  privado de outro módulo (o `app.py` já faz o mesmo com
  `rls._obter_perfil_efetivo`). Se a função mudar de assinatura, a
  suíte da campanha quebra.
- **Adaptação de colunas.** O ranking da campanha usa `LOJA`/`CONSULTOR`
  maiúsculas; a função de vendas espera `Loja`/`Consultor`. Renomeia
  numa cópia só para gerar a máscara — nada muda no CSV nem na tela.
- **Consultor pertence ao grupo da loja ATUAL.** A coluna `Loja` do
  ranking de consultores traz ` *` para quem produziu em mais de uma
  loja. A marca virou constante (`MARCA_MULTIPLAS_LOJAS`) e é removida
  antes de comparar; sem isso, quem foi transferido para a loja do
  supervisor sumiria do destaque, calado. A loja de origem **não**
  destaca essa pessoa, mesmo tendo produção dela — o destaque segue a
  loja que a coluna mostra.
- **Escopo vem de `aplicar_rls(df)`**, como em vendas: "visualizar
  como" e fail-closed valem igual.

## Verificação

`TestDestaqueDoEscopo` (6 testes, herda e reroda os 7 de RLS). Três
sabotagens pegas: marca não removida (1), máscara não repassada (5),
escopo sem RLS (5). Suíte: 1283 passam. **Não validado visualmente** —
o destaque usa o caminho `st.dataframe` + Styler que os rankings de
vendas já usam.
