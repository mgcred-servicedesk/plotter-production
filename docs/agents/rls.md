# Row-Level Security (RLS)

## Ordem obrigatória

Aplicar imediatamente após o carregamento de dados e **antes** de qualquer
filtro, cálculo ou render:

```python
from src.dashboard.rls import (
    aplicar_rls,
    aplicar_rls_metas,
    aplicar_rls_supervisores,
)

df       = aplicar_rls(df)
df_metas = aplicar_rls_metas(df_metas, df)
df_sup   = aplicar_rls_supervisores(df_sup, df)
```

- Nunca renderizar dados que não passaram por RLS.
- Nunca aplicar RLS após filtros de UI.
- A ordem importa: `aplicar_rls_metas` e `aplicar_rls_supervisores`
  dependem do `df` já filtrado.

## Hierarquia de perfis (do mais alto ao mais baixo)

| Perfil | Escopo | Acesso |
|---|---|---|
| `admin` | global | tudo + "Visualizar Como" qualquer perfil + gestão de usuários |
| `gestor` | global | visão consolidada das operações (read-only) |
| `gerente_comercial` | regiões (`escopo = [regiao, …]`) | dados das regiões atribuídas |
| `supervisor` | lojas (`escopo = [loja, …]`) | dados das lojas atribuídas |
| `consultor` | próprio usuário | apenas contratos do próprio `CONSULTOR` |

## "Visualizar Como"

`admin` pode simular qualquer combinação perfil × escopo via seletor na
sidebar. Útil para validar UX e RLS sem trocar de usuário.

## Contrato do `usuario_logado()`

```python
from src.dashboard.auth import tela_login, usuario_logado, fazer_logout, PERFIS

if not tela_login():
    return  # interrompe execução se não autenticado

user = usuario_logado()
# user = {"nome": str, "perfil": str, "escopo": list | None}

PERFIS  # dict: perfil_key → label legível
```

## Credenciais e armazenamento

- Default: `admin` / `admin123` — **obrigatório** trocar após primeiro login.
- Senhas: bcrypt.
- Usuários: tabela `usuarios` no Supabase.

## Estado atual da implementação

Os cinco perfis estão implementados no código em
[src/dashboard/auth.py](../../src/dashboard/auth.py) e
[src/dashboard/rls.py](../../src/dashboard/rls.py).

### Perfil `consultor`

Adicionado pela migration `006_perfil_consultor.sql`:

- Coluna `consultor_id` em `usuario_escopos` (FK → `consultores.id`).
- `CHECK` de exclusividade: cada escopo referencia exatamente **um** de
  `regiao_id` / `loja_id` / `consultor_id`.
- Policies RLS no Postgres: `pol_contratos_consultor` e
  `pol_metas_consultor` restringem o consultor aos próprios contratos e
  às metas da sua loja.

Na aplicação:

- `aplicar_rls(df, coluna_consultor="CONSULTOR")` filtra
  `df[df["CONSULTOR"].isin(escopo)]`.
- `aplicar_rls_supervisores` filtra supervisores pelas lojas onde o
  consultor tem contratos (derivado de `df[coluna_loja].unique()`).
- `obter_regioes_permitidas` retorna `[]` para `consultor` (sem filtro
  de região na sidebar).
- `carregar_metas_consultor(mes, ano, loja)` em `loaders.py` (com split
  `_atual`/`_historico`) carrega metas `CONSULTOR-sc` da loja.

### Matriz de permissões de UI

A decisão de **quais abas e cards renderizar** por perfil vive em
[src/dashboard/permissions.py](../../src/dashboard/permissions.py) via
`pode_ver(chave, role)`. Consultor, por exemplo, não vê
`cards_gerenciais` nem a maioria das abas — apenas `tab_consultor`
(Meu Dashboard) com os cards pessoais.
