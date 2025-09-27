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
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')  
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')  
    MAIL_DEFAULT_SENDER = ('Royal Burger', MAIL_USERNAME)  
