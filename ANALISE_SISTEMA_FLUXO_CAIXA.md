# 📊 ANÁLISE PROFUNDA — Sistema de Fluxo de Caixa Royal Burger

## 🎯 **VISÃO GERAL DO SISTEMA**

O sistema de fluxo de caixa do Royal Burger é uma **solução completa de contabilidade gerencial** que registra, rastreia e analisa todas as movimentações financeiras do restaurante. Ele diferencia **compromissos financeiros** (Pending) de **movimentos reais de caixa** (Paid), permitindo tanto o controle de **fluxo de caixa direto** quanto a gestão de **contas a pagar/receber**.

---

## 🏗️ **ARQUITETURA E COMPONENTES**

### **1. Estrutura de Dados**

#### **1.1. Tabela Principal: `FINANCIAL_MOVEMENTS`**

A tabela central armazena **todas as movimentações financeiras** com os seguintes campos:

| Campo | Tipo | Descrição | Uso Prático |
|-------|------|-----------|-------------|
| `ID` | INT | Identificador único | Chave primária |
| `TYPE` | VARCHAR | Tipo: `REVENUE`, `EXPENSE`, `CMV`, `TAX` | Classificação contábil |
| `"VALUE"` | DECIMAL | Valor da movimentação | Sempre positivo |
| `CATEGORY` | VARCHAR | Categoria macro (ex: "Vendas", "Custos Fixos") | Agrupamento para relatórios |
| `SUBCATEGORY` | VARCHAR | Subcategoria (ex: "Cartão de Crédito", "Aluguel") | Detalhamento |
| `DESCRIPTION` | VARCHAR | Descrição da movimentação | Contexto e rastreabilidade |
| `MOVEMENT_DATE` | TIMESTAMP | **Data real do movimento de caixa** | Usado para fluxo de caixa real |
| `PAYMENT_STATUS` | VARCHAR | `Pending` ou `Paid` | Diferencia compromisso de caixa |
| `PAYMENT_METHOD` | VARCHAR | Método de pagamento | Análise por forma de pagamento |
| `SENDER_RECEIVER` | VARCHAR | Quem pagou/recebeu | Rastreabilidade |
| `RELATED_ENTITY_TYPE` | VARCHAR | Tipo de entidade relacionada | Link com origem (ex: "order", "purchase_invoice") |
| `RELATED_ENTITY_ID` | INT | ID da entidade relacionada | Rastreabilidade completa |
| `NOTES` | VARCHAR | Observações adicionais | Contexto adicional |
| `PAYMENT_GATEWAY_ID` | VARCHAR | ID do gateway de pagamento | Conciliação bancária |
| `TRANSACTION_ID` | VARCHAR | ID da transação no gateway | Rastreamento externo |
| `BANK_ACCOUNT` | VARCHAR | Conta bancária | Conciliação |
| `RECONCILED` | BOOLEAN | Se foi reconciliado | Controle de conciliação |
| `RECONCILED_AT` | TIMESTAMP | Data da conciliação | Auditoria |
| `CREATED_BY` | INT | ID do usuário que criou | Auditoria |
| `CREATED_AT` | TIMESTAMP | Data de criação | Auditoria |
| `UPDATED_AT` | TIMESTAMP | Última atualização | Auditoria |

**Conceito Chave: `MOVEMENT_DATE` vs `CREATED_AT`**
- **`MOVEMENT_DATE`**: Data em que o dinheiro **realmente entrou/saiu** do caixa (usado para fluxo de caixa real)
- **`CREATED_AT`**: Data em que o registro foi criado no sistema
- **Para `Pending`**: `MOVEMENT_DATE` pode ser a **data esperada** de pagamento (melhora projeção)

---

## 🔄 **FLUXOS DE FUNCIONAMENTO**

### **2. FLUXO 1: Registro Automático de Vendas (Pedidos)**

#### **2.1. Quando Ocorre**

Quando um pedido é finalizado (status muda para `'delivered'`), o sistema **automaticamente** registra:

1. **Receita (REVENUE)**
2. **CMV (Custo de Mercadoria Vendida)**
3. **Taxa de Pagamento (EXPENSE)** — se aplicável

#### **2.2. Processo Detalhado**

**Passo 1: Finalização do Pedido**
```
Cliente recebe pedido → Status muda para 'delivered'
```

**Passo 2: Transação Atômica (Tudo ou Nada)**
```python
# Em order_service.py - update_order_status()
1. Atualiza status do pedido para 'delivered'
2. Baixa estoque dos ingredientes (deduct_stock_for_order)
3. Registra receita (REVENUE)
4. Calcula e registra CMV
5. Calcula e registra taxa de pagamento (se houver)
6. COMMIT único ou ROLLBACK completo
```

**Passo 3: Cálculo do CMV**

O sistema calcula o CMV de duas formas (com fallback):

1. **Prioridade 1**: Usa `COST_PRICE` do produto (se disponível e > 0)
2. **Prioridade 2**: Calcula pela soma dos custos dos ingredientes

```python
# Para cada item do pedido:
CMV_item = (custo_unitário_produto OU soma_custos_ingredientes) × quantidade
CMV_total = Σ CMV_item
```

**Passo 4: Registro da Receita**

```json
{
  "type": "REVENUE",
  "value": 50.00,  // Valor total do pedido (já com descontos)
  "category": "Vendas",
  "subcategory": "Cartão de Crédito",  // Baseado no payment_method
  "description": "Venda - Pedido #123",
  "movement_date": "2024-01-15T14:30:00",  // Data do pagamento
  "payment_status": "Paid",  // Sempre Paid para pedidos finalizados
  "payment_method": "credit",
  "related_entity_type": "order",
  "related_entity_id": 123
}
```

**Passo 5: Registro do CMV**

```json
{
  "type": "CMV",
  "value": 15.00,  // Custo calculado dos ingredientes
  "category": "Custos Variáveis",
  "subcategory": "Ingredientes Consumidos",
  "description": "CMV - Pedido #123",
  "movement_date": "2024-01-15T14:30:00",
  "payment_status": "Paid",
  "related_entity_type": "order",
  "related_entity_id": 123
}
```

**Passo 6: Registro da Taxa de Pagamento (Fase 3)**

O sistema consulta `APP_SETTINGS` para obter as taxas configuradas:

```python
# Taxas configuráveis em APP_SETTINGS:
- TAXA_CARTAO_CREDITO: 2.5%  // Exemplo
- TAXA_CARTAO_DEBITO: 1.5%
- TAXA_PIX: 0.0%
- TAXA_IFOOD: 15.0%
- TAXA_UBER_EATS: 20.0%
```

**Exemplo Prático:**
- Pedido: R$ 100,00 pagos com cartão de crédito
- Taxa configurada: 2.5%
- Taxa calculada: R$ 2,50
- Registro automático:

```json
{
  "type": "EXPENSE",
  "value": 2.50,
  "category": "Custos Variáveis",
  "subcategory": "Taxas de Pagamento",
  "description": "Taxa credit - Pedido #123",
  "movement_date": "2024-01-15T14:30:00",
  "payment_status": "Paid",
  "payment_method": "credit",
  "related_entity_type": "order",
  "related_entity_id": 123
}
```

**Resultado Final:**
- ✅ Receita: R$ 100,00
- ✅ CMV: R$ 15,00
- ✅ Taxa: R$ 2,50
- ✅ **Lucro Bruto**: R$ 85,00 (Receita - CMV)
- ✅ **Lucro Líquido**: R$ 82,50 (Receita - CMV - Taxa)

---

### **3. FLUXO 2: Compra de Ingredientes (Nota Fiscal de Compra)**

#### **3.1. Quando Ocorre**

Quando uma **nota fiscal de compra** é criada, o sistema **automaticamente**:

1. Dá entrada no estoque dos ingredientes
2. Registra despesa financeira (EXPENSE)

#### **3.2. Processo Detalhado**

**Passo 1: Criação da Nota Fiscal**

