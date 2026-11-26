# Segurança Python — 24/11/2026

## Escopo autorizado
Atualizar dependências vulneráveis, testar e avaliar a preparação para deploy. Não há alteração de regras de negócio, RLS, cache, dados ou entrypoint; nenhuma implantação foi feita.

## Research e plano
Foram lidos AGENTS, índice, arquitetura, regras de negócio, convenções, RPI, colaboração e orquestração. A autorização explícita do usuário cobre as atualizações e a execução dos testes, preservando trabalho existente. Alterações limitadas às constraints e ambientes Python ativos: Soup Sieve3.0.4→4.1.3 no legado e Tornado6.6→6.6.1 nos dois ambientes.

## Decisões
A constraint de Soup Sieve foi acrescentada ao requirements-security.txt para impedir a volta da versão afetada em instalações opcionais/legadas. Isso não instala Soup Sieve no .venv canônico, onde ele estava e continua ausente. Instalações com --no-deps evitaram movimentar pacotes não relacionados; pip check aprovou os ambientes. A existência do venv legado foi preservada, sem removê-lo ou desativá-lo unilateralmente.

## Validação
- .venv:1918 testes passaram (rede bloqueada pelo runner externo), Ruff limpo e sintaxe de72 arquivos aprovada.
- .venv/venv:pip check passou e Tornado6.6.1 confirmado.
- venv:Soup Sieve4.1.3, BeautifulSoup4.14.3 e nbconvert7.17.2 validados; seletores respeitam limite de template, iframe é filho normal e notebook viraHTML sem executar células ou acessar rede.
- Não existe build/empacotamento Python configurado na raiz; sintaxe e testes não são descritos como build de distribuição.

## Limitações e handoff
Sem commit/push/deploy ou confirmação em produção. Python Ubuntu, locks completos e ambientes aposentados permanecem frentes distintas. Evidências externas:work/remediation-2026-11-24/python/results.json no workspace da conversa. Atualizar o contexto do projeto com estes resultados ao integrar a mudança.
