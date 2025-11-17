# 📊 Plano de Implementação: Sistema Completo de Relatórios PDF
## Análise Atual e Roadmap de Desenvolvimento

**Data:** 2024  
**Versão:** 1.0  
**Status:** Análise e Planejamento

---

## 🔍 1. ANÁLISE CRÍTICA DO SISTEMA ATUAL

### 1.1 Relatórios Existentes (JSON)

#### ✅ Implementados:
- **Vendas (`sales`)**: Vendas por data e por hora
- **Financeiro (`financial`)**: Receitas e despesas (usando FINANCIAL_TRANSACTIONS legado)
- **Performance (`performance`)**: Tempo médio de preparo e taxa de cancelamento
- **Funcionários (`employees`)**: Performance de atendentes

#### ⚠️ Limitações Identificadas:
1. **Períodos Fixos**: Apenas `last_7_days`, `last_30_days`, `this_month` - sem flexibilidade de datas customizadas
2. **Dados Básicos**: Falta profundidade analítica (tendências, comparações, métricas avançadas)
3. **Sem Agrupamentos**: Não há relatórios por categoria, produto, cliente, etc.
4. **Sem Visualizações**: Apenas dados tabulares, sem gráficos ou insights visuais

### 1.2 Relatórios PDF Existentes

#### ✅ Implementados:
- **Usuários**: Lista de usuários com filtros básicos
- **Ingredientes**: Lista de ingredientes e status de estoque
- **Produtos**: Lista de produtos do cardápio
- **Pedidos**: Lista de pedidos com filtros de data/status

#### ⚠️ Limitações Identificadas:
1. **Formato Básico**: Apenas tabelas simples, sem gráficos, sem análises profundas
2. **Sem Agregações**: Não calcula totais, médias, percentuais automaticamente
3. **Sem Comparações**: Não compara períodos ou mostra tendências
4. **Sem Métricas de Negócio**: Falta ROI, margem de lucro, custos por produto, etc.
5. **Sem Exportação Avançada**: Apenas PDF, sem Excel, CSV, ou outros formatos

### 1.3 Estrutura de Dados Disponível

#### Tabelas Principais para Relatórios:
- `ORDERS`: Pedidos e vendas
- `ORDER_ITEMS`: Itens dos pedidos
- `ORDER_ITEM_EXTRAS`: Extras e modificações
- `FINANCIAL_MOVEMENTS`: Movimentações financeiras (novo sistema)
- `FINANCIAL_TRANSACTIONS`: Transações financeiras (legado)
- `PRODUCTS`: Produtos do cardápio
- `INGREDIENTS`: Ingredientes e estoque
- `USERS`: Usuários (clientes e funcionários)
- `LOYALTY_POINTS`: Pontos de fidelidade
- `PURCHASE_INVOICES`: Notas fiscais de compra
- `PURCHASE_INVOICE_ITEMS`: Itens das compras
- `RECURRING_TAXES`: Impostos recorrentes
- `RECURRENCE_RULES`: Regras de recorrência
- `NOTIFICATIONS`: Notificações do sistema
- `CHATS`: Chat de pedidos
- `RESTAURANT_TABLES`: Mesas do restaurante

---

## 🎯 2. RELATÓRIOS NECESSÁRIOS PARA ANÁLISE COMPLETA

### 2.1 Relatórios de Vendas e Pedidos

#### 2.1.1 Relatório de Vendas Detalhado
**Objetivo:** Análise completa de vendas com múltiplas dimensões

**Conteúdo:**
- Resumo executivo (total vendido, número de pedidos, ticket médio)
- Vendas por período (diário, semanal, mensal)
- Vendas por tipo de pedido (delivery, pickup, on_site)
- Vendas por método de pagamento
- Vendas por status (completos, cancelados, em andamento)
- Top 10 produtos mais vendidos (quantidade e receita)
- Top 10 clientes (por valor gasto)
- Análise de horários de pico
- Comparação com período anterior (crescimento/queda %)
- Gráficos: linha temporal, pizza (métodos de pagamento), barras (top produtos)

**Filtros:**
- Data início/fim (customizável)
- Tipo de pedido
- Método de pagamento
- Status do pedido
- Cliente específico
- Produto específico

**Métricas Calculadas:**
- Ticket médio
- Taxa de conversão
- Taxa de cancelamento
- Crescimento percentual
- Variação diária/semanal/mensal