```json
POST /api/purchases/invoices
{
  "invoice_number": "NF-001/2024",
  "supplier_name": "Fornecedor ABC",
  "total_amount": 500.00,
  "purchase_date": "2024-01-10",
  "payment_status": "Pending",  // ou "Paid"
  "payment_method": "bank_transfer",
  "payment_date": null,  // Se Pending, pode ser null ou data futura
  "items": [
    {
      "ingredient_id": 1,
      "quantity": 10.0,
      "unit_price": 5.00
    },
    {
      "ingredient_id": 2,
      "quantity": 20.0,
      "unit_price": 20.00
    }
  ],
  "notes": "Compra mensal de ingredientes"
}
```

**Passo 2: Transação Atômica**

```python
# Em purchase_service.py - create_purchase_invoice()
1. Insere nota fiscal (PURCHASE_INVOICES)
2. Para cada item:
   - Insere item da nota (PURCHASE_INVOICE_ITEMS)
   - Atualiza estoque: STOCK_QUANTITY += quantity
3. Registra despesa financeira (EXPENSE)
4. COMMIT único ou ROLLBACK completo
```

**Passo 3: Registro da Despesa**

```json
{
  "type": "EXPENSE",
  "value": 500.00,
  "category": "Compras de Estoque",
  "subcategory": "Ingredientes",
  "description": "Compra - NF NF-001/2024 - Fornecedor ABC",
  "movement_date": null,  // Se Pending, null ou data futura
  "payment_status": "Pending",  // Ou "Paid" se já pago
  "payment_method": "bank_transfer",
  "sender_receiver": "Fornecedor ABC",
  "related_entity_type": "purchase_invoice",
  "related_entity_id": 1
}
```

**Cenário 1: Compra com Pagamento Pendente**
- Despesa registrada como `Pending`
- `movement_date` pode ser a data esperada de pagamento (ex: dia 15 do mês)
- Aparece em **Contas a Pagar**
- **Não afeta** o fluxo de caixa real até ser paga

**Cenário 2: Compra com Pagamento à Vista**
- Despesa registrada como `Paid`
- `movement_date` = data do pagamento
- **Afeta imediatamente** o fluxo de caixa real

---

### **4. FLUXO 3: Despesas Recorrentes (Regras de Recorrência)**

#### **4.1. Quando Ocorre**

O sistema permite criar **regras de recorrência** para despesas fixas (aluguel, salários, impostos) que são **geradas automaticamente** em períodos definidos.

#### **4.2. Tipos de Recorrência**

1. **MONTHLY** (Mensal): Gera no dia X de cada mês
2. **WEEKLY** (Semanal): Gera no dia X da semana (1=segunda, 7=domingo)
3. **YEARLY** (Anual): Gera no dia X do ano (1-365)

#### **4.3. Processo Detalhado**

**Passo 1: Criação da Regra**

```json
POST /api/recurrence/rules
{
  "name": "Aluguel",
  "description": "Aluguel mensal do ponto",
  "type": "EXPENSE",
  "category": "Custos Fixos",
  "subcategory": "Aluguel",
  "value": 3000.00,
  "recurrence_type": "MONTHLY",
  "recurrence_day": 5,  // Dia 5 de cada mês
  "sender_receiver": "Imobiliária XYZ",
  "notes": "Vencimento dia 5"
}
```

**Passo 2: Geração Automática**

```python
# Em recurrence_service.py - generate_recurring_movements()
# Pode ser chamado manualmente ou via cron job

# Para cada regra ativa:
1. Verifica se já foi gerada para o período (evita duplicação)
2. Calcula data de pagamento baseada na recorrência
3. Cria movimentação financeira como Pending
4. Registra link com a regra (related_entity_type='recurrence_rule')
```

**Exemplo: Geração Mensal**

```json
// Movimentação gerada automaticamente em janeiro/2024
{
  "type": "EXPENSE",
  "value": 3000.00,
  "category": "Custos Fixos",
  "subcategory": "Aluguel",
  "description": "Aluguel - MONTHLY",
  "movement_date": "2024-01-05",  // Data esperada (dia 5)
  "payment_status": "Pending",  // Inicialmente pendente
  "sender_receiver": "Imobiliária XYZ",
  "related_entity_type": "recurrence_rule",
  "related_entity_id": 1
}
```

