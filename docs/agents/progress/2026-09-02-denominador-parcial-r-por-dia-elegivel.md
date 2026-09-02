# 2026-09-02 — R$/dia elegível dividia pelo mês inteiro no mês em curso

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/loaders.py`, `app.py`,
`src/dashboard/tabs/gestao_consultores.py`, `tests/test_loaders_vinculos.py`,
`tests/test_tabs_gestao_presets.py`
**Commit(s):** (não commitado)

## Problema observado

O usuário pediu para verificar se o card **R$ por dia elegível**
(Performance do time) estava condizente. Estava, mas só em competência
fechada.

`_dias_uteis_competencia` devolvia **todos** os dias úteis do mês e
`cobertos` contava dias de vínculo até o fim do mês — **inclusive os que
ainda não aconteceram**. O numerador (produção paga) só tem o que já
ocorreu. Medido no banco em 02/09/2026:

| Competência | Card | Conta correta |
|---|---|---|
| 09/2026 (1 de 21 DU com dado) | R$ 128,28 | **R$ 2.693,82** |
| 08/2026 (fechada) | R$ 3.906,06 | R$ 3.906,06 |

O erro é exatamente `DU_total / DU_decorridos` e diminui sozinho ao longo
do mês, o que faz o card "melhorar" sem ninguém vender melhor.

## O que foi feito

- `carregar_vinculos_consultores(mes, ano, ate=None)`: `ate` é a data de
  referência da apuração; dias úteis posteriores não entram em
  `DIAS_ELEGIVEIS`. Nova coluna `DU_DECORRIDOS` ao lado de
  `DU_COMPETENCIA` (o mês inteiro), para a UI dizer "2 de 21".
- `app.py` resolve `data_ref_apuracao` do **último dia com dado**
  (`df["DATA"].max()`) — a mesma referência que já alimenta
  `du_decorridos` — e passa ao loader.
- Cards passam a rotular "de N DU decorridos" no mês em curso; o
  `R$ por dia elegível` ganha `help` dizendo que os dois lados param na
  mesma data e que amostra curta oscila.

## Decisões não óbvias

- **Última data com dado, não `today`** — validou-se sozinho: em
  02/09/2026 o ETL só tinha trazido 01/09. Com `today` o denominador
  teria 2 DU contra produção de 1, subestimando pela metade
  (R$ 1.346,91 em vez de R$ 2.693,82).
- **Corte por DIA, nunca proporcional** — quem foi admitido depois da
  referência fica com zero dias, não com fração. Se tiver produção paga
  (pagamento tardio de contrato de outra loja, casos Victor/Iluara), cai
  no diagnóstico de *produção sem vínculo*, que é onde esse caso deve
  aparecer.
- **`DU_COMPETENCIA` manteve o significado** (DU do mês) e o decorrido
  entrou como coluna nova. Mudar o sentido da coluna existente quebraria
  a leitura de quem já a consome.
- **`ate` entra na chave de cache** — avançar o dia recarrega em vez de
  servir o denominador de ontem.
- **Competência fechada não muda nada**: `ate` posterior ao fim do mês
  não trunca. A série de tendência (só competências fechadas) segue
  chamando o loader sem `ate`.

## Pendências / follow-ups

- [ ] A sub-visão **Critérios** com `METRICA_PROD_DIA` usa o mesmo
      `df_vinculos` e agora herda a truncagem — correto quando o período
      é a competência, mas com **atalho de período personalizado** o
      denominador continua sendo o da competência, não o do intervalo
      escolhido. Divergência anterior a esta mudança; decidir se o
      intervalo customizado deve calcular o próprio denominador.
- [ ] O card "Produção paga" exclui produção órfã (`dias = 0`), então
      não bate com a produção das outras abas quando há órfã. Hoje são
      0 pessoas em 08 e 09/2026 — sem efeito prático, mas estrutural.

## Referências

- Entrada anterior desta sessão:
  [2026-09-02-card-dias-elegiveis-media-por-colaborador.md](2026-09-02-card-dias-elegiveis-media-por-colaborador.md)
- Convenção do DU decorrido: `src/shared/dias_uteis.py`,
  `kpis/gerais.py` (`media_du_consultor`), migration 091.
