# Reconquista v2 — Contrato de importação (ETL)

Especificação para alimentar a base de Reconquista v2. Vale tanto para o
script local (`scripts/importar_reconquista.py`, neste repo) quanto para o
ETL recorrente no **angry-man**.

## Modelo

- **Export único**, aba `Export`, **1 linha por cliente** (`co_adesao`),
  já classificado em `de_status_reconquista`
  (EFETIVADA / PROMESSA / SEM RECONQUISTA).
- A cada carga a base é **truncada e realimentada** (foto atual). Não é
  cumulativo — o arquivo mais recente substitui tudo.
- A apuração mensal (por `dt_fim_relacionamento`, defasagem de 1 mês) e os
  KPIs ficam no **dashboard**; o ETL só carrega a foto.

## Fluxo

```
1. Detectar o arquivo de Reconquista (export com as 22 colunas abaixo).
2. Ler a aba `Export` (pular linhas de rodapé: co_adesao/status vazios).
3. Para cada linha montar o objeto JSON (mapeamento abaixo):
     - cod_bmg = int(no_franquia.split(" - ")[0])  (prefixo numérico)
     - datas em 'AAAA-MM-DD' (ou null)
     - dedup por co_adesao (manter a 1ª ocorrência)
     - NÃO enviar nu_matricula (LGPD)
4. Chamar a RPC:  fn_importar_reconquista(p_rows := <array de objetos>)
     - role service_role/admin (a função é REVOKE de PUBLIC)
     - TRUNCATE + INSERT atômicos; resolve loja_id e consultor_id no banco
5. Logar o retorno: (inseridos, sem_loja, sem_consultor).
     - sem_loja  > 0 → revisar lojas.cod_bmg
     - sem_consultor é tolerável: consultor_nome bruto é sempre persistido.
```

## Mapeamento coluna do arquivo → chave JSON da RPC

| Coluna (xlsx)            | Chave JSON              | Obs |
|---|---|---|
| `co_adesao`             | `co_adesao` (BIGINT)    | obrigatório |
| `de_status_reconquista` | `status`                | obrigatório, ∈ {EFETIVADA, PROMESSA, SEM RECONQUISTA} |
| `dt_fim_relacionamento` | `dt_fim_relacionamento` | DATE — referência da apuração |
| `dt_macica`             | `dt_macica`             | DATE |
| `dt_dna`                | `dt_dna`                | DATE |
| `dt_producao`           | `dt_producao`           | DATE |
| `de_subproduto`         | `subproduto`            | |
| `no_franquia`           | `no_franquia` + `cod_bmg` | cod_bmg = prefixo numérico |
| `no_consultor`          | `consultor_nome`        | nome **completo** |
| `no_gerente_regional`   | `gerente_regional`      | |
| `no_gerente_loja`       | `gerente_loja`          | |
| `no_coordenador_loja`   | `coordenador_loja`      | |
| `de_banco_origem`       | `banco_origem`          | |
| `de_banco_destino`      | `banco_destino`         | |
| `vl_saldo_contabil`     | `saldo_contabil`        | NUMERIC |
| `qt_dias_atraso`        | `dias_atraso`           | INT |
| `de_faixa_atraso`       | `faixa_atraso`          | |
| `de_tipo_pagamento`     | `tipo_pagamento`        | |
| `qt_fim_relacionamento` | `qt_fim_relacionamento` | INT |
| `de_link_aceite`        | `link_aceite`           | uso analítico |
| `flag_elegibilidade`    | `flag_elegibilidade`    | ELEGIVEL / NAO ELEGIVEL; opcional (ausente → NULL = ELEGIVEL no dashboard) |
| `nu_matricula`          | — (descartar)           | **LGPD: não armazenar** |

## Referência de implementação

`scripts/importar_reconquista.py` neste repo já implementa todo o contrato
acima (`montar_rows` + chamada da RPC). O angry-man pode portar a mesma
lógica para a sua estrutura de ETL.

## Resolução no banco (não fazer no ETL)

A RPC `fn_importar_reconquista` resolve internamente:
- `loja_id` via `lojas.cod_bmg` com `COALESCE(sucessora_id, id)`;
- `consultor_id` via `consultores.nome ILIKE <nome completo>` + loja.

O ETL só envia `cod_bmg` e `consultor_nome` — não precisa resolver FKs.
