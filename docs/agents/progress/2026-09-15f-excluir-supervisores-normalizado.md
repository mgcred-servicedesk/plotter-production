# 2026-09-15 — Supervisor vazando no ranking de consultores (grafia do nome)

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/kpis/gerais.py`, `tests/test_kpis_gerais.py`
**Commit(s):** —

## Objetivo

Revisar o atingimento dos consultores nos rankings.

## O que foi feito

- Auditoria com dados reais (08/2026 e 09/2026): fórmula (pontos ÷
  `META_PRATA` escopo CONSULTOR da loja principal) confere com
  `business-rules.md`; **zero divergência** entre o ranking e o card de
  cada consultor; 47/47 lojas com meta individual (só DIGITAL sem meta,
  com aviso); nenhum VALOR negativo; nenhum nome duplicado por
  caixa/acento.
- Bug achado: `excluir_supervisores` comparava nomes por igualdade
  exata. Em 08/2026 a supervisora `DJANE MARIA PEREIRA DOS SANTOS`
  (cadastro) aparecia nos contratos como `Djane Maria Pereira dos
  Santos` e entrava no ranking de consultores (1,5%).
- Correção: o match passa por `normalizar_nome` (`src/shared/texto.py`)
  nos dois lados. Teste novo em `TestHelpers`, verificado falhando sem a
  correção.

## Decisões não óbvias

- **`normalizar_nome` (dobra acento) em vez de só strip+upper** — é a
  chave canônica do projeto para comparar pessoas entre fontes.
  Não colapsa espaço duplo interno (só pontas); mantido por convenção.
- **Corrigido na origem, não nos rankings** — a função é usada em 16
  pontos; 08/2026 (mês fechado) muda levemente em pontuação,
  produtividade, gestão, produtos, comparativos etc. Aprovado pelo
  usuário. A rede de segurança em `kpis/produtividade.py` (re-exclusão
  por `_norm_nome`) vira no-op, como a própria docstring previa.

## Pendências / follow-ups

- [ ] Outros cortes de supervisor ainda por match exato (não tocados, fora
  do escopo aprovado): `contar_consultores` e o bloco em
  `kpis/gerais.py` (~linha 427), `tabs/em_analise.py:36`,
  `tabs/produtos.py:570`, `ui/prioridades_acao.py` (188/337/739, só
  strip), `ui/sidebar.py:289`.
- [ ] Rede em `kpis/produtividade.py` pode ser removida (decisão do
  usuário).

## Referências

- Docs consultados: [business-rules.md](../business-rules.md)
