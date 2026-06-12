# Reconquista MG CRED — Plano de Migração e Integração

> ⚠️ **HISTÓRICO (v1 — superado).** Este documento descreve o **modelo
> antigo** de Reconquista (snapshots por envio + maciças + flags). Esse
> modelo foi **substituído pela v2** em 2026-06-12 (export único, 1 linha
> por cliente, classificação por `de_status_reconquista`, apuração mensal
> por `dt_fim_relacionamento` com defasagem de 1 mês).
>
> **Fonte de verdade da v2:**
> - Regras: [`docs/agents/business-rules.md` → Reconquista (v2)](agents/business-rules.md)
> - Decisões: [`docs/agents/progress/2026-06-12-reconquista-v2.md`](agents/progress/2026-06-12-reconquista-v2.md)
> - Código: migrations `028/029/030`, `scripts/importar_reconquista.py`,
>   `src/dashboard/loaders.py` (`carregar_reconquista`).
> - Remoção do v1: migration `031_reconquista_drop_v1.sql` (destrutiva).
>
> Mantido apenas como referência do que existiu. Não usar como guia de
> implementação.

**Versão:** 1.1  
**Data:** 2026-05-28  
**Projetos afetados:** `Numeros_venda` · `angry-man`  
**Banco de dados:** Supabase (PostgreSQL) — mesmas credenciais nos dois projetos

---

## Índice

