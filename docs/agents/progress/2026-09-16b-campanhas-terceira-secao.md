# 2026-09-16 — Campanhas vira a terceira seção (era aba)

**Agente:** Claude Code
**Tipo:** refactor + feature
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/campanha.py`,
`src/dashboard/pages/campanhas.py` (novo), `src/dashboard/loaders.py`,
`src/dashboard/permissions.py`, `tests/test_kpis_campanha.py`,
`assets/campanhas/` (novo)
**Commit(s):** (branch `feat/campanha-semestral-2026h2`)

> Continuação de
> [2026-09-16-campanha-semestral-2026h2.md](2026-09-16-campanha-semestral-2026h2.md).
> A entrega anterior era uma **aba** dentro de Vendas; o usuário pediu
> que campanha fosse **evento em destaque**, irmã de Vendas e Pontuação.

## Objetivo

Promover Campanhas a terceira seção do `sac.segmented`, preparar o
terreno para campanhas futuras e abrir espaço para arte ilustrativa.

## O que foi feito

- Terceiro item no segmented (`dashboard_view = "campanhas"`).
- `tabs/campanha.py` → `pages/campanhas.py`. A chave `tab_campanha` saiu
  de `permissions.MATRIZ` (seção não é aba; não passa por `abas_visiveis`).
- `kpis/campanha.py` generalizado: `Campanha` (dataclass frozen) +
  registro `CAMPANHAS`. Toda função de apuração recebe a campanha.
- Descoberta de arte por prefixo em `assets/campanhas/<slug>/`.
- 48 testes (eram 35).

## Decisões não óbvias

- **Despacho ANTES de `carregar_periodo_dashboard`.** Campanha tem
  janela própria e não usa nada do mês da sidebar, então abrir a seção
  não paga a carga de Vendas (contratos do mês, metas, supervisores,
  análise, cancelados, reconquista e os seis grupos de KPI). Pontuação
  **não** pode fazer isso — depende de `kpis`, e por isso segue
  despachando lá embaixo. No compute Nano essa diferença é o que separa
  a seção de ser barata ou ser mais uma carga.

- **Supervisores passam a vir dos meses da campanha (união), não da
  sidebar.** Consequência direta do despacho antecipado: não há mais
  `df_sup_f`. É também mais correto — a campanha atravessa meses e há
  promoção de consultor a supervisor dentro da janela (migration 110).
  `carregar_consolidado_intervalo` passou a devolver
  `(df, df_supervisores, aviso)`.

- **Regra do promovido, confirmada com o usuário (16/09/2026):** a
  produção que ele fez como consultor **fica com a loja de origem** e
  como supervisor ele concorre **pela produção da loja que
  supervisiona**. O código já fazia isso sem querer, e agora está
  explícito: `excluir_supervisores` é aplicado **só** ao ranking de
  CONSULTOR; o ranking de LOJA usa o frame completo, e `contratos.loja_id`
  é por contrato — a produção dele nunca sai da loja onde foi feita.

- **Registro em vez de constantes de módulo.** Não sobrou nenhuma
  constante de campanha solta: `CAMPANHA_INICIO`, `META_VALOR` e afins
  viraram campos de `Campanha`. É o que faz a segunda campanha não
  precisar reabrir a primeira. `frozen=True` porque campanha em curso
  não muda de regra no meio.

- **`__post_init__` valida `familia_desempate` e a ordem das datas.**
  Desempate apontando para família inexistente daria ranking sem
  critério de desempate e ninguém perceberia — só os empates ficariam
  com a ordem arbitrária do sort.

- **Seletor de campanha só aparece com duas ou mais.** Um seletor de
  item único é ruído; a segunda entrada em `CAMPANHAS` o faz nascer.

- **Arte descoberta por prefixo, não configurada.** `hero.*`,
  `lateral*.*`, `rodape*.*` em `assets/campanhas/<slug>/`. Soltar o
  arquivo basta. `assets_da_campanha` engole `OSError` e pasta ausente:
  arte é ilustração, a ausência dela nunca pode derrubar a apuração.

- **`.gitkeep` na pasta da campanha.** Git não versiona diretório vazio;
  sem ele, um clone novo não teria `assets/campanhas/semestral-2026h2/`
  e `test_pasta_da_campanha_vigente_existe` falharia. Verificado com
  `git stash`.

## Pendências / follow-ups

Os quatro da entrada anterior seguem abertos (CNC_13 antes de novembro,
cache global, Power BI como fase 2, índice de `v_contratos_cancelados`).
Novos:

- [ ] **Arte da campanha ainda não existe.** A pasta está pronta e
      vazia; a página renderiza sem ela. Dimensões sugeridas em
      `assets/campanhas/README.md`.
- [ ] **Header da seção ainda recebe `mes`/`ano`** da sidebar, que a
      seção não usa. Não afeta número nenhum (é só o rótulo do período no
      topo), mas é incoerente — vale um header próprio de campanha.
- [ ] **Seletor de campanha persiste por rótulo**, não por slug
      (`st.selectbox` guarda o label). Renomear uma campanha reseta a
      seleção de quem estava com ela aberta. Irrelevante com uma
      campanha; revisar quando houver a segunda.

## Referências

- Entrada anterior:
  [2026-09-16-campanha-semestral-2026h2.md](2026-09-16-campanha-semestral-2026h2.md)
- Docs consultados: [ui-components.md](../ui-components.md),
  [conventions.md](../conventions.md), [rls.md](../rls.md)
