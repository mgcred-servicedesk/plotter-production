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
