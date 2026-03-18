# Testes Automatizados

Este diretório contém os testes automatizados do sistema de análise de vendas.

## 📋 Estrutura

```
tests/
├── __init__.py              # Inicialização do pacote de testes
├── conftest.py              # Fixtures compartilhadas (pytest)
├── test_pontuacao.py        # Testes do sistema de pontuação mensal
├── test_data_validation.py  # Testes de validação de dados
└── README.md                # Esta documentação
```

## 🚀 Como Executar os Testes

### Executar Todos os Testes

```bash
# Ativar ambiente virtual
source venv/bin/activate

# Executar todos os testes
pytest

# Executar com mais detalhes
pytest -v

# Executar com cobertura
pytest --cov=src --cov-report=html
```

### Executar Testes Específicos

```bash
# Executar apenas testes de pontuação
pytest tests/test_pontuacao.py

# Executar apenas testes de validação
pytest tests/test_data_validation.py

# Executar uma classe específica
pytest tests/test_pontuacao.py::TestCarregarPontuacaoMensal

# Executar um teste específico
pytest tests/test_pontuacao.py::TestCarregarPontuacaoMensal::test_carregar_pontuacao_marco_2026
```

### Executar por Markers

```bash
# Executar apenas testes unitários
pytest -m unit

# Executar apenas testes de integração
pytest -m integration

# Executar apenas testes de validação de dados
pytest -m data_validation
```

## 📝 Tipos de Testes

### 1. Testes de Pontuação (`test_pontuacao.py`)

Valida o sistema de pontuação mensal:
- ✅ Carregamento de tabelas de pontuação
- ✅ Cálculo correto de pontos (VALOR × PONTOS)
- ✅ Mapeamento de produtos
- ✅ Detecção de produtos sem pontuação

### 2. Testes de Validação (`test_data_validation.py`)

Valida integridade e qualidade dos dados:
- ✅ Mapeamento de colunas
- ✅ Regras de exclusão (emissões)
- ✅ Valores nulos em colunas críticas
- ✅ Valores numéricos válidos

## 🔧 Fixtures Disponíveis

Definidas em `conftest.py`:

- **`sample_vendas_df`**: DataFrame de vendas de exemplo
- **`sample_metas_df`**: DataFrame de metas de exemplo
- **`mes_teste`**: Mês padrão (3 = março)
- **`ano_teste`**: Ano padrão (2026)

## 📊 Cobertura de Testes

Para gerar relatório de cobertura:

```bash
pytest --cov=src --cov-report=html
```

O relatório será gerado em `htmlcov/index.html`

## ✅ Boas Práticas

1. **Sempre execute os testes antes de commit**
   ```bash
   pytest
   ```

2. **Adicione testes para novas funcionalidades**
   - Crie novos arquivos `test_*.py` para novos módulos
   - Use fixtures para dados de teste reutilizáveis

3. **Mantenha testes independentes**
   - Cada teste deve poder rodar isoladamente
   - Não dependa da ordem de execução

4. **Use markers para organizar**
   ```python
   @pytest.mark.unit
   def test_exemplo():
       pass
   ```

## 🐛 Debugging

Para debugar testes com mais informações:

```bash
# Mostrar print statements
pytest -s

# Parar no primeiro erro
pytest -x

# Mostrar traceback completo
pytest --tb=long

# Modo verbose com traceback
pytest -vv --tb=short
```

## 📚 Recursos

- [Documentação pytest](https://docs.pytest.org/)
- [Boas práticas de testes](https://docs.pytest.org/en/stable/goodpractices.html)
- [Fixtures pytest](https://docs.pytest.org/en/stable/fixture.html)
