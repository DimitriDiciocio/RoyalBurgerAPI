import os  
import fdb  

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  

class Config:  
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-dificil-de-adivinhar'  
    DEBUG = True  
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'uma-outra-chave-jwt-muito-segura'  
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 7200))  
    DATABASE_PATH = os.path.join(PROJECT_ROOT, 'database', 'royalburger.fdb')  
    FIREBIRD_HOST = 'localhost'  
    FIREBIRD_PORT = 3050  
    FIREBIRD_USER = 'SYSDBA'  
    FIREBIRD_PASSWORD = 'sysdba'  
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