#### 2.1.2 Relatório de Performance de Pedidos
**Objetivo:** Análise de eficiência operacional

**Conteúdo:**
- Tempo médio de preparo por período
- Tempo médio de entrega (delivery)
- Tempo médio total (criação → entrega)
- Taxa de cancelamento por motivo
- Taxa de cancelamento por período
- Pedidos por atendente (performance individual)
- Pedidos por entregador (performance individual)
- Análise de atrasos (pedidos que excederam prazos)
- Satisfação do cliente (se houver sistema de avaliação)

**Filtros:**
- Data início/fim
- Atendente específico
- Entregador específico
- Status do pedido
- Tipo de pedido

**Métricas Calculadas:**
- Tempo médio de preparo
- Tempo médio de entrega
- Taxa de cancelamento
- Taxa de atraso
- Eficiência por funcionário

#### 2.1.3 Relatório de Análise de Produtos
**Objetivo:** Entender quais produtos vendem mais e geram mais receita

**Conteúdo:**
- Top 20 produtos mais vendidos (quantidade)
- Top 20 produtos por receita
- Produtos menos vendidos (identificar problemas)
- Margem de lucro por produto
- Custo de produção por produto
- Rotatividade de produtos
- Produtos por categoria
- Análise de sazonalidade (se houver dados históricos)

**Filtros:**
- Data início/fim
- Categoria
- Produto específico
- Faixa de preço
- Status (ativo/inativo)

**Métricas Calculadas:**
- Quantidade vendida
- Receita total
- Margem de lucro
- Custo de produção
- ROI por produto
- Taxa de rotatividade

### 2.2 Relatórios Financeiros

#### 2.2.1 Relatório Financeiro Completo (Fluxo de Caixa)
**Objetivo:** Análise financeira detalhada usando FINANCIAL_MOVEMENTS

**Conteúdo:**
- Resumo executivo (receitas, despesas, lucro líquido, fluxo de caixa)
- Receitas por categoria (vendas, outros)
- Despesas por categoria (CMV, operacionais, impostos)
- Fluxo de caixa diário/semanal/mensal
- Contas a pagar (pendentes)
- Contas a receber (se aplicável)
- Análise de margem bruta e líquida
- Comparação com período anterior
- Projeção de fluxo de caixa (baseado em recorrências)
- Gráficos: fluxo de caixa temporal, pizza (categorias), barras (comparação)

**Filtros:**
- Data início/fim
- Tipo de movimentação (REVENUE, EXPENSE, CMV, TAX)
- Categoria
- Status de pagamento
- Método de pagamento

**Métricas Calculadas:**
- Receita total
- Despesa total
- CMV total
- Impostos totais
- Lucro bruto
- Lucro líquido
- Fluxo de caixa líquido
- Margem bruta (%)
- Margem líquida (%)
- ROI

#### 2.2.2 Relatório de Custos e CMV (Custo das Mercadorias Vendidas)
**Objetivo:** Análise detalhada de custos de produção

**Conteúdo:**
- CMV total por período
- CMV por categoria de ingrediente
- CMV por produto
- Custo médio por pedido
- Análise de desperdício (se houver dados)
- Comparação custo vs. receita por produto
- Top 10 produtos com maior custo
- Análise de variação de custos (comparação com período anterior)

**Filtros:**
- Data início/fim
- Categoria de ingrediente
- Produto específico
- Tipo de movimentação (CMV)

**Métricas Calculadas:**
- CMV total
- CMV médio por pedido
- CMV por produto
- Percentual de CMV sobre receita
- Variação de custos (%)

#### 2.2.3 Relatório de Impostos e Taxas
**Objetivo:** Análise de impostos e taxas recorrentes

**Conteúdo:**
- Total de impostos pagos por período
- Impostos por categoria
- Impostos recorrentes (RECURRING_TAXES)
- Taxas de métodos de pagamento (cartão, PIX, iFood, etc.)
- Análise de impacto das taxas na receita
- Comparação com período anterior
- Projeção de impostos futuros (baseado em recorrências)

**Filtros:**
- Data início/fim
- Categoria de imposto
- Tipo de recorrência
- Status (ativo/inativo)

**Métricas Calculadas:**
- Total de impostos
- Taxa média de pagamento
- Impacto percentual na receita
- Projeção futura

### 2.3 Relatórios de Estoque

