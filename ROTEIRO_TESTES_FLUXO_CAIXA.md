# 🧪 ROTEIRO DE TESTES — Sistema de Fluxo de Caixa

## 📋 **VISÃO GERAL**

Este roteiro consolida **todos os testes pendentes** dos sistemas de fluxo de caixa, organizados por categoria e prioridade. Os testes cobrem backend (API), integração, frontend e testes end-to-end.

### **Objetivos**
- Validar funcionalidades implementadas
- Garantir consistência transacional
- Verificar integrações entre módulos
- Validar interface e experiência do usuário
- Assegurar segurança e performance

---

## 🎯 **ESTRUTURA DE TESTES**

### **Categorias**
1. **Testes Unitários** - Funções e serviços isolados
2. **Testes de Integração** - Interação entre módulos
3. **Testes de API** - Endpoints e contratos
4. **Testes Funcionais** - Fluxos completos de negócio
5. **Testes de Frontend** - Interface e interações
6. **Testes End-to-End** - Cenários completos do usuário
7. **Testes de Performance** - Carga e escalabilidade
8. **Testes de Segurança** - Autenticação e autorização

---

## 🔴 **PARTE 1: TESTES DE BACKEND (API)**

### **1.1. Testes de Movimentações Financeiras**

#### **Teste 1.1.1: Criar Movimentação Financeira**
**Prioridade:** 🔴 ALTA  
**Arquivo:** `tests/test_financial_movements.py`

```python
def test_create_financial_movement_revenue():
    """Testa criação de movimentação de receita"""
    # Dados de teste
    movement_data = {
        'type': 'REVENUE',
        'value': 100.00,
        'category': 'Vendas',
        'subcategory': 'Cartão de Crédito',
        'description': 'Venda teste',
        'movement_date': '2024-01-15T10:00:00',
        'payment_status': 'Paid',
        'payment_method': 'credit'
    }
    
    # Executar
    success, error_code, result = financial_movement_service.create_financial_movement(
        movement_data, user_id=1
    )
    
    # Verificar
    assert success == True
    assert result['type'] == 'REVENUE'
    assert result['value'] == 100.00
    assert result['payment_status'] == 'Paid'
```

**Checklist:**
- [ ] Testar criação de receita (REVENUE)
- [ ] Testar criação de despesa (EXPENSE)
- [ ] Testar criação de CMV
- [ ] Testar criação de imposto (TAX)
- [ ] Testar validação de campos obrigatórios
- [ ] Testar validação de tipo inválido
- [ ] Testar validação de valor <= 0
- [ ] Testar validação de status inválido
- [ ] Testar criação com `movement_date` para Pending
- [ ] Testar criação sem `movement_date` para Paid (deve usar data atual)
- [ ] Testar criação com campos de gateway (Fase 6)

#### **Teste 1.1.2: Listar Movimentações com Filtros**
**Prioridade:** 🔴 ALTA

```python
def test_get_financial_movements_with_filters():
    """Testa listagem de movimentações com filtros"""
    # Criar movimentações de teste
    # ...
    
    # Testar filtros
    filters = {
        'start_date': '2024-01-01',
        'end_date': '2024-01-31',
        'type': 'REVENUE',
        'payment_status': 'Paid'
    }
    
    movements = financial_movement_service.get_financial_movements(filters)
    
    # Verificar
    assert len(movements) > 0
    assert all(m['type'] == 'REVENUE' for m in movements)
    assert all(m['payment_status'] == 'Paid' for m in movements)
```

**Checklist:**
- [ ] Testar filtro por data de início
- [ ] Testar filtro por data de fim
- [ ] Testar filtro por tipo
- [ ] Testar filtro por categoria
- [ ] Testar filtro por status de pagamento
- [ ] Testar filtro por entidade relacionada
- [ ] Testar filtro por gateway (Fase 6)
- [ ] Testar filtro por reconciliado (Fase 6)
- [ ] Testar combinação de múltiplos filtros
- [ ] Testar ordenação (por data, por valor)

#### **Teste 1.1.3: Atualizar Status de Pagamento**
**Prioridade:** 🔴 ALTA

```python
def test_update_payment_status():
    """Testa atualização de status de pagamento"""
    # Criar movimentação pendente
    # ...
    
    # Atualizar para Paid
    success, error_code, result = financial_movement_service.update_payment_status(
        movement_id=1,
        payment_status='Paid',
        movement_date='2024-01-15T10:00:00'
    )
    
    # Verificar
    assert success == True
    assert result['payment_status'] == 'Paid'
    assert result['movement_date'] is not None
```

**Checklist:**
- [ ] Testar atualização de Pending → Paid
- [ ] Testar atualização de Paid → Pending
- [ ] Testar validação de status inválido
- [ ] Testar obrigatoriedade de `movement_date` ao marcar como Paid
- [ ] Testar limpeza de `movement_date` ao marcar como Pending
- [ ] Testar atualização de movimentação inexistente

#### **Teste 1.1.4: Resumo do Fluxo de Caixa**
**Prioridade:** 🟡 MÉDIA

```python
def test_get_cash_flow_summary():
    """Testa cálculo de resumo do fluxo de caixa"""
    # Criar movimentações de teste
    # ...
    
    # Testar resumo do mês atual
    summary = financial_movement_service.get_cash_flow_summary(
        period='this_month',
        include_pending=False
    )
    
    # Verificar
    assert 'total_revenue' in summary
    assert 'total_expense' in summary
    assert 'total_cmv' in summary
    assert 'gross_profit' in summary
    assert 'net_profit' in summary
    assert 'cash_flow' in summary
```

**Checklist:**
- [ ] Testar resumo do mês atual
- [ ] Testar resumo do mês anterior
- [ ] Testar resumo dos últimos 30 dias
- [ ] Testar inclusão de pendentes
- [ ] Testar cálculo de lucro bruto (receita - CMV)
- [ ] Testar cálculo de lucro líquido (receita - CMV - despesas - impostos)
- [ ] Testar uso de `MOVEMENT_DATE` esperado para pendentes (Fase 4)
- [ ] Testar fallback para `CREATED_AT` quando `MOVEMENT_DATE` é NULL

