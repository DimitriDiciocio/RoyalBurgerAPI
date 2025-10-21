# Royal Burger API

API REST completa para o sistema de delivery da hamburgueria Royal Burger.

## 🚀 Funcionalidades

- **Sistema de Autenticação JWT** - Login seguro com tokens
- **Gestão de Usuários** - Clientes e funcionários (admin, manager, attendant)
- **Catálogo de Produtos** - Produtos, seções e ingredientes
- **Sistema de Pedidos** - Criação, rastreamento e gestão de pedidos
- **Chat em Tempo Real** - Comunicação entre cliente e atendimento
- **Sistema de Notificações** - Notificações push para usuários
- **Programa de Fidelidade** - Pontos e recompensas
- **Gestão de Endereços** - Múltiplos endereços por cliente
- **WebSockets** - Comunicação em tempo real

## 📋 Pré-requisitos

- Python 3.8+
- Firebird 3.0+
- pip (gerenciador de pacotes Python)

## 🛠️ Instalação

### 1. Clone o repositório

```bash
git clone <url-do-repositorio>
cd RoyalBurger_Multirepo/RoyalBurgerAPI
```

### 2. Crie um ambiente virtual

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
# Configurações de Segurança
SECRET_KEY=sua-chave-secreta-muito-dificil-de-adivinhar-aqui
JWT_SECRET_KEY=sua-outra-chave-jwt-muito-segura-aqui

# Configurações de E-mail
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=seu-email@gmail.com
MAIL_PASSWORD=sua-senha-de-app

# Configurações do Banco de Dados Firebird
FIREBIRD_HOST=localhost
FIREBIRD_PORT=3050
FIREBIRD_USER=SYSDBA
FIREBIRD_PASSWORD=sysdba
```

### 5. Configure o banco de dados

Certifique-se de que o Firebird está rodando e que o arquivo de banco `royalburger.fdb` existe no diretório `../database/`.

### 6. Execute a API

```bash
python run.py
```

A API estará disponível em `http://localhost:5000`

## 📚 Documentação da API

Acesse a documentação interativa em: `http://localhost:5000/api/docs`

### Principais Endpoints

#### Autenticação

- `POST /api/users/login` - Fazer login
- `POST /api/users/logout` - Fazer logout
- `POST /api/users/request-password-reset` - Solicitar recuperação de senha (verifica se email existe)
- `POST /api/users/verify-reset-code` - Verificar código de recuperação
- `POST /api/users/reset-password` - Redefinir senha com código

#### Clientes

- `POST /api/customers` - Cadastrar cliente
- `GET /api/customers` - Listar clientes (admin/manager)
- `GET /api/customers/{id}` - Obter cliente por ID
- `PUT /api/customers/{id}` - Atualizar cliente
- `DELETE /api/customers/{id}` - Inativar cliente
- `DELETE /api/customers/delete-account` - Deletar própria conta (cliente)

#### Produtos

- `GET /api/products` - Listar produtos
- `POST /api/products` - Criar produto (admin/manager)
- `GET /api/products/{id}` - Obter produto por ID
- `PUT /api/products/{id}` - Atualizar produto
- `DELETE /api/products/{id}` - Inativar produto

#### Pedidos

- `POST /api/orders` - Criar pedido (cliente)
- `GET /api/orders` - Listar pedidos do cliente
- `GET /api/orders/all` - Listar todos os pedidos (admin/manager)
- `GET /api/orders/{id}` - Obter pedido por ID
- `PATCH /api/orders/{id}/status` - Atualizar status
- `POST /api/orders/{id}/cancel` - Cancelar pedido

#### Chat

- `GET /api/chats/{order_id}` - Obter histórico do chat
- `POST /api/chats/{order_id}/messages` - Enviar mensagem

#### Notificações

- `GET /api/notifications` - Listar notificações não lidas
- `PATCH /api/notifications/{id}/read` - Marcar como lida
- `PATCH /api/notifications/read-all` - Marcar todas como lidas

#### Fidelidade