#### 2.3.1 Relatório de Estoque Completo
**Objetivo:** Análise detalhada de estoque e movimentações

**Conteúdo:**
- Resumo de estoque (total de ingredientes, valor total, status)
- Ingredientes por status (ok, low, out_of_stock)
- Valor total do estoque
- Ingredientes mais utilizados
- Ingredientes com maior giro
- Ingredientes parados (sem movimentação)
- Análise de reposição (quando estoque baixo)
- Histórico de movimentações (entradas e saídas)
- Previsão de reposição (baseado em consumo médio)

**Filtros:**
- Status de estoque
- Categoria de ingrediente
- Fornecedor
- Faixa de preço
- Faixa de quantidade

**Métricas Calculadas:**
- Valor total do estoque
- Quantidade total de itens
- Taxa de giro
- Tempo médio de reposição
- Custo médio de reposição

#### 2.3.2 Relatório de Compras e Fornecedores
**Objetivo:** Análise de compras e relacionamento com fornecedores

**Conteúdo:**
- Total de compras por período
- Compras por fornecedor
- Itens mais comprados
- Valor médio de compra
- Análise de notas fiscais (PURCHASE_INVOICES)
- Status de pagamento das compras
- Comparação de preços entre fornecedores (se houver múltiplos)
- Análise de frequência de compras

**Filtros:**
- Data início/fim
- Fornecedor
- Status de pagamento
- Item específico

**Métricas Calculadas:**
- Total gasto em compras
- Valor médio de compra
- Frequência de compras
- Custo médio por item

### 2.4 Relatórios de Clientes

#### 2.4.1 Relatório de Análise de Clientes
**Objetivo:** Entender comportamento e valor dos clientes

**Conteúdo:**
- Total de clientes (ativos, inativos, novos)
- Top 50 clientes por valor gasto
- Clientes mais frequentes (número de pedidos)
- Análise de recência, frequência e valor (RFV)
- Clientes inativos (último pedido há X dias)
- Análise de pontos de fidelidade (LOYALTY_POINTS)
- Clientes por região (baseado em endereços)
- Análise de ticket médio por cliente
- Taxa de retenção de clientes

**Filtros:**
- Data início/fim
- Status (ativo/inativo)
- Região/cidade
- Faixa de valor gasto
- Número mínimo de pedidos

**Métricas Calculadas:**
- Total de clientes
- Clientes ativos
- Clientes novos
- Ticket médio por cliente
- Valor médio por cliente
- Taxa de retenção
- Lifetime Value (LTV)

#### 2.4.2 Relatório de Programa de Fidelidade
**Objetivo:** Análise do programa de pontos

**Conteúdo:**
- Total de pontos acumulados
- Total de pontos resgatados
- Pontos expirados (se aplicável)
- Top clientes por pontos
- Análise de resgates (frequência, valor médio)
- Impacto do programa na receita
- Taxa de participação no programa

**Filtros:**
- Data início/fim
- Cliente específico
- Tipo de transação (ganho/resgate)

**Métricas Calculadas:**
- Total de pontos acumulados
- Total de pontos resgatados
- Valor em pontos
- Taxa de resgate
- Impacto na receita

### 2.5 Relatórios de Funcionários

#### 2.5.1 Relatório de Performance de Funcionários
**Objetivo:** Avaliar desempenho individual e coletivo

**Conteúdo:**
- Performance por atendente (pedidos atendidos, receita gerada, tempo médio)
- Performance por entregador (entregas, tempo médio, avaliações se houver)
- Ranking de funcionários
- Análise de produtividade (pedidos por hora)
- Análise de eficiência (tempo médio de atendimento)
- Horas trabalhadas (se houver sistema de ponto)
- Análise de absenteísmo (se aplicável)

**Filtros:**
- Data início/fim
- Funcionário específico
- Cargo (attendant, delivery)
- Status (ativo/inativo)

**Métricas Calculadas:**
- Pedidos atendidos
- Receita gerada
- Tempo médio de atendimento
- Produtividade (pedidos/hora)
- Eficiência (%)

### 2.6 Relatórios Operacionais

#### 2.6.1 Relatório de Mesas e Salão
**Objetivo:** Análise de ocupação e eficiência do salão

**Conteúdo:**
- Taxa de ocupação por mesa
- Tempo médio de permanência por mesa
- Rotatividade de mesas
- Mesas mais utilizadas
- Análise de horários de pico no salão
- Receita por mesa
- Análise de eficiência do atendimento no salão

