# 2026-11-04 — Loja de origem pela digitacao anterior a transferencia

Operacao esclareceu: contrato digitado antes da transferencia fica na loja
anterior. Transferencias de Alessandra e Vitoria permanecem em 01/10/2026.

Criada `database/migrations/148_contratos_origem_anterior_transferencia_outubro.sql`
para aplicacao pelo usuario, depois da 147. Nao aplicada remotamente.

- Alessandra: 3005011, 3005005, 3008434, 3008435, 3009606 e 3009607,
  digitados em setembro, de Mage para Santa Cruz da Serra: R$ 21.787,04.
- Vitoria: 3007254, digitado em 22/09, de Caxias Guanabara para Mage:
  R$ 4.910,06.
- Corrige loja_id e consultor_id para o cadastro da mesma pessoa na origem.
- Mantem a competencia de outubro, datas, valores e demais campos; compara
  toda a linha exceto loja_id, consultor_id e updated_at, e o valor da view.
- Guardas conferem contrato, ADE, digitacao, competencia, cadastro unico,
  vinculo na origem, transferencia em 01/10 e par coerente de loja/cadastro.
- Atomica e reaplicavel. Nao altera vinculos nem rematerializa snapshots.
- A apuracao anterior reproduziu 35 pendencias: 28 contempladas na 147 e 7
  nesta 148. Zero esperado somente depois de ambas, se nao houver novos dados.
- Corrigir tambem no extrator/origem; reimportacao pode desfazer o ajuste.

Validacao: leitura remota dos sete contratos confirmou a identificacao e
estado anterior. SQL e PL/pgSQL validados com pglast. Nao houve teste de
execucao contra PostgreSQL isolado; ambiente local indisponivel nesta sessao.
Nenhuma escrita em producao. Alteracoes locais preexistentes preservadas.
