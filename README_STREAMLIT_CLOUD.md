# Deploy no Streamlit Cloud Community

## Arquivos Necessários

Para fazer o deploy no Streamlit Cloud, você precisa destes arquivos:

1. **dashboard_supabase.py** - Arquivo principal do aplicativo
2. **requirements.txt** - Dependências Python
3. **config.toml** - Configurações do Streamlit
4. **.env** - Variáveis de ambiente (NÃO fazer commit no Git)

## Configuração das Variáveis de Ambiente

No Streamlit Cloud, configure estas variáveis de ambiente em **Settings > Secrets**:

```toml
SUPABASE_URL="https://seu-projeto.supabase.co"
SUPABASE_KEY="sua-chave-anon-ou-service-role"
DATA_DIR_DIGITACAO="/digitacao"
DATA_DIR_METAS="/metas"
DATA_DIR_TABELAS="/tabelas"
DATA_DIR_CONFIGURACAO="/configuracao"
OUTPUT_DIR_EXCEL="/outputs/relatorios_excel"
OUTPUT_DIR_PDF_EXECUTIVO="/outputs/relatorios_pdf/executivos"
OUTPUT_DIR_PDF_DETALHADO="/outputs/relatorios_pdf/detalhados"
LOCALE="pt_BR.UTF-8"
CURRENCY_SYMBOL="R$"
DATE_FORMAT="%d/%m/%Y"
HOLIDAYS="01/01/2026,03/01/2026,04/01/2026,10/01/2026,11/01/2026,17/01/2026,18/01/2026,24/01/2026,25/01/2026,31/01/2026,01/02/2026,07/02/2026,08/02/2026,14/02/2026,15/02/2026,16/02/2026,17/02/2026,21/02/2026,22/02/2026,28/02/2026,01/03/2026,07/03/2026,08/03/2026,14/03/2026,15/03/2026,21/03/2026,22/03/2026,28/03/2026,29/03/2026,04/04/2026,05/04/2026,06/04/2026,07/04/2026,08/04/2026,09/04/2026,10/04/2026,11/04/2026,12/04/2026,13/04/2026,14/04/2026"
DASHBOARD_TITLE="Dashboard de Análise de Vendas"
DASHBOARD_ICON="📊"
DASHBOARD_LAYOUT="wide"
CACHE_TTL="3600"
PDF_COMPANY_NAME="MG Cred"
PDF_LOGO_PATH="/assets/logotipo-mg-cred.png"
```

## Passos para Deploy

1. **Fazer upload do repositório** para o GitHub
2. **Conectar ao Streamlit Cloud**:
   - Acesse https://share.streamlit.io/
   - Conecte sua conta GitHub
   - Selecione o repositório `Numeros_venda`
3. **Configurar o app**:
   - Main file path: `dashboard_supabase.py`
   - Python version: 3.12 (recomendado)
4. **Adicionar variáveis de ambiente** em Settings > Secrets
5. **Fazer deploy** clicando em "Deploy"

## Estrutura de Diretórios no Cloud

O Streamlit Cloud criará automaticamente os diretórios necessários:
- `/digitacao` - Para arquivos de digitação
- `/metas` - Para arquivos de metas
- `/tabelas` - Para tabelas de referência
- `/configuracao` - Para configurações
- `/outputs/relatorios_excel` - Para saídas Excel
- `/outputs/relatorios_pdf/executivos` - Para PDFs executivos
- `/outputs/relatorios_pdf/detalhados` - Para PDFs detalhados

## Importante

- **NÃO** faça commit do arquivo `.env` no Git
- Use apenas chaves de **service_role** ou **anon** do Supabase
- Verifique se as políticas RLS do Supabase estão configuradas corretamente
- O projeto usa autenticação integrada, não é necessário login externo

## Solução de Problemas

Se ocorrer erro de importação, verifique:
1. Se todas as dependências estão em requirements.txt
2. Se as variáveis de ambiente estão configuradas corretamente
3. Se a conexão com Supabase está funcionando

Para testes locais, copie `.env.example` para `.env` e preencha suas credenciais.
