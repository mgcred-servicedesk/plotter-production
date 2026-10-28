# 2026-10-21 — Supabase: grants e planejamento de backup

**Tipo:** auditoria e registro solicitado pelo usuário.
**Projeto:** yesmihaeaqodtzqgjipv, compartilhado por Numeros_venda, angry-man e consumidores como bereshit.
**Estado:** pesquisa concluída; mudanças de permissões e implantação de backup pendentes. Nenhum grant, policy, dado ou configuração remota foi alterado nesta auditoria.

## Mudança de 30/10/2026

O Supabase deixará de conceder automaticamente os privilégios usados pela Data API às novas tabelas public nos projetos existentes. Tabelas existentes preservam seus grants. Novos projetos, branches e reconstruções precisam de permissões explícitas. Grants controlam acesso ao objeto; RLS controla as linhas. service_role também precisa de privilégios SQL.

Fontes oficiais consultadas em 21/10/2026:
- https://github.com/orgs/supabase/discussions/45329
- https://supabase.com/docs/guides/api/securing-your-api

## Evidências do banco em 21/10/2026

- 30 tabelas public, todas com RLS; 12 views, todas security_invoker=on.
- service_role tem SELECT/INSERT/UPDATE/DELETE efetivos nas tabelas e views; USAGE no schema e na sequência feriados_id_seq.
- anon tem SELECT efetivo em 22 tabelas e 10 views. Policies e tabelas subjacentes ainda condicionam acesso.
- 16 tabelas têm policy SELECT USING (true), incluindo consultores, lojas, periodos e caderno_fechamento_snapshot. Revisar necessidade por consumidor antes de restringir.
- Defaults de postgres em public ainda concedem privilégios amplos a anon/authenticated/service_role em tabelas, sequências e funções. Defaults são específicos do criador.
- Migration 143 FDR Liga declara grants para service_role e bloqueia anon/authenticated na tabela, view e RPC. A view também depende dos privilégios das tabelas consultadas.
- Advisor: search_path mutável em fn_eh_tabela_cobranca_consignavel e fn_eh_cobranca_consignavel_por_valor, ambas SECURITY INVOKER.
- PostgreSQL 17.6; tamanho do banco: 129 MB, não equivalente ao tamanho do dump.
- Storage: zero buckets e objetos no catálogo consultado; revalidar antes da implantação.
- Configuração visual de schemas expostos na Data API não foi inspecionada.

## Riscos e critérios para mudanças

1. Migrations 127 (Liga), 137 (Promessa) e 140 (Elegível) concedem execução das RPCs, mas dependem dos defaults para acesso de service_role às tabelas/views. schema.sql base também não declara grants. Produção atual possui acesso; risco é reconstrução sem defaults.
2. database/INTEGRACAO.md recomenda GRANT ALL em todas as tabelas/sequências e EXECUTE em todas as funções para anon/authenticated/service_role, além de defaults amplos. Reexecutar após migrations restritivas pode reabrir RPCs. Corrigir o guia; não usar o bloco como solução genérica.
3. angry-man consulta lojas, consultores, produtos e periodos via anon + RLS. Revogação indiscriminada pode interrompê-lo.
4. Definir matriz objeto × consumidor × papel × operação, preservar analíticos acessíveis apenas pelo servidor e manter service_role fora de Electron/web.
5. Usar nova migration numerada; migrations aplicadas são imutáveis. Novos objetos precisam declarar grants/revokes e RLS na própria migration.
6. Avaliar ordem completa de bootstrap: correção no final não resolve necessariamente consultas de migrations anteriores. Testar reconstrução sem defaults e acessos permitidos/negados.
7. Fazer backup verificável e ensaio de restauração antes das alterações relevantes.

## Backup proposto, ainda não operacional

Plano Free/Nano consta do histórico; faturamento e backups disponíveis precisam de confirmação. A documentação recomenda exportações via CLI e cópias externas para Free. Pro oferece backups diários com sete dias acessíveis; PITR é adicional pago com compute elegível. Plano pago não substitui cópia independente.

Fontes:
- https://supabase.com/docs/guides/platform/backups
- https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore

Proposta para decisão:
- Dump lógico diário e antes de migrations, alterações de permissões ou cargas de alto impacto.
- Incluir dados, schema, funções, triggers, policies, ACLs, sequências, papéis necessários e histórico de migrations; validar cobertura real da ferramenta. CSV não é backup completo.
- Garantir consistência dos dados. Dumps separados de roles/schema/data não formam automaticamente um único snapshot; evitar DDL durante coleta e avaliar janela/snapshot compartilhado.
- Preservar versões de código, Edge Functions e inventário de configurações separadamente. Guardar segredos/chaves de forma segura, sem Git/logs; avaliar material criptográfico necessário à recuperação.
- Criptografar antes de enviar para destino externo controlado pela organização, com acesso restrito e proteção contra exclusão/sobrescrita. Não guardar dumps no Git.
- Retenção inicial sugerida: sete diários, quatro semanais e três mensais; ajustar após medir volume/custo.
- Meta proposta de perda máxima: 24 horas mais duração da coleta. Prazo de recuperação depende de ensaio medido; não há SLA validado.
- Manifesto com projeto, data, versão PostgreSQL, escopo, resultado e SHA-256 dos arquivos finais. Hash garante detecção de alteração, não restauração.
- Testar restauração isolada inicialmente e periodicamente, com contagens, constraints, grants/RLS e fluxos de leitura/importação de teste; desativar efeitos externos nesse ambiente.
- Monitorar falhas e idade do último backup. Preferir executor estável; máquina local precisa estar ligada.
- Storage exige cópia separada dos arquivos quando usado: dump do banco contém metadados, não objetos.
- Procedimento precisa cobrir Auth/Storage, extensões, roles e configurações necessárias conforme o guia oficial.

## Próximas decisões e limitações

Confirmar plano/backups no Dashboard; escolher destino, executor, responsável, retenção e metas; validar credencial PostgreSQL segura e ferramenta compatível com PostgreSQL 17; executar primeiro backup e restauração isolada; então fechar plano de grants.
Chave service_role da API não é senha PostgreSQL. Não inserir credenciais em documentação.
Neste host, command -v encontrou docker no WSL, mas não pg_dump, psql ou supabase no PATH; daemon não verificado. Nenhuma ferramenta instalada.
Registro local ainda sem commit/push. Nenhum backup novo, restore ou agendamento foi executado. Não tratar a proposta como proteção operacional.
