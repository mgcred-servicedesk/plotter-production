# PROBLEMA PRINCIPAL: O dashboard está “falando tudo ao mesmo tempo”

Hoje todos os blocos competem pela atenção:

- muitos cards com mesmo peso visual;
- muitas cores simultâneas;
- muitos números absolutos;
- seções extensas;
- gráficos e tabelas densos;
- ausência de hierarquia narrativa.

Quando tudo é importante, nada é importante.

O usuário abre e vê:

- total pago;
- em análise;
- cancelados;
- média loja;
- média consultor;
- pontos efetivos;
- metas por produto;
- emissões;
- regiões;
- heatmap;
- tabelas.

Mas não fica claro:

> “qual é o principal problema hoje?”

Esse deveria ser o foco principal.

## A ESTRUTURA IDEAL DE NARRATIVA

O dashboard deveria seguir uma ordem narrativa:

### BLOCO 1 — ONDE ESTAMOS

Visão atual consolidada.

Responder:

- Quanto já realizamos?
- Quanto falta?
- Qual o percentual da meta?
- Qual o principal gargalo?

Hoje: Você tem isso distribuído em muitos cards.

**Melhor:** Concentrar em 3 KPIs principais no topo:

| KPI 1 — Realizado acumulado | KPI 2 — % da meta atingida | KPI 3 — Gap para meta |
|----------------------------|----------------------------|-----------------------|
| R$ 9,45M                   | 61,9%                      | R$ 5,8M faltantes     |

Esses três devem ser grandes e dominantes.

Hoje o “Total Pago” é visualmente relevante, mas “Pontos Efetivos” também compete.

👉 **Sugestão:**

- aumentar fonte dos 3 KPIs principais;
- remover mini-informações secundárias do topo;
- destacar o gap.

**Visual recomendado:**
- fonte 36~42 nos KPIs;
- subtítulo 12~14;
- indicador de status: 🔴 Crítico 🟡 Atenção 🟢 Saudável

### O “EM ANÁLISE” e “CANCELADOS” precisam virar indicadores de impacto, não só volume

Hoje:
- Em análise = R$ 1,5M
- Cancelados = R$ 5,4M

Mas falta responder: isso é bom ou ruim para a meta?

**Exemplo melhor:**

**Em análise:**
> “Se converter 35%, adiciona R$ 526 mil ao resultado.”

**Cancelados:**
> “Cancelamentos consumiram 36% da meta mensal.”

Isso gera leitura estratégica.

Hoje os números existem, mas não existe interpretação do impacto.

### O DASHBOARD PRECISA DE UM “FAROL EXECUTIVO”

Hoje não existe um resumo visual que diga:

> “Estamos no ritmo certo?”

Você mostra “meta diária”, mas isso está diluído.

**Crie um bloco de status:**

| Ritmo Atual vs Ritmo Necessário |      |
|--------------------------------|------|
| Ritmo atual:                   | R$ 609 mil/dia |
| Ritmo necessário:              | R$ 953 mil/dia |
| Desvio:                        | -36% |

Visual tipo velocímetro/barra: 🔴 Abaixo do ritmo

Esse é o coração da narrativa “para onde estamos indo”.

### “PARA ONDE ESTAMOS INDO” PRECISA DE PROJEÇÃO MAIS VISUAL

Hoje você tem projeção em números.

Mas projeção precisa ser vista como tendência:

**Exemplo:**

#### Projeção de Fechamento

| Meta:      | R$ 15,2M |
|------------|----------|
| Projeção:  | R$ 12,8M |

Barra horizontal:
`████████░░░░ 84% da meta`

**Mensagem automática:**
> “Mantido o ritmo atual, fecharemos 16% abaixo da meta.”

Isso conta a história.

Hoje o usuário precisa interpretar números manualmente.

### “PARA ONDE DEVEMOS IR” ESTÁ AUSENTE

Esse é o ponto mais importante.

O dashboard precisa responder:
> “onde agir agora?”

Hoje há análises por produto e região, mas não há priorização.

**Deveria existir um quadro:**

#### Prioridades de Ação

1. **Consignado**
   - Maior gap financeiro: R$ 4,0M
2. **CLT**
   - Baixo atingimento: 42%
3. **Região Robson**
   - Pior evolução: -5,6%

Isso transforma análise em ação.