**Filtros:**
- Data início/fim
- Mesa específica
- Atendente específico
- Status da mesa

**Métricas Calculadas:**
- Taxa de ocupação
- Tempo médio de permanência
- Rotatividade
- Receita por mesa

#### 2.6.2 Relatório de Chat e Atendimento
**Objetivo:** Análise de qualidade do atendimento

**Conteúdo:**
- Total de chats abertos
- Tempo médio de resposta
- Chats por atendente
- Taxa de resolução (chats fechados)
- Análise de mensagens por pedido
- Tempo médio de atendimento

**Filtros:**
- Data início/fim
- Atendente específico
- Status do chat (aberto/fechado)
- Pedido específico

**Métricas Calculadas:**
- Total de chats
- Tempo médio de resposta
- Taxa de resolução
- Mensagens por chat

### 2.7 Relatórios Gerenciais

#### 2.7.1 Dashboard Executivo (Resumo Geral)
**Objetivo:** Visão geral do negócio em um único relatório

**Conteúdo:**
- KPIs principais (receita, pedidos, ticket médio, lucro)
- Gráficos de tendências (vendas, receita, lucro)
- Top 5 produtos mais vendidos
- Top 5 clientes
- Alertas (estoque baixo, contas a pagar, etc.)
- Comparação com período anterior
- Metas vs. Realizado (se houver em APP_SETTINGS)

**Filtros:**
- Data início/fim
- Período de comparação

**Métricas Calculadas:**
- Todos os KPIs principais
- Variações percentuais
- Taxa de crescimento

#### 2.7.2 Relatório de Conciliação Bancária
**Objetivo:** Análise de conciliação financeira

**Conteúdo:**
- Movimentações conciliadas vs. não conciliadas
- Diferenças entre sistema e extrato bancário
- Análise por gateway de pagamento
- Transações pendentes de conciliação
- Histórico de conciliações

**Filtros:**
- Data início/fim
- Status de conciliação
- Gateway de pagamento
- Conta bancária

**Métricas Calculadas:**
- Total conciliado
- Total pendente
- Diferenças encontradas

---

## 🏗️ 3. ARQUITETURA E IMPLEMENTAÇÃO

### 3.1 Estrutura de Arquivos Proposta

```
RoyalBurgerAPI/
├── src/
│   ├── services/
│   │   ├── reports_service.py (existente - expandir)
│   │   ├── pdf_report_service.py (existente - expandir)
│   │   ├── advanced_reports_service.py (NOVO)
│   │   └── report_analytics_service.py (NOVO)
│   ├── routes/
│   │   ├── reports_routes.py (existente - expandir)
│   │   └── pdf_report_routes.py (existente - expandir)
│   └── utils/
│       ├── report_formatters.py (NOVO)
│       ├── chart_generators.py (NOVO)
│       └── report_validators.py (NOVO)
└── docs/
    └── PLANO_IMPLEMENTACAO_RELATORIOS_PDF.md (este arquivo)
```

### 3.2 Dependências Necessárias

#### Backend (Python):
```python
# Já existentes:
fpdf2  # Geração de PDF básica
# Adicionar:
matplotlib  # Gráficos para PDF
seaborn  # Gráficos estatísticos (opcional)
pandas  # Análise de dados e agregações
numpy  # Cálculos numéricos
reportlab  # Alternativa mais avançada ao fpdf2 (opcional)
```

#### Considerações:
- **fpdf2**: Mantém compatibilidade, mas limitado para gráficos
- **matplotlib**: Essencial para gráficos em PDF
- **pandas**: Facilita agregações e análises complexas
- **reportlab**: Considerar migração futura para mais recursos

### 3.3 Padrões de Código

#### Estrutura de Função de Relatório:
```python
def generate_[tipo]_report(filters=None, format='pdf'):
    """
    Gera relatório [tipo] com filtros aplicados.
    
    Args:
        filters: dict com filtros (start_date, end_date, etc.)
        format: 'pdf', 'json', 'excel' (futuro)
    
    Returns:
        bytes (PDF) ou dict (JSON)
    """
    # 1. Validar filtros
    # 2. Buscar dados do banco
    # 3. Calcular métricas e agregações
    # 4. Gerar visualizações (gráficos)
    # 5. Formatar e retornar
```

