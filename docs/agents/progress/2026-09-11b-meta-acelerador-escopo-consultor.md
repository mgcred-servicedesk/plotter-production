# 2026-09-11b — Meta de acelerador: escopo CONSULTOR, sem somar lojas

**Agente:** Claude Code (subagente `biz-rules`)
**Tipo:** bugfix / regra de negócio
**Arquivos tocados:** `src/dashboard/kpis/gerais.py`,
`src/dashboard/kpis/gestao.py`, `docs/agents/business-rules.md`
**Commit(s):** (não commitado nesta sessão)

Segunda leva de [2026-09-11 — Meta individual do consultor](2026-09-11-meta-individual-consultor-substitui-rateio.md).

## Objetivo

1. A meta de acelerador (escopo CONSULTOR, em quantidade) dobrava para
   quem produziu em duas lojas no mês: `LOJA.isin(lojas_ativas).sum()`
   somava 6 + 6 = 12.
2. O comentário de `kpis/gestao.py` afirmava que acelerador "não tem
   meta individual" — falso desde que o loader passou a trazer as
   colunas de nível.

## O que foi feito

- `calcular_kpis_qtd_produtos`: novo `lojas_meta`. Quando `df` tem UM
  único consultor, a meta vem só da **loja principal**
  (`resolver_loja_principal` — mesmo critério dos pontos e da coluna
  `Loja` dos rankings). Qualquer outro recorte segue somando as lojas
  ativas (0 no escopo LOJA, que é o certo). Sem parâmetro novo: a
  decisão nasce do próprio `df`, e quem decide a loja do consultor
  continua sendo um lugar só no código.
- `ACELERADORES_COL_META` (`kpis/gerais.py`): rótulo → coluna de meta,
  irmão de `PRODUTOS_DASHBOARD_COL_META`. Necessário porque
  `ACELERADORES` usa "Emissao" (sem acento) e a coluna é `EMISSAO`.
- `matriz_metas` (`kpis/gestao.py`) devolve os quatro aceleradores no
  nível PRATA. `COL_TOTAL` é calculado **antes** de anexá-los, então
  continua somando só os produtos monetários.
- Comentário corrigido em `gestao.py`.

## Validação (08/2026, dados reais)

```
ELAINE GUARDENGUI DA SILVA (1 loja) — metas CONSULTOR
  Emissão qtd=0 meta=6.0 %=0.0 | Super Conta qtd=7 meta=6.0 %=116.7
  BMG Med qtd=10 meta=6.0 %=166.7 | Vida Familiar qtd=5 meta=6.0 %=83.3
CAMILLY DE OLIVEIRA LAURIA (2 lojas) — metas CONSULTOR
  Emissão qtd=0 meta=6.0 | Super Conta qtd=2 meta=6.0 %=33.3
  BMG Med qtd=0 meta=6.0 | Vida Familiar qtd=1 meta=6.0 %=16.7   (era 12)
ORG-WIDE — metas LOJA: os quatro com meta=0.0
matriz_metas (ELAINE): CNC 40.000 + CLT 12.000 + Saque 0 + Consignado
  71.000 = Total 123.000; aceleradores 6/6/6/6 FORA do Total.
```

## Decisões não óbvias

- **Detecção do recorte por `df["CONSULTOR"].nunique() == 1`**, não por
  parâmetro novo em `obter_kpis_qtd_periodo`. Evita plumbing pela
  função memoizada e cobre qualquer chamador. Risco residual aceito:
  uma loja onde só uma pessoa produziu é lida como recorte de
  consultor — e nesse caso `lojas_ativas` já é uma loja só, então o
  resultado não muda.
- **Não extrapolar meta de acelerador para a loja** (individual ×
  headcount): a empresa define a meta GERAL da loja MENOR que esse
  produto (35,4M contra 57,5M), então extrapolar inventaria número.
- **`ACELERADORES_COL_META` em `gerais.py`, não em `gestao.py`** — os
  nomes de coluna já moram lá (`_PRODUTOS_QTD`), e a aba de Gestão não
  é a única superfície que pode precisar do mapa.

## Pendências / follow-ups (para o subagente de UI — `ui-dash`)

A meta já existe na camada de KPI, mas a aba Gestão ainda a bloqueia em
três pontos de `src/dashboard/tabs/gestao_consultores.py`:

- [ ] **~linha 521-528:** `bases` remove `BASE_META` quando
  `acelerador` — a opção "% da meta" nem aparece no seletor. Remover o
  gate e o comentário "Acelerador nao tem meta individual".
- [ ] **~linha 1007:** `lacuna_acel = calcular_lacuna(resultado,
  criterios, None, apenas=acels_sel)` passa `metas=None`; com meta, o
  critério de acelerador em base "% da meta" continuaria contribuindo 0
  para a lacuna. Passar `metas_res`.
- [ ] **~linha 682-687:** `_motivo_meta_indisponivel` responde
  "Acelerador nao tem meta individual" — texto agora falso.
- [ ] Formatação: a meta de acelerador é contagem de contratos (6), não
  R$. Conferir que o limiar exibido não seja formatado como moeda.

## Referências

- Docs: [business-rules.md](../business-rules.md) § Metas → "Meta de
  acelerador — quantidade, só no escopo CONSULTOR"
