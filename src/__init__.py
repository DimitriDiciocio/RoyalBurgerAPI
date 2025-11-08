from flask import Flask  
from dotenv import load_dotenv  
from flask_jwt_extended import JWTManager  
from flask_socketio import SocketIO  
from flask_mail import Mail  
import os  # ALTERAÇÃO: Import necessário para CORS_ALLOWED_ORIGINS
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
    # ALTERAÇÃO: CORS configurado de forma mais segura
    # Em produção, especificar origens exatas via variável de ambiente
    allowed_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '*')
    if allowed_origins != '*':
        # Se não for wildcard, converte string separada por vírgulas em lista
        allowed_origins = [origin.strip() for origin in allowed_origins.split(',')]
    
    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,  # ALTERAÇÃO: Configurável via env, não hardcoded "*"
            "methods": ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
            "allow_headers": ['Content-Type', 'Authorization', 'Content-Disposition'],
            "supports_credentials": True
        }
    })  
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
    from .routes.store_routes import store_bp
    app.register_blueprint(store_bp, url_prefix='/api/store')  
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
    from .routes.loyalty_routes import loyalty_bp  
    app.register_blueprint(loyalty_bp, url_prefix='/api/loyalty')  
    from .routes.groups_routes import groups_bp
    app.register_blueprint(groups_bp, url_prefix='/api/groups')
    from .routes.payment_routes import payment_bp
    app.register_blueprint(payment_bp, url_prefix='/api/payments')
    from .routes.table_routes import table_bp
    app.register_blueprint(table_bp, url_prefix='/api/tables')
    from .routes.promotion_routes import promotion_bp
    app.register_blueprint(promotion_bp, url_prefix='/api/promotions')
    app.register_blueprint(swagger_bp, url_prefix='/api/docs')  
    app.register_blueprint(swaggerui_blueprint, url_prefix='/api/docs')  
    from .sockets import chat_events  
    
    # ALTERAÇÃO: Handler de preflight melhorado - usa configuração de CORS centralizada
    # TODO: REVISAR - Este handler pode ser redundante se CORS estiver configurado corretamente acima
    @app.before_request
    def handle_preflight():
        from flask import request, make_response
        if request.method == "OPTIONS":
            response = make_response()
            # ALTERAÇÃO: Usa mesma configuração de CORS que o decorator principal
            origin = request.headers.get('Origin')
            cors_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '*')
            
            if cors_origins == '*' or origin in cors_origins.split(','):
                # Permite origem se estiver na lista ou se CORS permite todas
                response.headers.add("Access-Control-Allow-Origin", origin or '*')
            else:
                # Fallback seguro: não permite origem não autorizada
                response.headers.add("Access-Control-Allow-Origin", cors_origins.split(',')[0] if cors_origins != '*' else '*')
            
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
    
    # IMPLEMENTAÇÃO: Headers de segurança HTTP (Recomendação #1)
    @app.after_request
    def set_security_headers(response):
        """
        Adiciona headers de segurança HTTP em todas as respostas.
        Protege contra XSS, clickjacking, MIME sniffing e força HTTPS.
        """
        # Previne MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Previne clickjacking
        response.headers['X-Frame-Options'] = 'DENY'
        
        # Proteção XSS (navegadores antigos)
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # HSTS - força HTTPS (apenas em produção)
        if os.environ.get('FLASK_ENV') not in ('development', 'dev', 'test'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # Content Security Policy básica (ajustar conforme necessário)
        # TODO: REVISAR - Ajustar CSP conforme políticas de segurança da aplicação
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self';"
        )
        response.headers['Content-Security-Policy'] = csp_policy
        
        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Permissions Policy (antes Feature-Policy)
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response
    
    # IMPLEMENTAÇÃO: Handler global de erros (Recomendação #4)
    import logging
    logger = logging.getLogger(__name__)
    
    @app.errorhandler(400)
    def bad_request(error):
        """Handler para erros 400 (Bad Request)"""
        return {"error": "Requisição inválida", "code": "BAD_REQUEST"}, 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        """Handler para erros 401 (Unauthorized)"""
        return {"error": "Não autorizado", "code": "UNAUTHORIZED"}, 401
    
    @app.errorhandler(403)
    def forbidden(error):
        """Handler para erros 403 (Forbidden)"""
        return {"error": "Acesso negado", "code": "FORBIDDEN"}, 403
    
    @app.errorhandler(404)
    def not_found(error):
        """Handler para erros 404 (Not Found)"""
        return {"error": "Recurso não encontrado", "code": "NOT_FOUND"}, 404
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        """Handler para erros 405 (Method Not Allowed)"""
        return {"error": "Método não permitido", "code": "METHOD_NOT_ALLOWED"}, 405
    
    @app.errorhandler(409)
    def conflict(error):
        """Handler para erros 409 (Conflict)"""
        return {"error": "Conflito na requisição", "code": "CONFLICT"}, 409
    
    @app.errorhandler(422)
    def unprocessable_entity(error):
        """Handler para erros 422 (Unprocessable Entity)"""
        return {"error": "Entidade não processável", "code": "UNPROCESSABLE_ENTITY"}, 422
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handler para erros 500 (Internal Server Error)"""
        logger.error(f"Erro interno do servidor: {error}", exc_info=True)
        # Não expõe detalhes do erro ao cliente em produção
        if app.config.get('DEBUG'):
            return {"error": str(error), "code": "INTERNAL_ERROR"}, 500
        return {"error": "Erro interno do servidor", "code": "INTERNAL_ERROR"}, 500
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """
        Handler global para exceções não tratadas.
        Captura todas as exceções que não foram tratadas especificamente.
        """
        logger.error(f"Exceção não tratada: {type(e).__name__}: {e}", exc_info=True)
        
        # Se for erro HTTP conhecido, delega para handlers específicos
        if hasattr(e, 'code') and e.code:
            return e
        
        # Para outros erros, retorna 500
        if app.config.get('DEBUG'):
            return {"error": str(e), "code": "UNHANDLED_EXCEPTION", "type": type(e).__name__}, 500
        return {"error": "Erro interno do servidor", "code": "UNHANDLED_EXCEPTION"}, 500
    
    # Inicialização e cleanup do pool de conexões
    # O pool é criado automaticamente na primeira chamada de get_db_connection()
    # Fechamos o pool ao encerrar o app para shutdown graceful
    import atexit
    from .database import get_pool
    
    def close_db_pool():
        """Fecha todas as conexões do pool ao encerrar aplicação"""
        import logging
        logger = logging.getLogger(__name__)
        try:
            pool = get_pool()
            if pool:
                pool.close_all()
                logger.info("Pool de conexões fechado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao fechar pool de conexões: {e}", exc_info=True)
    
    atexit.register(close_db_pool)
    
    @app.route('/api/health')  
    def health_check():  
        return "API is running!"
    
    # Rota segura para servir uploads
    @app.route('/api/uploads/<path:filename>')
    def serve_upload(filename):
        """
        Serve arquivos de upload de forma segura
        """
        from flask import abort, request
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
            
            # Abordagem simplificada: ler arquivo em binário e retornar diretamente
            # Isso evita problemas com chunked encoding ou stream
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            file_size = len(image_data)
            
            # Criar resposta direta sem chunked encoding
            from flask import Response
            response = Response(
                image_data,
                mimetype=mimetype,
                headers={
                    'Content-Type': mimetype,
                    'Content-Length': str(file_size),
                    'Accept-Ranges': 'bytes',
                    'X-Content-Type-Options': 'nosniff',
                    'Cache-Control': 'public, max-age=3600',
                }
            )
            
            # Headers CORS
            origin = request.headers.get('Origin')
            if origin:
                response.headers.add('Access-Control-Allow-Origin', origin)
            else:
                response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            response.headers.add('Access-Control-Allow-Credentials', 'true')
            response.headers.add('Cross-Origin-Resource-Policy', 'cross-origin')
            
            return response
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erro ao servir upload: {e}", exc_info=True)
            abort(500)
    
    return app  