#### Estrutura de Dados de Relatório:
```python
report_data = {
    "metadata": {
        "type": "sales_detailed",
        "title": "Relatório de Vendas Detalhado",
        "period": {
            "start_date": "2024-01-01",
            "end_date": "2024-01-31"
        },
        "generated_at": "2024-01-31T10:00:00",
        "filters_applied": {...}
    },
    "summary": {
        "total_revenue": 50000.00,
        "total_orders": 500,
        "average_ticket": 100.00,
        "growth_percentage": 15.5
    },
    "data": {
        "sales_by_date": [...],
        "sales_by_product": [...],
        "sales_by_payment_method": [...]
    },
    "charts": {
        "sales_timeline": "base64_encoded_image",
        "payment_methods_pie": "base64_encoded_image"
    }
}
```

---

## 📋 4. PASSO A PASSO DE IMPLEMENTAÇÃO

### FASE 1: Fundação e Infraestrutura (Semanas 1-2)

#### 4.1.1 Atualizar Dependências
**Arquivo:** `requirements.txt`

```python
# Adicionar:
matplotlib==3.7.2
pandas==2.0.3
numpy==1.24.3
```

**Ação:**
- Adicionar dependências ao `requirements.txt`
- Documentar no README
- Testar instalação

#### 4.1.2 Criar Utilitários de Formatação
**Arquivo:** `src/utils/report_formatters.py` (NOVO)

**Conteúdo:**
- Funções para formatar valores monetários
- Funções para formatar datas
- Funções para formatar percentuais
- Funções para truncar textos longos
- Funções para calcular variações percentuais

**Exemplo:**
```python
def format_currency(value):
    """Formata valor como moeda brasileira"""
    return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def calculate_growth_percentage(current, previous):
    """Calcula percentual de crescimento"""
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return ((current - previous) / previous) * 100
```

#### 4.1.3 Criar Gerador de Gráficos
**Arquivo:** `src/utils/chart_generators.py` (NOVO)

**Conteúdo:**
- Função para gerar gráfico de linha (tendências temporais)
- Função para gerar gráfico de barras (comparações)
- Função para gerar gráfico de pizza (distribuições)
- Função para converter gráfico em base64 (para PDF)

**Exemplo:**
```python
import matplotlib
matplotlib.use('Agg')  # Backend sem GUI
import matplotlib.pyplot as plt
import io
import base64

def generate_line_chart(data, title, x_label, y_label):
    """Gera gráfico de linha e retorna base64"""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(data['dates'], data['values'])
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    
    # Converter para base64
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode()
    plt.close()
    
    return image_base64
```

#### 4.1.4 Expandir BaseReportPDF
**Arquivo:** `src/services/pdf_report_service.py`

**Adicionar métodos:**
- `add_chart()`: Adiciona gráfico ao PDF
- `add_metric_card()`: Adiciona card de métrica (KPI)
- `add_comparison_section()`: Adiciona seção de comparação
- `add_trend_analysis()`: Adiciona análise de tendências

**Exemplo:**
```python
def add_chart(self, chart_base64, width=190, height=100):
    """Adiciona gráfico ao PDF a partir de base64"""
    import base64
    from io import BytesIO
    from PIL import Image
    
    # Decodifica imagem
    image_data = base64.b64decode(chart_base64)
    image = Image.open(BytesIO(image_data))
    
    # Adiciona ao PDF
    self.image(image, x=10, y=self.get_y(), w=width, h=height)
    self.ln(height + 5)
```

### FASE 2: Relatórios de Vendas Expandidos (Semanas 3-4)

#### 4.2.1 Implementar Relatório de Vendas Detalhado
**Arquivo:** `src/services/advanced_reports_service.py` (NOVO)

**Função:** `generate_detailed_sales_report(filters)`

**Passos:**
1. Validar filtros (datas, tipos, etc.)
2. Buscar dados de ORDERS, ORDER_ITEMS, ORDER_ITEM_EXTRAS
3. Calcular métricas:
   - Total vendido
   - Número de pedidos
   - Ticket médio
   - Vendas por tipo de pedido
   - Vendas por método de pagamento
   - Top produtos
   - Top clientes
4. Gerar agregações temporais (diário, semanal, mensal)
5. Comparar com período anterior
6. Gerar gráficos:
   - Linha temporal de vendas
   - Pizza de métodos de pagamento
   - Barras de top produtos
7. Formatar para PDF

