# 2026-10-02 — angry-man: desktop sem a chave service_role (Fase A)

**Agente:** Claude Code
**Tipo:** bugfix de segurança (cross-repo: angry-man + migration 128 aqui)
**Arquivos tocados:**
- Numeros_venda: `database/migrations/128_lojas_codigo_dna_apply.sql`
- angry-man:
  - código: `electron/main.ts`, `electron/preload.cjs`, `vite.config.ts`, `src/lib/supabase.ts`, `src/contexts/AuthContext.tsx`, `src/services/import-orchestrator.ts`, `src/services/import-codigo-lojas.ts`, `src/types/electron.d.ts`
  - Edge Function: `supabase/functions/reconquista-rpc/index.ts`
  - testes e documentação
**Commit(s):** —

## Objetivo

Corrigir o achado crítico da revisão do angry-man: a chave `service_role`
ia **embutida no instalador**. O `vite define` do processo principal a
gravava em `dist-electron/main.js`, que é empacotado num `.asar` legível
por qualquer um. Com a chave, qualquer pessoa ignorava todo o RLS.

## O que foi feito

- O desktop passou a usar **o mesmo caminho de dados da web**:
  - login pela Edge Function `auth-login`, que barra quem não é
    admin/gestor no servidor;
  - leitura com a chave anon + RLS;
  - escrita e RPCs pelas Edge Functions com o JWT do app.
- O processo principal ficou sem client Supabase e sem bcrypt. Saíram os
  canais `supabase:query`, `supabase:rpc`, `auth:login` e
  `auth:hashPassword`.
- **Migration 128** (`fn_lojas_codigo_dna_apply`): o import de Códigos de
  Loja fazia UPDATE direto em `lojas`.
  - Na **web isso nunca gravou nada**: `lojas` só tem policy de SELECT,
    então o UPDATE afetava 0 linhas sem erro e o import contava todas como
    atualizadas.
  - Agora é uma RPC única, chamada via `reconquista-rpc`.
- Pacote compilado verificado: só a chave **anon** aparece no código do
  Electron e no bundle.

## Decisões não óbvias

- **Por que não um backend próprio para o desktop?** A web já roda em
  produção com as Edge Functions e a lista fechada de RPCs. Reaproveitar o
  caminho elimina a diferença que escondia bugs: RPC nova sem registro no
  mapa só falhava na web.
- **Metas:** a `fn_admin_import` faz DELETE + INSERT na mesma transação.
  O "apagar o mês e falhar o insert" do desktop deixa de existir para o
  primeiro lote. Os lotes seguintes (acima de 1000 metas no mês) ainda são
  chamadas separadas; follow-up no item 3 da revisão.
- **Regras de escrita conferidas:** a anon tem GRANT de UPDATE em
  `usuarios`, `contratos` e `metas`, mas as policies exigem
  `obter_perfil_atual()`, que vem de uma variável de sessão
  (`app.current_user_perfil`). Nenhuma função exposta a define, então a
  anon não escreve nessas tabelas.
- **Mudança de comportamento no desktop:**
  - a sessão expira em 8h;
  - o desktop depende das Edge Functions;
  - supervisor/gerente não entram mais (antes era bloqueio só na tela).

## Pendências / follow-ups

- [ ] **Usuário:** aplicar a migration 128.
- [ ] **Usuário:** republicar a Edge Function `reconquista-rpc`.
- [ ] **Usuário:** subir a versão, gerar o instalador e reinstalar.
- [ ] **Fase B — trocar a chave.** A chave vazada continua válida até as
      chaves legadas serem desativadas, e está em todo instalador ≤ 1.4.2.
      Consumidores encontrados (só caminhos, nenhum no Git):
      - `angry-man/.env`
      - `Numeros_venda/.env`
      - `Numeros_venda/.env.toml`
      - `bereshit/.env.local`
      - deploy do dashboard e Edge Functions (`SUPABASE_SERVICE_ROLE_KEY`)
- [ ] Sinalizado, não removido: a dependência `bcryptjs` do angry-man ficou
      sem nenhum uso (nem em scripts ou testes). Removível do
      `package.json` com confirmação.

## Referências

- Revisão do angry-man (sessão de 02/10/2026), itens 1 e 2
- Supabase: "Migrating to publishable and secret API keys"
