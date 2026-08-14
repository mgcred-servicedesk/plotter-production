# 2026-08-13 — Nova aba "Cobranca Consignavel" em Analiticos

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/loaders.py`, `src/dashboard/tabs/analiticos.py`
**Commit(s):** — (pendente)

## Objetivo

Criar sub-aba dentro de Analiticos, entre Reconquista e Distribuicao de
Produtos, listando as propostas (contratos) que compoem a Cobranca
Consignavel do mes.

## O que foi feito

- `_COLS_COBRANCA_CONSIGNAVEL` (loaders.py) ganhou `contrato_id` e
  `num_proposta` — mesmo padrao de `_COLS_CONTRATOS_PAGOS` — para dar
  Nº ADE as linhas da listagem.
- `carregar_reconquista` passa a devolver `cobranca_consignavel_contratos`:
  o DataFrame ja RLS'd que a funcao ja calculava internamente so para
  `len()` (contagem do card). Nenhum fetch/RLS novo — reuso direto da
  variavel existente.
- `_render_cobranca_consignavel` (analiticos.py): nova sub-aba, reusa
  `_filtrar_loja_consultor` e `_nr_ade` ja existentes no arquivo. Tabela:
  Nº ADE, Data Pagamento, Loja, Consultor, Regiao, Banco, Valor, Valor
  Bruto + export CSV, no mesmo padrao das abas irmas (Aceleradores,
  Propostas Pagas).
- Aba inserida em `tab_items` entre "Reconquista" e "Distribuicao de
  Produtos", visivel a todos os perfis (inclusive consultor).

## Decisões não óbvias

- **Visivel ao consultor** (diferente de "Distribuicao de Produtos",
  oculta para esse perfil): a listagem é do próprio RLS-scoped do
  usuário — simétrico a "Propostas Pagas"/"Reconquista", que já são
  visíveis ao consultor. Cobrança Consignável premia o consultor
  individualmente, então ver as próprias propostas que contam faz
  sentido.
- **Mostra Valor + Valor Bruto**, não só Valor: é exatamente o par que
  define se a linha qualifica (`VLR BRUTO != VLR BASE`), útil para
  auditoria. Não mostra TIPO OPER./SUBTIPO — são constantes por
  construção do filtro (sempre CONTRATO NOVO/NOVO), sem valor
  informativo na tabela.
- **Vazio tratado de forma única** (não distingue "fora da vigência
  < 08/2026" de "vigente mas sem propostas no período"): mesma
  mensagem genérica de "sem dados", consistente com as abas irmãs
  (Propostas Pagas, Cancelados etc.) — evita complexidade extra sem
  ganho real para o usuário.
- **Sem novo fetch**: a Cobranca Consignavel já era calculada dentro de
  `carregar_reconquista` (RLS aplicado, TTL de cache já resolvido);
  bastou expor a variável que já existia, em vez de chamar
  `carregar_cobranca_consignavel` de novo a partir da UI (evitaria
  reaplicar RLS/refetch redundante).

## Verificação

- `.venv/bin/ruff check src/ app.py` limpo.
- `.venv/bin/python -m pytest tests/` — 548 passed (suíte completa, sem
  regressão).
- `streamlit run app.py` sobe sem erro (HTTP 200); a tela de login
  impediu verificação visual completa da aba sem credenciais reais.
- Smoke test manual (script em `/tmp`, não commitado): chamou
  `_render_cobranca_consignavel` com DataFrame sintético (2 linhas) e
  com DataFrame vazio, stubando `st.*`/`exibir_tabela` — confirmou
  colunas da tabela, métricas (Quantidade/Valor Total) e mensagem do
  caso vazio corretas; confirmou via `inspect` que a ordem das abas é
  Reconquista < Cobranca Consignavel < Distribuicao de Produtos.

## Pendências / follow-ups

- Nenhum teste automatizado dedicado foi adicionado (`tests/`) — mesma
  lacuna já sinalizada no progress anterior
  (`2026-08-11-acelerador-combinado-reconquista-cobranca-consignavel.md`)
  para toda a feature de Cobrança Consignável/acelerador combinado.
  Funções de renderização deste arquivo não têm testes dedicados hoje
  (só helpers puros, ver `tests/test_tabs_analiticos.py`), então isso
  segue o padrão existente do arquivo, não é uma lacuna nova.
- Verificação visual em browser (login real) não foi feita — sem
  credenciais de teste disponíveis nesta sessão.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) §
  "Cobrança Consignável — critério", [architecture.md](../architecture.md)
- Progress relacionado:
  [2026-08-11-acelerador-combinado-reconquista-cobranca-consignavel.md](2026-08-11-acelerador-combinado-reconquista-cobranca-consignavel.md)
