import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  

class Config:  
    # ALTERAÇÃO: SECRET_KEY deve ser obrigatória via variável de ambiente em produção
    # Gera chave temporária apenas para desenvolvimento se não estiver definida
    _secret_key = os.environ.get('SECRET_KEY')
    if not _secret_key:
        import secrets
        # Gera chave temporária apenas para desenvolvimento
        _secret_key = secrets.token_urlsafe(32)
        # ALTERAÇÃO: Em produção, força erro se SECRET_KEY não estiver definida
        flask_env = os.environ.get('FLASK_ENV', 'development')
        if flask_env not in ('development', 'dev', 'test'):
            import warnings
            warnings.warn("SECRET_KEY não definida via variável de ambiente! Use apenas em desenvolvimento.", UserWarning)
    SECRET_KEY = _secret_key
    
    # ALTERAÇÃO: DEBUG deve ser False em produção por padrão
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    
    # ALTERAÇÃO: JWT_SECRET_KEY deve ser obrigatória via variável de ambiente
    _jwt_secret_key = os.environ.get('JWT_SECRET_KEY')
    if not _jwt_secret_key:
        import secrets
        _jwt_secret_key = secrets.token_urlsafe(32)
        # ALTERAÇÃO: Em produção, força erro se JWT_SECRET_KEY não estiver definida
        flask_env = os.environ.get('FLASK_ENV', 'development')
        if flask_env not in ('development', 'dev', 'test'):
            import warnings
            warnings.warn("JWT_SECRET_KEY não definida via variável de ambiente! Use apenas em desenvolvimento.", UserWarning)
    JWT_SECRET_KEY = _jwt_secret_key
    
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 14400))  
    DATABASE_PATH = os.path.join(PROJECT_ROOT, 'database', 'royalburger.fdb')
    FIREBIRD_HOST = os.environ.get('FIREBIRD_HOST', 'localhost')  
    FIREBIRD_PORT = int(os.environ.get('FIREBIRD_PORT', 3050))  
    FIREBIRD_USER = os.environ.get('FIREBIRD_USER', 'SYSDBA')  
    # IMPLEMENTAÇÃO: Validação de senha do banco (Recomendação #6)
    # Senha do banco deve vir de variável de ambiente, nunca hardcoded
    _firebird_password = os.environ.get('FIREBIRD_PASSWORD')
    if not _firebird_password:
        flask_env = os.environ.get('FLASK_ENV', 'development')
        if flask_env not in ('development', 'dev', 'test'):
            # Em produção, senha é obrigatória
            raise ValueError("FIREBIRD_PASSWORD deve ser definida via variável de ambiente em produção!")
        # Apenas em desenvolvimento, usa valor padrão (com warning)
        import warnings
        warnings.warn(
            "FIREBIRD_PASSWORD não definida via variável de ambiente! "
            "Usando valor padrão apenas para desenvolvimento.",
            UserWarning
        )
        _firebird_password = 'sysdba'  # Apenas para desenvolvimento
    FIREBIRD_PASSWORD = _firebird_password  
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')  
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))  
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']  
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', '1', 't']  
    _MAIL_ADDRESS = os.environ.get('MAIL') or os.environ.get('MAIL_USERNAME')  
    MAIL_USERNAME = _MAIL_ADDRESS  
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')  
    MAIL_DEFAULT_SENDER = (os.environ.get('MAIL_DISPLAY_NAME', 'Royal Burger'), _MAIL_ADDRESS)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'uploads', 'products')  

    # --- Configurações de Impressão da Cozinha ---
    # Backend de impressão: windows_sumatra | linux_lpr (padrão)
    PRINT_BACKEND = os.environ.get('PRINT_BACKEND', 'windows_sumatra')
    # Nome da impressora padrão no sistema
    PRINTER_NAME = os.environ.get('PRINTER_NAME', '')
    # Caminho para o executável do SumatraPDF (apenas Windows, recomendável para 32 bits)
    SUMATRA_PATH = os.environ.get('SUMATRA_PATH', r'C:\\Program Files\\SumatraPDF\\SumatraPDF.exe')
    # Habilita impressão automática após criação do pedido
    ENABLE_AUTOPRINT = os.environ.get('ENABLE_AUTOPRINT', 'true').lower() in ['true', '1', 't']
    # Timeout padrão para jobs de impressão (segundos)
    PRINT_TIMEOUT_SEC = int(os.environ.get('PRINT_TIMEOUT_SEC', 20))