# CLAUDE.md — Regras de comportamento (Claude Code)

Este arquivo contém **apenas** regras de comportamento específicas do
Claude Code. Todo conhecimento de projeto (arquitetura, regras de
negócio, padrões, convenções) mora em [`docs/agents/`](docs/agents/README.md).

## Antes de qualquer mudança — leia

1. [`AGENTS.md`](AGENTS.md) — ponto de entrada canônico (princípios inegociáveis).
2. [`docs/agents/README.md`](docs/agents/README.md) — índice completo.
3. O documento específico para a área que você vai tocar:
   - Arquitetura: [`docs/agents/architecture.md`](docs/agents/architecture.md)
   - Regras de negócio: [`docs/agents/business-rules.md`](docs/agents/business-rules.md)
   - Supabase / cache: [`docs/agents/data-layer.md`](docs/agents/data-layer.md)
   - RLS / perfis: [`docs/agents/rls.md`](docs/agents/rls.md)
   - Convenções (naming, formatters, Width API, cores): [`docs/agents/conventions.md`](docs/agents/conventions.md)
   - Componentes de UI (sac, exibir_tabela, tab renderer): [`docs/agents/ui-components.md`](docs/agents/ui-components.md)

---

## Antes de codar

- Exponha sua compreensão da tarefa antes de escrever código.
- Confirme o plano com o usuário antes de começar.
- Se faltar informação, liste perguntas em aberto — nunca inferir requisitos.
- Apresente opções e trade-offs quando houver mais de uma abordagem.
- Identifique quais arquivos/módulos a mudança toca antes de propor.

## Durante a implementação

- **Nunca instale novos pacotes sem pedir antes.**
- Prefira editar código existente a criar novas abstrações.
- Em refatoração, mude **apenas** o que a tarefa pede — sem limpezas não relacionadas.
- Não introduza padrões novos (não presentes no codebase) sem sinalizar.
- Siga convenções existentes sem perguntar; documente a escolha depois se não existir convenção.
- Tratamento de erros: siga padrão existente. Se não houver e impacto for baixo, use idioma da linguagem e documente. Alto impacto → pare e discuta.
- **Nunca engula erros silenciosamente.**

### Exclusão de código

- Nunca apague ou deprecie código unilateralmente.
- Se parecer não usado, **sinalize**: descreva o que é, por que parece desnecessário, consequência de remover.
- Aguarde confirmação explícita antes de remover.

## Após codar

- Rode `ruff check` e corrija erros que você introduziu.
- Resuma decisões tomadas, alternativas descartadas e por quê.
- Liste premissas explicitamente para o usuário validar.
- Registre decisões não óbvias em [`docs/agents/progress/`](docs/agents/progress/) (use o template).
- Peça ao usuário para atualizar contexto do projeto quando a tarefa fechar.

## Tiers de decisão

| Ação | Regra |
|---|---|
| Seguir padrões existentes, corrigir próprios erros | Fazer sempre — sem confirmação |
| Novos arquivos com decisão estrutural, novas dependências, tratamento de erro sem padrão | Perguntar primeiro |
| Apagar/deprecar código, criar arquivos de config/infra, alterar APIs públicas, logar credenciais | Nunca sem instrução explícita |

- Todas as decisões de impacto duradouro pertencem ao usuário.
- Velocidade nunca é motivo para pular confirmação.
- Se uma instrução introduz risco ou débito, diga claramente uma vez — depois siga o que o usuário decidir, salvo problema irreversível.

## Contribuição à base de conhecimento

Quando descobrir/decidir algo não óbvio, contribua de volta:

- **Padrão reutilizável?** Copie [`docs/agents/patterns/TEMPLATE.md`](docs/agents/patterns/TEMPLATE.md) e crie `docs/agents/patterns/<slug>.md`.
- **Decisão não óbvia no fim da sessão?** Anexe entrada em [`docs/agents/progress/`](docs/agents/progress/) (append-only — nunca edite entradas anteriores).
- **Divergência doc × código?** O código é a verdade. Corrija o doc ou abra follow-up no `progress/`.

## Rodando o projeto

```bash
# Dashboard (entrypoint único)
streamlit run app.py

# Relatórios Excel
python gerar_relatorio.py

# Relatórios PDF
python gerar_relatorio_pdf.py
```

Saídas: `outputs/relatorios_excel/` e `outputs/relatorios_pdf/`.

## Testes e lint

```bash
pytest tests/
ruff check src/
```

Testes em `tests/`; organização em `tests/README.md`.
