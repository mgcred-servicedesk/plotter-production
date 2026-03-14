"""
Script de teste para validar o mapeamento de colunas e higienização de dados.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from src.data_processing.column_mapper import (
    mapear_digitacao,
    mapear_tabelas,
    higienizar_vendedor,
    adicionar_coluna_subtipo_via_merge
)


def testar_higienizacao_vendedor():
    """Testa a função de higienização do campo VENDEDOR."""
    print("=" * 80)
    print("TESTE 1: Higienização do campo VENDEDOR")
    print("=" * 80)
    
    casos_teste = [
        ("3771 - YASMIM VELASCO DA SILVA", "YASMIM VELASCO DA SILVA"),
        ("1234 - JOÃO DA SILVA", "JOÃO DA SILVA"),
        ("MARIA SANTOS", "MARIA SANTOS"),
        ("", ""),
        (None, ""),
    ]
    
    todos_ok = True
    for entrada, esperado in casos_teste:
        resultado = higienizar_vendedor(entrada)
        status = "✓" if resultado == esperado else "✗"
        if resultado != esperado:
            todos_ok = False
        print(f"{status} '{entrada}' -> '{resultado}' (esperado: '{esperado}')")
    
    print(f"\nResultado: {'✓ TODOS OS TESTES PASSARAM' if todos_ok else '✗ ALGUNS TESTES FALHARAM'}")
    return todos_ok


def testar_mapeamento_digitacao():
    """Testa o mapeamento de colunas de digitação."""
    print("\n" + "=" * 80)
    print("TESTE 2: Mapeamento de Colunas - Digitação")
    print("=" * 80)
    
    try:
        df = pd.read_excel('digitacao/marco_2026.xlsx')
        print(f"\n✓ Arquivo carregado: {len(df)} registros")
        
        print(f"\nColunas ANTES do mapeamento:")
        print(f"  - VENDEDOR: {'✓' if 'VENDEDOR' in df.columns else '✗'}")
        print(f"  - FILIAL: {'✓' if 'FILIAL' in df.columns else '✗'}")
        print(f"  - VLR BASE: {'✓' if 'VLR BASE' in df.columns else '✗'}")
        print(f"  - TABELA: {'✓' if 'TABELA' in df.columns else '✗'}")
        
        df_mapped = mapear_digitacao(df)
        
        print(f"\nColunas DEPOIS do mapeamento:")
        print(f"  - CONSULTOR: {'✓' if 'CONSULTOR' in df_mapped.columns else '✗'}")
        print(f"  - LOJA: {'✓' if 'LOJA' in df_mapped.columns else '✗'}")
        print(f"  - VALOR: {'✓' if 'VALOR' in df_mapped.columns else '✗'}")
        print(f"  - PRODUTO: {'✓' if 'PRODUTO' in df_mapped.columns else '✗'}")
        
        if 'CONSULTOR' in df_mapped.columns:
            print(f"\nExemplos de CONSULTOR higienizado:")
            amostras = df_mapped['CONSULTOR'].dropna().head(5)
            for i, consultor in enumerate(amostras, 1):
                print(f"  {i}. {consultor}")
        
        if 'VALOR' in df_mapped.columns:
            print(f"\nEstatísticas de VALOR (VLR BASE):")
            print(f"  - Total: R$ {df_mapped['VALOR'].sum():,.2f}")
            print(f"  - Média: R$ {df_mapped['VALOR'].mean():,.2f}")
            print(f"  - Mínimo: R$ {df_mapped['VALOR'].min():,.2f}")
            print(f"  - Máximo: R$ {df_mapped['VALOR'].max():,.2f}")
        
        print(f"\n✓ Mapeamento de digitação concluído com sucesso!")
        return True
        
    except Exception as e:
        print(f"\n✗ Erro no mapeamento: {e}")
        import traceback
        traceback.print_exc()
        return False


def testar_join_tabelas():
    """Testa o JOIN entre digitação e tabelas."""
    print("\n" + "=" * 80)
    print("TESTE 3: JOIN entre Digitação e Tabelas")
    print("=" * 80)
    
    try:
        df_digitacao = pd.read_excel('digitacao/marco_2026.xlsx')
        df_tabelas = pd.read_excel('tabelas/Tabelas_marco_2026.xlsx')
        
        print(f"\n✓ Digitação carregada: {len(df_digitacao)} registros")
        print(f"✓ Tabelas carregadas: {len(df_tabelas)} registros")
        
        df_digitacao_mapped = mapear_digitacao(df_digitacao)
        df_tabelas_mapped = mapear_tabelas(df_tabelas)
        
        print(f"\nColunas em comum para JOIN:")
        print(f"  - Digitação tem 'PRODUTO': {'✓' if 'PRODUTO' in df_digitacao_mapped.columns else '✗'}")
        print(f"  - Tabelas tem 'PRODUTO': {'✓' if 'PRODUTO' in df_tabelas_mapped.columns else '✗'}")
        
        df_joined = adicionar_coluna_subtipo_via_merge(
            df_digitacao_mapped,
            df_tabelas_mapped
        )
        
        print(f"\n✓ JOIN realizado com sucesso!")
        print(f"  - Registros após JOIN: {len(df_joined)}")
        print(f"  - Coluna SUBTIPO adicionada: {'✓' if 'SUBTIPO' in df_joined.columns else '✗'}")
        print(f"  - Coluna PTS adicionada: {'✓' if 'PTS' in df_joined.columns else '✗'}")
        
        if 'SUBTIPO' in df_joined.columns:
            print(f"\nValores únicos de SUBTIPO (primeiros 10):")
            subtipos = df_joined['SUBTIPO'].value_counts().head(10)
            for subtipo, count in subtipos.items():
                print(f"  - {subtipo}: {count} registros")
        
        if 'PTS' in df_joined.columns:
            print(f"\nDistribuição de PTS:")
            pts_dist = df_joined['PTS'].value_counts().sort_index()
            for pts, count in pts_dist.items():
                print(f"  - {pts} pontos: {count} registros")
        
        super_conta_count = df_joined[df_joined['SUBTIPO'] == 'SUPER CONTA'].shape[0] if 'SUBTIPO' in df_joined.columns else 0
        print(f"\n✓ Registros de SUPER CONTA identificados: {super_conta_count}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Erro no JOIN: {e}")
        import traceback
        traceback.print_exc()
        return False


def testar_calculo_pontuacao():
    """Testa o cálculo de pontuação com VLR BASE."""
    print("\n" + "=" * 80)
    print("TESTE 4: Cálculo de Pontuação (VALOR × PTS)")
    print("=" * 80)
    
    try:
        df_digitacao = pd.read_excel('digitacao/marco_2026.xlsx')
        df_tabelas = pd.read_excel('tabelas/Tabelas_marco_2026.xlsx')
        
        df_digitacao_mapped = mapear_digitacao(df_digitacao)
        df_tabelas_mapped = mapear_tabelas(df_tabelas)
        
        df_joined = adicionar_coluna_subtipo_via_merge(
            df_digitacao_mapped,
            df_tabelas_mapped
        )
        
        if 'VALOR' in df_joined.columns and 'PTS' in df_joined.columns:
            df_joined['pontos'] = df_joined['VALOR'] * df_joined['PTS']
            
            print(f"\n✓ Pontuação calculada!")
            print(f"\nEstatísticas de Pontuação:")
            print(f"  - Total de pontos: {df_joined['pontos'].sum():,.0f}")
            print(f"  - Média de pontos por transação: {df_joined['pontos'].mean():,.2f}")
            print(f"  - Pontuação mínima: {df_joined['pontos'].min():,.2f}")
            print(f"  - Pontuação máxima: {df_joined['pontos'].max():,.2f}")
            
            print(f"\nTop 5 transações por pontuação:")
            top_5 = df_joined.nlargest(5, 'pontos')[['CONSULTOR', 'PRODUTO', 'VALOR', 'PTS', 'pontos']]
            for idx, row in top_5.iterrows():
                print(f"  - {row['CONSULTOR']}: {row['PRODUTO']} = R$ {row['VALOR']:,.2f} × {row['PTS']} = {row['pontos']:,.0f} pts")
            
            return True
        else:
            print(f"\n✗ Colunas necessárias não encontradas")
            return False
        
    except Exception as e:
        print(f"\n✗ Erro no cálculo: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Executa todos os testes."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "TESTES DE MAPEAMENTO E QUALIDADE" + " " * 26 + "║")
    print("╚" + "=" * 78 + "╝")
    
    resultados = []
    
    resultados.append(("Higienização VENDEDOR", testar_higienizacao_vendedor()))
    resultados.append(("Mapeamento Digitação", testar_mapeamento_digitacao()))
    resultados.append(("JOIN Tabelas", testar_join_tabelas()))
    resultados.append(("Cálculo Pontuação", testar_calculo_pontuacao()))
    
    print("\n" + "=" * 80)
    print("RESUMO DOS TESTES")
    print("=" * 80)
    
    for nome, resultado in resultados:
        status = "✓ PASSOU" if resultado else "✗ FALHOU"
        print(f"{status}: {nome}")
    
    todos_passaram = all(r[1] for r in resultados)
    
    print("\n" + "=" * 80)
    if todos_passaram:
        print("✓ TODOS OS TESTES PASSARAM COM SUCESSO!")
    else:
        print("✗ ALGUNS TESTES FALHARAM - REVISAR IMPLEMENTAÇÃO")
    print("=" * 80)
    
    return 0 if todos_passaram else 1


if __name__ == "__main__":
    sys.exit(main())