---

### **1.2. Testes de Registro Automático de Receita/CMV**

#### **Teste 1.2.1: Registro Automático ao Finalizar Pedido**
**Prioridade:** 🔴 ALTA  
**Arquivo:** `tests/test_order_financial_integration.py`

```python
def test_register_order_revenue_and_cmv():
    """Testa registro automático de receita e CMV"""
    # Criar pedido de teste
    order_id = create_test_order()
    
    # Finalizar pedido
    success = order_service.update_order_status(
        order_id=order_id,
        new_status='delivered'
    )
    
    # Verificar movimentações criadas
    movements = financial_movement_service.get_financial_movements({
        'related_entity_type': 'order',
        'related_entity_id': order_id
    })
    
    # Verificar
    assert success == True
    revenue = [m for m in movements if m['type'] == 'REVENUE']
    cmv = [m for m in movements if m['type'] == 'CMV']
    assert len(revenue) == 1
    assert len(cmv) == 1
    assert revenue[0]['payment_status'] == 'Paid'
    assert cmv[0]['payment_status'] == 'Paid'
```

**Checklist:**
- [ ] Testar: pedido finalizado → verificar status `delivered` E CMV registrado
- [ ] Testar: erro no registro financeiro → verificar rollback completo (status não atualizado para `delivered`)
- [ ] Testar: pedido com múltiplos itens → verificar CMV calculado corretamente
- [ ] Testar: pedido sem custo de ingredientes → verificar que CMV não é registrado (mas receita sim)
- [ ] Testar: pedido com `COST_PRICE` do produto → usar custo do produto
- [ ] Testar: pedido sem `COST_PRICE` → calcular pela soma dos ingredientes
- [ ] Testar: transação atômica (status + estoque + financeiro)

#### **Teste 1.2.2: Registro de Taxas de Pagamento**
**Prioridade:** 🟡 MÉDIA

```python
def test_register_payment_fee_credit_card():
    """Testa registro automático de taxa de cartão de crédito"""
    # Configurar taxa em APP_SETTINGS
    # TAXA_CARTAO_CREDITO = 2.5
    
    # Criar pedido com cartão de crédito
    order_id = create_test_order(payment_method='credit', total=100.00)
    
    # Finalizar pedido
    order_service.update_order_status(order_id, 'delivered')
    
    # Verificar movimentações
    movements = financial_movement_service.get_financial_movements({
        'related_entity_type': 'order',
        'related_entity_id': order_id
    })
    
    # Verificar
    fee = [m for m in movements if m['subcategory'] == 'Taxas de Pagamento']
    assert len(fee) == 1
    assert fee[0]['value'] == 2.50  # 2.5% de 100.00
    assert fee[0]['type'] == 'EXPENSE'
```

**Checklist:**
- [ ] Testar: pedido com cartão de crédito → verificar receita E despesa de taxa
- [ ] Testar: pedido com cartão de débito → verificar receita E despesa de taxa
- [ ] Testar: pedido com PIX → verificar receita SEM despesa de taxa (se taxa = 0)
- [ ] Testar: pedido com iFood → verificar receita E despesa de comissão
- [ ] Testar: pedido com Uber Eats → verificar receita E despesa de comissão
- [ ] Testar: pedido com dinheiro → verificar receita SEM despesa de taxa
- [ ] Verificar: taxa registrada na mesma transação (se falhar, rollback completo)
- [ ] Testar: cálculo correto da taxa (percentual do valor total)
- [ ] Testar: taxa = 0 não cria despesa

---

### **1.3. Testes de Compras e Estoque**

#### **Teste 1.3.1: Criar Nota Fiscal de Compra**
**Prioridade:** 🔴 ALTA  
**Arquivo:** `tests/test_purchases.py`

```python
def test_create_purchase_invoice():
    """Testa criação de nota fiscal de compra"""
    invoice_data = {
        'invoice_number': 'NF-001',
        'supplier_name': 'Fornecedor Teste',
        'total_amount': 500.00,
        'purchase_date': '2024-01-15T10:00:00',
        'payment_status': 'Paid',
        'payment_method': 'pix',
        'items': [
            {
                'ingredient_id': 1,
                'quantity': 10.0,
                'unit_price': 5.00
            }
        ]
    }
    
    # Executar
    success, error_code, result = purchase_service.create_purchase_invoice(
        invoice_data, user_id=1
    )
    
    # Verificar nota fiscal
    assert success == True
    assert result['invoice_id'] is not None
    
    # Verificar estoque atualizado
    ingredient = get_ingredient(1)
    assert ingredient['current_stock'] == previous_stock + 10.0
    
    # Verificar despesa criada
    expense = financial_movement_service.get_financial_movements({
        'related_entity_type': 'purchase_invoice',
        'related_entity_id': result['invoice_id']
    })
    assert len(expense) == 1
    assert expense[0]['type'] == 'EXPENSE'
    assert expense[0]['value'] == 500.00
```

**Checklist:**
- [ ] Testar: criar compra → verificar estoque atualizado E despesa registrada
- [ ] Testar: compra com status `Pending` → verificar despesa pendente
- [ ] Testar: compra com status `Paid` → verificar despesa paga com `movement_date`
- [ ] Testar: erro na criação → verificar rollback completo (sem estoque, sem despesa)
- [ ] Testar: compra com múltiplos itens → verificar todos os itens processados
- [ ] Testar: validação de ingrediente inexistente
- [ ] Testar: validação de quantidade <= 0
- [ ] Testar: validação de preço unitário <= 0
- [ ] Testar: transação atômica (nota + itens + estoque + despesa)

#### **Teste 1.3.2: Listar Notas Fiscais**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar listagem sem filtros
- [ ] Testar filtro por data de início
- [ ] Testar filtro por data de fim
- [ ] Testar filtro por fornecedor
- [ ] Testar filtro por status de pagamento
- [ ] Testar ordenação por data

---

### **1.4. Testes de Impostos Recorrentes**

