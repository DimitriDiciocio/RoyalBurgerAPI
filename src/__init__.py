from flask import Flask  # importa classe principal do Flask
from flask_jwt_extended import JWTManager  # importa gerenciador de JWT
from flask_socketio import SocketIO  # importa SocketIO para WebSockets
from flask_mail import Mail  # importa extensão de email
from .config import Config  # importa configurações da aplicação
import src.services.auth_service as auth_service  # importa serviço de autenticação
from flask_cors import CORS  # importa extensão CORS
from .routes.swagger_route import swagger_bp, swaggerui_blueprint  # importa blueprints da documentação

socketio = SocketIO(cors_allowed_origins="*")  # instância global do SocketIO
mail = Mail()  # instância global do Mail


def create_app():  # factory function para criar instância da aplicação
    app = Flask(__name__)  # cria instância do Flask
    app.config.from_object(Config)  # carrega configurações da classe Config
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)  # habilita CORS para rotas da API
    jwt = JWTManager(app)  # inicializa gerenciador de JWT
    app.config["JWT_BLOCKLIST_ENABLED"] = True  # habilita blacklist de tokens
    app.config["JWT_BLOCKLIST_TOKEN_CHECKS"] = ["access", "refresh"]  # tipos de token a verificar na blacklist
    @jwt.token_in_blocklist_loader  # decorator para verificar token na blacklist
    def check_if_token_in_blocklist(jwt_header, jwt_payload):  # função de verificação
        return auth_service.is_token_revoked(jwt_payload)  # delega verificação ao serviço
    @jwt.revoked_token_loader  # decorator para token revogado
    def revoked_token_callback(jwt_header, jwt_payload):  # callback de token revogado
        return {  # retorna resposta de erro
            "error": "Token revogado, faça login novamente",
            "code": "TOKEN_REVOKED",
            "message": "Este token foi revogado (logout realizado). Por favor, faça login novamente."
        }, 401  # status 401
    @jwt.expired_token_loader  # decorator para token expirado
    def expired_token_callback(jwt_header, jwt_payload):  # callback de token expirado
        return {  # retorna resposta de erro
            "error": "Sua sessão expirou, faça login novamente",
            "code": "SESSION_EXPIRED",
            "message": "Sua sessão expirou após 2 horas de inatividade. Por favor, faça login novamente para continuar."
        }, 401  # status 401
    @jwt.invalid_token_loader  # decorator para token inválido
    def invalid_token_callback(error):  # callback de token inválido
        return {  # retorna resposta de erro
            "error": "Token inválido, faça login novamente",
            "code": "INVALID_TOKEN",
            "message": "O token de acesso é inválido ou corrompido. Por favor, faça login novamente."
        }, 401  # status 401
    @jwt.unauthorized_loader  # decorator para token ausente
    def missing_token_callback(error):  # callback de token ausente
        return {  # retorna resposta de erro
            "error": "Token de acesso necessário",
            "code": "MISSING_TOKEN",
            "message": "Esta operação requer autenticação. Por favor, faça login para continuar."
        }, 401  # status 401
    socketio.init_app(app)  # inicializa SocketIO com a app
    mail.init_app(app)  # inicializa Mail com a app

    from .routes.customer_routes import customer_bp  # importa blueprint de clientes
    app.register_blueprint(customer_bp, url_prefix='/api/customers')  # registra rotas de clientes
    from .routes.user_routes import user_bp  # importa blueprint de usuários
    app.register_blueprint(user_bp, url_prefix='/api/users')  # registra rotas de usuários
    from .routes.product_routes import product_bp  # importa blueprint de produtos
    app.register_blueprint(product_bp, url_prefix='/api/products')  # registra rotas de produtos
    from .routes.order_routes import order_bp  # importa blueprint de pedidos
    app.register_blueprint(order_bp, url_prefix='/api/orders')  # registra rotas de pedidos
    from .routes.section_routes import section_bp  # importa blueprint de seções
    app.register_blueprint(section_bp, url_prefix='/api/sections')  # registra rotas de seções
    from .routes.ingredient_routes import ingredient_bp  # importa blueprint de ingredientes
    app.register_blueprint(ingredient_bp, url_prefix='/api/ingredients')  # registra rotas de ingredientes
    from .routes.chat_routes import chat_bp  # importa blueprint de chats
    app.register_blueprint(chat_bp, url_prefix='/api/chats')  # registra rotas de chats
    from .routes.notification_routes import notification_bp  # importa blueprint de notificações
    app.register_blueprint(notification_bp, url_prefix='/api/notifications')  # registra rotas de notificações
    from .routes.dashboard_routes import dashboard_bp  # importa blueprint do dashboard
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')  # registra rotas do dashboard
    from .routes.stock_routes import stock_bp  # importa blueprint de estoque
    app.register_blueprint(stock_bp, url_prefix='/api/stock')  # registra rotas de estoque
    from .routes.menu_routes import menu_bp  # importa blueprint do menu
    app.register_blueprint(menu_bp, url_prefix='/api/menu')  # registra rotas do menu
    from .routes.reports_routes import reports_bp  # importa blueprint de relatórios
    app.register_blueprint(reports_bp, url_prefix='/api/reports')  # registra rotas de relatórios
    from .routes.financial_routes import financial_bp  # importa blueprint financeiro
    app.register_blueprint(financial_bp, url_prefix='/api/financials')  # registra rotas financeiras
    from .routes.settings_routes import settings_bp  # importa blueprint de configurações
    app.register_blueprint(settings_bp, url_prefix='/api/settings')  # registra rotas de configurações
    app.register_blueprint(swagger_bp, url_prefix='/api/docs')  # registra blueprint do Swagger
    app.register_blueprint(swaggerui_blueprint, url_prefix='/api/docs')  # registra UI do Swagger
    from .sockets import chat_events  # importa eventos de socket do chat
    @app.route('/api/health')  # define rota de verificação de saúde
    def health_check():  # função handler de health check
        return "API is running!"  # retorna status da API
    return app  # retorna instância configurada da aplicação