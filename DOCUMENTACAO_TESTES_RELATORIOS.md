# 📋 Documentação de Testes - Relatórios Royal Burger

## 📅 Formato de Datas Padronizado

**TODOS os relatórios agora aceitam datas no formato brasileiro: `DD-MM-YYYY`**

Exemplos válidos:
- `01-01-2024` ✅
- `31-12-2024` ✅
- `15-06-2025` ✅

## 🔧 Configuração do Postman

### Variáveis de Ambiente

Crie as seguintes variáveis no Postman:

```
base_url = http://127.0.0.1:5000
token = (seu_token_jwt_após_login)
```

---

## 📊 Relatórios JSON

### 1. Relatório Financeiro Detalhado

**Rota:** `GET` ou `POST /api/reports/financial/detailed`

**Método GET:**
```
GET {{base_url}}/api/reports/financial/detailed?start_date=01-01-2024&end_date=31-01-2024
```

**Método POST:**
```
POST {{base_url}}/api/reports/financial/detailed
```

**Body (raw JSON):**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024"
}
```

**Headers:**
```
Authorization: Bearer {{token}}
Content-Type: application/json
```

---

## 📄 Relatórios PDF - GET

### 1. Relatório de Usuários

**Rota:** `GET /api/pdf_reports/users`

**Exemplo:**
```
GET {{base_url}}/api/pdf_reports/users?role=admin&status=active&created_after=01-01-2024&created_before=31-12-2024
```

**Parâmetros:**
- `role`: admin, manager, attendant, delivery, customer
- `status`: active, inactive
- `created_after`: DD-MM-YYYY
- `created_before`: DD-MM-YYYY
- `search`: texto de busca

---

### 2. Relatório de Ingredientes

**Rota:** `GET /api/pdf_reports/ingredients`

**Exemplo:**
```
GET {{base_url}}/api/pdf_reports/ingredients?stock_status=low&min_price=10.00
```

---

### 3. Relatório de Produtos

**Rota:** `GET /api/pdf_reports/products`

**Exemplo:**
```
GET {{base_url}}/api/pdf_reports/products?section_id=2&status=active&include_inactive=false
```

---

### 4. Relatório de Pedidos

**Rota:** `GET /api/pdf_reports/orders`

**Exemplo:**
```
GET {{base_url}}/api/pdf_reports/orders?start_date=01-01-2024&end_date=31-01-2024&status=completed
```

---

## 📄 Relatórios PDF - POST

### 1. Relatório de Vendas Detalhado

**Rota:** `POST /api/pdf_reports/sales/detailed`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "order_type": "delivery",
  "payment_method": "credit_card",
  "status": "completed"
}
```

---

### 2. Relatório de Performance de Pedidos

**Rota:** `POST /api/pdf_reports/orders/performance`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "attendant_id": 10,
  "deliverer_id": 20,
  "status": "completed",
  "order_type": "delivery"
}
```

---

### 3. Relatório de Análise de Produtos

**Rota:** `POST /api/pdf_reports/products/analysis`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "category_id": 5,
  "product_id": 100,
  "price_min": 10.0,
  "price_max": 50.0,
  "status": "active"
}
```

---

### 4. Relatório Financeiro Completo

**Rota:** `POST /api/pdf_reports/financial/complete`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "type": "REVENUE",
  "category": "Vendas",
  "payment_status": "Paid",
  "payment_method": "credit_card"
}
```

---

### 5. Relatório de CMV

**Rota:** `POST /api/pdf_reports/financial/cmv`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "category_id": 3,
  "product_id": 50
}
```

---

### 6. Relatório de Impostos

**Rota:** `POST /api/pdf_reports/financial/taxes`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "category": "ICMS",
  "status": "Paid"
}
```

---

### 7. Relatório Completo de Estoque

**Rota:** `POST /api/pdf_reports/stock/complete`

**Body:**
```json
{
  "status": "low",
  "category": "Carnes",
  "supplier": "Fornecedor ABC",
  "price_min": 10.0,
  "price_max": 100.0
}
```

---

### 8. Relatório de Compras

**Rota:** `POST /api/pdf_reports/purchases`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "supplier": "Fornecedor XYZ",
  "payment_status": "Paid"
}
```

---

### 9. Relatório de Análise de Clientes

**Rota:** `POST /api/pdf_reports/customers/analysis`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "region": "Centro",
  "min_orders": 5,
  "min_spent": 500.0
}
```

---

### 10. Relatório de Fidelidade

**Rota:** `POST /api/pdf_reports/loyalty`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "user_id": 123
}
```

---

### 11. Relatório de Mesas

