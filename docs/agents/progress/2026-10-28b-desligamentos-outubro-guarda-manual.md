# 2026-10-28 — Desligamentos de 28/10 travados pela guarda MANUAL

**Agente:** Claude Code
**Tipo:** bugfix (dado de cadastro)
**Arquivos tocados:** nenhum no repositório (SQL avulso aplicado pelo usuário no SQL Editor)
**Commit(s):** —

## Objetivo

O angry-man recusou o arquivo de movimentações de RH de 28/10 (3
desligamentos) com `CORRECAO_MANUAL_EXISTENTE` na linha 4. O usuário pediu
para destravar a atualização dos desligados.

## O que foi feito

- Diagnóstico: a pessoa da linha 4 tinha janela MANUAL aberta (admissão
  declarada em setembro) na loja de origem, mas produzia em outra loja
  desde o início de outubro — transferência nunca registrada no ledger.
- Transferência aplicada pelo **usuário** no card "Transferências e Cargo"
  do angry-man (`fn_movimentacoes_replace`, 117), depois de dry-run limpo
  (sem pendência, sem divergência).
- Dois desligamentos (incluindo o da linha 4) fechados por SQL avulso,
  entregue ao usuário e aplicado por ele no SQL Editor: fim =
  desligamento + 1, origem MANUAL, cadastros `Desligado (a)` — mesmas
  guardas e pós-condições da migration 142.
- O terceiro desligamento (último dia 28/10) fica para o import do
  angry-man em 29/10, por decisão do usuário.

## Decisões não óbvias

- **Sem migration versionada, por privacidade.** Migration com a lista
  de desligados deixa nomes no histórico do git. A RPC de RH já foi
  desenhada para não devolver nome; o repositório passa a seguir a mesma
  regra para correções pontuais. O fato fica no banco (origem MANUAL); o
  porquê fica aqui, sem nomes. Migrations anteriores (126, 142, 109–118)
  seguem com nomes no histórico — reescrever o histórico não foi feito.
- **`execute_sql`/SQL Editor, não `apply_migration`:** o `apply_migration`
  grava o texto do SQL em `supabase_migrations`, com os nomes.
- **Transferência pela porta 117, desligamento fora dela.** A janela nova
  nasce MANUAL e a guarda da 114 recusa qualquer janela MANUAL aberta —
  nenhuma porta do angry-man fecha MANUAL por desligamento.
- **Risco aceito no terceiro desligamento:** pela RPC 114 o fim gravado
  será a data do arquivo (28/10), perdendo o último dia trabalhado, a
  menos que haja produção em 28/10 (aí fecha em último contrato + 1).

## Pendências / follow-ups

- [ ] `fn_movimentacoes_rh_import` gravar desligamento + 1 — terceira
      correção fora da porta (setembro, 142, esta).
- [ ] Desligar quem tem janela MANUAL aberta pela porta: angry-man lista
      as linhas bloqueadas e o operador confirma explicitamente. Muda o
      contrato da RPC (whitelist + redeploy da Edge Function + UI).
      Todo transferido pela 117 nasce MANUAL e cai neste bloqueio.

## Referências

- Docs consultados: `angry-man/docs/headcount.md` (regra de 11/09),
  `angry-man/docs/importacao.md` (porta 117), migrations 114, 117, 126, 142.
