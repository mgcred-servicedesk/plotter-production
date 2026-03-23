"""
Script de diagnóstico para identificar divergências
no cálculo de valor e pontos do dashboard Supabase.

Usa requests direto na REST API (sem SDK supabase).
"""
import json
import os
import sys
from urllib.parse import quote

# python-dotenv está no venv
from dotenv import load_dotenv
import requests

load_dotenv()

BASE_URL = os.getenv("SUPABASE_URL", "")
API_KEY = os.getenv("SUPABASE_KEY", "")
HEADERS = {
    "apikey": API_KEY,
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

MES = 3
ANO = 2026


def rest_get(table, params=None, count=False):
    """GET na REST API do Supabase."""
    url = f"{BASE_URL}/rest/v1/{table}"
    h = {**HEADERS}
    if count:
        h["Prefer"] = "count=exact"
    resp = requests.get(url, headers=h, params=params or {})
    resp.raise_for_status()
    data = resp.json()
    cnt = None
    if count and "content-range" in resp.headers:
        rng = resp.headers["content-range"]
        cnt = int(rng.split("/")[1]) if "/" in rng else None
    return data, cnt


def rpc_call(fn_name, body):
    """POST em rpc/function."""
    url = f"{BASE_URL}/rest/v1/rpc/{fn_name}"
    resp = requests.post(url, headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()


def header(titulo):
    print(f"\n{'=' * 60}")
    print(f"  {titulo}")
    print(f"{'=' * 60}")


# ── 1. Período ──────────────────────────────────────────────
header("1. PERIODO")
periodos, _ = rest_get("periodos", {
    "select": "id,mes,ano,referencia",
    "mes": f"eq.{MES}",
    "ano": f"eq.{ANO}",
})
if not periodos:
    print("ERRO: Período não encontrado!")
    sys.exit(1)

periodo = periodos[0]
periodo_id = periodo["id"]
print(f"Período: {periodo['referencia']} (id={periodo_id})")


# ── 2. Pontuação efetiva ────────────────────────────────────
header("2. PONTUACAO EFETIVA (RPC obter_pontuacao_periodo)")
pontuacao = rpc_call("obter_pontuacao_periodo", {
    "p_mes": MES, "p_ano": ANO,
})

print(f"Total categorias com pontuação: {len(pontuacao)}")
for p in sorted(pontuacao, key=lambda x: x.get("categoria_codigo", "")):
    fb = " [FALLBACK]" if p.get("is_fallback") else ""
    print(
        f"  {p['categoria_codigo']:20s} → "
        f"pontos={p['pontos']:>8} "
        f"origem={p.get('periodo_origem', '?')}{fb}"
    )

mapa_pontos = {
    p["categoria_codigo"]: float(p["pontos"])
    for p in pontuacao
}


# ── 3. Categorias de produto ────────────────────────────────
header("3. CATEGORIAS_PRODUTO (conta_valor / conta_pontuacao)")
cats_data, _ = rest_get("categorias_produto", {
    "select": "codigo,nome,conta_valor,conta_pontuacao,ativo",
    "ativo": "eq.true",
    "order": "ordem",
})
categorias = {c["codigo"]: c for c in (cats_data or [])}
print(f"Total categorias ativas: {len(categorias)}")
for cod, c in categorias.items():
    cv = "V" if c["conta_valor"] else "-"
    cp = "P" if c["conta_pontuacao"] else "-"
    print(f"  {cod:20s} conta_valor={cv}  conta_pontuacao={cp}")


# ── 4. Contratos pagos ──────────────────────────────────────
header("4. CONTRATOS PAGOS DO PERIODO")

# Contar total
_, total_contratos = rest_get("contratos", {
    "select": "id",
    "periodo_id": f"eq.{periodo_id}",
    "status_pagamento_cliente": "eq.PAGO AO CLIENTE",
    "limit": "1",
}, count=True)
print(f"Total contratos pagos: {total_contratos}")

# Buscar com joins (paginado)
_select = (
    "id,valor,"
    "produtos(id,tabela,tipo,subtipo,categoria_id,"
    "categorias_produto(id,codigo,nome,"
    "conta_valor,conta_pontuacao))"
)

PAGE = 1000
all_data = []
offset = 0
while True:
    batch, _ = rest_get("contratos", {
        "select": _select,
        "periodo_id": f"eq.{periodo_id}",
        "status_pagamento_cliente": "eq.PAGO AO CLIENTE",
        "limit": str(PAGE),
        "offset": str(offset),
    })
    all_data.extend(batch)
    if len(batch) < PAGE:
        break
    offset += PAGE

print(f"Contratos carregados: {len(all_data)}")


# ── 5. Análise por categoria ────────────────────────────────
header("5. ANALISE POR CATEGORIA")

from collections import defaultdict

por_categoria = defaultdict(lambda: {
    "qtd": 0, "valor": 0.0, "pontos_calc": 0.0,
    "conta_valor": None, "conta_pontuacao": None,
    "tipo_produto": set(),
})

sem_produto = 0
sem_categoria = 0
sem_categoria_id = 0

for c in all_data:
    valor = float(c.get("valor", 0))
    produto = c.get("produtos") or {}
    categoria = produto.get("categorias_produto") or {}

    if not produto:
        sem_produto += 1
        cat_codigo = "__SEM_PRODUTO__"
    elif not categoria or not categoria.get("codigo"):
        sem_categoria_id += 1
        tipo = produto.get("tipo", "?")
        cat_codigo = f"__SEM_CAT__(tipo={tipo})"
    else:
        cat_codigo = categoria["codigo"]

    info = por_categoria[cat_codigo]
    info["qtd"] += 1
    info["valor"] += valor
    if categoria:
        info["conta_valor"] = categoria.get("conta_valor")
        info["conta_pontuacao"] = categoria.get("conta_pontuacao")
    if produto.get("tipo"):
        info["tipo_produto"].add(produto["tipo"])

    # Calcular pontos como o dashboard faria
    mult = mapa_pontos.get(cat_codigo, 0)
    info["pontos_calc"] += valor * mult

print(f"\nContratos sem produto_id:      {sem_produto}")
print(f"Contratos sem categoria_id:    {sem_categoria_id}")

# Tabela detalhada
total_valor_all = 0.0
total_valor_cv = 0.0
total_pontos = 0.0
total_pontos_cp = 0.0

print(
    f"\n{'Categoria':25s} {'Qtd':>6s} {'Valor':>15s} "
    f"{'Pontos':>15s} {'CV':>3s} {'CP':>3s} {'Mult':>6s} "
    f"{'Tipos'}"
)
print("-" * 110)

for cat_cod in sorted(por_categoria.keys()):
    info = por_categoria[cat_cod]
    cv = info["conta_valor"]
    cp = info["conta_pontuacao"]
    cv_str = "T" if cv is True else ("F" if cv is False else "?")
    cp_str = "T" if cp is True else ("F" if cp is False else "?")
    mult = mapa_pontos.get(cat_cod, 0)
    tipos = ", ".join(sorted(info["tipo_produto"])) or "-"

    total_valor_all += info["valor"]
    if cv is not False:  # True ou None (default True)
        total_valor_cv += info["valor"]
    total_pontos += info["pontos_calc"]
    if cp is not False:
        total_pontos_cp += info["pontos_calc"]

    print(
        f"{cat_cod:25s} {info['qtd']:>6d} "
        f"{info['valor']:>15,.2f} "
        f"{info['pontos_calc']:>15,.2f} "
        f"{cv_str:>3s} {cp_str:>3s} {mult:>6.2f} "
        f"{tipos[:30]}"
    )

header("6. TOTAIS")
print(f"Valor TODOS os contratos:            R$ {total_valor_all:>15,.2f}")
print(f"Valor com conta_valor=True/None:     R$ {total_valor_cv:>15,.2f}")
print(f"Pontos TODOS:                        {total_pontos:>15,.2f}")
print(f"Pontos com conta_pontuacao=True/None:{total_pontos_cp:>15,.2f}")
print()
print(f"Valor esperado pelo usuario:         R$  9.670.368,25")
print(f"Valor mostrado no dashboard:         R$ 10.146.358,55")
print(f"Diferenca:                           R$    475.990,30")
print()

# Detalhar categorias com conta_valor=False
header("7. CATEGORIAS COM conta_valor=FALSE (devem ser excluidas)")
for cat_cod in sorted(por_categoria.keys()):
    info = por_categoria[cat_cod]
    if info["conta_valor"] is False:
        print(
            f"  {cat_cod:25s} qtd={info['qtd']:>5d}  "
            f"valor=R$ {info['valor']:>12,.2f}"
        )

# Categorias com conta_valor=None (sem mapeamento)
header("8. CONTRATOS SEM CATEGORIA (conta_valor default=True)")
for cat_cod in sorted(por_categoria.keys()):
    info = por_categoria[cat_cod]
    if info["conta_valor"] is None:
        print(
            f"  {cat_cod:25s} qtd={info['qtd']:>5d}  "
            f"valor=R$ {info['valor']:>12,.2f}  "
            f"tipos={', '.join(sorted(info['tipo_produto']))}"
        )

# Categorias sem multiplicador de pontos
header("9. CATEGORIAS SEM MULTIPLICADOR NA PONTUACAO")
for cat_cod in sorted(por_categoria.keys()):
    if cat_cod.startswith("__"):
        continue
    info = por_categoria[cat_cod]
    mult = mapa_pontos.get(cat_cod, 0)
    if mult == 0 and info["valor"] > 0:
        print(
            f"  {cat_cod:25s} qtd={info['qtd']:>5d}  "
            f"valor=R$ {info['valor']:>12,.2f}  "
            f"pontos_perdidos!"
        )

print("\n✅ Diagnóstico completo.")