- `GET /api/loyalty/balance/{user_id}` - Consultar saldo de pontos
- `GET /api/loyalty/history/{user_id}` - Histórico de pontos
- `POST /api/loyalty/add-points` - Adicionar pontos (admin/manager)
- `POST /api/loyalty/spend-points` - Gastar pontos (admin/manager)
- `POST /api/loyalty/redeem` - Resgatar pontos por desconto
- `POST /api/loyalty/expire-accounts` - Executar expiração de pontos
- `GET /api/loyalty/stats` - Estatísticas do sistema (admin/manager)

## 🔐 Autenticação

A API utiliza JWT (JSON Web Tokens) para autenticação. Para acessar endpoints protegidos, inclua o token no header:

```
Authorization: Bearer <seu_token>
```

### Níveis de Acesso

- **customer** - Cliente comum
- **attendant** - Atendente
- **manager** - Gerente
- **admin** - Administrador

## 🌐 WebSockets

A API suporta WebSockets para funcionalidades em tempo real:

### Eventos de Chat

- `join_chat` - Entrar em uma sala de chat
- `send_message` - Enviar mensagem
- `chat_history` - Receber histórico
- `new_message` - Nova mensagem recebida

### Exemplo de Uso

```javascript
const socket = io("http://localhost:5000");

// Entrar no chat do pedido
socket.emit("join_chat", {
  token: "seu_jwt_token",
  chat_id: 123,
});

// Enviar mensagem
socket.emit("send_message", {
  token: "seu_jwt_token",
  chat_id: 123,
  content: "Olá!",
});

// Escutar mensagens
socket.on("new_message", (data) => {
  console.log("Nova mensagem:", data);
});
```

### Eventos da Cozinha

- `new_kitchen_order` — Emitido quando um novo pedido é criado/confirmado. Payload:

```
{
  "order_number": 1024,
  "order_type": "Delivery",
  "timestamp": "18/10/2025 16:45",
  "notes": "Cliente pediu para caprichar no queijo.",
  "items": [
    {"quantity": 2, "name": "X-Burger Clássico", "extras": [{"type":"add","name":"Bacon","quantity":1}]},
    {"quantity": 1, "name": "Batata Frita G"}
  ]
}
```

Reimpressão manual (admin/manager): `POST /api/orders/{order_id}/reprint`.

## 📊 Códigos de Status

- **200** - Sucesso
- **201** - Criado com sucesso
- **400** - Dados inválidos
- **401** - Não autenticado
- **403** - Acesso negado
- **404** - Recurso não encontrado
- **409** - Conflito (ex: loja fechada)
- **500** - Erro interno do servidor

## 🛡️ Segurança

- Autenticação JWT com expiração
- Validação de senhas fortes
- Validação de CPF
- Sanitização de dados de entrada
- CORS configurado
- Headers de segurança

## 🔧 Desenvolvimento

### Estrutura do Projeto

```
RoyalBurgerAPI/
├── src/
│   ├── routes/          # Rotas da API
│   ├── services/        # Lógica de negócio
│   ├── sockets/         # Eventos WebSocket
│   ├── templates/       # Templates de e-mail
│   ├── utils/           # Utilitários
│   └── openapi/         # Documentação Swagger
├── requirements.txt     # Dependências Python
└── run.py              # Arquivo principal
```

### Adicionando Novas Rotas

1. Crie o arquivo de rota em `src/routes/`
2. Implemente o serviço em `src/services/`
3. Registre a rota em `src/__init__.py`
4. Atualize a documentação Swagger

### Testando a API

Use a documentação Swagger em `http://localhost:5000/api/docs` para testar os endpoints ou ferramentas como Postman/Insomnia.

## 📝 Changelog

### v2.1.0

- ✅ Expiração de token JWT configurada (1 hora por padrão)
- ✅ Validação de formato de e-mail implementada
- ✅ Validação de número de telefone brasileiro implementada
- ✅ Rota de logout adicionada
- ✅ Rota de exclusão de conta para clientes
- ✅ Mensagens de erro mais claras e específicas

### v2.0.0

- ✅ Documentação Swagger completa
- ✅ Sistema de autenticação JWT corrigido
- ✅ Templates de e-mail criados
- ✅ WebSockets funcionando
- ✅ Todas as rotas documentadas
- ✅ Validações implementadas

### v1.0.0

- 🎉 Versão inicial da API

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## 📞 Suporte

Para suporte, entre em contato:

- Email: dev@royalburger.com
- Documentação: `http://localhost:5000/api/docs`
