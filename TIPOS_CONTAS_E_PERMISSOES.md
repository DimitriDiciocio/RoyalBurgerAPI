# 👥 TIPOS DE CONTAS E PERMISSÕES — Sistema Royal Burger

## 📋 **VISÃO GERAL**

O sistema Royal Burger possui **5 tipos de contas (roles)** com diferentes níveis de acesso e funcionalidades. Cada role tem permissões específicas para garantir segurança e organização das operações.

---

## 🔐 **TIPOS DE CONTAS**

### **1. 👑 ADMINISTRADOR (admin)**

**Descrição:** Conta com **acesso total** ao sistema. Pode realizar todas as operações e configurações.

#### **Funcionalidades Completas:**

##### **📊 Gestão Financeira (Fluxo de Caixa)**
- ✅ Visualizar todas as movimentações financeiras
- ✅ Criar e editar movimentações (receitas, despesas, CMV, impostos)
- ✅ Atualizar status de pagamento (Pending/Paid)
- ✅ Acessar resumo do fluxo de caixa
- ✅ Visualizar contas a pagar (pendências)
- ✅ Gerenciar impostos recorrentes
- ✅ Criar e gerenciar regras de recorrência
- ✅ Gerar movimentações recorrentes
- ✅ Realizar conciliação bancária
- ✅ Atualizar informações de gateway de pagamento
- ✅ Acessar relatórios de conciliação

##### **🛒 Gestão de Compras**
- ✅ Criar notas fiscais de compra
- ✅ Listar e visualizar compras
- ✅ Gerenciar entrada de estoque via compras

##### **📦 Gestão de Produtos e Estoque**
- ✅ Criar, editar e excluir produtos
- ✅ Gerenciar categorias de produtos
- ✅ Gerenciar ingredientes
- ✅ Visualizar e atualizar estoque
- ✅ Gerenciar ficha técnica de produtos (ingredientes)

##### **👥 Gestão de Usuários**
- ✅ Criar, editar e excluir usuários
- ✅ Alterar roles de usuários
- ✅ Ativar/desativar contas
- ✅ Visualizar lista completa de usuários
- ✅ Gerenciar permissões

##### **📋 Gestão de Pedidos**
- ✅ Visualizar todos os pedidos
- ✅ Atualizar status de pedidos
- ✅ Cancelar pedidos
- ✅ Visualizar histórico completo

##### **🎯 Gestão de Promoções**
- ✅ Criar, editar e excluir promoções
- ✅ Ativar/desativar promoções

##### **🏪 Gestão de Loja**
- ✅ Configurar informações da loja
- ✅ Gerenciar horários de funcionamento

##### **📊 Relatórios e Dashboard**
- ✅ Acessar dashboard administrativo
- ✅ Visualizar todos os relatórios
- ✅ Gerar relatórios em PDF
- ✅ Acessar estatísticas completas

##### **⚙️ Configurações do Sistema**
- ✅ Acessar e modificar configurações gerais (`APP_SETTINGS`)
- ✅ Configurar taxas de pagamento
- ✅ Configurar sistema de fidelidade
- ✅ Configurar impressão

##### **🔔 Notificações**
- ✅ Visualizar todas as notificações
- ✅ Enviar notificações

##### **💬 Chat**
- ✅ Acessar chat do sistema

##### **🎁 Sistema de Fidelidade**
- ✅ Gerenciar programa de fidelidade
- ✅ Visualizar pontos de clientes
- ✅ Configurar regras de pontos

##### **🪑 Mesas**
- ✅ Gerenciar mesas do restaurante
- ✅ Visualizar status das mesas

##### **📑 Grupos e Categorias**
- ✅ Gerenciar grupos de produtos
- ✅ Gerenciar categorias

##### **🔒 Segurança**
- ✅ **Único role que pode excluir permanentemente produtos**
- ✅ Pode alterar qualquer configuração crítica
- ✅ Proteção especial: não pode alterar role do último admin ativo

