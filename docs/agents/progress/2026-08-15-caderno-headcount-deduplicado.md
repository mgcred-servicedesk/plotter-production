# 2026-08-15 — Caderno: headcount deduplicado para produtividade

**Agente:** Codex
**Tipo:** bugfix de regra de negócio
**Arquivos tocados:** `database/migrations/073_caderno_headcount_deduplicado.sql`

## Problema

A migration 072 filtrava todas as linhas de `consultores` cujo status
começava por `ATIVO` e depois contava nomes distintos por loja. Como o RH
pode gravar uma nova linha para desligamento ou transferência sem remover a
linha ativa antiga, vínculos históricos continuavam no denominador da
produtividade.

Com os dados de 2026-08-15, a RPC publicada retornava 177 consultores para o
fechamento de junho. A mesma fonte, processada na ordem canônica do dashboard,
retornou 114; 30 lojas tinham diferença de headcount.

## Correção

A migration 073 substitui `obter_caderno_fechamento` mantendo todo o contrato
da 072 e altera apenas a formação do headcount:

1. normaliza o nome (`trim`, espaços internos e caixa);
2. conserva um registro por nome, escolhendo o maior `updated_at`;
3. aplica o status ativo por prefixo, preservando o comportamento legado de
   status vazio;
4. exclui nomes presentes na lista global normalizada de supervisores;
5. exclui consultores do backoffice `VAI E VEM`.

O `loja_id` usado é o do registro mais recente, portanto um vínculo anterior
não continua contando na loja de origem.

## Limitação temporal conhecida

`consultores` é uma fotografia do RH e não possui `periodo_id` nem vigência.
Assim, a migration replica exatamente o universo atual do dashboard, mas não
reconstrói qual era o headcount em uma competência passada. Para impedir que
uma atualização futura do RH altere um fechamento já publicado, o Caderno
deverá persistir o headcount no snapshot/versionamento do fechamento.
