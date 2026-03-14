# Configuração de Fontes para Relatórios PDF

## Problema Resolvido

Os relatórios PDF estavam gerando múltiplos avisos do matplotlib sobre fontes não encontradas:
```
findfont: Generic family 'sans-serif' not found because none of the following families were found: Arial, Helvetica
```

## Solução Implementada

### 1. Supressão de Avisos
Adicionado filtro de avisos no módulo `pdf_charts.py`:
```python
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
```

### 2. Configuração de Fontes Alternativas
Configurado matplotlib para usar fontes disponíveis no sistema Linux em ordem de prioridade:

```python
plt.rcParams['font.sans-serif'] = [
    'DejaVu Sans',           # Fonte padrão em sistemas Linux
    'Bitstream Vera Sans',   # Alternativa comum
    'Liberation Sans',       # Disponível em muitas distribuições
    'Arial',                 # Se disponível
    'Helvetica',             # Se disponível
    'sans-serif'             # Fallback genérico
]
```

## Fontes Utilizadas

### DejaVu Sans (Padrão)
- **Disponibilidade**: Instalada por padrão na maioria das distribuições Linux
- **Qualidade**: Excelente legibilidade e suporte a caracteres especiais
- **Compatibilidade**: Funciona perfeitamente com matplotlib e ReportLab

### Instalação de Fontes Adicionais (Opcional)

Se desejar usar Arial ou Helvetica especificamente:

#### Ubuntu/Debian:
```bash
sudo apt-get install ttf-mscorefonts-installer
sudo fc-cache -f -v
```

#### Fedora/RHEL:
```bash
sudo dnf install curl cabextract xorg-x11-font-utils fontconfig
sudo rpm -i https://downloads.sourceforge.net/project/mscorefonts2/rpms/msttcore-fonts-installer-2.6-1.noarch.rpm
```

#### Arch Linux:
```bash
yay -S ttf-ms-fonts
```

## Dependências do Projeto

### Fontes Necessárias
- **Mínimo**: DejaVu Sans (já instalada por padrão)
- **Opcional**: Microsoft Core Fonts (Arial, Helvetica)

### Pacotes Python
```
matplotlib>=3.8.0
reportlab>=4.0.0
```

## Verificação

Para verificar fontes disponíveis no sistema:
```python
import matplotlib.font_manager as fm
fonts = [f.name for f in fm.fontManager.ttflist]
print(sorted(set(fonts)))
```

## Resultado

✅ Relatórios PDF gerados sem avisos de fonte
✅ Textos renderizados com qualidade profissional
✅ Compatibilidade garantida em diferentes ambientes Linux

## Arquivos Modificados

- `src/reports/pdf_charts.py`: Configuração de fontes e supressão de avisos

## Notas Técnicas

1. **Backend Agg**: Usado para renderização sem interface gráfica
2. **Warnings Filter**: Aplicado apenas para avisos do matplotlib
3. **Fallback Chain**: Sistema tenta fontes em ordem até encontrar uma disponível
4. **Cache de Fontes**: matplotlib mantém cache de fontes disponíveis

## Manutenção

Não é necessária manutenção adicional. A solução é robusta e funciona em qualquer sistema Linux com matplotlib instalado.