#### **Teste 1.4.1: Criar Imposto Recorrente**
**Prioridade:** 🟡 MÉDIA  
**Arquivo:** `tests/test_recurring_taxes.py`

```python
def test_create_recurring_tax():
    """Testa criação de imposto recorrente"""
    tax_data = {
        'name': 'ICMS',
        'description': 'Imposto sobre Circulação de Mercadorias',
        'category': 'Tributos',
        'subcategory': 'ICMS',
        'value': 500.00,
        'payment_day': 10,
        'sender_receiver': 'Receita Federal'
    }
    
    success, error_code, result = recurring_tax_service.create_recurring_tax(
        tax_data, user_id=1
    )
    
    assert success == True
    assert result['payment_day'] == 10
    assert result['is_active'] == True
```

**Checklist:**
- [ ] Testar criação de imposto recorrente
- [ ] Testar validação de dia de pagamento (1-31)
- [ ] Testar validação de valor > 0
- [ ] Testar listagem de impostos ativos
- [ ] Testar listagem incluindo inativos
- [ ] Testar atualização de imposto
- [ ] Testar desativação de imposto (soft delete)

#### **Teste 1.4.2: Gerar Impostos Mensais**
**Prioridade:** 🟡 MÉDIA

```python
def test_generate_monthly_taxes():
    """Testa geração de impostos mensais"""
    # Criar imposto recorrente
    # ...
    
    # Gerar para mês atual
    success, count, errors = recurring_tax_service.generate_monthly_taxes(
        year=2024, month=1
    )
    
    # Verificar
    assert success == True
    assert count > 0
    
    # Verificar movimentação criada
    movements = financial_movement_service.get_financial_movements({
        'related_entity_type': 'recurring_tax',
        'type': 'TAX'
    })
    assert len(movements) > 0
```

**Checklist:**
- [ ] Testar geração de impostos mensais
- [ ] Testar prevenção de duplicação (não gerar duas vezes no mesmo mês)
- [ ] Testar geração apenas de impostos ativos
- [ ] Testar criação de movimentação com status `Pending`
- [ ] Testar uso de data esperada (dia do mês especificado)

---

### **1.5. Testes de Regras de Recorrência**

#### **Teste 1.5.1: Criar Regra de Recorrência**
**Prioridade:** 🟢 BAIXA  
**Arquivo:** `tests/test_recurrence_rules.py`

```python
def test_create_recurrence_rule_monthly():
    """Testa criação de regra de recorrência mensal"""
    rule_data = {
        'name': 'Aluguel',
        'type': 'EXPENSE',
        'category': 'Custos Fixos',
        'value': 2000.00,
        'recurrence_type': 'MONTHLY',
        'recurrence_day': 5
    }
    
    success, error_code, result = recurrence_service.create_recurrence_rule(
        rule_data, user_id=1
    )
    
    assert success == True
    assert result['recurrence_type'] == 'MONTHLY'
    assert result['recurrence_day'] == 5
```

**Checklist:**
- [ ] Testar: criar regra mensal → verificar criação
- [ ] Testar: criar regra semanal → verificar criação
- [ ] Testar: criar regra anual → verificar criação
- [ ] Testar validação de tipo de recorrência
- [ ] Testar validação de dia (1-31 para mensal, 1-7 para semanal, 1-365 para anual)
- [ ] Testar atualização de regra
- [ ] Testar desativação de regra (soft delete)

#### **Teste 1.5.2: Gerar Movimentações Recorrentes**
**Prioridade:** 🟢 BAIXA

```python
def test_generate_recurring_movements_monthly():
    """Testa geração de movimentações mensais"""
    # Criar regra mensal
    # ...
    
    # Gerar para mês atual
    success, count, errors = recurrence_service.generate_recurring_movements(
        year=2024, month=1
    )
    
    # Verificar
    assert success == True
    assert count > 0
    
    # Verificar movimentação criada
    movements = financial_movement_service.get_financial_movements({
        'related_entity_type': 'recurrence_rule'
    })
    assert len(movements) > 0
```

**Checklist:**
- [ ] Testar: criar regra mensal → gerar movimentações → verificar criação
- [ ] Testar: criar regra semanal → gerar movimentações → verificar criação
- [ ] Testar: criar regra anual → gerar movimentações → verificar criação
- [ ] Testar: gerar novamente no mesmo período → verificar que não duplica
- [ ] Testar: desativar regra → verificar que não gera mais movimentações
- [ ] Testar cálculo correto de data para recorrência semanal
- [ ] Testar cálculo correto de data para recorrência anual
- [ ] Testar uso de data esperada (Fase 4)

---

### **1.6. Testes de Conciliação Bancária (Fase 6)**

#### **Teste 1.6.1: Marcar Movimentação como Reconciliada**
**Prioridade:** 🟢 BAIXA  
**Arquivo:** `tests/test_reconciliation.py`

```python
def test_reconcile_financial_movement():
    """Testa marcação de movimentação como reconciliada"""
    # Criar movimentação paga
    # ...
    
    # Marcar como reconciliada
    success, error_code, result = financial_movement_service.reconcile_financial_movement(
        movement_id=1,
        reconciled=True,
        updated_by_user_id=1
    )
    
    # Verificar
    assert success == True
    assert result['reconciled'] == True
    assert result['reconciled_at'] is not None
```

**Checklist:**
- [ ] Testar: criar movimentação com gateway info → verificar campos salvos
- [ ] Testar: marcar movimentação como reconciliada → verificar `reconciled=true` e `reconciled_at`
- [ ] Testar: desmarcar como reconciliada → verificar `reconciled=false` e `reconciled_at=None`
- [ ] Testar: atualizar gateway info → verificar campos atualizados
- [ ] Testar: relatório de conciliação → verificar estatísticas corretas
- [ ] Testar: filtrar por `reconciled=false` → verificar apenas não reconciliadas
- [ ] Testar: filtrar por `payment_gateway_id` → verificar apenas do gateway
- [ ] Testar: filtrar por `transaction_id` → verificar transação específica

#### **Teste 1.6.2: Relatório de Conciliação**
**Prioridade:** 🟢 BAIXA

