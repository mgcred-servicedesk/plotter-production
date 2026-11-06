# 2026-10-30 — Atualização e validação de dependências de segurança

**Agente:** Codex
**Tipo:** bugfix
**Arquivos tocados:** `requirements.txt`, `requirements-security.txt`, este registro
**Commit(s):** não realizado

## Objetivo
Atualizar as dependências vulneráveis, testar e avaliar a prontidão para deploy.

## O que foi feito
- Atualizado o ambiente canônico `.venv` e adicionadas constraints das versões instaladas e testadas.
- Streamlit 1.66.1, Pillow 13.0.0, certifi 2026.10.23 e demais correções de segurança.
- 1.915 testes passaram; testes de integração externa excluídos e conexões externas bloqueadas durante a suíte.
- Tela de login renderizada por AppTest sem erros; geração PNG e assinatura/validação JWT com dados sintéticos passaram.
- `pip check`, sintaxe dos fontes e resolução simulada de instalação limpa passaram.
- Consulta de versões instaladas ao PyPI não encontrou advisories ativos no ambiente canônico.

## Decisões não óbvias
- Streamlit foi atualizado porque a versão 1.61.1 impedia instalar o Pillow 13 corrigido.
- Constraints cobrem também os pacotes opcionais presentes no ambiente; não os instalam. Isso mantém versões testadas quando esses pacotes forem selecionados.
- Ambientes legados alternativos não foram modificados. Alterações prévias de regras e documentação foram preservadas.

## Pendências / follow-ups
- [ ] Validar login real, permissões e fluxos com dados em homologação antes de produção.
- [ ] Confirmar runtime Python e configuração do provedor de deploy; patch do sistema operacional não foi alterado.
- [ ] Revisar separadamente os ambientes legados apontados pelo monitor.

## Patterns criados ou atualizados
Nenhum.

## Referências
- [Índice dos agentes](../README.md)
- [Arquitetura](../architecture.md)
- Evidências locais: work/deploy-readiness-2026-10-30 e outputs/monitoramento-dependencias/2026-10-30-pos-atualizacao.json na conversa.
