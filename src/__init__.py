# src/__init__.py

from flask import Flask
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from flask_mail import Mail
from .config import Config
import src.services.auth_service as auth_service

# NOVO: Importa os blueprints da documentação que criamos
from .routes.swagger_route import swagger_bp, swaggerui_blueprint

# Instâncias globais
socketio = SocketIO(cors_allowed_origins="*")
mail = Mail()


def create_app():
    """
    Cria e configura uma instância do aplicativo Flask.
    """
    app = Flask(__name__)
    app.config.from_object(Config)

    jwt = JWTManager(app)

    app.config["JWT_BLOCKLIST_ENABLED"] = True
    app.config["JWT_BLOCKLIST_TOKEN_CHECKS"] = ["access", "refresh"]

    @jwt.token_in_blocklist_loader
    def check_if_token_in_blocklist(jwt_header, jwt_payload):
        return auth_service.is_token_revoked(jwt_payload)

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return {
            "error": "Token revogado, faça login novamente",
            "code": "TOKEN_REVOKED",
            "message": "Este token foi revogado (logout realizado). Por favor, faça login novamente."
        }, 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return {
            "error": "Sua sessão expirou, faça login novamente",
            "code": "SESSION_EXPIRED",
            "message": "Sua sessão expirou após 2 horas de inatividade. Por favor, faça login novamente para continuar."
        }, 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return {
            "error": "Token inválido, faça login novamente",
            "code": "INVALID_TOKEN",
            "message": "O token de acesso é inválido ou corrompido. Por favor, faça login novamente."
        }, 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return {
            "error": "Token de acesso necessário",
            "code": "MISSING_TOKEN",
            "message": "Esta operação requer autenticação. Por favor, faça login para continuar."
        }, 401

    socketio.init_app(app)
    mail.init_app(app)

    # --- Registro de Blueprints (REST API) ---
    # CORREÇÃO: O prefixo de todas as rotas deve ser '/api' para o mundo exterior.

    from .routes.customer_routes import customer_bp
    app.register_blueprint(customer_bp, url_prefix='/api/customers')

    from .routes.user_routes import user_bp
    app.register_blueprint(user_bp, url_prefix='/api/users')

    from .routes.product_routes import product_bp
    app.register_blueprint(product_bp, url_prefix='/api/products')

    from .routes.order_routes import order_bp
    app.register_blueprint(order_bp, url_prefix='/api/orders')

    from .routes.section_routes import section_bp
    app.register_blueprint(section_bp, url_prefix='/api/sections')

    from .routes.ingredient_routes import ingredient_bp
    app.register_blueprint(ingredient_bp, url_prefix='/api/ingredients')

    from .routes.chat_routes import chat_bp
    app.register_blueprint(chat_bp, url_prefix='/api/chats')

    from .routes.notification_routes import notification_bp
    app.register_blueprint(notification_bp, url_prefix='/api/notifications')

    # Novas rotas para o painel administrativo
    from .routes.dashboard_routes import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')

    from .routes.stock_routes import stock_bp
    app.register_blueprint(stock_bp, url_prefix='/api/stock')

    from .routes.menu_routes import menu_bp
    app.register_blueprint(menu_bp, url_prefix='/api/menu')

    from .routes.reports_routes import reports_bp
    app.register_blueprint(reports_bp, url_prefix='/api/reports')

    from .routes.financial_routes import financial_bp
    app.register_blueprint(financial_bp, url_prefix='/api/financials')

    from .routes.settings_routes import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/api/settings')

    app.register_blueprint(swagger_bp, url_prefix='/api/docs')
    app.register_blueprint(swaggerui_blueprint, url_prefix='/api/docs')

    # --- Registro de Eventos de Socket ---
    from .sockets import chat_events

    # --- Rota de Verificação de Saúde ---
    @app.route('/api/health')
    def health_check():
        return "API is running!"

    return app