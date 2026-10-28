# 2026-10-27 — Handoff da refatoração de Performance

**Agente:** Devin
**Tipo:** research / handoff
**Arquivos tocados:** apenas esta entrada de progresso
**Commit(s):** —

## Objetivo

Retomar a aba Gestão > Performance do time na ordem confirmada pelo usuário:
correções e regressões; metas individuais/MIX/ritmo; consistência/IPV/amplitude
do time; envelhecimento da fila e conversão por consultor.

## O que foi feito

- Inspecionadas as alterações locais em `kpis/gestao.py`,
  `kpis/produtividade.py`, `tabs/gestao_consultores.py`, `ui/charts.py`
  e três arquivos de testes; nenhuma delas foi sobrescrita.
- Os 179 testes relacionados a produtividade/gestão passaram; Ruff em
  `src/ app.py` passou. Suíte completa: 1761 passaram e 5 falharam, em
  `test_kpis_gerais.py`, `test_loaders_cache_version.py` e testes de
  navegação de Reconquista (3); não são falhas dos testes de gestão.
- `git diff --check` indicou whitespace em quatro linhas dos testes locais.
  Não houve QA visual nem validação com dados reais.
- Detectada lacuna entre a correção já iniciada na série e o callback
  `_carregar_competencia_gestao` em `app.py`: quando a competência não tem
  pagamentos, ele devolve vínculos vazios sem carregar o ledger.

## Decisões não óbvias

- O usuário confirmou que os cinco grupos das alterações locais são o
  escopo da primeira etapa; não há outra lista.
- A meta mensal individual permanece integral mesmo em mês de admissão
  ou desligamento. Isso não decide automaticamente como calcular dias
  futuros elegíveis para o ritmo necessário.
- Para a quarta etapa, o usuário escolheu (1) envelhecimento da fila
  atual de contratos em análise e (2) conversão por coorte de cadastro.
  A taxa consolidada deve usar uma janela de observação de **30 dias
  corridos**, apenas para coortes com 30 dias completos.
- Não usar `pagos no mês / em análise hoje`: pagamento e cadastro
  pertencem a coortes diferentes. O pipeline atual expõe a fila
  remanescente e a base de pagos por mês de pagamento; a fonte da
  coorte completa de cadastros exige trabalho na camada de dados.
  Envelhecimento da fila atual não equivale ao histórico de transições
  entre estados (não há série de snapshots desse status na aba).

## Pendências / follow-ups

- [ ] Claude deve orquestrar separadamente dados/regras, testes e UI,
  sem dois agentes editarem os mesmos arquivos. Entrada sugerida:
  `app.py`, `src/dashboard/loaders.py`, `src/dashboard/kpis/gerais.py`,
  `src/dashboard/kpis/produtividade.py`,
  `src/dashboard/kpis/prestamista.py`, `src/dashboard/tabs/gestao_consultores.py`
  e testes correspondentes. Revisão Codex das decisões cross-domínio.
- [ ] Etapa 1: revisar os cinco grupos das alterações locais e corrigir o
  callback de competência sem pagamentos antes de validar a série.
- [ ] Etapa 2: usar metas CONSULTOR e loja principal; ausência de meta
  explícita; `avaliar_regra_mix` para pendências e falta; definir os dias
  futuros elegíveis quando o vínculo não tem término conhecido.
- [ ] Etapa 3: reconciliar vínculo e meta por mês; incluir elegíveis sem
  produção na amplitude; reutilizar contagens e razão do IPV sem converter
  ausência de elegíveis em zero.
- [ ] Etapa 4: definir a base completa de cadastrados e data de corte
  observável para a coorte madura; distinguir pagas em até 30 dias,
  pendentes e canceladas. Medir idade da fila atual desde
  `DATA_CADASTRO`, com data de referência e faixas explícitas.
