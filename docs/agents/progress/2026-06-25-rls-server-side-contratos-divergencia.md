# 2026-06-25 — RPC obter_digitacao_diaria + divergência doc×código sobre RLS de `contratos`

**Agente:** Claude Code (subagente `supabase-schema-rls`)
**Tipo:** feature + docs (registro de divergência)
**Arquivos tocados:** `database/migrations/035_fn_digitacao_diaria.sql`
**Commit(s):** (pendente)

## Objetivo

Criar a RPC `obter_digitacao_diaria(p_mes, p_ano)` para alimentar uma visão de
DIGITAÇÃO DIÁRIA (volume operacional do mês, todos os status), e registrar uma
divergência doc×código sobre a postura de RLS de `contratos` descoberta no
processo.

## O que foi feito

- Migration **035** com `obter_digitacao_diaria(INTEGER, INTEGER)`:
  - Lê `public.contratos` **direto** (não as views): a visão precisa de toda
    linha do mês em qualquer status; `v_contratos_dashboard` é pagos-only e as
    demais views excluem linhas.
  - Janela = **mês-calendário** (mês vigente → dia a dia até `current_date`;
    histórico → mês inteiro até o último dia). NÃO usa a janela móvel de 30
    dias da migration 003.
  - Retorna só agregados por dia: `qtd_digitada = COUNT(*)`,
    `valor_digitado = SUM(valor)` **bruto** (sem `conta_valor`), `ORDER BY
    data_cadastro`. 1 linha por dia com ≥1 contrato.
  - `SECURITY INVOKER` (implícito), `SET search_path = ''`, `LANGUAGE plpgsql
    STABLE` — mesmo padrão da migration 003. Colunas `contratos.data_cadastro`
    (DATE) e `contratos.valor` (NUMERIC) confirmadas no código.

## Decisões não óbvias

- **Por que ler `contratos` direto e não criar view?** Criar uma view nova seria
  objeto estrutural adicional para uma agregação trivial; as views existentes
  filtram por status e perderiam linhas. Ler a tabela direto + `GROUP BY` é o
  caminho mínimo.
- **Por que sem vazamento mesmo sem dimensão de perfil no retorno?** A RPC é
  `SECURITY INVOKER`, então ao ler `public.contratos` **herda** a policy
  `pol_contratos_select` (migration 011, baseada em `obter_perfil_atual()` /
  `obter_usuario_atual_id()`). O agregado já sai filtrado pelo perfil do
  chamador no servidor — o `COUNT`/`SUM` só enxerga as linhas que a policy
  libera.

## Divergência doc×código (RLS server-side real em `contratos`)

- **Achado:** `docs/agents/rls.md` enquadra a RLS principalmente como mecanismo
  **client-side** (`aplicar_rls` / `aplicar_rls_metas` /
  `aplicar_rls_supervisores` em `df`, descritos como a defesa primária; ver
  também a auto-memória "RLS fail-closed: RLS é client-side"). A seção de
  Postgres (rls.md, linhas ~82-84) cita as policies, mas pelos **nomes antigos
  por perfil** `pol_contratos_consultor` / `pol_metas_consultor`.
- **Código (verdade):** a migration **011** (`011_consolidar_rls_policies.sql`)
  **dropou** as policies por perfil e consolidou tudo em **uma** policy
  `pol_contratos_select` (`FOR SELECT`), com ramos por perfil em OR via
  `(SELECT obter_perfil_atual())` e join em `usuario_escopos` por
  `(SELECT obter_usuario_atual_id())`. Ou seja: existe RLS **server-side real e
  ativa** em `contratos`, independente do `aplicar_rls` da aplicação. Uma RPC
  `SECURITY INVOKER` já fica protegida no banco.
- **Impacto:** o `aplicar_rls*` client-side é **defesa em profundidade**, não a
  única barreira. RPCs agregadas que leem `contratos` como INVOKER são seguras
  por si só. A doc subestima isso e ainda aponta nomes de policy obsoletos.

## Pendências / follow-ups

- [ ] Atualizar `docs/agents/rls.md`: substituir `pol_contratos_consultor` por
      `pol_contratos_select` (consolidada na 011) e esclarecer que a RLS de
      `contratos` é **server-side real**, sendo o `aplicar_rls` client-side uma
      camada adicional (defesa em profundidade), não a barreira primária.
- [ ] Revisar a auto-memória "RLS fail-closed / RLS é client-side" à luz disso
      (a afirmação "RLS é client-side" vale para o filtro em `df`, mas há RLS
      server-side em `contratos`).
- [ ] Aplicar a migration 035 no Supabase SQL Editor (ainda não aplicada).

## Referências

- Migration: `database/migrations/035_fn_digitacao_diaria.sql`
- Policy: `database/migrations/011_consolidar_rls_policies.sql`
  (`pol_contratos_select`)
- Padrão de datas/RPC: `database/migrations/003_view_contratos_cancelados.sql`
- Docs consultados: [docs/agents/rls.md](../rls.md),
  [docs/agents/data-layer.md](../data-layer.md),
  [docs/agents/rpi-workflow.md](../rpi-workflow.md)
