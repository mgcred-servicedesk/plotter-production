# 2026-09-16 — Condições de premiação da Campanha Semestral

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/campanha.py`,
`src/dashboard/pages/campanhas.py`, `tests/test_kpis_campanha.py`
**Commit(s):** `71dad08` + este

> Terceira entrada do dia. Ver
> [a primeira](2026-09-16-campanha-semestral-2026h2.md) (apuração) e
> [a segunda](2026-09-16b-campanhas-terceira-secao.md) (seção e arte).

## Objetivo

Modelar a premiação: quantos consultores e lojas são contemplados,
conforme quais metas a campanha atinge.

## A regra (usuário, 09/2026)

| Degrau | Exige | Consultores | Lojas |
|---|---|---:|---:|
| 1ª | meta global R$ 75 mi | 8 | 4 |
| 2ª | 1ª **+** CNC R$ 23 mi | 12 | 6 |
| 3ª | 1ª **+** 2ª **+** CLT R$ 7,5 mi | 16 | 8 |

**Cumulativos e estritos.** Sem a global ninguém é contemplado, mesmo
com CNC e CLT batidos. CLT sem CNC não passa de 8/4.

## Decisões não óbvias

- **`atingida` e `liberada` são coisas diferentes, e as duas são
  expostas.** Um degrau pode estar batido e não valer, porque a cascata
  parou antes. É a informação mais fácil de interpretar errado na
  página inteira: quem vê "CNC 100%" sem o aviso conclui que ganhou. A
  tabela marca esse caso como "Atingida, mas travada".

- **`contemplacao` para no primeiro degrau que falha**, em vez de contar
  os atingidos. Sem isso, CNC+CLT sem global dariam 16/8.

- **Premiado é COLUNA, não destaque visual.** Ela viaja no CSV, e a
  lista de premiados é justamente o que sai da tela para virar
  pagamento. `highlight_mask` só funciona no caminho `st.dataframe`
  (`exibir_tabela` usa AG Grid por padrão) e não exporta.

- **O corte é pela POSIÇÃO densa, não pela linha.** Empate exato —
  mesmos pontos **e** mesma produção de desempate — na fronteira
  contempla os dois. Cortar por linha escolheria um vencedor pela ordem
  que o `sort` deixou por acaso, que é o que a posição densa existe para
  evitar. **Consequência aceita:** 9 contemplados para 8 vagas, num
  empate perfeito.

- **Valores de CNC e CLT vêm da arte oficial** (`rodape-2.png`), que
  quebra os R$ 75 mi em 44,5 + 23 + 7,5. Confirmados pelo usuário em
  16/09/2026 e pinados em `TestContratoConfirmadoDaPremiacao` — decidem
  pagamento, então um ajuste silencioso não pode passar.

- **O bloco de R$ 44,5 mi (Consignado + Antecipação + FGTS) fica fora
  por ora** — decisão do usuário, palavra dele: "no momento". Existe na
  arte e pode virar a 4ª condição.

  **Incluir não é só acrescentar uma linha:** `Condicao.familia` aponta
  para UMA família, e o bloco abrange três (`Consignado`,
  `Ant. de Benef.`, `FGTS`). Exigiria agrupá-las numa família só — o que
  muda a tabela "Produção por família" — ou permitir várias famílias por
  condição. Não generalizei preventivamente: a condição está fora, e o
  custo de fazer depois está registrado aqui.

- **Duas guardas novas em `__post_init__`:** condição para família
  inexistente (mediria zero e nunca seria atingida, calada) e degrau que
  contemple menos que o anterior (a cascata só avança). A primeira já
  pegou uma inconsistência num teste existente que trocava as famílias
  e deixava as condições órfãs.

## Verificação

Quatro sabotagens da cascata, todas pegas pela suíte: ignorar a ordem
dos degraus; `>` em vez de `>=` na meta; zero contemplados virando
degrau 1; corte do premiado por linha em vez de posição.

Estado real em 16/09/2026: global 34,0%, CNC 40,6%, CLT 32,9% — nenhuma
atingida, **0 contemplados**. Suíte: 1241 passam.

## Pendências / follow-ups

- [ ] **Empate na fronteira** — a regra "posição densa contempla os dois"
      é decisão de premiação, implementada como default defensável. Vale
      confirmar com quem paga.
- [ ] **4ª condição (R$ 44,5 mi)**, se voltar — ver a nota de modelagem
      acima.
- [ ] Os quatro follow-ups das entradas anteriores seguem abertos, com
      destaque para **CNC_13 antes de novembro**: o `grupo_meta` dele no
      banco é `FGTS_ANT_BENEF_13`, exatamente o bloco de R$ 44,5 mi.
