# 2026-10-08 — Seguro Prestamista CNC (IPV)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `database/migrations/134_prestamista_cnc.sql`, `src/dashboard/kpis/prestamista.py`, `src/dashboard/loaders.py`, `src/dashboard/ui/kpi_cards_reforma.py`, `app.py`, `tests/test_kpis_prestamista.py`, `tests/test_loader_prestamista.py`, `docs/agents/business-rules.md`; angry-man: `src/services/import-prestamista-cnc.ts`, `src/services/import-registry.ts`, `src/lib/supabase.ts`, `supabase/functions/reconquista-rpc/index.ts`, `tests/unit/import-prestamista-cnc.test.ts`
**Commit(s):** —

## Objetivo

Novo acompanhamento do seguro Prestamista do CNC: IPV = Qtd Seguro /
Qtd Elegível, meta 80%, exibido abaixo dos Aceleradores e acima da
Reconquista, com visão por perfil.

## O que foi feito

- Migration 134: `prestamista_cnc` (por período, deny para anon/authenticated),
  `v_prestamista_cnc`, `fn_importar_prestamista_cnc` (set-based, apaga e
  recarrega o período), `prestamista_cnc_meta` + `obter_meta_prestamista_cnc`
  (fallback temporal), seed 10/2026 = 80% / 60%.
- Dashboard: loader com RLS da Reconquista, regra pura em `kpis/prestamista.py`,
  bloco com 3 cards (IPV, seguros ativos, faltam para a meta) e abas por nível.
- angry-man: card "Prestamista CNC" (período obrigatório), conferência com o
  rodapé "Total", RPC registrada no `RPC_ENDPOINT_MAP` e na whitelist da
  Edge Function `reconquista-rpc`.

## Decisões não óbvias

- **Por período, não foto única** (usuário) — arquivo é acumulado do mês;
  histórico dos meses fechados fica.
- **Consultor vê o próprio IPV** (usuário), sem tabela.
- **Meta em tabela por período** (usuário), com `faixa_alerta` junto: o
  amarelo (60%) acompanha a meta se ela mudar.
- **IPV = soma/soma, igual ao BI** — seguro em proposta não elegível (não
  ocorre em 10/2026) entraria no numerador; não filtramos para bater com a fonte.
- **Não cruza com `contratos`** — Adesão = num_proposta, mas loja/consultor
  vêm do arquivo (mesmo racional da Liga).
- **Import set-based** (jsonb_to_recordset + LATERAL) em vez do loop da 127:
  ~1000 linhas no Nano.
- **IPV indefinido é None, não NaN** — NaN caía no vermelho do semáforo
  (pego por teste antes do commit).

## Pendências / follow-ups

- [x] Migration 134 aplicada pelo usuário em 2026-10-08 (verificada: funções únicas, grants só postgres/service_role, deny anon/authenticated, meta 10/2026 = 0,80/0,60, fallback ok; import testado com ROLLBACK).
- [x] Edge Function `reconquista-rpc` v11 publicada (= v10 + `fn_importar_prestamista_cnc`).
- [x] angry-man 1.4.5 gerado (Setup + zip win-x64; bundle sem service_role). Não commitado.
- [ ] Distribuir o 1.4.5, importar o arquivo de 10/2026 e rodar a validação da 134 (esperado 950 / 231 / 93, 0 sem loja, 3 sem consultor).
- [ ] `tests/test_kpis_gerais.py::TestObterMediasPeriodo::test_cache_e_dict_com_as_chaves_de_medias_du_por_nivel` já falhava antes desta tarefa (não relacionado).

## Referências

- Molde: migration 127 (Liga da Reconquista) e 066 (config por período).
- Docs: [business-rules.md § Seguro Prestamista CNC](../business-rules.md)

## Adendo (mesma sessão) — analíticos e resumo

- Cruzamento do arquivo de 10/2026 com `contratos.num_proposta`: 713/950
  casam (632 CNC, 80 Super Conta, 1 Antecipação), todas pagas em 10/2026 —
  o arquivo é por **mês de pagamento**. As 237 sem casamento têm todas as
  Qtd = 0. Até 06/10, todo CNC pago está no arquivo; faltam 6 Super Conta
  de portabilidade com proposta de 9 dígitos (ADE do BI provavelmente
  difere). 184 pagos em 07/10 ficam para o próximo arquivo (corte).
- **Super Conta fica no IPV** (usuário): é produto CNC no banco; o 40,3%
  do BI já o inclui.
- Sub-aba **Prestamista** nos Analíticos (pendências + quebras + arquivo),
  coluna/filtro **Prestamista** em Propostas Pagas, pill no **Resumo
  Executivo** (escolhas do usuário).
- `QUEBRAS_POR_PERFIL` saiu da UI para `kpis/prestamista.py` (usada pelo
  card e pela sub-aba).
- Sabotagem do casamento texto×inteiro da ADE derrubou 8 testes.
- `test_kpis_gerais.py::TestLimparCacheKpis::test_limpar_cache_kpis_forca_recalculo`
  falhou 1 vez em 3 rodadas da suíte — intermitente, não relacionado.