```python
def test_get_reconciliation_report():
    """Testa geração de relatório de conciliação"""
    # Criar movimentações de teste (reconciliadas e não reconciliadas)
    # ...
    
    # Gerar relatório
    report = financial_movement_service.get_reconciliation_report(
        start_date='2024-01-01',
        end_date='2024-01-31'
    )
    
    # Verificar
    assert 'total_movements' in report
    assert 'reconciled_count' in report
    assert 'unreconciled_count' in report
    assert 'reconciled_amount' in report
    assert 'unreconciled_amount' in report
    assert 'movements' in report
    assert report['total_movements'] == report['reconciled_count'] + report['unreconciled_count']
```

**Checklist:**
- [ ] Testar relatório sem filtros
- [ ] Testar relatório com filtro de data
- [ ] Testar relatório com filtro de reconciliado
- [ ] Testar relatório com filtro de gateway
- [ ] Testar estatísticas corretas (contagem e valores)
- [ ] Testar que apenas movimentações `Paid` aparecem no relatório

---

## 🔗 **PARTE 2: TESTES DE INTEGRAÇÃO**

### **2.1. Testes de Transações Atômicas**

#### **Teste 2.1.1: Transação Única - Pedido + Estoque + Financeiro**
**Prioridade:** 🔴 ALTA  
**Arquivo:** `tests/test_atomic_transactions.py`

```python
def test_order_completion_atomic_transaction():
    """Testa que finalização de pedido é atômica"""
    # Criar pedido com itens
    order_id = create_test_order_with_items()
    
    # Simular erro no registro financeiro (mock)
    with patch('financial_movement_service.register_order_revenue_and_cmv') as mock:
        mock.return_value = (False, None, None, None, "Erro simulado")
        
        # Tentar finalizar pedido
        success = order_service.update_order_status(order_id, 'delivered')
        
        # Verificar rollback completo
        assert success == False
        
        # Verificar que status NÃO foi atualizado
        order = get_order(order_id)
        assert order['status'] != 'delivered'
        
        # Verificar que estoque NÃO foi baixado
        ingredient = get_ingredient(1)
        assert ingredient['current_stock'] == previous_stock
        
        # Verificar que NENHUMA movimentação foi criada
        movements = financial_movement_service.get_financial_movements({
            'related_entity_type': 'order',
            'related_entity_id': order_id
        })
        assert len(movements) == 0
```

**Checklist:**
- [ ] Testar: sucesso → tudo é commitado (status + estoque + financeiro)
- [ ] Testar: erro no financeiro → rollback completo (status não atualizado, estoque não baixado)
- [ ] Testar: erro no estoque → rollback completo (status não atualizado, financeiro não registrado)
- [ ] Testar: erro no status → rollback completo (nenhuma alteração)

#### **Teste 2.1.2: Transação Única - Compra + Estoque + Despesa**
**Prioridade:** 🔴 ALTA

```python
def test_purchase_invoice_atomic_transaction():
    """Testa que criação de compra é atômica"""
    invoice_data = {
        'invoice_number': 'NF-001',
        'supplier_name': 'Fornecedor',
        'total_amount': 500.00,
        'items': [{'ingredient_id': 1, 'quantity': 10.0, 'unit_price': 50.00}]
    }
    
    # Simular erro no registro de despesa
    with patch('financial_movement_service.create_financial_movement') as mock:
        mock.return_value = (False, "ERROR", "Erro simulado")
        
        # Tentar criar compra
        success, error_code, result = purchase_service.create_purchase_invoice(
            invoice_data, user_id=1
        )
        
        # Verificar rollback
        assert success == False
        
        # Verificar que estoque NÃO foi atualizado
        ingredient = get_ingredient(1)
        assert ingredient['current_stock'] == previous_stock
        
        # Verificar que nota fiscal NÃO foi criada
        invoices = purchase_service.get_purchase_invoices({'invoice_number': 'NF-001'})
        assert len(invoices) == 0
```

**Checklist:**
- [ ] Testar: sucesso → tudo é commitado (nota + itens + estoque + despesa)
- [ ] Testar: erro na despesa → rollback completo
- [ ] Testar: erro no estoque → rollback completo
- [ ] Testar: erro na nota → rollback completo

---

### **2.2. Testes de Integração entre Módulos**

#### **Teste 2.2.1: Integração Order → Financial → Stock**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar fluxo completo: criar pedido → finalizar → verificar movimentações financeiras criadas
- [ ] Testar que CMV usa dados corretos do estoque
- [ ] Testar que baixa de estoque usa mesmos dados do CMV
- [ ] Testar consistência entre quantidade vendida e quantidade baixada

#### **Teste 2.2.2: Integração Purchase → Financial → Stock**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar fluxo completo: criar compra → verificar estoque atualizado → verificar despesa criada
- [ ] Testar que valor da despesa = valor total da nota fiscal
- [ ] Testar que quantidade de estoque = soma das quantidades dos itens

---

## 🌐 **PARTE 3: TESTES DE API (ENDPOINTS)**

### **3.1. Testes de Endpoints de Movimentações**

#### **Teste 3.1.1: GET /api/financial-movements/movements**
**Prioridade:** 🔴 ALTA  
**Arquivo:** `tests/test_api_financial_movements.py`

```python
def test_get_movements_endpoint():
    """Testa endpoint de listagem de movimentações"""
    # Autenticar como admin
    token = get_admin_token()
    
    # Fazer requisição
    response = client.get(
        '/api/financial-movements/movements',
        headers={'Authorization': f'Bearer {token}'},
        query_string={'type': 'REVENUE', 'payment_status': 'Paid'}
    )
    
    # Verificar
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert all(m['type'] == 'REVENUE' for m in data)
    assert all(m['payment_status'] == 'Paid' for m in data)
```

**Checklist:**
- [ ] Testar autenticação (token válido)
- [ ] Testar autorização (admin/manager)
- [ ] Testar acesso negado (attendant/customer)
- [ ] Testar listagem sem filtros
- [ ] Testar filtros individuais
- [ ] Testar combinação de filtros
- [ ] Testar validação de formato de data
- [ ] Testar validação de tipo inválido
- [ ] Testar resposta vazia quando não há resultados