**Passo 3: Pagamento Manual**

Quando o aluguel é pago, o usuário atualiza o status:

```json
PATCH /api/financial-movements/movements/456/payment-status
{
  "payment_status": "Paid",
  "movement_date": "2024-01-05T10:00:00"  // Data real do pagamento
}
```

**Proteção contra Duplicação:**
- O sistema verifica se já existe movimentação para a mesma regra no mesmo período
- Se já existe, **não gera novamente**

---

### **5. FLUXO 4: Projeção de Caixa**

#### **5.1. Conceito**

O sistema diferencia:
- **Fluxo de Caixa Real**: Apenas movimentações `Paid` com `movement_date` preenchido
- **Projeção de Caixa**: Inclui movimentações `Pending` usando `movement_date` esperado (ou `CREATED_AT` como fallback)

#### **5.2. Cálculo do Resumo**

```python
# Em financial_movement_service.py - get_cash_flow_summary()

# 1. Fluxo de Caixa Real (apenas Paid)
total_revenue = SUM(REVENUE WHERE payment_status='Paid')
total_expense = SUM(EXPENSE WHERE payment_status='Paid')
total_cmv = SUM(CMV WHERE payment_status='Paid')
total_tax = SUM(TAX WHERE payment_status='Paid')

gross_profit = total_revenue - total_cmv
net_profit = total_revenue - total_cmv - total_expense - total_tax
cash_flow = total_revenue - total_expense - total_cmv - total_tax

# 2. Projeção (incluindo Pending)
if include_pending:
    # Usa MOVEMENT_DATE esperado se disponível, senão CREATED_AT
    pending_amount = SUM(EXPENSE + TAX WHERE payment_status='Pending')
    # Considera a data esperada para projeção
```

**Exemplo Prático:**

**Situação em 15/01/2024:**
- Receitas pagas: R$ 10.000,00
- Despesas pagas: R$ 5.000,00
- CMV: R$ 3.000,00
- **Fluxo de Caixa Real**: R$ 2.000,00

**Pendências:**
- Aluguel (vencimento 20/01): R$ 3.000,00 (Pending)
- Salários (vencimento 25/01): R$ 5.000,00 (Pending)
- **Projeção de Caixa (fim do mês)**: R$ -6.000,00

---

### **6. FLUXO 5: Conciliação Bancária**

#### **6.1. Conceito**

O sistema permite marcar movimentações como **reconciliadas** após conferência com extratos bancários ou gateways de pagamento.

#### **6.2. Processo**

**Passo 1: Atualizar Informações de Gateway**

```json
PATCH /api/financial-movements/movements/123/gateway-info
{
  "payment_gateway_id": "pagarme",
  "transaction_id": "tx_abc123xyz",
  "bank_account": "Banco do Brasil - 12345-6"
}
```

**Passo 2: Marcar como Reconciliada**

```json
PATCH /api/financial-movements/movements/123/reconcile
{
  "reconciled": true
}
```

**Passo 3: Relatório de Conciliação**

```json
GET /api/financial-movements/reconciliation-report?start_date=01/01/2024&end_date=31/01/2024

{
  "total_movements": 150,
  "reconciled_count": 120,
  "unreconciled_count": 30,
  "reconciled_amount": 50000.00,
  "unreconciled_amount": 15000.00,
  "movements": [...]
}
```

---

## 📈 **MÉTRICAS E INDICADORES**

### **7. Indicadores Calculados**

#### **7.1. Lucro Bruto (Gross Profit)**
```
Lucro Bruto = Receita Total - CMV Total
```
**Interpretação:** Margem antes de despesas operacionais e impostos.

#### **7.2. Lucro Líquido (Net Profit)**
```
Lucro Líquido = Receita Total - CMV Total - Despesas Totais - Impostos Totais
```
**Interpretação:** Resultado final após todos os custos.

