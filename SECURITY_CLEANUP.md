# Limpeza de Segurança para Repositório Público

## ⚠️ AVISO DE SEGURANÇA

Este documento contém instruções para limpar dados sensíveis antes de tornar o repositório público.

## 🚨 DADOS SENSÍVEIS IDENTIFICADOS

### 1. Arquivo .env
- **CONTÉM**: Credenciais reais do Supabase
- **AÇÃO**: Já está no .gitignore, mas pode estar no histórico do Git
- **SOLUÇÃO**: Remover do histórico do Git

### 2. Diretórios com dados reais
- `digitacao/` - Dados de vendas reais (janeiro, fevereiro, março)
- `metas/` - Metas de vendas reais
- `pontuacao/` - Tabelas de pontuação real
- `configuracao/` - Dados de colaboradores e supervisores
- `tabelas/` - Tabelas de referência com dados reais
- `references/` - Arquivos de referência com dados
- `outputs/` - Relatórios gerados com dados reais

## 🔧 PASSOS PARA LIMPEZA

### 1. Remover .env do histórico do Git
```bash
# Fazer backup do .env atual
cp .env .env.backup

# Remover do histórico do Git
git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch .env' --prune-empty --tag-name-filter cat -- --all

# Limpar referências
git for-each-ref --format='delete %(refname)' | git update-ref --stdin

# Fazer garbage collection
git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

### 2. Verificar se dados sensíveis estão no histórico
```bash
# Procurar por URLs do Supabase no histórico
git log --all --full-history -- **/* | grep -i "supabase\|yesmihaeaqodtzqgjipv"

# Procurar por chaves de API
git log --all --full-history -- **/* | grep -i "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
```

### 3. Limpar diretórios de dados
```bash
# Remover do Git (mas manter localmente)
git rm -r --cached digitacao/
git rm -r --cached metas/
git rm -r -- cached pontuacao/
git rm -r -- cached tabelas/
git rm -r -- cached configuracao/
git rm -r -- cached references/
git rm -r -- cached outputs/

# Adicionar ao .gitignore (já feito)
git add .gitignore
```

### 4. Criar estrutura de diretórios vazia para o Cloud
```bash
# Criar diretórios vazios com .gitkeep
mkdir -p digitacao metas pontuacao tabelas configuracao references outputs/relatorios_excel outputs/relatorios_pdf/executivos outputs/relatorios_pdf/detalhados

# Criar arquivos .gitkeep
touch digitacao/.gitkeep
touch metas/.gitkeep
touch pontuacao/.gitkeep
touch tabelas/.gitkeep
touch configuracao/.gitkeep
touch references/.gitkeep
touch outputs/.gitkeep
touch outputs/relatorios_excel/.gitkeep
touch outputs/relatorios_pdf/.gitkeep
touch outputs/relatorios_pdf/executivos/.gitkeep
touch outputs/relatorios_pdf/detalhados/.gitkeep

# Adicionar ao Git
git add digitacao/.gitkeep metas/.gitkeep pontuacao/.gitkeep tabelas/.gitkeep configuracao/.gitkeep references/.gitkeep outputs/.gitkeep outputs/relatorios_excel/.gitkeep outputs/relatorios_pdf/.gitkeep outputs/relatorios_pdf/executivos/.gitkeep outputs/relatorios_pdf/detalhados/.gitkeep
```

### 5. Verificar arquivos de configuração
```bash
# Verificar se não há credenciais hardcodadas em arquivos Python
grep -r "yesmihaeaqodtzqgjipv\|vVOGHczfuTwHS4DseyUWJNxCfAy6BP6khreMWDDUXUM" src/
```

## ✅ VERIFICAÇÃO FINAL

### 1. Verificar .gitignore
```bash
cat .gitignore | grep -E "(digitacao|metas|pontuacao|tabelas|configuracao|references|outputs|\.env)"
```

### 2. Verificar status do Git
```bash
git status
```

### 3. Verificar se não há dados sensíveis nos arquivos que serão commitados
```bash
git diff --cached | grep -i "supabase\|key\|secret\|password"
```

## 🔄 RESTAURAÇÃO (se necessário)

Se precisar restaurar os dados após a limpeza:
```bash
# Restaurar .env do backup
cp .env.backup .env

# Os diretórios de dados já existem localmente
# Apenas não estão no Git
```

## 📝 RECOMENDAÇÕES

1. **NUNCA** fazer commit de arquivos .env
2. **SEMPRE** usar .env.example para configurações de exemplo
3. **VERIFICAR** o histórico do Git antes de tornar público
4. **USAR** chaves de API com permissões mínimas
5. **ROTACIONAR** chaves que foram expostas

## 🚀 APÓS LIMPEZA

Após seguir todos os passos:
1. Fazer commit das mudanças
2. Fazer push para um novo branch limpo
3. Verificar o repositório público
4. Configurar variáveis de ambiente no Streamlit Cloud