**Rota:** `POST /api/pdf_reports/sales/detailed`

#### 4.2.2 Implementar Relatório de Performance de Pedidos
**Função:** `generate_orders_performance_report(filters)`

**Passos:**
1. Buscar dados de ORDERS com tempos
2. Calcular:
   - Tempo médio de preparo
   - Tempo médio de entrega
   - Taxa de cancelamento
   - Taxa de atraso
3. Agrupar por atendente/entregador
4. Gerar gráficos de performance
5. Formatar para PDF

**Rota:** `POST /api/pdf_reports/orders/performance`

#### 4.2.3 Implementar Relatório de Análise de Produtos
**Função:** `generate_products_analysis_report(filters)`

**Passos:**
1. Buscar dados de ORDER_ITEMS, PRODUCTS, INGREDIENTS
2. Calcular:
   - Quantidade vendida por produto
   - Receita por produto
   - CMV por produto
   - Margem de lucro por produto
3. Identificar top e bottom produtos
4. Gerar gráficos comparativos
5. Formatar para PDF

**Rota:** `POST /api/pdf_reports/products/analysis`

### FASE 3: Relatórios Financeiros Avançados (Semanas 5-6)

#### 4.3.1 Expandir Relatório Financeiro Completo
**Arquivo:** `src/services/reports_service.py` (expandir `get_detailed_financial_report`)

**Melhorias:**
1. Adicionar gráficos de fluxo de caixa
2. Adicionar análise de tendências
3. Adicionar projeções baseadas em recorrências
4. Adicionar comparação com período anterior
5. Adicionar análise de margens

**Rota:** `POST /api/pdf_reports/financial/complete`

#### 4.3.2 Implementar Relatório de CMV
**Função:** `generate_cmv_report(filters)`

**Passos:**
1. Buscar dados de FINANCIAL_MOVEMENTS (tipo CMV)
2. Buscar dados de ORDER_ITEMS e INGREDIENTS
3. Calcular CMV por produto, categoria, período
4. Comparar com receita
5. Gerar gráficos de análise de custos
6. Formatar para PDF

**Rota:** `POST /api/pdf_reports/financial/cmv`

#### 4.3.3 Implementar Relatório de Impostos
**Função:** `generate_taxes_report(filters)`

**Passos:**
1. Buscar dados de FINANCIAL_MOVEMENTS (tipo TAX)
2. Buscar dados de RECURRING_TAXES
3. Calcular totais e projeções
4. Analisar impacto na receita
5. Gerar gráficos
6. Formatar para PDF

**Rota:** `POST /api/pdf_reports/financial/taxes`

### FASE 4: Relatórios de Estoque e Compras (Semanas 7-8)

#### 4.4.1 Expandir Relatório de Estoque
**Função:** `generate_complete_stock_report(filters)`

**Melhorias:**
1. Adicionar análise de giro
2. Adicionar previsão de reposição
3. Adicionar histórico de movimentações
4. Adicionar gráficos de status de estoque
5. Adicionar análise de valor

**Rota:** `POST /api/pdf_reports/stock/complete`

#### 4.4.2 Implementar Relatório de Compras
**Função:** `generate_purchases_report(filters)`

**Passos:**
1. Buscar dados de PURCHASE_INVOICES, PURCHASE_INVOICE_ITEMS
2. Calcular totais por fornecedor, item, período
3. Analisar frequência e valores
4. Gerar gráficos comparativos
5. Formatar para PDF

**Rota:** `POST /api/pdf_reports/purchases`

### FASE 5: Relatórios de Clientes e Fidelidade (Semanas 9-10)

#### 4.5.1 Implementar Relatório de Análise de Clientes
**Função:** `generate_customers_analysis_report(filters)`

**Passos:**
1. Buscar dados de USERS, ORDERS, ADDRESSES
2. Calcular métricas RFV (Recência, Frequência, Valor)
3. Identificar top clientes e segmentos
4. Analisar comportamento e padrões
5. Gerar gráficos de segmentação
6. Formatar para PDF

**Rota:** `POST /api/pdf_reports/customers/analysis`

#### 4.5.2 Implementar Relatório de Fidelidade
**Função:** `generate_loyalty_report(filters)`

**Passos:**
1. Buscar dados de LOYALTY_POINTS, LOYALTY_POINTS_HISTORY
2. Calcular totais de pontos, resgates, expirações
3. Analisar impacto na receita
4. Identificar top participantes
5. Gerar gráficos de engajamento
6. Formatar para PDF

