# 2026-11-03 — Correções de segurança nos ambientes Python

**Agente:** Codex (subtarefa de dependências Python)
**Tipo:** bugfix
**Arquivos tocados:** `.python-version`, este registro; pacotes locais dos ambientes `.venv` e `venv` (ignorados pelo Git)
**Commit(s):** não realizado

## Objetivo
Corrigir as CVEs identificadas desde 30/10, incluindo o ambiente Python antigo que ainda estava vulnerável.

## O que foi feito
- Python 3.12.16 e OpenSSL 3.5.9 em ambos os ambientes locais, com base isolada em `~/.local/share/mgcred-security-python/`; Python do sistema não alterado.
- Atualizadas as dependências vulneráveis de `venv`, incluindo GitPython, PyJWT, AnyIO, Certifi, Pillow, Cryptography, urllib3, Jupyter e ferramentas.
- Ambiente antigo alinhado aos requisitos atuais do projeto (Pandas 3.0.5, NumPy 2.5.1, Plotly 6.9.0, SDKs e Supabase). As regras de negócio não foram alteradas.
- 1.915 testes passaram no ambiente antigo já corrigido, excluindo integração externa; conexões externas bloqueadas durante a suíte.
- Tela de login por AppTest, PNG e JWT passaram no ambiente canônico com o novo runtime.
- `pip check` passou. Auditoria PyPI dos ambientes ativos não encontrou avisos para as versões instaladas.

## Decisões não óbvias
- `venv --upgrade` sozinho preservava aliases `python` e `python3` apontando ao binário Ubuntu antigo; os aliases foram corrigidos para a base 3.12.16, com validação real de `sys.version`, SSL e dependências.
- As três falhas iniciais da suíte antiga refletiam o Pandas 2 do ambiente, incompatível com os requisitos atuais já fixados em Pandas 3. O ambiente foi alinhado ao manifesto, sem modificar normalização de nulos ou regras de negócio.
- O runtime do sistema Ubuntu e o runtime empacotado do Codex foram preservados. Os ambientes dos projetos usam a distribuição corrigida isolada.

## Pendências / follow-ups
- [ ] Publicar as correções somente pelo processo de deploy autorizado e validar fluxos autenticados no destino.
- [ ] Confirmar runtime efetivo do provedor; atualização local não comprova implantação em produção.

## Patterns criados ou atualizados
Nenhum.

## Referências
- [Arquitetura](../architecture.md)
- [Regras de negócio](../business-rules.md)
- Evidências da conversa: `work/cve-remediation-2026-11-03/python/` (JUnit, relatórios pip, inventários e runtimes).
