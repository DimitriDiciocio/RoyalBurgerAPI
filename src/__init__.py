from flask import Flask  
from dotenv import load_dotenv  
from flask_jwt_extended import JWTManager  
from flask_socketio import SocketIO  
from flask_mail import Mail  
load_dotenv()  
from .config import Config  
import src.services.auth_service as auth_service  
from flask_cors import CORS  
from .routes.swagger_route import swagger_bp, swaggerui_blueprint  

socketio = SocketIO(cors_allowed_origins="*")  
mail = Mail()  


def create_app():  
    app = Flask(__name__)  
    app.config.from_object(Config)
    
    # Configuração para permitir multipart/form-data
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB  
    CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:5000"]}}, supports_credentials=True, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization', 'Content-Disposition'])  
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

    from .routes.customer_routes import customer_bp  
    app.register_blueprint(customer_bp, url_prefix='/api/customers')  
    from .routes.user_routes import user_bp  
    app.register_blueprint(user_bp, url_prefix='/api/users')  
    from .routes.product_routes import product_bp  
    app.register_blueprint(product_bp, url_prefix='/api/products')  
    from .routes.order_routes import order_bp  
    app.register_blueprint(order_bp, url_prefix='/api/orders')  
    from .routes.ingredient_routes import ingredient_bp  
    app.register_blueprint(ingredient_bp, url_prefix='/api/ingredients')  
    from .routes.chat_routes import chat_bp  
    app.register_blueprint(chat_bp, url_prefix='/api/chats')  
    from .routes.notification_routes import notification_bp  
    app.register_blueprint(notification_bp, url_prefix='/api/notifications')  
    from .routes.dashboard_routes import dashboard_bp  
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')  
    from .routes.stock_routes import stock_bp  
    app.register_blueprint(stock_bp, url_prefix='/api/stock')  
    from .routes.menu_routes import menu_bp  
    app.register_blueprint(menu_bp, url_prefix='/api/menu')  
    from .routes.reports_routes import reports_bp  
    app.register_blueprint(reports_bp, url_prefix='/api/reports')  
    from .routes.pdf_report_routes import pdf_reports_bp  
    app.register_blueprint(pdf_reports_bp, url_prefix='/api/pdf_reports')  
    from .routes.financial_routes import financial_bp  
    app.register_blueprint(financial_bp, url_prefix='/api/financials')  
    from .routes.settings_routes import settings_bp  
    app.register_blueprint(settings_bp, url_prefix='/api/settings')  
    from .routes.category_routes import category_bp  
    app.register_blueprint(category_bp, url_prefix='/api/categories')  
    from .routes.cart_routes import cart_bp  
    app.register_blueprint(cart_bp, url_prefix='/api/cart')  
    app.register_blueprint(swagger_bp, url_prefix='/api/docs')  
    app.register_blueprint(swaggerui_blueprint, url_prefix='/api/docs')  
    from .sockets import chat_events  
    
    # Handler global para requisições OPTIONS (preflight)
    @app.before_request
    def handle_preflight():
        from flask import request, make_response
        if request.method == "OPTIONS":
            response = make_response()
            # Verifica a origem da requisição
            origin = request.headers.get('Origin')
            allowed_origins = ["http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:5000"]
            
            if origin in allowed_origins:
                response.headers.add("Access-Control-Allow-Origin", origin)
            else:
                response.headers.add("Access-Control-Allow-Origin", "http://127.0.0.1:5500")
            
            response.headers.add('Access-Control-Allow-Headers', "Content-Type, Authorization, Content-Disposition")
            response.headers.add('Access-Control-Allow-Methods', "GET, POST, PUT, DELETE, PATCH, OPTIONS")
            response.headers.add('Access-Control-Allow-Credentials', "true")
            return response
    
    # Handler para permitir diferentes tipos de conteúdo
    @app.before_request
    def handle_content_type():
        from flask import request
        # Permite multipart/form-data para uploads
        if request.method in ['POST', 'PUT'] and request.content_type and 'multipart/form-data' in request.content_type:
            # Não faz nada, deixa o Flask processar normalmente
            pass
    
    @app.route('/api/health')  
    def health_check():  
        return "API is running!"
    
    # Rota segura para servir uploads
    @app.route('/api/uploads/<path:filename>')
    def serve_upload(filename):
        """
        Serve arquivos de upload de forma segura
        """
        from flask import send_from_directory, abort
        import os
        
        try:
            # Valida o nome do arquivo para segurança
            if '..' in filename or filename.startswith('/'):
                abort(400)
            
            # Determina o diretório baseado no tipo de arquivo
            if filename.startswith('products/'):
                upload_dir = os.path.join(os.getcwd(), 'uploads', 'products')
                filename = filename.replace('products/', '')
            else:
                abort(404)
            
            # Verifica se o arquivo existe
            file_path = os.path.join(upload_dir, filename)
            if not os.path.exists(file_path):
                abort(404)
            
            # Determina o MIME type
            if filename.endswith('.jpeg') or filename.endswith('.jpg'):
                mimetype = 'image/jpeg'
            elif filename.endswith('.png'):
                mimetype = 'image/png'
            elif filename.endswith('.gif'):
                mimetype = 'image/gif'
            else:
                abort(400)
            
            # Serve o arquivo com headers de segurança
            response = send_from_directory(upload_dir, filename, mimetype=mimetype)
            # Cache mais curto para evitar problemas com imagens atualizadas
            response.headers['Cache-Control'] = 'public, max-age=300'  # Cache por 5 minutos
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            # Adiciona ETag baseado na data de modificação do arquivo para cache mais inteligente
            import time
            file_mtime = os.path.getmtime(file_path)
            response.headers['ETag'] = f'"{int(file_mtime)}"'
            # Adiciona timestamp para cache busting
            response.headers['Last-Modified'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(file_mtime))
            return response
            
        except Exception as e:
            print(f"Erro ao servir upload: {e}")
            abort(500)
    
    return app  