#### **Teste 3.1.2: POST /api/financial-movements/movements**
**Prioridade:** 🔴 ALTA

```python
def test_create_movement_endpoint():
    """Testa endpoint de criação de movimentação"""
    token = get_admin_token()
    
    movement_data = {
        'type': 'EXPENSE',
        'value': 100.00,
        'category': 'Custos Fixos',
        'description': 'Despesa teste'
    }
    
    response = client.post(
        '/api/financial-movements/movements',
        headers={'Authorization': f'Bearer {token}'},
        json=movement_data
    )
    
    assert response.status_code == 201
    data = response.get_json()
    assert data['type'] == 'EXPENSE'
    assert data['value'] == 100.00
```

**Checklist:**
- [ ] Testar criação com dados válidos
- [ ] Testar validação de campos obrigatórios
- [ ] Testar validação de tipo inválido
- [ ] Testar validação de valor <= 0
- [ ] Testar autenticação obrigatória
- [ ] Testar autorização (admin/manager)

#### **Teste 3.1.3: PATCH /api/financial-movements/movements/<id>/payment-status**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar atualização de status válido
- [ ] Testar validação de status inválido
- [ ] Testar movimentação inexistente (404)
- [ ] Testar autenticação e autorização

#### **Teste 3.1.4: GET /api/financial-movements/summary**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar resumo do mês atual
- [ ] Testar resumo do mês anterior
- [ ] Testar resumo dos últimos 30 dias
- [ ] Testar inclusão de pendentes
- [ ] Testar cálculo correto das métricas

#### **Teste 3.1.5: GET /api/financial-movements/pending**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar listagem de pendentes
- [ ] Testar filtro por tipo
- [ ] Testar ordenação por data esperada

#### **Teste 3.1.6: PATCH /api/financial-movements/movements/<id>/reconcile**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar marcação como reconciliada
- [ ] Testar desmarcação
- [ ] Testar movimentação inexistente

#### **Teste 3.1.7: PATCH /api/financial-movements/movements/<id>/gateway-info**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar atualização de gateway info
- [ ] Testar atualização parcial (apenas alguns campos)
- [ ] Testar validação de dados

#### **Teste 3.1.8: GET /api/financial-movements/reconciliation-report**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar relatório sem filtros
- [ ] Testar relatório com filtros
- [ ] Testar estatísticas corretas

---

### **3.2. Testes de Endpoints de Compras**

#### **Teste 3.2.1: POST /api/purchases/invoices**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar criação de nota fiscal válida
- [ ] Testar validação de campos obrigatórios
- [ ] Testar validação de itens
- [ ] Testar validação de ingrediente inexistente
- [ ] Testar autenticação e autorização

#### **Teste 3.2.2: GET /api/purchases/invoices**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar listagem sem filtros
- [ ] Testar filtros (data, fornecedor, status)
- [ ] Testar ordenação

#### **Teste 3.2.3: GET /api/purchases/invoices/<id>**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar busca por ID válido
- [ ] Testar busca por ID inexistente (404)
- [ ] Testar retorno com itens

---

### **3.3. Testes de Endpoints de Recorrência**

#### **Teste 3.3.1: GET /api/recurrence/rules**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar listagem de regras ativas
- [ ] Testar listagem incluindo inativas
- [ ] Testar autenticação e autorização

#### **Teste 3.3.2: POST /api/recurrence/rules**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar criação de regra mensal
- [ ] Testar criação de regra semanal
- [ ] Testar criação de regra anual
- [ ] Testar validação de dados

#### **Teste 3.3.3: POST /api/recurrence/generate**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar geração para mês atual
- [ ] Testar geração para mês específico
- [ ] Testar validação de ano/mês
- [ ] Testar resposta com contagem de gerados

---

## 🎨 **PARTE 4: TESTES DE FRONTEND**

### **4.1. Testes de API Services**

#### **Teste 4.1.1: financial-movements.js**
**Prioridade:** 🔴 ALTA  
**Arquivo:** `tests/frontend/test_financial_movements_api.js`

```javascript
describe('Financial Movements API', () => {
    test('getFinancialMovements - lista movimentações', async () => {
        const movements = await getFinancialMovements({
            type: 'REVENUE',
            payment_status: 'Paid'
        });
        
        expect(Array.isArray(movements)).toBe(true);
        expect(movements.every(m => m.type === 'REVENUE')).toBe(true);
    });
    
    test('createFinancialMovement - cria movimentação', async () => {
        const movementData = {
            type: 'EXPENSE',
            value: 100.00,
            category: 'Custos Fixos',
            description: 'Teste'
        };
        
        const result = await createFinancialMovement(movementData);
        
        expect(result.id).toBeDefined();
        expect(result.type).toBe('EXPENSE');
    });
});
```

**Checklist:**
- [ ] Testar `getFinancialMovements` com filtros
- [ ] Testar `createFinancialMovement`
- [ ] Testar `updatePaymentStatus`
- [ ] Testar `getCashFlowSummary`
- [ ] Testar `getPendingPayments`
- [ ] Testar `reconcileMovement`
- [ ] Testar `updateGatewayInfo`
- [ ] Testar `getReconciliationReport`
- [ ] Testar tratamento de erros
- [ ] Testar timeout de requisições

#### **Teste 4.1.2: purchases.js**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar `createPurchaseInvoice`
- [ ] Testar `getPurchaseInvoices`
- [ ] Testar `getPurchaseInvoiceById`
- [ ] Testar tratamento de erros

#### **Teste 4.1.3: recurrence.js**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar `getRecurrenceRules`
- [ ] Testar `createRecurrenceRule`
- [ ] Testar `updateRecurrenceRule`
- [ ] Testar `deleteRecurrenceRule`
- [ ] Testar `generateRecurringMovements`

---

### **4.2. Testes de Componentes UI**

#### **Teste 4.2.1: Dashboard Financeiro**
**Prioridade:** 🔴 ALTA  
**Arquivo:** `tests/frontend/test_dashboard_financeiro.js`