**Rota:** `POST /api/pdf_reports/loyalty`

### FASE 6: Relatórios Operacionais e Gerenciais (Semanas 11-12)

#### 4.6.1 Implementar Relatório de Mesas
**Função:** `generate_tables_report(filters)`

**Passos:**
1. Buscar dados de RESTAURANT_TABLES, ORDERS
2. Calcular ocupação, rotatividade, receita por mesa
3. Analisar eficiência
4. Gerar gráficos de ocupação
5. Formatar para PDF

**Rota:** `POST /api/pdf_reports/tables`

#### 4.6.2 Implementar Dashboard Executivo
**Função:** `generate_executive_dashboard(filters)`

**Passos:**
1. Agregar dados de todas as áreas
2. Calcular KPIs principais
3. Gerar múltiplos gráficos (visão geral)
4. Adicionar alertas e insights
5. Formatar para PDF (formato especial, mais visual)

**Rota:** `POST /api/pdf_reports/executive/dashboard`

#### 4.6.3 Implementar Relatório de Conciliação
**Função:** `generate_reconciliation_report(filters)`

**Passos:**
1. Buscar dados de FINANCIAL_MOVEMENTS com campos de conciliação
2. Comparar movimentações conciliadas vs. não conciliadas
3. Identificar diferenças
4. Gerar relatório de auditoria
5. Formatar para PDF

**Rota:** `POST /api/pdf_reports/financial/reconciliation`

---

## 🔒 5. SEGURANÇA E PERFORMANCE

### 5.1 Segurança

#### Validação de Filtros:
- Validar todas as datas (formato, range válido)
- Validar IDs (inteiros positivos)
- Sanitizar strings de busca
- Limitar tamanho de períodos (ex: máximo 1 ano)
- Validar permissões (apenas admin/manager)

#### Proteção de Dados:
- Não expor dados sensíveis (senhas, tokens)
- Logar acessos a relatórios
- Rate limiting em endpoints de relatórios pesados

### 5.2 Performance

#### Otimizações de Query:
- Usar índices existentes (CREATED_AT, STATUS, etc.)
- Criar índices adicionais se necessário:
  ```sql
  CREATE INDEX IDX_ORDERS_CREATED_STATUS ON ORDERS(CREATED_AT, STATUS);
  CREATE INDEX IDX_FINANCIAL_MOVEMENTS_DATE_TYPE ON FINANCIAL_MOVEMENTS(MOVEMENT_DATE, TYPE);
  ```
- Usar agregações no banco (SUM, COUNT, AVG) ao invés de Python
- Paginar dados grandes (limitar resultados)

#### Cache:
- Cachear relatórios estáticos (ex: relatório do mês anterior)
- TTL de 1 hora para relatórios recentes
- Invalidar cache quando dados mudarem

#### Background Jobs:
- Para relatórios muito pesados, considerar processamento assíncrono
- Retornar job_id e permitir download quando pronto
- Usar Celery ou similar (futuro)

---

## 📊 6. ESTRUTURA DE DADOS PARA RELATÓRIOS

### 6.1 Schema de Resposta Padrão

```python
{
    "report": {
        "type": "sales_detailed",
        "title": "Relatório de Vendas Detalhado",
        "period": {
            "start_date": "2024-01-01",
            "end_date": "2024-01-31"
        },
        "generated_at": "2024-01-31T10:00:00Z",
        "filters": {...}
    },
    "summary": {
        "total_revenue": 50000.00,
        "total_orders": 500,
        "average_ticket": 100.00,
        "growth_percentage": 15.5,
        "comparison_period": {
            "total_revenue": 43250.00,
            "growth": 15.5
        }
    },
    "data": {
        "sales_by_date": [...],
        "sales_by_product": [...],
        "sales_by_payment_method": [...],
        "top_customers": [...]
    },
    "charts": {
        "sales_timeline": "base64_image",
        "payment_methods_pie": "base64_image"
    }
}
```

### 6.2 Estrutura de PDF

1. **Capa** (opcional para relatórios longos):
   - Logo
   - Título
   - Período
   - Data de emissão

2. **Resumo Executivo**:
   - KPIs principais
   - Cards de métricas
   - Comparação com período anterior