#### **7.3. Fluxo de Caixa**
```
Fluxo de Caixa = Receitas Pagas - Despesas Pagas - CMV - Impostos
```
**Interpretação:** Dinheiro que realmente entrou/saiu do caixa.

#### **7.4. Margem Bruta (%)**
```
Margem Bruta = (Lucro Bruto / Receita Total) × 100
```
**Interpretação:** Percentual de lucro sobre as vendas.

---

## 🔍 **CASOS DE USO PRÁTICOS**

### **8. Caso de Uso 1: Análise de Rentabilidade de um Pedido**

**Cenário:** Pedido #123 de R$ 50,00

**Dados Registrados:**
- Receita: R$ 50,00
- CMV: R$ 15,00
- Taxa de cartão (2.5%): R$ 1,25

**Análise:**
- Lucro Bruto: R$ 35,00 (70% de margem)
- Lucro Líquido: R$ 33,75 (67,5% de margem)

**Rastreabilidade:**
- Todas as movimentações têm `related_entity_id=123`
- É possível rastrear exatamente qual pedido gerou cada valor

---

### **9. Caso de Uso 2: Gestão de Contas a Pagar**

**Cenário:** Fim do mês, verificar o que precisa ser pago

**Consulta:**
```json
GET /api/financial-movements/pending?type=EXPENSE
```

**Resultado:**
```json
[
  {
    "id": 456,
    "type": "EXPENSE",
    "value": 3000.00,
    "description": "Aluguel - MONTHLY",
    "movement_date": "2024-01-05",  // Data esperada
    "payment_status": "Pending",
    "sender_receiver": "Imobiliária XYZ"
  },
  {
    "id": 457,
    "type": "EXPENSE",
    "value": 5000.00,
    "description": "Salários - MONTHLY",
    "movement_date": "2024-01-25",
    "payment_status": "Pending",
    "sender_receiver": "Funcionários"
  }
]
```

**Total a Pagar:** R$ 8.000,00

---

### **10. Caso de Uso 3: Relatório Mensal Completo**

**Consulta:**
```json
GET /api/financial-movements/summary?period=this_month&include_pending=true
```

**Resultado:**
```json
{
  "total_revenue": 50000.00,
  "total_expense": 20000.00,
  "total_cmv": 15000.00,
  "total_tax": 500.00,
  "gross_profit": 35000.00,
  "net_profit": 14500.00,
  "cash_flow": 14500.00,
  "pending_amount": 8000.00,  // Se include_pending=true
  "period": "this_month"
}
```

**Análise:**
- Margem Bruta: 70% (R$ 35.000 / R$ 50.000)
- Margem Líquida: 29% (R$ 14.500 / R$ 50.000)
- Projeção de Caixa (com pendências): R$ 6.500,00

---

## 🛡️ **GARANTIAS DE CONSISTÊNCIA**

### **11. Transações Atômicas**

**Princípio:** Operações relacionadas são executadas em uma única transação de banco de dados.

**Exemplos:**

1. **Finalização de Pedido:**
   - ✅ Status atualizado + Estoque baixado + Receita registrada + CMV registrado + Taxa registrada
   - ❌ Se qualquer passo falhar, **tudo é revertido** (ROLLBACK)

2. **Compra de Ingredientes:**
   - ✅ Nota fiscal criada + Estoque atualizado + Despesa registrada
   - ❌ Se qualquer passo falhar, **tudo é revertido**

**Benefício:** Elimina inconsistências entre estoque físico e registros financeiros.

---

### **12. Rastreabilidade Completa**

**Cada movimentação financeira pode ser rastreada até sua origem:**

- **Pedidos:** `related_entity_type='order'`, `related_entity_id=123`
- **Compras:** `related_entity_type='purchase_invoice'`, `related_entity_id=1`
- **Recorrências:** `related_entity_type='recurrence_rule'`, `related_entity_id=5`

**Benefício:** Facilita auditoria e correção de erros.

---

## 🎯 **REQUISITOS ATENDIDOS**

### **13. Checklist de Funcionalidades**