- [ ] Rodar regressões (sem vínculo, mês sem venda, transferência,
  ausência de meta, mês parcial e limite de 30 dias), Ruff e type checker
  se configurado; realizar QA desktop/mobile e registrar o resultado.
- [ ] Tratar as cinco falhas da suíte completa e o whitespace em frente
  própria ou no encerramento, sem associá-los indevidamente à etapa 1.

## Patterns criados ou atualizados

Nenhum.

## Referências

- Docs consultados: [collaboration.md](../collaboration.md),
  [rpi-workflow.md](../rpi-workflow.md),
  [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md) e [rls.md](../rls.md).

## Status dos follow-ups (2026-10-28)

> Seção anexada ao fim (append-only): o texto acima é o handoff original e
> não foi alterado. Detalhes nas entradas
> [2026-10-27b](2026-10-27b-performance-etapa1-e-suite-verde.md) (Etapa 1) e
> [2026-10-28](2026-10-28-performance-etapa2-metas-mix-ritmo.md) (Etapa 2).

| Follow-up original | Status | Onde |
|---|---|---|
| Orquestrar dados/regras, testes e UI sem dois agentes no mesmo arquivo; revisão Codex | **Feito** (orquestração e posse exclusiva por arquivo nas duas rodadas). Revisão Codex **pendente** com o usuário: D1, bloqueio de meta incompatível, E1 e E2 | 27b, 28 |
| Etapa 1 — cinco grupos + callback de competência sem pagamentos | **Feito** (commit `0d73059`). Mês com base global vazia é lacuna com aviso, não R$ 0/dia | 27b |
| Etapa 2 — metas CONSULTOR/loja principal, ausência de meta, `avaliar_regra_mix`, dias futuros | **Feito** (não commitado). Inclui `VINCULO FUTURO` e motivo explícito de SEM META; dias futuros vão até o fim do mês | 28 |
| Etapa 3 — vínculo × meta por mês, amplitude com elegíveis sem produção, IPV sem zero inventado | **Parcial**. Existem, com teste: IPV por colaborador na Performance; `resumo_performance_time`, `consistencia_performance` e `comparar_historico_proprio`, ainda **não ligados** na aba. Contadores de `sem_vinculo` incluem `VINCULO FUTURO` | 28 |
| Etapa 4 — coorte de cadastro (30 dias corridos) e idade da fila | **Pendente** (não iniciada; exige trabalho na camada de dados) | — |
| Regressões, Ruff, type checker, QA desktop/mobile | **Parcial**. Regressões cobertas por teste: sem vínculo, mês sem venda, transferência, ausência de meta, mês parcial. O limite de 30 dias é da Etapa 4. Ruff limpo; não há type checker configurado. QA visual **pendente** | 27b, 28 |
| Cinco falhas da suíte e whitespace | **Feito**. As falhas eram de FDR Liga/`cache_version` e testes desatualizados; o whitespace era CRLF | 27b |

Suíte: 1761 ✓ / 5 ✗ (partida) → 1848 ✓ / 0 ✗ (27b) → 1870 ✓ / 9 ✗ (HEAD
`0d73059`) → **1912 ✓ / 0 ✗** (28).

### Follow-ups novos

- [ ] Mesma perda de estado em outros `return` antecipados de
  `_render_criterios` (data final ainda não escolhida, intervalo sem contrato,
  `tabela.empty`) — 27b.
- [ ] Último mês da janela da série indisponível: a variação compara os dois
  últimos presentes; falta definir a regra — 27b.
- [ ] CSV da Performance não exporta `VINCULO FUTURO`; com todo o escopo em
  `VINCULO FUTURO`, a aba diz "Nenhum colaborador dentro do corte" — 28.
- [ ] Pivô CONSULTOR com `fill_value=0` esconde a ausência de meta por loja
  (camada de dados) — 28.
- [ ] `tests/test_loader_fim_relacionamento_liga.py` é o único arquivo CRLF do
  repositório — 27b.