---

### **2. 👔 GERENTE (manager)**

**Descrição:** Conta com **acesso administrativo operacional**. Pode gerenciar operações do dia a dia, mas com algumas limitações em relação ao admin.

#### **Funcionalidades:**

##### **📊 Gestão Financeira (Fluxo de Caixa)** ✅ **IGUAL AO ADMIN**
- ✅ Visualizar todas as movimentações financeiras
- ✅ Criar e editar movimentações
- ✅ Atualizar status de pagamento
- ✅ Acessar resumo do fluxo de caixa
- ✅ Visualizar contas a pagar
- ✅ Gerenciar impostos recorrentes
- ✅ Criar e gerenciar regras de recorrência
- ✅ Gerar movimentações recorrentes
- ✅ Realizar conciliação bancária
- ✅ Atualizar informações de gateway
- ✅ Acessar relatórios de conciliação

##### **🛒 Gestão de Compras** ✅ **IGUAL AO ADMIN**
- ✅ Criar notas fiscais de compra
- ✅ Listar e visualizar compras
- ✅ Gerenciar entrada de estoque

##### **📦 Gestão de Produtos e Estoque** ✅ **IGUAL AO ADMIN**
- ✅ Criar, editar produtos
- ✅ Gerenciar categorias
- ✅ Gerenciar ingredientes
- ✅ Visualizar e atualizar estoque
- ❌ **NÃO pode excluir permanentemente produtos** (apenas admin)

##### **👥 Gestão de Usuários** ✅ **IGUAL AO ADMIN**
- ✅ Criar, editar usuários
- ✅ Alterar roles (exceto último admin)
- ✅ Ativar/desativar contas
- ✅ Visualizar lista de usuários

##### **📋 Gestão de Pedidos** ✅ **IGUAL AO ADMIN**
- ✅ Visualizar todos os pedidos
- ✅ Atualizar status de pedidos
- ✅ Cancelar pedidos
- ✅ Visualizar histórico

##### **🎯 Gestão de Promoções** ✅ **IGUAL AO ADMIN**
- ✅ Criar, editar e excluir promoções
- ✅ Ativar/desativar promoções

##### **🏪 Gestão de Loja** ✅ **IGUAL AO ADMIN**
- ✅ Configurar informações da loja
- ✅ Gerenciar horários

##### **📊 Relatórios e Dashboard** ✅ **IGUAL AO ADMIN**
- ✅ Acessar dashboard
- ✅ Visualizar relatórios
- ❌ **NÃO pode gerar relatórios em PDF** (apenas admin)

##### **🔔 Notificações** ✅ **IGUAL AO ADMIN**
- ✅ Visualizar notificações
- ✅ Enviar notificações

##### **💬 Chat** ✅ **IGUAL AO ADMIN**
- ✅ Acessar chat

##### **🎁 Sistema de Fidelidade** ✅ **IGUAL AO ADMIN**
- ✅ Gerenciar programa de fidelidade
- ✅ Visualizar pontos
- ✅ Configurar regras

##### **🪑 Mesas** ✅ **IGUAL AO ADMIN**
- ✅ Gerenciar mesas
- ✅ Visualizar status

##### **📑 Grupos e Categorias** ✅ **IGUAL AO ADMIN**
- ✅ Gerenciar grupos
- ✅ Gerenciar categorias

##### **⚙️ Configurações do Sistema** ❌ **LIMITADO**
- ❌ **NÃO pode acessar configurações gerais** (`APP_SETTINGS`)
- ❌ **NÃO pode modificar taxas de pagamento**
- ❌ **NÃO pode alterar configurações críticas**

##### **🔒 Limitações Especiais**
- ❌ Não pode excluir permanentemente produtos
- ❌ Não pode gerar relatórios em PDF
- ❌ Não pode alterar configurações do sistema

---

### **3. 🧑‍💼 ATENDENTE (attendant)**

**Descrição:** Conta para funcionários que atendem clientes e gerenciam pedidos no dia a dia.