```javascript
describe('Financial Dashboard', () => {
    test('renderiza cards de resumo', () => {
        const dashboard = new FinancialDashboard('container');
        dashboard.render();
        
        const cards = document.querySelectorAll('.financial-summary-card');
        expect(cards.length).toBeGreaterThan(0);
    });
    
    test('carrega dados do resumo', async () => {
        const dashboard = new FinancialDashboard('container');
        await dashboard.loadData();
        
        const revenueCard = document.querySelector('.financial-summary-card.revenue');
        expect(revenueCard).toBeTruthy();
    });
});
```

**Checklist:**
- [ ] Testar renderização de cards de resumo
- [ ] Testar carregamento de dados
- [ ] Testar mudança de período
- [ ] Testar inclusão/exclusão de pendentes
- [ ] Testar formatação de valores monetários
- [ ] Testar cálculo de margem
- [ ] Testar estados de loading
- [ ] Testar tratamento de erros

#### **Teste 4.2.2: Lista de Movimentações**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar renderização da tabela
- [ ] Testar aplicação de filtros
- [ ] Testar paginação
- [ ] Testar ordenação
- [ ] Testar ação de marcar como pago
- [ ] Testar ação de editar
- [ ] Testar formatação de datas
- [ ] Testar formatação de valores
- [ ] Testar badges de tipo e status
- [ ] Testar estados vazios

#### **Teste 4.2.3: Formulário de Movimentação**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar renderização do formulário
- [ ] Testar validação de campos
- [ ] Testar submissão de formulário
- [ ] Testar edição de movimentação existente
- [ ] Testar seleção de tipo
- [ ] Testar campos condicionais
- [ ] Testar tratamento de erros de validação

#### **Teste 4.2.4: Gestão de Compras**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar listagem de compras
- [ ] Testar criação de nova compra
- [ ] Testar visualização de detalhes
- [ ] Testar adição/remoção de itens
- [ ] Testar cálculo de total
- [ ] Testar validação de formulário

#### **Teste 4.2.5: Gestão de Recorrências**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar listagem de regras
- [ ] Testar criação de regra
- [ ] Testar edição de regra
- [ ] Testar desativação de regra
- [ ] Testar geração de movimentações
- [ ] Testar formatação de tipo de recorrência

---

### **4.3. Testes de Integração Frontend**

#### **Teste 4.3.1: Integração Dashboard → API**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar carregamento de dados do dashboard
- [ ] Testar atualização ao mudar período
- [ ] Testar atualização ao incluir pendentes
- [ ] Testar sincronização de dados

#### **Teste 4.3.2: Integração Lista → Filtros → API**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar aplicação de filtros
- [ ] Testar atualização da lista ao aplicar filtros
- [ ] Testar limpeza de filtros
- [ ] Testar persistência de filtros na URL

#### **Teste 4.3.3: Integração Pedidos → Info Financeira**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar exibição de info financeira no detalhe do pedido
- [ ] Testar cálculo de lucro bruto/líquido
- [ ] Testar formatação de valores
- [ ] Testar exibição apenas para pedidos finalizados
- [ ] Testar estados de loading

---

### **4.4. Testes de UI/UX**

#### **Teste 4.4.1: Responsividade**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar layout mobile (< 768px)
- [ ] Testar layout tablet (768px - 1024px)
- [ ] Testar layout desktop (> 1024px)
- [ ] Testar tabelas com scroll horizontal em mobile
- [ ] Testar cards empilhados em mobile
- [ ] Testar navegação por tabs em mobile
- [ ] Testar formulários em mobile

#### **Teste 4.4.2: Acessibilidade**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar navegação por teclado
- [ ] Testar foco visível em elementos interativos
- [ ] Testar labels descritivos em inputs
- [ ] Testar ARIA labels em botões
- [ ] Testar contraste de cores (WCAG AA)
- [ ] Testar screen reader compatibility
- [ ] Testar alt text em imagens
- [ ] Testar estrutura semântica HTML

#### **Teste 4.4.3: Performance Frontend**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar tempo de carregamento inicial
- [ ] Testar lazy loading de gráficos
- [ ] Testar debounce em filtros
- [ ] Testar paginação de listas grandes
- [ ] Testar virtual scroll (se implementado)
- [ ] Testar cache de dados

---

## 🔄 **PARTE 5: TESTES END-TO-END**

### **5.1. Fluxos Completos de Negócio**

#### **Teste 5.1.1: Fluxo Completo de Venda**
**Prioridade:** 🔴 ALTA  
**Arquivo:** `tests/e2e/test_sale_flow.py`

```python
def test_complete_sale_flow():
    """Testa fluxo completo: pedido → finalização → movimentações financeiras"""
    # 1. Criar pedido
    order = create_order(items=[...], payment_method='credit')
    
    # 2. Finalizar pedido
    order_service.update_order_status(order['id'], 'delivered')
    
    # 3. Verificar movimentações criadas
    movements = get_financial_movements({'related_entity_type': 'order', 'related_entity_id': order['id']})
    
    # 4. Verificar receita
    revenue = [m for m in movements if m['type'] == 'REVENUE'][0]
    assert revenue['value'] == order['total_amount']
    
    # 5. Verificar CMV
    cmv = [m for m in movements if m['type'] == 'CMV'][0]
    assert cmv['value'] > 0
    
    # 6. Verificar taxa de pagamento
    fee = [m for m in movements if m['subcategory'] == 'Taxas de Pagamento'][0]
    assert fee['value'] > 0
    
    # 7. Verificar estoque baixado
    # ...
    
    # 8. Verificar resumo financeiro atualizado
    summary = get_cash_flow_summary('this_month')
    assert summary['total_revenue'] > 0
```

**Checklist:**
- [ ] Testar fluxo completo de venda com cartão de crédito
- [ ] Testar fluxo completo de venda com PIX
- [ ] Testar fluxo completo de venda com iFood
- [ ] Testar fluxo completo de venda com dinheiro
- [ ] Testar que todas as movimentações são criadas corretamente
- [ ] Testar que estoque é baixado corretamente
- [ ] Testar que resumo financeiro é atualizado

