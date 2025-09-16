# src/__init__.py

from flask import Flask
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from flask_mail import Mail
from .config import Config

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

    app.register_blueprint(swagger_bp, url_prefix='/api/docs')
    app.register_blueprint(swaggerui_blueprint, url_prefix='/api/docs')

    # --- Registro de Eventos de Socket ---
    from .sockets import chat_events

    # --- Rota de Verificação de Saúde ---
    @app.route('/api/health')
    def health_check():
        return "API is running!"

    return app