#### **Funcionalidades:**

##### **📋 Gestão de Pedidos** ✅
- ✅ Visualizar pedidos
- ✅ Atualizar status de pedidos
- ✅ Gerenciar pedidos em andamento

##### **🪑 Mesas** ✅
- ✅ Visualizar status das mesas
- ✅ Gerenciar mesas (abrir/fechar)

##### **🔔 Notificações** ✅
- ✅ Visualizar notificações
- ✅ Receber notificações de pedidos

##### **💬 Chat** ✅
- ✅ Acessar chat do sistema
- ✅ Comunicar com clientes

##### **📦 Estoque** ❌ **LIMITADO**
- ❌ Não pode criar/editar produtos
- ❌ Não pode gerenciar estoque diretamente
- ✅ Pode visualizar estoque (se permitido)

##### **❌ Sem Acesso:**
- ❌ Gestão financeira
- ❌ Gestão de usuários
- ❌ Configurações do sistema
- ❌ Relatórios administrativos
- ❌ Gestão de compras
- ❌ Gestão de promoções

---

### **4. 🚴 ENTREGADOR (delivery)**

**Descrição:** Conta para entregadores que realizam entregas de pedidos.

#### **Funcionalidades:**

##### **📋 Gestão de Pedidos** ✅ **LIMITADO**
- ✅ Visualizar pedidos de entrega
- ✅ Atualizar status de entrega
- ✅ Marcar pedido como "a caminho"
- ✅ Marcar pedido como "entregue"

##### **🔔 Notificações** ✅
- ✅ Receber notificações de novos pedidos de entrega
- ✅ Visualizar notificações

##### **❌ Sem Acesso:**
- ❌ Gestão financeira
- ❌ Gestão de produtos
- ❌ Gestão de usuários
- ❌ Configurações
- ❌ Relatórios
- ❌ Chat (geral)
- ❌ Mesas

---

### **5. 👤 CLIENTE (customer)**

**Descrição:** Conta para clientes que fazem pedidos no restaurante.

#### **Funcionalidades:**

##### **🛒 Pedidos** ✅
- ✅ Criar pedidos
- ✅ Visualizar seus próprios pedidos
- ✅ Acompanhar status dos pedidos
- ✅ Cancelar pedidos (se permitido)

##### **🎁 Sistema de Fidelidade** ✅
- ✅ Visualizar seus próprios pontos
- ✅ Resgatar pontos em pedidos
- ✅ Ver histórico de pontos

##### **🔔 Notificações** ✅
- ✅ Receber notificações sobre seus pedidos
- ✅ Visualizar notificações

##### **💬 Chat** ✅
- ✅ Acessar chat
- ✅ Comunicar com o restaurante

##### **❌ Sem Acesso:**
- ❌ Gestão financeira
- ❌ Gestão de produtos
- ❌ Gestão de usuários
- ❌ Configurações
- ❌ Relatórios administrativos
- ❌ Visualizar pedidos de outros clientes
- ❌ Gestão de estoque
- ❌ Mesas (gerenciamento)

---

## 📊 **TABELA COMPARATIVA DE PERMISSÕES**

| Funcionalidade | Admin | Manager | Attendant | Delivery | Customer |
|----------------|-------|---------|-----------|----------|----------|
| **Fluxo de Caixa** | ✅ Total | ✅ Total | ❌ | ❌ | ❌ |
| **Compras** | ✅ Total | ✅ Total | ❌ | ❌ | ❌ |
| **Produtos** | ✅ Total | ✅ Editar | ❌ | ❌ | ❌ |
| **Excluir Produtos** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Estoque** | ✅ Total | ✅ Total | ⚠️ Visualizar | ❌ | ❌ |
| **Usuários** | ✅ Total | ✅ Total | ❌ | ❌ | ❌ |
| **Pedidos** | ✅ Total | ✅ Total | ✅ Gerenciar | ✅ Entregas | ✅ Próprios |
| **Promoções** | ✅ Total | ✅ Total | ❌ | ❌ | ❌ |
| **Configurações** | ✅ Total | ❌ | ❌ | ❌ | ❌ |
| **Relatórios PDF** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Dashboard** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Mesas** | ✅ Total | ✅ Total | ✅ Gerenciar | ❌ | ❌ |
| **Fidelidade** | ✅ Total | ✅ Total | ❌ | ❌ | ✅ Próprio |
| **Chat** | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Notificações** | ✅ Total | ✅ Total | ✅ Receber | ✅ Receber | ✅ Receber |

