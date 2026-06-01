# 2026-06-01 — Portabilidade herda pts do CONSIG por banco + fix mensagem "Meta atingida" no período encerrado

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/loaders.py`, `src/dashboard/ui/kpi_cards_reforma.py`, `docs/agents/business-rules.md`, `scripts/diagnostico/`
**Commit(s):** (pendente)

## Objetivo

1. Bloco "Para Onde Estamos Indo" exibia "Meta atingida" no fim do mês mesmo quando a meta não foi atingida (`du_restantes == 0` forçava `media_necessaria = 0` e caía no `else` errado).
2. Total de pontos do dashboard em 05/2026 (`25.028.942`) não batia com o cálculo manual do usuário (`25.076.375`) — diferença de `47.433`.

## O que foi feito

- **kpi_cards_reforma.py**: refatorada a derivação das mensagens. `meta_atingida = total_vendas >= meta_mix` virou a fonte da verdade, e `periodo_encerrado = du_restantes <= 0` passou a ser estado explícito. Quatro ramos: sem meta / meta atingida / período encerrado sem atingir / em curso com gap. `msg_fechamento` flexiona "Fechamos" (passado) vs "Fecharemos" (futuro) conforme o período.
- **loaders.py**: adicionada constante `_PORTAB_BANCO_TO_CONSIG` mapeando `BANCO` → `CONSIG_<banco>` (`BMG`, `C6 BANK`, `ITAU` e variações). Após o lookup de `PONTOS`, contratos com `categoria_codigo == 'PORTABILIDADE'` recebem override do multiplicador via `mapa_pontos[CONSIG_<banco>]`. Bancos não mapeados ficam com 0 (visíveis no diagnóstico).
- **business-rules.md**: documentada a regra de Portabilidade.
- **scripts/diagnostico/**: criados `verificar_pontos_maio.py`, `inspecionar_portabilidade.py`, `inspecionar_consig_banco.py` para validar/reproduzir.

Validação: total de pontos 05/2026 passou de `25.028.942` para `25.076.375` (= cálculo manual do usuário, diff 0). Zero contratos com `VALOR>0` e `pontos=0` agora.

## Decisões não óbvias

- **Resolver Portabilidade em código, não via tabela `pontuacao`** — a migration 013 (alias categoria→categoria) explicitamente deixou Portabilidade fora porque o diferencial é `BANCO` (granularidade maior que categoria). Estender a migration 013 exigiria suporte a alias bank-conditional. Override em loaders é o mais leve e funciona retroativamente para todos os meses históricos sem depender de inserção manual em `pontuacao`.
- **`CONSIG_PRIV` excluído do mapping** — usuário confirmou que Privado é produto distinto e não se aplica a portabilidade; só BMG/C6/Itaú entram.
- **Bancos não mapeados ficam com 0** — preferi falhar visível (diagnóstico mostra) em vez de adotar fallback silencioso para qualquer CONSIG default. Se surgir banco novo, alguém vai notar.
- **`categoria_codigo` mantida como `'PORTABILIDADE'`** — identidade do produto não muda; só a pontuação herda. Isso preserva o comportamento dos relatórios que agrupam por categoria.

## Pendências / follow-ups

- [ ] Confirmar com operação se há outros bancos de portabilidade (Bradesco, Pan, etc) que devem entrar no mapping.
- [ ] Avaliar se faz sentido remover a flag `categoria_pts_id` da migration 013 para PORTABILIDADE (atualmente NULL, ok), ou explicitar via comentário que o alias por banco é resolvido em app-side.
- [ ] Testes em `tests/test_kpi_produtos.py` estão obsoletos (esperam coluna `Pontos` que não existe mais) — não relacionado a esta task, mas vale atualizar.

## Referências

- Conversa: usuário identificou diferença de `47.433` pontos em 05/2026.
- Docs consultados: [docs/agents/business-rules.md](../business-rules.md), [database/migrations/013_categoria_pts_alias.sql](../../../database/migrations/013_categoria_pts_alias.sql), [docs/agents/progress/2026-05-12-categoria-pts-alias.md](2026-05-12-categoria-pts-alias.md).
