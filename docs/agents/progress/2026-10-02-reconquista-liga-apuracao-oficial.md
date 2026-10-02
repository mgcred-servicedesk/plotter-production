# 2026-10-02 — Reconquista: liga do banco vira a apuração oficial

**Agente:** Claude Code
**Tipo:** feature (cross-repo: Numeros_venda + angry-man)
**Arquivos tocados:**
- Numeros_venda:
  - `database/migrations/127_reconquista_liga.sql`
  - `src/dashboard/kpis/reconquista.py`
  - `src/dashboard/loaders.py`
  - `src/dashboard/ui/kpi_cards_reforma.py`
  - `src/dashboard/tabs/analiticos.py`
  - testes (`test_loader_reconquista_liga.py`, `test_cards_reconquista_liga.py`, `test_kpis_reconquista.py`, `test_tabs_analiticos.py`)
  - `docs/agents/business-rules.md`
- angry-man:
  - `src/services/import-reconquista-liga.ts`
  - `import-registry.ts`
  - `lib/supabase.ts`
  - `supabase/functions/reconquista-rpc/index.ts`
  - teste vitest
**Commit(s):** —

## Objetivo

A partir de 09/2026, as Efetivadas da Reconquista passam a ser a contagem
que o banco contabiliza: arquivo da *liga*, propostas com `1`, importado
no angry-man para o período escolhido. O export `reconquista_YYYYMM`
continua sendo importado, mas vira só analítico. No analítico:
- sai a coluna Faixa Prêmio do Por Loja;
- o Detalhamento fica só com "Todos os meses";
- entra uma sub-aba "Liga".

## O que foi feito

- **Migration 127**:
  - tabela `reconquista_liga`, por `periodo_id`, guardando `qtde` 1 e 0;
  - bloqueio explícito de acesso direto, igual à 093;
  - view `v_reconquista_liga` com os mesmos nomes de loja, região e
    consultor da `v_reconquista`, para reaproveitar o recorte por perfil;
  - RPC `fn_importar_reconquista_liga(p_periodo_id, p_rows)`, que apaga e
    regrava só o período.
- **Loader**:
  - `carregar_reconquista` sobrescreve `totais["efetivadas"]` com a liga
    quando o período é 09/2026 ou posterior;
  - expõe `liga_status` e o frame `liga`, já recortado por perfil;
  - o acelerador por consultor recebe as efetivadas da liga por um novo
    parâmetro opcional de `montar_acelerador_por_consultor`.
- **Card**:
  - com liga, Efetivadas mostra só a quantidade, sem conversão e sem faixa
    sobre o prêmio CNC;
  - sem liga, mostra "—" e um aviso;
  - a barra antiga de conversão nunca aparece no regime da liga.
- **Analítico**:
  - sub-aba Liga, com filtro "Contabilizada" aberto em *Contabilizadas*;
  - Por Loja sem a Faixa Prêmio;
  - Detalhamento só com todos os meses, sem as colunas Apuração e Vigência.
- **angry-man**:
  - card "Reconquista — Liga" com período obrigatório;
  - parser que ignora o rodapé e confere o "Total" contra a contagem lida;
  - RPC registrada no `RPC_ENDPOINT_MAP` e na lista de funções permitidas
    da Edge Function.
- **Arquivo real de 09/2026 conferido pelo parser do angry-man**: 176
  linhas, 118 contabilizadas, todos os `cod_bmg` lidos e o Total batendo.

## Decisões não óbvias

- **Sem defasagem na liga.** O banco conta pelo mês da reconquista
  (maciça). Das 118 contabilizadas em 09/2026:
  - 36 não existem no export;
  - as 82 restantes têm `dt_fim` entre 03 e 08/2026.

  Aplicar a defasagem do export à liga deslocaria o prêmio de mês.
- **Sem conversão no card de liga** (decisão do usuário). A liga não traz
  a base total. Dividir pelos elegíveis do export misturaria duas bases
  diferentes.
- **Liga ausente vira `LIGA_NAO_IMPORTADA`, não zero, e não volta à regra
  antiga.** A faixa do acelerador não é calculada nesse caso, porque sairia
  "0 a 2" com cara de certa. Falha de leitura vira `LIGA_ERRO`, pelo mesmo
  motivo.
- **"Não importada" é decidido antes do RLS.** Liga importada que o
  recorte esvazia é zero legítimo (`LIGA_OK`).
- **Atribuição pelo arquivo da liga**, não pelo export: há propostas que
  só existem na liga, e em divergência o prêmio segue o que o banco
  contabilizou.
- **`qtde = 0` é guardado.** O analítico lista essas propostas para
  conferência com o banco (decisão do usuário).
- **`montar_acelerador_por_consultor` ganhou um parâmetro opcional** em
  vez de uma função paralela. A regra de universo e supervisor continua
  num lugar só.

## Pendências / follow-ups

- [ ] **Usuário:** aplicar a migration 127 no Supabase.
- [ ] **Usuário:** republicar a Edge Function `reconquista-rpc`. Sem isso,
      o import da liga falha no modo web (no Electron funciona).
- [ ] **Usuário:** importar `Reconquista_Setembro_Liga.xlsx` no angry-man
      com o período Set/26 e rodar as validações do rodapé da 127.
- [ ] Sinalizado, não removido:
      - `_marcar_vigencia_reconquista` ainda gera `apuracao_*` e
        `vigencia`, e as constantes `VIGENCIA_*` só são lidas por testes;
      - `por_loja` (apuração defasada) não é lido pela UI.

      Remover só com confirmação.
- [ ] O card de Promessas continua no `dt_fim` de M-1 (premissa adotada).
      Revisar se o negócio quiser outro recorte.

## Referências

- [business-rules.md § Liga](../business-rules.md)
- Migrations 028/053/093 (padrão da `reconquista`), 066 (vigência por `periodo_id`)