---

## 🔒 **REGRAS DE SEGURANÇA ESPECIAIS**

### **1. Proteção do Último Admin**
- ❌ **Nenhum role pode alterar o role do último administrador ativo**
- ✅ Sistema impede que o último admin seja rebaixado ou desativado
- ✅ Garante que sempre haverá pelo menos um admin no sistema

### **2. Hierarquia de Permissões**
```
Admin > Manager > Attendant/Delivery > Customer
```

### **3. Validação de Roles**
- ✅ Roles válidos: `admin`, `manager`, `attendant`, `delivery`, `customer`
- ✅ Sistema valida role antes de criar/atualizar usuário
- ✅ Roles são armazenados no banco de dados na tabela `USERS`

---

## 📝 **EXEMPLOS DE USO**

### **Cenário 1: Gerente precisa acessar fluxo de caixa**
✅ **Permitido** — Gerente tem acesso completo ao fluxo de caixa, igual ao admin.

### **Cenário 2: Atendente precisa criar produto**
❌ **Negado** — Apenas admin e manager podem criar produtos.

### **Cenário 3: Cliente quer ver pedidos de outros clientes**
❌ **Negado** — Cliente só pode ver seus próprios pedidos.

### **Cenário 4: Manager precisa alterar taxa de pagamento**
❌ **Negado** — Apenas admin pode alterar configurações do sistema.

### **Cenário 5: Admin quer excluir último admin ativo**
❌ **Negado** — Sistema impede alteração do último admin.

---

## 🎯 **RECOMENDAÇÕES DE USO**

### **Para Administradores:**
- Use para configurações críticas do sistema
- Gerencie usuários e permissões
- Configure taxas e parâmetros financeiros
- Gere relatórios administrativos

### **Para Gerentes:**
- Use para operações do dia a dia
- Gerencie fluxo de caixa e compras
- Gerencie produtos e estoque
- Visualize relatórios e dashboards

### **Para Atendentes:**
- Use para gerenciar pedidos
- Atender clientes
- Gerenciar mesas
- Comunicar via chat

### **Para Entregadores:**
- Use para visualizar pedidos de entrega
- Atualizar status de entrega
- Receber notificações

### **Para Clientes:**
- Use para fazer pedidos
- Acompanhar pedidos
- Gerenciar pontos de fidelidade
- Comunicar com o restaurante

---

## 📌 **NOTAS IMPORTANTES**

1. **Fluxo de Caixa:** Admin e Manager têm **acesso idêntico** a todas as funcionalidades financeiras.

2. **Configurações:** Apenas Admin pode modificar `APP_SETTINGS` (taxas, configurações gerais).

3. **Exclusão Permanente:** Apenas Admin pode excluir permanentemente produtos do sistema.

4. **Relatórios PDF:** Apenas Admin pode gerar relatórios em PDF.

5. **Proteção de Admin:** Sistema garante que sempre haverá pelo menos um admin ativo.

---

## 🔄 **ATUALIZAÇÕES RECENTES**

**Última atualização:** Sistema de fluxo de caixa agora permite acesso de **Admin e Manager** com permissões idênticas.

---

## 📚 **REFERÊNCIAS**

- `src/services/auth_service.py` — Sistema de autenticação e roles
- `src/services/user_service.py` — Gestão de usuários e validação de roles
- `src/routes/*` — Definição de permissões por rota

