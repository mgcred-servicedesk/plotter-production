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

O código em [src/dashboard/auth.py](../../src/dashboard/auth.py) e
[src/dashboard/rls.py](../../src/dashboard/rls.py) atualmente suporta
`admin`, `gestor`, `gerente_comercial`, `supervisor`. O perfil
`consultor` **está documentado aqui como parte da hierarquia esperada**
mas ainda não está implementado no código — adicionar exige:

1. Entrada no dict `PERFIS` em `auth.py`.
2. Ramo em `aplicar_rls` filtrando `df[df["CONSULTOR"] == user["nome"]]`
   (ou via `escopo`).
3. Definir comportamento de `aplicar_rls_metas` e `aplicar_rls_supervisores` para esse perfil.
