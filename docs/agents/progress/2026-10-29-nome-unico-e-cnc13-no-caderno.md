# 2026-10-29 — Regra única de nome de pessoa e CNC 13º fora do CNC no Caderno

**Agente:** Claude Code
**Tipo:** bugfix (alinhamento dashboard × Caderno)
**Arquivos tocados:** `src/shared/texto.py`, `tests/test_shared_texto.py`,
`tests/test_kpis_reconquista.py`,
`database/migrations/144_normalizacao_nome_unica.sql`,
`database/migrations/145_caderno_cnc13_grupo_proprio.sql`,
`docs/agents/business-rules.md`
**Commit(s):** — (não commitado; migrations não aplicadas)

## Objetivo

Realinhar o Caderno (Bereshit) ao dashboard em dois pontos levantados na
auditoria de 2026-10-29: a normalização de nome de pessoa, que cada lado
fazia pela metade, e o CNC 13º, que o Caderno somava ao CNC.

## O que foi feito

- `normalizar_nome` passou a colapsar espaço interno (tabulação e espaço não
  separável incluídos) além de dobrar acento.
- Migration 144: `public.fn_normalizar_nome(text)` com a mesma regra, as três
  colunas `nome_normalizado` dos ledgers geradas por ela e as 12 funções vivas
  que normalizavam inline trocando a expressão pela função (35 ocorrências).
- Migration 145: `obter_caderno_fechamento` com o grupo `CNC_13` próprio em
  `mix` e `productRanking`, e `contractVersion = 'v1.10'` no payload.

## Decisões não óbvias

- **Unir as duas regras, não escolher um lado** (decisão do usuário): o SQL
  colapsava espaço e não dobrava acento; o Python fazia o contrário. Os dois
  passam a fazer as duas coisas.
- **Sem `unaccent`**: a extensão não está instalada. `normalize(…, NFKD)` é
  `IMMUTABLE` no PG 17 e o banco é UTF8, então a função serve para coluna
  gerada sem extensão nova.
- **Corpos copiados das migrations vigentes, conferidos por md5** contra o
  `prosrc` em produção (o banco guarda CRLF na maioria). Cabeçalhos conferidos
  contra `pg_proc`, porque `CREATE OR REPLACE` redefine `SECURITY DEFINER` e
  `SET`. Gerador validado em Postgres 17 local: plpgsql compila, colunas
  geradas recalculam.
- **Impacto zero hoje**: nenhum nome com acento ou espaço repetido em
  ledgers, cadastro, supervisores ou contratos pagos desde 2025. Nas fontes
  externas que o Python também cruza (Reconquista, Liga, Promessa, Elegíveis,
  Prestamista, Fim de Relacionamento), nenhum espaço interno repetido; os três
  nomes acentuados da Reconquista já eram dobrados antes. A troca é preventiva.
- **`TestNormTexto.test_NAO_colapsa_espaco_interno` virou
  `test_colapsa_espaco_interno`**: era teste de caracterização do alias, e a
  regra antiga vinha só de convenção (progress/2026-09-15f). Suíte inteira
  verde depois da troca (1915 testes).
- **CNC 13º como grupo próprio, não PACK**: o MIX do Caderno não compara com
  meta, e onde não há meta o dashboard mostra cada produto do PACK separado.
  FGTS e Antecipação já eram grupos próprios no Caderno. O 13º não tem meta
  própria — por isso integra o PACK aqui.
- **`contractVersion` no payload**: snapshots antigos continuam congelados
  com o 13º dentro do CNC; sem o marcador, o leitor não distinguiria
  "CNC 13º = 0" de "CNC 13º somado ao CNC".

## Pendências / follow-ups

- [x] Aplicar a 144 (independe de deploy). Aplicada em 2026-10-29 pelo SQL
      Editor; as 13 funções em produção conferem por md5 com o arquivo.
- [ ] Publicar o Bereshit com suporte a `CNC_13` (commit `5d4ed88`, branch
      `feat/alinhamento-dashboard`, ainda sem push em 2026-10-29).
- [x] Aplicar a 145 antes do fechamento de 10/2026. Aplicada em 2026-10-29,
      **antes** do deploy do Bereshit, por decisão do usuário: 10/2026 não tem
      CNC 13º, então o parser antigo não perde nada até alguém republicar um
      mês que tenha. **Não republicar 02–04/2026 nem 05/2025 antes do deploy.**
- [ ] Republicar 02–04/2026 (e 05/2025, se desejado) para separar o 13º nos
      meses em que houve produção; junto da republicação de 01–07/2026 do
      relatório anual. Só depois do deploy do Bereshit.

**Verificação pós-aplicação (2026-10-29):** Caderno 08 e 09/2026 sem
`contractVersion` com md5 idêntico ao de antes; pagamentos sem vínculo
01–09/2026 iguais (`4 0 10 16 6 0 0 0 0`); produtividade individual 09/2026
com md5 idêntico; nenhuma chave `nome_normalizado` mudou (0/61, 0/425, 0/2).
03/2026: CNC + CNC_13 agora = CNC publicado (R$ 5.262.617,24), CNC_13 =
R$ 1.268.032,87, total do MIX igual ao publicado.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) — "PACK",
  "Exclusão de supervisores"; `docs/HEADCOUNT_ETL.md` §6.
- Bereshit: `docs/CONTRATO_FUNCIONAL.md`, "Alinhamento com o dashboard".