Sem isso, o dashboard informa, mas não direciona.

### EXCESSO DE CORES

Hoje há:
- azul;
- vermelho;
- verde;
- laranja;
- cinza;
- bordas coloridas;
- gráficos coloridos.

Isso gera ruído.

**Recomendo reduzir para:**
**Paleta:**
- Azul: neutro
- Verde: acima da meta
- Amarelo: atenção
- Vermelho: crítico
- Cinza: contexto

Hoje há muitos cards com borda vermelha sem contexto claro.

Use cor somente para status, nunca como decoração.

### HIERARQUIA VISUAL DOS CARDS

Hoje os cards têm peso semelhante.

Isso dificulta perceber:
- o que é principal;
- o que é secundário.

**Reorganização:**

| Linha 1: | Realizado | % Meta | Gap |
|----------|-----------|--------|-----|
| Linha 2: | Projeção  | Ritmo  | Conversão análise |
| Linha 3: | Produtos críticos | Regiões críticas | Consultores críticos |

A ordem visual deve seguir: **resultado → tendência → ação**

Hoje segue: **resultado → detalhes → detalhes → detalhes**

### TABELAS DEMAIS, AÇÃO DE MENOS

As tabelas de lojas/regiões são úteis, mas são densas demais para leitura executiva.

**Exemplo:** As tabelas por região:
- ocupam muito espaço;
- exigem leitura detalhada;
- quebram a narrativa.

**Melhor:** Mostrar apenas:
- Top 3 melhores regiões
- Top 3 piores regiões

E permitir expandir detalhes.

### O HEATMAP ESTÁ BOM, MAS FALTA SIGNIFICADO

O mapa de calor é visualmente bom.

Mas precisa de uma conclusão automática:
> “Região Jacqueline lidera em Consignado, enquanto Robson apresenta menor desempenho em CLT.”

Sem interpretação, vira apenas visualização.

### TIPOGRAFIA: TAMANHOS ESTÃO PEQUENOS PARA O QUE É CRÍTICO

Hoje:
- números importantes pequenos;
- subtítulos próximos do mesmo tamanho;
- muita informação secundária visível.

**Sugestão:**
- **KPI principal:** 36-42px
- **KPI secundário:** 24-28px
- **texto auxiliar:** 12-14px
- **labels:** 11-12px

Isso melhora leitura instantânea.

### CRIAR “MENSAGENS EXECUTIVAS”

Essa é a maior melhoria.

No topo do dashboard:

#### Resumo Executivo do Dia

> Estamos com 61,9% da meta atingida, porém 16% abaixo da projeção necessária. Consignado e CLT concentram o maior déficit, enquanto FGTS supera a meta. A prioridade deve ser elevar produção nas regiões Robson e Sandra para recuperar R$ 1,2M do gap.

Isso transforma números em narrativa.

### RESUMO DAS MUDANÇAS MAIS IMPORTANTES

Se eu priorizasse:

**PRIORIDADE 1**
- Criar um Resumo Executivo automático

**PRIORIDADE 2**
- Reduzir KPIs do topo para 3 indicadores principais

**PRIORIDADE 3**
- Adicionar bloco “Prioridades de Ação”

**PRIORIDADE 4**
- Reduzir tabelas e detalhamento visual inicial

**PRIORIDADE 5**
- Padronizar cores por status

**PRIORIDADE 6**
- Melhorar hierarquia tipográfica

**Resultado esperado:**

O dashboard deixa de ser:
> “um painel de números”

e passa a ser:
> “um painel de decisão”


🧠 PRINCÍPIO DO NOVO DASHBOARD

O layout vai seguir esse fluxo:

1. Onde estamos → 2. Para onde estamos indo → 3. Onde agir agora → 4. Exploração detalhada

## WIREFRAME (ESTRUTURA COMPLETA)

### 1. HEADER — CONTEXTO (fixo no topo)

[ LOGO ]   Dashboard de Performance Comercial

Período: Abril 2026 | Última atualização: 23/04 | DU: 18/22

[Filtros recolhidos por padrão]

👉 Mudança:
- esconder filtros (sidebar colapsada)
- foco total na leitura

### 2. BLOCO 1 — 📍 ONDE ESTAMOS (STATUS ATUAL)

> **RESUMO EXECUTIVO**
>
> Estamos com 61,9% da meta atingida, abaixo do ritmo necessário em -16%. Consignado e CLT puxam o resultado para baixo.