3. **Análise Detalhada**:
   - Tabelas de dados
   - Gráficos
   - Insights e observações

4. **Anexos** (se necessário):
   - Dados brutos
   - Metodologia
   - Glossário

---

## 🧪 7. TESTES

### 7.1 Testes Unitários

**Arquivo:** `tests/test_reports_service.py` (NOVO)

**Cenários:**
- Validação de filtros
- Cálculo de métricas
- Formatação de dados
- Geração de gráficos
- Formatação de PDF

### 7.2 Testes de Integração

**Cenários:**
- Geração completa de relatório
- Integração com banco de dados
- Performance com grandes volumes
- Tratamento de erros

---

## 📈 8. MELHORIAS FUTURAS

### 8.1 Exportação em Múltiplos Formatos
- Excel (.xlsx)
- CSV
- JSON estruturado

### 8.2 Agendamento de Relatórios
- Relatórios automáticos (diários, semanais, mensais)
- Envio por email
- Armazenamento de histórico

### 8.3 Relatórios Interativos
- Dashboard web com gráficos interativos
- Filtros dinâmicos
- Drill-down (clicar para detalhar)

### 8.4 Machine Learning
- Previsões de vendas
- Detecção de anomalias
- Recomendações automáticas

---

## ✅ 9. CHECKLIST DE IMPLEMENTAÇÃO

### Fase 1: Fundação
- [ ] Adicionar dependências (matplotlib, pandas, numpy)
- [ ] Criar `report_formatters.py`
- [ ] Criar `chart_generators.py`
- [ ] Expandir `BaseReportPDF` com novos métodos
- [ ] Criar testes unitários básicos

### Fase 2: Vendas
- [ ] Implementar relatório de vendas detalhado
- [ ] Implementar relatório de performance de pedidos
- [ ] Implementar relatório de análise de produtos
- [ ] Criar rotas correspondentes
- [ ] Testar geração de PDFs

### Fase 3: Financeiro
- [ ] Expandir relatório financeiro completo
- [ ] Implementar relatório de CMV
- [ ] Implementar relatório de impostos
- [ ] Criar rotas correspondentes
- [ ] Testar geração de PDFs

### Fase 4: Estoque
- [ ] Expandir relatório de estoque
- [ ] Implementar relatório de compras
- [ ] Criar rotas correspondentes
- [ ] Testar geração de PDFs

### Fase 5: Clientes
- [ ] Implementar relatório de análise de clientes
- [ ] Implementar relatório de fidelidade
- [ ] Criar rotas correspondentes
- [ ] Testar geração de PDFs

### Fase 6: Operacional
- [ ] Implementar relatório de mesas
- [ ] Implementar dashboard executivo
- [ ] Implementar relatório de conciliação
- [ ] Criar rotas correspondentes
- [ ] Testar geração de PDFs

### Finalização
- [ ] Documentar todas as rotas
- [ ] Atualizar Swagger/OpenAPI
- [ ] Criar guia de uso
- [ ] Testes de performance
- [ ] Revisão de segurança

---

## 📝 10. NOTAS DE IMPLEMENTAÇÃO

### 10.1 Considerações de Performance
- Relatórios grandes podem demorar. Considerar:
  - Limitar período máximo (ex: 1 ano)
  - Processamento assíncrono para relatórios > 10.000 registros
  - Cache de resultados

### 10.2 Considerações de Memória
- PDFs com muitos gráficos podem ser pesados
- Limitar número de gráficos por página
- Comprimir imagens antes de inserir no PDF

### 10.3 Considerações de UX
- Sempre mostrar progresso para relatórios longos
- Permitir cancelamento de geração
- Fornecer estimativa de tempo

---

## 🎯 CONCLUSÃO

Este documento apresenta um plano completo para transformar o sistema de relatórios atual em uma solução robusta e abrangente. A implementação deve ser feita de forma incremental, priorizando os relatórios mais críticos para o negócio.

**Prioridade de Implementação:**
1. **Alta**: Relatórios de Vendas Detalhado, Financeiro Completo, Dashboard Executivo
2. **Média**: Relatórios de Estoque, Clientes, Performance
3. **Baixa**: Relatórios Operacionais (Mesas, Chat), Conciliação

**Tempo Estimado Total:** 12 semanas (3 meses) com 1 desenvolvedor dedicado.

---

**Documento criado seguindo as diretrizes de `.cursorrules`**  
**Última atualização:** 2024

