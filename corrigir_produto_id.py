"""
Script de correção: atualiza produto_id nos contratos
que foram importados sem vínculo com a tabela de produtos.

Lê a planilha de digitação, faz match CONTRATO_ID ↔ TABELA,
resolve o produto_id no banco e atualiza os contratos.

Uso: python corrigir_produto_id.py [caminho_planilha]
     Default: digitacao/marco_2026.xlsx
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd
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

PLANILHA = sys.argv[1] if len(sys.argv) > 1 else "digitacao/marco_2026.xlsx"


def rest_get(table, params=None):
    url = f"{BASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=HEADERS, params=params or {})
    resp.raise_for_status()
    return resp.json()


def rest_patch(table, params, body):
    url = f"{BASE_URL}/rest/v1/{table}"
    resp = requests.patch(
        url, headers=HEADERS, params=params, json=body,
    )
    resp.raise_for_status()
    return resp.json()


def header(titulo):
    print(f"\n{'=' * 60}")
    print(f"  {titulo}")
    print(f"{'=' * 60}")


# ── 1. Carregar lookup de produtos (tabela → id) ────────────
header("1. CARREGANDO PRODUTOS DO BANCO")
all_prod = []
offset = 0
while True:
    batch = rest_get("produtos", {
        "select": "id,tabela",
        "limit": "1000",
        "offset": str(offset),
    })
    all_prod.extend(batch)
    if len(batch) < 1000:
        break
    offset += 1000

produtos_map = {p["tabela"]: p["id"] for p in all_prod}
print(f"Produtos no banco: {len(produtos_map)}")


# ── 2. Ler planilha ─────────────────────────────────────────
header("2. LENDO PLANILHA")
df = pd.read_excel(PLANILHA)
print(f"Linhas na planilha: {len(df)}")

if "CONTRATO ID" not in df.columns or "TABELA" not in df.columns:
    print("ERRO: Planilha precisa ter colunas 'CONTRATO ID' e 'TABELA'")
    sys.exit(1)

df = df[["CONTRATO ID", "TABELA"]].dropna(subset=["CONTRATO ID", "TABELA"])
df["CONTRATO ID"] = df["CONTRATO ID"].astype(int)
print(f"Linhas com CONTRATO ID + TABELA: {len(df)}")


# ── 3. Resolver produto_id ──────────────────────────────────
header("3. RESOLVENDO PRODUTO_ID")
df["produto_id"] = df["TABELA"].map(produtos_map)

com_match = df["produto_id"].notna().sum()
sem_match = df["produto_id"].isna().sum()
print(f"Com match: {com_match}")
print(f"Sem match: {sem_match}")

if sem_match > 0:
    sem = df[df["produto_id"].isna()]["TABELA"].unique()
    print("TABELAs sem match:")
    for t in sorted(sem)[:10]:
        print(f"  - {t}")


# ── 4. Buscar contratos sem produto_id ──────────────────────
header("4. CONTRATOS SEM PRODUTO_ID NO BANCO")

contrato_ids = df["CONTRATO ID"].tolist()

# Buscar em lotes (url query limit)
BATCH = 200
contratos_sem_prod = {}
for i in range(0, len(contrato_ids), BATCH):
    lote = contrato_ids[i:i + BATCH]
    ids_str = ",".join(str(c) for c in lote)
    result = rest_get("contratos", {
        "select": "id,contrato_id,produto_id",
        "contrato_id": f"in.({ids_str})",
        "produto_id": "is.null",
    })
    for r in result:
        contratos_sem_prod[r["contrato_id"]] = r["id"]

print(f"Contratos sem produto_id encontrados: {len(contratos_sem_prod)}")


# ── 5. Atualizar ────────────────────────────────────────────
header("5. ATUALIZANDO CONTRATOS")

# Preparar mapa contrato_id → produto_id
df_para_atualizar = df[
    (df["CONTRATO ID"].isin(contratos_sem_prod))
    & (df["produto_id"].notna())
].copy()

print(f"Contratos a atualizar: {len(df_para_atualizar)}")

if len(df_para_atualizar) == 0:
    print("Nada a fazer!")
    sys.exit(0)

# Confirmar antes de prosseguir
resposta = input(
    f"\nAtualizar {len(df_para_atualizar)} contratos? (s/n): "
)
if resposta.lower() != "s":
    print("Cancelado.")
    sys.exit(0)

# Atualizar em lotes
UPDATE_BATCH = 50
atualizados = 0
erros = 0

for i in range(0, len(df_para_atualizar), UPDATE_BATCH):
    lote = df_para_atualizar.iloc[i:i + UPDATE_BATCH]

    for _, row in lote.iterrows():
        contrato_id = int(row["CONTRATO ID"])
        produto_id = row["produto_id"]
        try:
            rest_patch(
                "contratos",
                {"contrato_id": f"eq.{contrato_id}"},
                {"produto_id": produto_id},
            )
            atualizados += 1
        except Exception as e:
            erros += 1
            if erros <= 5:
                print(f"  ERRO contrato {contrato_id}: {e}")

    progresso = min(i + UPDATE_BATCH, len(df_para_atualizar))
    print(
        f"  Progresso: {progresso}/{len(df_para_atualizar)} "
        f"(ok={atualizados}, erros={erros})"
    )

header("RESULTADO")
print(f"Atualizados: {atualizados}")
print(f"Erros: {erros}")
print(f"Total processados: {atualizados + erros}")
