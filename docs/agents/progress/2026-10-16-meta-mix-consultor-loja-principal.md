# 2026-10-16 — Meta MIX do consultor usa só a loja principal

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/gerais.py`, `tests/test_kpis_gerais.py`, `docs/agents/business-rules.md`
**Commit(s):** —

## Objetivo

Revisão da meta de cada consultor. A meta de pontos (Prata/Ouro) e a dos
aceleradores estavam certas; a meta MIX (e as metas dos cards por produto)
não.

## O que foi feito

- Novo helper `metas_produto_loja_principal` (`kpis/gerais.py`), irmão de
  `metas_pontos_consultor`: recorta o pivot CONSULTOR para a linha da loja
  principal. `app.py` passa a usá-lo no recorte de um consultor, no lugar
  do pivot inteiro.
- 5 testes em `TestMetasProdutoLojaPrincipal`, sabotados (helper devolvendo
  o pivot inteiro: caem 4).
- Conferência com dados reais 10/2026: Vitória 245.000 → 115.000;
  Alessandra e Cassiane 260.000 → 130.000; gerente com 3 lojas marcadas +
  Stella 360.000 → 130.000.

## Decisões não óbvias

- **Bug tinha duas portas.** (1) Consultor com produção em duas lojas:
  `filtrar_metas_ui` deixa as duas linhas e `calcular_kpis_gerais` soma os
  componentes do MIX → meta dobrada; cards por produto também dobravam.
  (2) Gerente marca N lojas e depois o consultor: `filtrar_metas_ui`
  prioriza `ui_filtro_lojas`, então o MIX somava N lojas. Aqui os cards por
  produto estavam certos (filtram pelas lojas da produção) e contradiziam o
  card MIX.
- **Recorte no app, não em `filtrar_metas_ui`** — o filtro de sidebar serve
  também ao escopo LOJA, onde somar lojas é o correto.
- **Sem fallback** — loja principal indeterminada ⇒ frame vazio (meta 0),
  mesmo contrato de `metas_pontos_consultor`; os avisos existentes cobrem.

## Pendências / follow-ups

- [ ] **Portabilidade fora do realizado de Consignado.** No banco,
  `categorias_produto.PORTABILIDADE` tem `grupo_dashboard`/`grupo_meta` =
  `CONSIGNADO` (usuário confirmou: no MIX, Portabilidade está junto de
  Consignado), mas `PRODUTOS_DASHBOARD["CONSIGNADO"]` (hardcoded) lista só
  `CONSIG_BMG/ITAU/C6`. Card de Consignado 10/2026: 39% (2,62 mi / 6,67 mi)
  contra 57% com Portabilidade (+1,21 mi). Afeta cards por produto, Gestão,
  `kpis/pontuacao.py` e prioridades — aguardando decisão do usuário.
- [ ] Aba Gestão resolve a loja do consultor pelo cadastro do RH (hoje), não
  pela loja principal; sem impacto em 10/2026 (único caso diverge dentro do
  mesmo patamar), risco em histórico.
- [ ] `TestObterMediasPeriodo::test_cache_e_dict_com_as_chaves_de_medias_du_por_nivel`
  já falhava antes desta mudança (chaves `producao_lojas` e
  `num_lojas_digitais` não previstas no teste).

## Referências

- Docs consultados: [business-rules.md](../business-rules.md#meta-do-consultor--escopo-consultor-nunca-rateio)

## Atualização — 2026-10-16 (Portabilidade no Consignado)

- Usuário confirmou: o card de Consignado é Novo + Refin + Portabilidade
  (meta para os três) e, na produção do MIX, Portabilidade soma no
  Consignado. `PRODUTOS_DASHBOARD["CONSIGNADO"]` ganhou `PORTABILIDADE`
  (único ponto de verdade; Gestão, `kpis/pontuacao.py` e prioridades
  derivam dele). Pendência acima **resolvida**.
- Conferência 10/2026: card de Consignado 2.621.475 (39%) → 3.836.069
  (57%) de 6.673.300.
- Teste `test_consignado_soma_novo_refin_e_portabilidade`, sabotado
  (sem `PORTABILIDADE` na lista, cai).
- Coluna Consignado da aba Gestão passa a incluir Portabilidade (deriva da
  mesma lista e compara com a mesma meta). A aba de quantidade
  "Consignado (Novo/Refin)" e as visões de Digitação/Distribuição seguem
  separando — não comparam com meta.