| Requisito | Status | Implementação |
|-----------|--------|---------------|
| Registro automático de receitas | ✅ | `register_order_revenue_and_cmv()` |
| Cálculo automático de CMV | ✅ | Cálculo baseado em produtos/ingredientes |
| Registro automático de taxas | ✅ | Baseado em `APP_SETTINGS` |
| Compra automática de despesas | ✅ | `create_purchase_invoice()` |
| Gestão de contas a pagar | ✅ | Filtro por `payment_status='Pending'` |
| Projeção de caixa | ✅ | `get_cash_flow_summary()` com `include_pending` |
| Despesas recorrentes | ✅ | Sistema de regras de recorrência |
| Conciliação bancária | ✅ | Campos de gateway e status de conciliação |
| Transações atômicas | ✅ | Uso de cursor compartilhado |
| Rastreabilidade | ✅ | Campos `related_entity_*` |
| Relatórios financeiros | ✅ | Endpoints de resumo e listagem |
| Filtros avançados | ✅ | Por data, tipo, categoria, status, etc. |

---

## 📊 **EXEMPLO DE FLUXO COMPLETO: UM DIA NO RESTAURANTE**

### **14. Cenário: 15 de Janeiro de 2024**

**Manhã (09:00):**
- Compra de ingredientes: R$ 500,00 (Pendente, vencimento dia 20)
- ✅ Despesa registrada como `Pending`
- ✅ Estoque atualizado

**Almoço (12:00-14:00):**
- Pedido #100: R$ 45,00 (Cartão de Crédito)
- Pedido #101: R$ 60,00 (PIX)
- Pedido #102: R$ 80,00 (iFood)

**Ao finalizar cada pedido:**
- ✅ Receita registrada
- ✅ CMV calculado e registrado
- ✅ Taxa de pagamento registrada (se aplicável)
- ✅ Estoque baixado

**Tarde (15:00):**
- Geração de despesas recorrentes do mês
- ✅ Aluguel: R$ 3.000,00 (Pendente, vencimento dia 5)
- ✅ Salários: R$ 5.000,00 (Pendente, vencimento dia 25)

**Fim do Dia:**
- **Resumo Real (Paid):**
  - Receitas: R$ 185,00
  - CMV: R$ 55,00
  - Taxas: R$ 2,00
  - **Fluxo de Caixa Real**: R$ 128,00

- **Projeção (com Pendências):**
  - Pendências: R$ 8.500,00
  - **Projeção de Caixa**: R$ -8.372,00

---

## 🔧 **CONFIGURAÇÕES NECESSÁRIAS**

### **15. Configuração de Taxas de Pagamento**

As taxas devem ser configuradas em `APP_SETTINGS`:

```sql
UPDATE APP_SETTINGS SET
  TAXA_CARTAO_CREDITO = 2.5,
  TAXA_CARTAO_DEBITO = 1.5,
  TAXA_PIX = 0.0,
  TAXA_IFOOD = 15.0,
  TAXA_UBER_EATS = 20.0
WHERE ID = (SELECT MAX(ID) FROM APP_SETTINGS);
```

---

## 🚀 **PRÓXIMOS PASSOS SUGERIDOS**

1. **Dashboard Visual:** Criar interface gráfica para visualização dos dados
2. **Alertas:** Notificações quando contas a pagar estão próximas do vencimento
3. **Exportação:** Exportar relatórios para Excel/PDF
4. **Integração Bancária:** Importar extratos automaticamente
5. **Análise Preditiva:** Previsão de fluxo de caixa baseada em histórico

---

## 📝 **CONCLUSÃO**

O sistema de fluxo de caixa do Royal Burger é uma **solução robusta e completa** que:

✅ **Automatiza** o registro de todas as movimentações financeiras  
✅ **Garante consistência** através de transações atômicas  
✅ **Fornece rastreabilidade** completa de cada valor  
✅ **Diferencia** compromissos de movimentos reais de caixa  
✅ **Calcula métricas** importantes (lucro bruto, líquido, margens)  
✅ **Suporta projeções** de caixa com base em pendências  
✅ **Facilita conciliação** bancária com gateways  

O sistema está **pronto para uso em produção** e pode ser expandido conforme necessário.

