# 2026-06-26 — Padronização de datas para dd/mm/aaaa

## Contexto
Pedido: auditar o dashboard e garantir que toda data exibida fique em
dd/mm/aaaa (usuário relatou ver datas em UTC / com milissegundos).

## Auditoria (conclusão)
A camada de exibição já estava **quase toda** em dd/mm/aaaa: toda coluna
de data exibida em tabela passa por `exibir_tabela` →
`_exibir_dataframe` → `_formatar_dataframe_br`, que formatava colunas
`datetime64` (inclusive tz-aware) para dd/mm/aaaa. Demais pontos
(header, cards de pagamentos online) formatam à mão.

Levantamento empírico dos dtypes reais (carregando os loaders):
- `contratos_pagos.DATA_CADASTRO` vinha como **texto ISO** `'2026-06-19'`
  (str), enquanto em `em_analise`/`cancelados` a mesma coluna era
  `datetime64`. Hoje não era exibida (as tabelas de pagos usam `DATA`),
  mas é inconsistência de fonte.
- `CREATED_AT` / `IMPORTED_AT` são `datetime64[us, UTC]` (UTC + micros);
  só aparecem já formatados (header/cards).

Gap estrutural: `_formatar_dataframe_br` **só** tratava `datetime64`.
Qualquer coluna de data que chegasse como **string ISO/UTC** escapava —
causa-raiz do que o usuário via.

## Mudanças
1. `src/dashboard/components/tables.py`: `_formatar_dataframe_br` agora
   também detecta colunas-texto de data e as converte para dd/mm/aaaa.
   Detecção **por valor, não por nome** (`_coluna_texto_e_data`), com
   dois filtros anti-falso-positivo: (a) todos os valores casam o padrão
   ISO `^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}|$)`; (b) todos convertem para
   data válida via `pd.to_datetime` (descarta códigos como `1234-56-78`).
2. `src/dashboard/loaders.py` (`carregar_contratos_pagos`): normaliza
   `DATA_CADASTRO` para `datetime64` (consistência com os outros loaders).
3. `tests/test_ui_tables.py` (novo): 7 casos cobrindo datetime64,
   tz-aware/UTC, texto ISO, texto ISO com hora/UTC, nulos→"", texto
   não-data intacto e código-parecido-com-data intacto.

## Não óbvio / aprendizados
- **Gotcha pandas**: nesta versão, colunas de string têm dtype `str`
  (StringDtype), **não** `object`. O guard inicial `serie.dtype != object`
  rejeitava as datas-texto (e fazia os testes "não-data" passarem pelo
  motivo errado). Removido o guard de dtype — o `isinstance(v, str)` +
  validade do `to_datetime` filtram com segurança.
- Padrão novo sinalizado: detecção de data por valor no formatador
  central (defense-in-depth — cobre qualquer coluna de data futura que
  chegue como texto, sem depender de o loader tipar).

## Pendências / decisões do usuário (não alteradas unilateralmente)
- `ui/charts.py`: hovertemplates usam `%{x|%d/%m}` (sem ano).
- `tabs/evolucao.py:40`: `strftime("%d/%m")` (anotação, sem ano).
- `feriados_mgmt.py`: `strftime("%A")` → dia da semana em inglês
  (locale), não é formato de data mas é inconsistente.
- Caminho AG Grid (`_build_aggrid_options`) não formata datas; hoje
  **inerte** (nenhum caller usa `usar_aggrid=True`).