1. [Contexto e Objetivo](#1-contexto-e-objetivo)
2. [Privacidade e LGPD — Decisões de design](#2-privacidade-e-lgpd--decisões-de-design)
3. [Fonte de dados](#3-fonte-de-dados)
4. [Pontes com o schema existente](#4-pontes-com-o-schema-existente)
5. [Migration 018 — Tabelas novas](#5-migration-018--tabelas-novas)
6. [Migration 019 — Views e função de exibição](#6-migration-019--views-e-função-de-exibição)
7. [Migration 020 — RPCs de importação](#7-migration-020--rpcs-de-importação)
8. [ETL — Especificação para o angry-man](#8-etl--especificação-para-o-angry-man)
9. [Dashboard — Especificação para o Numeros_venda](#9-dashboard--especificação-para-o-numeros_venda)
10. [Regras de negócio críticas](#10-regras-de-negócio-críticas)
11. [Checklist de implementação](#11-checklist-de-implementação)

---

## 1. Contexto e Objetivo

O **Projeto Reconquista MG CRED** é uma campanha periódica de retenção de clientes que possuem
contratos CNC (Crédito Novo ao Consumidor) em situação de inadimplência. A MG CRED recebe arquivos
Excel periodicamente com os clientes elegíveis para reconquista. Cada lote de envios é chamado de
**Maciça**.

**Meta:** Converter ao menos **30%** dos clientes da base de cada maciça
(coluna `FLAG_RECONQUISTA` passando de `0` para `1`).

**O que precisa ser feito:**
- Armazenar o histórico de snapshots de cada maciça no Supabase.
- Expor KPIs de reconquista no dashboard Streamlit (`Numeros_venda`).
- Criar RPCs para que o `angry-man` possa importar os arquivos Excel.

---

## 2. Privacidade e LGPD — Decisões de design

> ⚠️ **Esta seção deve ser lida antes de qualquer alteração no schema ou no ETL.**
> Decisões tomadas aqui não são bugs — são requisitos legais intencionais.

### 2.1 Dado não armazenado: CPF

**Decisão:** O CPF dos clientes **não é armazenado** em nenhuma tabela do banco de dados.

**Motivação:** Mitigação de risco de vazamento de dados pessoais sensíveis (LGPD — Lei
13.709/2018). O CPF é dado pessoal de identificação direta. Sua exposição em um banco
de dados acessível por múltiplos sistemas e usuários representa risco legal significativo.

**O que temos vs o que não temos:**

| Dado | Onde existe | Armazenado no banco? | Motivo |
|---|---|---|---|
| `CLIENTE` (nome) | `contratos.cliente` | ✅ Sim | Nome não é único — baixo risco isolado |
| `CPF` | `Contratos.xlsx` (fonte) | ❌ Não | Dado pessoal sensível — LGPD |
| `COD_ADE` | `reconquista_snapshot` + `contratos.num_proposta` | ✅ Sim | Código de contrato — não é dado pessoal |

**Para agentes de IA e desenvolvedores:**
> Não adicionar coluna `cpf` à tabela `contratos`, `reconquista_snapshot` ou qualquer
> outra tabela sem aprovação explícita. Não propor migrations que incluam CPF como
> dado em texto claro.

### 2.2 Identificação de pessoa entre maciças sem CPF

Sem CPF, o cruzamento de clientes entre maciças é feito por `COD_ADE`. Isso cobre
a maioria dos casos (clientes com o mesmo contrato de referência). Clientes que
assinaram novo contrato entre maciças e mudaram de `COD_ADE` **não serão cruzados** —
essa é a limitação aceita como trade-off do requisito de privacidade.

### 2.3 Fallback obfuscado (somente se exigido por necessidade de negócio)

Se no futuro for estritamente necessário cruzar clientes entre maciças por identidade
pessoal, a abordagem aprovada é **hash SHA-256 com salt secreto** — nunca CPF em
texto claro:

```python
import hashlib, os

# Salt fixo e secreto, armazenado apenas em variável de ambiente
_SALT = os.environ["CPF_HASH_SALT"].encode()

def cpf_hash(cpf: str) -> str:
    """Retorna hash irreversível do CPF. Jamais armazena o CPF original."""
    cpf_limpo = "".join(c for c in cpf if c.isdigit()).zfill(11)
    return hashlib.sha256(_SALT + cpf_limpo.encode()).hexdigest()
```

O hash é computado pelo `angry-man` **antes** de enviar ao Supabase. O banco nunca
vê o CPF original. A coluna seria `cpf_hash TEXT` (não `cpf`), para deixar claro
que é um pseudônimo.

> **Atenção (LGPD):** Dado pseudonimizado ainda é considerado dado pessoal pela LGPD
> se a chave de reversão (salt) estiver acessível. Tratar com o mesmo cuidado.
> Só implementar este fallback com aprovação do responsável pelo projeto.

---

## 3. Fonte de Dados

### 2.1 Arquivos Excel das Maciças

Recebidos periodicamente no formato:
```
Reconquista_MG CRED_{AAAAMM}_{AAAAMMDD}.xlsx
```

Exemplos:
- `Reconquista_MG CRED_202604_20260401.xlsx` — 1.º envio de Abril
- `Reconquista_MG CRED_202605_20260521.xlsx` — 1.º envio de Maio

**Schema fixo (24 colunas — estável desde 20/04/2026):**

| Coluna | Tipo | Descrição |
|---|---|---|
| `COD_ADE` | BIGINT | Chave do contrato de origem (= `contratos.num_proposta`) |
| `FRANQUEADO` | TEXT | Sempre `MG CRED` — ignorar |
| `FRANQUIA` | TEXT | Ex: `"53418 - - RJ - Duque De Caxias - Centro II"` |
| `COORD_FRANQUIA` | TEXT | Coordenador da franquia |
| `SALDO_CONTABIL` | NUMERIC | Saldo do contrato original |
| `DIAS_ATRASO` | INTEGER | Dias de inadimplência |
| `FAIXA_ATRASO` | TEXT | Faixa de atraso (ex: `"31-60"`) |
| `MOT_IPD_OPERAR` | TEXT | Motivo de impedimento operacional (pode ser nulo) |
| `CONSULTOR` | TEXT | Nome truncado do consultor (≤ ~14 chars) |
| `FLAG_CNC` | 0/1 | Reconquistado via novo contrato CNC |
| `FLAG_CONSIGNADO` | 0/1 | Reconquistado via consignado |
| `FLAG_CARTAO` | 0/1 | Reconquistado via cartão |
| `FLAG_DNA` | 0/1 | Reconquistado via processo DNA (reversível!) |
| `FLAG_RECONQUISTA` | 0/1 | OR de todos os flags — métrica principal |
| `TIPO_PGTO` | TEXT | Tipo de pagamento |
| `FLAG_RL` | 0/1 | Flag de relacionamento |
| `DAT_FIM_RELAC` | DATE | Data fim do relacionamento |
| `BANCO_ORIGEM` | TEXT | Banco de origem |
| `BANCO_DESTINO` | TEXT | Banco de destino |
| `QTD_FDR` | INTEGER | Quantidade FDR |
| `LINK` | TEXT | Link de acompanhamento |
| `TIPO_CONTA` | TEXT | Tipo de conta |
| `REGRA_PGTO` | TEXT | Regra de pagamento |
| `SUBPRODUTO` | TEXT | Subproduto (ex: `NOVO`, `SUPER CONTA`) |

### 2.2 Arquivo Contratos.xlsx (por maciça)

Gerado a partir do primeiro arquivo de cada maciça. Contém os dados do contrato
original correspondente a cada `COD_ADE`. A coluna de ligação é `Nº PROP/ADE`.

**Colunas relevantes a preservar:**

| Coluna em Contratos.xlsx | Mapeamento no banco |
|---|---|
| `Nº PROP/ADE` | = `COD_ADE` — chave de join |
| `CLIENTE` | `contratos.cliente` (já existe) |
| `CPF` | Identificador único da pessoa física |
| `CONTRATO ID` | `contratos.contrato_id` (já existe) |
| `VENDEDOR` | Nome completo + código (ex: `"3474 - CHALLANA DE SANTANA SILVA"`) |
| `FILIAL` | Nome da loja (ex: `"HELP ALCANTARA"`) |

> **Observação:** O `CPF` é o identificador correto da pessoa. Um mesmo CPF pode ter
> `COD_ADE` diferentes em maciças distintas (quando um novo contrato foi criado).
> O `COD_ADE` identifica o **contrato**, não a pessoa.

---

## 4. Pontes com o Schema Existente

O banco já possui todas as tabelas dimensionais necessárias. As ligações são:

| Campo do xlsx | Tabela existente | Coluna | Lógica de lookup |
|---|---|---|---|
| `FRANQUIA` | `lojas` | `cod_bmg` | `cod_bmg = CAST(split_part(FRANQUIA, ' - ', 1) AS INTEGER)` |
| `CONSULTOR` | `consultores` | `nome` | `nome ILIKE CONSULTOR_TRUNCADO || '%'` + filtro por `loja_id` |
| `COD_ADE` | `contratos` | `num_proposta` | `num_proposta = COD_ADE::TEXT` |

**Confirmado:** `lojas.cod_bmg` corresponde ao código numérico do prefixo de `FRANQUIA`.

| lojas.nome | lojas.cod_bmg | FRANQUIA (prefixo) |
|---|---|---|
| HELP ALCANTARA | 49820 | `49820 - - RJ - São Gonçalo - Alcântara` |
| HELP BONSUCESSO | 49924 | `49924 - - RJ - Rio De Janeiro - Bonsucesso` |
| HELP BANGU | 49923 | `49923 - - RJ - Rio De Janeiro - Bangu II` |

**Atenção — CONSULTOR truncado:** A coluna `CONSULTOR` nos arquivos Excel contém apenas
os primeiros ~14 caracteres do nome completo (ex: `"CHALLANA DE"` em vez de
`"CHALLANA DE SANTANA SILVA"`). O lookup por prefixo é suficiente, mas deve ser
combinado com `loja_id` para evitar colisões entre consultores de lojas distintas.

---

## 5. Migration 018 — Tabelas Novas

**Arquivo:** `database/migrations/018_reconquista_tables.sql`  
**Projeto:** `Numeros_venda`

```sql
-- ============================================================
-- Migration 018 — Projeto Reconquista MG CRED
-- Adiciona: macicas, reconquista_snapshot
-- Depende de: lojas, consultores (já existentes)
-- ============================================================


-- ===========================================
-- 1. macicas
-- Representa cada campanha de reconquista.
-- Uma maciça agrupa N envios de xlsx no mesmo
-- período de campanha.
-- ===========================================

CREATE TABLE macicas (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo             TEXT NOT NULL,
    descricao          TEXT,
    dat_primeiro_envio DATE NOT NULL,
    dat_ultimo_envio   DATE,
    meta_retencao      NUMERIC(5,2) NOT NULL DEFAULT 30.0,
    ativo              BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_macicas_codigo UNIQUE (codigo),
    CONSTRAINT chk_macicas_meta CHECK (meta_retencao BETWEEN 0 AND 100)
);

COMMENT ON TABLE macicas IS
    'Campanhas de reconquista MG CRED. Cada maciça agrupa '
    'múltiplos envios de arquivos Excel no mesmo período. '
    'Exemplo: Maciça Abril 2026 (código 202604) tem 15 envios '
    'de 01/04 a 20/05. A maciça muda aproximadamente no dia 20 '
    'do mês.';
COMMENT ON COLUMN macicas.codigo IS
    'Código no formato AAAAMM. Ex: 202604, 202605.';
COMMENT ON COLUMN macicas.dat_primeiro_envio IS
    'Data do primeiro arquivo xlsx recebido nesta campanha.';
COMMENT ON COLUMN macicas.dat_ultimo_envio IS
    'Data do último arquivo xlsx recebido. Atualizado a cada carga.';
COMMENT ON COLUMN macicas.meta_retencao IS
    'Meta de taxa de reconquista em %. Padrão: 30.0';

CREATE TRIGGER trg_macicas_updated_at
    BEFORE UPDATE ON macicas
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 2. reconquista_snapshot
-- Estado de cada cliente (COD_ADE) a cada
-- envio de arquivo Excel. Representa o estado
-- no momento do envio — não é cumulativo.
-- A FLAG_RECONQUISTA pode reverter de 1 para 0
-- (especialmente FLAG_DNA, que é reversível).
-- ===========================================

CREATE TABLE reconquista_snapshot (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    macica_id        UUID NOT NULL
                         REFERENCES macicas(id)
                         ON DELETE CASCADE,
    dat_envio        DATE NOT NULL,
    cod_ade          BIGINT NOT NULL,
    loja_id          UUID REFERENCES lojas(id)
                         ON DELETE SET NULL,
    consultor_id     UUID REFERENCES consultores(id)
                         ON DELETE SET NULL,
    subproduto       TEXT,
    saldo_contabil   NUMERIC(15, 2),
    dias_atraso      INTEGER,
    faixa_atraso     TEXT,
    mot_ipd_operar   TEXT,
    flag_cnc         SMALLINT NOT NULL DEFAULT 0,
    flag_consignado  SMALLINT NOT NULL DEFAULT 0,
    flag_cartao      SMALLINT NOT NULL DEFAULT 0,
    flag_dna         SMALLINT NOT NULL DEFAULT 0,
    flag_reconquista SMALLINT NOT NULL DEFAULT 0,
    flag_rl          SMALLINT NOT NULL DEFAULT 0,
    tipo_pgto        TEXT,
    tipo_conta       TEXT,
    regra_pgto       TEXT,
    dat_fim_relac    DATE,
    banco_origem     TEXT,
    banco_destino    TEXT,
    qtd_fdr          INTEGER,
    link             TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_reconquista_snapshot
        UNIQUE (macica_id, dat_envio, cod_ade),
    CONSTRAINT chk_rsnap_flag_cnc         CHECK (flag_cnc IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_consignado  CHECK (flag_consignado IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_cartao      CHECK (flag_cartao IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_dna         CHECK (flag_dna IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_reconquista CHECK (flag_reconquista IN (0, 1)),
    CONSTRAINT chk_rsnap_flag_rl          CHECK (flag_rl IN (0, 1))
);

COMMENT ON TABLE reconquista_snapshot IS
    'Snapshot do estado de cada cliente (COD_ADE) a cada envio '
    'de arquivo Excel da campanha. Não é cumulativo — cada linha '
    'representa o estado naquele momento. FLAG_RECONQUISTA pode '
    'reverter (principalmente FLAG_DNA, que é um estado do processo '
    'e não um fato contábil irreversível como FLAG_CNC).';
COMMENT ON COLUMN reconquista_snapshot.cod_ade IS
    'Código do contrato de origem. Corresponde a contratos.num_proposta '
    'e ao campo Nº PROP/ADE do arquivo Contratos.xlsx. '
    'Identifica o CONTRATO, não a pessoa (use CPF para isso).';
COMMENT ON COLUMN reconquista_snapshot.loja_id IS
    'FK para lojas. Resolvido via lojas.cod_bmg = prefixo numérico '
    'da coluna FRANQUIA do xlsx. Ex: FRANQUIA "53418 - ..." → cod_bmg=53418.';
COMMENT ON COLUMN reconquista_snapshot.consultor_id IS
    'FK para consultores. Resolvido via nome ILIKE CONSULTOR_TRUNCADO || ''%'' '
    'combinado com loja_id. O campo CONSULTOR no xlsx é truncado (~14 chars).';
COMMENT ON COLUMN reconquista_snapshot.flag_reconquista IS
    'Métrica principal. OR lógico de flag_cnc, flag_consignado, '
    'flag_cartao, flag_dna. Valor do momento do envio — pode reverter.';
COMMENT ON COLUMN reconquista_snapshot.flag_dna IS
    'Reversível. Representa estado de processo DNA no sistema de origem. '
    'Pode voltar a 0 se o processo for cancelado ou em reprocessamento '
    'de base (confirmado: 8 reversões em 14/04→20/04/2026).';
COMMENT ON COLUMN reconquista_snapshot.flag_cnc IS
    'Irreversível. Novo contrato CNC pago — fato contábil.';

-- Índices para as queries mais frequentes do dashboard
CREATE INDEX idx_rsnap_macica
    ON reconquista_snapshot (macica_id);

CREATE INDEX idx_rsnap_dat_envio
    ON reconquista_snapshot (macica_id, dat_envio);

CREATE INDEX idx_rsnap_cod_ade
    ON reconquista_snapshot (cod_ade);

CREATE INDEX idx_rsnap_loja
    ON reconquista_snapshot (loja_id);

CREATE INDEX idx_rsnap_consultor
    ON reconquista_snapshot (consultor_id);

CREATE INDEX idx_rsnap_flag
    ON reconquista_snapshot (macica_id, flag_reconquista);
```

---

## 6. Migration 019 — Views e Função de Exibição

**Arquivo:** `database/migrations/019_reconquista_views.sql`  
**Projeto:** `Numeros_venda`

```sql
-- ============================================================
-- Migration 019 — Views e função para o dashboard Reconquista
-- Depende de: 018_reconquista_tables.sql
-- ============================================================


-- ===========================================
-- fn_macica_ativa
-- Retorna a maciça a ser exibida para um dado
-- mês/ano de visualização.
--
-- REGRA DE NEGÓCIO:
--   A maciça muda aproximadamente no dia 20 do
--   mês. Para um mês M sem maciça própria, exibe
--   a maciça anterior mais recente.
--
--   Exemplos:
--   - Junho/2026 sem maciça própria → exibe Maio/2026
--   - Quando Junho/2026 for carregada → exibe Junho/2026
--
--   Implementação: retorna a maciça ativa mais
--   recente cujo dat_primeiro_envio caiu dentro ou
--   antes do último dia do mês solicitado.
-- ===========================================

CREATE OR REPLACE FUNCTION fn_macica_ativa(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    id                 UUID,
    codigo             TEXT,
    descricao          TEXT,
    dat_primeiro_envio DATE,
    dat_ultimo_envio   DATE,
    meta_retencao      NUMERIC
)
LANGUAGE SQL
STABLE
SET search_path = ''
AS $$
    SELECT
        m.id,
        m.codigo,
        m.descricao,
        m.dat_primeiro_envio,
        m.dat_ultimo_envio,
        m.meta_retencao
    FROM public.macicas m
    WHERE m.ativo = true
      AND m.dat_primeiro_envio <=
          (make_date(p_ano, p_mes, 1) + INTERVAL '1 month - 1 day')::date
    ORDER BY m.dat_primeiro_envio DESC
    LIMIT 1;
$$;

COMMENT ON FUNCTION fn_macica_ativa(INTEGER, INTEGER) IS
    'Retorna a maciça de reconquista a ser exibida para o mês/ano '
    'solicitado. Se não há maciça para o mês corrente, retorna a '
    'última disponível (fallback para mês anterior). '
    'Exemplo: fn_macica_ativa(6, 2026) retorna Maciça de Maio/2026 '
    'enquanto a de Junho não estiver carregada.';


-- ===========================================
-- v_reconquista_ultimo
-- Último snapshot registrado por cliente
-- (cod_ade) por maciça.
-- Usado pelas demais views de KPI.
-- ===========================================

CREATE VIEW v_reconquista_ultimo
    WITH (security_invoker = on)
AS
SELECT DISTINCT ON (macica_id, cod_ade)
    macica_id,
    cod_ade,
    dat_envio        AS dat_ultimo_envio,
    loja_id,
    consultor_id,
    subproduto,
    saldo_contabil,
    dias_atraso,
    faixa_atraso,
    mot_ipd_operar,
    flag_cnc,
    flag_consignado,
    flag_cartao,
    flag_dna,
    flag_reconquista,
    flag_rl
FROM reconquista_snapshot
ORDER BY macica_id, cod_ade, dat_envio DESC;

COMMENT ON VIEW v_reconquista_ultimo IS
    'Último snapshot por cliente (cod_ade) por maciça. '
    'Representa o estado mais atual de cada cliente na campanha. '
    'Usado como base para os KPIs do dashboard.';


-- ===========================================
-- v_reconquista_por_loja
-- KPIs de reconquista agrupados por loja.
-- Baseado no último snapshot de cada cliente.
-- ===========================================

CREATE VIEW v_reconquista_por_loja
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    m.descricao,
    m.meta_retencao,
    l.id                                                            AS loja_id,
    l.nome                                                          AS loja,
    r.nome                                                          AS regiao,
    COUNT(*)                                                        AS total_clientes,
    SUM(s.flag_reconquista)                                         AS reconquistados,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0), 1
    )                                                               AS taxa_pct,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0)
        - m.meta_retencao, 1
    )                                                               AS gap_pp,
    ROUND(AVG(s.saldo_contabil), 2)                                 AS saldo_medio,
    ROUND(AVG(s.dias_atraso), 0)                                    AS dias_atraso_medio
FROM v_reconquista_ultimo s
JOIN macicas m            ON m.id = s.macica_id
LEFT JOIN lojas l         ON l.id = s.loja_id
LEFT JOIN regioes r       ON r.id = l.regiao_id
GROUP BY
    s.macica_id, m.codigo, m.descricao, m.meta_retencao,
    l.id, l.nome, r.nome;

COMMENT ON VIEW v_reconquista_por_loja IS
    'KPIs de reconquista por loja. Baseado no último snapshot '
    'de cada cliente por maciça. Inclui taxa atual, gap em '
    'relação à meta e perfil financeiro médio.';


-- ===========================================
-- v_reconquista_por_consultor
-- KPIs de reconquista agrupados por consultor.
-- ===========================================

CREATE VIEW v_reconquista_por_consultor
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    m.meta_retencao,
    l.nome                                                          AS loja,
    r.nome                                                          AS regiao,
    con.nome                                                        AS consultor,
    COUNT(*)                                                        AS total_clientes,
    SUM(s.flag_reconquista)                                         AS reconquistados,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0), 1
    )                                                               AS taxa_pct,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0)
        - m.meta_retencao, 1
    )                                                               AS gap_pp
FROM v_reconquista_ultimo s
JOIN macicas m               ON m.id = s.macica_id
LEFT JOIN consultores con    ON con.id = s.consultor_id
LEFT JOIN lojas l            ON l.id = con.loja_id
LEFT JOIN regioes r          ON r.id = l.regiao_id
GROUP BY
    s.macica_id, m.codigo, m.meta_retencao,
    l.nome, r.nome, con.nome;

COMMENT ON VIEW v_reconquista_por_consultor IS
    'KPIs de reconquista por consultor. Baseado no último snapshot '
    'de cada cliente por maciça.';


-- ===========================================
-- v_reconquista_evolucao
-- Taxa de reconquista por data de envio.
-- Usado para o gráfico de linha no dashboard.
-- ===========================================

CREATE VIEW v_reconquista_evolucao
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    m.meta_retencao,
    s.dat_envio,
    COUNT(*)                                                        AS total_clientes,
    SUM(s.flag_reconquista)                                         AS reconquistados,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0), 2
    )                                                               AS taxa_pct
FROM reconquista_snapshot s
JOIN macicas m ON m.id = s.macica_id
GROUP BY s.macica_id, m.codigo, m.meta_retencao, s.dat_envio
ORDER BY s.macica_id, s.dat_envio;

COMMENT ON VIEW v_reconquista_evolucao IS
    'Evolução diária da taxa de reconquista por maciça. '
    'Cada linha representa um envio de arquivo Excel. '
    'Usado para o gráfico de linha no dashboard.';


-- ===========================================
-- v_reconquista_indiferentes
-- Clientes com 3+ aparições na mesma maciça
-- que nunca converteram (flag_reconquista=0).
-- São o principal alvo de ação.
-- ===========================================

CREATE VIEW v_reconquista_indiferentes
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    s.cod_ade,
    l.nome                                                          AS loja,
    con.nome                                                        AS consultor,
    COUNT(DISTINCT s.dat_envio)                                     AS aparicoes,
    ROUND(AVG(s.saldo_contabil), 2)                                 AS saldo_medio,
    ROUND(AVG(s.dias_atraso), 0)                                    AS dias_atraso_medio,
    MIN(s.dat_envio)                                                AS primeira_aparicao,
    MAX(s.dat_envio)                                                AS ultima_aparicao
FROM reconquista_snapshot s
JOIN macicas m              ON m.id = s.macica_id
LEFT JOIN lojas l           ON l.id = s.loja_id
LEFT JOIN consultores con   ON con.id = s.consultor_id
GROUP BY s.macica_id, m.codigo, s.cod_ade, l.nome, con.nome
HAVING COUNT(DISTINCT s.dat_envio) >= 3
   AND MAX(s.flag_reconquista) = 0;

COMMENT ON VIEW v_reconquista_indiferentes IS
    'Clientes que aparecem 3 ou mais vezes na mesma maciça '
    'sem nunca converterem. Representam o principal alvo de '
    'ação ativa. Atenção: distinguir indiferença comportamental '
    'de bloqueio operacional (mot_ipd_operar preenchido).';
```

---

## 7. Migration 020 — RPCs de Importação

**Arquivo:** `database/migrations/020_reconquista_rpcs.sql`  
**Projeto:** `Numeros_venda`

Estas funções são chamadas pelo `angry-man` para importar os dados.
O design usa JSONB para permitir importação em lote e minimizar
round-trips ao banco.

```sql
-- ============================================================
-- Migration 020 — RPCs de importação do Reconquista
-- Depende de: 018_reconquista_tables.sql
-- Chamadas por: angry-man (role: admin ou service_role)
-- ============================================================


-- ===========================================
-- fn_upsert_macica
-- Cria ou atualiza uma maciça.
-- Retorna o UUID da maciça (nova ou existente).
-- Chamada uma vez por arquivo xlsx importado.
-- ===========================================

CREATE OR REPLACE FUNCTION fn_upsert_macica(
    p_codigo             TEXT,
    p_descricao          TEXT,
    p_dat_primeiro_envio DATE,
    p_dat_ultimo_envio   DATE   DEFAULT NULL,
    p_meta_retencao      NUMERIC DEFAULT 30.0
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO public.macicas (
        codigo, descricao, dat_primeiro_envio,
        dat_ultimo_envio, meta_retencao
    )
    VALUES (
        p_codigo, p_descricao, p_dat_primeiro_envio,
        p_dat_ultimo_envio, p_meta_retencao
    )
    ON CONFLICT (codigo) DO UPDATE
        SET descricao          = EXCLUDED.descricao,
            dat_ultimo_envio   = GREATEST(
                                     macicas.dat_ultimo_envio,
                                     EXCLUDED.dat_ultimo_envio
                                 ),
            updated_at         = now()
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION fn_upsert_macica IS
    'Cria ou atualiza uma maciça. Retorna o UUID. '
    'Se a maciça já existe (mesmo codigo), apenas atualiza '
    'dat_ultimo_envio (mantendo o mais recente) e descricao. '
    'Chamada pelo angry-man uma vez por arquivo xlsx processado.';


-- ===========================================
-- fn_importar_reconquista_snapshot
-- Importa em lote as linhas de um arquivo xlsx.
-- Recebe JSONB com array de objetos.
-- Faz o lookup de loja_id e consultor_id
-- internamente para evitar N+1 no cliente.
-- ===========================================

CREATE OR REPLACE FUNCTION fn_importar_reconquista_snapshot(
    p_macica_id UUID,
    p_dat_envio DATE,
    p_rows      JSONB     -- array de objetos, ver schema abaixo
)
RETURNS TABLE (
    inseridos  INTEGER,
    atualizados INTEGER,
    sem_loja   INTEGER,
    sem_consultor INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
/*
Schema esperado para cada objeto em p_rows:
{
    "cod_ade":         9601063,       -- BIGINT, obrigatório
    "cod_bmg_loja":    53418,         -- INT: prefixo numérico de FRANQUIA
    "consultor_prefix": "CHALLANA DE",-- TEXT: valor truncado de CONSULTOR
    "subproduto":      "SUPER CONTA",
    "saldo_contabil":  1500.00,
    "dias_atraso":     45,
    "faixa_atraso":    "31-60",
    "mot_ipd_operar":  null,
    "flag_cnc":        0,
    "flag_consignado": 0,
    "flag_cartao":     0,
    "flag_dna":        0,
    "flag_reconquista":0,
    "flag_rl":         0,
    "tipo_pgto":       null,
    "tipo_conta":      null,
    "regra_pgto":      null,
    "dat_fim_relac":   null,
    "banco_origem":    null,
    "banco_destino":   null,
    "qtd_fdr":         0,
    "link":            null
}
*/
DECLARE
    v_inseridos     INTEGER := 0;
    v_atualizados   INTEGER := 0;
    v_sem_loja      INTEGER := 0;
    v_sem_consultor INTEGER := 0;
    v_row           JSONB;
    v_loja_id       UUID;
    v_consultor_id  UUID;
    v_affected      INTEGER;
BEGIN
    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows)
    LOOP
        -- Lookup loja por cod_bmg
        SELECT id INTO v_loja_id
        FROM public.lojas
        WHERE cod_bmg = (v_row->>'cod_bmg_loja')::INTEGER
        LIMIT 1;

        IF v_loja_id IS NULL THEN
            v_sem_loja := v_sem_loja + 1;
        END IF;

        -- Lookup consultor por prefixo de nome + loja
        SELECT id INTO v_consultor_id
        FROM public.consultores
        WHERE nome ILIKE (v_row->>'consultor_prefix') || '%'
          AND (loja_id = v_loja_id OR loja_id IS NULL)
        ORDER BY
            CASE WHEN loja_id = v_loja_id THEN 0 ELSE 1 END,
            nome
        LIMIT 1;

        IF v_consultor_id IS NULL THEN
            v_sem_consultor := v_sem_consultor + 1;
        END IF;

        -- Upsert do snapshot
        INSERT INTO public.reconquista_snapshot (
            macica_id, dat_envio, cod_ade,
            loja_id, consultor_id, subproduto,
            saldo_contabil, dias_atraso, faixa_atraso, mot_ipd_operar,
            flag_cnc, flag_consignado, flag_cartao,
            flag_dna, flag_reconquista, flag_rl,
            tipo_pgto, tipo_conta, regra_pgto,
            dat_fim_relac, banco_origem, banco_destino,
            qtd_fdr, link
        )
        VALUES (
            p_macica_id,
            p_dat_envio,
            (v_row->>'cod_ade')::BIGINT,
            v_loja_id,
            v_consultor_id,
            v_row->>'subproduto',
            (v_row->>'saldo_contabil')::NUMERIC,
            (v_row->>'dias_atraso')::INTEGER,
            v_row->>'faixa_atraso',
            v_row->>'mot_ipd_operar',
            COALESCE((v_row->>'flag_cnc')::SMALLINT, 0),
            COALESCE((v_row->>'flag_consignado')::SMALLINT, 0),
            COALESCE((v_row->>'flag_cartao')::SMALLINT, 0),
            COALESCE((v_row->>'flag_dna')::SMALLINT, 0),
            COALESCE((v_row->>'flag_reconquista')::SMALLINT, 0),
            COALESCE((v_row->>'flag_rl')::SMALLINT, 0),
            v_row->>'tipo_pgto',
            v_row->>'tipo_conta',
            v_row->>'regra_pgto',
            (v_row->>'dat_fim_relac')::DATE,
            v_row->>'banco_origem',
            v_row->>'banco_destino',
            (v_row->>'qtd_fdr')::INTEGER,
            v_row->>'link'
        )
        ON CONFLICT (macica_id, dat_envio, cod_ade) DO UPDATE
            SET loja_id          = EXCLUDED.loja_id,
                consultor_id     = EXCLUDED.consultor_id,
                subproduto       = EXCLUDED.subproduto,
                saldo_contabil   = EXCLUDED.saldo_contabil,
                dias_atraso      = EXCLUDED.dias_atraso,
                faixa_atraso     = EXCLUDED.faixa_atraso,
                mot_ipd_operar   = EXCLUDED.mot_ipd_operar,
                flag_cnc         = EXCLUDED.flag_cnc,
                flag_consignado  = EXCLUDED.flag_consignado,
                flag_cartao      = EXCLUDED.flag_cartao,
                flag_dna         = EXCLUDED.flag_dna,
                flag_reconquista = EXCLUDED.flag_reconquista,
                flag_rl          = EXCLUDED.flag_rl,
                tipo_pgto        = EXCLUDED.tipo_pgto,
                tipo_conta       = EXCLUDED.tipo_conta,
                regra_pgto       = EXCLUDED.regra_pgto,
                dat_fim_relac    = EXCLUDED.dat_fim_relac,
                banco_origem     = EXCLUDED.banco_origem,
                banco_destino    = EXCLUDED.banco_destino,
                qtd_fdr          = EXCLUDED.qtd_fdr,
                link             = EXCLUDED.link;

        GET DIAGNOSTICS v_affected = ROW_COUNT;
        -- ROW_COUNT = 1 tanto em INSERT quanto em UPDATE com ON CONFLICT
        -- Para distinguir, verificamos se o id já existia (xmax > 0 não
        -- é acessível via GET DIAGNOSTICS; usar contador simples)
        v_inseridos := v_inseridos + 1;
    END LOOP;

    -- Atualizar dat_ultimo_envio da maciça
    UPDATE public.macicas
    SET dat_ultimo_envio = GREATEST(dat_ultimo_envio, p_dat_envio),
        updated_at       = now()
    WHERE id = p_macica_id;

    RETURN QUERY SELECT v_inseridos, v_atualizados, v_sem_loja, v_sem_consultor;
END;
$$;

COMMENT ON FUNCTION fn_importar_reconquista_snapshot IS
    'Importa em lote os snapshots de um arquivo xlsx. '
    'Resolve loja_id (via lojas.cod_bmg) e consultor_id '
    '(via nome ILIKE prefixo + loja) internamente. '
    'Faz upsert por (macica_id, dat_envio, cod_ade). '
    'Retorna contadores de inserções, sem_loja e sem_consultor '
    'para logging no angry-man. '
    'Recomendado: chamar em lotes de 500 linhas.';


-- Permissões: apenas service_role e admin podem chamar
-- (ajustar conforme política RLS do projeto)
REVOKE ALL ON FUNCTION fn_upsert_macica FROM PUBLIC;
REVOKE ALL ON FUNCTION fn_importar_reconquista_snapshot FROM PUBLIC;
```

---

## 8. ETL — Especificação para o angry-man

> **Privacidade:** O ETL não deve ler, logar, transmitir ou armazenar o CPF dos clientes.
> O campo `CPF` presente no `Contratos.xlsx` deve ser ignorado na importação.
> Ver [Seção 2](#2-privacidade-e-lgpd--decisões-de-design).

### 8.1 Fluxo de importação por arquivo

```
ENTRADA: arquivo xlsx do tipo "Reconquista_MG CRED_{AAAAMM}_{AAAAMMDD}.xlsx"

PASSO 1 — Extrair metadados do nome do arquivo
    codigo_macica = nome[24:30]       # ex: "202605"
    dat_envio     = parse(nome[31:39]) # ex: date(2026, 5, 21)
    descricao     = f"Maciça {MESES[mes]} {ano}"

PASSO 2 — Criar/atualizar a maciça via RPC
    macica_id = fn_upsert_macica(
        p_codigo             = codigo_macica,
        p_descricao          = descricao,
        p_dat_primeiro_envio = dat_envio,   # na criação
        p_dat_ultimo_envio   = dat_envio    # na atualização: usa GREATEST
    )

PASSO 3 — Ler o xlsx e preparar o payload
    df = pd.read_excel(arquivo, dtype=str)

    Para cada linha, extrair:
        cod_bmg_loja    = int(df["FRANQUIA"].str.split(" - ").str[0])
        consultor_prefix = df["CONSULTOR"].str.strip()
        dat_fim_relac   = parse_date_or_none(df["DAT_FIM_RELAC"])
        # Todos os flags: int(df["FLAG_*"]) com fallback 0 se NaN

    rows = [
        {
            "cod_ade":          int(row["COD_ADE"]),
            "cod_bmg_loja":     cod_bmg_loja,
            "consultor_prefix": consultor_prefix,
            "subproduto":       row["SUBPRODUTO"] or None,
            "saldo_contabil":   float(row["SALDO_CONTABIL"]) or None,
            "dias_atraso":      int(row["DIAS_ATRASO"]) if not NaN else None,
            "faixa_atraso":     row["FAIXA_ATRASO"] or None,
            "mot_ipd_operar":   row["MOT_IPD_OPERAR"] or None,
            "flag_cnc":         int(row["FLAG_CNC"] or 0),
            "flag_consignado":  int(row["FLAG_CONSIGNADO"] or 0),
            "flag_cartao":      int(row["FLAG_CARTAO"] or 0),
            "flag_dna":         int(row["FLAG_DNA"] or 0),
            "flag_reconquista": int(row["FLAG_RECONQUISTA"] or 0),
            "flag_rl":          int(row["FLAG_RL"] or 0),
            "tipo_pgto":        row["TIPO_PGTO"] or None,
            "tipo_conta":       row["TIPO_CONTA"] or None,
            "regra_pgto":       row["REGRA_PGTO"] or None,
            "dat_fim_relac":    dat_fim_relac,
            "banco_origem":     row["BANCO_ORIGEM"] or None,
            "banco_destino":    row["BANCO_DESTINO"] or None,
            "qtd_fdr":          int(row["QTD_FDR"] or 0),
            "link":             row["LINK"] or None,
        }
        for row in df.itertuples()
    ]

PASSO 4 — Chamar a RPC em lotes de 500
    BATCH_SIZE = 500
    total = {"inseridos": 0, "sem_loja": 0, "sem_consultor": 0}

    for batch in chunks(rows, BATCH_SIZE):
        result = supabase.rpc("fn_importar_reconquista_snapshot", {
            "p_macica_id": macica_id,
            "p_dat_envio":  dat_envio.isoformat(),
            "p_rows":       batch           # lista de dicts → JSONB
        }).execute()
        total += result.data[0]

PASSO 5 — Log do resultado
    logger.info(
        f"[Reconquista] {arquivo.name}: "
        f"{total['inseridos']} upserts, "
        f"{total['sem_loja']} sem loja, "
        f"{total['sem_consultor']} sem consultor"
    )
    if total['sem_loja'] > 0 or total['sem_consultor'] > 0:
        logger.warning("Revisar cod_bmg das lojas ou nomes de consultores.")
```

### 8.2 Identificação do tipo de arquivo

O angry-man deve detectar arquivos de reconquista pelo padrão do nome:

```python
import re

PATTERN_RECONQUISTA = re.compile(
    r"^Reconquista_MG CRED_(\d{6})_(\d{8})\.xlsx$"
)

def eh_arquivo_reconquista(nome: str) -> bool:
    return bool(PATTERN_RECONQUISTA.match(nome))
```

### 8.3 Tratamentos especiais

- **`FRANQUIA` com código inválido:** se `split(" - ")[0]` não for numérico,
  logar como aviso e enviar `cod_bmg_loja = null`.
- **`DAT_FIM_RELAC` vazia:** enviar `null` (não `""` nem `"NaT"`).
- **`COD_ADE` duplicado no mesmo arquivo:** manter apenas a primeira ocorrência
  (edge case: duplicatas dentro de um mesmo xlsx).
- **Arquivos das primeiras semanas de Abril (schema antigo):** os arquivos
  de 01/04 a 19/04/2026 têm schema diferente (menos de 24 colunas).
  Verificar se `len(df.columns) >= 24` antes de processar; rejeitar e logar
  se não atender.

---

## 9. Dashboard — Especificação para o Numeros_venda

### 9.1 Novo arquivo

**Criar:** `src/dashboard/tabs/reconquista.py`

### 9.2 Loader (adicionar em `src/dashboard/loaders.py`)

```python
@st.cache_data(ttl=600)
def carregar_reconquista(mes: int, ano: int) -> dict:
    """
    Retorna todos os dados de reconquista para o mês/ano informado.
    Usa fn_macica_ativa para resolver qual maciça exibir.
    TTL curto (10 min) pois dados mudam durante o dia.
    """
    sb = _sb()

    # 1. Maciça ativa para o mês
    macica = sb.rpc("fn_macica_ativa", {"p_mes": mes, "p_ano": ano}).execute()
    if not macica.data:
        return {"macica": None}

    m = macica.data[0]
    macica_id = m["id"]

    # 2. KPIs globais (via v_reconquista_por_loja agregado)
    lojas = (
        sb.table("v_reconquista_por_loja")
          .select("*")
          .eq("macica_id", macica_id)
          .execute()
    )

    # 3. Por consultor
    consultores = (
        sb.table("v_reconquista_por_consultor")
          .select("*")
          .eq("macica_id", macica_id)
          .execute()
    )

    # 4. Evolução diária
    evolucao = (
        sb.table("v_reconquista_evolucao")
          .select("*")
          .eq("macica_id", macica_id)
          .execute()
    )

    # 5. Indiferentes
    indiferentes = (
        sb.table("v_reconquista_indiferentes")
          .select("*")
          .eq("macica_id", macica_id)
          .execute()
    )

    return {
        "macica":       m,
        "por_loja":     pd.DataFrame(lojas.data),
        "por_consultor": pd.DataFrame(consultores.data),
        "evolucao":     pd.DataFrame(evolucao.data),
        "indiferentes": pd.DataFrame(indiferentes.data),
    }
```

### 9.3 Estrutura do componente (reconquista.py)

```
def render_reconquista(mes: int, ano: int):

    dados = carregar_reconquista(mes, ano)

    if dados["macica"] is None:
        st.info("Nenhuma maciça de reconquista disponível para este período.")
        return

    macica = dados["macica"]

    # ── Cabeçalho ─────────────────────────────────────────────────
    st.subheader(f"🎯 Reconquista — {macica['descricao']}")

    # Aviso quando a maciça exibida é de mês anterior
    if macica["codigo"] != f"{ano}{mes:02d}":
        st.info(
            f"ℹ️ Exibindo {macica['descricao']} — "
            f"maciça de {mes:02d}/{ano} ainda não disponível."
        )

    df_loja = dados["por_loja"]
    total = df_loja["total_clientes"].sum()
    reconq = df_loja["reconquistados"].sum()
    taxa   = reconq / total * 100 if total else 0
    meta   = macica["meta_retencao"]
    gap    = max(0, int(total * meta / 100) - reconq)

    # ── KPIs globais (4 métricas) ──────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Base da Maciça",   f"{total:,}".replace(",", "."))
    col2.metric("Reconquistados",   f"{reconq:,}".replace(",", "."))
    col3.metric("Taxa Atual",       f"{taxa:.1f}%",
                delta=f"{taxa - meta:.1f} pp vs meta")
    col4.metric("GAP p/ Meta 30%", f"{gap:,}".replace(",", ".") + " clientes")

    # ── Gráfico de evolução ────────────────────────────────────────
    st.subheader("Evolução da Taxa por Envio")
    df_ev = dados["evolucao"]
    # Gráfico de linha: taxa_pct por dat_envio + linha tracejada em meta
    # (usar plotly)

    # ── Abas internas ──────────────────────────────────────────────
    tab_loja, tab_cons, tab_indf = st.tabs(
        ["Por Loja", "Por Consultor", "Indiferentes"]
    )

    with tab_loja:
        # Tabela com colunas: loja, regiao, total, reconquistados,
        # taxa_pct, gap_pp (vermelho/verde), saldo_medio
        ...

    with tab_cons:
        # Tabela com colunas: consultor, loja, total,
        # reconquistados, taxa_pct, gap_pp
        ...

    with tab_indf:
        st.caption(
            f"{len(dados['indiferentes'])} clientes com 3+ aparições "
            "sem conversão. Diferenciar bloqueio operacional "
            "(mot_ipd_operar preenchido) de indiferença real."
        )
        # Tabela com: cod_ade, loja, consultor, aparições,
        # saldo_medio, dias_atraso_medio, primeira/última aparição
        ...
```

### 9.4 Adição à navegação

Em `dashboard_supabase.py` (ou no arquivo principal de navegação),
adicionar a aba "Reconquista" no menu de tabs ou páginas lateral.

---

## 10. Regras de Negócio Críticas

### 9.1 FLAG_RECONQUISTA é reversível

`FLAG_DNA` pode voltar de 1 para 0. Confirmado empiricamente: 8 clientes
reverteram em 14/04→20/04/2026. `FLAG_CNC` é irreversível (fato contábil).

**Consequência:** O dashboard deve mostrar sempre o **último snapshot**
(via `v_reconquista_ultimo`), não o pico histórico. Um cliente que tinha
`FLAG_RECONQUISTA=1` e voltou para 0 **não deve ser contado como reconquistado**.

### 9.2 COD_ADE identifica contrato, não pessoa

O mesmo cliente (CPF) pode ter `COD_ADE` diferente em maciças distintas
se um novo contrato foi criado. Para cruzar clientes entre maciças,
usar CPF (disponível em `Contratos.xlsx`).

### 9.3 Regra de exibição de maciça por mês

A maciça muda aproximadamente no dia 20 do mês (confirmado pelo padrão
dos arquivos: Abril encerra em 20/05, Maio começa em 21/05).

Regra implementada em `fn_macica_ativa(mes, ano)`:
> Retornar a maciça mais recente cujo `dat_primeiro_envio` caiu
> dentro ou antes do último dia do mês solicitado.

| Mês solicitado | Maciça ativa | Situação |
|---|---|---|
| Abril/2026 | 202604 | Normal |
| Maio/2026 | 202605 | Normal (disponível a partir de 21/05) |
| Junho/2026 | 202605 | Fallback — Junho ainda não carregado |
| Junho/2026 | 202606 | Normal — após carga da maciça de Junho |

### 9.4 Schema dos arquivos antes de 20/04/2026

Os 3 primeiros arquivos da Maciça de Abril (01/04, 08/04, 10/04) têm
schema diferente (menos de 24 colunas). O ETL deve rejeitar arquivos
com menos de 24 colunas e registrar o motivo.

---

## 11. Checklist de Implementação

### Privacidade (ambos os projetos)

- [ ] Confirmar que nenhuma coluna `cpf` foi adicionada a qualquer tabela
- [ ] Confirmar que o ETL do angry-man ignora a coluna `CPF` do `Contratos.xlsx`
- [ ] Confirmar que logs do angry-man não registram CPF em texto claro

### Numeros_venda

- [ ] Executar `018_reconquista_tables.sql` no Supabase (SQL Editor)
- [ ] Executar `019_reconquista_views.sql` no Supabase
- [ ] Executar `020_reconquista_rpcs.sql` no Supabase
- [ ] Conceder permissões às RPCs para o role correto (`service_role` ou `admin`)
- [ ] Adicionar loader `carregar_reconquista()` em `src/dashboard/loaders.py`
- [ ] Criar `src/dashboard/tabs/reconquista.py`
- [ ] Adicionar a aba ao menu de navegação do dashboard principal
- [ ] Testar `fn_macica_ativa(5, 2026)` → deve retornar Maciça 202605
- [ ] Testar `fn_macica_ativa(6, 2026)` → deve retornar 202605 (fallback)

### angry-man

- [ ] Adicionar detecção de arquivos de reconquista pelo padrão de nome
- [ ] Implementar `ETLReconquista` (ou equivalente ao padrão do projeto)
- [ ] Chamar `fn_upsert_macica` para criar/atualizar a maciça
- [ ] Chamar `fn_importar_reconquista_snapshot` em lotes de 500 linhas
- [ ] Logar `sem_loja` e `sem_consultor` como warnings
- [ ] Adicionar validação: rejeitar xlsx com menos de 24 colunas
- [ ] Testar com arquivo `Reconquista_MG CRED_202605_20260521.xlsx`

### Dados iniciais (carga manual ou via angry-man)

- [ ] Inserir Maciça Abril: `codigo=202604`, `dat_primeiro_envio=2026-04-01`,
      `dat_ultimo_envio=2026-05-20`
- [ ] Inserir Maciça Maio: `codigo=202605`, `dat_primeiro_envio=2026-05-21`
- [ ] Carregar todos os 15 arquivos de Abril via ETL
- [ ] Carregar os 3 arquivos de Maio via ETL
- [ ] Verificar `sem_loja` e `sem_consultor` nos logs e corrigir se necessário

---

*Documento gerado a partir da análise exploratória dos dados realizada no projeto
`reconquista` em 28/05/2026. Fontes: `analise_planilhas.py`, `analise_incidencia.py`,
`analise_macica_maio.py`, `resultado_incidencia.txt`, `resultado_maio.txt`.*