**Rota:** `POST /api/pdf_reports/tables`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "table_id": 5,
  "attendant_id": 10
}
```

---

### 12. Dashboard Executivo

**Rota:** `POST /api/pdf_reports/executive/dashboard`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024"
}
```

---

### 13. Relatório de Conciliação Bancária

**Rota:** `POST /api/pdf_reports/financial/reconciliation`

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "payment_gateway": "Mercado Pago",
  "bank_account": "Conta Corrente",
  "reconciled": true
}
```

---

## 📝 Exemplos de Coleção Postman

### Exemplo 1: Relatório Financeiro (JSON) - GET

```
GET {{base_url}}/api/reports/financial/detailed?start_date=01-01-2024&end_date=31-01-2024
```

**Headers:**
```
Authorization: Bearer {{token}}
```

---

### Exemplo 2: Relatório Financeiro (JSON) - POST

```
POST {{base_url}}/api/reports/financial/detailed
```

**Headers:**
```
Authorization: Bearer {{token}}
Content-Type: application/json
```

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024"
}
```

---

### Exemplo 3: Relatório de Vendas Detalhado (PDF)

```
POST {{base_url}}/api/pdf_reports/sales/detailed
```

**Headers:**
```
Authorization: Bearer {{token}}
Content-Type: application/json
```

**Body:**
```json
{
  "start_date": "01-01-2024",
  "end_date": "31-01-2024",
  "order_type": "delivery",
  "payment_method": "credit_card"
}
```

---

## ⚠️ Notas Importantes

1. **Formato de Data Padrão:** Todos os relatórios agora aceitam datas no formato **DD-MM-YYYY** (brasileiro)
   - ✅ `01-01-2024` (correto)
   - ✅ `31-12-2024` (correto)
   - ❌ `2024-01-01` (ainda funciona, mas não é o padrão recomendado)
   - ❌ `01/01/2024` (não funciona - use hífen)

2. **Conversão Automática:** As datas são convertidas automaticamente para ISO (YYYY-MM-DD) internamente

3. **Validação:** Todas as datas são validadas antes do processamento

4. **Mensagens de Erro:** Em caso de data inválida, a mensagem indicará o formato esperado: `DD-MM-YYYY`

---

## 🧪 Scripts de Teste para Postman

### Pre-request Script (Collection Level)

```javascript
// Adiciona o token de autenticação se existir
if (pm.environment.get("token")) {
  pm.request.headers.add({
    key: "Authorization",
    value: "Bearer " + pm.environment.get("token"),
  });
}
```

### Test Script (para requisições com datas)

```javascript
pm.test("Status code is 200", function () {
  pm.response.to.have.status(200);
});

pm.test("Response time is less than 5000ms", function () {
  pm.expect(pm.response.responseTime).to.be.below(5000);
});

// Para respostas JSON
if (pm.response.headers.get("Content-Type")?.includes("application/json")) {
  pm.test("Response is JSON", function () {
    pm.response.to.be.json;
  });
}

// Para respostas PDF
if (pm.response.headers.get("Content-Type") === "application/pdf") {
  pm.test("Response is PDF", function () {
    pm.response.to.have.status(200);
  });
}
```

---

## 📅 Função Helper para Datas no Postman

Adicione esta função no Pre-request Script da Collection para facilitar:

```javascript
// Função helper para formatar datas no formato brasileiro
function formatDateBR(daysAgo = 0) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const year = date.getFullYear();
  return `${day}-${month}-${year}`;
}

// Exemplo de uso:
// formatDateBR(0) retorna data de hoje: "18-11-2024"
// formatDateBR(30) retorna 30 dias atrás: "19-10-2024"
```

---

## 🔍 Troubleshooting

### Erro: "Data inválida"
- Verifique se está usando o formato `DD-MM-YYYY`
- Certifique-se de usar hífen (`-`) e não barra (`/`)
- Exemplo correto: `01-01-2024`
- Exemplo incorreto: `01/01/2024`

### Erro: "Intervalo de datas inválido"
- A data de início deve ser anterior ou igual à data de fim
- Verifique se as datas estão no formato correto

### Erro: "start_date e end_date são obrigatórios"
- Para rotas GET, envie os parâmetros na query string
- Para rotas POST, envie no body JSON
- Certifique-se de que ambos os campos estão preenchidos

---

## 📚 Resumo de Formato de Datas

| Formato | Exemplo | Status |
|---------|---------|--------|
| DD-MM-YYYY | `01-01-2024` | ✅ Padrão recomendado |
| YYYY-MM-DD | `2024-01-01` | ✅ Aceito (compatibilidade) |
| DD/MM/YYYY | `01/01/2024` | ❌ Não aceito |

**Recomendação:** Use sempre `DD-MM-YYYY` para consistência.

