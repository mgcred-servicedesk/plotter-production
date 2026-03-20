# Modo Escuro - Dashboard MGCred

## 🌙 Implementação Concluída

O dashboard agora possui suporte completo a **modo escuro** com alternância via toggle na sidebar.

## 🎨 Paleta de Cores

### Tema Claro (Padrão)
- **Background Principal**: `#FFFFFF`
- **Background Secundário**: `#F8F9FA`
- **Cards**: Gradiente branco → cinza claro
- **Card Pontos**: Gradiente verde-azulado claro
- **Texto Principal**: `#2C3E50` (azul escuro)
- **Texto Secundário**: `#7F8C8D` (cinza)
- **Sombras**: Preto com 8-12% opacidade

### Tema Escuro
- **Background Principal**: `#1A1A1A` (preto suave)
- **Background Secundário**: `#2D2D2D` (cinza escuro)
- **Cards**: Gradiente cinza escuro → cinza médio
- **Card Pontos**: Gradiente verde-azulado escuro
- **Texto Principal**: `#E8F1F8` (azul claro)
- **Texto Secundário**: `#BDC3C7` (cinza claro)
- **Sombras**: Preto com 30-50% opacidade

### Cores de Destaque (Adaptadas)
| Cor | Tema Claro | Tema Escuro |
|-----|-----------|-------------|
| Azul Corporativo | `#2C3E50` | `#E8F1F8` |
| Azul Accent | `#3498DB` | `#5DADE2` |
| Verde Sucesso | `#27AE60` | `#52D273` |
| Laranja Alerta | `#E67E22` | `#F39C12` |
| Vermelho Crítico | `#E74C3C` | `#EC7063` |
| Dourado | `#F39C12` | `#F4D03F` |
| Teal (Pontos) | `#16A085` | `#48C9B0` |

## 🔧 Implementação Técnica

### 1. CSS com Variáveis (`assets/dashboard_style.css`)

```css
:root {
    /* Variáveis do tema claro */
    --bg-primary: #FFFFFF;
    --bg-card: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
    --text-primary: #2C3E50;
    /* ... */
}

[data-theme="dark"] {
    /* Variáveis do tema escuro */
    --bg-primary: #1A1A1A;
    --bg-card: linear-gradient(135deg, #2D2D2D 0%, #3A3A3A 100%);
    --text-primary: #E8F1F8;
    /* ... */
}
```

### 2. Função de Aplicação de Tema (`dashboard_refatorado.py`)

```python
def aplicar_tema(tema):
    """Aplica o tema selecionado (claro ou escuro)."""
    if tema == "Escuro":
        tema_css = '''
        <script>
            document.documentElement.setAttribute('data-theme', 'dark');
        </script>
        '''
    else:
        tema_css = '''
        <script>
            document.documentElement.removeAttribute('data-theme');
        </script>
        '''
    st.markdown(tema_css, unsafe_allow_html=True)
```

### 3. Toggle na Sidebar

```python
tema = st.selectbox(
    "🎨 Tema",
    ["Claro", "Escuro"],
    index=0,
    help="Alternar entre modo claro e escuro"
)
aplicar_tema(tema)
```

## 📊 Elementos Estilizados

### Cards de Métricas
- ✅ Background adaptativo
- ✅ Bordas coloridas mantidas
- ✅ Sombras ajustadas para cada tema
- ✅ Texto com contraste adequado
- ✅ Card de Pontos com destaque especial em ambos os temas

### Títulos e Textos
- ✅ Títulos (h1-h4) com cor adaptativa
- ✅ Parágrafos e spans com cor secundária
- ✅ Labels de métricas com cor primária

### Efeitos Interativos
- ✅ Hover nos cards mantido
- ✅ Transições suaves (0.3s)
- ✅ Elevação visual ao passar o mouse

## 🎯 Características

### Acessibilidade
- **Contraste adequado** em ambos os temas (WCAG AA)
- **Cores de destaque** ajustadas para melhor visibilidade
- **Sombras** proporcionais ao tema

### Performance
- **CSS otimizado** com variáveis
- **Sem recarregamento** ao trocar tema
- **Transições suaves** entre temas

### Consistência
- **Paleta coerente** em ambos os modos
- **Hierarquia visual** mantida
- **Destaque de pontos** preservado

## 🚀 Como Usar

1. Abra o dashboard
2. Na sidebar, localize **"🎨 Tema"**
3. Selecione entre **"Claro"** ou **"Escuro"**
4. O tema é aplicado instantaneamente

## 📝 Notas Técnicas

- O tema é aplicado via atributo `data-theme` no elemento raiz
- Utiliza variáveis CSS para fácil manutenção
- JavaScript inline para aplicação imediata
- Compatível com todos os navegadores modernos

## 🔮 Melhorias Futuras

- [ ] Persistir preferência de tema no localStorage
- [ ] Detectar preferência do sistema operacional
- [ ] Adicionar tema "Auto" (segue sistema)
- [ ] Animação de transição entre temas
- [ ] Temas customizados adicionais

### Atualizações Recentes de Legibilidade (Tema Claro e Escuro)
- Redução de fadiga visual no Tema Claro, substituindo o branco excessivo (#FFFFFF) por `Slate 100` (#F1F5F9).
- Suavização de textos, substituindo pretos absolutos por cinzas frios da paleta Slate (#1E293B).
- Ajuste dos verdes e vermelhos para a paleta Emerald e Red (Tailwind), evitando tons super-saturados que causavam desconforto visual durante longas jornadas de trabalho com os dados.
- O tema claro agora não é mais um "brilhante absoluto", mas uma plataforma neutra onde os cards brancos saltam de forma mais agradável, no estilo *dashboard analytics moderno*.
