# 2026-10-16 — Promessa Diária: lead sem consultor vai para o supervisor da loja

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `database/migrations/138_reconquista_promessa_consultor_identificado.sql`, `src/dashboard/kpis/reconquista.py`, `src/dashboard/loaders.py`, `src/dashboard/tabs/analiticos.py`, `tests/test_kpis_reconquista_promessa.py`, `tests/test_loader_reconquista_promessa.py`, `docs/agents/business-rules.md`
**Commit(s):** — (não commitado)

## Objetivo

Continuação de [2026-10-16c](2026-10-16c-reconquista-v3-promessa-diaria.md).
O usuário pediu: promessa cujo consultor não é identificado vai para o
supervisor atuar; proposta feita por alguém na loja anterior pertence a
essa loja. Também: redeploy da Edge Function e nova build do angry-man.

## O que foi feito

- Migration 138 (`CREATE OR REPLACE VIEW`, coluna nova no fim):
  `v_reconquista_promessa.consultor_identificado = consultor_id IS NOT NULL`.
  **Não aplicada** — o usuário aplica pelo SQL Editor.
- `promessas_por_consultor`: separa identificados / não identificados
  **antes** de `excluir_supervisores`; os não identificados viram a linha
  "`<SUPERVISOR> · sem consultor identificado`" do supervisor vigente da
  loja (`carregar_supervisores(mes, ano)`, coluna LOJA, match por
  `normalizar_nome`). Loja sem supervisor => "`Sem supervisor vigente · <LOJA>`".
- Loader: `KeyError` (view sem a coluna) => `promessas_por_consultor = None`
  + `logger.exception`. Caption e aviso da sub-aba atualizados.
- 11 testes novos; 5 sabotagens (todos como identificados, lead no nome do
  arquivo, supervisor errado, descartar loja sem supervisor, classificar
  depois da exclusão) — todas pegas, código restaurado.
- Edge Function `reconquista-rpc` redeployada (v12, `verify_jwt=false`
  mantido) com `fn_importar_reconquista_promessa` na whitelist.
- angry-man 1.4.7: bump em `package.json`/`package-lock.json` (sem commit
  nem tag) e build Windows (`Setup 1.4.7.exe` + `-1.4.7-win.zip` em
  `release/win-x64/`). Conferido no `app.asar`: card novo presente, sem
  service_role.

## Decisões não óbvias

- **Por que coluna nova na view e não comparar `consultor` com
  `consultor_nome`?** — a view faz `COALESCE(con.nome, consultor_nome)` e o
  match é ILIKE: resolvido e não resolvido têm o mesmo texto. Sem o
  booleano não há como distinguir.
- **Classificar antes de excluir supervisor** — nome não resolvido na loja
  da promessa é lead da loja, mesmo que seja o nome de um supervisor de
  outra loja (caso LETICIA GONCALVES DA COSTA, supervisora de Mesquita,
  com promessas em 49889).
- **Supervisor = cadastro** (escolha do usuário), não a coluna do arquivo.
  Consequência: enquanto o cadastro de HELP ALCANTARA / CARREFOUR estiver
  invertido (ver business-rules § Promessa Diária), o lead sem consultor de
  49820 vai para MARIANA DE OLIVEIRA RODRIGUES.
- **"Não identificado" = só sem cadastro na loja** — o usuário não marcou
  "consultor de outra loja/supervisor" como critério extra.

## Pendências / follow-ups

- [ ] Usuário aplica a 138 no SQL Editor; validar com o bloco VALIDACAO.
- [ ] Usuário corrige o cadastro (ERICA → HELP ALCANTARA, MARIANA → HELP
      ALCANTARA CARREFOUR, nome com "ROSA" em supervisores e consultores) e
      reimporta 09 e 10/2026.
- [ ] Usuário instala a 1.4.7 e importa 09 e 10/2026; conferir contra os
      números esperados de 2026-10-16c.
- [ ] Commit nos dois repos (Numeros_venda e angry-man, incluindo o
      `chore(release): 1.4.7`).

## Referências

- [business-rules.md § Promessa Diária](../business-rules.md#promessa-diária--promessas-a-partir-de-092026-v3)
