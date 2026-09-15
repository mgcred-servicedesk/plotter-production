# 2026-09-15 — Resumo por loja no fim do Dashboard de Pontuação (+ região e exportação)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/pontuacao.py`,
`src/dashboard/pages/dashboard_pontuacao.py`, `src/dashboard/permissions.py`,
`tests/test_kpis_pontuacao.py`, `tests/test_permissions.py`,
`tests/test_pages_resumo_lojas_pontuacao.py`
**Commit(s):** (não commitado)

## Objetivo

Para admin, gestor e gerente comercial: tabela no fim da página de
Pontuação com, por loja, os pontos efetivos, a projeção, o atingimento
das Metas Prata e Ouro e a meta diária por DU.

## O que foi feito

- `calcular_resumo_lojas_pontuacao` (`kpis/pontuacao.py`), função pura.
  Colunas: Loja, Pontos, Projeção, Meta Prata, Ating. Prata %, Meta
  Ouro, Ating. Ouro %, Meta Diária Prata, Meta Diária Ouro. A última
  linha é `TOTAL` (`ROTULO_TOTAL_RESUMO_LOJAS`).
- Chave nova `resumo_lojas_pontuacao` na matriz de permissões (admin,
  gestor e gerente_comercial).
- `_render_resumo_lojas` em `pages/dashboard_pontuacao.py`, desenhado
  com `exibir_tabela` e com a linha TOTAL destacada.
- `app.py` passa `df_metas_loja=df_metas_f`, `consultor_selecionado` e
  `mes`/`ano`, que servem só para o nome do arquivo.
- Flag "Separar por região" (`st.toggle`, chave de matriz
  `resumo_lojas_por_regiao`, só admin e gestor). Mostra uma tabela por
  região, cada uma com o próprio TOTAL, e o "Total geral" no fim. A
  função é `calcular_resumo_lojas_pontuacao_por_regiao`.
- Botão de exportação no fim, via `botao_exportar_csv`. O frame vem de
  `montar_exportacao_resumo_lojas`, que fica em `pages/dashboard_pontuacao.py`.

## Decisões não óbvias

- **Fórmulas iguais às dos cards (`calcular_kpis_gerais`), por loja.**
  Projeção = pontos ÷ DU decorridos × DU total. Meta diária =
  max(0, meta − pontos) ÷ DU restantes, para Prata e para Ouro. A regra
  é a "Meta diária restante" do business-rules, escolhida pelo usuário.
- **A meta é a do escopo LOJA (`df_metas_f`), nunca `df_metas_kpis`.**
  Com um consultor selecionado, `df_metas_kpis` passa a ser a linha de
  escopo CONSULTOR. Por isso a página recebe um parâmetro separado.
- **O resumo some quando há um consultor selecionado.** A página
  mostra um aviso no lugar. Comparar a meta da loja com a produção de
  uma pessoa é justamente a distorção que já foi corrigida nos cards.
- **Universo: lojas com produção OU com meta > 0.** Uma loja com meta e
  sem ponto aparece zerada.
- **"Não se aplica" é NaN, não 0.** Isso vale para loja sem meta
  (atingimento e meta diária) e para meta não batida com o período
  encerrado (meta diária). `exibir_tabela` mostra NaN como célula
  vazia, e não travessão, e trocar isso mexeria no componente
  compartilhado. Por isso um caption nomeia as lojas sem meta, como a
  aba Rankings faz. A distinção continua por valor da meta, nunca por
  nome de loja (ver `2026-09-11-pontuacao-sem-meta-travessao.md`).
- **A meta diária do TOTAL usa o gap do agregado, e não a soma dos gaps
  das lojas.** Assim ela bate com o card "meta diária restante": loja
  acima da meta compensa loja abaixo. Por isso a soma das metas diárias
  das lojas pode ser maior que a do TOTAL. Isso é intencional e tem
  teste (`test_total_bate_com_cards_do_topo`).
- **A flag não aparece para o gerente comercial.** O recorte dele já é a
  própria região. A decisão é pelo perfil efetivo: um admin em
  "Visualizar Como gerente" também não vê a flag.
- **A região é a REGIAO do período (escolha do usuário), não a
  REGIAO_ATUAL.** É o mesmo eixo das metas, então meta e realizado ficam
  na mesma região, mesmo em mês passado com loja remanejada. A região
  vem primeiro da meta. Loja só com produção usa a REGIAO do `df`; se
  houver mais de uma, vale a de mais pontos, com desempate alfabético
  (critério de `resolver_loja_principal`). Loja sem região vai para o
  bloco "Sem região", o último.
- **Cada bloco de região é o mesmo `calcular_resumo_lojas_pontuacao`
  aplicado às lojas dela.** Não há segunda implementação de fórmula,
  universo ou ordenação. O Total geral é o TOTAL da tabela única e bate
  com os cards.
- **Exportação em CSV (padrão do projeto), sem pacote novo para XLSX.**
  - Números continuam números: sem separador de milhar e sem "%", com
    `;`, decimal `,` e UTF-8 com BOM, então o Excel pt-BR soma e ordena.
  - Arredondamento igual ao da tela: pontos com 2 casas, % com 1.
  - Os captions não vão para o arquivo, por isso existe a coluna
    `Observação` ("Sem meta X cadastrada" / "Período encerrado — X não
    atingida"), que explica a célula em branco.
  - Por região: coluna `Região` primeiro, linhas `TOTAL <região>` e
    `TOTAL GERAL`.
  - O arquivo segue a flag: `resumo_lojas_pontuacao_AAAA_MM[_por_regiao].csv`.
- Ordenação: Ating. Prata % decrescente; lojas sem meta vão para o fim,
  ordenadas por pontos.

## Pendências / follow-ups

- [ ] Validar no app real com dados de 09/2026 (os testes usam frames
      sintéticos e a página renderizada via AppTest).
- [ ] Se o CSV não bastar (ex.: largura de coluna, formato de % no
      Excel), avaliar XLSX com openpyxl. Ele está instalado no .venv,
      mas não está declarado como dependência, então precisa de aprovação.

Nota: `exibir_tabela` com `highlight_mask` já cai para `st.dataframe`,
então a linha TOTAL não se perde ao ordenar pelo AG Grid.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) (Metas,
  Meta diária restante), [ui-components.md](../ui-components.md)
  (`exibir_tabela`).