#### **Teste 5.1.2: Fluxo Completo de Compra**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar fluxo completo: criar compra → verificar estoque → verificar despesa
- [ ] Testar compra com status Pending
- [ ] Testar compra com status Paid
- [ ] Testar compra com múltiplos itens
- [ ] Testar que despesa é criada automaticamente
- [ ] Testar que estoque é atualizado corretamente

#### **Teste 5.1.3: Fluxo Completo de Recorrência**
**Prioridade:** 🟢 BAIXA

**Checklist:**
- [ ] Testar fluxo: criar regra → gerar movimentações → verificar criação
- [ ] Testar prevenção de duplicação
- [ ] Testar desativação de regra

---

## ⚡ **PARTE 6: TESTES DE PERFORMANCE**

### **6.1. Testes de Carga**

#### **Teste 6.1.1: Performance de Listagem**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar listagem com 100 movimentações
- [ ] Testar listagem com 1000 movimentações
- [ ] Testar listagem com 10000 movimentações
- [ ] Testar tempo de resposta < 2s para 1000 registros
- [ ] Testar uso de índices no banco

#### **Teste 6.1.2: Performance de Cálculos**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar cálculo de resumo com muitos registros
- [ ] Testar tempo de resposta do resumo < 1s
- [ ] Testar otimização de queries agregadas

---

## 🔒 **PARTE 7: TESTES DE SEGURANÇA**

### **7.1. Testes de Autenticação e Autorização**

#### **Teste 7.1.1: Autorização por Role**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar acesso admin a todas as rotas
- [ ] Testar acesso manager a todas as rotas
- [ ] Testar acesso negado para attendant
- [ ] Testar acesso negado para customer
- [ ] Testar acesso negado sem autenticação
- [ ] Testar token expirado
- [ ] Testar token inválido

#### **Teste 7.1.2: Validação de Dados**
**Prioridade:** 🔴 ALTA

**Checklist:**
- [ ] Testar SQL injection em filtros
- [ ] Testar XSS em campos de texto
- [ ] Testar validação de tipos de dados
- [ ] Testar validação de valores negativos
- [ ] Testar validação de datas inválidas

---

## 📊 **PARTE 8: TESTES DE REGRESSÃO**

### **8.1. Testes de Compatibilidade**

#### **Teste 8.1.1: Compatibilidade com Sistema Legado**
**Prioridade:** 🟡 MÉDIA

**Checklist:**
- [ ] Testar que FINANCIAL_TRANSACTIONS ainda funciona (se mantido)
- [ ] Testar migração de dados (se aplicável)
- [ ] Testar que relatórios antigos ainda funcionam

---

## ✅ **CHECKLIST CONSOLIDADO**

### **Backend (API)**
- [ ] **Testes Unitários de Serviços**
  - [ ] `financial_movement_service.py` - Todas as funções
  - [ ] `purchase_service.py` - Todas as funções
  - [ ] `recurring_tax_service.py` - Todas as funções
  - [ ] `recurrence_service.py` - Todas as funções
  - [ ] `order_service.py` - Integração financeira

- [ ] **Testes de Integração**
  - [ ] Transações atômicas (Pedido + Estoque + Financeiro)
  - [ ] Transações atômicas (Compra + Estoque + Despesa)
  - [ ] Integração entre módulos

- [ ] **Testes de API (Endpoints)**
  - [ ] GET /api/financial-movements/movements
  - [ ] POST /api/financial-movements/movements
  - [ ] PATCH /api/financial-movements/movements/<id>/payment-status
  - [ ] GET /api/financial-movements/summary
  - [ ] GET /api/financial-movements/pending
  - [ ] PATCH /api/financial-movements/movements/<id>/reconcile
  - [ ] PATCH /api/financial-movements/movements/<id>/gateway-info
  - [ ] GET /api/financial-movements/reconciliation-report
  - [ ] POST /api/purchases/invoices
  - [ ] GET /api/purchases/invoices
  - [ ] GET /api/purchases/invoices/<id>
  - [ ] GET /api/recurrence/rules
  - [ ] POST /api/recurrence/rules
  - [ ] PATCH /api/recurrence/rules/<id>
  - [ ] DELETE /api/recurrence/rules/<id>
  - [ ] POST /api/recurrence/generate

### **Frontend (Web)**
- [ ] **Testes de API Services**
  - [ ] `financial-movements.js`
  - [ ] `purchases.js`
  - [ ] `recurrence.js`

- [ ] **Testes de Componentes UI**
  - [ ] Dashboard Financeiro
  - [ ] Lista de Movimentações
  - [ ] Formulário de Movimentação
  - [ ] Gestão de Compras
  - [ ] Gestão de Recorrências
  - [ ] Conciliação Bancária

- [ ] **Testes de Integração Frontend**
  - [ ] Dashboard → API
  - [ ] Lista → Filtros → API
  - [ ] Pedidos → Info Financeira

- [ ] **Testes de UI/UX**
  - [ ] Responsividade (mobile, tablet, desktop)
  - [ ] Acessibilidade (WCAG AA)
  - [ ] Performance Frontend

### **End-to-End**
- [ ] Fluxo completo de venda
- [ ] Fluxo completo de compra
- [ ] Fluxo completo de recorrência

### **Performance**
- [ ] Testes de carga
- [ ] Testes de performance de queries

### **Segurança**
- [ ] Testes de autenticação/autorização
- [ ] Testes de validação de dados
- [ ] Testes de SQL injection
- [ ] Testes de XSS

---

## 📝 **ESTRUTURA DE ARQUIVOS DE TESTE**

### **Backend**
```
RoyalBurgerAPI/
├── tests/
│   ├── test_financial_movements.py
│   ├── test_order_financial_integration.py
│   ├── test_purchases.py
│   ├── test_recurring_taxes.py
│   ├── test_recurrence_rules.py
│   ├── test_reconciliation.py
│   ├── test_atomic_transactions.py
│   ├── test_api_financial_movements.py
│   ├── test_api_purchases.py
│   ├── test_api_recurrence.py
│   └── e2e/
│       └── test_sale_flow.py
```

