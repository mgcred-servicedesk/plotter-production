"""
Script de diagnóstico para verificar BMG MED e Seguro (Vida Familiar)
no banco de dados.

Verifica:
1. Contratos em análise com BMG MED/Seguro (deveriam ter sub_status != 'Liquidada')
2. Contratos pagos (v_contratos_dashboard) com BMG MED/Seguro e valor > 0
3. Valores que estão sendo contabilizados incorretamente
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.supabase_client import get_supabase_client
import pandas as pd


def verificar_bmg_seguro_em_analise(mes: int, ano: int):
    """Verifica BMG MED e Seguro no pipeline de em análise."""
    sb = get_supabase_client()
    
    print(f"\n{'='*60}")
    print(f"DIAGNÓSTICO BMG MED / SEGURO - Período: {mes}/{ano}")
    print(f"{'='*60}")
    
    # 1. Verificar contratos em análise via RPC
    print("\n📋 1. CONTRATOS EM ANÁLISE (via RPC obter_contratos_em_analise)")
    print("-" * 60)
    
    resp = sb.rpc(
        "obter_contratos_em_analise",
        {"p_mes": mes, "p_ano": ano}
    ).execute()
    
    if resp.data:
        df_analise = pd.DataFrame(resp.data)
        
        # Filtrar BMG MED e Seguro
        mask_bmg_med = df_analise['tipo_operacao'] == 'BMG MED'
        mask_seguro = df_analise['tipo_operacao'] == 'Seguro'
        
        df_bmg_med = df_analise[mask_bmg_med]
        df_seguro = df_analise[mask_seguro]
        
        print(f"\n🔹 BMG MED em análise: {len(df_bmg_med)} contratos")
        if not df_bmg_med.empty:
            print(f"   Valor total: R$ {df_bmg_med['valor'].sum():,.2f}")
            print(f"   Sub-status únicos: {df_bmg_med['sub_status_banco'].unique().tolist()}")
            print(f"\n   ⚠️  ALERTA: BMG MED não deveria aparecer em 'em análise'")
            print(f"      (deveria estar em 'contratos pagos' quando liquidado)")
        
        print(f"\n🔹 Seguro (Vida Familiar) em análise: {len(df_seguro)} contratos")
        if not df_seguro.empty:
            print(f"   Valor total: R$ {df_seguro['valor'].sum():,.2f}")
            print(f"   Sub-status únicos: {df_seguro['sub_status_banco'].unique().tolist()}")
            print(f"\n   ⚠️  ALERTA: Seguro não deveria aparecer em 'em análise'")
            print(f"      (deveria estar em 'contratos pagos' quando liquidado)")
        
        if df_bmg_med.empty and df_seguro.empty:
            print("   ✅ Nenhum BMG MED ou Seguro encontrado em 'em análise'")
            print("   (Isso está correto - eles só aparecem quando liquidados)")
    else:
        print("   Nenhum contrato em análise encontrado")
    
    # 2. Verificar contratos pagos (v_contratos_dashboard)
    print("\n\n📋 2. CONTRATOS PAGOS (via view v_contratos_dashboard)")
    print("-" * 60)
    
    # Buscar período
    resp_periodo = sb.table("periodos").select("id").eq("mes", mes).eq("ano", ano).execute()
    if not resp_periodo.data:
        print(f"   ❌ Período {mes}/{ano} não encontrado")
        return
    
    periodo_id = resp_periodo.data[0]['id']
    
    # Buscar contratos pagos via view
    resp_pagos = sb.from_("v_contratos_dashboard").select("*").eq("periodo_id", periodo_id).execute()
    
    if resp_pagos.data:
        df_pagos = pd.DataFrame(resp_pagos.data)
        
        # Filtrar BMG MED e Seguro
        mask_bmg_med = df_pagos['tipo_operacao'] == 'BMG MED'
        mask_seguro = df_pagos['tipo_operacao'] == 'Seguro'
        
        df_bmg_med = df_pagos[mask_bmg_med]
        df_seguro = df_pagos[mask_seguro]
        
        print(f"\n🔹 BMG MED pagos/liquidados: {len(df_bmg_med)} contratos")
        if not df_bmg_med.empty:
            valor_total = df_bmg_med['valor'].sum()
            print(f"   Valor total: R$ {valor_total:,.2f}")
            print(f"   Categorias: {df_bmg_med['categoria_codigo'].unique().tolist()}")
            print(f"   conta_valor: {df_bmg_med['conta_valor'].unique().tolist()}")
            
            if valor_total > 0:
                print(f"\n   ⚠️  ATENÇÃO: BMG MED tem valor > 0")
                print(f"      Deveria ter conta_valor=false e valor zerado no dashboard")
        else:
            print("   Nenhum BMG MED encontrado nos contratos pagos")
        
        print(f"\n🔹 Seguro (Vida Familiar) pagos/liquidados: {len(df_seguro)} contratos")
        if not df_seguro.empty:
            valor_total = df_seguro['valor'].sum()
            print(f"   Valor total: R$ {valor_total:,.2f}")
            print(f"   Categorias: {df_seguro['categoria_codigo'].unique().tolist()}")
            print(f"   conta_valor: {df_seguro['conta_valor'].unique().tolist()}")
            
            if valor_total > 0:
                print(f"\n   ⚠️  ATENÇÃO: Seguro tem valor > 0")
                print(f"      Deveria ter conta_valor=false e valor zerado no dashboard")
        else:
            print("   Nenhum Seguro encontrado nos contratos pagos")
    else:
        print("   Nenhum contrato pago encontrado")
    
    # 3. Verificar categorias_produto
    print("\n\n📋 3. CONFIGURAÇÃO DE CATEGORIAS (categorias_produto)")
    print("-" * 60)
    
    resp_cat = sb.table("categorias_produto").select("*").in_("codigo", ["BMG_MED", "SEGURO_VIDA", "CARTAO"]).execute()
    
    if resp_cat.data:
        df_cat = pd.DataFrame(resp_cat.data)
        for _, row in df_cat.iterrows():
            print(f"\n🔹 {row['codigo']} ({row['nome']}):")
            print(f"   conta_valor: {row['conta_valor']}")
            print(f"   conta_pontuacao: {row['conta_pontuacao']}")
            print(f"   grupo_dashboard: {row['grupo_dashboard']}")
            
            if row['conta_valor']:
                print(f"   ✅ Valor será contabilizado")
            else:
                print(f"   ✅ Valor será ZERADO no dashboard (apenas quantidade)")
    
    print("\n" + "="*60)
    print("DIAGNÓSTICO CONCLUÍDO")
    print("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Verificar BMG MED e Seguro no banco")
    parser.add_argument("--mes", type=int, default=4, help="Mês (1-12)")
    parser.add_argument("--ano", type=int, default=2026, help="Ano")
    
    args = parser.parse_args()
    
    verificar_bmg_seguro_em_analise(args.mes, args.ano)
