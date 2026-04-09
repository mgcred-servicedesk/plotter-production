"""
Script de diagnostico para identificar a diferenca entre o valor
esperado (14.661.855,85) e o valor calculado no dashboard (14.869.959,15).

Diferenca: R$ 208.103,30

Verifica:
1. Contratos sem categoria mapeada que mantem VALOR > 0
2. Contratos com conta_valor incorreto
3. Valor por categoria/tipo_operacao antes e depois das exclusoes
4. Produtos de emissao/seguro que possam estar "vazando" valor
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from supabase import create_client

VALOR_ESPERADO = 14_661_855.85
VALOR_DASHBOARD = 14_869_959.15
DIFERENCA = VALOR_DASHBOARD - VALOR_ESPERADO

sb = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)


def carregar_dados(mes: int, ano: int) -> pd.DataFrame:
    """Carrega contratos pagos da view, identico ao app.py."""
    # Buscar periodo
    resp = (
        sb.table("periodos")
        .select("id, mes, ano")
        .eq("mes", mes)
        .eq("ano", ano)
        .limit(1)
        .execute()
    )
    if not resp.data:
        print(f"Periodo {mes}/{ano} nao encontrado!")
        sys.exit(1)

    periodo_id = resp.data[0]["id"]
    print(f"Periodo: {mes}/{ano} (id={periodo_id})")

    # Paginar contratos
    all_data = []
    offset = 0
    page_size = 1000
    while True:
        batch = (
            sb.from_("v_contratos_dashboard")
            .select("*")
            .eq("periodo_id", periodo_id)
            .order("id")
            .limit(page_size)
            .offset(offset)
            .execute()
        )
        rows = batch.data or []
        all_data.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    print(f"Total de contratos carregados: {len(all_data)}")

    rows = []
    for c in all_data:
        rows.append({
            "CONTRATO_ID": c.get("contrato_id"),
            "LOJA": c.get("loja", ""),
            "CONSULTOR": c.get("consultor", ""),
            "PRODUTO": c.get("produto", ""),
            "TIPO_PRODUTO": c.get("tipo_produto", ""),
            "SUBTIPO": c.get("subtipo", ""),
            "TIPO OPER.": c.get("tipo_operacao", ""),
            "VALOR": float(c.get("valor", 0)),
            "BANCO": c.get("banco", ""),
            "categoria_codigo": c.get("categoria_codigo", ""),
            "grupo_dashboard": c.get("grupo_dashboard"),
            "grupo_meta": c.get("grupo_meta"),
            "conta_valor": c.get("conta_valor", True),
            "conta_pontuacao": c.get("conta_pontuacao", True),
            "status_pagamento_cliente": c.get(
                "status_pagamento_cliente", ""
            ),
            "sub_status_banco": c.get("sub_status_banco", ""),
        })

    return pd.DataFrame(rows)


def diagnosticar(df: pd.DataFrame):
    """Executa todos os diagnosticos."""
    print("\n" + "=" * 70)
    print("DIAGNOSTICO DE VALOR TOTAL")
    print("=" * 70)

    valor_bruto_total = df["VALOR"].sum()
    print(f"\n1. VALOR BRUTO (antes de exclusoes): "
          f"R$ {valor_bruto_total:,.2f}")
    print(f"   Valor esperado:  R$ {VALOR_ESPERADO:,.2f}")
    print(f"   Valor dashboard: R$ {VALOR_DASHBOARD:,.2f}")
    print(f"   Diferenca:       R$ {DIFERENCA:,.2f}")

    # ── 2. Analise por conta_valor ──────────────────
    print("\n2. ANALISE POR conta_valor:")
    for cv in [True, False, None]:
        if cv is None:
            mask = df["conta_valor"].isna()
            label = "NULL/NaN"
        else:
            mask = df["conta_valor"] == cv
            label = str(cv)
        sub = df[mask]
        print(f"   conta_valor={label}: "
              f"{len(sub)} contratos, "
              f"VALOR = R$ {sub['VALOR'].sum():,.2f}")

    # ── 3. Contratos SEM categoria ──────────────────
    print("\n3. CONTRATOS SEM CATEGORIA (categoria_codigo vazio/NULL):")
    sem_cat = df[
        (df["categoria_codigo"] == "")
        | df["categoria_codigo"].isna()
    ]
    print(f"   Quantidade: {len(sem_cat)}")
    print(f"   Valor total: R$ {sem_cat['VALOR'].sum():,.2f}")
    if not sem_cat.empty:
        print("\n   Detalhamento por TIPO_PRODUTO:")
        det = (
            sem_cat.groupby("TIPO_PRODUTO")
            .agg(qtd=("VALOR", "size"), valor=("VALOR", "sum"))
            .sort_values("valor", ascending=False)
        )
        for idx, row in det.iterrows():
            print(f"     {idx}: {row['qtd']} contratos, "
                  f"R$ {row['valor']:,.2f}")

        print("\n   Detalhamento por TIPO OPER.:")
        det2 = (
            sem_cat.groupby("TIPO OPER.")
            .agg(qtd=("VALOR", "size"), valor=("VALOR", "sum"))
            .sort_values("valor", ascending=False)
        )
        for idx, row in det2.iterrows():
            print(f"     {idx}: {row['qtd']} contratos, "
                  f"R$ {row['valor']:,.2f}")

    # ── 4. Valor por categoria ──────────────────────
    print("\n4. VALOR POR CATEGORIA (conta_valor=True):")
    com_valor = df[df["conta_valor"] == True]  # noqa
    det_cat = (
        com_valor.groupby("categoria_codigo")
        .agg(qtd=("VALOR", "size"), valor=("VALOR", "sum"))
        .sort_values("valor", ascending=False)
    )
    for idx, row in det_cat.iterrows():
        marca = ""
        if idx in ("CARTAO", "BMG_MED", "SEGURO_VIDA"):
            marca = " ⚠️  DEVERIA SER conta_valor=false!"
        print(f"   {idx}: {row['qtd']} contratos, "
              f"R$ {row['valor']:,.2f}{marca}")

    # ── 5. Produtos de emissao com valor > 0 ───────
    print("\n5. EMISSAO/SEGURO COM VALOR > 0:")
    tipos_emissao = ["CARTÃO BENEFICIO", "Venda Pré-Adesão"]
    tipos_seguro = ["BMG MED", "Seguro"]

    for label, tipos in [
        ("Emissao", tipos_emissao),
        ("Seguro", tipos_seguro),
    ]:
        if "TIPO OPER." in df.columns:
            sub = df[df["TIPO OPER."].isin(tipos)]
        else:
            sub = pd.DataFrame()

        sub_com_valor = sub[sub["VALOR"] > 0]
        print(f"   {label}:")
        print(f"     Total contratos: {len(sub)}")
        print(f"     Com VALOR > 0: {len(sub_com_valor)}, "
              f"soma = R$ {sub_com_valor['VALOR'].sum():,.2f}")
        print(f"     conta_valor distribuicao: "
              f"{sub['conta_valor'].value_counts().to_dict()}")

    # ── 6. Categorias especiais com conta_valor=True
    print("\n6. CATEGORIAS ESPECIAIS (CARTAO, BMG_MED, SEGURO_VIDA) "
          "COM conta_valor=True:")
    cats_especiais = ["CARTAO", "BMG_MED", "SEGURO_VIDA"]
    for cat in cats_especiais:
        sub = df[
            (df["categoria_codigo"] == cat)
            & (df["conta_valor"] == True)  # noqa
        ]
        if not sub.empty:
            print(f"   ⚠️  {cat}: {len(sub)} contratos com "
                  f"conta_valor=True, "
                  f"VALOR = R$ {sub['VALOR'].sum():,.2f}")
        else:
            print(f"   ✓ {cat}: OK (nenhum com conta_valor=True)")

    # ── 7. Simular exclusao como o dashboard faz ────
    print("\n7. SIMULACAO DA EXCLUSAO (como app.py faz):")
    df_sim = df.copy()

    # Aplicar fallback de categoria (identico ao app.py)
    tipo_para_cat = {
        "CNC": "CNC",
        "CNC 13º": "CNC_13",
        "CNC 13": "CNC_13",
        "CNC ANT": "ANT_BENEF",
        "SAQUE": "SAQUE",
        "SAQUE BENEFICIO": "SAQUE_BENEFICIO",
        "CONSIG": "CONSIG_BMG",
        "CONSIG BMG": "CONSIG_BMG",
        "CONSIG PRIV": "CONSIG_PRIV",
        "CONSIG ITAU": "CONSIG_ITAU",
        "CONSIG Itau": "CONSIG_ITAU",
        "CONSIG C6": "CONSIG_C6",
        "FGTS": "FGTS",
        "EMISSAO": "CARTAO",
        "EMISSAO CB": "CARTAO",
        "EMISSAO CC": "CARTAO",
        "Portabilidade": "PORTABILIDADE",
        "PORTABILIDADE": "PORTABILIDADE",
    }

    mask_sem_cat = (
        (df_sim["categoria_codigo"] == "")
        | df_sim["categoria_codigo"].isna()
    )
    if mask_sem_cat.any():
        df_sim.loc[mask_sem_cat, "categoria_codigo"] = (
            df_sim.loc[mask_sem_cat, "TIPO_PRODUTO"]
            .map(tipo_para_cat)
            .fillna("")
        )
        # Nota: no app.py tambem atualiza conta_valor/conta_pontuacao
        # do banco. Aqui vamos verificar o que ficaria sem essa atualizacao.

    # Exclusao por conta_valor
    mask_sem_valor = df_sim["conta_valor"] == False  # noqa
    valor_excluido = df_sim.loc[mask_sem_valor, "VALOR"].sum()
    df_sim.loc[mask_sem_valor, "VALOR"] = 0

    valor_final = df_sim["VALOR"].sum()
    print(f"   Valor bruto:    R$ {valor_bruto_total:,.2f}")
    print(f"   Valor excluido: R$ {valor_excluido:,.2f}")
    print(f"   Valor final:    R$ {valor_final:,.2f}")
    print(f"   Valor esperado: R$ {VALOR_ESPERADO:,.2f}")
    print(f"   Diferenca:      R$ {valor_final - VALOR_ESPERADO:,.2f}")

    # ── 8. Identificar possiveis "vazamentos" ───────
    print("\n8. CONTRATOS COM VALOR > 0 APOS EXCLUSAO "
          "QUE PODEM SER SUSPEITOS:")
    # Contratos que ficaram com valor > 0 mas parecem ser
    # emissao/seguro pelo TIPO OPER.
    tipos_suspeitos = tipos_emissao + tipos_seguro
    if "TIPO OPER." in df_sim.columns:
        suspeitos = df_sim[
            (df_sim["TIPO OPER."].isin(tipos_suspeitos))
            & (df_sim["VALOR"] > 0)
        ]
        if not suspeitos.empty:
            print(f"   ⚠️  {len(suspeitos)} contratos de "
                  f"emissao/seguro AINDA com valor > 0!")
            print(f"   Valor: R$ {suspeitos['VALOR'].sum():,.2f}")
            print(suspeitos[
                ["CONTRATO_ID", "TIPO OPER.", "TIPO_PRODUTO",
                 "categoria_codigo", "conta_valor", "VALOR"]
            ].to_string(index=False))
        else:
            print("   ✓ Nenhum contrato suspeito com valor > 0")

    # ── 9. Contratos sem categoria e com valor > 0 apos exclusao
    print("\n9. CONTRATOS SEM CATEGORIA FINAL E COM VALOR > 0:")
    sem_cat_final = df_sim[
        ((df_sim["categoria_codigo"] == "")
         | df_sim["categoria_codigo"].isna())
        & (df_sim["VALOR"] > 0)
    ]
    if not sem_cat_final.empty:
        print(f"   ⚠️  {len(sem_cat_final)} contratos sem categoria "
              f"com VALOR > 0!")
        print(f"   Valor total: R$ {sem_cat_final['VALOR'].sum():,.2f}")
        det = (
            sem_cat_final.groupby(["TIPO_PRODUTO", "TIPO OPER."])
            .agg(qtd=("VALOR", "size"), valor=("VALOR", "sum"))
            .sort_values("valor", ascending=False)
        )
        print(det.to_string())
    else:
        print("   ✓ Todos os contratos com valor tem categoria")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Diagnostica diferenca no valor total"
    )
    parser.add_argument(
        "--mes", type=int, default=4,
        help="Mes de referencia (default: 4)"
    )
    parser.add_argument(
        "--ano", type=int, default=2025,
        help="Ano de referencia (default: 2025)"
    )
    args = parser.parse_args()

    df = carregar_dados(args.mes, args.ano)
    if df.empty:
        print("Nenhum dado encontrado!")
        sys.exit(1)

    diagnosticar(df)
