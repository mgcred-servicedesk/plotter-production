"""
Módulo para criação de gráficos para relatórios PDF.
"""
import warnings
from io import BytesIO

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use('Agg')

warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')


# Paleta de cores padrão
COLORS = {
    'primary': '#1F4E78',
    'success': '#28A745',
    'danger': '#DC3545',
    'warning': '#FFC107',
    'info': '#17A2B8',
    'secondary': '#6C757D',
    'light': '#F8F9FA',
    'dark': '#343A40'
}


def configurar_estilo_grafico():
    """Configura estilo padrão para todos os gráficos."""
    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = [
        'DejaVu Sans', 'Bitstream Vera Sans', 'Liberation Sans',
        'Arial', 'Helvetica', 'sans-serif'
    ]
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.titlesize'] = 12
    plt.rcParams['axes.labelsize'] = 10
    plt.rcParams['xtick.labelsize'] = 9
    plt.rcParams['ytick.labelsize'] = 9
    plt.rcParams['legend.fontsize'] = 9
    plt.rcParams['figure.titlesize'] = 14


def criar_grafico_atingimento(atingimento_pct, expectativa_pct, meta_total):
    """
    Cria gráfico de gauge para atingimento e expectativa.
    
    Args:
        atingimento_pct: Percentual de atingimento atual
        expectativa_pct: Percentual de expectativa (projeção)
        meta_total: Valor da meta total
    
    Returns:
        BytesIO com a imagem do gráfico
    """
    configurar_estilo_grafico()
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    
    # Gráfico de Atingimento
    criar_gauge(ax1, atingimento_pct, "Atingimento Atual", COLORS['primary'])
    
    # Gráfico de Expectativa
    criar_gauge(ax2, expectativa_pct, "Expectativa (Projeção)", COLORS['info'])
    
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer


def criar_gauge(ax, percentual, titulo, cor):
    """Cria um gráfico de gauge (medidor circular)."""
    # Limitar percentual a 150% para visualização
    percentual_visual = min(percentual, 150)
    
    # Criar gauge
    theta = np.linspace(0, np.pi, 100)
    r = np.ones_like(theta)
    
    # Fundo do gauge
    ax.fill_between(theta, 0, r, color='#E0E0E0', alpha=0.3)
    
    # Preenchimento até o percentual
    theta_fill = np.linspace(0, np.pi * (percentual_visual / 100), 100)
    r_fill = np.ones_like(theta_fill)
    
    # Cor baseada no percentual
    if percentual >= 100:
        fill_color = COLORS['success']
    elif percentual >= 70:
        fill_color = COLORS['warning']
    else:
        fill_color = COLORS['danger']
    
    ax.fill_between(theta_fill, 0, r_fill, color=fill_color, alpha=0.8)
    
    # Adicionar texto no centro com cor escura para melhor visibilidade
    ax.text(np.pi/2, 0.5, f'{percentual:.1f}%', 
            ha='center', va='center', fontsize=24, fontweight='bold',
            color='#2C3E50')
    
    ax.set_ylim(0, 1.2)
    ax.set_xlim(0, np.pi)
    ax.axis('off')
    ax.set_title(titulo, fontsize=12, fontweight='bold', pad=10)


def criar_grafico_barras_top10(df, coluna_nome, coluna_valor, titulo, cor=None):
    """
    Cria gráfico de barras horizontais para TOP 10.
    
    Args:
        df: DataFrame com os dados
        coluna_nome: Nome da coluna com os nomes (ex: 'Loja', 'Consultor')
        coluna_valor: Nome da coluna com os valores (ex: 'Pontos', 'Valor')
        titulo: Título do gráfico
        cor: Cor das barras (opcional)
    
    Returns:
        BytesIO com a imagem do gráfico
    """
    configurar_estilo_grafico()
    
    if cor is None:
        cor = COLORS['primary']
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Pegar top 10 e inverter para mostrar do maior para o menor (de cima para baixo)
    df_top = df.head(10).sort_values(coluna_valor, ascending=True)
    
    # Criar barras horizontais
    bars = ax.barh(df_top[coluna_nome], df_top[coluna_valor], color=cor, alpha=0.8)
    
    # Adicionar valores nas barras
    for i, (idx, row) in enumerate(df_top.iterrows()):
        valor = row[coluna_valor]
        if valor >= 1000000:
            texto = f'{valor/1000000:.1f}M'
        elif valor >= 1000:
            texto = f'{valor/1000:.0f}K'
        else:
            texto = f'{valor:.0f}'
        
        ax.text(valor, i, f' {texto}', va='center', fontsize=9, fontweight='bold')
    
    ax.set_xlabel(coluna_valor, fontsize=10, fontweight='bold')
    ax.set_title(titulo, fontsize=12, fontweight='bold', pad=15)
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer


def criar_grafico_pizza_produtos(df_produtos, titulo="Distribuição por Produto"):
    """
    Cria gráfico de pizza para distribuição de produtos.
    
    Args:
        df_produtos: DataFrame com colunas 'Produto' e 'Pontos' (ou 'Valor')
        titulo: Título do gráfico
    
    Returns:
        BytesIO com a imagem do gráfico
    """
    configurar_estilo_grafico()
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Determinar coluna de valores
    coluna_valor = 'Pontos' if 'Pontos' in df_produtos.columns else 'Valor'
    
    # Cores para cada produto
    cores = [COLORS['primary'], COLORS['success'], COLORS['info'], 
             COLORS['warning'], COLORS['danger'], COLORS['secondary']]
    
    # Criar gráfico de pizza
    wedges, texts, autotexts = ax.pie(
        df_produtos[coluna_valor],
        labels=df_produtos['Produto'],
        autopct='%1.1f%%',
        colors=cores[:len(df_produtos)],
        startangle=90,
        textprops={'fontsize': 10}
    )
    
    # Melhorar aparência dos textos
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(9)
    
    ax.set_title(titulo, fontsize=12, fontweight='bold', pad=15)
    
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer


def criar_grafico_barras_regioes(df_regioes, titulo="Performance por Região"):
    """
    Cria gráfico de barras agrupadas para comparação de regiões.
    
    Args:
        df_regioes: DataFrame com dados das regiões
        titulo: Título do gráfico
    
    Returns:
        BytesIO com a imagem do gráfico
    """
    configurar_estilo_grafico()
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Preparar dados
    regioes = df_regioes['Região'].tolist() if 'Região' in df_regioes.columns else df_regioes.index.tolist()
    pontos = df_regioes['Pontos'].tolist() if 'Pontos' in df_regioes.columns else []
    atingimento = df_regioes['Atingimento %'].tolist() if 'Atingimento %' in df_regioes.columns else []
    
    x = np.arange(len(regioes))
    width = 0.35
    
    # Criar barras
    if pontos:
        # Normalizar pontos para escala de 0-100 para comparação visual
        max_pontos = max(pontos) if pontos else 1
        pontos_norm = [p / max_pontos * 100 for p in pontos]
        
        bars1 = ax.bar(x - width/2, pontos_norm, width, label='Pontos (normalizado)',
                       color=COLORS['primary'], alpha=0.8)
    
    if atingimento:
        bars2 = ax.bar(x + width/2, atingimento, width, label='Atingimento %',
                       color=COLORS['success'], alpha=0.8)
    
    ax.set_xlabel('Região', fontsize=10, fontweight='bold')
    ax.set_ylabel('Percentual', fontsize=10, fontweight='bold')
    ax.set_title(titulo, fontsize=12, fontweight='bold', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(regioes, rotation=45, ha='right')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer


def criar_grafico_evolucao_diaria(df, coluna_data='DATA', coluna_valor='pontos', titulo="Evolução Diária"):
    """
    Cria gráfico de linha para evolução diária.
    
    Args:
        df: DataFrame com os dados
        coluna_data: Nome da coluna de data
        coluna_valor: Nome da coluna de valor
        titulo: Título do gráfico
    
    Returns:
        BytesIO com a imagem do gráfico
    """
    configurar_estilo_grafico()
    
    fig, ax = plt.subplots(figsize=(12, 5))
    
    # Agrupar por data
    df_diario = df.groupby(pd.to_datetime(df[coluna_data]).dt.date)[coluna_valor].sum().reset_index()
    df_diario.columns = ['Data', 'Valor']
    
    # Criar linha
    ax.plot(df_diario['Data'], df_diario['Valor'], 
            marker='o', linewidth=2, markersize=6,
            color=COLORS['primary'], alpha=0.8)
    
    # Preencher área abaixo da linha
    ax.fill_between(df_diario['Data'], df_diario['Valor'], alpha=0.3, color=COLORS['primary'])
    
    ax.set_xlabel('Data', fontsize=10, fontweight='bold')
    ax.set_ylabel(coluna_valor.capitalize(), fontsize=10, fontweight='bold')
    ax.set_title(titulo, fontsize=12, fontweight='bold', pad=15)
    ax.grid(True, alpha=0.3)
    
    # Rotacionar labels do eixo x
    plt.xticks(rotation=45, ha='right')
    
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer


def criar_kpi_card_image(titulo, valor, subtitulo="", cor=None):
    """
    Cria uma imagem de card KPI para usar no PDF.
    
    Args:
        titulo: Título do KPI
        valor: Valor do KPI
        subtitulo: Texto adicional (opcional)
        cor: Cor do card (opcional)
    
    Returns:
        BytesIO com a imagem do card
    """
    if cor is None:
        cor = COLORS['primary']
    
    fig, ax = plt.subplots(figsize=(4, 2.5))
    
    # Remover eixos
    ax.axis('off')
    
    # Adicionar retângulo de fundo
    rect = mpatches.Rectangle((0.05, 0.1), 0.9, 0.8, 
                              linewidth=2, edgecolor=cor, 
                              facecolor='white', alpha=0.9)
    ax.add_patch(rect)
    
    # Adicionar título
    ax.text(0.5, 0.75, titulo, ha='center', va='center',
            fontsize=11, fontweight='bold', color=COLORS['dark'])
    
    # Adicionar valor
    ax.text(0.5, 0.45, str(valor), ha='center', va='center',
            fontsize=20, fontweight='bold', color=cor)
    
    # Adicionar subtítulo se fornecido
    if subtitulo:
        ax.text(0.5, 0.2, subtitulo, ha='center', va='center',
                fontsize=9, color=COLORS['secondary'])
    
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    buffer.seek(0)
    plt.close()
    
    return buffer
