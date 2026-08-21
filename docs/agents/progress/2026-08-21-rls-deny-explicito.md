# 2026-08-21 — RLS deny explícito (advisor `0008_rls_enabled_no_policy`)

**Agente:** Claude Code
**Tipo:** bugfix / docs
**Arquivos tocados:** `database/migrations/093_rls_deny_explicito.sql`
**Commit(s):** (pendente)

## Objetivo

Entender dois avisos INFO do advisor do Supabase — `public.consultor_afastamento`
e `public.reconquista` com RLS ligado e nenhuma policy — e ajustar o banco de
acordo.

## O que foi feito

- Diagnóstico dos dois casos, que são de naturezas **opostas**.
- Migration `093_rls_deny_explicito.sql`: policy nomeada `USING (false)` +
  `REVOKE ALL` de `anon`/`authenticated` nas duas tabelas, com bloco de
  validação no fim do arquivo. **Ainda não aplicada.**

## Decisões não óbvias

- **O aviso não é vulnerabilidade.** RLS ligado sem policy é o estado *mais
  restritivo possível* (nega tudo para quem não faz bypass). O linter reporta
  porque a causa comum do padrão é esquecimento — a tabela fica muda para a
  aplicação e ninguém entende por quê.

- **`consultor_afastamento` já era intencional.** A
  [089](../../../database/migrations/089_consultor_afastamento.sql) fecha de
  propósito: guarda motivo de afastamento (saúde, gravidez), e com uma chave
  Supabase compartilhada o que `anon` lê qualquer portador lê. A policy nova não
  muda comportamento — escreve a **intenção** no catálogo, que o par (RLS ligado,
  zero policies) não consegue comunicar nem ao linter nem a quem ler o schema
  daqui a um ano.

- **`reconquista` era drift real, e é o achado que motivou o arquivo.** A
  [028](../../../database/migrations/028_reconquista_v2_tabela.sql) cria a tabela
  com **zero** linhas de RLS ou GRANT, e nenhuma migration posterior liga RLS
  nela — mas o banco tem RLS ligado. Foi ligado fora do fluxo de migrations
  (botão do Studio). Aplicar `database/migrations/` do zero produzia um banco
  diferente do de produção, que é justamente a garantia que o diretório existe
  para dar.

- **Efeito silencioso do drift:** a
  [030](../../../database/migrations/030_reconquista_v2_view.sql) declara
  `v_reconquista WITH (security_invoker = on)` para "respeitar as policies de
  quem consulta". Sem policy na tabela base, a view devolve **zero linhas** para
  qualquer role sem bypass — o design declarado no cabeçalho da 030 é hoje letra
  morta. Passou despercebido porque a chave do `.env` é `service_role`
  (`BYPASSRLS`) e o recorte por perfil é client-side
  (`_filtrar_rls_reconquista`, `loaders.py:2203`).

- **Por que fechar e não abrir** (decisão do usuário, 2026-08-21) — abrir com
  `USING (true)` + `GRANT` no padrão 076/086 faria o `security_invoker` da view
  voltar a funcionar. Descartado: 076/086 guardam estrutura organizacional,
  `reconquista` guarda **carteira de cliente** (`co_adesao`, `saldo_contabil`,
  `link_aceite`). Enquanto a chave for única e compartilhada, liberar `anon` é
  liberar para todo portador.

- **Por que não replicar `pol_contratos_select` (011)** — policy por perfil via
  `obter_perfil_atual()` / `usuario_escopos` tem custo alto e benefício zero
  enquanto todo acesso for `service_role`, que sequer avalia policy. Registrado
  no COMMENT da policy como o caminho a seguir **se** o projeto sair da chave
  única: `pol_reconquista_deny` é o ponto exato a substituir.

- **Numeração `093`** — o "093" citado no cabeçalho da 091 e nos follow-ups de
  [2026-08-21-caderno-headcount-ponderado](2026-08-21-caderno-headcount-ponderado.md)
  é um passo **Python** (`carregar_consultores_ativos` com coluna `PESO`), que
  não gera arquivo `.sql`. Não há conflito; o cabeçalho da 093 diz isso
  explicitamente.

## Pendências / follow-ups

- [ ] **093 ainda NÃO aplicada.** Não há Postgres local — a migration não foi
      validada contra banco nenhum, só revisada. O bloco de validação no fim do
      arquivo tem os 4 checks
- [ ] Antes de aplicar, checar grants residuais de `anon` em `reconquista` (a
      028 nunca revogou os defaults do schema `public`):
      `SELECT grantee, privilege_type FROM information_schema.role_table_grants
      WHERE table_name = 'reconquista' AND grantee IN ('anon','authenticated');`
- [ ] Depois de aplicar, confirmar que os dois avisos somem do advisor e que
      `SELECT count(*) FROM v_reconquista` não muda
- [ ] **Auditar drift semelhante** — se o RLS de `reconquista` foi ligado pelo
      Studio, pode haver mais objetos em produção que nenhuma migration descreve.
      Vale um diff entre `pg_class.relrowsecurity` / `pg_policy` e o que
      `database/migrations/` declara

## Referências

- Docs consultados: [rls.md](../rls.md), [data-layer.md](../data-layer.md)
- Entrada relacionada: [2026-05-11-supabase-performance-warnings](2026-05-11-supabase-performance-warnings.md)
- Migrations relacionadas: 028, 030, 076, 086, 089, 090, 011
- Lint: <https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy>
