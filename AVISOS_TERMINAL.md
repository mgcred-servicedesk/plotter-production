# 📋 Guia de Avisos do Terminal

## Avisos Comuns e Soluções

### ✅ **Avisos Normais (Podem ser Ignorados)**

#### 1. **ScriptRunContext Warning**
```
WARNING streamlit.runtime.scriptrunner_utils.script_run_context: 
Thread 'MainThread': missing ScriptRunContext! 
This warning can be ignored when running in bare mode.
```

**O que é:** Aviso do Streamlit quando executado fora do servidor web (modo bare).

**Quando aparece:** Ao executar o script diretamente com `python dashboard_refatorado.py`

**Solução:** 
- ✅ **Ignorar** - É esperado e não afeta o funcionamento
- ✅ **Executar corretamente:** `streamlit run dashboard_refatorado.py`
- ✅ **Já configurado:** Filtro de warnings adicionado no código

---

#### 2. **MemoryCacheStorageManager Warning**
```
WARNING streamlit.runtime.caching.cache_data_api: 
No runtime found, using MemoryCacheStorageManager
```

**O que é:** Streamlit usando cache em memória ao invés de cache persistente.

**Quando aparece:** Ao executar fora do servidor Streamlit.

**Solução:** 
- ✅ **Ignorar** - Funciona perfeitamente com cache em memória
- ✅ **Executar via Streamlit:** `streamlit run dashboard_refatorado.py`

---

### ⚠️ **Avisos que Merecem Atenção**

#### 1. **FutureWarning (Pandas/NumPy)**
```
FutureWarning: Some behavior will change in future versions
```

**O que é:** Avisos sobre mudanças futuras em bibliotecas.

**Solução:**
- ✅ **Já configurado:** Filtros de warnings no código
- 📝 **Monitorar:** Atualizar código quando novas versões forem lançadas

---

#### 2. **DeprecationWarning**
```
DeprecationWarning: Function X is deprecated
```

**O que é:** Funções que serão removidas em versões futuras.

**Solução:**
- ✅ **Já configurado:** Filtros de warnings no código
- 📝 **Ação futura:** Substituir funções deprecated quando necessário

---

## 🔧 Configurações Aplicadas

### 1. **Arquivo `.streamlit/config.toml`**
```toml
[logger]
level = "error"  # Mostra apenas erros, não warnings
messageFormat = "%(asctime)s %(message)s"
```

**Efeito:** Reduz verbosidade do Streamlit, mostrando apenas erros críticos.

---

### 2. **Filtros de Warnings no Código**
```python
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')
```

**Efeito:** Suprime warnings conhecidos e esperados.

---

## 🚀 Como Executar Sem Avisos

### **Método Recomendado:**
```bash
streamlit run dashboard_refatorado.py
```

**Resultado:** Terminal limpo, sem avisos desnecessários.

---

### **Método Alternativo (Desenvolvimento):**
```bash
# Com warnings visíveis (para debug)
python -W default dashboard_refatorado.py

# Sem warnings (produção)
python -W ignore dashboard_refatorado.py
```

---

## 📊 Tipos de Avisos por Categoria

### **Categoria: Streamlit**
- ✅ ScriptRunContext → **Ignorar**
- ✅ CacheStorageManager → **Ignorar**

### **Categoria: Pandas/NumPy**
- ⚠️ FutureWarning → **Monitorar** (já filtrado)
- ⚠️ DeprecationWarning → **Monitorar** (já filtrado)

### **Categoria: Plotly**
- ✅ Geralmente não gera warnings

### **Categoria: Python**
- ❌ SyntaxError → **Corrigir imediatamente**
- ❌ ImportError → **Corrigir imediatamente**
- ⚠️ ResourceWarning → **Investigar**

---

## 🛠️ Troubleshooting

### **Se ainda aparecem muitos avisos:**

1. **Verificar versão do Streamlit:**
```bash
./venv/bin/python -m streamlit --version
```

2. **Limpar cache do Streamlit:**
```bash
streamlit cache clear
```

3. **Recriar ambiente virtual (último recurso):**
```bash
rm -rf venv
python -m venv venv
./venv/bin/pip install -r requirements.txt
```

---

### **Se avisos críticos aparecerem:**

1. **Capturar aviso completo:**
```bash
streamlit run dashboard_refatorado.py 2>&1 | tee avisos.log
```

2. **Analisar o arquivo `avisos.log`**

3. **Reportar se for bug do código**

---

## 📝 Notas Importantes

- ✅ **Avisos do Streamlit são normais** quando executado fora do servidor
- ✅ **Filtros de warnings já estão configurados** no código
- ✅ **Terminal limpo ao executar via `streamlit run`**
- ⚠️ **Não ignore erros (errors)**, apenas warnings
- 📊 **Logs de erro estão em nível "error"** no config.toml

---

## 🎯 Resumo Rápido

| Aviso | Severidade | Ação |
|-------|-----------|------|
| ScriptRunContext | Baixa | Ignorar |
| CacheStorage | Baixa | Ignorar |
| FutureWarning | Média | Monitorar |
| DeprecationWarning | Média | Monitorar |
| ImportError | Alta | Corrigir |
| SyntaxError | Alta | Corrigir |

---

**Configuração completa!** O dashboard agora executa com terminal limpo e apenas avisos importantes são exibidos. 🎉