### **Frontend**
```
RoyalBurgerWeb/
├── tests/
│   ├── frontend/
│   │   ├── test_financial_movements_api.js
│   │   ├── test_purchases_api.js
│   │   ├── test_recurrence_api.js
│   │   ├── test_dashboard_financeiro.js
│   │   ├── test_movements_list.js
│   │   └── test_integration.js
│   └── e2e/
│       └── test_fluxo_caixa_e2e.js
```

---

## 🎯 **PRIORIZAÇÃO DE EXECUÇÃO**

### **Fase 1: Testes Críticos (Prioridade ALTA)**
1. Testes de transações atômicas
2. Testes de registro automático de receita/CMV
3. Testes de criação de movimentações
4. Testes de endpoints principais
5. Testes de autorização

### **Fase 2: Testes Importantes (Prioridade MÉDIA)**
1. Testes de compras e estoque
2. Testes de taxas de pagamento
3. Testes de projeção de caixa
4. Testes de frontend principais
5. Testes de performance

### **Fase 3: Testes Complementares (Prioridade BAIXA)**
1. Testes de recorrências
2. Testes de conciliação bancária
3. Testes de UI/UX avançados
4. Testes de regressão

---

## 🛠️ **FERRAMENTAS RECOMENDADAS**

### **Backend (Python)**
- **pytest** - Framework de testes
- **pytest-cov** - Coverage
- **unittest.mock** - Mocks e stubs
- **faker** - Dados de teste
- **requests** - Testes de API

### **Frontend (JavaScript)**
- **Jest** - Framework de testes
- **@testing-library/dom** - Testes de DOM
- **jsdom** - Ambiente DOM para testes
- **MSW (Mock Service Worker)** - Mock de APIs

### **E2E**
- **Playwright** ou **Cypress** - Testes end-to-end
- **Selenium** - Alternativa

---

## 📋 **TEMPLATE DE TESTE**

### **Template para Teste Unitário (Python)**
```python
import pytest
from src.services import financial_movement_service

class TestFinancialMovementService:
    """Testes para financial_movement_service"""
    
    def test_create_financial_movement_success(self):
        """Testa criação bem-sucedida de movimentação"""
        # Arrange
        movement_data = {
            'type': 'REVENUE',
            'value': 100.00,
            'category': 'Vendas',
            'description': 'Teste'
        }
        
        # Act
        success, error_code, result = financial_movement_service.create_financial_movement(
            movement_data, user_id=1
        )
        
        # Assert
        assert success == True
        assert error_code is None
        assert result['id'] is not None
        assert result['type'] == 'REVENUE'
    
    def test_create_financial_movement_invalid_type(self):
        """Testa validação de tipo inválido"""
        # Arrange
        movement_data = {
            'type': 'INVALID',
            'value': 100.00,
            'category': 'Vendas',
            'description': 'Teste'
        }
        
        # Act
        success, error_code, result = financial_movement_service.create_financial_movement(
            movement_data, user_id=1
        )
        
        # Assert
        assert success == False
        assert error_code == 'INVALID_TYPE'
```

### **Template para Teste de API (Python)**
```python
import pytest
from flask import Flask
from src import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def admin_token(client):
    """Obtém token de admin para testes"""
    response = client.post('/api/auth/login', json={
        'email': 'admin@test.com',
        'password': 'admin123'
    })
    return response.get_json()['token']

def test_get_movements_endpoint(client, admin_token):
    """Testa endpoint de listagem de movimentações"""
    response = client.get(
        '/api/financial-movements/movements',
        headers={'Authorization': f'Bearer {admin_token}'}
    )
    
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
```

### **Template para Teste Frontend (JavaScript)**
```javascript
import { getFinancialMovements } from '../src/js/api/financial-movements.js';

describe('Financial Movements API', () => {
    beforeEach(() => {
        // Setup: mock fetch ou MSW
    });
    
    test('getFinancialMovements retorna array', async () => {
        const movements = await getFinancialMovements();
        expect(Array.isArray(movements)).toBe(true);
    });
    
    test('getFinancialMovements com filtros', async () => {
        const movements = await getFinancialMovements({
            type: 'REVENUE',
            payment_status: 'Paid'
        });
        
        expect(movements.every(m => m.type === 'REVENUE')).toBe(true);
        expect(movements.every(m => m.payment_status === 'Paid')).toBe(true);
    });
});
```

---

## 🚀 **PRÓXIMOS PASSOS**

1. **Configurar Ambiente de Testes**
   - [ ] Instalar dependências de teste (pytest, jest, etc)
   - [ ] Configurar banco de dados de testes
   - [ ] Configurar fixtures e mocks

2. **Implementar Testes Críticos (Fase 1)**
   - [ ] Testes de transações atômicas
   - [ ] Testes de registro automático
   - [ ] Testes de endpoints principais

3. **Implementar Testes Importantes (Fase 2)**
   - [ ] Testes de compras
   - [ ] Testes de frontend
   - [ ] Testes de performance

4. **Implementar Testes Complementares (Fase 3)**
   - [ ] Testes de recorrências
   - [ ] Testes de conciliação
   - [ ] Testes de UI/UX

5. **Configurar CI/CD**
   - [ ] Integrar testes no pipeline
   - [ ] Configurar coverage mínimo
   - [ ] Configurar relatórios de testes

---

## 📊 **MÉTRICAS DE SUCESSO**

### **Cobertura de Código**
- **Mínimo:** 70% de cobertura
- **Ideal:** 80%+ de cobertura
- **Crítico:** 90%+ para serviços financeiros

### **Taxa de Sucesso**
- **Mínimo:** 95% dos testes passando
- **Ideal:** 100% dos testes passando

### **Performance**
- **Listagem:** < 2s para 1000 registros
- **Resumo:** < 1s
- **Criação:** < 500ms

---

**Documento criado em:** {{ data_atual }}  
**Versão:** 1.0  
**Baseado em:** Roteiros de Integração e Ajustes do Sistema de Fluxo de Caixa