**KPIs PRINCIPAIS (linha dominante)**

| REALIZADO | % META | GAP |
|-----------|--------|-----|
| R$ 9,45M | 61,9% 🔴 | -R$ 5,8M |

**KPIs DE CONTEXTO (linha secundária)**

| EM ANÁLISE | CANCELADOS | TICKET MÉDIO |
|------------|------------|--------------|
| R$ 1,5M | R$ 5,4M | R$ 5.2K |
| Potencial: +R$ 500K | Impacto: -36% da meta | |

👉 Aqui entra interpretação (muito importante)

### 3. BLOCO 2 — 📈 PARA ONDE ESTAMOS INDO (TENDÊNCIA)

**Ritmo vs Meta**

**RITMO ATUAL vs NECESSÁRIO**

- Atual: `██████░░░░` R$ 609K/DIA
- Necessário: `██████████` R$ 953K/DIA

Status: 🔴 Abaixo do ritmo (-36%)

**Projeção de Fechamento**

**PROJEÇÃO DO MÊS**

- Meta: R$ 15,2M
- Projeção: R$ 12,8M

`████████░░░░░░░░` 84%

→ Mantido o ritmo, fecharemos 16% abaixo da meta

**Evolução (gráfico simplificado)**

Linha: Realizado acumulado vs meta acumulada
(Só 1 gráfico principal — remover excesso)

### 4. BLOCO 3 — 🎯 PARA ONDE DEVEMOS IR (AÇÃO)

🔥 Esse é o bloco mais importante do dashboard

**Prioridades automáticas**

> **PRIORIDADES DE AÇÃO**
>
> 1. **CONSIGNADO**
>    - Gap: -R$ 4,0M
> 2. **CLT**
>    - Baixo atingimento: 42%
> 3. **REGIÃO ROBSON**
>    - Queda: -5,6%

**Produtos (ranking simplificado)**

| Produto | % Meta | Status |
|---------|--------|--------|
| FGTS | 177% | 🟢 |
| CNC | 64% | 🟡 |
| Consignado | 48% | 🔴 |
| CLT | 42% | 🔴 |
| Saque | 62% | 🟡 |

👉 Sem excesso de gráficos aqui — direto ao ponto

**Regiões (Top / Bottom)**

| TOP 3 REGIÕES | PIORES 3 REGIÕES |
|---------------|------------------|
| Jacqueline 🟢 | Robson 🔴 |
| Glenda 🟢 | Sandra 🔴 |
| ... | ... |

### 5. BLOCO 4 — 🔍 EXPLORAÇÃO (DETALHAMENTO)

Aqui você mantém seu conteúdo atual, mas reorganizado

Tabs:
`[ Produtos ] [ Regiões ] [ Consultores ] [ Lojas ]`

Dentro de cada aba:
- gráficos comparativos
- heatmap
- tabelas completas

👉 Agora isso vira exploração, não poluição inicial

### 6. BLOCO OPCIONAL — ALERTAS

⚠ **ALERTAS**

- Cancelamentos acima de 25%
- CLT abaixo de 50% da meta
- Ritmo diário insuficiente há 5 dias

## 🎨 DIRETRIZES VISUAIS

**Cores (padronização)**
- Verde → acima da meta
- Amarelo → atenção (60–90%)
- Vermelho → crítico (<60%)
- Azul → neutro

👉 remover bordas coloridas aleatórias

**Tipografia**
- KPI principal: grande (36+)
- % meta: destaque visual
- textos auxiliares: pequenos e leves

**Espaçamento**
- mais respiro entre blocos
- menos cards grudados
- menos "caixinhas"

## 🚫 O QUE REMOVER OU REDUZIR

- múltiplos gráficos redundantes
- tabelas gigantes na tela inicial
- excesso de indicadores simultâneos
- cores decorativas

## 🧠 RESUMO VISUAL FINAL

```
[ HEADER ]

[ RESUMO EXECUTIVO ]

[ KPIs PRINCIPAIS ]

[ KPIs CONTEXTO ]

[ RITMO + PROJEÇÃO ]

[ PRIORIDADES DE AÇÃO ]

[ PRODUTOS / REGIÕES RESUMO ]

[ TABS DE DETALHAMENTO ]
```